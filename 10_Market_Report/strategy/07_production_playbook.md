# Production Playbook — How a Quarterly Ships

**Document:** 07 of 7 (Strategy series)
**Purpose:** The operational manual for producing one issue of *The Fields Quarterly*. Tooling, schedule, roles, checklists, and what to do when things go wrong.

---

## 1. Tooling stack

### Recommended primary stack: Quarto + Typst

| Layer | Tool | Reason |
|---|---|---|
| Source format | Quarto `.qmd` (markdown + executable code) | Version-controlled in git; charts regenerate with new data |
| Chart engine | `plotnine` (or `matplotlib`) with custom Fields theme | Direct from Cosmos DB; reproducible |
| Typesetting | Typst (via Quarto 1.4+) | Near-InDesign typography at minutes-to-render speed |
| Web edition | Quarto HTML output + light React enhancements | Same source produces print and web |
| PDF output | Typst → PDF/X-1a | Print-grade, embedded fonts |
| Audio | Recorded by Will, edited in Descript or Audacity | Manual workflow |
| Version control | Git (existing `Fields_Orchestrator` repo) | Track every change, every issue |

### Fallback stack (if Quarto+Typst learning curve is blocking)

Use the existing **Jinja2 + headless Chrome → PDF** pipeline already built for per-property reports (`scripts/generate_appraisal_report.py`). Extend to multi-page. Less typographically refined; ships faster.

### Asset management

- **Photography**: stored at `Will954633/fields-local-photography` repo. Pull current quarter's shots into the report repo per issue.
- **Charts**: regenerated from data per issue. Cached PNGs committed with the issue's git tag.
- **Fonts**: Tiempos family + Söhne licensed via Klim direct purchase. Stored locally; not committed to git.
- **PDF outputs**: stored in `10_Market_Report/issues/q[X]-[Y]/` with a `manifest.json` listing every chart's data closure date.

## 2. Repository layout (proposed)

```
10_Market_Report/
├── README.md
├── strategy/
│   ├── 01_strategic_positioning.md
│   ├── 02_psychology_playbook.md
│   ├── 03_content_blueprint.md
│   ├── 04_visual_format_spec.md
│   ├── 05_conversion_architecture.md
│   ├── 06_macro_micro_framework.md
│   └── 07_production_playbook.md
├── research/
│   ├── internal_data_inventory.md
│   ├── best_in_class_reports.md
│   ├── homeowner_psychology.md
│   ├── visual_and_format_design.md
│   └── market_analysis_frameworks.md
├── working_notes/
│   └── 00_research_log.md
├── draft/
│   └── q2_2026_sample_text.md
├── assets/
│   └── (photography, fonts, brand assets)
├── pipeline/
│   ├── generate_market_report.py     ← entrypoint
│   ├── chart_theme.py                ← Fields visual style
│   ├── fci_calculator.py             ← Fields Conviction Index
│   ├── conviction_map_generator.py   ← signature visual
│   └── templates/
│       ├── _quarto.yml
│       ├── 00_cover.qmd
│       ├── 02_editor_letter.qmd
│       ├── 03_fci.qmd
│       ├── ...
│       └── 16_appendix.qmd
└── issues/
    ├── q2_2026/
    │   ├── manifest.json
    │   ├── pdf/
    │   ├── web/
    │   ├── audio/
    │   └── social_cuts/
    └── q3_2026/
        └── ...
```

## 3. Issue cycle — 8 weeks per issue

A single issue runs an 8-week cycle. Issues overlap: while Issue N is in distribution weeks 1-8, Issue N+1 is being researched in weeks 5-8.

### Week -8 to -5 (research and data gathering)

- Pull current quarter's data via `scripts/market_update_data.py` for each suburb.
- Refresh ABS, RBA, Cotality, SQM macro indicators.
- Identify the issue's tension (the one editorial through-line). This is the most important decision of the cycle.
- Run a Fields CEO Agent (Engineering / Growth / Product) post-mortem of the previous issue: what worked, what didn't.
- Source any new external data needed (e.g. flood overlay shapefile for Issue 1, school catchment for Issue 4).

### Week -4 to -2 (drafting)

- Draft the editorial sections: editor's letter, the tension chapter, suburb sections, closing.
- Generate all charts via the pipeline against locked data.
- Internal QA: editorial rules check (forbidden words, advice language, prediction language, single-figure-headline check, value framing).
- Photography pull: select images for section openers.
- First red-pen pass by Will.

