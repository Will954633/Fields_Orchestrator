#!/usr/bin/env python3
"""
market_status.py — "can we actually sell this address?" guard, via PropRadar.

Why this exists
---------------
Before any marketing asset goes to a physical address we have to know the property
is actually sellable by us. Two disqualifiers (Will, 2026-08-01):

  * CURRENTLY FOR SALE — we can't sell a home that's already listed with another
    agent. The one exception is a listing nearing the end of its 90-day Form 6
    exclusive agency, which has its OWN process (the "Listing Nearing Expiry"
    worklist source) and must not be swept into a generic mail-out.
  * CURRENTLY FOR LEASE / RENT — the owner has told the market what they want to do
    with the property, and it isn't sell.

In both cases the person browsing that address is far more likely a BUYER or a
RENTER than the owner, which also invalidates the owner-lookup inference.

What this module can and cannot tell you
----------------------------------------
PropRadar answers the FOR-SALE half properly, and better than our own
`Gold_Coast` collections: it covers every suburb (not just our three), returns
`on_market` on the cheap search call, gives `days_on_market` for the Form 6 test,
and returns a canonical address+postcode we can use to correct our own records.

It does NOT answer the lease half. Verified against the live API 2026-08-01:
  - `/properties/{id}.rental` is an AVM ESTIMATE ({estimated_weekly, yield,
    confidence:"low"}) — not a live lease listing.
  - `/suburbs/QLD/{suburb}/listings?listing_type=rent` silently IGNORES the
    parameter (the echoed `query` object doesn't even contain it) and returns
    for-sale listings.
  - `/suburbs/QLD/{suburb}/rentals` 404s.
We have no lease source anywhere else either (`Gold_Coast.listing_status` only has
for_sale / under_contract / sold / withdrawn; there is no rent scrape). So lease
status is reported honestly as UNKNOWN rather than silently assumed clear — see
`lease_status` in the returned dict. Do not treat "no lease found" as "not leased".

Results are cached in system_monitor.propradar_market_status (default 7 days) so a
nightly job doesn't re-spend quota on the same addresses. Hobby tier = 20,000
calls/month, ~1-2 calls per uncached address.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import propradar_client as pr

CACHE_DB = "system_monitor"
CACHE_COLL = "propradar_market_status"
CACHE_DAYS = 7

# A Form 6 exclusive agency runs 90 days. Anything at/past this is in the window
# where the "why it hasn't sold" approach applies — a DIFFERENT play to a mail-out,
# so we flag it rather than either mailing them or silently dropping them.
FORM6_DAYS = 90
FORM6_NEAR_DAYS = 75

LEASE_UNKNOWN = ("unknown — PropRadar has no lease/rental listing data and we have "
                 "no other rent source; do not read this as 'not leased'")


def _now():
    return datetime.now(timezone.utc)


def _key(address: str) -> str:
    return " ".join((address or "").lower().replace(",", " ").split())


# PropRadar's /properties/search REQUIRES a postcode (400 invalid_postcode without
# one), but many of our addresses are rebuilt from slugs and carry only a suburb.
SUBURB_POSTCODES = {
    "robina": "4226", "varsity lakes": "4227", "burleigh waters": "4220",
    "burleigh heads": "4220", "mermaid waters": "4218", "mermaid beach": "4218",
    "merrimac": "4226", "worongary": "4213", "clear island waters": "4226",
    "palm beach": "4221", "miami": "4220", "reedy creek": "4227",
    "mudgeeraba": "4213", "carrara": "4211", "nerang": "4211",
}


def postcode_for(address: str) -> str | None:
    """Postcode from the address text, else inferred from a known suburb name."""
    import re
    m = re.search(r"\b(4\d{3})\b", address or "")
    if m:
        return m.group(1)
    low = (address or "").lower()
    # longest suburb name first so "burleigh waters" wins over "burleigh heads"
    for name in sorted(SUBURB_POSTCODES, key=len, reverse=True):
        if name in low:
            return SUBURB_POSTCODES[name]
    return None


def check(address: str, postcode: str | None = None, db=None,
          max_age_days: int = CACHE_DAYS, spend: dict | None = None) -> dict:
    """Market status for one address. Cached; `spend` accumulates API call counts."""
    key = _key(address)
    coll = db[CACHE_COLL] if db is not None else None
    if coll is not None:
        hit = coll.find_one({"_id": key})
        seen_at = hit.get("checked_at") if hit else None
        if seen_at is not None and seen_at.tzinfo is None:
            seen_at = seen_at.replace(tzinfo=timezone.utc)  # Mongo returns naive UTC
        # Never serve a cached ERROR — retry it, or one transient 400 sticks for a week.
        if seen_at and not (hit or {}).get("error") and \
                seen_at > _now() - timedelta(days=max_age_days):
            return hit

    out = {"_id": key, "query_address": address, "checked_at": _now(),
           "lease_status": LEASE_UNKNOWN, "source": "propradar"}
    pc = postcode or postcode_for(address)
    if not pc:
        out["error"] = "no postcode: PropRadar search requires one and none could be inferred"
        out["on_market"] = None
        if coll is not None:
            coll.replace_one({"_id": key}, out, upsert=True)
        return out
    try:
        d, _ = pr.call("/properties/search", {"address": address, "postcode": pc})
        if spend is not None:
            spend["calls"] = spend.get("calls", 0) + 1
        out["found"] = bool(d.get("found"))
        out["property_id"] = d.get("property_id")
        out["on_market"] = bool(d.get("on_market"))
        matches = d.get("matches") or []
        if matches:
            # PropRadar's canonical address — our stored postcodes are not always right
            # (819 Legend Trail is recorded QLD 4213 in crm_contacts, 4226 here).
            out["canonical_address"] = matches[0].get("address")

        if out["on_market"] and out.get("property_id"):
            time.sleep(0.5)  # 2 rps sustained
            p, _ = pr.call(f"/properties/{out['property_id']}")
            if spend is not None:
                spend["calls"] = spend.get("calls", 0) + 1
            lst = p.get("listing") or {}
            out["days_on_market"] = lst.get("days_on_market")
            out["sale_type"] = lst.get("sale_type")
            out["asking_low"] = lst.get("asking_price_low")
            out["asking_high"] = lst.get("asking_price_high")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        out["on_market"] = None  # unknown, NOT false

    if coll is not None:
        coll.replace_one({"_id": key}, out, upsert=True)
    return out


def verdict(st: dict) -> tuple[bool, str]:
    """(may_we_market_to_this_address, human reason).

    What `found` actually means (measured 2026-08-01 over 180 addresses): PropRadar's
    /properties/search is a LISTING + SOLD index, not a cadastral database. 18 of 180
    addresses were found and 17 of those 18 were on_market; a verified real address
    that sold in March 2026 returns found=True/on_market=False, while ordinary
    never-listed houses return found=False. So `found=False` reads as "no current
    listing", which is the signal we want — treating it as "unverified" blocked 162
    of 180 addresses for the wrong reason.

    Sale side is therefore answered. Lease side is NOT — see LEASE_UNKNOWN.
    """
    if st.get("error"):
        return False, f"NO — could not check sale status ({st['error'][:80]}); erring closed"

    dom = st.get("days_on_market")
    if st.get("on_market") or st.get("gc_for_sale"):
        src = "PropRadar" if st.get("on_market") else "our own listings data"
        if dom is not None and dom >= FORM6_NEAR_DAYS:
            state = "PAST" if dom >= FORM6_DAYS else "nearing"
            return False, (f"NO for mail — ON THE MARKET {dom} days ({src}), {state} the "
                           f"90-day Form 6 window. Route to the listing-expiry process.")
        return False, (f"NO — currently FOR SALE with another agent ({src}"
                       + (f", {dom} days on market" if dom is not None else "") + "). "
                       "The visitor is most likely a buyer, not the owner.")

    basis = ("no current listing in PropRadar or our own data"
             if st.get("found") else
             "not in PropRadar's listing/sold index and not listed in our own data")
    return True, f"Not for sale ({basis}). ⚠ {LEASE_UNKNOWN}"


if __name__ == "__main__":
    from shared.db import get_client  # noqa: E402
    db = get_client()[CACHE_DB]
    for a in sys.argv[1:]:
        st = check(a, db=db)
        ok, why = verdict(st)
        print(f"{a}\n  on_market={st.get('on_market')} dom={st.get('days_on_market')} "
              f"canonical={st.get('canonical_address')}\n  -> {ok}: {why}")
