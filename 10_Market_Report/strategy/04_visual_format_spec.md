# Visual & Format Spec — The Fields Quarterly

**Document:** 04 of 7 (Strategy series)
**Source:** `research/visual_and_format_design.md` (full reference brief)
**Purpose:** Operational design decisions Fields commits to. This is the spec a designer or developer can build against.

---

## 1. Design philosophy (one paragraph)

Data journalism that happens to be about property — not a property report that happens to contain charts. Closer to *The Economist*'s restraint and the *Financial Times'* visual discipline than to anything any agent has ever published. Authority is signalled by what is left out: no stock photography, no rounded headline figures, no agent's face on the cover. Restraint, exact figures, sourced charts, white space, and a single brand colour against off-white. Librarian, not luxury.

## 2. Format tiers (4 deliverables per issue)

| Tier | Format | Distribution | Cost per issue | Trust signal | Lead value |
|---|---|---|---|---|---|
| 1 | **Web edition** (scrollytelling at `fieldsestate.com.au/quarterly/q[X]-[Y]`) | Free, ungated until ~50%, soft email gate at gate point | Time only — existing React/Vite stack | Medium | Email capture |
| 2 | **PDF edition** (32-page A4, print-grade) | Email-gated download | 1 designer day per issue once template built | High | Email + intent |
| 3 | **Print edition** (saddle-stitched / perfect-bound) | Mailed to qualified leads (CRM top 200 + opt-in subscribers) | $15-20 per copy + postage | Highest | Hot leads |
| 4 | **Audio episode** (20-25min Will-narrated) | Podcast feed + embedded on report page | 1 day Will's recording + light edit | Medium-high | Brand recall, drive listens |

A fifth derivative — **per-chart social cuts** — auto-generated from the same data sources. 12-week distribution per issue.

**Decision:** Issue 1 ships all four tiers. Subsequent issues automate.

## 3. Length

**Body: 32 pages. Appendix: 4-6 pages. Total: 36-38 pages.**

Sits between the Economist Special Report (12-16pp) and the Knight Frank Wealth Report (~80pp). Long enough to demonstrate depth; short enough to be finished. Sections sized for finish-rate, not for maximum surface area.

## 4. Type system

| Use | Typeface | Weights | Size / leading |
|---|---|---|---|
| Display & headlines | **Tiempos Headline** (Klim Type Foundry) | 400 / 600 | 32-72pt, varies by hierarchy |
| Body | **Tiempos Text** | 400 / 400 italic | 10-10.5pt / 14pt |
| Sans / data labels / captions | **Söhne** (Klim) or **Inter** (free fallback) | 400 / 500 / 600 | 7-9pt |
| Numerals (charts + tables) | Tiempos / Söhne tabular lining figures | n/a | match context |
| Numerals (body prose) | Tiempos old-style figures | n/a | match body |

**Free-tier fallback** if Tiempos licensing not budgeted: **Source Serif Pro** (display + body) + **Inter** (sans). Both Adobe-open-source. Avoid Georgia (web-default), Playfair Display (wedding-invitation), Helvetica Neue (Monocle imitation).

**License decision:** Tiempos Headline + Text + Söhne family from Klim ≈ AUD $700-900 one-off for a small business. Recommend the paid stack for Issues 1-2, evaluate.

## 5. Colour palette

| Use | Token | Notes |
|---|---|---|
| Primary brand (data) | **Deep Ocean Blue `#003D5B`** | Refers water without being literal; reads authoritative on white; prints well CMYK |
| Background (paper) | **Cream `#F7F4EE`** | Warmer than Economist's `#F5F4F0`; signals "paper" not "screen" |
| Type | **Charcoal `#1A1A1A`** | Never pure black on cream — too harsh |
| Secondary data | **Slate `#6B7280`** | Greyscale supporting series in charts |
| Grid lines | **Light grey `#9CA3AF`** | Hairline, never bold |
| Chart surface | **Pure white `#FFFFFF`** | Charts only — keeps data legible against the paper background |
| Single accent | **Burnt sienna `#C75D2C`** | Used at most twice per issue, where genuine emphasis required |
| Heatmap ramp | **ColorBrewer BuPu** | Single-hue sequential. Never red-green (colour-blind hostile + reads "stocks") |

