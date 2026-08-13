#!/usr/bin/env python3
"""
build_learning_snapshot.py
==========================
Compiles the article generator's FEEDBACK SNAPSHOT — the small, curated,
diff-reviewable evidence file that `fields-automation/pipeline/learning_context.py`
turns into a prompt block.

Why a committed JSON file and not a live query
----------------------------------------------
The generator runs in GitHub Actions and writes PUBLIC copy. Evidence that
steers public copy must be reviewable BEFORE it ships, not fetched at runtime.
A file in the repo means Will can read the exact text the model will be told,
in the diff. It also costs zero RU and cannot fail mid-generation.

Refresh cadence: whenever `article_performance.py`, `build_hook_corpus.py` or
`build_content_learnings.py` produce a materially different picture. Weekly at most.

WHAT IS DELIBERATELY EXCLUDED (and why)
---------------------------------------
1. The 36 `dead_angle` records, verbatim.
   They are AN1-AN40 — Facebook *lead-form ad* concepts from the homeowner
   funnel. The article generator's angle namespace is BIGGEST_GAIN,
   POTENTIAL_LOSS, RENO_ROI ... There is ZERO overlap; the generator has never
   proposed an AN* angle and cannot. Injecting them as "do not re-propose"
   would answer a question nobody asked. Worse, several died as *topics the
   article pipeline legitimately covers* (AN13 renovation-ROI, AN19 suburb
   split, AN40 kitchen ROI) — on 70-450 impressions, out of market, against a
   lead form. Feeding those in as bans would kill working article angles on
   evidence that does not transfer.
   What DOES transfer is the failure MECHANIC, at hook level. That is what
   `dead_hook_mechanics` below carries — abstracted, and scoped in the prompt
   to headline construction only, never to topic selection.

2. `content_hook_aggregates` (hook_type weighted CTR).
   Ad copy, other market, lead-form context. We now have article-native
   headline CTR at 12,195 and 44,198 impressions, which strictly dominates it
   and says the same thing. Adding it would be tokens, not information.

3. Anything with `insufficient_evidence` or below the impression floor.

Usage:
    python3 scripts/build_learning_snapshot.py            # write + print
    python3 scripts/build_learning_snapshot.py --show     # print only
    python3 scripts/build_learning_snapshot.py --out PATH
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

DEFAULT_OUT = Path("/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning/"
                   "artifacts/learning_snapshot.json")

# Minimum paid impressions before a headline is allowed to be evidence of anything.
IMPRESSION_FLOOR = 500

# The laws that bear on ARTICLE WRITING. The corpus holds 26; most are about ad
# delivery, budget and bidding and have nothing to say to a writer. These do.
RELEVANT_LAW_IDS = [
    "law_headline_formula_for_cheap_clicks",
    "law_broad_market_commentary_is_the_anti_pattern",
    "law_abstract_without_dollars_dead",
    "law_dollar_anchor_not_sufficient",
    "law_aggregate_stats_dont_personalise",
    "law_facebook_scroll_depth_caps_at_50pct",
    "law_conversion_content_never_reached",
    "law_articles_are_dead_ends",
]

# The cautions that MUST travel with the evidence into the prompt. Non-negotiable:
# without these the block teaches the generator to be interesting rather than useful.
MANDATORY_CAUTION_IDS = [
    "caution_hook_corpus_has_no_lead_outcomes",
    "caution_reward_sparsity_verdicts_are_coinflips",
    "caution_out_of_market_economics_do_not_transfer",
]

# Failure mechanics abstracted from the 36 dead angles. Each is the shared
# mechanism behind >=3 of them, restated at hook level so it transfers to a
# headline. The angle codes are kept only so the claim is auditable.
DEAD_HOOK_MECHANICS = [
    {
        "mechanic": "Naming the category instead of showing the number",
        "detail": "'a five-figure gap', 'the valuation spread', 'the equity you can't see'. "
                  "The abstraction is the failure, not the topic.",
        "from_angles": ["AN6", "AN8", "AN23", "AN25", "AN39"],
    },
    {
        "mechanic": "A population statistic offered as if it were personal",
        "detail": "'89% of homes are overvalued', '3.6% national growth'. Aggregates create "
                  "awareness, never identification. One specific address outperforms every time.",
        "from_angles": ["AN1", "AN5", "AN24"],
    },
    {
        "mechanic": "Pure utility with no open question",
        "detail": "'Sold-price alerts', 'The Cost of Selling — itemised'. Useful, complete, "
                  "and therefore nothing to click. A headline that answers itself has no reader.",
        "from_angles": ["AN7", "AN16", "AN22"],
    },
    {
        "mechanic": "More than one number in the hook",
        "detail": "Three-figure frameworks and spreads compete with themselves. One dominant "
                  "number per headline. A second number belongs in the body.",
        "from_angles": ["AN23", "AN39", "AN31"],
    },
    {
        "mechanic": "Generic 'how to' / 'is now a good time' framing",
        "detail": "Confirmed on our OWN articles, not just ads — see the headline table.",
        "from_angles": ["AN8", "AN9", "AN13"],
    },
]


def build(db) -> dict:
    # ---- 1. Article-native headline outcomes -------------------------------
    headlines = []
    for r in db.article_performance.find(
            {"paid_headline.impressions": {"$gte": IMPRESSION_FLOOR}}):
        p = r.get("paid_headline") or {}
        if p.get("ctr") is None:
            continue
        headlines.append({
            "title": r.get("title"),
            "impressions": p["impressions"],
            "ctr_pct": round(p["ctr"] * 100, 2),
        })
    headlines.sort(key=lambda h: -h["ctr_pct"])

    # ---- 2. Read depth — the body problem ----------------------------------
    read_depth = []
    for r in db.article_performance.find({"read_depth.paid_sessions": {"$gte": 10}}):
        rd = r["read_depth"]
        read_depth.append({
            "title": r.get("title"),
            "paid_sessions": rd.get("paid_sessions"),
            "avg_scroll_pct": rd.get("paid_avg_scroll_pct"),
            "headline_ctr_pct": round((r.get("paid_headline", {}).get("ctr") or 0) * 100, 2),
        })

    # ---- 3. Distribution reality ------------------------------------------
    grades = {}
    for r in db.article_performance.find({}, {"evidence_grade": 1}):
        g = r.get("evidence_grade")
        grades[g] = grades.get(g, 0) + 1

    # ---- 4. Laws + cautions ------------------------------------------------
    def _pull(ids):
        out = []
        for _id in ids:
            d = db.content_learnings.find_one({"_id": _id})
            if not d:
                print(f"  WARN: learning '{_id}' not found — snapshot will omit it",
                      file=sys.stderr)
                continue
            out.append({
                "id": d["_id"],
                "title": d.get("title"),
                "actionable": d.get("actionable"),
                "confidence": d.get("confidence"),
                "evidence": d.get("evidence"),
            })
        return out

    laws = _pull(RELEVANT_LAW_IDS)
    cautions = _pull(MANDATORY_CAUTION_IDS)

    # Rule 7b applied to a read: an empty result must assert an outcome.
    if not headlines:
        raise RuntimeError(
            f"0 articles cleared the {IMPRESSION_FLOOR}-impression floor. "
            "article_performance is empty or paid_headline was never populated — "
            "this is a broken upstream, not an honest empty.")
    if len(laws) < len(RELEVANT_LAW_IDS):
        raise RuntimeError("content_learnings is missing laws the snapshot depends on; "
                           "re-run scripts/build_content_learnings.py before shipping this.")
    if len(cautions) < len(MANDATORY_CAUTION_IDS):
        raise RuntimeError("A MANDATORY caution is missing. The block must not ship without "
                           "its caveats — that is the whole point of it.")

    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "built_by": "scripts/build_learning_snapshot.py (Fields_Orchestrator)",
        "impression_floor": IMPRESSION_FLOOR,
        "headline_outcomes": headlines,
        "read_depth": read_depth,
        "distribution": grades,
        "laws": laws,
        "cautions": cautions,
        "dead_hook_mechanics": DEAD_HOOK_MECHANICS,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--show", action="store_true", help="print only, do not write")
    args = ap.parse_args()

    db = get_client()["system_monitor"]
    snap = build(db)
    text = json.dumps(snap, indent=2, ensure_ascii=False)

    if args.show:
        print(text)
        return

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(text):,} chars)")
    print(f"  {len(snap['headline_outcomes'])} headlines >= {IMPRESSION_FLOOR} impressions")
    print(f"  {len(snap['read_depth'])} articles with read-depth n>=10")
    print(f"  {len(snap['laws'])} laws, {len(snap['cautions'])} mandatory cautions")


if __name__ == "__main__":
    main()
