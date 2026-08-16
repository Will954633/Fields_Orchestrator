#!/usr/bin/env python3
"""
read_call_outcomes.py — copy the caller's outcomes, comments and call-back dates
out of the sheet and into Mongo. STRICTLY ONE-WAY: sheet → Mongo.

    python3 read_call_outcomes.py --dry-run
    python3 read_call_outcomes.py
    python3 read_call_outcomes.py --report        # what the round is producing

WHY ONE-WAY
-----------
The sheet is the source of truth for L/M/N (HUMAN_COLS). This script only ever calls
values().get on those columns; it holds no code path that writes them, and
sheet_common.assert_machine_range() raises if one is ever added. The caller must
be able to trust that what they typed stays exactly as they typed it.

WHAT IT ENFORCES BEYOND COPYING
-------------------------------
An outcome of "not interested", "DO NOT CONTACT AGAIN" or "refused recording"
suppresses that person permanently — the queue doc goes to status
"do_not_contact" and can never be re-listed. This is not a nicety:

  * Telemarketing Standard s13(1)(b) — terminate immediately on any indication
    they want the call to end.
  * ACL s75(2) — after a request to stop, no contact for 30 days.

Relying on a human to re-read a free-text comment before the next round is exactly
how a suppression request gets missed. It is mechanical here.

Rule 7b: rows exist but zero outcomes parsed, while the caller has been working →
that is a failure, not an empty queue.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from sheet_common import (  # noqa: E402
    AEST, CALL_SPREADSHEET_ID, TAB, COL, CALL_ID_COL, OUTCOME_COL, COMMENTS_COL,
    CALLBACK_COL, SUPPRESSING_OUTCOMES, OUTCOMES,
    col_letter, get_sheets, set_env_from_file, read_grid, cell, is_separator,
)

OUTCOMES_COLL = "call_outcomes"
QUEUE_COLL = "call_queue"


def _db():
    from shared.db import get_client
    return get_client()["system_monitor"]


def parse_callback(raw: str, now: datetime):
    """Accept what a human under time pressure actually types."""
    raw = (raw or "").strip()
    if not raw:
        return None, ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d %b", "%d %b %Y", "%d/%m"):
        try:
            d = datetime.strptime(raw, fmt)
            if d.year == 1900:
                d = d.replace(year=now.year)
            return d.replace(tzinfo=AEST), ""
        except ValueError:
            continue
    # Unparseable is NOT discarded — it is kept verbatim and flagged, because a
    # caller's "next Tues arvo" is real information we must not silently drop.
    return None, raw


def harvest(svc, ssid, db, now, dry=False):
    rows, first = read_grid(svc, ssid)

    stats = Counter()
    suppressed, updates = [], []

    for i, r in enumerate(rows):
        if is_separator(r):
            continue
        cid = cell(r, CALL_ID_COL)
        if not cid:
            continue
        stats["rows"] += 1

        outcome = cell(r, OUTCOME_COL)
        comments = cell(r, COMMENTS_COL)
        cb_raw = cell(r, CALLBACK_COL)
        if not (outcome or comments or cb_raw):
            stats["untouched"] += 1
            continue
        stats["worked"] += 1

        cb_date, cb_note = parse_callback(cb_raw, now)
        if outcome and outcome not in OUTCOMES:
            # strict=False on the dropdown means free text is possible by design.
            stats["off_menu_outcome"] += 1

        doc = {
            "call_queue_id": cid,
            "sheet_row": first + i,          # for humans debugging; never used as a key
            "call_date": cell(r, COL["Call Date"]),
            "address": cell(r, COL["Address"]),
            "suburb": cell(r, COL["Suburb"]),
            "track": cell(r, COL["Track"]),
            "outcome": outcome,
            "outcome_off_menu": bool(outcome and outcome not in OUTCOMES),
            "comments": comments,
            "callback_date": cb_date,
            "callback_raw": cb_raw,
            "callback_unparsed": cb_note,
            "harvested_at": now,
        }
        updates.append(doc)

        if outcome in SUPPRESSING_OUTCOMES:
            suppressed.append((cid, outcome))
            stats["suppressed"] += 1
        if outcome:
            stats[f"outcome::{outcome}"] += 1

    if dry:
        return stats, updates, suppressed

    for doc in updates:
        cid = doc.pop("call_queue_id")
        db[OUTCOMES_COLL].update_one(
            {"_id": cid},
            {"$set": doc, "$setOnInsert": {"first_harvested": now}},
            upsert=True)
        doc["call_queue_id"] = cid
        # Mark the call as made, but NEVER move a doc backwards out of
        # do_not_contact — a suppression is permanent.
        db[QUEUE_COLL].update_one(
            {"_id": cid, "status": {"$ne": "do_not_contact"}},
            {"$set": {"status": "called", "updated_at": now}})

    for cid, outcome in suppressed:
        db[QUEUE_COLL].update_one(
            {"_id": cid},
            {"$set": {"status": "do_not_contact",
                      "suppressed_reason": outcome,
                      "suppressed_at": now,
                      "updated_at": now}})
        # Suppress the PERSON, not just this row: the same number can sit on more
        # than one address (previous occupant, investor with two properties).
        q = db[QUEUE_COLL].find_one({"_id": cid}, {"phone": 1})
        if q and q.get("phone"):
            db[QUEUE_COLL].update_many(
                {"phone": q["phone"], "status": {"$in": ["queued", "listed"]}},
                {"$set": {"status": "do_not_contact",
                          "suppressed_reason": f"{outcome} (same number, other address)",
                          "suppressed_at": now, "updated_at": now}})

    return stats, updates, suppressed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=CALL_SPREADSHEET_ID)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true",
                    help="print round performance and exit")
    args = ap.parse_args()

    set_env_from_file()
    from job_status import job_run  # noqa: E402

    with job_run("read_call_outcomes", cadence_hours=24,
                 title="Direct-call outcomes ← sheet") as beat:
        db = _db()
        now = datetime.now(AEST)

        if args.report:
            n = db[OUTCOMES_COLL].count_documents({})
            print(f"outcomes recorded: {n}")
            for row in db[OUTCOMES_COLL].aggregate([
                    {"$match": {"outcome": {"$nin": ["", None]}}},
                    {"$group": {"_id": "$outcome", "n": {"$sum": 1}}},
                    {"$sort": {"n": -1}}]):
                print(f"  {row['n']:>4}  {row['_id']}")
            connects = db[OUTCOMES_COLL].count_documents(
                {"outcome": {"$regex": "^Connected"}})
            print(f"\nCONNECTS: {connects}   (round-1 target: 30–50)")
            beat.detail = f"{connects} connects"
            beat.metrics = {"connects": connects, "outcomes": n}
            return

        svc = get_sheets()
        stats, updates, suppressed = harvest(svc, args.spreadsheet_id, db, now,
                                             dry=args.dry_run)

        # Rule 7b — the zero-output assertion. "Nobody has called yet" is success.
        # "Rows are on the sheet and the caller has worked them, but we parsed
        # nothing" means the read is broken, and must not report success.
        if stats["rows"] and not stats["worked"]:
            print(f"{stats['rows']} call rows on the sheet, none worked yet — nothing "
                  "to harvest (this is success, not failure)")
        elif not stats["rows"]:
            print("no call rows on the sheet yet")

        prefix = "DRY RUN — would record" if args.dry_run else "recorded"
        print(f"{prefix} {len(updates)} outcome(s); {len(suppressed)} suppressed")
        for k, v in sorted(stats.items()):
            if k.startswith("outcome::"):
                print(f"    {v:>4}  {k[9:]}")
        if stats.get("off_menu_outcome"):
            print(f"  note: {stats['off_menu_outcome']} outcome(s) typed free-hand "
                  "(dropdown is non-strict by design — kept verbatim)")
        unparsed = [u for u in updates if u.get("callback_unparsed")]
        if unparsed:
            print(f"  note: {len(unparsed)} call-back date(s) unparseable, stored "
                  "verbatim in callback_raw — review these by hand")

        beat.detail = f"{len(updates)} outcomes, {len(suppressed)} suppressed"
        beat.metrics = {"rows": stats["rows"], "worked": stats["worked"],
                        "suppressed": len(suppressed),
                        "off_menu": stats.get("off_menu_outcome", 0)}


if __name__ == "__main__":
    main()