### Week -1 (finalisation)

- Final QA: chart sources, sample sizes, citation density, accessibility tags.
- Audio recording (Will, single-take or two-take cuts).
- Audio edit (Descript / Audacity).
- Print press order placed (allow 5-7 working days for delivery).
- Web edition QA (Lighthouse mobile ≥ 90, PostHog events firing, gate position correct, attribution working).
- PDF QA (PDF/X-1a, file size ≤ 8MB web, embedded fonts, alt text on charts).
- CSV publishing (free download, no email gate).
- All UTM parameters set.

### Week 0 (ship)

- Email blast to existing list (with PDF attached + web link).
- Press copies posted (top 5 local journalists, 3 national property press contacts, top 5 brokers).
- Social rollout begins (week 0 = cover stat ad bucket).
- Audio published to podcast feed + report page.

### Weeks 1-7 (distribution + nurture)

Per the schedule in `05_conversion_architecture.md` Section 9.

### Week 8 (close-out + start next)

- Issue retrospective: actuals vs targets across all conversion benchmarks.
- Conviction tracker entries logged for the next issue's "What we said" page.
- Issue archived to `issues/q[X]-[Y]/` with manifest.

## 4. Roles and responsibilities

Currently a one-operator business. As the team scales (planned post-Q3 2026 if revenue lands), responsibilities split.

### Issue 1-2 (Will alone)
- All research, drafting, charts, audio, distribution.
- One external red-pen review (a friend with editorial chops, not paid).
- One paid designer engaged for cover + section openers if budget allows.

### From Issue 3-4 (assuming traction)
- **Will:** editorial direction, voice, the tension, the suburb sections, the editor's letters, audio narration, soft CTAs.
- **Data analyst (contracted or part-time):** data refresh, FCI calculation, chart generation, methodology validation.
- **Designer (contracted, quarterly retainer):** cover + section openers + chart polish + print proof.
- **Audio editor (contracted):** podcast cleanup + transcript.

### From Year 2
- **Editorial coordinator:** schedule, distribution, social cuts, nurture sequence.
- **Researcher:** macro updates, deep-dive sections, methodology improvements.

## 5. Per-issue checklist (consolidated)

Use this checklist for every issue.

### Editorial
- [ ] Tension identified and documented in editor's letter
- [ ] Three reader archetypes layered (curious owner / active seller / active buyer / informed observer)
- [ ] Each section has a sentence-case conclusion title
- [ ] Each section opens with a named-but-anonymised case (narrative transportation)
- [ ] At least one contrarian-but-evidenced finding included
- [ ] At least one "What surprised us" callout
- [ ] "What we don't know" page populated with 3-5 honest items
- [ ] Methodology page reflects all data used
- [ ] Editor's letter signed by Will
- [ ] Closing letter signed and dated

### Compliance (editorial rules)
- [ ] No forbidden words (search-and-find: stunning, nestled, boasting, rare opportunity, robust market, unprecedented, hot market, must-see, gem, premium, exclusive)
- [ ] No advice language (you should, consider, now is a good time, recommend, act now)
- [ ] No predictive language (will, going to, set to, expected to, predicted to)
- [ ] All numbers in `$1,250,000` format
- [ ] All suburbs capitalised
- [ ] Hedging hierarchy used appropriately (strong/medium/weak)
- [ ] No single valuation in any headline (ranges only)
- [ ] Value-framing applied to every property feature

### Data
- [ ] Every chart has source + sample size + date in caption
- [ ] All public-facing stats trace back to `precomputed_market_charts` or `precomputed_indexed_prices` (not raw DB queries)
- [ ] FCI on cover matches FCI on inside spread
- [ ] Sample sizes <30 flagged in caption
- [ ] Cotality / Domain / PropTrack / SQM data attributed where used
- [ ] ABS / RBA / APRA citations include catalogue number / publication date
- [ ] Conviction tracker entries reconciled (Issue 2+)
- [ ] Real Pain & Gain holding-cost assumptions stated

### Visual
- [ ] All chart titles state conclusion (sentence case)
- [ ] Direct labelling used; legends only when essential
- [ ] No 3D, gradients, decorative elements
- [ ] Single-hue ramps for choropleths
- [ ] Tabular numerals in charts and tables
- [ ] Sparklines in tables where the table has a row per suburb / per period
- [ ] Photography is observational, not promotional
- [ ] Captions on every photograph (location + date + observation)
- [ ] No stock imagery anywhere
- [ ] Cover paper specification correct (300-350gsm uncoated)

