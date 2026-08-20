#!/usr/bin/env python3
"""
leads_prune_nonleads.py — take our own test builds, demos and speculative
pre-builds back off the Live Leads Tracker.

Why
---
The sheet is insert-only by design, so Will's manual Status/notes edits are never
clobbered. The cost of that design is that it has no way to take anything back:
once a row is inserted it is there forever, even after the underlying record is
flagged as a test, marked internal, or turns out never to have been a lead at all.

Found 2026-08-17 while assembling a mail-out: rows sitting in the mailer-ready
pool that were our own test builds and speculative pre-builds. Two of them
(`18-collingwood-avenue-robina`, `25-huntingdale-crescent-robina`) were already
`is_test:True, owner.is_internal:True` and the generators had correctly STOPPED
emitting them — they survived purely because nothing ever reconciles the sheet
against source. The next stage would have posted a homeowner analysis to a house
on the strength of our own QA.

Safety rule
-----------
A row is pruned only when its source document EXISTS and positively classifies as
not-a-lead (`live_leads_to_sheet.is_not_a_lead`). A document that has gone MISSING
is left strictly alone — a dropped collection, a bad query or a half-finished
migration would otherwise wipe the real list, and "the doc isn't there" is exactly
the shape a transient fault takes. Absence is never evidence here (Rule 8).

Rows are moved to a "Not a Lead" tab rather than deleted, so a wrong call is
visible and reversible instead of silent.

Usage
  python3 scripts/leads_prune_nonleads.py --dry-run
  python3 scripts/leads_prune_nonleads.py
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

from bson import ObjectId                              # noqa: E402
from shared.db import get_client                       # noqa: E402
from job_status import job_run                         # noqa: E402
from live_leads_to_sheet import (                      # noqa: E402
    LIVE_SPREADSHEET_ID, AEST, get_sheets, tab_id, set_env_from_file,
    is_not_a_lead, TAB as LEADS_TAB, HEADERS as LEAD_HEADERS, TEST_EMAILS,
)

PRUNE_TAB = "Not a Lead"
LEDGER_COLL = "leads_pruned_nonleads"
EXTRA_HEADERS = ["Pruned (AEST)", "Why"]
HEADERS = LEAD_HEADERS + EXTRA_HEADERS
LEAD_ID_COL, ADDR_COL = 12, 7


def _cell(row, i):
    return (row[i] if i < len(row) else "").strip()


def ensure_tab(svc, ssid):
    sid = tab_id(svc, ssid, PRUNE_TAB)
    if sid is not None:
        return sid
    res = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"addSheet": {"properties": {"title": PRUNE_TAB,
                                     "gridProperties": {"frozenRowCount": 1}}}}]}).execute()
    sid = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range=f"'{PRUNE_TAB}'!A1",
        valueInputOption="RAW", body={"values": [HEADERS]}).execute()
    print(f"Created tab '{PRUNE_TAB}'.")
    return sid


def fb_is_not_a_lead(d: dict) -> str | None:
    """Reason this fb_leads doc is not a callable lead, or None if it is one.

    Out-of-market copy-test leads (SEQ ex-GC) must receive NOTHING and must never
    reach Will's callable list — a Gold Coast report in a Brisbane inbox burns the
    brand (Will, 2026-07-28). The puller tags them `test_market`; the sheet filtered
    on `is_test`, so 7 of them sat on the callable list until 2026-08-20.
    """
    if d.get("is_test") or d.get("test_market"):
        return "test_market (out-of-market copy test)"
    email = ((d.get("fields") or {}).get("email") or "").lower()
    if email in TEST_EMAILS:
        return "test email"
    return None


def classify(rows, db):
    """-> (to_prune, checked, missing). property_reports- and fb_leads-backed rows are
    checkable; other sources have their own generators and are left alone."""
    to_prune, checked, missing = [], 0, 0
    for i, r in enumerate(rows):
        lid = _cell(r, LEAD_ID_COL)
        if lid.startswith("fb_leads:"):
            d = db["fb_leads"].find_one({"_id": lid.split(":", 1)[1]})
            if d is None:
                missing += 1      # same safety rule — absence is never evidence
                continue
            checked += 1
            why = fb_is_not_a_lead(d)
            if why:
                to_prune.append({"row": i + 2, "values": r, "why": why,
                                 "slug": (d.get("fields") or {}).get("email", ""),
                                 "lead_id": lid})
            continue
        if not lid.startswith("property_reports:"):
            continue
        raw = lid.split(":", 1)[1]
        try:
            d = db["property_reports"].find_one({"_id": ObjectId(raw)})
        except Exception:
            d = db["property_reports"].find_one({"_id": raw})
        if d is None:
            missing += 1          # see the safety rule — never prune on absence
            continue
        checked += 1
        why = is_not_a_lead(d)
        if why:
            to_prune.append({"row": i + 2, "values": r, "why": why,
                             "slug": d.get("slug", ""), "lead_id": lid})
    return to_prune, checked, missing


def sweep(svc, ssid, db, *, dry_run=False):
    rows = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{LEADS_TAB}'!A2:O10000").execute().get("values", [])
    to_prune, checked, missing = classify(rows, db)

    metrics = {"leads": len(rows), "checked": checked, "missing_doc": missing,
               "pruned": len(to_prune)}

    if missing:
        print(f"  {missing} row(s) have no source document — left in place on purpose "
              f"(absence is not evidence).")
    if not to_prune:
        print(f"Nothing to prune ({checked} property_reports-backed row(s) checked).")
        return metrics

    print(f"\n{len(to_prune)} row(s) are not real leads:")
    for p in to_prune:
        print(f"   row {p['row']:>4}  {_cell(p['values'], ADDR_COL)[:50]:<52} [{p['why']}]")

    if dry_run:
        print("\n(dry run — nothing moved)")
        return metrics

    ts = datetime.now(AEST).strftime("%Y-%m-%d %H:%M")
    ensure_tab(svc, ssid)
    svc.spreadsheets().values().append(
        spreadsheetId=ssid, range=f"'{PRUNE_TAB}'!A1",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [p["values"] + [""] * (len(LEAD_HEADERS) - len(p["values"]))
                         + [ts, p["why"]] for p in to_prune]}).execute()

    leads_sid = tab_id(svc, ssid, LEADS_TAB)
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"deleteDimension": {"range": {"sheetId": leads_sid, "dimension": "ROWS",
                                       "startIndex": p["row"] - 1, "endIndex": p["row"]}}}
        for p in sorted(to_prune, key=lambda p: p["row"], reverse=True)]}).execute()

    for p in to_prune:
        db[LEDGER_COLL].replace_one(
            {"_id": p["lead_id"]},
            {"lead_id": p["lead_id"], "slug": p["slug"], "why": p["why"],
             "pruned_at": datetime.now(AEST),
             "address": _cell(p["values"], ADDR_COL)}, upsert=True)

    print(f"\nMoved {len(to_prune)} row(s) to '{PRUNE_TAB}'.")
    return metrics


def run(spreadsheet_id=LIVE_SPREADSHEET_ID, dry_run=False):
    set_env_from_file()
    svc = get_sheets()
    client = get_client()
    try:
        m = sweep(svc, spreadsheet_id, client["system_monitor"], dry_run=dry_run)
        # Rule 7b. The sheet is full of property_reports-backed rows; checking none
        # of them means the lead-id format changed or the lookup broke, which would
        # otherwise report as a clean "nothing to prune".
        if m["leads"] and not m["checked"]:
            raise RuntimeError(
                f"{m['leads']} rows on the sheet but 0 were checkable — the "
                "'property_reports:<id>' lead-id format or the lookup has broken")
        return m
    finally:
        client.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        print(run(args.spreadsheet_id, dry_run=True))
        return

    with job_run("leads_prune_nonleads", cadence_hours=24,
                 title="Leads — prune test/internal rows") as beat:
        m = run(args.spreadsheet_id)
        beat.metrics = m
        beat.detail = (f"{m['pruned']} pruned to '{PRUNE_TAB}' of {m['checked']} checked"
                       + (f"; {m['missing_doc']} left (no source doc)"
                          if m["missing_doc"] else ""))


if __name__ == "__main__":
    main()
