# Content Blueprint — The Fields Quarterly

**Document:** 03 of 7 (Strategy series)
**Sources:** `01_strategic_positioning.md`, `02_psychology_playbook.md`, all five research files in `/research/`
**Purpose:** Define section-by-section what the report contains, why, what data feeds it, what chart sits there, and what reader job it performs. This is the table of contents with reasons.

---

## 1. The named proprietary asset — *Fields Conviction Index*

**Decision:** every issue is anchored by a named, proprietary index.

The lesson from Knight Frank (PIRI 100), Cotality (Hedonic Home Value Index), S&P/Case-Shiller, Halifax, and HTW (Property Clock) is unanimous: a named index that compounds over time is the single biggest reason a market report becomes citable rather than disposable.

**Name:** *Fields Conviction Index* (FCI).
- "Fields" — brand.
- "Conviction" — implies analytical judgement, not raw measurement.
- "Index" — comparable, trackable, anchored.

**Composition:** weighted composite of four observable forces:
| Component | Weight | Source | Direction |
|---|---|---|---|
| Indexed price (hedonic) | 40% | `precomputed_indexed_prices` rolling 12-month | + = rising prices |
| Sale-to-list ratio | 20% | Fields scraper (first list price → sold price) | + = vendors getting closer to ask |
| Stock-on-market vs 5-year baseline | 20% | `precomputed_active_listings` + historical | − = tighter than baseline = +FCI |
| Days-on-market median (inverse) | 20% | `precomputed_market_charts` | − = faster sales = +FCI |

Each component is z-scored against its own 5-year history, then combined. Rebased to FCI = 100 at January 2020.

**Scale interpretation (designed before publication):**
- 80-95 = cooling
- 95-105 = balanced
- 105-115 = firming
- 115+ = tight / sellers' advantage
- Below 80 = buyers' advantage

**Why this composition works:** it is not just a price index. It captures *behavioural state* — how fast, how tight, how negotiable — which is what readers actually want to know. Pure price indices miss the moment a market starts to break.

**Public deliverable:** every issue carries one giant FCI numeral on the cover, an FCI sparkline in every section header, and a downloadable monthly FCI CSV for free (no email gate). The FCI becomes the citation hook; the report becomes the explanation.

## 2. The signature visual — *Fields Conviction Map*

The HTW Property Clock teaches us that one branded visual = brand recognition. Our equivalent, with a Gold Coast spin:

**Plot:** every Gold Coast suburb plotted on a 2-axis scatter:
- **X axis:** 12-month indexed price change (%)
- **Y axis:** 5-year-baseline-adjusted listings tightness (z-score)
- **Quadrants:** Heating (top-right), Frothy (top-left, prices up but stock building), Tightening (bottom-right, stock falling but prices flat), Cooling (bottom-left).

Robina, Burleigh Waters, Varsity Lakes are highlighted in brand colour; other suburbs in mid-grey. Each suburb is a labelled dot with a 12-month tail (where it came from). This converts to a single shareable image journalists and brokers will reuse; over four issues it becomes "Fields says Burleigh moved from Frothy to Tightening this quarter."

**Where it lives:** page 6-7 spread, every issue. Same template, new dots.

## 3. The "one tension" doctrine

Lesson from Hamptons (UK) *Market Insight*: the best quarterly reports pick **one** big idea and dramatise it. No quarterly recap of every metric; one editorial through-line per issue.

Each issue has a working title that is the tension:
- Q2 2026 candidate: **"The Standoff"** — sales volumes have collapsed but prices have not. Why?
- Q3 2026 candidate: **"The Split"** — units and houses no longer move together. What that means.
- Q4 2026 candidate: **"What We Got Right (and Wrong)"** — a year of conviction tracking.
- Q1 2027 candidate: **"The Rates Test"** — if RBA cuts, who runs first?

Every section serves the tension. Charts are chosen because they advance the through-line. The data tells one story, not five.

## 4. Length and shape

**Body: 32 pages. Appendix: 4-6 pages. Total: 36-38 pages.**

This sits between the Economist Special Report (12-16pp) and the Knight Frank Wealth Report (~80pp). Long enough to demonstrate depth; short enough to be finished. Bain/McKinsey thought-leadership averages 24-40pp, which is the credible band for an analytical document.

