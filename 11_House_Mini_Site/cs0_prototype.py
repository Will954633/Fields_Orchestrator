#!/usr/bin/env python3
"""CS0 dynamic-comparable PROTOTYPE — proves the design on the real subject.

Reuses competitor_matcher's subject-profile + scoring + aperture + difference-line
helpers, but queries SOLD docs (last 12 months), applies the relevance gate
(close tier, ring<=2) and the fact-verification gate (timeline cross-check).
Read-only. Prints the chosen comp + which facts are verified."""
import sys, re, datetime as dt
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from shared.db import get_gold_coast_db
from property_reports import competitor_matcher as cm

SUBJECT = {
    "address": "13 Terrace Court, Merrimac", "_suburb_key": "merrimac",
    "bedrooms": 6, "bathrooms": 3, "carspaces": 2,
    "lot_size_sqm": 658, "total_floor_area": 221, "property_type": "House",
    "description": "pool dual living cul-de-sac north-facing deck",
}
PRICE_ANCHOR = 1_950_000
WINDOW_MONTHS = 12

db = get_gold_coast_db()
subject = cm._subject_profile(SUBJECT, None, PRICE_ANCHOR)
print("SUBJECT:", {k: subject[k] for k in ("group","bedrooms","bathrooms","land","floor","price","features")})

cutoff = dt.date.today().replace(year=dt.date.today().year - 1)
catchment = [SUBJECT["_suburb_key"]] + [s for s in cm.DEFAULT_CATCHMENT if s != SUBJECT["_suburb_key"]]

def newest_sold_event(d):
    """The current sale = most-recent is_sold timeline event. Returns (date, price, ev)."""
    v2 = d.get("scraped_data_v2") or {}
    tl = v2.get("timeline") if isinstance(v2, dict) else None
    if not tl: return None, None, None
    sales = [e for e in tl if isinstance(e,dict) and e.get("category")=="Sale" and e.get("is_sold") and e.get("event_date")]
    if not sales: return None, None, None
    sales.sort(key=lambda e: str(e.get("event_date")), reverse=True)
    top = sales[0]
    try: d0 = dt.date.fromisoformat(str(top["event_date"])[:10])
    except: d0 = None
    return d0, cm._parse_price(top.get("event_price")), top

# IMPORTANT (design correction): recency comes from the timeline's newest sold
# event, NOT sale_date/sold_date (those often hold a PRIOR sale). Sold price
# parses from listing_price/sale_price ("SOLD - $X"), not `price` (null on solds).
SOLD_PROJ = dict(cm._CANDIDATE_PROJECTION, scraped_data_v2=1, sale_price=1,
                 sale_date=1, sold_date=1, sale_method=1, domain_valuation_at_listing=1)

def gather_sold(suburbs, bed, bed_band, price, price_band):
    out = []
    lo, hi = price*(1-price_band), price*(1+price_band)
    for sub in suburbs:
        if sub not in db.list_collection_names(): continue
        q = {"listing_status": "sold"}
        if bed_band is not None:
            q["bedrooms"] = {"$in": list(range(bed-bed_band, bed+bed_band+1))}
        for d in db[sub].find(q, SOLD_PROJ):
            d["_suburb_key"] = sub
            if cm._property_type_group(d) != subject["group"]: continue
            tl_date, tl_price, _ = newest_sold_event(d)
            # recency from timeline; fall back to sale_date only if no timeline
            rd = tl_date
            if rd is None:
                sd = d.get("sale_date") or d.get("sold_date")
                try: rd = dt.date.fromisoformat(str(sd)[:10]) if sd else None
                except: rd = None
            if rd is None or rd < cutoff: continue
            cand_price = tl_price or cm._parse_price(d.get("listing_price"), d.get("sale_price"))
            if not cand_price or not (lo <= cand_price <= hi): continue
            d["_price"] = cand_price
            out.append(d)
    return out

