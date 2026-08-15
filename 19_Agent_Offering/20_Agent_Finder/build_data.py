#!/usr/bin/env python3
"""
Build the agent-record dataset for the Southern Gold Coast agent-finder prototype.

Two layers, deliberately kept separate because they have very different depth:

  AGENT layer   - `Gold_Coast.<suburb>` documents with listing_status == "sold".
                  Carries the individual `agent_name` (may be a comma-joined list
                  of co-agents), `agency_name`, `sold_date`, `sale_price`,
                  `property_type`, `days_on_market`. Thinner, but it is the only
                  place an individual is named.

  AGENCY layer  - `scraped_data.property_timeline[]` sold events. ~70k events
                  back to 2016 with agency_name / price / days_on_market, but
                  NO individual agent. Supporting context only.

Every numeric field on the sold documents is stored as a STRING
("$1,520,000", "51", "4") - parse, never assume.

Output: prototype/data.json

NOTE: manual build script, not a scheduled process. If it is ever put on a cron
it must be wrapped in job_status.job_run() per CLAUDE.md Rule 7, with the
outcome assertion on the zero-agent path (Rule 7b) that is already below.
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.db import get_client  # noqa: E402

SUBURBS = [
    "robina", "varsity_lakes", "burleigh_waters", "burleigh_heads", "palm_beach",
    "miami", "mermaid_waters", "mermaid_beach", "mudgeeraba", "reedy_creek",
    "currumbin", "currumbin_waters", "tugun", "elanora", "coolangatta", "bilinga",
    "tallebudgera", "tallebudgera_valley", "merrimac", "worongary",
    "clear_island_waters", "broadbeach_waters", "broadbeach", "bonogin",
    "springbrook", "currumbin_valley",
]

AGENT_WINDOW_MONTHS = 36
AGENCY_WINDOW_MONTHS = 24
MIN_AGENT_SALES = 3
MIN_AGENCY_SALES = 8

OUT = Path(__file__).resolve().parent / "prototype" / "data.json"


def pretty(slug):
    return " ".join(w.capitalize() for w in slug.split("_"))


def parse_money(v):
    """'$1,520,000' -> 1520000. None for POA / ranges / junk."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v) if v > 0 else None
    m = re.findall(r"[\d,]{4,}", str(v).replace(" ", ""))
    if not m:
        return None
    try:
        n = int(m[0].replace(",", ""))
    except ValueError:
        return None
    return n if 100_000 <= n <= 30_000_000 else None


def parse_int(v):
    if v is None:
        return None
    try:
        return int(str(v).strip().split(".")[0])
    except (ValueError, TypeError):
        return None


