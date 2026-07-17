#!/usr/bin/env python3
"""
five_property_friday.py — Draft a client's "5 that matter" shortlist from their brief.

Methodology (see 07_Focus/five-property-friday-playbook.md):
  1. FILTER  — hard-match the brief (suburbs, min beds/baths, budget, for_sale).
  2. SCORE   — rank by OUR signals: price-vs-value gap, situation (days on market,
               price cuts), valuation confidence.
  3. SANITY  — flag any |gap| > 25% for human review; never auto-surface an extreme
               gap as a "value" call (usually a data mismatch, not a real bargain).
  4. CURATE  — pick 5 with distinct roles (value / negotiation / premium-priced-right
               / stretch / watch) so it reads as curation, not a dump.

Output is a MARKDOWN DRAFT for Will to review + sharpen — it never sends anything.

Usage:
  python3 scripts/five_property_friday.py --suburbs robina --beds 3 --baths 2 --budget 1300000
  python3 scripts/five_property_friday.py --lead-id 1004184862437951        # pull brief from fb_leads
  python3 scripts/five_property_friday.py --suburbs robina,varsity_lakes --beds 3 --baths 2
"""
import os, sys, re, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client

SANITY_PCT = 25.0            # |gap| beyond this = flag for review, not a value call
CONF_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.4, "very_low": 0.15, None: 0.3}
SUBURB_COLLECTIONS = {"robina", "burleigh_waters", "varsity_lakes",
                      "merrimac", "mudgeeraba", "reedy_creek", "worongary"}


def parse_price(p):
    """'$1,420,000' -> 1420000; 'Offer Above $1.8m' -> 1800000; 'Contact Agent' -> None."""
    if not p:
        return None
    s = str(p).lower().replace(",", "").replace(" ", "")
    m = re.search(r'\$?(\d+(?:\.\d+)?)m', s)          # 1.8m
    if m:
        return int(float(m.group(1)) * 1_000_000)
    m = re.search(r'(\d{6,})', s)                     # 1420000
    return int(m.group(1)) if m else None


def brief_from_lead(lead_id):
    doc = get_client()["system_monitor"]["fb_leads"].find_one({"_id": lead_id})
    if not doc:
        sys.exit(f"lead {lead_id} not found")
    f = doc.get("fields", {})
    area = (f.get("area") or "").lower()
    subs = list(SUBURB_COLLECTIONS) if "all" in area or "open" in area else [area]
    subs = [s for s in subs if s in SUBURB_COLLECTIONS]
    beds = int(re.sub(r"\D", "", str(f.get("bedrooms", "0"))) or 0)
    baths = int(re.sub(r"\D", "", str(f.get("bathrooms", "0"))) or 0)
    return {"suburbs": subs or ["robina"], "beds": beds, "baths": baths,
            "budget": None, "email": f.get("email")}


def gather(brief):
    db = get_client()["Gold_Coast"]
    out = []
    for sub in brief["suburbs"]:
        if sub not in SUBURB_COLLECTIONS:
            continue
        q = {"listing_status": "for_sale"}
        if brief["beds"]:
            q["bedrooms"] = {"$gte": brief["beds"]}
        if brief["baths"]:
            q["bathrooms"] = {"$gte": brief["baths"]}
        for d in db[sub].find(q):
            vd = d.get("valuation_data") or {}
            conf = vd.get("confidence") or {}
            recon = conf.get("reconciled_valuation")
            rng = conf.get("range") or {}
            ask = parse_price(d.get("price") or d.get("display_price"))
            gap = ((ask - recon) / recon * 100) if (ask and recon) else None
            out.append({
                "address": d.get("address") or d.get("display_address"),
                "url_slug": d.get("url_slug"),
                "suburb": sub, "beds": d.get("bedrooms"), "baths": d.get("bathrooms"),
                "price_text": d.get("price") or d.get("display_price"),
                "ask": ask, "recon": recon,
                "lo": rng.get("low"), "hi": rng.get("high"),
                "conf": conf.get("confidence"),
                "dom": d.get("days_on_market"),
                "reduced": bool(d.get("price_history") or d.get("price_changes")),
                "gap": gap,
            })
    return out


def score(c, budget):
    s = 0.0
    cw = CONF_WEIGHT.get(c["conf"], 0.3)
    if c["gap"] is not None and abs(c["gap"]) <= SANITY_PCT:
        # under our value (negative gap) scores up, weighted by confidence
        s += (-c["gap"]) * cw * 0.1
    if c["dom"] and c["dom"] > 45:
        s += 1.0
    if budget and c["ask"] and c["ask"] <= budget:
        s += 1.0
    if budget and c["ask"] and c["ask"] > budget * 1.15:
        s -= 2.0                    # well over budget
    s += cw                         # prefer confident valuations
    return s


