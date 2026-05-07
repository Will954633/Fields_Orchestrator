# Fields Quarterly — Project Index

**Project:** The Fields Quarterly — flagship property market update report.
**Owner:** Will Simpson.
**Started:** 2026-05-06.
**Goal:** Set a new global standard for property reporting, compressed to one specific market — the southern Gold Coast. Drive Q3 2026 lead generation. Become the citation standard for southern Gold Coast property within 12 months.

This folder is a complete strategic and operational brief for the report. Read in the order below.

---

## Read in this order

### 1. Strategy (start here)

The seven documents in `strategy/` are the contract. Anyone joining the project reads them in this order.

| # | Document | Purpose |
|---|---|---|
| 01 | [`01_strategic_positioning.md`](strategy/01_strategic_positioning.md) | What this report is, who it is for, why it exists, and what it deliberately is not. The doctrine. |
| 02 | [`02_psychology_playbook.md`](strategy/02_psychology_playbook.md) | Operationalised reader psychology — every finding mapped to a page, chart, or design rule. |
| 03 | [`03_content_blueprint.md`](strategy/03_content_blueprint.md) | The proprietary index (Fields Conviction Index), signature visual (Conviction Map), section-by-section anatomy, length, cadence. |
| 04 | [`04_visual_format_spec.md`](strategy/04_visual_format_spec.md) | Type stack, palette, layout, chart vocabulary, photography rules, cover spec, file specs. The design system. |
| 05 | [`05_conversion_architecture.md`](strategy/05_conversion_architecture.md) | Funnel, soft gating, email nurture, print trigger, embedded CTAs, tracking, conversion benchmarks. |
| 06 | [`06_macro_micro_framework.md`](strategy/06_macro_micro_framework.md) | What we measure, what we deliberately do not measure, methodology, suburb-specific dimensions. |
| 07 | [`07_production_playbook.md`](strategy/07_production_playbook.md) | Tooling (Quarto + Typst), 8-week issue cycle, roles, checklists, risk register. |

### 2. Research (the supporting evidence)

The five documents in `research/` are the evidence base for the strategy. Read for understanding, not as constraints.

| Document | Words | Purpose |
|---|---|---|
| [`internal_data_inventory.md`](research/internal_data_inventory.md) | ~3,200 | Every internal data source mapped (Cosmos collections, knowledge base, Drive, scripts) |
| [`best_in_class_reports.md`](research/best_in_class_reports.md) | ~3,700 | 27 global property + finance reports audited for what they do well and where they fail |
| [`homeowner_psychology.md`](research/homeowner_psychology.md) | ~4,400 | Behavioural economics, trust architecture, named studies — Genesove & Mayer, Northcraft & Neale, Loewenstein, Cialdini |
| [`visual_and_format_design.md`](research/visual_and_format_design.md) | ~5,000 | FT Visual Vocabulary, type theory, format tiers, chart catalogue, conversion architecture for long-form |
| [`market_analysis_frameworks.md`](research/market_analysis_frameworks.md) | ~4,000 | RBA / APRA / ABS / Cotality / SQM frameworks; signal-vs-noise; current May 2026 cycle state |

### 3. Sample draft

[`draft/q1_2026_sample_text.md`](draft/q1_2026_sample_text.md) — a complete text-only walkthrough of Issue 01, **anchored on real Q1 2026 data** — the FCI, all suburb sub-indices, transaction counts, sale volumes, days-on-market medians, and rolling 12-month medians are actual values from the live calculator at `pipeline/fci_calculator.py`. Anonymised property examples and forward-looking commentary remain illustrative pending live capture; flagged with `[ILLUSTRATIVE]` where they appear.

### 4. Self-review

[`working_notes/01_self_review.md`](working_notes/01_self_review.md) — three passes (gaps & WOW, conversion + compliance audit, global-standard audit) with a consolidated 24-action list of must-fix-before-Issue-1 items.

