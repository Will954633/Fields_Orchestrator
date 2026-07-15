#!/usr/bin/env python3
"""
One-off: write hand-authored, evidence-backed analyses + bespoke headlines for the
three "took too long" case studies Will picked (2026-06-02), each illustrating a
different controllable reason a sound home sat on the market:
  - 1 Glenalta Place, Robina      → vacant presentation (empty home)
  - 5 Myna Way, Burleigh Waters    → renovated 3-bed priced at the top of its bracket
  - 2 Georgetown Street, Varsity Lakes → below-standard listing photography

Facts are from each case's verified scaffold (build_case_study). Every analysis is
run through draft_case_analysis._validate (forbidden words / no-advice / no-forecast
/ full money format). Stays published=False — review via ?preview_cases=1 first.
"""
import sys, datetime as dt
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client
from scripts.property_reports.draft_case_analysis import _validate

MODEL_NOTE = "Fields editorial (hand-authored from verified scaffold)"

CASES = {
    "overpricing-1-glenalta-place-robina": {
        "concept": "presentation_vacant",
        "eyebrow": "Case study · presentation",
        "headline": "An empty house, and the months it waited",
        "analysis": {
            "setup": (
                "1 Glenalta Place, Robina is a three-bedroom, two-bathroom house with two car spaces "
                "on a 372-square-metre corner block, a short walk from Robina Town Centre. The condition "
                "read scored the home at 8 out of 10 overall, consistent with a well-maintained, move-in-ready "
                "property. Across the campaign the home was presented unoccupied: several interior photographs "
                "show bare rooms — an empty kitchen, an unfurnished hallway — while the living spaces carry "
                "digitally added (virtually staged) furniture rather than a furnished home."
            ),
            "decision": (
                "The home was marketed by private treaty in a suburb where the median time on market was "
                "26 days, across 2,353 transactions and a median sale price of $1,450,000, up 5.8 per cent "
                "year-on-year. It went to market vacant. An empty home leaves the buyer to picture the scale "
                "of each room and how they would live there without the cues a furnished home provides."
            ),
            "what_happened": (
                "The property sold for $1,235,000 by private treaty on 14 July 2025, after 185 days on the "
                "market — roughly seven times the suburb's 26-day median time on market over the same period."
            ),
            "analysis": (
                "An empty home changes how a buyer reads a space. The National Association of Realtors' 2023 "
                "staging survey found that 81 per cent of buyers' agents say staging helps buyers visualise a "
                "property and 48 per cent report it brings a faster sale; the same evidence points the other way "
                "for a vacant presentation. Virtual staging — furniture added to a photograph rather than the "
                "room — can fill the gap in an image, but the bare rooms return at the inspection. Here a "
                "well-maintained home in a convenient location, presented unoccupied, took 185 days against a "
                "26-day suburb median. The condition was not the variable; the presentation was."
            ),
            "lesson": (
                "This sale shows time on market as information in its own right. A well-kept home shown empty, "
                "in a strong-turnover suburb, spent close to half a year finding its buyer. The data records how "
                "a vacant presentation and a long campaign sat together; the reader can weigh what the staging "
                "evidence says about why."
            ),
        },
    },
    "overpricing-5-myna-way-burleigh-waters": {
        "concept": "priced_above_bracket",
        "eyebrow": "Case study · pricing",
        "headline": "A renovated home priced at the top of its bracket",
        "analysis": {
            "setup": (
                "5 Myna Way, Burleigh Waters is a renovated three-bedroom, two-bathroom house with four car "
                "spaces on a 447-square-metre block. The condition read scored it at 9 out of 10 across the "
                "kitchen, bathrooms, interior and outdoor categories — a comprehensively renovated home, "
                "described in the listing as having 'nothing more to spend, nothing more to do.'"
            ),
            "decision": (
                "The home was offered by private treaty at a figure near the top of the three-bedroom range "
                "for the suburb. Across 33 three-bedroom houses sold in Burleigh Waters during 2025, the median "
                "sale price was $1,420,000, and most transacted between $1,100,000 and $1,450,000. The "
                "three-bedroom homes that sold higher generally sat on larger blocks of 600 to 700 square "
                "metres, or sold within a few weeks."
            ),
            "what_happened": (
                "5 Myna Way sold for $1,665,000 by private treaty on 6 June 2025, after 105 days on the market, "
                "against a suburb median time on market of 30 days. The result sits about 17 per cent above the "
                "2025 median for a three-bedroom house in Burleigh Waters, on a 447-square-metre block."
            ),
            "analysis": (
                "A renovation lifts what a home can achieve, but the bedroom count still anchors the pool of "
                "buyers who consider it. As 'Before You List' documents, buyers in a bracket price first against "
                "the comparable evidence — here, other three-bedroom Burleigh Waters homes — and a figure set "
                "above that evidence narrows the field to the few buyers willing to pay a four-bedroom price for "
                "three bedrooms. The quality of the renovation is visible in the condition read; what the 105 "
                "days record is the distance between the asking position and where the three-bedroom comparable "
                "sales sat."
            ),
            "lesson": (
                "Condition and asking price are separate levers. A comprehensively renovated home can command "
                "the upper end of its bracket, but the bracket is set by the comparable sales for that bedroom "
                "count, not by the renovation alone. The 105 days are the record of a price that sat ahead of the "
                "three-bedroom evidence until a buyer met it."
            ),
        },
    },
    "overpricing-2-georgetown-street-varsity-lakes": {
        "concept": "presentation_photography",
        "eyebrow": "Case study · presentation",
        "headline": "The listing photos, and the buyers they reached",
        "analysis": {
            "setup": (
                "2 Georgetown Street, Varsity Lakes is a three-bedroom, two-bathroom house with two car spaces "
                "on a 400-square-metre block. The condition read scored the home at 7 out of 10 overall — a "
                "sound, well-kept family home. The listing photography sat below a professional standard: the "
                "facade image is partly obscured by overgrown shrubs and shot into harsh shadow; interior frames "
                "show a television left switched on, draped cloths and everyday clutter; the images are low "
                "resolution and include an unflattering overhead roof shot."
            ),
            "decision": (
                "The home went to market by private treaty in a suburb where the median time on market was 26.5 "
                "days and the median sale price $1,400,000, up 18.2 per cent year-on-year. The listing led with "
                "the photographs a buyer scrolling a portal sees first: a part-hidden facade, rooms with the "
                "television on and personal clutter in frame, and an overhead shot of the roofline."
            ),
            "what_happened": (
                "2 Georgetown Street sold for $1,075,000 by private treaty on 3 September 2025, after 89 days on "
                "the market — more than three times the suburb's 26.5-day median over the same period."
            ),
            "analysis": (
                "Photographs are the first contact almost every buyer has with a home, and the evidence ties "
                "their quality to engagement. Industry photography data (VHT Studios, aligned with National "
                "Association of Realtors figures) reports that listings with professional photography draw 118 "
                "per cent more online views and sell around 32 per cent faster, and Johnson, Tidwell and "
                "Villupuram (2020) find curb appeal alone can account for up to about 7 per cent of sale price. "
                "The condition read here was sound; the photography was not the home. A part-obscured facade, a "
                "television left on and clutter in frame give a scrolling buyer fewer reasons to click, and the "
                "89 days track a campaign that started behind on first impressions."
            ),
            "lesson": (
                "Presentation in the photographs and the quality of the home are not the same thing. A sound, "
                "well-kept house can be carried into the market by images that undersell it, and the time on "
                "market is where that shows up. The data records a 7-out-of-10 home, photographed below the "
                "standard its market expected, taking three times the local median to sell."
            ),
        },
    },
}


def main():
    coll = get_client()["system_monitor"]["case_study_library"]
    now = dt.datetime.utcnow().isoformat() + "Z"
    for cid, spec in CASES.items():
        err = _validate(spec["analysis"])
        if err:
            print(f"✗ {cid}: VALIDATION FAILED — {err}")
            continue
        analysis = dict(spec["analysis"], model=MODEL_NOTE, generated_at=now, attempt=1)
        r = coll.update_one(
            {"case_id": cid},
            {"$set": {
                "concept": spec["concept"],
                "eyebrow": spec["eyebrow"],
                "headline": spec["headline"],
                "analysis": analysis,
                "published": False,
            }},
        )
        print(f"✓ {cid}: validated + written (matched {r.matched_count})")


if __name__ == "__main__":
    main()