**Forbidden:** Economist red (signals imitation), luxury-property gold (signals marketing), any gradient or 3D treatment.

## 6. Layout grid

- **Trim:** A4 (210 × 297mm). European document feel.
- **Grid:** 12 columns, 8mm gutters.
- **Margins:** 18mm outer, 22mm inner (gutter-side).
- **Body type:** sits in columns 2-9 (8 columns wide).
- **Marginalia:** columns 10-12 (sparkline annotations, source citations, sample sizes, field-notes margin column).
- **Charts:** can break grid to full-bleed when visualisation demands.
- **Page furniture:** running header (section name | "Fields Quarterly Issue [N]" | page number) + running footer (methodology breadcrumb).

## 7. Chart vocabulary — the canon

Universal rules apply to every chart:

1. **Source line** under every chart: source + sample size + date stamp.
2. **Sentence-case titles that state the conclusion.** "Burleigh Waters has moved further than Robina since 2022" — never "Median Price by Suburb."
3. **Direct labelling** beats legends. Use legends only when labels would clutter past readability.
4. **Y-axis at zero** for bar charts; truncated allowed for line charts with a clear visual cue (zigzag).
5. **No 3D, no shadows, no gradients, no decorative elements.** Tufte data-ink ratio applies ruthlessly.
6. **Sparklines in tables** wherever the table has a row per suburb / per period.
7. **Annotation > legend.** If you can write the insight on the chart, do.
8. **Single-hue sequential ramps for heat / choropleth.** Diverging only for true mid-point data.
9. **Tabular numerals** in all chart figures.

### Chart catalogue

| # | Chart type | When to use | Fields version specifics |
|---|---|---|---|
| 1 | Indexed price line | Compare suburbs starting at different absolute levels | Three suburbs + ghost line for Greater Brisbane, rebased to Q1 2020 = 100. Direct labelling at line end. Three real-event annotations. |
| 2 | Half-violin + scatter (distribution) | Reveal that median hides bimodal markets | Per suburb; KDE shape on top, individual sale dots below; median marked. |
| 3 | DOM trend + cumulative distribution | Median vs long-tail of stale stock | Twin chart. Top: median DOM 24mo line. Bottom: cumulative curve of currently-listed properties' DOM. |
| 4 | Sale-to-list diverging bar | Buyer-vs-seller power | One bar per suburb, last 90 days. Auctions excluded (footnote). |
| 5 | Stock-on-market + seasonality ribbon | Tightness vs historical pattern | Column chart of weekly active listings; 10-90th percentile historical band shown as grey ribbon. |
| 6 | Scatter — yield vs price | Investor pricing signal | Log-x price, linear yield. Trend line + confidence band. |
| 7 | Long-run price-to-income line | Honest affordability | Gold Coast vs national, rebased index, 10+ years. |
| 8 | Twin small-multiple (rates + prices) | Serviceability overlay | Stacked panels sharing x-axis (avoiding twin-axis cardinal sin). |
| 9 | Street-level price heatmap (choropleth) | Suburb-level hides street truth | ~20m segment resolution; single-hue ramp; sale dots overlaid; hatching where N<3 in 24mo. |
| 10 | Time-on-market cumulative curve | "What's my realistic time-to-sell?" | One line per suburb, last 12mo; median + 90th percentile labelled. |
| 11 | Comparable-sale scatter + confidence band | Fields' valuation methodology made visible | Per profiled suburb; price y, floor area x; trend line + 90% CI (1.645σ). |
| 12 | Migration Sankey | Origin → destination flows | ABS Cat. 3412.0 prior 12mo. Flows >50 only. |
| 13 | Approvals vs completions paired column | Supply pipeline | Last 5 years, by quarter. Annotated approval-to-completion gap. |
| 14 | Vacancy + new-bond inflow combo | Rental-market direction | Line + light-column overlay. |
| 15 | The Conviction Map | Suburb scatter on price-momentum × tightness | See 03_content_blueprint Section 2. |
| 16 | The four-source reconciliation | Domain vs Cotality vs PropTrack vs SQM | Single chart, four lines, all rebased to Jan 2020 = 100. |
| 17 | Real Pain & Gain box-plot per suburb | Honest after-cost returns | Distribution of real-after-cost returns; median line; "X% produced a real-after-cost loss" annotation. |

