#!/usr/bin/env python3
"""Build the ranked flyer-mailout candidate list.

Scans Gold_Coast target-suburb collections for owner-occupier properties
(classified from the sale/rental timeline via occupancy_classifier), held at
least --min-years, and not currently listed/sold. Output is a CSV ranked by
tenure (longest-held first) — the strongest "next move is a sale" prior.

NOTE: cadastral-only docs store their address at scraped_data.address (upper
case), not top-level address — the fallback below is load-bearing (2026-07-17:
without it ~1,600 candidates were dropped).

Usage:
    python3 scripts/samantha/flyer_candidates.py [--min-years 7] [--out PATH]

Before mailing any wave: run a fresh listing-status verification on the
selected addresses — mongo listing_status can be stale (see memory:
verify_fresh_listing_status).
"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.mongo_client_factory import get_mongo_client
from scripts.property_reports.occupancy_classifier import (
    classify_from_timeline,
    normalise_stored_timeline,
)

SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
FIELDS = ["address", "suburb", "years_held", "last_sale_date",
          "last_sale_price", "confidence", "listing_status", "intent_signal"]


def worklist_rows() -> list[dict]:
    """No-contact high/medium lead_worklist addresses — behavioural intent beats tenure prior,
    so these rank at the TOP of the flyer list (Will-approved 2026-07-17)."""
    sm = get_mongo_client()["system_monitor"]
    rows = []
    for d in sm["lead_worklist"].find(
            {"is_test": False, "priority": {"$in": ["high", "medium"]},
             "address": {"$nin": [None, ""]}},
            {"address": 1, "priority": 1, "property": 1, "occupancy": 1,
             "years_held": 1, "last_sold_date": 1, "last_sold_price": 1, "email": 1}):
        if d.get("email"):
            continue  # contactable leads get outreach drafts, not flyers
        prop = d.get("property") or {}
        if prop.get("listing_status") in ("for_sale", "sold"):
            continue
        if (d.get("occupancy") or {}).get("type") == "investor":
            continue  # never mail tenanted addresses
        rows.append({"address": d["address"],
                     "suburb": prop.get("suburb") or "",
                     "years_held": d.get("years_held") or "",
                     "last_sale_date": d.get("last_sold_date") or "",
                     "last_sale_price": d.get("last_sold_price") or "",
                     "confidence": (d.get("occupancy") or {}).get("confidence") or "",
                     "listing_status": prop.get("listing_status") or "not_listed",
                     "intent_signal": f"worklist_{d.get('priority')}"})
    return rows


def _norm(a: str) -> str:
    return " ".join(a.lower().replace(",", " ").split())


def _as_str(v) -> str:
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for key in ("full", "full_address", "display", "displayAddress", "street"):
            if isinstance(v.get(key), str) and v[key].strip():
                return v[key].strip()
    return ""


def build(min_years: float) -> list[dict]:
    db = get_mongo_client()["Gold_Coast"]
    now = datetime.now(timezone.utc)
    out, seen = [], set()
    for sub in SUBURBS:
        cur = db[sub].find(
            {"scraped_data.property_timeline": {"$exists": True, "$ne": []},
             "listing_status": {"$nin": ["for_sale", "sold"]}},
            {"address": 1, "scraped_data.address": 1,
             "scraped_data.property_timeline": 1, "listing_status": 1})
        n = 0
        for d in cur:
            n += 1
            sd = d.get("scraped_data", {}) or {}
            addr = _as_str(d.get("address")) or _as_str(sd.get("address")).title()
            if not addr:
                continue
            k = _norm(addr)
            if k in seen:
                continue
            r = classify_from_timeline(normalise_stored_timeline(d))
            if not r or r.get("type") != "owner_occupier":
                continue
            ev = r.get("evidence") or {}
            lsd = ev.get("last_sale_date")
            if not lsd:
                continue
            try:
                held = datetime.strptime(lsd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                years = (now - held).days / 365.25
            except ValueError:
                continue
            if years < min_years:
                continue
            seen.add(k)
            out.append({"address": addr, "suburb": sub,
                        "years_held": round(years, 1), "last_sale_date": lsd,
                        "last_sale_price": ev.get("last_sale_price") or "",
                        "confidence": r.get("confidence"),
                        "listing_status": d.get("listing_status") or "not_listed"})
        print(f"{sub}: scanned {n} timeline docs", file=sys.stderr)
    out.sort(key=lambda r: -r["years_held"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-years", type=float, default=7)
    ap.add_argument("--out", default=None,
                    help="output CSV path (default: output/flyer_candidates_extended_<date>.csv)")
    ap.add_argument("--include-worklist", action="store_true",
                    help="prepend no-contact high/medium lead_worklist addresses (intent > tenure)")
    args = ap.parse_args()

    rows = build(args.min_years)
    for r in rows:
        r.setdefault("intent_signal", "")
    if args.include_worklist:
        wl = worklist_rows()
        have = {_norm(r["address"]) for r in wl}
        rows = wl + [r for r in rows if _norm(r["address"]) not in have]
        print(f"worklist intent addresses prepended: {len(wl)}", file=sys.stderr)
    out = args.out or f"output/flyer_candidates_extended_{datetime.now().date()}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} unique candidates -> {out}")


if __name__ == "__main__":
    main()
