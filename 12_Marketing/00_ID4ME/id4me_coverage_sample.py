#!/usr/bin/env python3
"""Measure what fraction of our address universe ID4ME can actually service.

Samples residential houses across the three target suburbs, runs each through
ID4ME, and reports coverage: does the address resolve, does it yield people, and
crucially how STALE those people are. "Has a record" and "has a usable current
contact" are very different numbers, and only the second one is worth paying for.

    python3 id4me_coverage_sample.py --n 200
    python3 id4me_coverage_sample.py --n 60 --suburb robina

Writes a JSON summary plus a per-address CSV to output/ (gitignored - the CSV
contains personal information).

Deliberately does NOT write to Mongo. This is a measurement, not an enrichment
run; storing PII for 200 households to answer a coverage question would be
collecting far more than the question needs.
"""

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ID4ME_DIR = Path(__file__).resolve().parent / "unzipped_20260813" / "01_ID4ME"
sys.path.insert(0, str(ID4ME_DIR))

import lookup as id4me_lookup          # noqa: E402
from api import AuthError, Id4meClient  # noqa: E402

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db  # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
OUT_DIR = Path(__file__).resolve().parent / "output"
TODAY = date.today()


def sample_addresses(n_per_suburb: int, suburbs: list[str]) -> list[dict]:
    """Random residential houses that carry a usable street address."""
    db = get_gold_coast_db()
    out = []
    for suburb in suburbs:
        docs = db[suburb].aggregate([
            {"$match": {"property_type": "House",
                        "address": {"$exists": True, "$nin": [None, ""]}}},
            {"$sample": {"size": n_per_suburb}},
            {"$project": {"address": 1, "listing_status": 1}},
        ])
        for d in docs:
            out.append({"suburb": suburb, "address": d["address"],
                        "listing_status": d.get("listing_status") or "off_market"})
    return out


def _age_years(iso_date: str) -> float | None:
    if not iso_date:
        return None
    try:
        return (TODAY - datetime.strptime(iso_date[:10], "%Y-%m-%d").date()).days / 365.25
    except ValueError:
        return None


