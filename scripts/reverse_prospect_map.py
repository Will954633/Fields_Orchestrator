#!/usr/bin/env python3
"""
reverse_prospect_map.py — reverse-prospecting agent map for a subject property.

PURPOSE (internal targeting only)
─────────────────────────────────────────────────────────────────────────────
Before spending on cold outreach around a subject property, work out WHO to talk
to. For a given subject it surfaces:

  1. Agencies ranked by the VOLUME of closely-comparable recent sales they made
     (last 24 months, similar land + beds, non-waterfront). These agents hold the
     under-bidders on stock like the subject.
  2. Long / reduced campaigns in-band (high days-on-market, price cuts) — flags a
     deep, exhausted buyer register.
  3. Current direct competitors (same suburb, similar land/beds, on market now).
  4. Withdrawn / expired stock in-band whose vendors may still want to sell.
  5. A prioritised, plain-language call list.

⚠ LEGAL / COMPLIANCE — READ BEFORE USE
─────────────────────────────────────────────────────────────────────────────
This is an INTERNAL TARGETING TOOL. Its "rank" is a COUNT OF TRANSACTIONS, not a
measure of agent ability. It computes NO performance/quality score of any kind.
QLD Property Occupations Act Sch 2 ss207-209 govern representations about agents
and property value (reverse onus, compelled substantiation) — so this output must
NEVER be used to publicly rate, grade, rank or compare any agent's performance.
"These agents recently sold comparable stock" is the only claim it supports.
Cold-contact rules (DNC / Spam Act / POA reg s21(3) on withdrawn approaches) apply
separately to any outreach — see memory cold_contact_legal_position_2026-08.

Read-only against the database.

USAGE
    python3 scripts/reverse_prospect_map.py --address "93 Burleigh Street"
    python3 scripts/reverse_prospect_map.py --id 690bd81b8b8f546592617fbb
    python3 scripts/reverse_prospect_map.py --slug some-slug
    # tuning:
    python3 scripts/reverse_prospect_map.py --address "93 Burleigh Street" \
        --land-pct 0.30 --beds-tol 1 --months 24 --json out.json
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_client
from shared.waterfront import detect_waterfront

HEADER = (
    "INTERNAL TARGETING DATA ONLY — this is a COUNT of comparable transactions, "
    "NOT a rating of any agent. It must NOT be used to publicly rate, rank or "
    "compare agent performance (QLD POA ss207-209)."
)

SCRATCH = (
    "/tmp/claude-1001/-home-fields-Fields-Orchestrator/"
    "545fb342-e0c9-4a83-8bdf-e8c189e850c8/scratchpad"
)

# Labels in system_monitor.lead_worklist that indicate a vendor whose campaign
# has stalled / withdrawn / is expiring — a potential still-motivated seller.
EXPIRY_LABELS = {"pre_market_withdrawn", "on_market_stale", "on_market_expiring"}


# ── helpers ──────────────────────────────────────────────────────────────────

def suburb_to_collection(suburb: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (suburb or "").strip().lower()).strip("_")


def parse_price(v):
    """'$2,130,000' / 2130000 / None -> int|None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.findall(r"\d[\d,]*", str(v))
    if not m:
        return None
    try:
        return int(m[0].replace(",", ""))
    except ValueError:
        return None


def resolve_land(doc) -> "int|None":
    """Land size (sqm) with fallbacks — the primary field is null on many docs."""
    for path in (
        ("land_size_sqm",),
        ("onthehouse_data", "land_size_sqm"),
        ("property_insights", "lot_size", "value"),
        ("floor_plan_analysis", "total_land_area", "value"),
    ):
        o = doc
        ok = True
        for p in path:
            if isinstance(o, dict) and p in o:
                o = o[p]
            else:
                ok = False
                break
        if ok and o not in (None, 0):
            try:
                return int(round(float(o)))
            except (TypeError, ValueError):
                pass
    # last resort: 'land_size' free-text string, e.g. "822 m²"
    val = parse_price(doc.get("land_size"))
    return val


def resolve_agency(doc) -> "str|None":
    for k in ("agency_name", "agency", "selling_agency"):
        v = doc.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return None


