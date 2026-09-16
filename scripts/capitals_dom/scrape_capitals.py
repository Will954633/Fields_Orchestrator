#!/usr/bin/env python3
"""scrape_capitals.py — pull Domain sold days-on-market for the matched capital
panels selected by screen_panel.py, into system_monitor.domain_sold_capitals.

Reuses domain_sold_sync.crawl_suburb (Domain internal GraphQL searchListings, via
Bright Data) — the SAME method that populates system_monitor.domain_sold for the
Gold Coast, so every city's DOM is measured identically (soldDate − dateListed,
agent-listed sales, capped 730d). Scrapes the UNION of the house and unit panels
per city (a suburb in only one panel still contributes only its in-band property
type at aggregation time; here we just collect all its sold rows).

Writes a SEPARATE collection from the GC data so the two never mix. Self-reports
via job_run with a Rule-7b zero-output assertion.

Usage:
  python3 scripts/capitals_dom/scrape_capitals.py --since 2016-01-01 [--dry-run] [--city NSW]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))

from shared.db import get_client  # noqa: E402
from job_status import job_run  # noqa: E402
from domain_sold_sync import crawl_suburb  # noqa: E402

PANEL = HERE / "panel.json"
COLL = "domain_sold_capitals"


def union_suburbs(panel, city=None):
    """Union of house+unit panel members per city, de-duplicated by slug."""
    seen, out = {}, []
    for kind in ("house_panel", "unit_panel"):
        for st, subs in panel[kind].items():
            if city and st != city:
                continue
            for s in subs:
                if s["slug"] not in seen:
                    seen[s["slug"]] = True
                    out.append({"suburb": s["suburb"], "slug": s["slug"], "state": s["state"]})
    return out


def scrape(since, dry_run, city=None):
    panel = json.loads(PANEL.read_text())
    scope = union_suburbs(panel, city)
    db = get_client()["system_monitor"]
    coll = db[COLL]
    now = datetime.now(timezone.utc)
    st = {"suburbs_ok": 0, "suburbs_failed": 0, "seen": 0, "new": 0,
          "houses": 0, "units": 0, "with_dom": 0, "oldest": "9999", "newest": "0000"}
    print(f"Scraping {len(scope)} panel suburbs (since {since})…\n")
    for sub in scope:
        rows, meta = crawl_suburb(sub, since)
        if rows is None:
            st["suburbs_failed"] += 1
            print(f"  {sub['slug']}: FETCH FAILED")
            continue
        st["suburbs_ok"] += 1
        h = sum(1 for r in rows if r["dwelling"] == "house")
        u = sum(1 for r in rows if r["dwelling"] == "unit")
        st["houses"] += h
        st["units"] += u
        for r in rows:
            st["seen"] += 1
            if r["dom_days"] is not None:
                st["with_dom"] += 1
            st["oldest"] = min(st["oldest"], r["sold_date"])
            st["newest"] = max(st["newest"], r["sold_date"])
            if dry_run:
                continue
            _id = f"{r['suburb_key']}|{r['listing_id']}|{r['sold_date']}"
            res = coll.update_one(
                {"_id": _id},
                {"$set": {**r, "state": sub["state"], "last_seen": now,
                          "source": "domain_searchlistings"},
                 "$setOnInsert": {"first_seen": now}},
                upsert=True)
            if res.upserted_id is not None:
                st["new"] += 1
        print(f"  {sub['slug']:<26} {len(rows)} sold ({h}h/{u}u) "
              f"{meta.get('pages')}pg {meta.get('secs')}s"
              f"{'' if meta.get('reached_since') else ' [hit cap before since]'}")
        time.sleep(0.3)
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2016-01-01")
    ap.add_argument("--city", choices=["NSW", "VIC", "QLD"], help="one city only")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        st = scrape(args.since, dry_run=True, city=args.city)
        print(f"\ndry-run: {st['seen']} sold ({st['houses']}h/{st['units']}u), "
              f"{st['with_dom']} with DOM, range {st['oldest']}..{st['newest']}, "
              f"{st['suburbs_failed']} fail")
        return

    with job_run("domain_sold_capitals", cadence_hours=31 * 24,
                 title="Domain Sold DOM — capital-city matched panels") as beat:
        st = scrape(args.since, dry_run=False, city=args.city)
        if st["suburbs_ok"] == 0 or st["suburbs_failed"] > st["suburbs_ok"]:
            raise RuntimeError(
                f"reached {st['suburbs_ok']} suburb(s), {st['suburbs_failed']} failed — "
                "Domain/Bright Data broken, not an empty market")
        if st["with_dom"] < 500:
            raise RuntimeError(
                f"only {st['with_dom']} sold rows with DOM across the panels — "
                "scrape under-delivered, not writing a hollow comparison")
        beat.detail = (f"{st['seen']} sold ({st['houses']}h/{st['units']}u), "
                       f"{st['with_dom']} with DOM, {st['new']} new, "
                       f"range {st['oldest']}..{st['newest']}, {st['suburbs_failed']} fail")
        beat.metrics = {k: v for k, v in st.items() if k not in ("oldest", "newest")}
        print("\n" + beat.detail)


if __name__ == "__main__":
    main()