**Structure (the spine):**

| # | Section | Pages | Job | Source data |
|---|---|---|---|---|
| 0 | Cover | 1 | Authority cue | FCI numeral, three-sentence cover stat |
| 1 | Masthead + colophon | 1 | Trust cue | Edition, date stamp, "data closed" date |
| 2 | Editor's letter | 1 | Voice + accountability | Will, signed |
| 3 | The Fields Conviction Index | 2 | Headline number, framed | Composite calculation |
| 4 | The Fields Conviction Map | 2 | Signature visual | Suburb scatter |
| 5 | The Tension (issue thesis) | 2 | Editorial through-line | One chart + 800 words |
| 6 | Where prices actually are | 4 | Price chapter | Indexed price, distribution, four-source reconciliation |
| 7 | How fast the market moves | 3 | Velocity chapter | DOM distribution, sale-to-list, stock-on-market |
| 8 | Who is buying | 2 | Demand chapter | Migration, demographics, lending |
| 9 | What is being built | 2 | Supply chapter | Approvals, completions, pipeline |
| 10 | The Three Suburbs | 6 (2 per suburb) | The micro chapter | Suburb dashboards |
| 11 | The Real Pain & Gain | 2 | Honest returns chapter | After-cost holding returns |
| 12 | Last quarter's conviction tracker | 1 | Forecast accountability | What we said + what happened |
| 13 | What this report does not answer | 2 | Honesty chapter | Limits, caveats, sample sizes |
| 14 | Methodology | 2 | Trust + citations | How every chart is made |
| 15 | Editor's closing | 1 | Voice + soft CTA | Will, signed |
| 16 | Appendix | 4-6 | Receipts | Tables, sources, sample sizes, raw data attribution |

Section 12 (the conviction tracker) is empty in Issue 1 — but the *space* is reserved for it. From Issue 2 onwards, this becomes one of the most-read pages.

## 5. Section-by-section detail

### Section 0 — Cover

**Goal:** in three seconds, a Burleigh Waters homeowner picks it up and decides it's not a brochure.

**Elements:**
- Display serif: **"The Fields Quarterly"** + edition (e.g. "Issue 01 · Q2 2026").
- Vast tabular numeral: the **FCI for the quarter** (e.g. `108.4`).
- Three-sentence cover stat — exact numbers, no advice. Example for Q2 2026:
  > *In Q2 2026, southern Gold Coast house prices rose 1.7% on the Fields Conviction Index. Sales volumes fell 28% versus the five-year average. Days-on-market for sold properties closed 13% faster despite the volume drop.*
- Footer: "Smarter with data. fieldsestate.com.au/quarterly".

**Forbidden elements:** photo of agent or property, hero asking-price, marketing tagline, "stunning", "premium", any phrase from a real-estate flyer.

### Section 1 — Masthead + colophon

**Page facing the inside cover.** Equivalent to the editorial mast in a journal.

**Elements:**
- Title block: *The Fields Quarterly · Issue [N] · [Quarter] [Year]*
- Editor: Will Simpson (with email).
- Methodology summary: "Hedonic indexed prices, comparable-sales valuations, four-source reconciliation. Full method on page 28."
- Data closed: "31 March 2026 (Q2 issue)."
- Next edition: "31 July 2026."
- Permanent URL: `fieldsestate.com.au/quarterly/q2-2026`.
- Funding model: "Free for buyers. Funded by sellers who commission custom analyses."
- Privacy line: "Your email is used only to send the next edition. One-click unsubscribe."

This page does the work of pre-empting the "what's their angle?" objection without ever being defensive.

### Section 2 — Editor's letter

**One page. Will, signed.**

Three things, in order:
1. **The tension** — one paragraph naming the editorial through-line. This is the share-able sentence ("Sales volumes have halved on the southern Gold Coast. Prices have not. Here is why we think that is.").
2. **Why we built it** — one paragraph on the analytical operation. "I built the database. I run the model. I am responsible for any errors." Authority through accountability.
3. **What we admit we don't know** — one short paragraph naming one specific uncertainty in this issue. ("This issue cannot tell you whether the volume drop is structural or seasonal — we'll know in October.")