def split_agents(v):
    """agent_name is comma-joined for co-listings — split into individuals."""
    if not v:
        return []
    return [a.strip() for a in re.split(r"\s*(?:,|&|/| and )\s*", str(v)) if a.strip()]


def parse_date(v):
    if not v:
        return None
    s = str(v)[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def resolve_dom(doc) -> "int|None":
    for k in ("days_on_market", "days_on_domain"):
        v = doc.get(k)
        if isinstance(v, int):
            return v
        pv = parse_price(v)
        if pv is not None:
            return pv
    return None


def price_history_summary(doc):
    """Return (n_events, n_reductions, first_price, last_price) or None."""
    ph = doc.get("price_history")
    if not isinstance(ph, list) or not ph:
        return None
    prices = [parse_price(e.get("price_numeric") if e.get("price_numeric") is not None
                           else e.get("price_text"))
              for e in ph if isinstance(e, dict)]
    prices = [p for p in prices if p]
    reductions = 0
    for a, b in zip(prices, prices[1:]):
        if b < a:
            reductions += 1
    first = prices[0] if prices else None
    last = prices[-1] if prices else None
    return {"events": len(ph), "reductions": reductions,
            "first_price": first, "last_price": last}


def display_addr(doc):
    return doc.get("address") or doc.get("street_address") or "(no address)"


# ── subject resolution ───────────────────────────────────────────────────────

def resolve_subject(db, args):
    """Find the subject doc across Gold_Coast collections."""
    from bson import ObjectId
    colls = [c for c in db.list_collection_names()
             if not c.startswith("system") and c not in ("address_search_index",)]

    if args.id:
        try:
            oid = ObjectId(args.id)
        except Exception:
            oid = None
        for coll in colls:
            q = {"$or": [{"_id": oid}] if oid else []}
            q["$or"] += [{"property_id": args.id}, {"domain_id": args.id}, {"id": args.id}]
            d = db[coll].find_one(q)
            if d:
                return d, coll
    if args.slug:
        for coll in colls:
            d = db[coll].find_one({"slug": args.slug})
            if d:
                return d, coll
    if args.address:
        # whitespace / case tolerant prefix match on address or street_address
        pat = re.escape(args.address.strip())
        pat = pat.replace(r"\ ", r"\s+")
        rx = {"$regex": pat, "$options": "i"}
        for coll in colls:
            d = db[coll].find_one({"$or": [{"address": rx}, {"street_address": rx}]})
            if d:
                return d, coll
    return None, None


# ── core ─────────────────────────────────────────────────────────────────────

def in_band(doc, subj_land, subj_beds, land_pct, beds_tol):
    if detect_waterfront(doc).get("is_waterfront"):
        return False, None, None
    land = resolve_land(doc)
    beds = doc.get("bedrooms")
    if subj_land and land is not None:
        lo, hi = subj_land * (1 - land_pct), subj_land * (1 + land_pct)
        if not (lo <= land <= hi):
            return False, land, beds
    if subj_beds is not None and isinstance(beds, int):
        if abs(beds - subj_beds) > beds_tol:
            return False, land, beds
    return True, land, beds


def build_map(db, subject, coll_name, args):
    coll = db[coll_name]
    subj_land = resolve_land(subject)
    subj_beds = subject.get("bedrooms")
    cutoff = datetime.now() - timedelta(days=args.months * 30.5)

    result = {
        "header": HEADER,
        "subject": {
            "address": display_addr(subject),
            "suburb": subject.get("suburb"),
            "collection": coll_name,
            "land_sqm": subj_land,
            "bedrooms": subj_beds,
            "listing_status": subject.get("listing_status"),
            "current_agent": subject.get("agent_name"),
            "current_agency": resolve_agency(subject),
        },
        "band": {"land_pct": args.land_pct, "beds_tol": args.beds_tol,
                 "months": args.months,
                 "land_range_sqm": [round(subj_land * (1 - args.land_pct)),
                                    round(subj_land * (1 + args.land_pct))] if subj_land else None,
                 "beds_range": [subj_beds - args.beds_tol, subj_beds + args.beds_tol]
                 if isinstance(subj_beds, int) else None},
    }

    # ---- 1. comparable recent sales -> agency ranking -----------------------
    agency_stats = defaultdict(lambda: {"count": 0, "agents": defaultdict(int),
                                        "prices": [], "sales": []})
    comps = []
    no_agency_sales = 0
    subj_id = subject.get("_id")
    for d in coll.find({"listing_status": "sold"}):
        if d.get("_id") == subj_id:
            continue
        sd = parse_date(d.get("sold_date"))
        if not sd or sd < cutoff:
            continue
        ok, land, beds = in_band(d, subj_land, subj_beds, args.land_pct, args.beds_tol)
        if not ok:
            continue
        price = parse_price(d.get("sale_price"))
        agency = resolve_agency(d)
        agents = split_agents(d.get("agent_name"))
        rec = {"address": display_addr(d), "sold_date": d.get("sold_date"),
               "sale_price": price, "land_sqm": land, "bedrooms": beds,
               "agency": agency, "agents": agents,
               "days_on_market": resolve_dom(d),
               "price_history": price_history_summary(d)}
        comps.append(rec)
        if agency:
            s = agency_stats[agency]
            s["count"] += 1
            for a in agents:
                s["agents"][a] += 1
            if price:
                s["prices"].append(price)
            s["sales"].append(rec)
        else:
            no_agency_sales += 1

    ranked = []
    for agency, s in agency_stats.items():
        prices = sorted(s["prices"])
        med = prices[len(prices) // 2] if prices else None
        ranked.append({
            "agency": agency,
            "relevant_recent_sales": s["count"],   # TARGETING count, not a score
            "agents": sorted(s["agents"].items(), key=lambda x: -x[1]),
            "median_sale_price": med,
            "example_sales": sorted(s["sales"], key=lambda r: r["sold_date"] or "",
                                    reverse=True)[:4],
        })
    ranked.sort(key=lambda r: (-r["relevant_recent_sales"],
                               -(r["median_sale_price"] or 0)))

    result["comparable_sales_by_agency"] = {
        "n_comps_in_band": len(comps),
        "n_comps_without_agency_data": no_agency_sales,
        "note": (f"{no_agency_sales} in-band sold rows lack agency data and are "
                 "counted here but cannot be attributed to an agency."),
        "ranking": ranked,
    }

    # ---- 2. long / reduced campaigns in-band --------------------------------
    long_campaigns = []
    ph_have = ph_total = 0
    for r in comps:
        ph_total += 1
        dom = r["days_on_market"]
        ph = r["price_history"]
        if ph:
            ph_have += 1
        flagged = (dom is not None and dom >= args.long_dom) or \
                  (ph and ph["reductions"] >= 1)
        if flagged:
            long_campaigns.append(r)
    long_campaigns.sort(key=lambda r: -(r["days_on_market"] or 0))
    result["long_or_reduced_campaigns"] = {
        "long_dom_threshold_days": args.long_dom,
        "price_history_coverage": f"{ph_have}/{ph_total} in-band sold rows carry "
                                  f"price_history (~21% platform-wide on sold docs)",
        "campaigns": long_campaigns,
    }

    # ---- 3. current direct competitors --------------------------------------
    competitors = []
    for status in ("for_sale", "under_contract"):
        for d in coll.find({"listing_status": status}):
            if d.get("_id") == subj_id:
                continue
            ok, land, beds = in_band(d, subj_land, subj_beds, args.land_pct, args.beds_tol)
            if not ok:
                continue
            competitors.append({
                "address": display_addr(d), "listing_status": status,
                "under_contract": status == "under_contract",
                "land_sqm": land, "bedrooms": beds,
                "agency": resolve_agency(d),
                "agent": subject and d.get("agent_name"),
                "days_on_market": resolve_dom(d),
                "price_history": price_history_summary(d),
            })
    competitors.sort(key=lambda c: -(c["days_on_market"] or 0))
    result["current_competitors"] = competitors

    # ---- 4. withdrawn / expired ---------------------------------------------
    withdrawn = []
    for d in coll.find({"listing_status": "withdrawn"}):
        if detect_waterfront(d).get("is_waterfront"):
            continue
        land = resolve_land(d)
        beds = d.get("bedrooms")
        # withdrawn docs are sparse on land; keep if in-band OR land unknown
        in_land = True
        if subj_land and land is not None:
            lo, hi = subj_land * (1 - args.land_pct), subj_land * (1 + args.land_pct)
            in_land = lo <= land <= hi
        if not in_land:
            continue
        ph = price_history_summary(d)
        last_price = parse_price(d.get("sale_price"))
        if ph and ph.get("last_price"):
            last_price = last_price or ph["last_price"]
        withdrawn.append({
            "address": display_addr(d), "land_sqm": land, "bedrooms": beds,
            "last_advertised_price": last_price,
            "agency": resolve_agency(d), "agent": d.get("agent_name"),
            "price_history": ph, "land_known": land is not None,
        })

    # lead_worklist expiry-signal rows in this suburb
    sm = db.client["system_monitor"]
    worklist_hits = []
    if "lead_worklist" in sm.list_collection_names():
        suburb = (subject.get("suburb") or "").lower()
        subj_addr = (subject.get("address") or subject.get("street_address") or "").lower()
        for w in sm["lead_worklist"].find({"seller_intent.label": {"$in": list(EXPIRY_LABELS)}}):
            addr = w.get("address") or ""
            if suburb and suburb not in addr.lower():
                continue
            if subj_addr[:12] and addr.lower().startswith(subj_addr[:12]):
                continue  # skip the subject itself
            si = w.get("seller_intent") or {}
            worklist_hits.append({
                "address": addr, "label": si.get("label"),
                "conclusion": si.get("conclusion"),
                "last_sold_price": w.get("last_sold_price"),
                "last_sold_date": w.get("last_sold_date"),
                "years_held": w.get("years_held"),
            })
    result["withdrawn_expired"] = {
        "withdrawn_listings": withdrawn,
        "lead_worklist_expiry_signals": worklist_hits,
        "labels_used": sorted(EXPIRY_LABELS),
    }

    # ---- 5. prioritised call list -------------------------------------------
    call_list = []
    for r in ranked[:6]:
        top_agents = [a for a, _ in r["agents"][:2]]
        who = ", ".join(top_agents) if top_agents else "(agency, agent unnamed)"
        call_list.append({
            "priority": len(call_list) + 1,
            "agency": r["agency"],
            "suggested_agents": top_agents,
            "relevant_recent_sales": r["relevant_recent_sales"],
            "why": (f"Sold {r['relevant_recent_sales']} comparable home(s) in-band in "
                    f"the last {args.months} months — {who} holds the under-bidders "
                    f"on stock like the subject."),
        })
    result["prioritised_call_list"] = {
        "framing": ("Approach order reflects who recently sold the most comparable "
                    "stock (and therefore holds the most relevant under-bidders). "
                    "This is NOT a ranking of agent ability."),
        "calls": call_list,
    }
    return result


# ── rendering ────────────────────────────────────────────────────────────────

def money(v):
    return f"${v:,}" if isinstance(v, int) else "—"


def render(res):
    L = []
    L.append("=" * 78)
    L.append(HEADER)
    L.append("=" * 78)
    s = res["subject"]
    L.append(f"\nSUBJECT: {s['address']}")
    L.append(f"  suburb={s['suburb']}  land={s['land_sqm']}sqm  beds={s['bedrooms']}"
             f"  status={s['listing_status']}  agent={s['current_agent']}")
    b = res["band"]
    L.append(f"  BAND: land {b['land_range_sqm']} sqm | beds {b['beds_range']} | "
             f"last {b['months']} months | non-waterfront")

    cs = res["comparable_sales_by_agency"]
    L.append(f"\n1) AGENCIES BY VOLUME OF COMPARABLE RECENT SALES "
             f"(n_comps={cs['n_comps_in_band']}; {cs['n_comps_without_agency_data']} "
             f"lack agency data)")
    for i, r in enumerate(cs["ranking"], 1):
        ag = ", ".join(f"{a}({n})" for a, n in r["agents"][:3]) or "—"
        L.append(f"  {i:>2}. {r['agency']:<38} {r['relevant_recent_sales']:>2} sales "
                 f"| median {money(r['median_sale_price'])} | {ag}")

    lc = res["long_or_reduced_campaigns"]
    L.append(f"\n2) LONG / REDUCED CAMPAIGNS IN-BAND "
             f"(DOM>={lc['long_dom_threshold_days']}d or a price cut) — "
             f"{lc['price_history_coverage']}")
    for r in lc["campaigns"][:15]:
        ph = r["price_history"]
        red = f", {ph['reductions']} cut(s)" if ph and ph["reductions"] else ""
        L.append(f"   - {r['address']:<44} DOM={r['days_on_market']}{red} "
                 f"| {r['agency'] or 'agency?'} | {money(r['sale_price'])}")

    L.append("\n3) CURRENT DIRECT COMPETITORS (on market now)")
    for c in res["current_competitors"]:
        uc = " [UNDER CONTRACT]" if c["under_contract"] else ""
        ph = c["price_history"]
        red = f", {ph['reductions']} cut(s)" if ph and ph["reductions"] else ""
        L.append(f"   - {c['address']:<44} land={c['land_sqm']} beds={c['bedrooms']} "
                 f"DOM={c['days_on_market']}{red} | {c['agency'] or 'agency?'}{uc}")

    w = res["withdrawn_expired"]
    L.append(f"\n4) WITHDRAWN / EXPIRED IN-BAND ({len(w['withdrawn_listings'])} "
             f"withdrawn listings; {len(w['lead_worklist_expiry_signals'])} "
             f"lead_worklist expiry signals)")
    for x in w["withdrawn_listings"][:20]:
        lk = "" if x["land_known"] else " (land unknown)"
        L.append(f"   - {x['address']:<44} land={x['land_sqm']}{lk} beds={x['bedrooms']} "
                 f"| last {money(x['last_advertised_price'])} "
                 f"| {x['agent'] or x['agency'] or 'agent?'}")
    for x in w["lead_worklist_expiry_signals"][:15]:
        yh = f"held {x['years_held']}y, " if x.get("years_held") else ""
        lsp = money(x["last_sold_price"]) if isinstance(x.get("last_sold_price"), int) \
            else (x.get("last_sold_price") or "—")
        lsd = x.get("last_sold_date") or ""
        L.append(f"   * [{x['label']}] {x['address']}  ({yh}last sold {lsp} {lsd})".replace(" )", ")"))

    cl = res["prioritised_call_list"]
    L.append(f"\n5) PRIORITISED CALL LIST\n   {cl['framing']}")
    for c in cl["calls"]:
        L.append(f"   #{c['priority']} {c['agency']} — {c['why']}")
    L.append("\n" + "=" * 78)
    L.append(HEADER)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Reverse-prospect agent map (internal targeting only).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--address")
    g.add_argument("--id")
    g.add_argument("--slug")
    ap.add_argument("--land-pct", type=float, default=0.30,
                    help="land tolerance fraction of subject (default 0.30)")
    ap.add_argument("--beds-tol", type=int, default=1)
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--long-dom", type=int, default=120,
                    help="days-on-market threshold for a 'long' campaign")
    ap.add_argument("--json", nargs="?", const="__auto__",
                    help="write JSON (path optional; defaults to scratchpad)")
    args = ap.parse_args()

    db = get_client()["Gold_Coast"]
    subject, coll = resolve_subject(db, args)
    if not subject:
        print("SUBJECT NOT FOUND. Tried address/street_address/_id/property_id/slug.",
              file=sys.stderr)
        sys.exit(2)

    res = build_map(db, subject, coll, args)
    print(render(res))

    if args.json:
        path = args.json
        if path == "__auto__":
            os.makedirs(SCRATCH, exist_ok=True)
            safe = re.sub(r"[^a-z0-9]+", "_", res["subject"]["address"].lower())[:50]
            path = os.path.join(SCRATCH, f"reverse_prospect_{safe}.json")
        with open(path, "w") as f:
            json.dump(res, f, indent=2, default=str)
        print(f"\n[json written: {path}]", file=sys.stderr)


if __name__ == "__main__":
    main()