def parse_date(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def split_agents(name):
    """'Mitch Harrop, Joe Walker' -> both names.

    Co-listed sales are credited to BOTH agents. That is a real modelling
    choice and it is disclosed on the page: sale counts across agents
    therefore sum to more than the number of transactions.
    """
    if not name:
        return []
    out = []
    for p in re.split(r"\s*(?:,|&| and | / |\|)\s*", str(name)):
        p = " ".join(p.split()).strip(" .-")
        if len(p) < 4 or len(p) > 45 or any(ch.isdigit() for ch in p):
            continue
        if len(p.split()) < 2:
            continue
        out.append(p)
    return out


def norm_type(t):
    if not t:
        return "Other"
    t = str(t).strip().lower()
    if "house" in t or "acreage" in t or "duplex" in t:
        return "House"
    if "townhouse" in t or "terrace" in t or "villa" in t:
        return "Townhouse"
    if "apartment" in t or "unit" in t or "flat" in t or "studio" in t:
        return "Unit"
    if "land" in t:
        return "Land"
    return "Other"


def pctl(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return int(s[lo] + (s[hi] - s[lo]) * (k - lo))


def summarise(sales):
    prices = [s["price"] for s in sales if s["price"]]
    doms = [s["dom"] for s in sales if s["dom"]]
    return {
        "n": len(sales),
        "n_priced": len(prices),
        "n_dom": len(doms),
        "median_price": int(st.median(prices)) if prices else None,
        "p10_price": pctl(prices, 0.10),
        "p90_price": pctl(prices, 0.90),
        "median_dom": int(st.median(doms)) if doms else None,
        "last_sale": max((s["date"] for s in sales), default=None),
    }


def main():
    db = get_client()["Gold_Coast"]
    present = set(db.list_collection_names())
    subs = [s for s in SUBURBS if s in present]
    now = datetime.utcnow()
    agent_cut = now - timedelta(days=AGENT_WINDOW_MONTHS * 30)
    agency_cut = now - timedelta(days=AGENCY_WINDOW_MONTHS * 30)

    agents = defaultdict(lambda: {"sales": [], "agencies": defaultdict(int),
                                  "suburbs": defaultdict(int), "types": defaultdict(int)})
    agencies = defaultdict(lambda: {"sales": [], "suburbs": defaultdict(int)})
    suburb_prices = defaultdict(list)

    n_sold_docs = 0
    for slug in subs:
        for d in db[slug].find(
                {"listing_status": "sold"},
                {"agent_name": 1, "agency_name": 1, "sold_date": 1, "sale_price": 1,
                 "property_type": 1, "days_on_market": 1}):
            n_sold_docs += 1
            dt = parse_date(d.get("sold_date"))
            price = parse_money(d.get("sale_price"))
            ptype = norm_type(d.get("property_type"))
            dom = parse_int(d.get("days_on_market"))
            if price and dt and dt >= agency_cut:
                suburb_prices[slug].append(price)
            if not dt or dt < agent_cut:
                continue
            names = split_agents(d.get("agent_name"))
            if not names:
                continue
            agency = (d.get("agency_name") or "").strip() or None
            rec = {"date": dt.strftime("%Y-%m-%d"), "price": price,
                   "dom": dom if dom and 0 < dom < 730 else None,
                   "type": ptype, "suburb": slug}
            for nm in names:
                a = agents[nm]
                a["sales"].append(rec)
                a["suburbs"][slug] += 1
                a["types"][ptype] += 1
                if agency:
                    a["agencies"][agency] += 1

    n_events = 0
    for slug in subs:
        for d in db[slug].find({"scraped_data.property_timeline": {"$exists": True}},
                               {"scraped_data.property_timeline": 1}):
            for e in (d.get("scraped_data") or {}).get("property_timeline") or []:
                if not e.get("is_sold") or not e.get("agency_name"):
                    continue
                dt = parse_date(e.get("date"))
                if not dt or dt < agency_cut:
                    continue
                n_events += 1
                dom = parse_int(e.get("days_on_market"))
                ag = agencies[e["agency_name"].strip()]
                ag["sales"].append({"date": dt.strftime("%Y-%m-%d"),
                                    "price": parse_money(e.get("price")),
                                    "dom": dom if dom and 0 < dom < 730 else None,
                                    "suburb": slug})
                ag["suburbs"][slug] += 1

    out_agents = []
    for nm, a in agents.items():
        if len(a["sales"]) < MIN_AGENT_SALES:
            continue
        years = {}
        for x in a["sales"]:
            years[x["date"][:4]] = years.get(x["date"][:4], 0) + 1
        out_agents.append({
            "name": nm,
            "agency": (max(a["agencies"].items(), key=lambda kv: kv[1])[0]
                       if a["agencies"] else None),
            "suburbs": dict(sorted(a["suburbs"].items(), key=lambda kv: -kv[1])),
            "types": dict(sorted(a["types"].items(), key=lambda kv: -kv[1])),
            "by_year": dict(sorted(years.items())),
            "sales": sorted(a["sales"], key=lambda s: s["date"], reverse=True)[:60],
            **summarise(a["sales"]),
        })
    out_agents.sort(key=lambda x: -x["n"])

    out_agencies = {}
    for nm, a in agencies.items():
        if len(a["sales"]) < MIN_AGENCY_SALES:
            continue
        s = summarise(a["sales"])
        s["suburbs"] = dict(sorted(a["suburbs"].items(), key=lambda kv: -kv[1])[:8])
        out_agencies[nm] = s

    subs_out = {}
    for slug in subs:
        p = suburb_prices[slug]
        subs_out[slug] = {"name": pretty(slug),
                          "median_price": int(st.median(p)) if p else None,
                          "n": len(p)}

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coverage": {
            "suburbs": len(subs),
            "sold_documents_scanned": n_sold_docs,
            "agency_sold_events": n_events,
            "agent_window_months": AGENT_WINDOW_MONTHS,
            "agency_window_months": AGENCY_WINDOW_MONTHS,
            "min_agent_sales": MIN_AGENT_SALES,
            "agents_published": len(out_agents),
            "agencies_published": len(out_agencies),
        },
        "suburbs": subs_out,
        "agents": out_agents,
        "agencies": out_agencies,
    }

    if not out_agents:
        raise RuntimeError(
            "0 agents published from %d sold documents - source is broken, not empty"
            % n_sold_docs)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print("suburbs=%d sold_docs=%d agency_events=%d" % (len(subs), n_sold_docs, n_events))
    print("agents=%d agencies=%d" % (len(out_agents), len(out_agencies)))
    print("wrote %s (%.0f KB)" % (OUT, OUT.stat().st_size / 1024))


if __name__ == "__main__":
    main()