### Production
- [ ] PDF/X-1a:2001 export for print
- [ ] Standard PDF for web download (≤ 8MB)
- [ ] Web edition Lighthouse ≥ 90 mobile
- [ ] PostHog events firing on every section reach
- [ ] UTM parameters on every outbound link
- [ ] All fonts embedded
- [ ] Bleed correct (3mm) for print edition
- [ ] CSV download published (free, no gate)
- [ ] Permanent canonical URL active
- [ ] Audio edition has accurate transcript
- [ ] Print proofs reviewed under daylight + tungsten before press
- [ ] Australia Post Express Parcel labels generated for high-value list

### Distribution
- [ ] Email blast queued
- [ ] Facebook ad buckets set up (cover stat, conviction map, real pain & gain)
- [ ] LinkedIn post draft prepared
- [ ] Per-chart social cuts generated
- [ ] Press copies addressed
- [ ] Print copies for CRM top 200 prepared
- [ ] Audio published to podcast feed
- [ ] Conviction tracker email teaser scheduled (Issue 2+)

## 6. Data refresh cadence

**Source-of-truth ingestion is automatic** via the existing orchestrator pipeline (nightly at 20:30 AEST). For the Quarterly:

| Source | Cadence | Manual step |
|---|---|---|
| `precomputed_indexed_prices` | Daily (orchestrator) | None |
| `precomputed_market_charts` | Daily (orchestrator) | None |
| `precomputed_macro_indicators` | Monthly (cron) | Verify against RBA SMP / APRA / ABS releases |
| Cotality HVI | Manual quarterly pull from latest Cotality publication | Yes — paste figures + citation |
| Domain / PropTrack / SQM cross-references | Manual quarterly | Yes — for the four-source reconciliation |
| Council overlay (GCCC) | Annual / when updated | Yes — pull shapefile or extract |
| ICA Insurance Probability Zones | Annual | Yes — pull current published map |
| ABS Census | 5-yearly (next 2026/27) | Yes — refresh demographic charts post-release |

The pipeline is built so that 80% of the data is ready by the end of the quarter; the remaining 20% (cross-reference data, ABS, narrative) is human work in weeks -8 to -2.

## 7. Risk register and mitigation

| Risk | Mitigation |
|---|---|
| **Data error in published issue** | Two independent QA passes (Will + external red pen). Public correction policy. Public correction log in appendix from Issue 2 onwards. |
| **One-shot misforecast destroys credibility** | All forward-looking statements use conditional language. Conviction tracker (Issue 2+) ensures we grade ourselves. The editorial rule against forecasts protects us. |
| **Sample sizes too small for a suburb** | Sample size flagged in every chart. Suburbs with <30 transactions in a quarter get qualifying language. The "What we don't know" page lists sample-size limitations. |
| **Volunteered-into-the-record liability (advice)** | The "no advice" rule is enforced in the editorial pass. Disclaimers in the appendix and the privacy line in every email. |
| **Print press delay** | Order placed 7 days early. PDF distribution doesn't depend on print. Print is a quality multiplier, not a critical path. |
| **Audio delay** | Audio is a multiplier, not critical path. If late, ship without and back-fill within 7 days. |
| **Web gate technical fail** | Test PostHog event firing + email delivery in staging before press. Have a manual fallback (mailto: link) ready. |
| **Email deliverability drop** | Send via established sender (Resend / Postmark). Warm the list with the monthly Pulse. Don't add aggressive marketing copy. |
| **Designer dropout (when contracted)** | Maintain a Quarto template that can ship without a designer. The designer adds polish; the template ensures the issue ships. |
| **Will burnout** | Issue 1-2 are the test. If Issue 3 is feeling rushed, drop the audio or print run for that issue and protect editorial quality. The Quarterly is the brand; everything else is multiplier. |

## 8. Failure modes — when to abort an issue

An issue should not ship if:

1. The editorial through-line (the tension) cannot be defended by the data. Better to delay a week than publish a thesis that breaks under scrutiny.
2. The conviction tracker for the previous quarter shows >50% of signals were wrong. Pause and write a "we got this wrong" mid-quarter explainer instead of pretending nothing happened.
3. The data closes <14 days before publication and the indexed-price calculation has unresolved sample-size issues. Better to push the issue date back and disclose than to publish soft data.
4. The methodology page cannot be written. If the chapter can't explain how every chart is made, something in the pipeline isn't reproducible.
5. Will's voice isn't in the editorial letters. The brand depends on the named author. If Will hasn't read and personally signed off, don't ship.