Signed in scanned handwriting at the bottom.

### Section 3 — The Fields Conviction Index

**Two pages.** Spread layout.

**Left page:**
- Headline: "The Fields Conviction Index, Issue [N]"
- Sub-headline as conclusion: e.g. "108.4: a market still tight, but cooling at the edges."
- 5-year FCI line chart (rebased to 100 at Jan 2020) — annotated with: RBA cuts, Olympics announcement, peak FCI date, the trough.
- Sparkline of last 12 months in the margin.

**Right page:**
- The four components shown as small multiples:
  - Indexed price (current vs 12mo ago)
  - Sale-to-list ratio (current vs 5-year median)
  - Stock-on-market (current vs 5-year baseline ribbon)
  - Days-on-market (current vs 5-year median)
- Below: a one-paragraph plain-English read: "The FCI rose 1.4 points on the quarter. The lift was driven primarily by stock contraction and faster days-on-market. Indexed prices contributed only marginally."
- Source line beneath every chart.

### Section 4 — The Fields Conviction Map

**Two pages.** Full-bleed scatter on the right page; explanation on the left.

**Right page (the visual):**
- Scatter of every Gold Coast suburb (or top 30 by transaction volume).
- X = 12-month price change (%). Y = listings tightness z-score.
- Four quadrants labelled.
- Robina, Burleigh Waters, Varsity Lakes called out in brand colour.
- Each suburb dot has a 12-month tail showing trajectory.
- Three or four narrative annotations on the chart itself: "Burleigh Waters moved from Frothy to Tightening this quarter — the seventh consecutive quarter of stock contraction."

**Left page (the explanation):**
- Four quadrant definitions in small print.
- A one-paragraph reading: "What the map says this quarter."
- Five suburbs called out by name with one-line context.

This is the page screenshot-able for social. Optimise for that.

### Section 5 — The Tension (issue thesis)

**Two pages.** This is the editorial heart.

