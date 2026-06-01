#!/usr/bin/env python3
"""Select REAL candidate homes per case study, correct field names, only homes
that actually have the data each card needs. Read-only. Writes a markdown report."""
import sys, json, re, datetime as dt
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db
from collections import defaultdict

OUT = "/home/fields/Fields_Orchestrator/11_House_Mini_Site/candidates_report.md"
CORE = ["robina", "burleigh_waters", "varsity_lakes"]
lines = []
def p(*a): lines.append(" ".join(str(x) for x in a))

def num(v):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    s = re.sub(r"[^0-9]", "", str(v).split("-")[0].split("to")[0])
    return float(s) if s and len(s) >= 5 else None

def recent(d, months=12):
    sd = d.get("sale_date")
    if not sd: return True  # keep if undated (sale_price still useful)
    try:
        t = dt.datetime.strptime(str(sd)[:10], "%Y-%m-%d").date()
        return t >= dt.date.today().replace(year=dt.date.today().year-1)
    except: return True

def current_sale(d):
    """Most-recent Sale event from the Domain profile timeline = this listing's sale.
    Returns (dom, method, event_price) or (None, None, None)."""
    v2 = d.get("scraped_data_v2") or {}
    tl = v2.get("timeline") if isinstance(v2, dict) else None
    if not tl:
        return None, None, None
    sales = [e for e in tl if isinstance(e, dict) and e.get("category") == "Sale" and e.get("event_date")]
    if not sales:
        return None, None, None
    sales.sort(key=lambda e: str(e.get("event_date")), reverse=True)
    top = sales[0]
    return top.get("days_on_market"), (top.get("price_description") or "").strip(), top.get("event_price")

def dom_of(d):
    """Domain's published timeline DOM is authoritative (seller-verifiable); fall
    back to our derived top-level value only when the timeline lacks it."""
    tdom = current_sale(d)[0]
    return tdom if isinstance(tdom, (int, float)) else d.get("days_on_market")

def dom_confident(d):
    """True only when timeline DOM and top-level DOM agree (or only one exists)."""
    tdom = current_sale(d)[0]; top = d.get("days_on_market")
    if isinstance(tdom, (int, float)) and isinstance(top, (int, float)):
        return tdom == top
    return True

def method_of(d):
    m = d.get("sale_method")
    if m: return str(m).lower()
    pd = current_sale(d)[1] or ""
    return pd.lower()

db = get_gold_coast_db()
rows = []
for col in CORE:
    for d in db[col].find({"listing_status": "sold"}):
        rows.append((col, d))
p(f"# Case-study candidate homes (verified) — {dt.datetime.utcnow().date()}")
p(f"Total sold (all-time, core): {len(rows)}")
p(f"(DOM + method now read from scraped_data_v2.timeline where the top-level field is empty)")
p("")

def domain_mid(d):
    dv = d.get("domain_valuation_at_listing") or {}
    return dv.get("mid") if isinstance(dv, dict) else None

# ---- CS1 overpricing (reframed): long DOM AND sold below Domain's at-listing estimate ----
p("## CS1 — Overpricing penalty (long DOM + sold below Domain estimate-at-listing)")
p("- Note: the data has NO intra-campaign asking-price-reduction trail. Reframed on the available")
p("-       signal: a long time on market AND a sale below the at-listing estimate = priced ahead of the market.")
c1 = []
for col, d in rows:
    dom = dom_of(d); sp = num(d.get("sale_price")); mid = domain_mid(d)
    if dom and sp and mid and dom >= 60 and mid > sp:
        below = (mid - sp) / mid * 100
        c1.append((below, dom, col, d.get("address"), mid, sp, method_of(d), d.get("bedrooms"), d.get("property_type"), dom_confident(d)))
