# Content Learnings Corpus

**Built:** 2026-08-13 · **Scripts:** `scripts/build_hook_corpus.py`, `scripts/build_content_learnings.py`

Fields' content knowledge used to live in two places a generator could not read:
Markdown prose (a 557-line ledger, 29 cycle docs, a 910-line test summary) and two
MongoDB collections that had **never been joined**. This is that knowledge, made
machine-readable.

---

## What exists

| Collection | Docs | What it is |
|---|---|---|
| `system_monitor.content_hook_corpus` | 92 | One doc per ad-headline: the text, its hook classification, its **measured** outcome, and the campaign objective it ran under. |
| `system_monitor.content_hook_aggregates` | 60 | Impression-weighted rollups per `hook_type` / `primary_emotional_lever` / `message_theme`, plus objective-controlled versions. |
| `system_monitor.content_learnings` | 80 | Structured funnel verdicts: 3 archetypes, 26 laws, 15 cautions, 36 dead angles. |

### `content_hook_corpus` — the join nobody had done

`ad_profiles` (203 ads, lifetime delivery metrics) × `ad_semantic_annotations`
(92 ads classified by hook type, emotional lever, tone, message theme,
reading complexity, word counts). They join on `ad_id`. **92 of 92 matched** —
every annotation has a profile.

Each row carries the text (`display_text`, `headline_text`, `hook_text`,
`body_text`), the classification, the outcome (`impressions`, `clicks`,
`ctr_pct`, `link_clicks`, `spend_aud`, `cpc_aud`, `cpm_aud`), the conversion
fields where attributable (`leads`, `cost_per_lead_aud`, `downstream_sessions`,
`downstream_converters`), and the confounders (`campaign_objective`,
`campaign_name`, `uses_custom_audience`, `format`).

### `content_learnings` — the prose, structured

Each doc: stable `_id`, `kind` (`archetype` | `dead_angle` | `law` | `caution`),
`title`, `finding`, `evidence` (numbers + spend + n), `numbers` (machine-readable),
`source_file`, `source_detail`, `date_established`, `confidence`,
`confidence_reason`, `actionable`, and `contradicts` where a finding conflicts
with another source.

---

## How to query it

```bash
set -a && source .env && set +a && source /home/fields/venv/bin/activate

# Rebuild (idempotent — both scripts replace their collections)
python3 scripts/build_hook_corpus.py
python3 scripts/build_content_learnings.py

# Agent-readable dumps — read these at cycle start
python3 scripts/build_hook_corpus.py --show
python3 scripts/build_content_learnings.py --show
python3 scripts/build_content_learnings.py --show --kind dead_angle
```

```python
import sys; sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client
db = get_client()["system_monitor"]

# Never re-test these
dead = {d["angle_code"] for d in db.content_learnings.find({"kind": "dead_angle"})}

# Only rank hook types on rows that clear the evidence gate
for a in db.content_hook_aggregates.find(
        {"dimension": "hook_type", "insufficient_evidence": False,
         "controlled_for_objective": {"$ne": True}}).sort("total_impressions", -1):
    print(a["value"], a["n_ads"], a["total_impressions"], a["weighted_ctr_pct"])

# The only fair hook comparison — held inside one objective
db.content_hook_aggregates.find({"controlled_for_objective": True,
                                 "campaign_objective": "OUTCOME_TRAFFIC"})
```

---

## Limitations — read before quoting any number

**1. The hook corpus measures CLICKS, not leads.** All 92 annotated ads sit in
`OUTCOME_ENGAGEMENT` (57), `OUTCOME_TRAFFIC` (33) or `OUTCOME_AWARENESS` (2).
**Not one is `OUTCOME_LEADS`**, and zero attributable leads join to any of them.
The account's 108 lead-optimised ads — including all 43 homeowner-funnel angles —
are entirely unannotated. Since `law_personal_open_loop` establishes that high CTR
does not predict conversion in this account, the hook taxonomy is currently
evidence about scroll-stop only. *Annotating the 108 `OUTCOME_LEADS` ads is the
single highest-value unblock here.*

**2. CTR is not comparable across campaign objectives.** `OUTCOME_ENGAGEMENT`
delivery buys cheap in-feed interactions and inflates raw CTR several-fold.
`drafts/marketing-test-summary.md` documents an earlier
"property stories beat market commentary" conclusion that was produced exactly
this way and later retracted. Every row records its objective; every aggregate
carries an `objective_mix`. **Use the `controlled_for_objective: true` aggregates
for any comparison.**