def assess(result: dict) -> dict:
    """Reduce one lookup to the coverage facts we actually care about."""
    people = result.get("people") or []
    ages = [a for a in (_age_years(p.get("source_date_latest")) for p in people)
            if a is not None]
    freshest = min(ages) if ages else None

    mobiles = {m for p in people for m in (p.get("mobiles") or set())}
    emails = {e for p in people for e in (p.get("emails") or set())}
    landlines = {l for p in people for l in (p.get("landlines") or set())}
    blocked = {b for p in people
               for b in (p.get("dncr_blocked") or "").split("; ") if b}

    # A contact is only useful if it is BOTH recent and reachable. Counting
    # "has a phone number" alone overstates coverage badly - most of these
    # households have a landline attached to an occupant who left years ago.
    def fresh_people(max_years):
        return [p for p in people
                if (a := _age_years(p.get("source_date_latest"))) is not None
                and a <= max_years]

    fresh2 = fresh_people(2)
    fresh2_mobile = any(p.get("mobiles") for p in fresh2)

    return {
        "status": result["status"],
        "resolved": result["status"] == "ok",
        "people_count": len(people),
        "raw_count": result.get("result_count", 0),
        "freshest_years": round(freshest, 2) if freshest is not None else None,
        "has_people": bool(people),
        "fresh_1y": bool(fresh_people(1)),
        "fresh_2y": bool(fresh2),
        "fresh_5y": bool(fresh_people(5)),
        "has_mobile": bool(mobiles),
        "has_email": bool(emails),
        "has_landline": bool(landlines),
        "has_callable": bool((mobiles | landlines) - blocked),
        "fresh2_and_mobile": fresh2_mobile,
        "n_mobiles": len(mobiles),
        "n_emails": len(emails),
        "n_blocked": len(blocked),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=200, help="total addresses to sample")
    ap.add_argument("--suburb", action="append", help="restrict to suburb(s)")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    suburbs = args.suburb or SUBURBS
    per = max(1, args.n // len(suburbs))
    targets = sample_addresses(per, suburbs)
    print(f"sampled {len(targets)} addresses across {len(suburbs)} suburb(s)", flush=True)

    try:
        client = Id4meClient()
    except AuthError as exc:
        print(f"ID4ME authentication failed: {exc}")
        return 2

    # A dead session makes EVERY address return "address_not_found", which is
    # indistinguishable from genuinely absent data - so an unguarded run would
    # publish "0% coverage" as a measurement. Prove the pipeline works on a
    # known-good address first, and abort if the opening stretch is all misses.
    control = "20 Chantilly Place, Robina, QLD 4226"
    probe = id4me_lookup.lookup(client, control, compliance=False)
    if probe["status"] != "ok":
        print(f"ABORT: control address returned {probe['status']} "
              f"({probe.get('error')}). The lookup path is broken - any coverage "
              f"number from this run would measure our own session, not the data.")
        return 2
    print(f"control OK: {len(probe['people'])} people at {control}", flush=True)

    rows = []
    for i, t in enumerate(targets, 1):
        res = id4me_lookup.lookup(client, t["address"], compliance=True)
        row = {**t, **assess(res)}
        rows.append(row)

        if i == 15 and not any(r["resolved"] for r in rows):
            print("ABORT: 15/15 addresses unresolved. That is a broken session or "
                  "a wrong address format, not 0% coverage. Nothing written.")
            return 2
        if i % 10 == 0 or i == len(targets):
            ok = sum(r["resolved"] for r in rows)
            f2 = sum(r["fresh_2y"] for r in rows)
            print(f"[{i}/{len(targets)}] resolved {ok} | fresh<=2y {f2}", flush=True)
        if i < len(targets):
            time.sleep(args.delay)

    n = len(rows)
    def pct(key):
        c = sum(bool(r[key]) for r in rows)
        return {"n": c, "pct": round(100 * c / n, 1)}

    ages = [r["freshest_years"] for r in rows if r["freshest_years"] is not None]
    summary = {
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": n,
        "suburbs": suburbs,
        "address_resolved": pct("resolved"),
        "any_people": pct("has_people"),
        "freshest_record_1y": pct("fresh_1y"),
        "freshest_record_2y": pct("fresh_2y"),
        "freshest_record_5y": pct("fresh_5y"),
        "has_mobile": pct("has_mobile"),
        "has_email": pct("has_email"),
        "has_landline": pct("has_landline"),
        "has_callable_phone": pct("has_callable"),
        "USABLE_fresh2y_with_mobile": pct("fresh2_and_mobile"),
        "median_freshest_age_years": round(statistics.median(ages), 2) if ages else None,
        "mean_people_per_resolved": round(
            statistics.mean([r["people_count"] for r in rows if r["resolved"]] or [0]), 1),
        "status_breakdown": dict(Counter(r["status"] for r in rows)),
        "by_suburb": {},
    }
    for s in suburbs:
        sub = [r for r in rows if r["suburb"] == s]
        if sub:
            summary["by_suburb"][s] = {
                "n": len(sub),
                "resolved_pct": round(100 * sum(r["resolved"] for r in sub) / len(sub), 1),
                "fresh2y_pct": round(100 * sum(r["fresh_2y"] for r in sub) / len(sub), 1),
                "usable_pct": round(100 * sum(r["fresh2_and_mobile"] for r in sub) / len(sub), 1),
            }

    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    (OUT_DIR / f"coverage_{stamp}.json").write_text(json.dumps(summary, indent=2))
    with open(OUT_DIR / f"coverage_{stamp}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(json.dumps(summary, indent=2))
    print(f"\n  {OUT_DIR}/coverage_{stamp}.json\n  {OUT_DIR}/coverage_{stamp}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