c1.sort(key=lambda x: -(x[0] * 3 + x[1] / 20))
if not c1: p("- none meeting DOM>=60 + below-estimate")
for below, dom, col, addr, mid, sp, meth, bd, ty, dc in c1[:14]:
    flag = "" if dc else " ⚠DOM-unconfirmed"
    p(f"- [{col}] {addr} | {bd}bd {ty} | est ${mid:,.0f} → sold ${sp:,.0f} ({below:.1f}% below) | DOM={dom:.0f}{flag} | {meth}")
p("")

# ---- CS2 well-priced fast sale: low DOM (timeline-derived) ----
p("## CS2 — Well-priced fast sale (low DOM)")
c2 = []
for col, d in rows:
    dom = dom_of(d); sp = num(d.get("sale_price"))
    if dom and sp and dom > 0:
        c2.append((dom, col, d.get("address"), sp, method_of(d), d.get("bedrooms"), d.get("property_type"), dom_confident(d)))
c2.sort(key=lambda x: x[0])
p(f"- candidates with DOM>0: {len(c2)}")
for dom, col, addr, sp, meth, bd, ty, dc in c2[:14]:
    flag = "" if dc else " ⚠DOM-unconfirmed"
    p(f"- [{col}] {addr} | {bd}bd {ty} | sold ${sp:,.0f} | DOM={dom:.0f}{flag} | {meth}")
p("")

# ---- CS3 auction (timeline- or field-derived) ----
p("## CS3 — Auction vs private treaty (method = auction)")
c3 = [(col, d) for col, d in rows if "auction" in method_of(d)]
p(f"- auction-sold homes available: {len(c3)}")
c3s = sorted(c3, key=lambda cd: -(dom_of(cd[1]) or 0))
for col, d in c3s[:14]:
    sp = num(d.get("sale_price")); dom = dom_of(d)
    flag = "" if dom_confident(d) else " ⚠DOM-unconfirmed"
    p(f"  - [{col}] {d.get('address')} | {d.get('bedrooms')}bd {d.get('property_type')} | sold ${ (sp or 0):,.0f} | DOM={dom}{flag}")
p("")

# ---- CS4 renovation matched pair: same suburb+beds+type, condition grade present ----
p("## CS4 — Renovation matched pairs (condition grade present)")
def cond(d):
    pvd = d.get("property_valuation_data") or {}
    cs = pvd.get("condition_summary") if isinstance(pvd, dict) else None
    return json.dumps(cs)[:60] if cs else None
groups = defaultdict(list)
for col, d in rows:
    sp = num(d.get("sale_price"))
    if sp and d.get("bedrooms") and cond(d):
        groups[(col, d.get("bedrooms"), d.get("property_type"))].append((sp, d.get("address") or "?", cond(d)))
shown = 0
for key, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    if len(g) >= 3 and shown < 6:
        g.sort(key=lambda x: x[0])
        p(f"- {key[1]}bd {key[2]} in {key[0]} (n={len(g)}): low ${g[0][0]:,.0f} ({g[0][1]}) … high ${g[-1][0]:,.0f} ({g[-1][1]})")
        shown += 1
p("")

# ---- Domain-vs-reality bonus ----
p("## BONUS — Domain estimate-at-listing vs actual sale (biggest misses)")
cb = []
for col, d in rows:
    dv = d.get("domain_valuation_at_listing") or {}
    mid = dv.get("mid") if isinstance(dv, dict) else None
    sp = num(d.get("sale_price"))
    if mid and sp and sp > 0:
        err = (mid - sp)/sp*100
        cb.append((abs(err), err, col, d.get("address"), mid, sp, dv.get("accuracy")))
cb.sort(key=lambda x: -x[0])
for ae, err, col, addr, mid, sp, acc in cb[:10]:
    p(f"- [{col}] {addr} | Domain ${mid:,.0f} vs sold ${sp:,.0f} ({err:+.1f}%) | grade={acc}")
p("")

open(OUT, "w").write("\n".join(lines))
print("OK rows", len(rows), "cs1", len(c1), "cs2", len(c2), "cs3", len(c3), "->", OUT)
