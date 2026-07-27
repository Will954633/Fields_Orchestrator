"""
validate_coverage_gaps.py — triage Gold_Coast.propradar_coverage_gaps (addresses PropRadar
recorded a sale at that we don't hold) into a clean enrichment queue before any Domain scrape.

PropRadar records have quirks (property-type leaked into the address, wrong postcode), so we
gate them: a gap is only enrichable if its postcode matches the suburb and the address parses
cleanly. Invalid rows are marked status='invalid' (not deleted — auditable); valid rows stay
'pending' for the enrichment step (Domain profile scrape → property doc → off-market page).

Usage:
    python3 scripts/propradar/validate_coverage_gaps.py            # report only
    python3 scripts/propradar/validate_coverage_gaps.py --apply    # write status
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db, cosmos_retry  # noqa: E402

EXPECTED_PC = {"robina": "4226", "burleigh_waters": "4220", "varsity_lakes": "4227"}
NON_ADDRESS_TOKENS = {"DETACHED", "UNIT", "HOUSE", "TOWNHOUSE", "APARTMENT", "VILLA", "DUPLEX"}


def validate(addr: str, suburb_key: str):
    if not addr:
        return "invalid", "empty address"
    pcs = re.findall(r"\b(\d{4})\b", addr)
    pc = pcs[-1] if pcs else None
    exp = EXPECTED_PC.get(suburb_key)
    if pc and exp and pc != exp:
        return "invalid", f"postcode {pc} != {exp} (wrong locality)"
    toks = {t.strip().upper() for t in addr.replace(",", " ").split()}
    bad = toks & NON_ADDRESS_TOKENS
    if bad:
        return "invalid", f"property-type token in address: {','.join(bad)}"
    if not re.match(r"^\s*\d", addr):
        return "invalid", "no leading street number"
    return "valid", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    db = get_gold_coast_db()
    coll = db["propradar_coverage_gaps"]
    rows = list(coll.find({}))
    valid, invalid = [], []
    for r in rows:
        status, reason = validate(r.get("address", ""), r.get("suburb_key", ""))
        (valid if status == "valid" else invalid).append((r, reason))
        if args.apply and status == "invalid" and r.get("status") != "invalid":
            cosmos_retry(lambda r=r, reason=reason: coll.update_one(
                {"_id": r["_id"]}, {"$set": {"status": "invalid", "invalid_reason": reason}}),
                f"gap-invalid:{r['_id']}")

    print(f"coverage gaps: {len(rows)} | enrichable(valid): {len(valid)} | invalid: {len(invalid)}")
    print("\n-- INVALID (excluded from enrichment) --")
    for r, reason in invalid:
        print(f"  {r.get('address'):<52} [{r.get('suburb_key')}] — {reason}")
    print("\n-- VALID enrichment queue (Domain-profile scrape → property doc → off-market page) --")
    for r, _ in valid[:40]:
        print(f"  {r.get('address'):<52} [{r.get('suburb_key')}] pid={r.get('_id')}")
    print("\n" + ("APPLIED status writes" if args.apply else "(report only — pass --apply to mark invalid rows)"))


if __name__ == "__main__":
    main()