**3. Evidence gate: 500 impressions / 3 ads.** Groups below either are stamped
`insufficient_evidence: true` and `rankable: false`. Only **55 of 92** rows clear
the impression floor. All aggregates are impression-weighted (sum clicks ÷ sum
impressions), never a mean of per-ad CTRs — a 100% CTR on 3 impressions must not
move a group mean. `story_narrative` shows the highest weighted CTR of any hook
type (16.19%) and is gated out at n=2. Do not quote it as a winner.

**4. The funnel verdicts rest on SEVEN lead events.** ~$832 (or $868 by the
mandate doc's tally) produced 7 leads: 4 "quality Yes", **one of which carried a
fake +93 phone number** — so three verifiable. The corpus says of itself:
*"Every cycle 'verdict' to date is a coin-flip dressed as a finding."*
Every archetype and conversion claim inherits that.

**5. Dead angles are CTR verdicts wearing conversion language.** The auto-pause
threshold was $15 spend with 0 leads, so most kills rest on 70–450 impressions
and **zero lead events**. They are honest reads about scroll-stop. They are not
evidence about conversion. `confidence` on each record says which.

**6. All copy testing ran OUT OF MARKET** (Brisbane + Sunshine Coast, Gold Coast
excluded, to protect the ~1M GC core audience). Per the mandate doc: funnel
*shape*, PII-resistance *ranking* and hook *mechanics* transfer; **absolute CPL
and conversion rate do not**. Never quote a funnel-run CPL as a Gold Coast
forecast.

**7. CPLs in the sources are moving snapshots.** Spend accrues hourly, leads do
not, so a quoted CPL rises after an angle's last lead. AN14 is quoted at $6.42,
$8.50, $16.78, $18.87, $21.23, $22.29, $24.13 and $26.02 across cycles — all for
the same single lead. Two docs quoting the same angle at different hours will
disagree and neither is wrong.

**8. Three findings CONTRADICT other sources.** They are stored as `caution`,
with a `contradicts` field, not silently resolved:

- **"Broad targeting beats custom audiences"** — appears in `CLAUDE.md` and the
  funnel ledger as established. `marketing-test-summary.md` Part 5 Error 3
  explicitly retracts it as a confounded comparison. Open question, not a law.
- **"Phone field doesn't hurt lead volume"** — the ledger says no volume drop;
  `NEXT_CYCLE_AD_PLAN_2026-07-30.md` §3 says it cost $30/lead vs ~$15, 0 hot.
  **Both cite the same Buyer Brief v3 form.** Unresolved.
- **"OFFSITE_CONVERSIONS is the #1 lever"** — stated as settled in `CLAUDE.md`;
  the source rates it Medium-High and confounded, with the isolating experiment
  having produced **one** website view.

**9. Two background rules oppose each other and were never reconciled.**
`law_background_by_format` (light wins CTR on data formats, 7 confirmations) vs
`law_bg_ctr_vs_bg_conversion` (dark produced ~3× the lead rate). Both are stored,
with the tension flagged.

**10. `content_learnings` is hand-curated from the sources, not parsed.** The
source Markdown is read-only and was not modified. Re-running the script rewrites
the collection from the literals in the script — if the sources change, the
script must be edited.

---

## Snapshot of what the join actually found (2026-08-13)

92 rows · 305,208 impressions · $2,624.27 spend · **0 attributed leads**.
55 rows clear the 500-impression floor.

Hook types that clear the evidence gate, impression-weighted:

| hook_type | n | impressions | wCTR | objective mix |
|---|---|---|---|---|
| statistic_number | 35 | 137,904 | 4.72% | ENG 18 / TRA 12 |
| question | 25 | 67,114 | 3.13% | ENG 16 / TRA 6 |
| contrarian_claim | 12 | 59,012 | 0.79% | ENG 2 / TRA 7 |
| curiosity_gap | 8 | 10,497 | 4.57% | ENG 3 / TRA 1 |
| problem_statement | 5 | 1,984 | 1.41% | ENG 1 / TRA 3 |

Held **within** `OUTCOME_TRAFFIC` (the only fair comparison): statistic_number
4.78% (n=12, 110,195 impr) · question 2.81% (n=7, 40,624) · problem_statement
1.42% (n=3, 1,975) · contrarian_claim 0.79% (n=7, 59,000). The contrarian_claim
figure is dominated by one 44,198-impression ad at 0.31% — check
`impressions_by_objective` before reading it as a hook-type effect.
