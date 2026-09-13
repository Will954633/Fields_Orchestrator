#!/usr/bin/env python3
"""domain_sold_sync.py — sold listings from Domain's GraphQL searchListings(Sold),
houses AND units, across the GC-wide suburb set.

WHAT THIS IS FOR (read before assuming it's a median source)
------------------------------------------------------------
Discovered 2026-09-13 during the GC-wide overview build: Domain's `searchListings`
Sold surface returns only **agent-listed** sales — it structurally lacks the
Valuer-General (VG) government-transfer records that onthehouse carries. Measured,
last 12 months:
    Robina    — Domain 124 house sales vs onthehouse 306 (105 of them VG)
    Helensvale— Domain 199 vs onthehouse 270 (153 VG)
VG sales sit at a different (usually lower) price point, so Domain's median is
biased high and its completeness varies suburb-by-suburb. Therefore:

    onthehouse (agent + VG + RP) is the COMPLETE source for medians/volume.
    Domain searchListings is NOT a substitute and must not be the median base.

Domain's genuine strength here is **days on market**: it carries the listing date
AND the exact sold date, and DOM only exists for agent-listed sales anyway (a
government transfer has no marketing campaign). So this feeds:
  - DOM by property type / bedroom / suburb (the "which type sells fastest" work)
  - exact sold dates + prices as a cross-check on onthehouse
  - a per-suburb Domain-vs-onthehouse reconciliation

Contract
--------
- Writes `system_monitor.domain_sold`. NEVER writes Gold_Coast.
- Costs Bright Data per request (Domain is Akamai-blocked; see domain_graphql.py).
  Scoped to the recent window that fits inside the 1000-result cap (one pagination
  pass per suburb, newest-first) — for the biggest GC suburb (Robina) 1000 results
  reach back to 2013, so `--since` covers the useful window without date-windowing.
  `--deep-windows` adds year-by-year windowing for full history if ever needed.
- Immutable history: a sold record is never expired.

Usage:
  python3 scripts/domain_sold_sync.py --all-gc --since 2016-01-01 --dry-run
  python3 scripts/domain_sold_sync.py --all-gc --since 2016-01-01
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_client
from shared.domain_graphql import execute
from job_status import job_run
from onthehouse.suburbs import CORE, ALL_GC

COLL = "domain_sold"
PAGE_SIZE = 200
MAX_PAGES = 5                       # Domain caps searchListings at ~1000 results
PAUSE_S = 0.4                       # politeness between Bright Data calls
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"])}

# Domain searchListings propertyType strings (differ from onthehouse's sold-index
# labels — verified 2026-09-13). Attached/unit classes:
_UNIT_TYPES = {"ApartmentUnitFlat", "Townhouse", "Duplex", "Villa", "SemiDetached",
               "BlockOfUnits", "Studio", "Penthouse", "Terrace", "NewApartments"}
_HOUSE_TYPES = {"House", "NewHouseLand", "NewHomeDesigns"}

_QUERY = """query Sold($p: SearchListingsParametersInput!) {
  searchListings(searchParams: $p) {
    totalResults
    results { ... on SearchListingsResultListing {
      listingId propertyType bedrooms bathrooms carspaces dateListed
      displayableAddress { unitNumber streetNumber street suburb { name } postcode state }
      soldData { soldDate { day month year } soldPrice { displayPrice } }
    } }
  }
}"""


def _iso(sd: dict | None):
    if not sd or not sd.get("year"):
        return None
    m = _MONTHS.get(sd.get("month"), 0)
    if not m:
        return None
    return f"{int(sd['year'])}-{m:02d}-{int(sd['day']):02d}"


def _price(pd: dict | None):
    """Exact dollar figure from a displayPrice, or None (ranges/'Contact agent')."""
    import re
    s = (pd or {}).get("displayPrice") or ""
    if "-" in s or "to" in s.lower():
        return None
    m = re.findall(r"[\d,]{4,}", s)
    if not m:
        return None
    v = int(m[0].replace(",", ""))
    return v if 100_000 < v < 50_000_000 else None


def _dwelling(pt: str) -> str:
    if pt in _HOUSE_TYPES:
        return "house"
    if pt in _UNIT_TYPES:
        return "unit"
    return "other"   # VacantLand, Rural, AcreageSemiRural, DevelopmentSite, …


def crawl_suburb(sub: dict, since: str) -> tuple[list[dict] | None, dict]:
    """Paginate Sold results newest-first until below `since` or the cap. Returns
    (rows, meta). rows None on transport failure (signals retry/skip upstream)."""
    t0 = time.monotonic()
    rows, pages, stopped_early = [], 0, False
    for pg in range(1, MAX_PAGES + 1):
        params = {
            "locations": [{"suburb": sub["suburb"].title(), "state": "QLD",
                           "postcode": sub["slug"].rsplit("-", 1)[1],
                           "includeSurroundingSuburbs": False}],
            "listingType": "Sold", "page": pg, "pageSize": PAGE_SIZE,
        }
        data = execute(_QUERY, {"p": params})
        if data is None:
            return (None, {"pages": pages, "secs": round(time.monotonic() - t0, 1)}) if not rows else (rows, {"pages": pages, "partial": True, "secs": round(time.monotonic() - t0, 1)})
        res = (data.get("searchListings") or {}).get("results") or []
        pages += 1
        if not res:
            break
        page_min_date = "9999"
        for x in res:
            sd = (x.get("soldData") or {})
            sold = _iso(sd.get("soldDate"))
            if not sold:
                continue
            page_min_date = min(page_min_date, sold)
            if sold < since:
                continue
            a = x.get("displayableAddress") or {}
            suburb_name = ((a.get("suburb") or {}).get("name") or "").strip()
            # Only keep records whose own suburb matches the target (searchListings
            # can bleed neighbours); compare on the plain suburb name.
            if suburb_name and suburb_name.lower() != sub["suburb"].lower():
                continue
            listed = str(x.get("dateListed") or "")[:10] or None
            dom = None
            if listed and sold >= listed:
                dom = (date.fromisoformat(sold) - date.fromisoformat(listed)).days
                if dom > 730:            # stale re-list, not a real campaign length
                    dom = None
            rows.append({
                "listing_id": x.get("listingId"),
                "suburb_key": sub["slug"],
                "suburb": suburb_name or sub["suburb"],
                "address": " ".join(str(a.get(k) or "") for k in
                                     ("unitNumber", "streetNumber", "street")).strip(),
                "postcode": (a.get("postcode")),
                "property_type": x.get("propertyType"),
                "dwelling": _dwelling(x.get("propertyType") or ""),
                "beds": x.get("bedrooms"), "baths": x.get("bathrooms"),
                "car_spaces": x.get("carspaces"),
                "listed_date": listed,
                "sold_date": sold,
                "sale_price": _price(sd.get("soldPrice")),
                "dom_days": dom,
            })
        time.sleep(PAUSE_S)
        # Results are newest-first; once a whole page is older than `since`, stop.
        if page_min_date < since:
            stopped_early = True
            break
    return rows, {"pages": pages, "secs": round(time.monotonic() - t0, 1),
                  "reached_since": stopped_early}


def sync(db, scope: list[dict], since: str, dry_run: bool) -> dict:
    now = datetime.now(timezone.utc)
    coll = db[COLL]
    st = {"suburbs_ok": 0, "suburbs_failed": 0, "seen": 0, "new": 0, "updated": 0,
          "houses": 0, "units": 0, "with_dom": 0, "with_price": 0, "pages": 0}
    for sub in scope:
        rows, meta = crawl_suburb(sub, since)
        if rows is None:
            st["suburbs_failed"] += 1
            print(f"{sub['slug']}: FETCH FAILED")
            continue
        st["suburbs_ok"] += 1
        st["pages"] += meta.get("pages", 0)
        h = sum(1 for r in rows if r["dwelling"] == "house")
        u = sum(1 for r in rows if r["dwelling"] == "unit")
        st["houses"] += h
        st["units"] += u
        print(f"{sub['slug']}: {len(rows)} sold ({h} house / {u} unit) "
              f"{meta.get('pages')}pg {meta.get('secs')}s"
              f"{'' if meta.get('reached_since') else ' [hit cap before `since`]'}")
        for r in rows:
            st["seen"] += 1
            if r["dom_days"] is not None:
                st["with_dom"] += 1
            if r["sale_price"] is not None:
                st["with_price"] += 1
            if dry_run:
                continue
            _id = f"{r['suburb_key']}|{r['listing_id']}|{r['sold_date']}"
            res = coll.update_one(
                {"_id": _id},
                {"$set": {**r, "last_seen": now, "source": "domain_searchlistings"},
                 "$setOnInsert": {"first_seen": now}},
                upsert=True)
            if res.upserted_id is not None:
                st["new"] += 1
            elif res.modified_count:
                st["updated"] += 1
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-gc", action="store_true",
                    help="all 82 GC suburbs (default: core 3)")
    ap.add_argument("--since", default="2016-01-01",
                    help="earliest sold date to keep (default 2016-01-01)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    scope = ALL_GC if args.all_gc else CORE
    db = get_client()["system_monitor"]

    if args.dry_run:
        st = sync(db, scope, args.since, dry_run=True)
        print(f"\ndry-run: {st['seen']} sold ({st['houses']}h/{st['units']}u), "
              f"{st['with_dom']} with DOM, {st['with_price']} priced, "
              f"{st['suburbs_failed']} fail")
        return

    job = "domain_sold_sync_gc_wide" if args.all_gc else "domain_sold_sync"
    with job_run(job, cadence_hours=31 * 24 if args.all_gc else 24,
                 title="Domain Sold (searchListings, agent-listed, DOM source)") as beat:
        st = sync(db, scope, args.since, dry_run=False)
        if st["suburbs_ok"] == 0 or st["suburbs_failed"] > st["suburbs_ok"]:
            raise RuntimeError(
                f"reached {st['suburbs_ok']} suburb(s), {st['suburbs_failed']} failed — "
                "Domain/Bright Data broken, not an empty market")
        beat.detail = (f"{st['seen']} sold ({st['houses']}h/{st['units']}u) across "
                       f"{st['suburbs_ok']} suburbs; {st['new']} new, {st['with_dom']} "
                       f"with DOM, {st['with_price']} priced, {st['suburbs_failed']} fail")
        beat.metrics = st
        print("\n" + beat.detail)


if __name__ == "__main__":
    main()
