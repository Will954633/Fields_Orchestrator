#!/usr/bin/env python3
"""Cross-check the load-bearing fields (sale price, method, sale date, DOM) of the
shortlisted case-study candidates against the Domain property-profile timeline.
Read-only. Writes verify_candidates_report.md."""
import sys, json, re, datetime as dt
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db

OUT = "/home/fields/Fields_Orchestrator/11_House_Mini_Site/verify_candidates_report.md"
CORE = ["robina", "burleigh_waters", "varsity_lakes"]

# Shortlisted addresses to verify (from candidates_report.md, current run)
SHORTLIST = {
    "CS1": ["1 Yawl Place", "19 Gerona Circuit", "31 Huntingdale Crescent",
            "44 Mornington Terrace", "9 Maitland Street", "8 Roseville Court",
            "147 Glen Eagles Drive", "18 Queenscliff Crescent", "26 Camphor Wood Court"],
    "CS2": ["6 Glasshouse Drive", "29 Stingray Crescent", "29 Auk Avenue",
            "3 Whitehead Drive", "58 Sea Eagle Drive", "29 Windemere Crescent",
            "7 Port Peyra Crescent", "22 Southlake Drive", "33 Lakeridge Drive"],
    "CS3": ["1/8 Washington Court", "1/1 Washington Court", "138 Camberwell Circuit",
            "10 Pipit Parade", "27 Bittern Avenue", "53 Manly Drive",
            "23 Kestrel Drive", "39 Brier Crescent"],
    "CS0_example": ["135 Camberwell Circuit"],
}

lines = []
def p(*a): lines.append(" ".join(str(x) for x in a))

def num(v):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    s = re.sub(r"[^0-9]", "", str(v))
    return float(s) if s and len(s) >= 5 else None

def current_sale(d):
    v2 = d.get("scraped_data_v2") or {}
    tl = v2.get("timeline") if isinstance(v2, dict) else None
    if not tl: return None
    sales = [e for e in tl if isinstance(e, dict) and e.get("category") == "Sale" and e.get("event_date") and e.get("is_sold")]
    if not sales: return None
    sales.sort(key=lambda e: str(e.get("event_date")), reverse=True)
    return sales[0]

db = get_gold_coast_db()
# index docs by address prefix
idx = {}
for col in CORE:
    for d in db[col].find({"listing_status": "sold"}):
        a = (d.get("address") or "")
        idx[a] = (col, d)

def find(addr_prefix):
    for a, (col, d) in idx.items():
        if a.startswith(addr_prefix):
            return col, d, a
    return None, None, None

p("# Candidate field cross-check vs Domain timeline")
p(f"Generated {dt.datetime.utcnow().isoformat()}Z")
p("Checks: stored sale_price vs timeline event_price · stored sale_method vs timeline price_description ·")
p("stored sold_date vs timeline event_date · top-level DOM vs timeline DOM.")
p("")

clean = warn = missing = 0
for card, addrs in SHORTLIST.items():
    p(f"## {card}")
    for ap in addrs:
        col, d, full = find(ap)
        if not d:
            p(f"- ❓ `{ap}` — not found in DB")
            missing += 1
            continue
        ev = current_sale(d)
        sp_stored = num(d.get("sale_price"))
        lp = d.get("listing_price")  # e.g. "SOLD - $1,800,000" or "Auction"
        sp_lp = num(lp) if lp and "SOLD" in str(lp).upper() else None
        meth_stored = (d.get("sale_method") or "").lower()
        sd_stored = str(d.get("sold_date") or d.get("sale_date") or "")[:10]
        dom_top = d.get("days_on_market")
        issues = []
        if ev:
            sp_tl = num(ev.get("event_price"))
            meth_tl = (ev.get("price_description") or "").lower()
            sd_tl = str(ev.get("event_date") or "")[:10]
            dom_tl = ev.get("days_on_market")
            # price check
            if sp_stored and sp_tl and abs(sp_stored - sp_tl) > 1000:
                issues.append(f"PRICE stored ${sp_stored:,.0f} ≠ timeline ${sp_tl:,.0f}")
            if sp_lp and sp_tl and abs(sp_lp - sp_tl) > 1000:
                issues.append(f"listing_price ${sp_lp:,.0f} ≠ timeline ${sp_tl:,.0f}")
            # method check
            if meth_stored and meth_tl:
                norm = lambda s: "auction" if "auction" in s else ("private treaty" if "private" in s else s)
                if norm(meth_stored) != norm(meth_tl):
                    issues.append(f"METHOD stored '{meth_stored}' ≠ timeline '{meth_tl}'")
            # date check (within 7 days tolerance — settle vs contract)
            try:
                if sd_stored and sd_tl:
                    ds = abs((dt.date.fromisoformat(sd_stored) - dt.date.fromisoformat(sd_tl)).days)
                    if ds > 14:
                        issues.append(f"DATE stored {sd_stored} vs timeline {sd_tl} ({ds}d apart)")
            except Exception:
                pass
            # DOM check
            if isinstance(dom_top, (int, float)) and isinstance(dom_tl, (int, float)) and dom_top != dom_tl:
                issues.append(f"DOM top={dom_top} ≠ timeline={dom_tl}")
            summary = f"sold ${ (sp_tl or 0):,.0f} | {meth_tl} | {sd_tl} | DOM={dom_tl}"
        else:
            issues.append("NO timeline — relying on stored fields only")
            summary = f"sold ${ (sp_stored or 0):,.0f} | {meth_stored} | {sd_stored} | DOM(top)={dom_top}"
        if issues:
            warn += 1
            p(f"- ⚠ `{full}` — {summary}")
            for i in issues: p(f"    - {i}")
        else:
            clean += 1
            p(f"- ✅ `{full}` — {summary}")
    p("")

p(f"## Totals: clean={clean} · with-discrepancy={warn} · not-found={missing}")
open(OUT, "w").write("\n".join(lines))
print(f"OK clean={clean} warn={warn} missing={missing} -> {OUT}")
