#!/usr/bin/env python3
"""
leads_came_to_market.py — move leads whose home has gone on the market off the
working list, onto a "Came to Market" tab where we can still see them.

Why
---
A lead whose home is now listed with another agent is not a lead any more, and
leaving them on "All Leads" quietly poisons everything downstream: they get
counted in pool sizes, they get picked up by mail-out selection, and the one
person reading the sheet has no way to tell them apart. Worse, they are the most
interesting rows we have — these are the ones we LOST, and the reason to keep
them is to be able to count that and look at why.

So they move rather than vanish. The row is carried across whole (including any
Status/notes Will typed into it) and stamped with what we detected and when.

What counts as "on the market"
------------------------------
Three independent sale sources, because none is complete on its own — PropRadar,
our own Gold_Coast scrape, and onthehouse. ANY of them saying so is decisive.
This is the same `market_status_for` used by the Activity tab, imported rather
than reimplemented, so the two sheets can never disagree.

⚠ Two rules that are easy to get wrong and expensive to get wrong:

1. **`Listing Nearing Expiry` leads are EXEMPT.** Their whole reason for existing
   is that the home IS on the market and the Form 6 exclusive agency is running
   out. Sweeping them would delete the worklist we deliberately built. See
   `propradar/market_status.py` — the same carve-out is documented there.

2. **A row is only moved on a positive listing signal, never on an error.** A
   PropRadar timeout returns `on_market: None`, and `verdict()` errs closed with
   "could not check" — correct for "should we mail?", catastrophic here, because
   an API wobble would move the whole list into Lost. Detection keys on a source
   affirmatively saying "listed", so an outage moves nothing.

Usage
  python3 scripts/leads_came_to_market.py --dry-run    # show what would move
  python3 scripts/leads_came_to_market.py              # do it
  python3 scripts/leads_came_to_market.py --max-calls 400
"""
from __future__ import annotations
import argparse
import os
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "propradar"))

from shared.db import get_client                      # noqa: E402
from job_status import job_run                        # noqa: E402
import market_status as ms                            # noqa: E402
from live_leads_to_sheet import (                     # noqa: E402
    LIVE_SPREADSHEET_ID, GC_DB, AEST, get_sheets, tab_id, set_env_from_file,
    TAB as LEADS_TAB, HEADERS as LEAD_HEADERS,
)

LOST_TAB = "Came to Market"
LEDGER_DB = "system_monitor"
LEDGER_COLL = "leads_came_to_market"

# Appended to the right of the lead's own columns, so the carried row keeps its
# original shape and column meanings.
EXTRA_HEADERS = ["Detected (AEST)", "Signal", "Days on market", "Asking", "Why"]
HEADERS = LEAD_HEADERS + EXTRA_HEADERS

SOURCE_COL, ADDR_COL, LEAD_ID_COL = 1, 7, 12          # B, H, M (0-indexed)

# See rule 1 in the module docstring. Matched as a substring because the sheet
# stores combined sources like "Analyse Your Home / Form Submission".
EXEMPT_SOURCES = ("Listing Nearing Expiry",)


def _cell(row, i):
    return (row[i] if i < len(row) else "").strip()


def ensure_tab(svc, ssid, dry_run=False):
    """Return the sheetId of the Lost tab, creating it with headers if absent."""
    sid = tab_id(svc, ssid, LOST_TAB)
    if sid is not None:
        return sid
    if dry_run:
        print(f"(would create tab '{LOST_TAB}')")
        return None
    res = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"addSheet": {"properties": {"title": LOST_TAB,
                                     "gridProperties": {"frozenRowCount": 1}}}}
    ]}).execute()
    sid = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range=f"'{LOST_TAB}'!A1",
        valueInputOption="RAW", body={"values": [HEADERS]}).execute()
    print(f"Created tab '{LOST_TAB}'.")
    return sid


def resolved_addresses(db):
    """slug/key -> canonical postal address, from the cadastral resolver.

    The sheet stores off-market lookups without state or postcode ("37 Majorca
    Crescent Varsity Lakes"). PropRadar's search REQUIRES a postcode, so an
    unresolved address silently returns "no postcode" and would never be
    detected as listed. Resolving first is what makes the sweep see them.
    """
    out = {}
    for d in db["address_resolution"].find({}, {"canonical": 1, "raw": 1}):
        canon = d.get("canonical")
        if not canon:
            continue
        out[ms._key(canon)] = canon
        if d.get("raw"):
            out[ms._key(d["raw"])] = canon
    return out


def listing_signal(st):
    """(is_listed, signal_name). Positive evidence only — never an error."""
    if st.get("on_market"):
        return True, "PropRadar"
    if st.get("gc_for_sale"):
        return True, "our own listings data"
    if st.get("oth_for_sale"):
        return True, "onthehouse"
    return False, ""


