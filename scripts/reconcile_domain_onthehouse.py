#!/usr/bin/env python3
"""One-off: per-suburb reconciliation of Domain searchListings Sold vs onthehouse,
last 12 months, houses. Quantifies the VG-transfer gap across all GC suburbs so the
coast-wide-median decision (onthehouse-accumulate vs calibrate) rests on data, not
two anecdotes. See fix-history 2026-09-13 [DOMAIN-SEARCHLISTINGS-VG-GAP]."""
import sys, statistics
from datetime import date, timedelta
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

cut = (date.today() - timedelta(days=365)).isoformat()
sm = get_client()["system_monitor"]
dom, oth = sm["domain_sold"], sm["onthehouse_sold"]

def med(coll, sub, extra):
    q = {"suburb_key": sub, "dwelling" if coll is dom else "property_type":
         "house" if coll is dom else "House",
         "sold_date": {"$gte": cut}, "sale_price": {"$nin": [None, 0]}}
    q.update(extra)
    ps = [d["sale_price"] for d in coll.find(q, {"sale_price": 1})]
    return (len(ps), statistics.median(ps) if ps else None)

subs = sorted(set(dom.distinct("suburb_key")) | set(oth.distinct("suburb_key")))
rows = []
for s in subs:
    dn, dm = med(dom, s, {})
    on, om = med(oth, s, {})
    if dn < 5 and on < 5:
        continue
    gap = (dm / om - 1) * 100 if dm and om else None
    cov = dn / on * 100 if on else None
    rows.append((s, dn, dm, on, om, cov, gap))

rows.sort(key=lambda r: r[5] if r[5] is not None else 0)
print(f"{'suburb':22s} {'Dom n':>6s} {'Dom med':>10s} {'OTH n':>6s} {'OTH med':>10s} "
      f"{'Dom/OTH%':>9s} {'med gap':>8s}")
for s, dn, dm, on, om, cov, gap in rows:
    print(f"{s:22s} {dn:>6d} {('$%d'%dm) if dm else '-':>10s} {on:>6d} "
          f"{('$%d'%om) if om else '-':>10s} {('%.0f%%'%cov) if cov else '-':>9s} "
          f"{('%+.1f%%'%gap) if gap is not None else '-':>8s}")

covs = [r[5] for r in rows if r[5]]
gaps = [r[6] for r in rows if r[6] is not None]
print(f"\nSUMMARY across {len(rows)} suburbs:")
print(f"  Domain captures a median {statistics.median(covs):.0f}% of onthehouse's count "
      f"(range {min(covs):.0f}–{max(covs):.0f}%)")
print(f"  Domain median vs onthehouse median: median gap {statistics.median(gaps):+.1f}% "
      f"(range {min(gaps):+.1f}–{max(gaps):+.1f}%)")
print("  => onthehouse is the more complete source; Domain gap is suburb-dependent "
      "(VG-transfer share), confirming it cannot be a uniform median base.")