**Left page:**
- Section title (the issue's working name, e.g. "The Standoff").
- One half-page hero chart that *contains* the tension visually. For Q2 2026: a twin-line chart of indexed prices vs sales volume, both rebased — the lines diverging is the visual signature of the issue's thesis.
- Source line.

**Right page:**
- 600-800 words of editorial: the issue's thesis stated, evidenced, and contextualised.
- Opening sentence reaches across all four reader archetypes.
- One named-but-anonymised property example in the middle (narrative transportation per Green & Brock 2000).
- Closes with a question ("If volume returns, do prices follow? Or does the standoff break in the other direction?") that flows into the rest of the report.

### Section 6 — Where prices actually are

**Four pages. The price chapter.**

**Page 1:** indexed price line chart for the southern Gold Coast composite + the three core suburbs, rebased to Q1 2020 = 100. Direct labelling, three or four annotations. Caption: "Hedonic-adjusted index. See methodology, page 28."

**Page 2:** the four-source reconciliation chart — the original visualisation no other Gold Coast publisher offers.
- Single chart, four lines: Domain median, Cotality Hedonic, PropTrack asking, SQM asking.
- All rebased to Jan 2020 = 100.
- Annotations explain the gap and the reason.
- Caption: "When sources disagree, we report the gap, not a winner. The four indices answer slightly different questions."

This is the page Informed Observers (journalists, brokers) cite the most.

**Page 3:** distribution chart per suburb — half-violin + sale dots.
- Three small multiples (Robina, Burleigh Waters, Varsity Lakes).
- Median line drawn; 25/75/95 percentile labelled.
- Sample sizes prominent.
- Caption: "The median hides the shape. Burleigh Waters' bimodal distribution reflects canal vs non-canal sub-markets."

**Page 4:** the by-tier price-path chart.
- For each suburb: lines for entry-tier, mid-tier, prestige-tier prices.
- Visualises whether the suburb is rising in concert or splitting.
- Specifically designed to defuse anchoring — the reader sees the tier they belong to instead of being anchored by the median.

### Section 7 — How fast the market moves

**Three pages. The velocity chapter.**

**Page 1:** Days-on-market — twin chart.
- Top: median DOM by suburb, last 24 months, line chart.
- Bottom: cumulative-curve distribution of currently-listed properties' DOM (the "what % of stock has been listed >60 days?" question).
- Annotation: the long-tail flag if stale stock is building.

**Page 2:** Sale-to-list ratio.
- Diverging bar from 100% baseline.
- One bar per suburb, last 90 days.
- Excludes auctions (footnote).
- Annotation explains negotiation latitude per suburb.

**Page 3:** Stock-on-market with seasonality band.
- Column chart of weekly active listings.
- Grey ribbon = 10-90th percentile of historical same-week values.
- Reader sees "this is unusual December" or "this is normal February" at a glance.

### Section 8 — Who is buying

**Two pages. The demand chapter.**

**Page 1:** Migration Sankey diagram — origins (Sydney, Melbourne, Brisbane, regional) → Gold Coast suburbs. ABS data, last 12 months. Caption: "Flows >50 persons only. Source: ABS Cat. 3412.0."

**Page 2:** Demographic and lending picture.
- Who is buying — owner-occupier vs investor share, age band, FHB share.
- Lending picture — DTI distribution of new mortgages, average LVR.
- The new APRA DTI speed limit (≤20% at DTI ≥6×) referenced.
- Caption: "Entry-level FHB demand has narrowed under the May 2025 first-home concession's $700-800k bracket."

### Section 9 — What is being built

**Two pages. The supply chapter.**

**Page 1:** Approvals vs completions.
- Paired column chart, last 5 years, by quarter.
- Annotation of the gap (approved-but-not-completed pipeline).

**Page 2:** Pipeline by suburb.
- DAs lodged + DAs approved + off-the-plan units in marketing for the three core suburbs.
- Caption: "Approvals lead completions by 18-24 months. The pipeline shown today is housing supply for 2027-28."
- Footnote: "Approvals are not pre-sales. We do not count brochures as completions."

### Section 10 — The Three Suburbs

**Six pages. Two per suburb. The most-read chapter.**

For each suburb, two pages following an identical template:

**Page 1 — Identity:**
- Section opener photograph (Will's local photography — observational, not promotional).
- Suburb name.
- Three-stat header (FCI for the suburb, indexed-price 12mo change, transaction count).
- 600 words on the suburb's character — geography, housing stock, who lives there, what defines this market. Always values, not flaws ("walking distance to beach, lower entry price" not "small block").
- One named-but-anonymised recent transaction that opens the data narrative for this suburb.

**Page 2 — Data dashboard:**
- Indexed price chart (5 years).
- Sales volume sparkline + 5-year mean.
- DOM distribution boxplot.
- Sale-to-list ratio.
- Comparable-sales scatter (price vs floor area, with confidence band).
- A "What surprised us this quarter" callout box (confirmation-bias counter; Section B.7 of the playbook).
- Three-numbers-to-watch closing block (signal, not advice).

**Suburb-specific dimensions:**
- **Robina:** master-planned vs older estate split shown explicitly. Houses-vs-units divergence chart.
- **Burleigh Waters:** the **flood-data honesty panel** (City Plan overlay vs ICA Insurance Probability Zones). One of the report's most cited sections. Canal vs non-canal split.
- **Varsity Lakes:** lake-fronting vs non-lake split. Bond Uni rental floor noted.

### Section 11 — The Real Pain & Gain

**Two pages.** A direct response to CoreLogic's *Pain & Gain* report — but corrected.

**The thesis:** Cotality reports nominal returns. We strip CPI, council rates, average maintenance, and mortgage interest. The result: a six-year hold returning 22% nominal often returns 4% real. This is publishable, repeatable, and impossible for CoreLogic to publish without offending bank clients.

**Page 1:** The Real Pain & Gain table.
- Hold-period bands (0-2yr, 2-5yr, 5-10yr, 10yr+).
- Three columns: nominal gain, real gain (CPI-adjusted), real gain after holding costs.
- One column for sample size.
- Captioned with assumptions explicit: "CPI from ABS, holding-cost assumptions per [methodology page]."

**Page 2:** The chart — distribution of real-after-cost returns by suburb.
- Box-plot per suburb, last 12 months of resold stock.
- Median line drawn.
- Annotation: "X% of resold properties produced a real-after-cost loss."
- Caption: "Honest returns. The number you actually pocketed after inflation, council rates, average maintenance, and mortgage interest."

This section is the credibility bombshell. Once published, it's the section every honest analyst will share.

### Section 12 — Last quarter's conviction tracker

**One page.** From Issue 2 onwards.

**Format:**
- Two columns. Left: "What we said in [previous edition]." Right: "What happened."
- 4-6 entries per page.
- Each entry has a clear icon: ✓ confirmed, ✗ disconfirmed, ⏳ unresolved.
- One-paragraph closing: "What we got wrong, and what we changed."

This is the page that earns long-term trust. Cooley/Edelman 2025: companies that admit being wrong build *more* trust than those that don't.

**Issue 1:** this page is replaced by a forward-looking commitment: "From Issue 2 onwards, this page will track the previous quarter's conditional signals against subsequent data."

### Section 13 — What this report does not answer

**Two pages.** The honesty chapter.

**Page 1:** Three to five honest items per quarter.
- Sample-size limitations.
- Data-source disagreements.
- Assumptions in the indexed-price calculation.
- Where photo-analysis ML may have erred.
- One question we asked the data and couldn't answer.

**Page 2:** A "what we are working on" panel.
- Methodology improvements in development.
- Data sources we are integrating.
- Open invitation to send corrections (with email).

This is the page that moves an Informed Observer from sceptic to amplifier.

### Section 14 — Methodology

**Two pages. First-class.**

**Page 1:** the technical method.
- Hedonic regression: how the FCI is built.
- Comparable-sales adjustment: how the value range is computed.
- DOM definition: list-to-unconditional, not list-to-settlement.
- Sale-to-list: first list price, not current.
- Exclusions explicitly listed.
- Sample-size threshold: any quarter <30 transactions flagged.

**Page 2:** sources and credits.
- Every data source named with link.
- Academic underpinnings cited where used (Abelson 2005, Genesove & Mayer 2001, Loewenstein 1994).
- Cotality, Domain, REA acknowledged where their data is referenced.
- Correction policy stated.

### Section 15 — Editor's closing

**One page.** Will, signed.

**Three things:**
1. One paragraph: a reflection on the issue — what surprised the editor, what they're watching.
2. One paragraph: the soft CTA — "If you'd like the same analysis applied to your home, reply to this email." or "Get the next edition: fieldsestate.com.au/quarterly/subscribe."
3. One paragraph: an invitation. "Tell us what you'd want analysed in the next edition — reply to this email."

Signed in scanned handwriting.

### Section 16 — Appendix

**Four to six pages. Receipts.**

- Full data tables for every chart (so a journalist can verify).
- Sample sizes table by suburb × quarter × metric.
- All sources with URLs.
- Methodology micro-FAQs.
- Permanent CSV download URL.
- Correction log (Issue 2+).
- "How to cite this report" line.

## 6. Cross-issue spine

Some elements are constant; some change every issue. The series identity sits in what's constant.

**Always present (the spine):**
- The cover with FCI numeral
- The Fields Conviction Map
- The Three Suburbs section
- The Methodology pages
- The "What we don't know" page
- The Editor's letter (open and close)

**Changes every issue (the variation):**
- The Tension (one editorial through-line)
- The cover stat (current numbers)
- The named-property opening of the suburb sections
- The "What surprised us" callouts
- The conviction tracker (from Issue 2)
- The signature deep-dive — one per issue (e.g. flood data Q2; school catchments Q3; off-the-plan supply Q4)

**Series of WOW moments planned:**
- Q2 2026: The four-source price reconciliation chart + Burleigh Waters flood-data honesty panel.
- Q3 2026: Real Pain & Gain (after-cost returns).
- Q4 2026: First conviction-tracker page + Year in Review.
- Q1 2027: Home-improvement ROI by suburb (kitchen, pool, extension).
- Q2 2027: School catchment vs non-catchment median analysis.

Each issue has at least one new originality. The reader is rewarded for staying subscribed.

## 7. Annual Year-in-Review (the December asset)

Q4 issue is also the year-in-review. Borrows the Cotality *Best of the Best* format because it's already proven to own December media:
- Top 5 sales of the year (named).
- Top 10 fastest-selling streets.
- Top 10 biggest discounts.
- Best-yielding pockets.
- Plus the conviction tracker for the full year.

This issue writes itself for journalists and is the most-distributed issue.

## 8. Distribution cadence

- **Quarterly flagship report** — 1st of February, May, August, November (after each quarter's data closes).
- **Monthly Pulse** — short email + chart pack, mid-month, between issues. Keeps the email list warm.
- **Weekly micro-update (Issue 4 onwards)** — one chart, one paragraph, three numbers. Sub-1000-word email. Modeled on John Burns' newsletter playbook (40k subscribers).
- **Audio episode** — paired with each quarterly. 20-25 minutes. Hosted on the report page + pushed to Spotify/Apple as "The Fields Quarterly" feed.
- **Social cuts** — auto-generated from each chart. 12-week distribution per issue.

## 9. The 12-month editorial calendar

Treat each issue as Hamptons-style with one big idea.

| Issue | Cycle close | Distribution | Working title | Signature original |
|---|---|---|---|---|
| 01 | Q2 2026 (Apr-Jun) | Aug 2026 | "The Standoff" | Four-source price reconciliation; flood-data honesty panel |
| 02 | Q3 2026 (Jul-Sep) | Nov 2026 | "The Split" | Houses-vs-units indexed divergence chart for each suburb |
| 03 | Q4 2026 (Oct-Dec) | Feb 2027 | "What We Got Right (and Wrong)" | First conviction tracker; year-in-review list-driven format |
| 04 | Q1 2027 (Jan-Mar) | May 2027 | "The Rates Test" | Home-improvement ROI by suburb |

Each title is editorial-led, not metric-led. A reader remembers a tension; they don't remember a number.

## 10. The reader experiences this report as

A reader who has finished the report should be able to do the following:

1. **State the issue's tension in one sentence.** ("The Standoff: sales have halved but prices haven't moved. Why?")
2. **Recall the FCI for this issue.** ("108 — slightly tight.")
3. **Place their own home on the Conviction Map.** ("Burleigh Waters is in Tightening.")
4. **Cite at least one number from the suburb section.** ("Days on market in Burleigh fell from 48 to 28.")
5. **Recall one thing the report admits it doesn't know.** ("Whether the volume drop is structural or seasonal.")
6. **Have a low-friction next action available.** (Subscribe to next edition. Try the "your suburb" interactive. Request a Position Report.)

If the reader can do all six, the report has done its job. The conversion is the consequence, not the goal.

## 11. What this blueprint deliberately rejects

1. **Boilerplate market summary.** Replaced with the Tension.
2. **Capital-city aggregation.** Replaced with three suburbs at depth.
3. **A single median in a headline.** Replaced with ranges and distributions.
4. **Forecasts.** Replaced with the conviction tracker — we report indicators, then check ourselves.
5. **Hidden methodology.** Replaced with a first-class methodology chapter.
6. **A single CTA at the end.** Replaced with three soft CTAs distributed across the report.
7. **Stock photography.** Replaced with Will's observational suburb photography.
8. **Generic chart titles.** Replaced with sentence-case conclusions.

If a draft includes any of these eight, it has slipped backwards. Rewrite.

## 12. Key open decisions for Will

These are choices the blueprint cannot make alone.

1. **The first issue's tension.** Recommended: "The Standoff" — sales-volume vs price tension, evidence-rich, reader-relevant. Alternative: lead with the Burleigh Waters flood-data section as the standalone WOW.
2. **Print run for Issue 1.** Recommended: 200 print copies, distributed only to top 200 known prospects from CRM and high-LinkedIn-engagement Gold Coast contacts. Cost ~$3,000 at $15/copy + postage. Single seller conversion pays it back many times.
3. **Audio narration — Will or AI clone?** Recommended: Will's voice for Issue 1-3 minimum. Brand-defining.
4. **Should the Conviction Map go on the website's home page?** Recommended: yes, after Issue 1 is published — becomes the "what's the southern Gold Coast doing" landing page that Daniel's feedback was asking for.
5. **Pricing for the per-property Position Report (the conversion offer).** Currently free. Recommend keeping free until Q4 2026, then introducing a tiered model (free for Quarterly subscribers, $295 for non-subscribers).