## 8. Original visualisations (the WOW moments)

The list of Fields-only visualisations no Gold Coast competitor can produce:

1. **The Fields Conviction Index** — proprietary headline number, giant cover numeral.
2. **The Fields Conviction Map** — signature visual.
3. **Property-level micro-suburb price paths** — every recently-sold property as a faint line, suburb median in bold over the top.
4. **Comparable-sale scatter with confidence band** — methodology visible.
5. **Asking-vs-actual gap distribution** — only possible because Fields captures first-list vs sold prices.
6. **Days-to-sell distribution by listing month** — seasonality at sub-suburb level.
7. **Home-improvement ROI by suburb** — kitchen / bathroom / pool / extension uplifts.
8. **The "What's similar to your home?" interactive** (web-only) — reader enters address → personalised one-page chart pack. Lead-capture engine.
9. **Flood-data honesty panel** (Burleigh Waters) — City Plan overlay vs ICA Insurance Probability Zones.
10. **Conviction tracker** (Issue 2+) — last quarter's signals checked.
11. **Real Pain & Gain** — after-cost returns table.
12. **Four-source reconciliation chart** — Domain vs Cotality vs PropTrack vs SQM in one frame.

## 9. Photography direction

**Rule:** photography supports the data, never decorates it.

| What to shoot | Why | Where it goes |
|---|---|---|
| Suburb identity shots — quiet, observational frames | Mark place without selling it | Section openers (one half-page or full-bleed per suburb) |
| Built-form details (brick, fence, roof typical of suburb) | Earn place when paired with stock-composition chart | Inside-body where the chart needs context the chart cannot give |
| Process shots — Will at desk, database screen, comp report on kitchen table | Personal accountability, "one person did this" | Editor's letter; methodology page |

**Forbidden:** Stock real-estate imagery, smiling agents, "happy family" couples, twilight property exteriors, infinity pools, drone tourism.

**Captions:** every photo gets a caption with location + date + one observation in Will's voice. Sit in marginalia column, 8pt italic sans.

## 10. Cover specification

**The single most important page.**

### What the cover does NOT do
- No smiling agent.
- No hero property.
- No price headline ($1.2M).
- No "stunning", "premium", "exclusive", or any forbidden word.
- No location stock-photo treatment.

### What the cover DOES do
- States identity: **"The Fields Quarterly"** (Tiempos Headline, restrained, large but not screaming).
- States edition: **"Issue 01 · Q2 2026"** (Söhne / Inter small caps, like an academic journal masthead).
- States the **Fields Conviction Index** for the issue, in massive tabular numerals dwarfing everything else (e.g. `108.4`).
- Beneath, the three-sentence cover stat (see content blueprint Section 0).
- Footer: tagline ("Smarter with data") + URL + edition.
- One restrained visual element: either a single observational photograph (suburb identity, treated like a Penguin Classics cover) OR a thumbnail-size FCI sparkline over 5 years. **Not both.**

**Reference covers worth studying:** Penguin Classics drama series, Knight Frank Wealth Report 2024-25 cover, McKinsey Global Institute reports, The Economist Special Reports, *Apollo* magazine.

### Cover paper (print)
300-350gsm uncoated matte cover stock. The hand registers weight before the eye reads the cover.

## 11. Production tool — Quarto + Typst

**Decision:** **Quarto + Typst** for primary production. InDesign reserved only for cover and section-opener custom typography if a designer is contracted.

**Why:**
- Markdown source — version controlled in git.
- Charts rendered live from Python against the live Cosmos DB — when next quarter's data arrives, the report regenerates.
- Typst output gives near-InDesign quality at minutes-to-render speeds.
- Custom templates take initial investment but pay back across 4+ issues.
- Free.