### 5. Working notes

[`working_notes/00_research_log.md`](working_notes/00_research_log.md) — the foundation findings consolidated from prior memory and the research log of this strategy work.

---

## Top-line summary

**The Fields Quarterly is a 32-page, quarterly, named-author, methodology-first property analytical report covering three southern Gold Coast suburbs (Robina, Burleigh Waters, Varsity Lakes) at depth no national publisher can match.** It anchors on a proprietary composite index (Fields Conviction Index, FCI) and a signature suburb-scatter visual (Fields Conviction Map). Every issue is structured around one editorial tension. The free web edition soft-gates at the 50% scroll mark for email capture; the print edition is mailed to qualified leads; the 22-minute audio episode multiplies distribution; per-chart social cuts run for 12 weeks per issue. Conversion is engineered as a four-stage nurture: subscribe → live web layer → 4-email sequence → soft offer of a Position Report or Buyer Assist match.

The report differentiates from CoreLogic, Domain, Knight Frank, HTW, and every Gold Coast agency report on **suburb-level depth, methodology transparency, named authorial accountability, an explicit "what we don't know" page, real-after-cost returns (vs nominal-only Pain & Gain), four-source price reconciliation (Domain vs Cotality vs PropTrack vs SQM), and a quarterly conviction tracker that grades the previous issue against subsequent data**.

Editorially the report follows Fields' established rules: no advice (data only), no predictions (conditional language only), no single valuation in headlines (ranges only), value framing on every property feature, forbidden marketing words enforced, exact-numbered prices, capitalised suburbs, citation density at the level of academic publications.

Production runs on Quarto + Typst against the live Cosmos DB so each quarterly edition regenerates from updated data rather than being manually re-typeset. Issue 1 ships in **August 2026** (covering the Q2 cycle), with a recommended go/no-go decision by 30 June 2026 contingent on the FCI calculator being built and data parity for the four-source reconciliation being verified.

If executed as designed, the report becomes the citation standard for southern Gold Coast property within 12 months — and a serious contributor to Fields' Q3-Q4 2026 lead pipeline.

---

## The 24 must-fix-and-could-improve action items

From the self-review:

### Must-fix before Issue 1 ships
1. Build `pipeline/fci_calculator.py` — the highest-priority engineering task.
2. Verify suburb-level data parity for the four-source reconciliation chart. If parity isn't achievable, replace with a different signature original.
3. Validate Real Pain & Gain holding-cost assumptions against actual Gold Coast council rate schedules.
4. Photography shoot list — 30 frames, 2 days fieldwork.
5. Add "Where we differ from Cotality / Domain / PropTrack / SQM" sidebar to methodology page. *(Done in sample draft.)*
6. Substitute marketing-sense "premium" with non-forbidden language; clarify "premium" is technical-term-allowed when quantified. *(Done in sample draft.)*
7. Soften borderline-forecasting in the tension chapter to conditional language. *(Done in sample draft.)*
8. Add named-but-anonymised opening case to Robina and Varsity Lakes suburb sections. *(Done in sample draft.)*
9. Apply value framing to non-canal Burleigh Waters explicitly. *(Done in sample draft.)*
10. Add public consistency commitment to colophon and methodology. *(Done in sample draft.)*

