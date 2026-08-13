#!/usr/bin/env python3
"""
build_content_learnings.py — structure the funnel verdicts into a queryable corpus.

Fields' hardest-won content knowledge is trapped in Markdown prose:

  03_Facebook/Home_Owner_Lead_Funnel_Search/00_MASTER_LEDGER.md   (557 lines)
  03_Facebook/Home_Owner_Lead_Funnel_Search/cycles/*.md            (29 cycle docs)
  drafts/marketing-test-summary.md                                 (910 lines)
  system_monitor.fb_ad_tests                                       (17 docs)

An article/ad generator cannot read prose. This script writes each durable,
reusable finding into `system_monitor.content_learnings` as a structured
document with a stable `_id`, a `kind`, the finding, the EVIDENCE (numbers +
spend + n), the source file, the date established, and an honest `confidence`.

Kinds
-----
  archetype   — a copy archetype with a measured cost and intent profile
  dead_angle  — an angle tested and killed; must never be re-tested
  law         — a durable operating rule that survived its evidence review
  caution     — a rule that is CONTESTED, retracted, or rests on confounded data

Every record's `confidence` is the honest one. Most of this corpus rests on
single-digit leads: the entire homeowner funnel run produced SEVEN leads on
~$832 of spend across 43 angles. Nothing here is statistically significant.
It is the best evidence we have, which is a different claim.

Usage
-----
  python3 scripts/build_content_learnings.py           # write
  python3 scripts/build_content_learnings.py --dry-run
  python3 scripts/build_content_learnings.py --show    # agent-readable, cycle start
  python3 scripts/build_content_learnings.py --show --kind dead_angle
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

from shared.db import get_client  # noqa: E402

try:
    from shared.env import load_env  # noqa: E402

    load_env()
except Exception:  # pragma: no cover
    pass

COLLECTION = "content_learnings"

LEDGER = "03_Facebook/Home_Owner_Lead_Funnel_Search/00_MASTER_LEDGER.md"
CYCLES = "03_Facebook/Home_Owner_Lead_Funnel_Search/cycles/"
SUMMARY = "drafts/marketing-test-summary.md"
FB_TESTS = "system_monitor.fb_ad_tests"

# The denominator that governs the whole homeowner-funnel half of this corpus.
RUN_CONTEXT = (
    "Homeowner Lead Funnel search, 2026-07-28 to 2026-07-30 (3 days, 29 hourly "
    "cycles). ~$832 spent, ~13,190 impressions, 43 angles tested, ~57 variants "
    "killed, and SEVEN leads total (4 'Yes' selling intent, 3 'No' junk). "
    "Every per-angle verdict below rests on that denominator. Angles were killed "
    "on CTR and spend thresholds (0 leads at $15, or CPL > $25), not on "
    "statistically significant conversion differences — a kill means 'did not "
    "earn more budget', not 'proven not to work'. The wider two-week window "
    "(2026-07-15 to 07-29) spans ~$1,743 and 107 ads. The mandate doc's own "
    "tally is '$868 spend -> 7 leads -> 4 quality Yes (one of those a fake +93 "
    "phone)' — so the verifiable qualified count is THREE. All testing ran "
    "OUT OF MARKET (Brisbane + Sunshine Coast); economics do not transfer to "
    "the Gold Coast."
)


def _rec(**kw):
    kw.setdefault("run_context", RUN_CONTEXT)
    kw["built_at"] = datetime.now(timezone.utc).isoformat()
    return kw


# ==========================================================================
# ARCHETYPES
# ==========================================================================
ARCHETYPES = [
    _rec(
        _id="archetype_knowledge_gap",
        kind="archetype",
        title="Archetype A — 'Knowledge Gap' (information asymmetry): expensive, qualified",
        finding=(
            "Copy that tells the reader there is a specific dollar gap between "
            "what they believe their own home is worth and what the data shows, "
            "with the lead form as the thing that closes that gap, is the only "
            "mechanic that ever produced a Yes-selling-intent lead. Expensive "
            "per lead; every lead qualified."
        ),
        evidence=(
            "4 of the run's 7 leads. At discovery (Cycle 17): AN2 "
            "'missmillion_light' 2 leads @ $10.78 · AN14 '7daywindow_dark' 1 @ "
            "$22.29 · AN15 '150kgap_dark' 1 @ $23.33 → avg $16.70 CPL, 4/4 Yes "
            "intent. These CPLs are SNAPSHOTS and rose as spend accrued: by "
            "Cycle 22 the same three read $12.72 / $26.02 / $25.58."
        ),
        numbers={"avg_cpl_aud_at_discovery": 16.70, "n_leads": 4,
                 "pct_yes_intent": 100, "angles": ["AN2", "AN14", "AN15"]},
        source_file=f"{CYCLES}cycle_20260729_1601.md",
        source_detail=f"Cycle 17, 2026-07-29 16:01 AEST; restated {LEDGER} line 27",
        date_established="2026-07-29",
        confidence="low",
        confidence_reason=(
            "Corroborated across three independent angles and topics, which is "
            "why it is not the weakest thing here — but it rests on FOUR lead "
            "events, and one of the four carried a fake +93 phone number, so "
            "the verifiable count is three. The mandate doc calls every cycle "
            "verdict 'a coin-flip dressed as a finding'."
        ),
        actionable=(
            "Use when lead QUALITY matters more than volume — anything Will "
            "will personally call. Never quote $16.70 as a forecast CPL."
        ),
    ),
    _rec(
        _id="archetype_identity_threat",
        kind="archetype",
        title="Archetype B — 'Identity Threat' (social comparison): cheap, worthless",
        finding=(
            "Binary social-classification hooks — 'which group is your home "
            "in?' — stop scroll and fill forms cheaply, but the form itself "
            "satisfies the curiosity, so the submitter has no downstream need. "
            "Every lead it produced stated NO selling intent."
        ),
        evidence=(
            "3 of 7 leads. AN3 'neighbour_dark' 2 leads @ $4.04 (both No) · "
            "AN28 'thesplit_dark' 1 @ $4.72 (No) → avg $4.27 CPL, 0/3 Yes "
            "intent at Cycle 17. THAT $4.27 IS THE MOST FLATTERING INSTANT THE "
            "ARCHETYPE EVER HAD. AN28's CPL then decayed $4.72 → $8.38 → $9.15 "
            "→ $9.80, and at its Cycle 26 cull the real figure was 432 "
            "impressions, ~$28 spend, 1 junk lead — roughly $28 CPL. The "
            "ledger header separately restates the archetype average as $4.70."
        ),
        numbers={"avg_cpl_aud_at_discovery": 4.27, "avg_cpl_aud_ledger_header": 4.70,
                 "an28_cpl_at_cull_aud": 28.0, "n_leads": 3, "pct_yes_intent": 0,
                 "angles": ["AN3", "AN28"]},
        source_file=f"{CYCLES}cycle_20260729_1601.md + {CYCLES}cycle_20260730_1001.md",
        source_detail="Cycle 17 discovery; Cycle 26 cull",
        date_established="2026-07-29",
        confidence="low",
        confidence_reason=(
            "n=3 leads. '0% qualified' is 0 of 3 — consistent with a true "
            "qualification rate up to ~60%. And the headline cost advantage "
            "largely evaporated with more spend, so even the cheap half of the "
            "finding is weaker than it reads."
        ),
        actionable=(
            "Do not buy this archetype expecting sellers, and do not quote "
            "'~$4 CPL' — use the range $4.27–$28 or the final figure."
        ),
    ),
    _rec(
        _id="archetype_hybrid_failed",
        kind="archetype",
        title="The Archetype A x B hybrid has failed once and is UNRESOLVED once",
        finding=(
            "Two attempts to combine Identity Threat's scroll-stop with "
            "Knowledge Gap's intent qualification. The first failed clearly: "
            "conditional framing destroys the scroll-stop — identity threat "
            "works as an IMMEDIATE classification, never as a hypothetical. "
            "The second never got a lead window before the run ended."
        ),
        evidence=(
            "AN31 'The Tomorrow Test' (identity binary + 'if you listed "
            "tomorrow'): light 0.00% CTR on 93 impressions, dark 2.99% on 67; "
            "160 combined, $7.62, 0 leads — killed Cycle 21. AN35 'The Two "
            "Categories' (current-state classification + knowledge-gap payoff): "
            "dark culled at 0.0% CTR / 104 impressions; LIGHT survived at "
            "4.69–5.9% CTR across three reads and was never given an afternoon "
            "conversion window."
        ),
        numbers={"attempts": 2, "clear_failures": 1, "unresolved": 1},
        source_file=f"{CYCLES}cycle_20260729_2001.md + {CYCLES}cycle_20260730_1201.md",
        source_detail="Cycles 18, 21, 25, 27, 28",
        date_established="2026-07-30",
        confidence="low",
        confidence_reason=(
            "AN31 is a clean CTR failure readable without leads. AN35_light is "
            "NOT a failure — it is untested on the metric that matters."
        ),
        actionable=(
            "AN35_light is the one open GC deployment candidate from the run. "
            "If hybridising again, use current-state classification, never a "
            "conditional verb."
        ),
    ),
]

# ==========================================================================
# LAWS — mechanics that survived their evidence review
# ==========================================================================
LAWS = [
    _rec(
        _id="law_conversion_dna",
        kind="law",
        title="The conversion DNA: ONE dominant dollar number + 'a home like YOURS' + soft CTA",
        finding=(
            "Converting copy carries exactly one visceral dollar figure, "
            "attached to something that could happen to the reader's own home, "
            "closed by a soft CTA to check their own comparable sales. Every "
            "dead angle fails on self-relevance. Interesting facts do not "
            "convert; personal identification does."
        ),
        evidence=(
            "4 of 4 Yes-intent leads share it (AN2 home-value gap, AN14 "
            "listing window, AN15 agent-vs-comps gap). Counter-evidence at both "
            "boundaries: AN39's three-agent '$280,000 spread' returned 0 link "
            "clicks on 114 impressions given a fair auction; AN3 — a story "
            "about two OTHER homes — produced only junk. Champion AN2 took 2 "
            "clicks by ~56 impressions."
        ),
        numbers={"converting_axes": 3, "angles_tested": 43},
        source_file=f"{CYCLES}cycle_20260730_1101.md",
        source_detail="Stated Cycle 16, refined Cycle 27",
        date_established="2026-07-30",
        confidence="medium",
        confidence_reason=(
            "The CTR half (single vs multi-figure) rests on a clean 0.00% read "
            "over 114 impressions. The conversion half rests on 4 leads, and "
            "the converters were also the earliest-launched and "
            "longest-running ads — exposure time is a confounder."
        ),
        actionable="Default template for any seller-facing hook.",
    ),
    _rec(
        _id="law_personal_open_loop",
        kind="law",
        title="High CTR without a personal open loop never converts",
        finding=(
            "Angles that generate interest, anger, awareness or relief about a "
            "TOPIC reliably produce strong CTR and zero leads. Conversion needs "
            "an open loop only the form can close ('what is MY number?')."
        ),
        evidence=(
            "NINE separate high-CTR non-converters: AN9 conditioning 4.9-8.7% "
            "CTR / $31.11 / 0 leads (peak 14.29% dark) · AN10 stale-listing "
            "11.1-11.6% / $31.45 / 0L · AN13 reno 8.98-10.19% / ~$31 / 0L · "
            "AN17 '3.7% Rule' 4.5-7.8% / $24.79 / 311 impressions / 0L · AN5 "
            "national 6.5-9.8% / $23.12 / 0L · AN19 suburb split 5.06-5.49% / "
            "415 combined / 0L · AN26 speed signal 7.59% (3rd highest CTR in "
            "the portfolio) / 289 combined / $22.31 / 0L · AN30 $80K photo "
            "~4.6% / 317 combined / 0L."
        ),
        numbers={"high_ctr_non_converters": 9},
        source_file=f"{CYCLES}cycle_20260729_0801.md + {CYCLES}cycle_20260729_1901.md",
        source_detail="Cycles 9, 16, 19, 20, 22",
        date_established="2026-07-29",
        confidence="high",
        confidence_reason=(
            "HIGH for the negative claim 'CTR does not predict conversion in "
            "this account' — nine angles, thousands of impressions, zero leads "
            "between them. LOW for the causal explanation (open loops)."
        ),
        actionable=(
            "Never promote an angle on CTR alone. CTR and conversion measure "
            "different things here."
        ),
    ),
    _rec(
        _id="law_dollar_anchored",
        kind="law",
        title="The Knowledge-Gap mechanic is DOLLAR-ANCHORED — strip the number and it collapses",
        finding=(
            "The winning mechanic does not generalise to non-monetary fears. "
            "Run on a real, top-ranked seller fear but with no dollar figure, "
            "scroll-stop collapses."
        ),
        evidence=(
            "AN37 'The Settlement Gap' targeted the #1 Halo fear (owning two "
            "homes at once, ~40% of market, 515 keyword mentions) and was built "
            "deliberately WITHOUT a dollar figure as a falsifier: ~1.3% CTR on "
            "312 combined impressions, dark just 0.62%, 0 leads. Killed at "
            "Cycle 24 and named 'the run's headline learning'."
        ),
        numbers={"ctr_pct": 1.3, "impressions": 312, "leads": 0},
        source_file=f"{CYCLES}cycle_20260730_0801.md",
        source_detail="Cycle 24, 2026-07-30 08:01 AEST",
        date_established="2026-07-30",
        confidence="medium",
        confidence_reason=(
            "One deliberately-constructed falsification test, well powered for "
            "CTR (312 impressions distinguishes 1.3% from ~5%). n=1 angle."
        ),
        actionable="Every seller hook carries a dollar figure or it does not ship.",
    ),
    _rec(
        _id="law_dollar_anchor_not_sufficient",
        kind="law",
        title="A dollar anchor is NECESSARY BUT NOT SUFFICIENT — one number, not a puzzle",
        finding=(
            "Adding the proven dollar anchor to a dead axis does not revive it, "
            "and multi-figure hooks fail even when dollar-anchored. The reader "
            "must not have to solve a comparison. The winning shape is a single "
            "dominant number about a home like theirs."
        ),
        evidence=(
            "AN39 'The Valuation Spread' (three appraisals $1.2M/$1.35M/$1.48M "
            "→ a $280,000 spread): 0 link clicks on 114 combined impressions, "
            "0.00% CTR both backgrounds, AFTER a starvation-relief cull "
            "guaranteed a fair auction for a full hour. AN40 'Kitchen Math' "
            "($80,000 kitchen returns ~$34,000): dark 0.0% on 69 impressions, "
            "light 1.4% on 71 — the second kill of the renovation axis after "
            "AN13's narrative-only death."
        ),
        numbers={"an39_ctr_pct": 0.0, "an39_impressions": 114,
                 "an40_dark_ctr_pct": 0.0, "an40_light_ctr_pct": 1.4},
        source_file=f"{CYCLES}cycle_20260730_1101.md + {CYCLES}cycle_20260730_1201.md",
        source_detail="Cycles 27, 28",
        date_established="2026-07-30",
        confidence="medium",
        confidence_reason=(
            "Two independent CTR confirmations, no lead window needed. Small "
            "denominators (114 and ~140 impressions)."
        ),
        actionable="One number per hook. Never a spread, never a three-way framework.",
    ),
    _rec(
        _id="law_abstract_without_dollars_dead",
        kind="law",
        title="Abstract concepts die at scroll speed — 7 of 7, zero exceptions",
        finding=(
            "Any hook that NAMES a gap rather than SHOWING it, or that costs "
            "more than one cognitive step, is scrolled past. Cognitive load is "
            "the shared failure mode of every abstract-axis kill."
        ),
        evidence=(
            "AN6 'five-figure gap' 0.6% CTR / 151 impressions · AN8 'a "
            "different number' 2.4% / 247 · AN12 visual info-gap 0.00% / 76 · "
            "AN20 'wrong year' 0.9% / 106 · AN22 net proceeds 2.81% / 178 · "
            "AN23 three numbers 2.99% / 167 · AN25 equity 3.68% / 190. "
            "Contrast AN2's concrete '$1,440,000 → $2,500,000' at 9.44% CTR."
        ),
        numbers={"confirmations": 7, "exceptions": 0},
        source_file=f"{CYCLES}cycle_20260729_1901.md",
        source_detail="First 2026-07-28; 7/7 tally 2026-07-29",
        date_established="2026-07-29",
        confidence="high",
        confidence_reason=(
            "Seven independent angles, all CTR-based (no lead window needed), "
            "thousands of impressions, no exceptions."
        ),
        actionable="Show the number. Never name the category the number is in.",
    ),
    _rec(
        _id="law_aggregate_stats_dont_personalise",
        kind="law",
        title="Aggregate statistics create awareness; single specific examples create identification",
        finding=(
            "'89% of estimates are wrong' makes the reader think about most "
            "people's homes. 'One home was valued $1,440,000 and sold for "
            "$2,500,000' makes them think about their own. The same statistic "
            "failed in three separate packagings."
        ),
        evidence=(
            "AN1 raw stat 2.4% CTR / 295 impressions / $21.71 / 0 leads · AN4 "
            "same stat plus an address ask 1.4% / 155 · AN24 same stat as a "
            "research narrative, dark 3.92% / 102, light 3.03% / 99. Six "
            "variants, ~900 impressions, zero leads."
        ),
        numbers={"packagings": 3, "variants": 6, "impressions": 900, "leads": 0},
        source_file=f"{CYCLES}cycle_20260729_1501.md",
        source_detail="Cycle 16",
        date_established="2026-07-29",
        confidence="high",
        confidence_reason="Three formats, ~900 impressions, zero conversions.",
        actionable=None,
    ),
    _rec(
        _id="law_fear_beats_aspiration",
        kind="law",
        title="Loss framing beats gain framing — but the upside frame was never properly read",
        finding=(
            "Aspirational 'you could gain $X' framing did not stop the scroll; "
            "loss framing did. Attributed to prospect theory. NOTE this is one "
            "angle, and the run's only other upside hook never delivered."
        ),
        evidence=(
            "AN18 'Week Three' (+4% premium = $60,000, from 44,937 GC sales): "
            "0.00% CTR on 121 impressions, BOTH backgrounds, $5.00 — killed. "
            "Same period, AN14's loss frame ('75% of attention gone by Day 7') "
            "converted at $6.42 CPL with 11.32% CTR."
        ),
        numbers={"an18_ctr_pct": 0.0, "an18_impressions": 121},
        source_file=f"{CYCLES}cycle_20260728_2201.md",
        source_detail="Cycle 8, 2026-07-28",
        date_established="2026-07-28",
        confidence="medium",
        confidence_reason=(
            "0.00% on 121 impressions is unambiguous, but it is a single angle "
            "and the question was deliberately re-opened later — see "
            "caution_upside_frame_untested."
        ),
        actionable="Default to loss framing; treat upside framing as untested, not dead.",
    ),
    _rec(
        _id="law_one_fact_not_two",
        kind="law",
        title="Double-shock competes with itself — lead with ONE fact and ONE question",
        finding=(
            "Combining two proven shocks in one ad does not compound. The facts "
            "compete for attention and the personal question gets lost."
        ),
        evidence=(
            "AN21 'The Price-Cut Number' fused AN14's timing with AN2's dollar "
            "shock (~$47,000 at week 4): light 170 impressions / 6.47% CTR / "
            "$13.37 / 0 leads; dark 70 / 1.43%. Cycle note: 'proven converters "
            "lead with ONE jarring fact, then a PERSONAL question. AN21 led "
            "with two facts and no question.'"
        ),
        numbers={"impressions": 240, "leads": 0},
        source_file=f"{CYCLES}cycle_20260729_1801.md",
        source_detail="Cycle 19",
        date_established="2026-07-29",
        confidence="low",
        confidence_reason=(
            "One angle, and its CTR was actually fine — the failure is a "
            "zero-conversion inference over ~240 impressions."
        ),
        actionable=None,
    ),
    _rec(
        _id="law_background_by_format",
        kind="law",
        title="Background is format-dependent for CTR: data/table -> light, narrative -> dark",
        finding=(
            "The same copy on the wrong background loses most of its clicks. "
            "Codified as launch policy: data/table/comparison launch LIGHT "
            "only; narrative/story launch DARK only; ambiguous launches both "
            "and kills the loser at 50 impressions."
        ),
        evidence=(
            "Seven independent confirmations, zero exceptions at the time. "
            "AN21 table: light 10.53% / 95 impressions vs dark 1.43% / 70 — a "
            "7.4x gap. AN22: light 3.74% vs dark 0.00% / 74. AN23: light 2.63% "
            "vs dark 0.00% / 72. AN25: light 5.56% / 90 vs dark 0.00% / 77. "
            "Narrative side: AN14 dark 11.32% vs light 1.92% (5.9x); AN9 dark "
            "14.29% vs light 4.81% (3.0x); AN3 light 6.25% / 96 vs dark 1.15% "
            "/ 87."
        ),
        numbers={"confirmations": 7, "max_gap_multiple": 7.4},
        source_file=f"{CYCLES}cycle_20260729_1401.md",
        source_detail="First 2026-07-28; policy at 6/6 on 2026-07-29",
        date_established="2026-07-29",
        confidence="medium",
        confidence_reason=(
            "Many confirmations, but each on only 70-200 impressions, and "
            "there is one documented angle-specific exception (AN35)."
        ),
        actionable=(
            "Ship both backgrounds for a genuinely new format; assume the rule "
            "only for formats it has already been confirmed on."
        ),
    ),
    _rec(
        _id="law_bg_ctr_vs_bg_conversion",
        kind="law",
        title="Light gets the clicks; dark gets the leads — the two background rules OPPOSE each other",
        finding=(
            "A distinct and opposite finding to law_background_by_format, found "
            "later. Light wins CTR on data formats, but dark produced roughly "
            "3x the lead rate across both archetypes. Optimising background on "
            "CTR can therefore cost leads. The two rules were never reconciled."
        ),
        evidence=(
            "Cycle 18: dark 4,038 impressions / 5 leads = 1 per 808 (~$58 per "
            "lead); light 4,886 / 2 leads = 1 per 2,443 (~$139 per lead). Lead "
            "rate 0.150% vs 0.066%. End-of-run: dark 5,870 impressions / 5 "
            "leads / $404 vs light 6,857 / 2 leads / $395. Only "
            "AN2_missmillion breaks the pattern — and it is the champion."
        ),
        numbers={"dark_leads": 5, "dark_impressions": 5870,
                 "light_leads": 2, "light_impressions": 6857},
        source_file=f"{CYCLES}cycle_20260729_1701.md",
        source_detail="Cycles 18, 22, 24",
        date_established="2026-07-29",
        confidence="low",
        confidence_reason=(
            "Seven lead events split 5/2. One lead moving sides changes the "
            "ratio materially, and the biggest exception is the champion ad."
        ),
        actionable=(
            "Hold both rules in tension. Do not kill a dark variant on CTR "
            "alone while it is still inside a lead window."
        ),
        contradicts=["law_background_by_format"],
    ),
    _rec(
        _id="law_auction_starvation",
        kind="law",
        title="Above ~16 ad sets fresh ones starve — relieve by CULLING a competitor, not raising budget",
        finding=(
            "Above roughly 16 concurrent ad sets at $15/day on this account, "
            "Meta declines to serve brand-new ad sets at all. Budget is not the "
            "lever — they cannot spend even $1 of their $15. Removing a "
            "competing ad set restores delivery within an hour."
        ),
        evidence=(
            "AN39/AN40 launched 08:01, ACTIVE and not in review, had <11 "
            "impressions each after ~2 hours (8i/$0.15, 9i/$0.42, 11i/$0.95, "
            "7i/$0.60) against 12 established competitors — versus prior new "
            "ad sets clearing 300-580 impressions in their first window (AN14 "
            "366 and 384, AN2_light 584). Culling AN28 (2 ad sets, ~$30/day) at "
            "10:01 lifted them to ~48-64 impressions within one hour."
        ),
        numbers={"before_impressions": 11, "after_impressions_1h": 64,
                 "starvation_ceiling_adsets": 16},
        source_file=f"{CYCLES}cycle_20260730_1001.md + {CYCLES}cycle_20260730_1101.md",
        source_detail="Cycles 25, 26, 27",
        date_established="2026-07-30",
        confidence="medium",
        confidence_reason=(
            "Cleanly diagnosed, pre-committed, and the intervention reversed it "
            "within the hour. Single instance."
        ),
        actionable=(
            "Diagnose zero delivery as starvation before calling it a copy "
            "fail. Subtract, verify pickup, then add."
        ),
    ),
    _rec(
        _id="law_lead_window_is_afternoon",
        kind="law",
        title="Every lead landed 13:00-22:00 AEST — morning CTR is not a conversion verdict",
        finding=(
            "Delivery runs all day but conversion does not. Overnight is dead "
            "for leads yet live for CTR signal — the run deliberately exploited "
            "that to accumulate free CTR reads on fresh probes."
        ),
        evidence=(
            "All 7 leads landed 13:00-22:00 across both days (28 Jul 15:47, "
            "18:28, 19:11, 20:06, 21:54, 22:40; 29 Jul 15:23). Morning "
            "08:00-13:00 delivered ~1,561 impressions for 0 leads on both "
            "days. Overnight 22:00-08:00 delivered ~1,792 impressions at ~179/h "
            "for 0 leads, and ~1,550 / $36 / 0 leads on day 3."
        ),
        numbers={"lead_window": "13:00-22:00 AEST", "morning_leads": 0,
                 "overnight_leads": 0},
        source_file=f"{CYCLES}cycle_20260729_2101.md",
        source_detail="Cycles 16, 23, 24, 25",
        date_established="2026-07-29",
        confidence="medium",
        confidence_reason=(
            "7 of 7 in one 9-hour window is striking, but n=7 and it is partly "
            "explained by budget-cap timing — converters exhausted their "
            "$15/day by mid-morning and reset around 13:00. The docs "
            "acknowledge the confound."
        ),
        actionable="Read CTR any time. Read conversion only after an afternoon window.",
    ),
    _rec(
        _id="law_morning_delivery_rate",
        kind="law",
        title="Morning delivery is ~58-73% of afternoon rate; overnight ~40%",
        finding=(
            "Do not assess a fresh ad's delivery as failed before roughly 12:00 "
            "AEST — the shortfall may be the daypart, not the creative."
        ),
        evidence=(
            "Day 1 afternoon (13:00-22:00, 9h): ~$248 / ~3,896 impressions = "
            "~$28/h, ~433 impressions/h. Overnight (10h): ~$110 / ~1,792 = "
            "~$11/h, ~179/h. Day 2 morning (08:00-13:00, 5h): ~$123 / ~1,561 = "
            "~$25/h, ~312/h. Intra-morning ramp 08-09 ~160/h → 09-10 ~190/h → "
            "10-11 ~310/h."
        ),
        numbers={"morning_pct_of_afternoon": [58, 73], "overnight_pct": 40},
        source_file=f"{CYCLES}cycle_20260729_1001.md",
        source_detail="Cycles 11, 23",
        date_established="2026-07-29",
        confidence="high",
        confidence_reason="Direct measurement, repeated across three dayparts and two days.",
        actionable=None,
    ),
    _rec(
        _id="law_kill_thresholds",
        kind="law",
        title="The operating kill rules — what 'dead' actually means in this corpus",
        finding=(
            "The mechanical thresholds are themselves a durable artefact: they "
            "define the word 'dead' in every dead_angle record here."
        ),
        evidence=(
            "Auto-pause at spend >= $15 with 0 leads, or >= $20 with CPL > $25. "
            "Winner flags at CPL <= $8 (report) / <= $5 (alert). Manual CTR "
            "kill: <2.5% CTR on 150+ impressions = scroll-stop failure. Minimum "
            "50 impressions per variant for any CTR assessment. Budget $15/day "
            "per ad set, target 16-24 active, checkpoint hourly 08:00-22:00 "
            "AEST. From the marketing summary: minimum 7 days before analysing "
            "an experiment, minimum 20 sessions before any session-quality "
            "conclusion."
        ),
        numbers={"autopause_spend_aud": 15, "autopause_cpl_aud": 25,
                 "ctr_kill_pct": 2.5, "ctr_kill_impressions": 150},
        source_file=f"{LEDGER} + {SUMMARY}",
        source_detail="Ledger lines 35-40; summary Part 15",
        date_established="2026-07-28",
        confidence="high",
        confidence_reason=(
            "Configuration, not inference. But note what it implies: a $15 kill "
            "threshold means most dead-angle verdicts rest on 70-450 "
            "impressions and ZERO lead events. They are CTR verdicts wearing "
            "conversion language."
        ),
        actionable=None,
    ),
    _rec(
        _id="law_seller_lead_engine_does_not_exist",
        kind="law",
        title="There is no working homeowner-SELLER lead flow — the only proven engine is buyer-side",
        finding=(
            "Before the funnel search began, the seller lead ad had produced "
            "zero leads on $203 over 90 days. The only functioning lead engine "
            "in the account targets BUYERS. Any plan assuming an existing "
            "seller funnel assumes something that does not exist."
        ),
        evidence=(
            "90 days to 2026-07-28, total account spend $800.91: 'Leads: "
            "Analyse Your Home — Before an Agent' (SELLER) $203.29, 0 leads, "
            "CPL infinite. 'Leads: Buyer Brief — 5 that matter' (BUYER) "
            "$160.03, 9 leads, $17.78 CPL. Traffic AYH video copy test $167.92, "
            "0 leads (86 landing-page views). Remarketing $82.30, 0 leads. The "
            "AYH landing funnel is separately dead: analyse_leads channel dead "
            "since 2026-04-10, ~1 Lead/week reaching Meta."
        ),
        numbers={"seller_spend_aud": 203.29, "seller_leads": 0,
                 "buyer_spend_aud": 160.03, "buyer_leads": 9,
                 "buyer_cpl_aud": 17.78, "account_90d_spend_aud": 800.91},
        source_file=LEDGER,
        source_detail="PHASE 0 — Learning",
        date_established="2026-07-28",
        confidence="high",
        confidence_reason=(
            "A zero over $203 and 90 days is a well-powered null. The buyer "
            "$17.78 rests on 9 leads and is directional."
        ),
        actionable=(
            "The $5 seller CPL target is a North Star, not a day-1 number — "
            "buyer leads (an easier ask) cost $17.78."
        ),
    ),
    _rec(
        _id="law_core_suburb_beats_broad_gc",
        kind="law",
        title="Core-suburb targeting beats broad Gold Coast for engagement depth, at half the volume",
        finding=(
            "Narrowing from broad Gold Coast to Robina / Varsity Lakes / "
            "Burleigh Waters multiplies every engagement metric 2-3x while "
            "roughly halving volume. The source calls this the one variable it "
            "cleanly isolated."
        ),
        evidence=(
            "V2 test, 173 visitors (broad GC) vs 102 (core suburbs): 2min+ "
            "sessions 17.3% → 25.5% · cards per visitor 11.0 → 13.7 · card "
            "click rate 0.54% → 1.34% (2.5x) · property view rate 2.9% → 8.9% "
            "(3.1x) · CTA click rate 1.2% → 4.0% (3.3x) · scroll depth flat at "
            "~50%."
        ),
        numbers={"broad_visitors": 173, "core_visitors": 102,
                 "cta_click_multiple": 3.3, "property_view_multiple": 3.1},
        source_file=SUMMARY,
        source_detail="Part 10; Part 4 item 7",
        date_established="2026-04-03",
        confidence="medium",
        confidence_reason=(
            "The cleanest isolation in the summary, but n=275 visitors total "
            "and the effects rest on double-digit event counts."
        ),
        actionable=None,
    ),
    _rec(
        _id="law_facebook_scroll_depth_caps_at_50pct",
        kind="law",
        title="Scroll depth from Facebook traffic caps at ~50% regardless of content quality",
        finding=(
            "A traffic-type ceiling, not a content problem. Better content makes "
            "people slow down and read more carefully; it does not make them "
            "scroll further. Conversion content must live in the first 10-15 "
            "cards."
        ),
        evidence=(
            "Three separate tests, ~1,200 total sessions, identical result: V2 "
            "broad 50.1%, V2 core 50.3%, V3 49.8% — average and median both "
            "~50%, unchanged by content improvements that lifted time on page "
            "+24%."
        ),
        numbers={"scroll_depth_pct": 50, "tests": 3, "sessions": 1200},
        source_file=SUMMARY,
        source_detail="Part 4 item 6; Part 10",
        date_established="2026-04-05",
        confidence="high",
        confidence_reason="The best-replicated finding in the whole corpus — three tests, ~1,200 sessions.",
        actionable="Put anything that must be seen above the halfway point of the page.",
    ),
    _rec(
        _id="law_conversion_content_never_reached",
        kind="law",
        title="Only 10% of feed visitors reach the CTA — it sits below the scroll ceiling",
        finding=(
            "The V3 feed CTA sits at card ~40-45 of 50, past the ~50% scroll "
            "ceiling, so most visitors mathematically cannot see it."
        ),
        evidence=(
            "V3 section funnel: feed view 86% → Seller Anchor 38% (a 48pp "
            "drop) → Big Mistake 32% → Insight 30% → Compare 24% → Fields Pick "
            "15% → Save Worthy 14% → Seller Bridge 13% → CTA 10%."
        ),
        numbers={"cta_reach_pct": 10, "first_drop_pp": 48},
        source_file=SUMMARY,
        source_detail="Part 7",
        date_established="2026-04-05",
        confidence="high",
        confidence_reason="Direct funnel measurement across the full V3 session set.",
        actionable=None,
    ),
    _rec(
        _id="law_articles_are_dead_ends",
        kind="law",
        title="Article pages are dead ends — 95% read and leave; zero property views from any ad",
        finding=(
            "Articles work as top-of-funnel engagement and produce essentially "
            "no navigation deeper into the site. This is the structural "
            "middle-of-funnel gap."
        ),
        evidence=(
            "Of 310 tracked Facebook sessions: 296 stayed on the article page "
            "only, 2 reached /for-sale, 1 reached a property page, 11 reached "
            "market-intelligence. And: zero tracked property views across ALL "
            "ads in the attribution data."
        ),
        numbers={"sessions": 310, "article_only": 296, "property_views": 1},
        source_file=SUMMARY,
        source_detail="Part 7",
        date_established="2026-04-05",
        confidence="high",
        confidence_reason="Large-sample and unambiguous.",
        actionable=(
            "A new hook cannot fix this. Do not attribute a conversion failure "
            "to the headline until a next step exists."
        ),
    ),
    _rec(
        _id="law_headline_formula_for_cheap_clicks",
        kind="law",
        title="The cheap-click headline formula: specific price + specific timeframe + implied story",
        finding=(
            "For top-of-funnel click volume, the reliably cheapest headline "
            "shape is a concrete price and a time gap with a story the reader "
            "wants resolved. Congruent with the later AN2 conversion finding."
        ),
        evidence=(
            "'Someone Bought This Robina Home Six Months Ago' $0.16/click, 946 "
            "clicks, $152.96 · 'The Owner Paid $475,000 in 2010. They're Now "
            "Asking $1,285,000' $0.31/click, 111 clicks · '$1,710,000 on "
            "Outrigger Drive' $0.14/click, 92 clicks · 'Who buys for $1,550,000 "
            "and sells eighteen months later for $3,465,000?' $0.12/click, 48 "
            "clicks."
        ),
        numbers={"cpc_range_aud": [0.12, 0.31]},
        source_file=SUMMARY,
        source_detail="Part 6",
        date_established="2026-04-05",
        confidence="high",
        confidence_reason=(
            "HIGH for click cost and volume — thousands of clicks. UNKNOWN for "
            "session quality; the source flags that explicitly."
        ),
        actionable="Use for reach and traffic goals only, never as a lead-quality signal.",
    ),
    _rec(
        _id="law_direct_utility_cheapest_clicks",
        kind="law",
        title="Direct listing ads get the cheapest clicks in the account — and this CONTRADICTS the seller finding",
        finding=(
            "'Houses for sale in [suburb]' is the cheapest, highest-volume "
            "creative by a wide margin. Note the tension: plain utility is dead "
            "for SELLER lead-gen (AN7, AN16) and alive for BUYER traffic."
        ),
        evidence=(
            "'Traffic: Houses for sale - Robina' $176.19, 1,477 link clicks, "
            "$0.12/click over 16 days — the account's #1 ad by BOTH volume and "
            "CPC. Combined Robina/VL/BW $183.15 / 816 clicks / $0.22. Burleigh "
            "Waters only $111.56 / 263 clicks / $0.42. The summary flags this "
            "ad was omitted entirely from the original March analysis "
            "('Error 4', a major omission)."
        ),
        numbers={"spend_aud": 176.19, "link_clicks": 1477, "cpc_aud": 0.12},
        source_file=SUMMARY,
        source_detail="Part 4 item 4; Part 5 Error 4; Part 6",
        date_established="2026-04-05",
        confidence="high",
        confidence_reason=(
            "HIGH for clicks (1,477 of them). Session quality is a named "
            "critical data gap — 1,477 clicks with no quality data attached."
        ),
        actionable=None,
    ),
    _rec(
        _id="law_broad_market_commentary_is_the_anti_pattern",
        kind="law",
        title="Broad market commentary without a personal stake gets the most expensive clicks",
        finding=(
            "Informational suburb-level headlines with no curiosity gap cost "
            "20-60x the best formats."
        ),
        evidence=(
            "'Robina's Fastest-Moving Year in Half a Decade' $7.29/click (copy) "
            "and $5.10/click (original), 8 clicks total, ~$56 spent · "
            "'Southern Gold Coast Apartment Boom' $5.83/click, 6 clicks · "
            "'Gold Coast Interstate Migration' $2.02/click, 6 clicks · 'Robina "
            "Sales Volume Surges 111%' $3.31/click, 2 clicks. Against "
            "$0.12-$0.31 for story formats. Independently corroborated by the "
            "hook corpus: the same 'Fastest-Moving Year' ad is the WORST "
            "performer above the evidence floor at 0.05% CTR on 1,879 "
            "impressions."
        ),
        numbers={"worst_cpc_aud": 7.29, "best_cpc_aud": 0.12, "multiple": 60},
        source_file=SUMMARY,
        source_detail="Part 6; corroborated by system_monitor.content_hook_corpus",
        date_established="2026-04-05",
        confidence="high",
        confidence_reason=(
            "A 20-60x cost spread survives any plausible confound, and the "
            "independently-built hook corpus reproduces it."
        ),
        actionable="Never ship a suburb-statistic headline with no personal stake.",
    ),
    _rec(
        _id="law_sell_focused_pushy_content_dead",
        kind="law",
        title="Sell-focused pushy content does not work on Facebook",
        finding=(
            "Facebook users do not think of themselves as sellers. Sell content "
            "needs search intent, not scroll mode."
        ),
        evidence=(
            "$49 spent across 6 sell-themed ads produced ZERO website sessions. "
            "'Test - Sell: Robina' $38.50 / 7 clicks / $5.50 CPC. 'The Science "
            "of Getting More for Your Home' $0.42 spent, 0 clicks, paused at "
            "108 impressions / 0.0% CTR."
        ),
        numbers={"spend_aud": 49, "ads": 6, "sessions": 0},
        source_file=f"{SUMMARY} + {FB_TESTS}",
        source_detail="Summary Part 4 item 2, Part 13; fb_ad_tests ad_pause 2026-03-05",
        date_established="2026-03-13",
        confidence="medium",
        confidence_reason=(
            "A zero-sessions result is strong, but the source itself caveats: "
            "'This was all POST_ENGAGEMENT optimisation. Nobody has tested sell "
            "content under OFFSITE_CONVERSIONS.' It also names an untested "
            "exception — curiosity-driven sell content reframed as a story — "
            "and the entire AN1-AN43 run is arguably that exception, and it "
            "DID produce leads."
        ),
        actionable=(
            "Do not re-test casually. The story-framed exception is already "
            "partly validated by the funnel run."
        ),
    ),
    _rec(
        _id="law_lifestyle_photos_dead",
        kind="law",
        title="Lifestyle / aspirational imagery without a data hook is dead",
        finding="Photography without data context does not drive action.",
        evidence=(
            "$157 spent across awareness and engagement 'Fields Photography' "
            "campaigns produced 17 link clicks at $2.40/click from awareness "
            "and ONE link click from engagement — quantified elsewhere as "
            "'$157, 1 session'. The paused ad record: 0.0% CTR on 968 "
            "impressions, $2.47, 0 clicks, against an account average of 0.29%. "
            "The hook corpus independently shows the two photography creatives "
            "at 0.28% and 0.15% CTR — its bottom two."
        ),
        numbers={"spend_aud": 157, "link_clicks": 18, "cpc_aud": 2.40},
        source_file=f"{SUMMARY} + {FB_TESTS}",
        source_detail="Summary Part 4 item 3, Part 13; fb_ad_tests 2026-03-05",
        date_established="2026-03-13",
        confidence="medium",
        confidence_reason=(
            "$157 with one session is a real null, and the hook corpus "
            "reproduces it. Both photography ads ran under OUTCOME_AWARENESS, "
            "which does not optimise for clicks — partially objective-confounded."
        ),
        actionable=None,
    ),
    _rec(
        _id="law_organic_automated_data_cards_dead",
        kind="law",
        title="Automated 2x/day AI data-card posting is dead — do not re-enable",
        finding=(
            "Content without personality does not work for an unknown brand. "
            "People follow people, not data platforms."
        ),
        evidence=(
            "AI-generated data cards posted 2x/day at 06:30 and 17:00 AEST: "
            "zero engagement, Facebook could not find an audience, nobody "
            "clicked. Killed 2026-03-30. Independently corroborated by "
            "system_monitor.fb_ad_tests: 15 of 15 finalised organic page posts "
            "graded 'weak' with total_engagements of exactly 0, across 10 photo "
            "and 5 text posts and 11 different templates."
        ),
        numbers={"posts_measured": 15, "weak": 15, "total_engagements": 0,
                 "templates": 11},
        source_file=f"{SUMMARY} + {FB_TESTS}",
        source_detail="Summary Part 9; fb_ad_tests post_performance, finalised 2026-03-09",
        date_established="2026-03-30",
        confidence="medium",
        confidence_reason=(
            "An absolute zero across 15 posts and two independent records. But "
            "organic REACH was never separately measured, so this may be a "
            "distribution problem rather than a content problem — the records "
            "cannot distinguish."
        ),
        actionable=(
            "Never judge a content template on its organic post performance. "
            "Nothing on this page has ever gotten organic engagement, so a zero "
            "carries no information about the copy."
        ),
    ),
    _rec(
        _id="law_factual_accuracy_gate_is_load_bearing",
        kind="law",
        title="The editorial factual-accuracy guardrail killed a queued ad mid-run",
        finding=(
            "A 'cash-offer discount' big-number hook was cut before build "
            "because 2026 data would not support the size of the gap. Precedent: "
            "cut rather than ship a misleading figure."
        ),
        evidence=(
            "Verbatim: 'Dropped by research: a cash-offer discount big-number "
            "hook — 2026 data says unconditional cash discount is only ~1-5%, "
            "so a large-gap card would overstate it (factual-accuracy "
            "guardrail). Cut rather than ship a misleading figure.' CGT "
            "concepts were separately rejected on comps-fit grounds. Every "
            "launched card carried an 'Illustrative example' footer and a "
            "comparable-RANGE payoff to satisfy the no-single-valuation-in-"
            "headlines rule."
        ),
        numbers={},
        source_file=f"{CYCLES}cycle_20260730_1201.md",
        source_detail="Cycle 28",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason="A documented decision, not an inference.",
        actionable=None,
    ),
]

# ==========================================================================
# CAUTIONS — contested, retracted, confounded, or open
# ==========================================================================
CAUTIONS = [
    _rec(
        _id="caution_reward_sparsity_verdicts_are_coinflips",
        kind="caution",
        title="READ FIRST — the entire copy-discovery run rests on 7 lead events",
        finding=(
            "You cannot optimise copy, let alone sequences of copy, on seven "
            "events. This is the single most important caveat on every "
            "archetype and conversion claim in this corpus. The corpus says so "
            "about itself."
        ),
        evidence=(
            "Verbatim from the mandate scoping doc: '$868 spend → 7 leads → 4 "
            "quality \"Yes\" (one of those a fake +93 phone). Blended CPL $124. "
            "The killer problem is reward sparsity. 1-2 leads per winning ad is "
            "statistically noise. You cannot optimise copy — let alone "
            "sequences of copy — on 7 events. Every cycle \"verdict\" to date is "
            "a coin-flip dressed as a finding. All conversions landed Day 1, "
            "then flatlined despite continued spend — but off 1-2 leads that "
            "decay is indistinguishable from noise.'"
        ),
        numbers={"spend_aud": 868, "leads": 7, "quality_yes": 4,
                 "verifiable_quality_yes": 3, "blended_cpl_aud": 124},
        source_file="03_Facebook/Home_Owner_Lead_Funnel_Search/04_EXPANDED_MANDATE_SCOPING.md",
        source_detail="Section 1",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason="The corpus's own self-assessment, arithmetically checkable.",
        actionable=(
            "The prescribed fix was to move the optimisation target up-funnel "
            "to engagement, where there are 50-100x the data points per dollar."
        ),
    ),
    _rec(
        _id="caution_one_of_four_quality_leads_was_fake",
        kind="caution",
        title="'4 quality leads' is really 3 — one carried a fake +93 phone number",
        finding=(
            "Every CPL and qualification rate computed on 4 quality leads "
            "understates the true cost by roughly 33%."
        ),
        evidence="Mandate scoping section 1: '7 leads → 4 quality \"Yes\" (one of those a fake +93 phone).'",
        numbers={"claimed_quality": 4, "verifiable_quality": 3},
        source_file="03_Facebook/Home_Owner_Lead_Funnel_Search/04_EXPANDED_MANDATE_SCOPING.md",
        source_detail="Section 1",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason="Stated directly in the source.",
        actionable=None,
    ),
    _rec(
        _id="caution_cpl_snapshots_decay",
        kind="caution",
        title="Every CPL in these documents is a moving snapshot, not a settled figure",
        finding=(
            "Spend accrues hourly while leads do not, so an angle's quoted CPL "
            "rises continuously after its last lead. Two documents quoting the "
            "same angle at different hours will disagree and neither is wrong."
        ),
        evidence=(
            "AN14 quoted across cycles 6→22 on the SAME single lead: $6.42 → "
            "$8.50 → $16.78 → $18.87 → $21.23 → $22.29 → $24.13 → $26.02. AN15: "
            "$15.74 → $19.25 → $23.33 → $25.58. AN28: $4.72 → $8.38 → $9.80 → "
            "~$28. Archetype B average quoted as $4.27 (Cycle 17) and $4.70 "
            "(ledger header)."
        ),
        numbers={},
        source_file=f"{CYCLES} (multiple) + {LEDGER}",
        source_detail="Observed 2026-07-28 to 2026-07-30",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason="Arithmetic.",
        actionable="Always cite the cycle a CPL came from, or cite the range.",
    ),
    _rec(
        _id="caution_out_of_market_economics_do_not_transfer",
        kind="caution",
        title="All copy testing ran OUT OF MARKET — funnel shape transfers, economics do not",
        finding=(
            "Every angle was tested in Brisbane and the Sunshine Coast with the "
            "Gold Coast excluded, to protect the ~1M GC core audience. An "
            "explicit validity ceiling applies."
        ),
        evidence=(
            "Verbatim: 'Transfers to GC: funnel SHAPE, PII-resistance RANKING, "
            "warm-up DEPTH, hook MECHANICS — these are structural/psychological. "
            "Does NOT transfer: absolute CPL, absolute conversion rate, whether "
            "the person is a real prospect (Brisbane people aren't your "
            "buyers). Economics are re-validated only in a GC run — never trust "
            "a Brisbane CPL as a GC forecast.' Out-of-market leads received "
            "nothing post-submit by design."
        ),
        numbers={},
        source_file="03_Facebook/Home_Owner_Lead_Funnel_Search/04_EXPANDED_MANDATE_SCOPING.md",
        source_detail=f"Section 10; {LEDGER} lines 13-18",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason="An explicit scoping statement.",
        actionable="Never quote a funnel-run CPL as a Gold Coast forecast.",
    ),
    _rec(
        _id="caution_confounded_content_conclusions",
        kind="caution",
        title="Almost every March 2026 content 'learning' was a confounded comparison",
        finding=(
            "'Property stories beat generic market commentary' was produced by "
            "comparing an OFFSITE_CONVERSIONS campaign against a "
            "POST_ENGAGEMENT campaign. Content, optimisation goal, campaign "
            "structure, budget, run period and targeting all differed at once. "
            "The optimisation goal was likely the primary driver. Which CONTENT "
            "type works best remains UNANSWERED."
        ),
        evidence=(
            "Verbatim: 'Most of our early comparisons compared ads that "
            "differed in content, optimisation goal, campaign structure, AND "
            "targeting all at once. When we said \"property stories beat market "
            "commentary,\" we were actually comparing an OFFSITE_CONVERSIONS "
            "campaign against a POST_ENGAGEMENT campaign. We can't cleanly "
            "separate which factor caused the difference.' The corrected "
            "record: 'Is Now a Good Time to Buy' delivered the HIGHEST QUALITY "
            "sessions in the entire account — 127s (Burleigh Waters), 83s "
            "(Robina), 28-40% engagement — and looked bad only because "
            "POST_ENGAGEMENT made its sessions cost $8.62 vs $2.31. The "
            "isolating experiment (#3) got ONE website view and is inconclusive."
        ),
        numbers={"bw_session_s": 127, "robina_session_s": 83,
                 "cost_per_session_post_engagement_aud": 8.62,
                 "cost_per_session_offsite_aud": 2.31,
                 "isolation_experiment_views": 1},
        source_file=SUMMARY,
        source_detail="Part 1 line 10; Part 5 Error 1; Part 16 item 5",
        date_established="2026-04-05",
        confidence="high",
        confidence_reason=(
            "A methodological finding about our own data, stated explicitly and "
            "repeatedly by the source. Needs no sample."
        ),
        actionable=(
            "NEVER compare content types across campaign objectives. Use "
            "content_hook_aggregates' objective-controlled rows, not the raw "
            "ones."
        ),
    ),
    _rec(
        _id="caution_broad_vs_custom_targeting_retracted",
        kind="caution",
        title="'Broad targeting beats custom audiences' is RETRACTED — do not treat it as a law",
        finding=(
            "This appears in CLAUDE.md and the funnel ledger as an established "
            "learning. The marketing summary lists it as Error 3, a corrected "
            "mistake. It is not safe to treat as established in either "
            "direction."
        ),
        evidence=(
            "Verbatim correction: 'Original claim: Watch This Sale (broad + "
            "Advantage) outperformed Is Now Good Time (custom audiences). "
            "Correction: These campaigns also had different optimisation goals, "
            "different content, different budgets, and different run periods. "
            "We cannot attribute the performance difference to targeting alone. "
            "This was a confounded comparison.'"
        ),
        numbers={},
        source_file=SUMMARY,
        source_detail="Part 5, Error 3",
        date_established="2026-04-05",
        confidence="high",
        confidence_reason=(
            "HIGH that the claim is confounded. The underlying question — does "
            "broad beat custom — is simply unproven."
        ),
        actionable=(
            "Treat as an open question. CLAUDE.md and the funnel ledger both "
            "still carry it as established — a live inconsistency someone "
            "should reconcile."
        ),
        contradicts=["CLAUDE.md 'Established learnings'", f"{LEDGER} PHASE 0"],
    ),
    _rec(
        _id="caution_offsite_conversions_lever_has_a_caveat",
        kind="caution",
        title="'OFFSITE_CONVERSIONS is the #1 lever' is rated Medium-High by its own source, not settled",
        finding=(
            "Optimisation goal appears to dominate content type in explaining "
            "campaign performance differences. The magnitude is large and the "
            "mechanism is logical, but the isolating experiment failed and the "
            "evidence is entangled with content type."
        ),
        evidence=(
            "3.7x cost difference, $2.31 vs $8.62 per session, at campaign "
            "level. Source caveat verbatim: 'This was confounded with content "
            "type. Experiment #3 was designed to isolate this variable (same "
            "\"Is Now Good Time: BW\" content in both goals) but only got 1 "
            "website view in the OFFSITE_CONVERSIONS version — not enough "
            "data.' Facebook was 'literally finding different types of people "
            "for each campaign'."
        ),
        numbers={"cost_multiple": 3.7, "isolation_experiment_views": 1},
        source_file=SUMMARY,
        source_detail="Part 4 item 1; Part 13",
        date_established="2026-04-05",
        confidence="medium",
        confidence_reason=(
            "The source's OWN rating is Medium-High with an explicit "
            "confounding note. CLAUDE.md states it as settled; the source does "
            "not. A 3.7x effect probably survives the confound, but it has "
            "never been isolated."
        ),
        actionable="Keep using it. Do not cite it as a clean result.",
    ),
    _rec(
        _id="caution_phone_field_contradiction",
        kind="caution",
        title="Two sources give OPPOSITE verdicts on whether a required phone field suppresses leads",
        finding=(
            "The ledger's fifth established learning says the phone field is "
            "free. The later relaunch plan says it doubled cost per lead and "
            "killed quality. Both cite the SAME Buyer Brief v3 form. Unresolved."
        ),
        evidence=(
            "Ledger lines 88-89: 'Native FB lead forms with name+email+phone "
            "proven to capture 100% phone with no volume drop (Buyer Brief v3 "
            "form). Phone field does NOT suppress leads.' Versus "
            "NEXT_CYCLE_AD_PLAN_2026-07-30.md section 3: 'Adding the "
            "phone-required field hurt — Buyer Brief v3 (name+email+phone) cost "
            "$30/lead, 0 hot; the lighter v1/v2 got hot leads at ~$15.'"
        ),
        numbers={"v3_cpl_aud": 30, "v1_v2_cpl_aud": 15},
        source_file=f"{LEDGER} lines 88-89 vs 03_Facebook/Home_Owner_Lead_Funnel_Search/NEXT_CYCLE_AD_PLAN_2026-07-30.md",
        source_detail="Section 3",
        date_established="2026-07-30",
        confidence="low",
        confidence_reason=(
            "A direct contradiction between two internal sources about the same "
            "form. Neither can be relied on until reconciled."
        ),
        actionable=(
            "RESOLVE BEFORE RELYING ON EITHER. This is one of the four "
            "'established learnings' in CLAUDE.md and it is contested."
        ),
        contradicts=["CLAUDE.md 'Established learnings'"],
    ),
    _rec(
        _id="caution_the_funnel_is_not_the_bottleneck",
        kind="caution",
        title="The ad funnel is NOT the broken part — the leak is downstream follow-up",
        finding=(
            "The two-week retrospective concludes ads produced real contactable "
            "people at $4-30 each, and zero became an enquiry because the leads "
            "were not worked. More ads do not fix this."
        ),
        evidence=(
            "2026-07-15 to 07-29: 21 contactable Facebook instant-form leads, "
            "18 with BOTH phone and email, 0 inbound enquiries or booked calls, "
            "6 of 21 contacted — 'the newest ~15 (incl. a warm \"yes\" seller) "
            "never worked'. Verbatim: 'Headline: the ad funnel is NOT the "
            "broken part. The leak is downstream. The fix that unlocks "
            "enquiries is working the leads we already have, not more ads.' "
            "Also ~9 on-site address captures, all no-contact, several "
            "out-of-area (Worongary, Ashmore)."
        ),
        numbers={"contactable_leads": 21, "with_phone_and_email": 18,
                 "contacted": 6, "enquiries": 0},
        source_file="03_Facebook/Home_Owner_Lead_Funnel_Search/NEXT_CYCLE_AD_PLAN_2026-07-30.md",
        source_detail="Section 1",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason="Direct lead-by-lead accounting.",
        actionable="Before proposing new copy, check whether the existing leads were worked.",
    ),
    _rec(
        _id="caution_portfolio_fragmentation_destroyed_power",
        kind="caution",
        title="107 concurrent ads split the budget so thin most arms could never reach a verdict",
        finding=(
            "The retrospective verdict on the whole method. The dark/light "
            "novelty matrix produced arms with $4-15 lifetime spend and no "
            "statistical power."
        ),
        evidence=(
            "2026-07-15 to 07-29: ~$1,743 spend, 107 ads running, 58,537 "
            "impressions, 819 link clicks, 21 contactable leads, 0 inbound "
            "enquiries. Verbatim: 'The 38-ad AN## dark/light novelty matrix "
            "split the budget so thin most arms got $4-15 and 0 conversions — "
            "no statistical power, ~$600+ drained on noise.' Prescribed "
            "replacement: max 4 arms at ~$15-20/day for 5-7 days, ~$100+ per "
            "arm."
        ),
        numbers={"spend_aud": 1743, "ads": 107, "impressions": 58537,
                 "link_clicks": 819, "enquiries": 0,
                 "prescribed_max_arms": 4, "prescribed_spend_per_arm_aud": 100},
        source_file="03_Facebook/Home_Owner_Lead_Funnel_Search/NEXT_CYCLE_AD_PLAN_2026-07-30.md",
        source_detail="Sections 1, 3, 5",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason="An accounting fact, not an inference.",
        actionable="Max 4 arms, ~$100+ each, before drawing any conclusion.",
    ),
    _rec(
        _id="caution_meta_delivery_preference_is_not_quality",
        kind="caution",
        title="Meta's own delivery preference predicts engagement, NOT conversion",
        finding=(
            "The ads Meta chose to serve hardest were repeatedly the ones that "
            "never converted. Do not read impression share as an early winner "
            "signal."
        ),
        evidence=(
            "AN5 took 20% of ALL impressions (114 of 571) on day 1 as "
            "Facebook's delivery leader and converted 0 leads on $23.12. AN8 "
            "was 'the highest-delivery angle with the worst engagement rate' — "
            "247 impressions, 2.4% CTR, 0 leads. Conversely AN2, the champion, "
            "was never a delivery leader."
        ),
        numbers={"an5_impression_share_pct": 20, "an5_leads": 0},
        source_file=f"{CYCLES}cycle_20260728_1615.md",
        source_detail="Cycles 2, 5",
        date_established="2026-07-28",
        confidence="medium",
        confidence_reason="Two clear cases plus the champion counter-example; day-1 sample.",
        actionable=None,
    ),
    _rec(
        _id="caution_ctr_verdict_vs_conversion_verdict",
        kind="caution",
        title="A CTR verdict is legitimate at any hour; a conversion verdict needs the 13:00-22:00 window",
        finding=(
            "A methodological rule the run developed and applied repeatedly. "
            "Killing on morning CTR when the ad's whole purpose was a "
            "conversion test destroys the test."
        ),
        evidence=(
            "Applied at Cycle 24 (AN35 HELD at 2.7% CTR because 'its real test "
            "— does the hybrid CONVERT? — needs lead-hours; overnight can't "
            "answer'), Cycle 27 (AN39 KILLED on 0.00%/114 impressions because "
            "'that is a CTR/scroll-stop read — it does not need the afternoon "
            "lead-window, so killing it now is not the premature-kill error'), "
            "and Cycle 29 (AN36_dark killed on 0.00%/121, AN36_light held "
            "despite 0.76%)."
        ),
        numbers={},
        source_file=f"{CYCLES}cycle_20260730_1101.md",
        source_detail="Cycles 24, 27, 29",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason="A method consistently applied and documented, not an empirical claim.",
        actionable=None,
    ),
    _rec(
        _id="caution_upside_frame_untested",
        kind="caution",
        title="THREE angles were launched and never read — they are OPEN, not dead",
        finding=(
            "The run was switched off before its last three concepts delivered. "
            "One of them, AN43, is the first non-loss-framed hook ever tried. "
            "Do not record these as failures."
        ),
        evidence=(
            "AN43 'Over Asking' (asked $965,000, a buyer paid $1,061,000 — "
            "$96,000 over asking; grounded in auctions averaging ~+4.4% over, "
            "2026, 14k+ sales): launched 12:01 on 2026-07-30, still 0 "
            "impressions and $0 spend at 13:01, verified ACTIVE (ramp lag, not "
            "review-block). Same status for AN42 'The Bank's Number' "
            "($1,180,000 bank valuation vs $1,340,000 sold = $160,000 gap) and "
            "AN41 'The Asking-Sold Gap' ($1,290,000 listed / $1,201,000 sold = "
            "$89,000; 21 and 39 impressions, 0% CTR)."
        ),
        numbers={"open_angles": ["AN41", "AN42", "AN43"]},
        source_file=f"{CYCLES}cycle_20260730_1301.md",
        source_detail="Cycles 27, 28, 29",
        date_established="2026-07-30",
        confidence="high",
        confidence_reason=(
            "Zero delivery is a fact, not a result. Recording these as dead "
            "would be the error this record exists to prevent — it partially "
            "re-opens law_fear_beats_aspiration."
        ),
        actionable="If the funnel restarts, these three are the queue.",
    ),
    _rec(
        _id="caution_video_cpc_untested",
        kind="caution",
        title="Video CPCs looked competitive with static — the test was designed and never run",
        finding=(
            "Video was cheap enough to be worth a real test and aligns with the "
            "Will-on-camera organic strategy, but the video-vs-static "
            "experiment was never executed."
        ),
        evidence=(
            "From 2026-04-01: 'Video: Leading vs Lagging Indicators' "
            "$0.57/click, 45 clicks in 4 days · 'Video: Market Update - Varsity "
            "Lakes' $0.36/click, 34 clicks in 2 days · 'Traffic: Houses for "
            "Sale - Video Format' $0.31/click, 74 clicks in 3 days. Variables "
            "table status: 'Ad format (static image vs video) — Emerging, need "
            "2+ weeks.'"
        ),
        numbers={"cpc_range_aud": [0.31, 0.57]},
        source_file=SUMMARY,
        source_detail="Part 12, Experiment H",
        date_established="2026-04-05",
        confidence="low",
        confidence_reason="Days-old data, no session-quality comparison, experiment never run.",
        actionable=None,
    ),
    _rec(
        _id="caution_hook_corpus_has_no_lead_outcomes",
        kind="caution",
        title="The semantic hook corpus contains ZERO lead-optimised ads — CTR is all it can measure",
        finding=(
            "All 92 semantically annotated ads sit in OUTCOME_ENGAGEMENT, "
            "OUTCOME_TRAFFIC or OUTCOME_AWARENESS campaigns. Not one is "
            "OUTCOME_LEADS, and no attributable lead joins to any of them. The "
            "hook_type / emotional_lever / message_theme evidence therefore "
            "speaks ONLY to click-through, never to conversion — the exact "
            "distinction law_personal_open_loop says is decisive."
        ),
        evidence=(
            "Join of ad_profiles (203) to ad_semantic_annotations (92) matches "
            "92 of 92 on ad_id. Objective mix of the matched set: "
            "OUTCOME_ENGAGEMENT 57 ads / 74,649 impressions · OUTCOME_TRAFFIC "
            "33 / 217,956 · OUTCOME_AWARENESS 2 / 12,603. The account's 108 "
            "OUTCOME_LEADS ads — including all 43 homeowner-funnel angles — are "
            "entirely UNANNOTATED. Attributed leads in the corpus: 0. Only 55 "
            "of 92 rows clear a 500-impression evidence floor."
        ),
        numbers={"annotated_ads": 92, "unannotated_ads": 111,
                 "outcome_leads_annotated": 0, "attributed_leads": 0,
                 "rows_above_evidence_floor": 55},
        source_file="system_monitor.content_hook_corpus (built 2026-08-13)",
        source_detail="scripts/build_hook_corpus.py",
        date_established="2026-08-13",
        confidence="high",
        confidence_reason="Direct count over the joined collections.",
        actionable=(
            "Annotating the 108 OUTCOME_LEADS ads is the single highest-value "
            "unblock — it would let the hook taxonomy be tested against leads "
            "rather than clicks."
        ),
    ),
]

# ==========================================================================
# DEAD ANGLES — never re-test
# (code, description, why it died + numbers, confidence)
# ==========================================================================
_DEAD = [
    ("AN1", "raw statistic — 'Honest Number: 89% overvalued'",
     "Aggregate statistics create awareness, not personal urgency; outperformed "
     "3-5x by every narrative and question hook. 2.4% CTR, 295 impressions "
     "(dark+light), $21.71, 0 leads. Killed Cycle 6, 2026-07-28.", "high"),
    ("AN3", "'A home near you sold' — neighbour social comparison",
     "The cheapest lead source in the whole account at $4.04 CPL, and BOTH "
     "leads were No-intent junk. Dark killed at 1.15% CTR (Cycle 4); light "
     "auto-paused at $16.03 / 279 impressions / 0 leads. Later diagnosis: it is "
     "a story about two OTHER homes, not the viewer's.", "medium"),
    ("AN4", "address friction — AN1's copy plus an address field on the form",
     "The cleanest A/B in the run: 1.43% combined CTR on 155 impressions vs "
     "AN1's 2.96% on IDENTICAL copy. Address friction kills at the SCROLL "
     "level, before the form is ever seen — this is not form abandonment. "
     "Killed Cycle 3, 2026-07-28.", "medium"),
    ("AN5", "'Your street isn't the national average' (0.4-2.3% vs 3.6%)",
     "Meta's own delivery favourite — 20% of all day-1 impressions, 12.35% peak "
     "CTR — and still converted zero. 6.5-9.8% CTR, $23.12, 600+ impressions, 0 "
     "leads, auto-paused at the $15 threshold. The lesson is about Meta's "
     "delivery preference, not the angle.", "medium"),
    ("AN6", "'five-figure gap' — an abstract label with no figure",
     "0.6% CTR on 151 impressions; light variant 0.00% on 60. Killed Cycle 3, "
     "2026-07-28. One of the 7-of-7 abstract kills.", "high"),
    ("AN7", "'Sold-price alerts' — pure utility, no curiosity gap",
     "Utility states exactly what you get, so it opens no loop. A sub-$5 CPL "
     "was predicted and never materialised. Light 0.00% CTR / 50 impressions / "
     "$2.02 (Cycle 4); dark 3.52% / 142 / $8.50 (Cycle 6).", "high"),
    ("AN8", "'Every agent gives you a different number' — abstract question",
     "States the problem without a specific curiosity gap. Facebook delivered "
     "it heavily and nobody clicked: 2.4% CTR on 247 impressions — the "
     "highest-delivery, worst-engagement angle at the time. Killed Cycle 5.", "high"),
    ("AN9", "narrative-only — agent conditioning call (Levitt & Syverson 3.7%)",
     "Peak 14.29% CTR on dark, 4.9-8.7% settled, $31.11 spent, 0 leads. "
     "Narrative creates identification but not action — it needs a "
     "dollar-shock open loop.", "high"),
    ("AN10", "narrative-only — the 29-day stale listing",
     "11.1-11.6% CTR, $31.45, 0 leads, auto-paused. Second narrative-only kill.", "high"),
    ("AN11", "behaviour recognition — 'You searched your home's value at 11pm'",
     "Recognition without an action hook. Dark 0.00% / 44 impressions; light "
     "3.80% / 79 / $4.16. Killed Cycles 5-6. A later cycle flags the mechanic "
     "as possibly untested rather than dead — the phone-mockup execution may "
     "have been too literal.", "low"),
    ("AN12", "visual info-gap — split card 'What the Agent Sees / What You See: ?'",
     "0.00% CTR on 76 combined impressions. The most visually distinctive "
     "creative in the test produced zero engagement — people engage with "
     "stories, not diagrams. NOTE: the CONCEPT (information asymmetry) is "
     "Fields' core wedge and is NOT dead; the visual treatment is.", "medium"),
    ("AN13", "narrative-only — renovation-ROI table",
     "Peak 13.79% CTR on light, 8.98-10.19% settled, ~$31.24, 0 leads. Sixth "
     "narrative-only kill. The reno AXIS was later re-killed dollar-anchored "
     "as AN40.", "high"),
    ("AN14_light", "light variant of a CONVERTING angle (7-day window)",
     "Auto-paused at $16.76 with 0 leads — the DARK variant took the lead "
     "(11.32% vs light 1.92%). Background-specific; the ANGLE converts.", "low"),
    ("AN15_light", "light variant of a CONVERTING angle ($150K gap)",
     "Background-specific kill; the dark variant converted at $15.74-$25.58 "
     "CPL with Yes intent. The ANGLE converts.", "low"),
    ("AN16", "utility cost-table — 'The Cost of Selling' ($37K-$66K itemised)",
     "Costs are a service question people ask AFTER deciding to sell, not a "
     "scroll-stopper. 1.17% CTR, 171 impressions, $9.96 (dark 1.37%/73, light "
     "1.02%/98). Killed Cycle 8. Reconfirmed twice on the same composite-cost "
     "axis by AN22 and AN29.", "high"),
    ("AN17", "agent-trust + dollar shock — 'The 3.7% Rule' ($55,500)",
     "The agent-trust axis creates ANGER at agents, not curiosity about your "
     "own number — the form resolves nothing. Also the run's clearest early-CTR "
     "trap: dark fell 12.24% (49 impressions) to 7.79% (154). $24.79, 311 "
     "impressions, 0 leads. Killed Cycle 9.", "high"),
    ("AN18", "positive urgency — 'Week Three' (+4% premium = $60,000)",
     "0.00% CTR on 121 impressions, BOTH backgrounds, $5.00. Aspiration does "
     "not stop the scroll; fear does. Killed Cycle 8. NOTE the upside frame was "
     "deliberately re-opened later as AN43, which never delivered — see "
     "caution_upside_frame_untested.", "medium"),
    ("AN19", "suburb split / micro-geography — 'Same suburb, 400m apart, $312,000'",
     "Hyper-local specificity produces topic-level interest, not personal "
     "identification. Dark 178 impressions / 5.06% / $8.51 (Cycle 17); light "
     "237 / 5.49% / $9.66 (Cycle 19); 0 leads across 415 impressions.", "medium"),
    ("AN20", "abstract temporal — 'The Wrong Year' (2023 anchor, comps moved $180K-$310K)",
     "Three cognitive steps before scroll-stop: recognise you have a stale "
     "number, connect it to 2023, feel the gap. 0.9% CTR on 106 combined "
     "impressions (dark 0.00%/47, light 1.7%/59). Killed Cycle 12.", "medium"),
    ("AN21", "price-cut number — ~$47,000 average first reduction in week 4",
     "Double-shock: two competing facts, no personal question. Dark 70 "
     "impressions / 1.43% (Cycle 13); light 170 / 6.47% / $13.37 / 0 leads "
     "(Cycle 19). Also the sharpest background-rule case at a 7.4x gap.", "low"),
    ("AN22", "net proceeds — '$1.5M sale, $1,337,000-$1,413,000 in the bank'",
     "Financial INFORMATION rather than a gap between belief and reality — "
     "'huh, interesting', not 'what about MY home?'. Dark 74 impressions / "
     "0.00% (Cycle 14); light briefly recovered 1.43% to 3.74%, came off "
     "probation, then died at 178 / 2.81% / $9.30 / 0 leads (Cycle 17).", "medium"),
    ("AN23", "framework complexity — 'The Three Numbers' (owner vs agent vs comps)",
     "Triple frameworks create comprehension, not identification; converters "
     "carry one concept and one number. Dark 72 impressions / 0.00% (Cycle 14); "
     "light 167 / 2.99% / $8.14 / 0 leads (Cycle 18).", "medium"),
    ("AN24", "89% repackage — 'The Estimate Test' (AN1's stat as a research narrative)",
     "Third confirmation that aggregate statistics do not personalise. Dark 102 "
     "impressions / 3.92%; light 99 / 3.03%; 0 leads. Killed Cycle 16. With AN1 "
     "and AN4 this is 6 variants over ~900 impressions and zero leads.", "high"),
    ("AN25", "equity abstract — known mortgage balance vs unknown market-value drift",
     "Requires holding two abstract numbers and computing a difference. Dark 77 "
     "impressions / 0.00% (Cycle 15); light 190 / 3.68% / $9.16 / 0 leads "
     "(Cycle 18). Sixth abstract-concept kill.", "medium"),
    ("AN26", "speed signal — '14 days vs 90+ days, the gap is in the pricing data'",
     "The single strongest proof that CTR does not predict conversion: 3rd "
     "highest CTR in the entire portfolio, zero leads. Dark 144 impressions / "
     "5.56% / $10.20; light 145 / 7.59% / $12.11; 289 combined, 0 leads. "
     "Killed Cycle 20.", "medium"),
    ("AN27", "landlord segment — 'Tenant Discount' ($72K-$108K tenanted vs vacant)",
     "The first and only angle not targeting owner-occupiers. Dark 133 "
     "impressions / 2.26% / $7.51; light 198 / 3.54% / $5.33; 331 combined, "
     "3.1% CTR (below portfolio average), 0 leads. Killed Cycle 20. This is a "
     "result about a NICHE SEGMENT INSIDE BROAD TARGETING, not proof the "
     "landlord segment is unreachable with segment-targeted delivery.", "medium"),
    ("AN28", "identity threat — 'The Split' (top vs bottom quarter sellers)",
     "Archetype B's exemplar: it converts, into junk. 432 combined impressions, "
     "~$28, 1 lead with NO selling intent (dark 197/3.55%/1 lead; light "
     "235/3.83%/0). Killed Cycle 26, both for its verdict and to relieve "
     "auction starvation.", "low"),
    ("AN29", "composite cost — 'The Waiting Tax' ($64,600 = -$25K sale, -$39.6K rent)",
     "Composite dollar figures require processing multiple costs = cognitive "
     "load = scroll-past. Dark 108 impressions / 4.63%; light 182 / 2.75%; 290 "
     "combined, $14.22, 0 leads. Killed Cycle 21. Same failure as AN16 and "
     "AN22.", "medium"),
    ("AN30", "presentation gap — 'The $80K Photo' (two identical homes, 3 doors apart)",
     "317 combined impressions, ~4.6% CTR, $14.89, 0 leads. Ninth high-CTR "
     "non-converter. Home presentation is a topic, not a personal knowledge "
     "gap. Killed Cycle 22.", "medium"),
    ("AN31", "conditional pre-commitment — 'The Tomorrow Test' (hybrid #1)",
     "Conditional/hypothetical verb framing kills scroll-stop. Identity threat "
     "works as IMMEDIATE classification, not as a hypothetical. Light 0.00% CTR "
     "on 93 impressions; dark 2.99% on 67; 160 combined, $7.62, 0 leads. "
     "Killed Cycle 21.", "medium"),
    ("AN32", "agent choice in the abstract — 'Agency Gap' ($167,000 best vs worst)",
     "Targeted the #1 Halo seller fear (32,368 keyword mentions across 2,351 "
     "conversations) and was deliberately built to differ from AN17 (risk "
     "assessment, not anger). Still failed: ~1.5% CTR on 450 impressions, 0 "
     "leads. Killed Cycle 24. The agent axis is now 0 for 3 (AN9, AN17, AN32).", "medium"),
    ("AN35_dark", "dark variant of the hybrid 'Two Categories'",
     "Light beat dark in three consecutive reads against the run-wide dark rule "
     "(5.9% vs 2.7%, then 4.69% vs 2.02%, then 1.5%/137 vs 0.0%/104). Dark "
     "culled Cycle 28 as the provably wrong variant. AN35_LIGHT SURVIVED and is "
     "UNRESOLVED, not dead.", "medium"),
    ("AN36", "time decay / cost of waiting — 'The 21-Day Cost' (7% = $70,000 on $1M)",
     "Dark 0.00% CTR on 121 impressions, culled Cycle 29. The axis was marked "
     "dead across AN36 + AN29 + AN18. TENSION WORTH NOTING: AN14, a CONVERTING "
     "angle, is also a time-urgency angle — 'time decay is dead' and 'AN14 "
     "converts' coexist uneasily in the sources.", "low"),
    ("AN37", "no-dollar process fear — 'The Settlement Gap' (owning two homes at once)",
     "Built deliberately WITHOUT a dollar figure to test whether the winning "
     "mechanic generalises. ~1.3% CTR on 312 combined impressions, dark 0.62%, "
     "0 leads. Killed Cycle 24. The run's single most informative kill — it "
     "established that the mechanic is dollar-anchored. Killed the CONTENT, "
     "proved the MECHANIC.", "medium"),
    ("AN39", "multi-figure puzzle — 'The Valuation Spread' ($1.2M/$1.35M/$1.48M -> $280,000)",
     "0 link clicks on 114 combined impressions, 0.00% CTR both backgrounds, "
     "AFTER starvation relief guaranteed a fair auction for a full hour. A "
     "multi-figure puzzle about agents in general, not one number about a home "
     "like yours. Killed Cycle 27.", "medium"),
    ("AN40", "renovation return — 'Kitchen Math' ($80,000 kitchen returns ~$34,000)",
     "An AXIS-level verdict. Renovation return was tested twice: narrative-only "
     "(AN13, 9-10% CTR, zero conversion) and dollar-anchored (AN40, dark "
     "0.0%/69 impressions, light 1.4%/71). Reno value does not stop scroll for "
     "seller intent even with the winning DNA. Killed Cycle 28.", "medium"),
]

DEAD_ANGLES = [
    _rec(
        _id=f"dead_angle_{code}",
        kind="dead_angle",
        angle_code=code,
        title=f"{code} — {desc}",
        finding=f"DO NOT RE-TEST. {code} ({desc}) was tested and killed.",
        evidence=why,
        source_file=LEDGER,
        source_detail=(
            f"{LEDGER} 'Killed/Paused' roster, plus the cycle doc that killed "
            f"it in {CYCLES}"
        ),
        date_established="2026-07-30",
        confidence=conf,
        confidence_reason={
            "high": (
                "Multiple confirmations or a well-powered CTR null (250+ "
                "impressions). Still a CTR verdict — the $15 kill threshold "
                "means no angle here accumulated enough spend for a conversion "
                "verdict."
            ),
            "medium": (
                "A single clean CTR read on 70-450 impressions with zero lead "
                "events. Honest about scroll-stop; not evidence about "
                "conversion."
            ),
            "low": (
                "Killed on a small denominator, or a VARIANT-level rather than "
                "ANGLE-level verdict, or with a documented counter-signal. "
                "Treat as a weak prior, not a closed result."
            ),
        }[conf],
    )
    for code, desc, why, conf in _DEAD
]


ALL_RECORDS = ARCHETYPES + LAWS + CAUTIONS + DEAD_ANGLES


def build(dry_run=False):
    db = get_client()["system_monitor"]
    if not dry_run:
        db[COLLECTION].delete_many({})
        db[COLLECTION].insert_many(ALL_RECORDS)
    return ALL_RECORDS


def show(kind=None, db=None):
    db = db or get_client()["system_monitor"]
    q = {"kind": kind} if kind else {}
    docs = list(db[COLLECTION].find(q))
    if not docs:
        print("content_learnings is empty — run build_content_learnings.py first.")
        return

    order = {"caution": 0, "archetype": 1, "law": 2, "dead_angle": 3}
    # the sample-size caution must be the first thing anyone reads
    first = "caution_reward_sparsity_verdicts_are_coinflips"
    docs.sort(key=lambda d: (order.get(d["kind"], 9), d["_id"] != first, d["_id"]))

    print("=" * 78)
    print("CONTENT LEARNINGS — read this before writing copy or picking an angle")
    print("=" * 78)
    print(RUN_CONTEXT)
    print()
    print("CONFIDENCE IS PART OF EVERY FINDING. 'low' means single-digit leads.")
    print()

    last = None
    for d in docs:
        if d["kind"] != last:
            last = d["kind"]
            print()
            print("#" * 78)
            print(f"# {last.upper().replace('_', ' ')}S")
            print("#" * 78)
        print()
        print(f"[{d['_id']}]  confidence={d['confidence']}")
        print(f"  {d['title']}")
        print(f"  FINDING : {d['finding']}")
        if d.get("evidence"):
            print(f"  EVIDENCE: {d['evidence']}")
        if d.get("actionable"):
            print(f"  USE     : {d['actionable']}")
        if d.get("contradicts"):
            print(f"  CONFLICT: contradicts {', '.join(d['contradicts'])}")
        print(f"  WHY {d['confidence'].upper()}: {d['confidence_reason']}")
        print(f"  SOURCE  : {d['source_file']} — {d.get('source_detail','')} "
              f"({d['date_established']})")

    print()
    print("=" * 78)
    counts = {}
    for d in docs:
        counts[d["kind"]] = counts.get(d["kind"], 0) + 1
    print("  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    conf = {}
    for d in docs:
        conf[d["confidence"]] = conf.get(d["confidence"], 0) + 1
    print("confidence: " + "  ".join(f"{k}={v}" for k, v in sorted(conf.items())))
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--kind", choices=["archetype", "dead_angle", "law", "caution"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.show:
        show(args.kind)
        return

    recs = build(args.dry_run)
    counts = {}
    for r in recs:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    print(f"{'built (dry run)' if args.dry_run else 'wrote'} "
          f"system_monitor.{COLLECTION}: {len(recs)} documents")
    for k, v in sorted(counts.items()):
        print(f"  {k:<12} {v}")
    conf = {}
    for r in recs:
        conf[r["confidence"]] = conf.get(r["confidence"], 0) + 1
    print("  confidence: " + "  ".join(f"{k}={v}" for k, v in sorted(conf.items())))


if __name__ == "__main__":
    main()