**Pipeline:**
1. Quarto `.qmd` source files for each section.
2. Python code blocks pull data from `precomputed_indexed_prices`, `precomputed_market_charts`, `precomputed_macro_indicators` — or via `market_update_data.py` script wrapper.
3. Charts generated via `plotnine` / `matplotlib` with custom Fields theme (matching colour palette + type stack).
4. Typst output produces the print-grade PDF.
5. Quarto HTML output produces the web edition (with light React enhancements for the interactive elements).
6. Audio recorded separately; transcript auto-generated and posted as alt-text.

**Alternative option (if Quarto+Typst too steep):** keep the existing Jinja2 + headless Chrome pipeline used for per-property reports, extended to multi-page. Less typographically refined but ships faster.

## 12. File specifications

| Format | Spec |
|---|---|
| Trim | A4 (210 × 297mm) for print and screen PDF |
| Resolution | 300dpi for print images; sRGB → CMYK conversion at export |
| Bleed | 3mm on print edition |
| Fonts | All embedded (Tiempos family + Söhne / Inter) |
| PDF web | Standard PDF, target ≤ 8MB |
| PDF print | PDF/X-1a:2001, 30-60MB |

## 13. Print specifications

| Spec | Value |
|---|---|
| Paper (text) | 120-150gsm uncoated matte |
| Paper (cover) | 300-350gsm uncoated matte |
| Recommended stocks | Colorplan, Munken Pure, Mohawk Superfine (premium); standard premium offset uncoated otherwise |
| Binding | Saddle-stitched up to 32 pages; perfect-bound from 36+ pages |
| Print run | Issue 1: 100-200 copies. Scale only if first cycle generates demand |
| Distribution | Australia Post Express Parcel for high-value leads (the box is part of the experience); standard satchel for general subscribers |

## 14. Pre-publication checklist (operational)

Run before every issue ships:

- [ ] Every chart has source + sample size + date in caption
- [ ] Every fact claim is sourced in appendix
- [ ] No forbidden words (search-and-find pass: stunning, nestled, boasting, rare opportunity, robust market, unprecedented, hot market, must-see, gem, premium, exclusive)
- [ ] No advice language (you should, consider, now is a good time) — manual editorial pass
- [ ] No predictive language (will, going to, set to) — replaced with conditional ("if X holds, the data is consistent with Y")
- [ ] All numbers in `$1,250,000` format, no abbreviations
- [ ] All suburbs capitalised
- [ ] FCI on cover matches FCI on inside spread
- [ ] Last-quarter conviction tracker reconciled (Issue 2+)
- [ ] Methodology breadcrumb visible on every spread
- [ ] Editor's letter signed by Will, dated, with email
- [ ] Appendix sample sizes match body chart captions
- [ ] Two independent reads (Will + one external red-pen pass)
- [ ] PDF accessibility: alt text on charts, tagged headings
- [ ] Web edition Lighthouse ≥ 90 mobile
- [ ] Audio edition has accurate transcript
- [ ] All UTM parameters set on outbound links
- [ ] Print proofs reviewed under daylight + tungsten before press run
- [ ] Permanent canonical URL active (`fieldsestate.com.au/quarterly/q[X]-[Y]`)
- [ ] Free CSV download published (no email gate)
- [ ] Post-publication CEO Agent post-mortem scheduled

## 15. Brand voice rules — quick reference

(Consolidated from the editorial constraints; full version in `02_psychology_playbook.md` Section F.)

- **No advice** — data only, reader draws conclusions.
- **No predictions** — conditional language only.
- **No single valuation in headlines** — comparable ranges only.
- **Value framing** — every property feature is a value, not a flaw.
- **Forbidden words** — listed above.
- **Number format** — `$1,250,000` (never `$1.25m`).
- **Suburbs always capitalised.**
- **Hedging hierarchy** — match the strength of the data.
- **"Mum understands" test** — every paragraph readable without industry jargon.

If a draft section fails any of these, rewrite.