## 9. Distribution mechanics — operational

### Email infrastructure
- Sender: `will@fieldsestate.com.au` (high deliverability — never automated alias).
- Reply-to: same. Replies are read.
- Sending platform: Resend or Postmark (transactional + nurture).
- List management: tagged by issue + subscription preference (quarterly only / pulse / weekly).
- Unsubscribe: one-click, no friction. Single line at footer.

### Print infrastructure
- Printer: a Gold Coast or Brisbane trade printer (saves freight, supports local). Pagination, Currie Group, or local shop.
- Quotes solicited from three printers per issue until a long-term relationship is established.
- Mailing: Australia Post Express Parcel labels generated from CRM. The box is part of the experience — branded boxes if budget allows.

### Social infrastructure
- Per-chart cuts auto-generated as 1080×1080 (Instagram), 1080×1920 (Stories/Reels), 1200×627 (LinkedIn).
- Each cut has consistent branding (Fields wordmark, page reference, source line).
- All cuts link to web edition with `?utm_source=fb&utm_medium=chart&utm_campaign=q[X]_[Y]` and per-chart `utm_content`.

### Audio infrastructure
- Hosted on Fields' own podcast feed (cheap; no platform lock-in).
- Pushed to Spotify, Apple Podcasts, Google Podcasts via a podcast host (Buzzsprout / Transistor / Libsyn).
- Embedded on the web edition page.

## 10. The first issue (Q2 2026) — go / no-go criteria

Before greenlighting Issue 1 (Q2 2026, planned distribution August 2026):

| Criterion | Status (as of 2026-05-06) | Action if not met |
|---|---|---|
| Data pipeline produces FCI for all 3 suburbs | Pending (FCI calculator not yet built) | Build via `pipeline/fci_calculator.py` |
| Conviction Map dataset (≥30 suburbs) ready | Partial | Extend `precomputed_market_charts` coverage |
| Four-source price reconciliation possible | Partial | Verify Cotality / Domain / PropTrack / SQM data parity at suburb level |
| Real Pain & Gain holding-cost methodology defined | Not started | Write methodology + assumptions |
| Flood overlay vs ICA zone Venn diagram data | Likely possible | Verify both shapefiles available |
| Quarto + Typst template built | Not started | 2-3 weeks of build time |
| Designer engaged for cover | Not started | Brief by week -8 |
| Photography refreshed for the three suburbs | Likely partial | Will: shoot list + 2 days of fieldwork |
| Print printer quotes obtained | Not started | Solicit by week -2 |
| Email infrastructure (Resend / Postmark) live | Likely live | Verify |
| Audio recording setup | Likely live (Will already records) | Verify |

**Recommended go-decision date:** by end of Q2 2026 calendar month (30 June 2026). If by 30 June the FCI calculator and Quarto template are not built, push Issue 1 to October (Q3 distribution) and use July-August for build.

## 11. Continuous improvement — between issues

### What we keep doing if successful
- One-tension-per-issue discipline (Hamptons-style)
- The conviction tracker
- The "What we don't know" page
- The free CSV download
- The named author + photo + signature
- The signature visual (Conviction Map)
- The methodology chapter

### What we test and iterate
- Gate position (50% works in theory; A/B test 40% vs 60% over 2-3 issues)
- Email subject lines (test confrontational vs descriptive)
- Print copy thresholds (Issue 2: increase print run if Issue 1 generated >$5K of attributed inbound)
- Per-chart social cut formats (which charts get the most shares; double down)
- Audio length (start at 22 min; trim if completion <60%; lengthen if >85%)
- Issue ordering of sections (does the conviction tracker reach more readers if it's earlier?)

### What we write down to learn from
- After every issue, an issue retrospective document in `working_notes/issue_[X]_retro.md`.
- Quarterly review of conversion benchmarks vs target.
- Annual review of "what we got right and wrong" — informs the Issue 3 / Q4 conviction tracker.

## 12. The handover document (when scaling)

When Will hands any part of this off (designer / data analyst / editor):

The seven strategy documents in `strategy/` are the contract. Anyone joining the team reads them in order. Anyone deviating from them needs to write down why and get sign-off.

The five research documents in `research/` are the supporting evidence — read for understanding, not as constraints.

This playbook (`07_production_playbook.md`) is the operational manual. New team members read it once, then refer back to the checklists.
