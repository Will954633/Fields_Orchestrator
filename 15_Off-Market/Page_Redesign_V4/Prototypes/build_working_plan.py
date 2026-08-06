#!/usr/bin/env python3
"""
build_working_plan.py — the private working plan, prototyped against a real address.

THE PRINCIPLE (from the 2026-08-06 review, and it is the right cut):
  Decisions only the OWNER can answer  -> ask them.
      what a move must work around · appetite for preparation · what matters most
      (price / certainty / speed / disruption / privacy) · what access a campaign
      could have · anything Fields would need to work around
  Decisions requiring INSPECTION and JUDGEMENT -> Fields recommends.
      sale method · listing price · channel mix · open-home cadence · photography
      · staging · settlement structure · which preparation work actually pays

  The owner supplies constraints. Fields supplies the recommendation. Reflecting
  their button presses back at them demonstrates nothing.

⚠ NO CONTACT PROMISE, either direction (decision 2026-08-06). The reviewed copy
  reinstated "nobody calls unless you ask" — removed here. What survives is the
  claim that is true regardless: we don't sell you on to whoever pays most.

⚠ Every recommendation is PROVISIONAL and says what would change it. The plan
  names what cannot responsibly be settled from public records — that list is the
  honest part, and it is also the argument for an inspection.

    python3 build_working_plan.py --slug 28-wedgebill-parade-burleigh-waters \
        --suburb burleigh_waters --answers answers_example.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = "/home/fields/Fields_Orchestrator"
for p in (ORCH, os.path.join(ORCH, "scripts"),
          os.path.join(ORCH, "15_Off-Market/Page_Redesign_V2")):
    sys.path.insert(0, p)

from dotenv import load_dotenv
from src.mongo_client_factory import get_mongo_client

# ── the five owner-only questions ──────────────────────────────────────────
QUESTIONS = [
    {"id": "move-constraint", "prompt": "What would a move need to work around?",
     "why": "Timing is usually a life constraint, not a market one.",
     "options": ["No fixed timing", "Buying another home first", "A school or work date",
                 "Tenants or an existing lease", "Finance or settlement coordination"]},
    {"id": "prep-appetite", "prompt": "How much preparation would feel reasonable?",
     "why": "Your appetite, not a list of jobs — we recommend the work after seeing the home.",
     "options": ["Only essential repairs and cleaning", "A modest presentation refresh",
                 "Willing to do more if the evidence supports it",
                 "Not sure — show me what would matter", "I'd prefer to sell largely as-is"]},
    {"id": "priority", "prompt": "What matters most?",
     "why": "This drives the method, the campaign shape and the pricing approach.",
     "options": ["Highest achievable price", "A predictable result",
                 "Moving within a particular period", "Minimal household disruption",
                 "Privacy", "Flexibility around the next purchase"]},
    {"id": "access", "prompt": "What access could a campaign reasonably have?",
     "why": "This is the input behind inspection planning — not a cadence you should have to choose.",
     "options": ["Weekends are generally fine", "Weekdays are easier",
                 "Limited inspections only", "Children, pets or work need considering",
                 "Property may be vacant", "Not sure yet"]},
    {"id": "work-around", "prompt": "Anything else we'd need to work around?",
     "why": "Where the household situation comes in.", "free_text": True},
]


def money(v):
    try:
        return f"${int(round(float(v))):,}"
    except Exception:
        return None


def money_m(v):
    try:
        f = float(v)
    except Exception:
        return None
    return ("$" + f"{f/1_000_000:.2f}".rstrip("0").rstrip(".") + " million") if f >= 1e6 \
        else f"${int(round(f)):,}"


def load_property(slug, suburb):
    c = get_mongo_client()
    gc, sm = c["Gold_Coast"], c["system_monitor"]
    doc = gc[suburb].find_one({"url_slug": slug}) or \
        gc[suburb].find_one({"address": {"$regex": slug.split("-")[0] + r"\s", "$options": "i"}})
    ms = (sm["market_pulse"].find_one({"suburb": suburb}) or {}).get("data_snapshot") or {}
    return doc or {}, ms


# ── the recommendation engine ──────────────────────────────────────────────
# Each function returns (recommendation, reasoning, what_would_change_it).

def recommend_method(ans, ms):
    """Sale method. The evidence favours private treaty in QLD, but the PRIORITY
    the owner gave is what selects it — otherwise this is the review's objection:
    copy that argues for one answer, then asks the owner to endorse it."""
    p = ans.get("priority")
    if p == "A predictable result":
        return ("We'd start with a priced private-treaty campaign and a defined offers period.",
                "A deadline gives the campaign a decision point without the cost or the "
                "no-price-guide problem an auction carries in Queensland.",
                "If you wanted an unconditional result on a fixed day, auction becomes "
                "the stronger structure despite the cost.")
    if p == "Privacy":
        return ("We'd run a controlled private-treaty campaign with inspections by appointment.",
                "Privacy and auction do not sit well together — an auction is a public "
                "process by design.",
                "If reach mattered more than discretion, this would change.")
    return ("We'd start with a priced private-treaty campaign.",
            "Across the largest Australian studies the sale method did not change the "
            "price once property, location and conditions were controlled for "
            "(Frino, Peat & Wright, 2012). What does differ is cost — an auction campaign "
            "here typically runs $5,000–$10,000 against $2,000–$5,000 — and Queensland law "
            "bars a price guide at auction, which works against how buyers filter.",
            "A firm deadline, or a genuinely unusual property with no reliable comparables, "
            "would push us toward auction.")


def recommend_timing(ans, ms):
    c = ans.get("move-constraint")
    season = ("November has historically sat about 3.3% above the annual catchment average "
              "and January about 1.4% below — a 4.7 point spread across 18,978 matched sales, "
              "2010–2025. That is a recurring pattern, not a forecast.")
    if c == "Buying another home first":
        return ("We'd work backwards from the purchase, not the calendar.",
                "Buying first sets the sequence — the campaign gets built to land when you "
                "need certainty. " + season,
                "A longer settlement can buy coordination room without changing the launch.")
    if c in ("A school or work date", "Finance or settlement coordination"):
        return ("We'd work backwards from your date.",
                "Your deadline is the constraint that matters. " + season +
                " A small seasonal difference is unlikely to outweigh a fixed date.",
                "If the date moved, the spring window would be worth revisiting.")
    if c == "Tenants or an existing lease":
        return ("We'd align the launch with the lease and plan access around the tenancy.",
                "Tenanted campaigns need notice periods built into the schedule, and "
                "presentation is harder to control. " + season,
                "A vacant possession date would open the timing up considerably.")
    return ("Nothing here needs a date yet.",
            season + " With no deadline, the campaign can be built to be ready rather than "
            "rushed to a month.",
            "A purchase or a date would make this the first thing we plan around.")


def recommend_prep(ans, doc):
    a = ans.get("prep-appetite")
    basic = ((doc.get("valuation_data") or {}).get("subject_property") or {}) \
        .get("features", {}).get("basic", {})
    reno = basic.get("renovation_level")
    known = (f"Our records read the renovation level as {reno} of 5" if reno
             else "We hold no interior read for this home")
    base = ("The highest-return pre-sale work is presentation, not reconstruction. Peer-"
            "reviewed hedonic work attributes up to around 7% of sale price to curb appeal "
            "(Johnson, Tidwell & Villupuram, 2020) — an association with presentation "
            "quality, not a guaranteed return on a given spend. What the data does not "
            "support is that a full renovation reliably recovers its cost.")
    if a == "I'd prefer to sell largely as-is":
        return ("We'd prepare rather than improve.",
                base + f" {known}, so we would confirm at inspection. As-is is a legitimate "
                "position — we would still want photography-grade cleaning and access.",
                "If a specific room reads badly in the photography, we would flag it.")
    if a in ("Willing to do more if the evidence supports it", "Not sure — show me what would matter"):
        return ("We'd start with a presentation assessment, not a renovation decision.",
                base + f" {known}. The priority order is usually gardens, exterior cleaning, "
                "minor repairs, then anything interior — but which items pay here cannot be "
                "settled from public records.",
                "The kitchen and bathrooms are the two rooms most likely to change the answer.")
    return ("We'd aim for a modest presentation refresh.",
            base + f" {known}.",
            "We would not recommend major expenditure before inspecting.")


def recommend_campaign(ans, ms):
    acc, pri = ans.get("access"), ans.get("priority")
    if acc == "Limited inspections only" or pri == "Minimal household disruption":
        return ("We'd group inspections rather than run frequent ad-hoc appointments.",
                "Concentrating buyers into fewer windows creates the same competitive "
                "pressure with far less intrusion on the household.",
                "Enquiry volume after launch would set the exact schedule.")
    if acc == "Property may be vacant":
        return ("We'd keep the inspection schedule flexible while the property is empty.",
                "A vacant home removes the usual constraint, so access can follow demand.",
                "Vacant homes photograph differently — styling may be worth assessing.")
    return ("We'd run a concentrated opening period, then set the schedule by enquiry.",
            "A fresh listing draws its largest pool of ready buyers in the first fortnight, "
            "so everything — photography, floor plan, copy, targeting — is prepared before "
            "launch rather than assembled while the campaign runs.",
            "Access constraints would reshape this before anything else.")


OPEN_DECISIONS = [
    "the final launch price",
    "whether styling would change how the rooms photograph",
    "the photography and media package",
    "which preparation work would return more than it costs",
    "settlement structure",
]


def build(slug, suburb, ans):
    doc, ms = load_property(slug, suburb)
    vd = doc.get("valuation_data") or {}
    rng = (vd.get("confidence") or {}).get("range") or {}
    out = [f"# A private working plan — {doc.get('address', slug)}", ""]
    out += ["*Provisional. Built from public records, recent sales and what you've told us. "
            "Nothing here has been confirmed by seeing the home.*", "", "---", ""]

    # Position — reflect the constraints as a situation, not a list of selections
    out += ["## Your current position", ""]
    pos = []
    c, p, a = ans.get("move-constraint"), ans.get("priority"), ans.get("prep-appetite")
    if c and c != "No fixed timing":
        pos.append(f"a move that has to work around {c.lower()}")
    else:
        pos.append("no fixed timing")
    if p:
        pos.append(f"{p.lower()} as the thing that matters most")
    if a:
        pos.append(f"an appetite for preparation described as \"{a.lower()}\"")
    out.append("You've told us: " + "; ".join(pos) + ".")
    if ans.get("work-around"):
        out.append(f"\nAnd to work around: {ans['work-around']}")
    if rng.get("low"):
        out.append(f"\nThe sales around this home currently support "
                   f"**{money_m(rng['low'])} – {money_m(rng['high'])}**.")

    for title, fn, arg in [("How we'd approach it", recommend_method, ms),
                           ("Timing", recommend_timing, ms),
                           ("Preparation", recommend_prep, doc),
                           ("The campaign", recommend_campaign, ms)]:
        rec, why, change = fn(ans, arg)
        out += ["", "---", "", f"## {title}", "", f"**{rec}**", "", why,
                "", f"*What would change this:* {change}"]

    out += ["", "---", "", "## What we can't settle from here", "",
            "These need someone to walk through the property:", ""]
    out += [f"- {d}" for d in OPEN_DECISIONS]
    out += ["", "That list is the honest part. Anyone who hands you a complete plan from "
                "public records alone is guessing at the half that needs seeing."]

    out += ["", "---", "", "## Where this could go next", "",
            "A walkthrough would replace the provisional items above with a plan specific to "
            "this home.", "",
            "**No agent is paying to appear here, and your interest in your own home is not "
            "sold to anyone.** Fields is the agency that built this — there's no third party "
            "being handed your address."]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--suburb", required=True)
    ap.add_argument("--answers", help="JSON file of answers; omit to print the questions")
    args = ap.parse_args()
    load_dotenv(os.path.join(ORCH, ".env"))
    if not args.answers:
        for q in QUESTIONS:
            print(f"\n{q['prompt']}\n  ({q['why']})")
            for o in q.get("options", []):
                print(f"    [ ] {o}")
            if q.get("free_text"):
                print("    ____________________")
        return
    ans = json.loads(Path(args.answers).read_text())
    md = build(args.slug, args.suburb, ans)
    out = HERE / f"plan_{args.slug}.md"
    out.write_text(md)
    print(md)


if __name__ == "__main__":
    main()