def assign_roles(cands, budget):
    """Pick up to 5 with distinct roles. Returns list of (role, cand)."""
    picked, used = [], set()
    # Budget guard: core roles must be within (a hair over) budget; only "stretch" goes above.
    def wb(c):
        return (not budget) or (c["ask"] is not None and c["ask"] <= budget * 1.03)

    def take(role, key, pool=None):
        pool = pool if pool is not None else cands
        for c in pool:
            if id(c) in used:
                continue
            if key(c):
                used.add(id(c)); picked.append((role, c)); return

    clean = [c for c in cands if c["gap"] is not None and abs(c["gap"]) <= SANITY_PCT]
    # 1 best value: most under our range (negative gap), confident, within budget
    take("Best value", lambda c: wb(c) and c["gap"] is not None and c["gap"] < -3 and c["conf"] in ("high", "medium"),
         sorted(clean, key=lambda c: c["gap"]))
    # 2 negotiation: long DOM or reduced, within budget
    take("Negotiation play", lambda c: wb(c) and ((c["dom"] and c["dom"] > 45) or c["reduced"]),
         sorted(cands, key=lambda c: -(c["dom"] or 0)))
    # 3 premium priced right: fairly priced on comps, confident, within budget
    take("Premium, priced right", lambda c: wb(c) and c["gap"] is not None and -8 <= c["gap"] <= 8 and c["conf"] in ("high", "medium"))
    # 4 stretch: just above budget but strong (only role allowed over budget)
    if budget:
        take("The stretch", lambda c: c["ask"] and budget * 1.03 < c["ask"] <= budget * 1.2)
    # 5 watch: best remaining within budget
    take("One to watch", lambda c: wb(c), sorted(cands, key=lambda c: -score(c, budget)))
    # backfill to 5 from top score
    for c in sorted(cands, key=lambda c: -score(c, budget)):
        if len(picked) >= 5:
            break
        if id(c) not in used:
            used.add(id(c)); picked.append(("One to watch", c))
    return picked[:5]


def money(n):
    return f"${n:,.0f}" if n else "—"


def take_line(role, c):
    if c["gap"] is not None and c["lo"] and c["hi"]:
        if c["gap"] < -3:
            return (f"Asking {money(c['ask'])} sits {abs(c['gap']):.0f}% below our comparable-sales "
                    f"range of {money(c['lo'])}–{money(c['hi'])}. On the comps we analysed, homes like "
                    f"this have generally cleared higher.")
        if c["gap"] > 8:
            return (f"Asking {money(c['ask'])} is {c['gap']:.0f}% above our comparable-sales range "
                    f"of {money(c['lo'])}–{money(c['hi'])} — priced ahead of what the comps support.")
        return (f"Asking {money(c['ask'])} sits inside our comparable-sales range of "
                f"{money(c['lo'])}–{money(c['hi'])} — fairly priced on the comps.")
    if c["recon"]:
        return (f"No clean asking price published; our comparable-sales range is "
                f"{money(c['lo'])}–{money(c['hi'])} ({c['conf']} confidence).")
    return "Valuation data still resolving — flagged to watch."


def render(brief, picks, flagged):
    subs = ", ".join(s.replace("_", " ").title() for s in brief["suburbs"])
    lines = [f"# Draft shortlist — {subs}",
             f"_Brief: {brief['beds']}+ bed / {brief['baths']}+ bath"
             + (f", budget {money(brief['budget'])}" if brief.get("budget") else ", budget: NOT SET")
             + f" · {brief.get('email','')}_", ""]
    if not brief.get("budget"):
        lines.append("> ⚠️ No budget on file — send the welcome email to capture it before finalising.\n")
    for i, (role, c) in enumerate(picks, 1):
        lines.append(f"**{i}. {role} — {c['address']}** · {c['beds']} bed / {c['baths']} bath"
                     f" · asking {c['price_text']}")
        lines.append(f"   - {take_line(role, c)}")
        if c["dom"]:
            lines.append(f"   - On market {c['dom']} days.")
        lines.append("")
    if flagged:
        lines.append("---\n### ⚠️ Flagged for your review (extreme value gap — likely data mismatch, NOT auto-surfaced)")
        for c in flagged:
            lines.append(f"- {c['address']}: asking {money(c['ask'])} vs our {money(c['recon'])} "
                         f"({c['gap']:+.0f}%) — verify before using.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lead-id")
    ap.add_argument("--suburbs", help="comma-separated keys, e.g. robina,varsity_lakes")
    ap.add_argument("--beds", type=int, default=0)
    ap.add_argument("--baths", type=int, default=0)
    ap.add_argument("--budget", type=int)
    args = ap.parse_args()

    if args.lead_id:
        brief = brief_from_lead(args.lead_id)
        if args.budget:
            brief["budget"] = args.budget
    else:
        if not args.suburbs:
            sys.exit("--suburbs or --lead-id required")
        brief = {"suburbs": [s.strip().lower() for s in args.suburbs.split(",")],
                 "beds": args.beds, "baths": args.baths, "budget": args.budget, "email": ""}

    cands = gather(brief)
    if brief.get("budget"):
        cands = [c for c in cands if not (c["ask"] and c["ask"] > brief["budget"] * 1.25)]
    flagged = [c for c in cands if c["gap"] is not None and abs(c["gap"]) > SANITY_PCT]
    scoreable = [c for c in cands if c not in flagged]
    scoreable.sort(key=lambda c: -score(c, brief.get("budget")))
    picks = assign_roles(scoreable, brief.get("budget"))
    print(render(brief, picks, flagged))
    print(f"\n_[{len(cands)} candidates · {len(flagged)} flagged · draft only, nothing sent]_", file=sys.stderr)


if __name__ == "__main__":
    main()