# walk aperture rings
chosen_ring = None; survivors = []
for ri, ring in enumerate(cm.APERTURE_RINGS):
    subs = cm._geo_for_ring(ring["geo"], SUBJECT["_suburb_key"], catchment)
    cands = gather_sold(subs, subject["bedrooms"], ring["beds"], subject["price"], ring["price"])
    scored = []
    for c in cands:
        s = cm._score(subject, c)
        scored.append((s, c))
    scored.sort(key=lambda x: x[0])
    print(f"ring {ri} ({ring['geo']}, +/-{int(ring['price']*100)}% , +/-{ring['beds']}bd): {len(scored)} sold substitutes; best score={scored[0][0]:.3f} ({scored[0][1].get('address')})" if scored else f"ring {ri}: 0")
    if scored and scored[0][0] <= cm.CLOSE_MATCH_THRESHOLD and ri <= 2:
        chosen_ring = ri; survivors = scored; break
    if scored and not survivors:
        survivors = scored  # remember best-effort

print()
if chosen_ring is None:
    print("RELEVANCE GATE: no close-tier sold match at ring<=2 → CS0 would HIDE.")
    if survivors:
        print("  (best available, NOT shown):", f"{survivors[0][0]:.3f}", survivors[0][1].get("address"))
    raise SystemExit

# fact gate on the chosen best
def current_sale(d):
    v2 = d.get("scraped_data_v2") or {}
    tl = v2.get("timeline") if isinstance(v2, dict) else None
    if not tl: return None
    sales = [e for e in tl if isinstance(e,dict) and e.get("category")=="Sale" and e.get("is_sold") and e.get("event_date")]
    if not sales: return None
    sales.sort(key=lambda e: str(e.get("event_date")), reverse=True)
    return sales[0]

print(f"\n=== Close-tier candidates at ring {chosen_ring} (score <= 0.30 shown), with verification richness ===")
for score, c in survivors[:12]:
    # re-fetch full doc (projection dropped timeline + sale fields)
    full = db[c["_suburb_key"]].find_one({"_id": c["_id"]})
    ev = current_sale(full)
    sp = cm._parse_price(full.get("sale_price"), full.get("listing_price"))
    sd = str(full.get("sold_date") or full.get("sale_date") or "")[:10]
    meth = (full.get("sale_method") or "").lower()
    print(f"--- candidate score={score:.3f}: {full.get('address')}")
    verified = {}
    if ev:
        sp_tl = cm._parse_price(ev.get("event_price"))
        # stale-timeline trap: timeline newest-sold must be ~ this sale
        try:
            gap = abs((dt.date.fromisoformat(sd) - dt.date.fromisoformat(str(ev.get("event_date"))[:10])).days) if sd else 999
        except: gap = 999
        if gap <= 21 and sp_tl and sp and abs(sp_tl-sp) <= 1000:
            verified["sale_price"] = sp_tl
            verified["method"] = ev.get("price_description")
            verified["sale_date"] = str(ev.get("event_date"))[:10]
            if isinstance(ev.get("days_on_market"), (int,float)):
                verified["dom"] = ev.get("days_on_market")
        else:
            print(f"    FACT GATE: timeline does not describe this sale (gap={gap}d, tl_price={sp_tl} vs stored={sp}) → reject candidate")
            continue
    else:
        print("    no timeline; sale_price/method from stored fields only")
        if sp: verified["sale_price"]=sp
        if meth: verified["method"]=meth
    diff = cm._difference_line(subject, c)
    dv = full.get("domain_valuation_at_listing") or {}
    has_dom = "dom" in verified
    print("    VERIFIED:", verified, "| has_DOM:", has_dom)
    print("    DIFF LINE:", diff)
    print("    domain_est_at_listing:", dv.get("mid"), "grade", dv.get("accuracy"))
    if score <= cm.CLOSE_MATCH_THRESHOLD and has_dom:
        print("    *** BEST PICK: close-tier AND full timeline (DOM) ***")