def sweep(svc, ssid, db, gc_db, *, max_calls=500, dry_run=False):
    """Detect + move. Returns a metrics dict for the heartbeat."""
    from engagement_activity_to_sheet import market_status_for

    rows = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{LEADS_TAB}'!A2:O10000").execute().get("values", [])
    total = len(rows)

    resolved = resolved_addresses(db)
    targets, exempt = {}, 0
    for i, r in enumerate(rows):
        addr, src = _cell(r, ADDR_COL), _cell(r, SOURCE_COL)
        if not addr:
            continue
        if any(e in src for e in EXEMPT_SOURCES):
            exempt += 1
            continue
        canon = resolved.get(ms._key(addr), addr)
        targets.setdefault(canon, []).append(i)

    if not targets:
        return {"leads": total, "checked": 0, "exempt": exempt, "moved": 0,
                "sources_live": 0}

    status = market_status_for(list(targets), db, gc_db, max_calls, resolved=None)

    # Rule 7b: prove the sweep could actually have found something. If every sale
    # source is dark, "nothing is listed" is not a finding, it is a broken run —
    # and moving zero rows would look identical to a healthy night.
    import onthehouse_listings_sync as ohl
    oth_live = db[ohl.COLL].count_documents({"active": True})
    gc_live = sum(gc_db[s].count_documents({"listing_status": "for_sale"})
                  for s in ("robina", "varsity_lakes", "burleigh_waters"))
    pr_ok = sum(1 for v in status.values() if not v.get("error"))
    sources_live = sum(1 for x in (pr_ok, gc_live, oth_live) if x)

    moved, ts = [], datetime.now(AEST).strftime("%Y-%m-%d %H:%M")
    for canon, idxs in targets.items():
        st = status.get(canon) or {}
        is_listed, signal = listing_signal(st)
        if not is_listed:
            continue
        _, why = ms.verdict(st)
        dom = st.get("days_on_market")
        lo, hi = st.get("asking_low"), st.get("asking_high")
        asking = (f"${lo:,.0f}" if lo and lo == hi else
                  f"${lo:,.0f}–${hi:,.0f}" if lo and hi else
                  f"${lo:,.0f}" if lo else "")
        for i in idxs:
            moved.append({"row": i + 2, "values": rows[i], "canonical": canon,
                          "signal": signal, "dom": dom, "asking": asking, "why": why,
                          "lead_id": _cell(rows[i], LEAD_ID_COL), "detected": ts})

    metrics = {"leads": total, "checked": len(targets), "exempt": exempt,
               "moved": len(moved), "sources_live": sources_live,
               "propradar_ok": pr_ok, "gc_listed": gc_live, "oth_listed": oth_live}

    if not moved:
        print(f"No leads have come to market ({len(targets)} address(es) checked).")
        return metrics

    print(f"\n{len(moved)} lead(s) have come to market:")
    for m in moved:
        dom = f", {m['dom']}d on market" if m["dom"] is not None else ""
        print(f"   row {m['row']:>4}  {_cell(m['values'], ADDR_COL)[:52]:<54} "
              f"[{m['signal']}{dom}]")

    if dry_run:
        print("\n(dry run — nothing moved)")
        return metrics

    sid = ensure_tab(svc, ssid)
    svc.spreadsheets().values().append(
        spreadsheetId=ssid, range=f"'{LOST_TAB}'!A1",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [
            m["values"] + [""] * (len(LEAD_HEADERS) - len(m["values"]))
            + [m["detected"], m["signal"],
               str(m["dom"]) if m["dom"] is not None else "", m["asking"], m["why"]]
            for m in moved]}).execute()

    # Delete bottom-up: each deleteDimension shifts everything below it, so
    # ascending order would delete the wrong rows after the first one.
    leads_sid = tab_id(svc, ssid, LEADS_TAB)
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"deleteDimension": {"range": {"sheetId": leads_sid, "dimension": "ROWS",
                                       "startIndex": m["row"] - 1, "endIndex": m["row"]}}}
        for m in sorted(moved, key=lambda m: m["row"], reverse=True)]}).execute()

    led = db[LEDGER_COLL]
    for m in moved:
        led.replace_one({"_id": m["lead_id"] or f"{m['canonical']}:{m['detected']}"},
                        {"lead_id": m["lead_id"], "address": m["canonical"],
                         "detected_at": datetime.now(AEST), "signal": m["signal"],
                         "days_on_market": m["dom"], "asking": m["asking"],
                         "why": m["why"], "source": _cell(m["values"], SOURCE_COL),
                         "lead_date": _cell(m["values"], 0)}, upsert=True)

    print(f"\nMoved {len(moved)} row(s) to '{LOST_TAB}'.")
    return metrics


def run(spreadsheet_id=LIVE_SPREADSHEET_ID, max_calls=500, dry_run=False):
    set_env_from_file()
    svc = get_sheets()
    client = get_client()
    try:
        db, gc_db = client["system_monitor"], client[GC_DB]
        m = sweep(svc, spreadsheet_id, db, gc_db, max_calls=max_calls, dry_run=dry_run)

        # Rule 7b — assert an outcome, don't just fail to throw.
        if m["leads"] and not m["checked"]:
            raise RuntimeError(
                f"{m['leads']} leads on the sheet but 0 addresses checked — "
                "address column or exemption logic is broken, not an empty list")
        if m["checked"] and not m.get("sources_live"):
            raise RuntimeError(
                "every sale source is dark (PropRadar erroring, Gold_Coast has no "
                "live listings, onthehouse table empty) — 'nothing came to market' "
                "is unprovable, not a clean result")
        return m
    finally:
        client.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--max-calls", type=int, default=500,
                    help="PropRadar call budget for this run (hobby tier = 20k/mo)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        m = run(args.spreadsheet_id, args.max_calls, dry_run=True)
        print(f"\n{m}")
        return

    with job_run("leads_came_to_market", cadence_hours=24,
                 title="Leads — came to market sweep") as beat:
        m = run(args.spreadsheet_id, args.max_calls)
        beat.metrics = m
        beat.detail = (f"{m['moved']} moved to '{LOST_TAB}' of {m['checked']} checked "
                       f"({m['exempt']} expiry-worklist exempt)")


if __name__ == "__main__":
    main()
