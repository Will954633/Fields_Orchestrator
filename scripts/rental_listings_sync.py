#!/usr/bin/env python3
"""
rental_listings_sync.py — current FOR-LEASE listings, the missing half of the
"can we actually sell this?" guard.

Why
---
We must never post marketing to a home the owner is leasing: they have told the
market what they want to do with it, and it isn't sell. Until now we had no way to
know. PropRadar has NO lease data (verified 2026-08-01: `/properties/{id}.rental` is
an AVM estimate, `listings?listing_type=rent` silently ignores the param, `/rentals`
404s), and `Gold_Coast.listing_status` only carries for_sale / under_contract /
sold / withdrawn.

Source: onthehouse.com.au (CoreLogic-backed). Chosen over Domain's property-profile
because it serves a per-SUBURB rental index — one page gives every current rental in
the suburb instead of one request per address — and because it fetches directly from
this VM with no Bright Data proxy cost (Domain is Akamai-blocked from our IP; see
shared/domain_fetch.py).

Writes system_monitor.rental_listings. A listing that disappears from its suburb's
index is marked active=False rather than deleted, so we keep the history and can see
"was leased, no longer is".

Usage:
  python3 scripts/rental_listings_sync.py --dry-run
  python3 scripts/rental_listings_sync.py
  python3 scripts/rental_listings_sync.py --suburbs robina-4226
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from curl_cffi import requests as cffi
from shared.db import get_client
from job_status import job_run

BASE = "https://www.onthehouse.com.au/property-for-rent/qld"
COLL = "rental_listings"
MAX_PAGES = 6           # the loop stops earlier once the target suburb stops growing
PAGE_PAUSE_S = 1.5      # be a polite client
# Each index page is 0.5-2.8 MB and every query also returns surrounding suburbs, so a
# naive "stop when no NEW record appears" rule keeps paging long after the suburb we
# asked for is exhausted. Stop on the target suburb instead — the neighbours get their
# own pass anyway, since they're all in SUBURBS.
PAGE_BUDGET_S = 420     # hard ceiling for one suburb, so the nightly job can't hang
# Backstop for listings picked up from SURROUNDING suburbs we never query directly:
# they can never be reconciled, so retire them if they go unseen this long.
STALE_AFTER_DAYS = 10

# Suburbs we hold contacts in. Keep aligned with propradar/market_status.SUBURB_POSTCODES.
SUBURBS = [
    "robina-4226", "varsity-lakes-4227", "burleigh-waters-4220",
    "burleigh-heads-4220", "mermaid-waters-4218", "merrimac-4226",
    "worongary-4213", "clear-island-waters-4226", "palm-beach-4221",
    "miami-4220", "reedy-creek-4227", "mudgeeraba-4213",
]

# The page embeds structured records — {"category":"RentalListing","address":{...}} —
# which beats scraping the rendered cards: real address COMPONENTS, listed date, agency.
_REC_START = re.compile(r'\{"category":"RentalListing"')

# Street types are abbreviated inconsistently across sources (PL/PLACE, CCT/CIRCUIT,
# DR/DRIVE). The match key drops the street type entirely rather than trying to
# normalise every variant — number + street name + suburb is already unique.
_STREET_TYPES = {
    "st", "street", "rd", "road", "ave", "av", "avenue", "dr", "drive", "ct", "court",
    "pl", "place", "cres", "crescent", "cct", "circuit", "cir", "circle", "bvd", "blvd",
    "boulevard", "pde", "parade", "tce", "terrace", "ln", "lane", "way", "trl", "trail",
    "cl", "close", "gr", "grove", "esp", "esplanade", "pkwy", "parkway", "sq", "square",
    "tr", "track", "rise", "view", "vista", "walk", "mews", "loop", "link", "chase",
}


def _clean(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def address_key(address: str) -> str | None:
    """Source-agnostic join key: unit | street number | street name | suburb.

    Deliberately drops the street TYPE and all punctuation, so
    "70/22 BARBET PL, BURLEIGH WATERS, QLD 4220" and
    "70/22 Barbet Place, Burleigh Waters QLD 4220" collapse to the same key.
    """
    a = re.sub(r"\bqld\b|\b4\d{3}\b", " ", _clean(address))
    parts = [p.strip() for p in a.split(",") if p.strip()] or [a.strip()]
    street = parts[0]
    suburb = parts[1] if len(parts) > 1 else ""
    if not suburb:  # no comma — assume trailing tokens are the suburb
        toks = street.split()
        cut = next((i for i, t in enumerate(toks) if t in _STREET_TYPES), None)
        if cut is None:
            return None
        street, suburb = " ".join(toks[: cut + 1]), " ".join(toks[cut + 1:])
    toks = [t for t in street.split() if t]
    nums = [t for t in toks if t.isdigit()]
    name = [t for t in toks if not t.isdigit() and t not in _STREET_TYPES]
    if not nums or not name:
        return None
    unit, number = (nums[0], nums[1]) if len(nums) >= 2 else ("", nums[0])
    return f"{unit}|{number}|{' '.join(name)}|{' '.join(suburb.split())}".strip()


def key_from_components(addr: dict) -> str | None:
    unit = (addr.get("unitNumber") or "").strip()
    num = (addr.get("streetNumber") or "").strip()
    name = _clean(addr.get("streetName") or "").strip()
    sub = _clean(addr.get("suburb") or "").strip()
    if not (num and name and sub):
        return None
    # "22-24" style ranges -> first number, matching how we store addresses
    num = num.split("-")[0].strip()
    unit = unit.split("-")[0].strip()
    return f"{unit}|{num}|{name}|{sub}"


def _json_objects(html: str):
    """Yield the RentalListing records embedded in the page (brace-matched)."""
    for m in _REC_START.finditer(html):
        depth, i, n = 0, m.start(), len(html)
        in_str = esc = False
        while i < n:
            ch = html[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        yield json.loads(html[m.start():i + 1])
                    except Exception:
                        pass
                    break
            i += 1


def fetch(url: str) -> str | None:
    try:
        r = cffi.get(url, impersonate="chrome120", timeout=45)
        return r.text if r.status_code == 200 else None
    except Exception as e:
        print(f"  fetch failed {url}: {type(e).__name__} {str(e)[:120]}")
        return None


def parse_suburb(sub: str) -> list[dict] | None:
    """Every current rental listing in one suburb. None = the fetch failed (which must
    NOT be read as 'no rentals here' — that would wrongly clear every address)."""
    out, seen, ok_any = {}, set(), False
    t0 = time.time()
    for page in range(1, MAX_PAGES + 1):
        if time.time() - t0 > PAGE_BUDGET_S:
            print(f"  {sub}: page budget reached at page {page}")
            break
        url = f"{BASE}/{sub}" + (f"?page={page}" if page > 1 else "")
        html = fetch(url)
        if html is None:
            break
        ok_any = True
        new = 0          # new records anywhere
        new_here = 0     # new records in the suburb we actually asked for
        for rec in _json_objects(html):
            a = rec.get("address") or {}
            lid = str(rec.get("id") or rec.get("clPropertyId") or "")
            key = key_from_components(a)
            if not key or key in seen:
                continue
            seen.add(key)
            new += 1
            lst = rec.get("listing") or {}
            true_sub = f"{_clean(a.get('suburb') or '').strip().replace(' ', '-')}-{a.get('postCode') or ''}"
            if true_sub == sub:
                new_here += 1
            out[key] = {
                "match_key": key, "suburb_key": true_sub, "found_via": sub,
                "address": a.get("formattedAddress"),
                "unit": a.get("unitNumber"), "street_number": a.get("streetNumber"),
                "street": a.get("streetName"), "street_type": a.get("streetType"),
                "suburb": a.get("suburb"), "postcode": a.get("postCode"),
                "property_type": rec.get("type"), "beds": rec.get("beds"),
                "listed_date": lst.get("listedDate"),
                "agency": ((lst.get("agency") or {}).get("name")),
                "listing_id": lid,
            }
        if not new_here:
            break
        time.sleep(PAGE_PAUSE_S)
    return list(out.values()) if ok_any else None


def sync(db, suburbs: list[str], dry_run: bool = False) -> dict:
    """Fetch every requested suburb's index, then reconcile in ONE pass.

    Each index page also returns surrounding suburbs (the site sets
    includeSurroundSuburbs), so a listing is filed under its OWN suburb, not the one
    we happened to query through. Reconciliation is deferred until all fetches are in,
    otherwise a Burleigh Waters listing seen via the Robina page would be deactivated
    when the Burleigh Waters pass ran.
    """
    now = datetime.now(timezone.utc)
    coll = db[COLL]
    stats = {"suburbs_ok": 0, "suburbs_failed": 0, "active": 0, "new": 0, "ended": 0}

    all_rows, covered = {}, set()
    for sub in suburbs:
        rows = parse_suburb(sub)
        if rows is None:
            stats["suburbs_failed"] += 1
            print(f"{sub}: FETCH FAILED — its listings will NOT be deactivated")
            continue
        stats["suburbs_ok"] += 1
        covered.add(sub)
        mine = [r for r in rows if r["suburb_key"] == sub]
        print(f"{sub}: {len(mine)} in-suburb (+{len(rows) - len(mine)} nearby)")
        for r in rows:
            all_rows[r["match_key"]] = r
        if dry_run:
            for r in mine[:3]:
                print(f"    {r['address']}  (listed {r.get('listed_date')}, {r.get('agency')})")

    stats["active"] = len(all_rows)
    if dry_run:
        return stats

    for key, r in all_rows.items():
        res = coll.update_one(
            {"_id": key},
            {"$set": {**r, "active": True, "last_seen": now, "source": "onthehouse"},
             "$setOnInsert": {"first_seen": now}}, upsert=True)
        if res.upserted_id is not None:
            stats["new"] += 1

    # Only ever deactivate inside a suburb whose own index we successfully fetched.
    if covered:
        ended = coll.update_many(
            {"suburb_key": {"$in": sorted(covered)}, "active": True,
             "_id": {"$nin": list(all_rows)}},
            {"$set": {"active": False, "ended_at": now}})
        stats["ended"] = ended.modified_count

    # Staleness backstop. Each index also returns SURROUNDING suburbs, so we pick up
    # listings in suburbs we never query directly (Mermaid Beach, Broadbeach, ...).
    # Those can never be reconciled by the rule above and would stay "active" forever —
    # a stale rental record silently blocks an address that is no longer leased.
    # Anything not re-seen in STALE_AFTER_DAYS is retired regardless of suburb.
    stale_cut = now - timedelta(days=STALE_AFTER_DAYS)
    stale = coll.update_many(
        {"active": True, "last_seen": {"$lt": stale_cut}},
        {"$set": {"active": False, "ended_at": now, "ended_reason": "stale"}})
    stats["stale_retired"] = stale.modified_count
    return stats


def is_for_lease(db, address: str) -> dict | None:
    """Active rental listing for this address, if any. Used by the sellability guard."""
    k = address_key(address)
    return db[COLL].find_one({"_id": k, "active": True}) if k else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburbs", nargs="*", default=SUBURBS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_client()["system_monitor"]
    with job_run("rental_listings_sync", cadence_hours=24,
                 title="Rental Listings (onthehouse) → lease guard") as beat:
        st = sync(db, args.suburbs, args.dry_run)
        beat.detail = (f"{st['active']} active across {st['suburbs_ok']} suburb(s); "
                       f"{st['new']} new, {st['ended']} ended, "
                       f"{st.get('stale_retired', 0)} stale retired, "
                       f"{st['suburbs_failed']} fetch failure(s)")
        beat.metrics = st
        print("\n" + beat.detail)


if __name__ == "__main__":
    main()