### Should-add for Issue 1 if possible
11. Endow the Curious Owner archetype with a parallel conversion path beyond subscribe.
12. Develop a thumbnail-recognisable visual device (wordmark or chart-fingerprint).
13. Pre-publication PR pitch list (3 journalists, 2 brokers, 2 buyers' agents, 2 academics).
14. Add audio production sub-spec to `07_production_playbook.md`.
15. Add the "we never miss an issue" commitment to the public-facing colophon.

### Plan for Issue 2-4
16. Gold Coast Buyer Survey (Issue 2-3 administration; Issue 3 publication).
17. Annual long-form thought-leadership essay (Q4 2026 / Issue 4 companion).
18. Dispute / takedown mechanism documented.
19. Internationalisation footnote for the international migration audience.
20. Audio guest segment (one local figure per issue from Issue 2 onwards).

### Strategy doc gaps
21. Add `08_seo_distribution_plan.md` for organic discovery.
22. Add "Competitive intelligence reaction" recurring habit to `07_production_playbook.md`.
23. Add specific PostHog event thresholds to `05_conversion_architecture.md` Section 11.
24. Add third-party pre-publication review to `07_production_playbook.md` Section 7.

These items are the difference between a strong strategy and an excellent one. Most are <2 hours each; the FCI calculator is the only multi-day engineering task.

---

## Critical decisions that need Will

These cannot be made in the documents alone. They need Will's judgement.

1. **The first issue's editorial tension.** Recommended: "The Standoff" — sales-volume vs price tension. Alternative: "Living with Water" (the Burleigh flood-data section as the standalone WOW).
2. **Print run for Issue 1.** Recommended: 200 copies, distributed only to top 200 known prospects from CRM and high-LinkedIn-engagement Gold Coast contacts.
3. **Audio narration — Will or AI clone?** Recommended: Will's voice for Issue 1-3 minimum.
4. **Should the Conviction Map go on the website's home page after Issue 1?** Recommended: yes.
5. **Pricing for the per-property Position Report (the conversion offer).** Recommended: free until Q4 2026, then tiered (free for Quarterly subscribers, paid for non-subscribers).
6. **The first issue's working title.** Recommended: *The Fields Quarterly · Issue 01 · Q2 2026*.
7. **Tiempos / Söhne licensing budget.** Recommended: paid stack for Issues 1-2, then evaluate.
8. **Designer engagement.** Recommended: contract a senior editorial designer for the cover and section-opener typography for Issue 1.
9. **Issue 1 ship date.** Recommended: 15 August 2026 (covering Q2 data closed 30 June 2026).

---

## Files and folders

```
10_Market_Report/
├── README.md                            ← you are here
├── strategy/                            ← the contract (read first)
│   ├── 01_strategic_positioning.md
│   ├── 02_psychology_playbook.md
│   ├── 03_content_blueprint.md
│   ├── 04_visual_format_spec.md
│   ├── 05_conversion_architecture.md
│   ├── 06_macro_micro_framework.md
│   └── 07_production_playbook.md
├── research/                            ← the evidence
│   ├── internal_data_inventory.md
│   ├── best_in_class_reports.md
│   ├── homeowner_psychology.md
│   ├── visual_and_format_design.md
│   └── market_analysis_frameworks.md
├── working_notes/
│   ├── 00_research_log.md               ← foundation findings
│   └── 01_self_review.md                ← 3-pass review with action list
├── draft/
│   └── q1_2026_sample_text.md           ← complete sample of Issue 01
└── assets/                              ← (empty; for photography, fonts, brand)
```

---

## How this brief was produced

The work behind these documents:

- 5 parallel research streams launched (data inventory, best-in-class reports, homeowner psychology, visual/format design, macro-micro frameworks) — each produced 3,000-5,000 words of cited research.
- Foundation findings consolidated from the existing Fields memory system (60+ memory files spanning editorial rules, market data sources, prior tests, and strategic context).
- Strategy synthesised across 7 operational documents.
- Sample draft of Issue 01 produced, then reviewed across 3 passes for gaps, conversion psychology compliance, and global-standard ambition.
- Highest-priority review fixes applied to the strategy and the sample.

Total elapsed time: a single working session.

The documents are now ready for Will to read, mark up, and direct toward Issue 01 production.

---

## Single sentence

**The Fields Quarterly is the most rigorously sourced, most transparently caveated, most beautifully made record of what the southern Gold Coast property market actually did and why — written for the reader, not the agent.**

If, after Issue 1 ships, that sentence is still defensible, the report has done its job.
