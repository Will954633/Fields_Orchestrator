# Visual & Format Design Brief — Fields Market Report

*Research compiled May 2026. Reference points: FT Visual Vocabulary, Knight Frank Wealth Report, Monocle, The Economist, NYT Upshot, ProPublica, Klim Type Foundry. Audience: a sceptical, finance-savvy Gold Coast homeowner who reads the AFR and treats real-estate marketing with quiet contempt.*

---

## 1. Design philosophy

The Fields Market Report should read as **data journalism that happens to be about property** — not a property report that happens to contain charts. The closest analogues are *The Economist* (restraint, one chart one message, white space, no ornament), the *Knight Frank Wealth Report* (institutional gravitas, twenty-edition heritage cues, named proprietary indices like PIRI 100), *Monocle* (Plantin serif + Helvetica rigour, dense but orderly grid, paper-stock changes between sections), and the FT/Reuters/NYT Upshot newsroom standards (Visual Vocabulary discipline, sourced footnotes, exact figures). The reader test: a 55-year-old Burleigh Waters homeowner with an SMSF should pick it up, scan three pages, and think *this is calibrated like a research note, not a brochure*. That means: no stock photography of golden-hour pools, no "stunning" or "nestled", no rounded headline figures, no agent's face on the cover. Instead — a measured serif body, a single restrained brand colour against off-white, captions that cite sources and sample sizes, and a sleeve of original visualisations no other Gold Coast operator could produce because no other Gold Coast operator has the data. The look is *librarian, not luxury*. Authority is signalled by what is left out.

---

## 2. Format decision: print + digital + audio

### Recommendation: **Tiered hybrid release** — digital first, premium print for qualified leads, audio for distribution multiplier.

**Tier 1 — Web edition (free, ungated, primary):** A scrollytelling-style page at `fieldsestate.com.au/report/[quarter]-[year]`. Built with the same React/Vite stack as the rest of the site (no Shorthand subscription needed). Charts are live D3/Plot/Recharts components reading from the existing market-metrics API — when the underlying data refreshes, the report refreshes. This is the discoverable, share-on-LinkedIn, link-from-Facebook-ad version. Soft email gate AFTER the reader has seen ~50% of content (delayed gating lifts conversion 35-45% vs hard gate per Brixon 2025 data).

**Tier 2 — PDF edition (email-gated, downloadable):** Same content as web edition, redesigned for A4 print-quality PDF (300dpi, embedded fonts, CMYK-safe palette). Single field email capture. Studies and reports are the highest-converting B2B/B2C lead-magnet format in financial services (6-12% landing-page conversion when value-density is high; financial impact calculators hit 9-12%). One field forms outperform 3+ field forms by ~12%.

**Tier 3 — Print edition (qualified-leads only, ~50-200 copies):** Saddle-stitched or perfect-bound depending on length. Mailed to (a) anyone who books a seller consultation, (b) top 200 known prospects from CRM, (c) every property-page lead-magnet conversion that opts into "send me the print edition" at $0 cost to them. This is the gifting / coffee-table / fridge-magnet artefact. Royal Printers / Pagination 2024 research: print materials are remembered by ~80% of recipients vs ~50% for email; require 21% less cognitive load (Canada Post). Trust premium is concentrated in older + high-income demographics — i.e. the seller market.

**Tier 4 — Audio edition (~20-25 min episode):** Will reads (or AI voice clones — but Will's voice builds the brand). Released as a podcast feed and embedded on the report web page. Audio is no longer a secondary channel: 76% of consumers remember audio content; audio-first omnichannel campaigns drive 84% listener action (Acast 2024). Audio also handles the "I'm driving from Robina to my office" listener that the PDF can't reach.

**Tier 5 — Social cuts (extracted, not produced separately):** Each chart in the report is a square / 9:16 export with the same visual identity, captioned for Facebook / Instagram / LinkedIn. The report becomes a 12-week content engine, not a one-shot drop.

### Cost / benefit summary

| Format | Production cost | Recurring | Reach | Trust signal | Lead value |
|---|---|---|---|---|---|
| Web | Time only (existing stack) | Auto-refreshes | Highest | Medium | Email capture |
| PDF | Time + design | Quarterly redesign | Medium | High | Email + intent |
| Print | $5-15/copy + postage | Quarterly print run | Lowest | Highest | Hot leads only |
| Audio | 1-2 hrs Will's time | Quarterly episode | High (commute) | Medium-high | Brand recall |
| Social cuts | Auto-generated from charts | Free | Highest reach | Medium | Top of funnel |

---

## 3. Length

### Recommendation: **28-36 pages flagship, plus appendix.**

This is the "medium-long" sweet spot. Knight Frank Wealth Report runs ~80-110pp but is global and twenty editions deep — Fields hasn't earned that yet, and a thin first edition reads as confident. HTW Month in Review is ~80-90pp but it's a national network's collated commentary, not a single-author analytical piece. The Economist's flagship Special Reports run 12-16pp inside the magazine; standalone McKinsey / Bain / Knight Frank thought-leadership averages 24-40pp. Unbounce conversion data: pages with >125 words can outconvert short pages by 220% when the offer is high-value and complex — property valuation qualifies. But each unnecessary page reduces *finish rate*, and finish rate is what produces the "this is different" effect.

**Proposed structure (target 32pp body + 4-6pp appendix):**

| Section | Pages | Purpose |
|---|---|---|
| Cover + masthead + colophon | 2 | Authority cues |
| Editor's letter (Will, signed) | 1 | Voice, accountability |
| The Fields Index (proprietary headline number) | 2 | The takeaway, framed |
| Methodology box (running footer throughout) | — | Trust |
| Section 1: Where prices actually are | 6 | Indexed price, distribution, tier |
| Section 2: How fast the market moves | 5 | DOM, sale-to-list, clearance, stock |
| Section 3: Who is buying and selling | 4 | Migration, demographic, finance |
| Section 4: The three core suburbs in detail | 6 | Robina / Burleigh Waters / Varsity Lakes |
| Section 5: What the data does not tell you | 3 | Limits, caveats, honest uncertainty |
| Closing letter + how to get the next edition | 1 | Conversion |
| Appendix: data, sources, sample sizes | 4-6 | Receipts |

The appendix is critical — every chart in the body cites `App. p.34` for full data. This is the single biggest credibility signal that separates this from a brochure.

---

## 4. Typography & layout system

### Type stack

- **Headlines / display:** *Tiempos Headline* (Klim Type Foundry) — a Plantin/Times-derived serif Sowersby designed specifically for editorial authority. If budget is tight, the free fallback is *Source Serif Pro* (Adobe, open-source). Avoid Georgia (web-default, no gravitas) and Playfair Display (too "wedding invitation").
- **Body:** *Tiempos Text* at 10-10.5pt on 14pt leading, max 65 characters per line. Body type is the single most important decision — it carries 90% of the reader's time.
- **Sans / data labels / captions:** *Söhne* (Klim) or *Inter* (free, open-source, near-perfect substitute). Never Helvetica Neue (Monocle owns that signal; copying it reads as imitation). Sans is for chart axes, footnotes, page furniture.
- **Numerals:** Tabular lining figures throughout charts and tables. Old-style figures in body prose for amounts ("$1,250,000"). This is the small detail that finance readers register subconsciously.

### Grid

12-column grid, 8mm gutters, 18mm outer margin, 22mm inner (gutter-side) margin. A4 trim (210×297mm) for print compatibility — gives a slightly more "European document" feel than US Letter. Body type sits in columns 2-9 (8 cols wide); marginalia (sparkline annotations, source citations, sample sizes) live in columns 10-12. Charts can break the grid to full-bleed when the visualisation demands it (e.g. street-level heatmap).

### Colour palette

- **Primary brand (data):** Single restrained accent. Avoid red (Economist owns it, also reads "alarm"). Recommend **deep ocean blue `#003D5B`** or **Gold Coast indigo `#1A3A52`** — references water without being literal, reads authoritative on white, prints well CMYK.
- **Background:** Off-white `#F7F4EE` (warmer than Economist's `#F5F4F0`, signals "paper" not "screen"). Pure white only for chart canvases.
- **Type:** Charcoal `#1A1A1A` (never pure black — too harsh on cream stock).
- **Supporting greys:** `#6B7280` for secondary data, `#9CA3AF` for grid lines, `#E5E7EB` for chart backgrounds when needed.
- **Single secondary accent (for highlight only):** Burnt sienna `#C75D2C` — used sparingly, maybe twice in the document, where genuine emphasis is required.
- **Heatmap ramp:** Colorbrewer `BuPu` (single-hue sequential) for heatmaps. Never red-green (colour-blind hostile, also reads "stock market").

### Page furniture

- Running header: section name (left) | "Fields Market Report Q[X] [YEAR]" (centre) | page number (right). Hairline rule.
- Running footer: methodology breadcrumb — e.g. "All transaction figures: Domain.com.au verified sales | Sample sizes in App. p.34"
- Pull quotes set in Tiempos Headline at 24pt, indented one column.
- Chart titles: sentence case, bold sans, never "Figure 3.4: Median Price by Suburb". Instead: "Burleigh Waters median has moved further than Robina's since 2022".
- Captions: italic sans, 8pt, with source + N + date stamp on every single chart.

### References
- ProPublica's typography guide (Tiempos in use): https://guides.propublica.org/design/typography/
- Klim Type Foundry on Tiempos: https://klim.co.nz/fonts/tiempos-text/
- The Economist style guide: https://sa.ipaa.org.au/wp-content/uploads/2026/02/Economist-CHARTstyleguide_20170505.pdf
- Monocle teardown (Plantin + Helvetica + grid): https://visualjournalcraft.com/article/monocle-brand-identity-teardown

---

## 5. Chart vocabulary — the canon

Following the FT Visual Vocabulary's 9-category framework. For each recurring chart in the report, the table below specifies use, abuse, and the Fields version.

### 5.1 Indexed price line (Change-over-Time)
- **When to use:** Comparing trajectories across suburbs / markets that started at different absolute levels. Rebase to 100 at a defensible base date (e.g. Q1 2020 — pre-pandemic).
- **When it fails:** Cherry-picked base dates flatter or flatter the story; readers without finance literacy mis-read "100" as a price.
- **Fields version:** Three lines (Robina, Burleigh Waters, Varsity Lakes) + one ghost line (Greater Brisbane) for context, rebased to Q1 2020 = 100. Direct labelling at line end (no legend). Y-axis shows "100 = Q1 2020 value". One-sentence caption explains what indexing is. Annotate three real-world events (RBA cuts, Olympics announcement, etc.) with thin vertical guides.
- **FHFA / Case-Shiller methodology reference:** https://www.fhfa.gov/data/hpi

### 5.2 Distribution of sale prices (Distribution)
- **When to use:** Showing that "median" hides bimodal markets — a suburb with a lot of $900K units and a lot of $2.5M canal-front houses has the same median as one with everything at $1.4M.
- **When it fails:** Box plots without context look medical-school. Histograms with the wrong bin width create or destroy peaks.
- **Fields version:** **Half-violin + scatter** (Wilke 2019) — KDE shape on top, individual sale dots on bottom, median marked. One per suburb, small-multiples style. This is one of the wow moments — no Gold Coast operator currently shows distribution shape, only headline median.
- Reference: https://clauswilke.com/dataviz/boxplots-violins.html

### 5.3 Days-on-market trend + distribution (Change-over-Time + Distribution)
- **When to use:** Headline trend is a lie if the median masks a long tail of stale stock.
- **Fields version:** Twin chart — line of median DOM over 24 months (top), cumulative-curve distribution of currently-listed properties' DOM (bottom). The cumulative curve answers "what % of current stock has been listed >60 days?" which is the question buyers actually have.

### 5.4 Sale-to-list ratio / vendor discount (Deviation)
- **When to use:** Cleanest single signal of buyer-vs-seller power.
- **When it fails:** Auction sales distort it; off-market sales aren't captured.
- **Fields version:** Diverging bar from 100% baseline, one bar per suburb, last 90 days. Caption explicitly excludes auctions and notes sample size.

### 5.5 Auction clearance rate (Magnitude)
- **When to use:** Weekly leading indicator in auction-heavy markets.
- **When it fails:** Gold Coast clearance is volatile and small-N — a single-week reading is noise.
- **Fields version:** 4-week rolling mean as the line, weekly readings as light dots behind. Annotate the "noise band" so readers see what is and isn't a real move.

### 5.6 Stock on market (Magnitude)
- **Fields version:** Column chart of active listings by week, last 12 months, with seasonality band (10th-90th percentile of historical same-week values) shown as a grey ribbon behind. Reader can see at a glance "this is normal December" vs "this is unusual December."

### 5.7 Rental yield vs sale price (Correlation)
- **Fields version:** Scatter, one dot per recent let, log-x scale on price, linear y on yield. Trend line + confidence band. This is John Burns / CoreLogic territory but at suburb micro-level.

### 5.8 Price-to-income ratio (Correlation, with policy overlay)
- **Fields version:** Long-run line, Gold Coast vs national, rebased index. The honest version of "is housing affordable?" without saying so.

### 5.9 Interest rate / serviceability overlay (Change-over-Time)
- **Fields version:** Twin-axis (cardinal sin done carefully) — house price index left axis, RBA cash rate right axis, both rebased to Jan 2020. Or better: two separate small-multiple panels stacked, sharing x-axis. Cairo would prefer the latter.

### 5.10 Street-level price heatmap (Spatial)
- **When to use:** Suburb-level statistics hide street-level reality. A canal-front street in Burleigh Waters has nothing in common with the highway-side street.
- **When it fails:** Heatmaps with no individual sales shown look made-up; sparse-data areas mislead.
- **Fields version:** Choropleth at street-segment level (~20m resolution), single-hue sequential ramp, individual sale dots overlaid for transparency. Hatched areas where N<3 sales in 24mo. This is a Fields-only capability — nobody else has the cadastral + sales data joined.

### 5.11 Time-on-market cumulative curve (Distribution)
- **When to use:** "What's my realistic time-to-sell?" — the question every prospective vendor has.
- **Fields version:** Cumulative curve of sold-properties' days-to-sell, one line per suburb, last 12 months. Reader's eye picks out the median (50% line) and the long-tail point (e.g. "10% take longer than 180 days"). Captioned with the median + 90th percentile in plain text.

### 5.12 Comparable-sale scatter with confidence band (Correlation)
- **Fields version:** For each profiled suburb — scatter of recent sales (price y-axis, floor area x-axis), trend line + 90% confidence band (using the existing valuation-system 1.645×σ method). Individual transactions plotted as small dots. Reader can see "$2M for 250sqm is mid-band; $2.4M would be top edge." This is *the* visual that demonstrates Fields' valuation methodology.

### 5.13 Migration / demographic flows (Flow)
- **Fields version:** Sankey diagram — left side origins (Sydney, Melbourne, Brisbane, regional), right side destination Gold Coast suburbs. ABS data, prior-12-months. Caption: "Flows >50 persons only. Source: ABS Census 2021."

### 5.14 Construction approvals vs completions (Magnitude / change)
- **Fields version:** Paired columns by quarter, last 5 years. Annotate the gap (approved-but-not-completed pipeline) — relevant because supply hits the market 18-24 months after approval.

### 5.15 Bond data + vacancy rate (Change-over-Time)
- **Fields version:** Line chart of vacancy rate, with new-bond inflow as light columns behind. Single cleanest indicator of rental market direction.

### Universal chart rules (apply to every chart)

1. **Source line.** Every chart has a source, sample size, and date stamp. No exceptions.
2. **Sentence-case titles that state the conclusion.** "Burleigh Waters has moved further than Robina since 2022" — not "Median Price by Suburb."
3. **Direct labelling.** Legends only when labels would clutter beyond reading.
4. **Y-axis at zero for bar charts. Y-axis truncated allowed for line charts** (with a clear visual cue — a zigzag or note).
5. **No 3D, no shadows, no gradients.** Tufte's data-ink ratio: erase non-data ink ruthlessly.
6. **Sparklines in tables.** Every suburb table row gets a 24-month price sparkline in column 1. Tufte says ~160 sparklines fit per newspaper column — the same density makes a one-page suburb dashboard possible.
7. **Annotation > legend.** If you can write the insight on the chart itself, do.
8. **Single-hue sequential ramps for heat / choropleth. Diverging only for true mid-point data.**

---

## 6. Original visualisations (the WOW moments)

These are the 8 visualisations no other Gold Coast or Australian property report does. Each leverages a Fields-only data asset.

### 6.1 The Fields Index (proprietary headline)
A single composite indicator combining indexed price, DOM, sale-to-list, and stock change into one number, rebased to 100 at Jan 2020. Updated monthly, displayed as a giant numeral on the cover and a sparkline on every page. Same trick Knight Frank uses with PIRI 100, S&P with Case-Shiller, Bloomberg with their Indices. Once readers see it twice they start asking "what's the Fields Index doing?" — that's brand.

### 6.2 Property-level micro-suburb price paths
For each of the 3 core suburbs, a small-multiples panel showing the trajectory of every individual recently-sold property as a faint line, with the suburb median as a bold line on top. Reader sees the dispersion that the median hides. This is the "data journalism" version of the suburb price chart — and only possible because Fields has property-level resold data.

### 6.3 Comparable-sales scatter with confidence band
Per § 5.12 above. The visual demonstration of how the Fields valuation actually works. Shown twice in the report: once for the methodology section, once applied to a featured property.

### 6.4 Asking-vs-actual gap (per suburb, monthly)
Distribution of (sale price ÷ asking price) per suburb. Median line + 25/75 percentile band. Clearly shows "vendors in Robina are getting 98% of asking; in [other suburb] they're getting 91%". This data exists in the Fields DB, no public source publishes it at suburb level.

### 6.5 Days-to-sell distribution by listing month
Sold-properties chart — what month they listed in, how many days they took to sell. Reveals seasonality at sub-suburb level. Useful to vendors planning a campaign.

### 6.6 Home-improvement ROI by suburb
Where Fields' photo-classification + valuation pipeline meets editorial. For each suburb, a bar chart: "median uplift in valuation per renovation type" — kitchen, bathroom, landscaping, pool, extension. Even rough numbers from the existing dataset would be unique to Fields.

### 6.7 The "What's similar to your home?" interactive (web-only)
Reader enters address. Web version pulls their property's suburb + bedrooms + land size + closest comps and renders a personalised one-page chart pack. Inverts the report from "broadcast" to "addressed-to-you". This is the report's lead capture engine and the moat: every interaction enriches the dataset.

### 6.8 Flood-data honesty panel
For Burleigh Waters specifically — overlay map showing City Plan flood overlay vs ICA Insurance Probability Zones, with property dots coloured by both. Captioned plainly: many properties in the council overlay are not in any insurer zone. This is the Fields editorial value framework made visible: trade-offs are value, not flaws. No competitor will publish this because it's not a marketing message — and that's exactly why it's credibility.

### 6.9 The 12-month conviction tracker (running)
At the end of each quarterly edition: a small panel showing the previous quarter's predictions and what actually happened. Forecasters never do this. Doing it once builds permanent trust.

### 6.10 The "Gold Coast in three sentences" cover stat
A single front-cover paragraph that states the three most important data findings in plain English with exact numbers — e.g. *"In Q2 2026, Burleigh Waters median moved from $1,840,000 to $1,895,000 (+3.0%, n=42 sales). Days-on-market median stretched from 28 to 41 days. The vendor-to-list-price ratio held at 99.1%."* Cover communicates substance, not vibe.

---

## 7. Photography direction

Will's local photography is the report's single greatest non-data asset and must be deployed with restraint. **Rule: photography supports the data, never decorates it.** Knight Frank's Wealth Report uses photography sparingly — section openers, never page-fillers. Monocle uses photography to mark the *kind* of section you're entering.

### What to shoot

- **Suburb identity shots (3-5 per suburb):** A single quiet, observational frame that names the place — the lake at Varsity, the Tallebudgera Creek crossing, the canal mouths at Burleigh Waters, the Robina Town Centre rooftop pre-dawn. Not aerial drone tourism shots. Not golden-hour pools. Documentary, not promotional.
- **Built-form details:** Brick textures, fence treatments, roof pitches typical of each suburb. These earn their place when paired with a chart on stock composition or build-age.
- **Process shots:** Will at his desk, the database screen, a printed comp report on a kitchen table. Builds the personal-authority frame — *one person did this work*.
- **Never:** Stock real-estate imagery, smiling agents, "happy family" couples, twilight property exteriors, infinity pools.

### Captions

Every photo gets a caption. Treat captions as editorial: location, year shot, why this image accompanies this section. Captions sit in the marginalia column in 8pt italic sans.

### Placement rules

- **Section openers:** One half-page or full-bleed photograph, single-line caption, section title set in display serif beneath. Same template every time. Five section openers = five photographs total.
- **Cover:** Single image, treated more like a book-jacket than a magazine cover (see §8).
- **Inside-body:** Photograph only when it contains information the chart cannot — e.g. an architectural detail typical of a price tier.
- **Web edition:** Photographs become section-divider scrollytelling moments, with the photo briefly fixed and text scrolling over.

---

## 8. Cover design brief

The cover is the single most important page. It must communicate *substance, not vibe* before a reader opens it.

### What the cover does NOT do

- It does not show a smiling agent.
- It does not show a hero property.
- It does not use a price headline ($1.2M) — that is a marketing tactic and reads as such.
- It does not use the word "stunning", "premium", or "exclusive".
- It does not have a location stock-photo treatment.

### What the cover DOES do

- States its identity: **"Fields Gold Coast Market Report"** (display serif, restrained, large but not screaming).
- States its edition: **"Quarterly. Issue 01. Q[X] [YEAR]."** (small sans, like an academic journal masthead).
- States a single, exact, verifiable proprietary number — *the* Fields Index for the quarter — set in massive tabular numerals, dwarfing everything else: e.g. **`118.7`**.
- Beneath: the three-sentence cover stat from §6.10. Tiny, careful, exact.
- Footer: tagline ("Smarter with data") + URL + edition number. Like a hardcover book spine.
- One restrained visual element: either a single hero photograph (suburb identity, observational, treated like a Penguin Classics cover) OR a thumbnail-size sparkline of the Fields Index over 5 years. Not both.

### Cover paper (print)

300-350gsm uncoated matte cover stock. The hand feels the weight before the eye reads the cover. Luxury report design (Knight Frank, Christie's, Monocle special editions) consistently invests in cover stock — Royal Printers / Pagination / Canada Post research all confirm tactile cues drive trust scores, especially in older + higher-income demographics, which is precisely the seller market.

### Reference covers worth studying

- Penguin Classics drama series (single illustration, restrained typography)
- Knight Frank Wealth Report 2024-25 (https://www.knightfrank.com/site-assets/research/reports/the-wealth-report/previous-editions/the-wealth-report-2024.pdf)
- McKinsey Global Institute reports
- The Economist Special Reports
- Apollo magazine (art world — peer prestige register)
- *Avoid:* Anything with "luxury living" in the title.

---

## 9. Lead capture / conversion architecture

### The funnel

1. **Top of funnel:** Facebook ad / LinkedIn post / organic article mentions the report. Drives traffic to the **web edition**.
2. **Mid-funnel:** Web edition is **ungated for the first ~50% of content** then soft-gates the rest behind a single email field. Brixon 2025 data: delayed gating lifts conversion 35-45% over hard gates. One-field forms convert ~12-15% better than three-field forms.
3. **Email captured:** Triggers a 4-email nurture sequence — (1) instant PDF delivery, (2) two days later, audio version drops with a personal note from Will, (3) one week later, the personalised "your suburb" interactive, (4) two weeks later, soft-CTA to book a property analysis or to request the print edition by post.
4. **Print edition trigger:** Anyone who replies to email #4 with an address gets the print edition mailed. Cost contained, quality of lead is screened.
5. **Conversion:** The print edition's last page is a single, modest CTA: *"If you'd like a personal analysis of your home, reply to this email or scan this QR code."* No "call me now". No "limited spots". No urgency theatre.

### Embedded CTAs in the report

- **Frequency:** ~1 every 8-10 pages. Never mid-chart, never mid-section. Always at section breaks.
- **Language:** "If you want to test this on your own home, [link]." / "Curious how your suburb compares? [link]." Information-gap CTAs, not advice-CTAs. Aligned with editorial rule: no "you should sell."
- **Footer / sidebar persistence:** Web edition has a small persistent sidebar — "Q[X] [YEAR] Edition. Get next quarter delivered. [email field]." PDF has a one-line footer on every page: "Next edition mailed [DATE]. fieldsestate.com.au/report"

### Audio version

- Hosted on the report page + pushed to Spotify / Apple Podcasts as the "Fields Quarterly" feed.
- 20-25 minutes. Not a verbatim reading — a compressed summary with Will's voice and live numbers. This becomes evergreen distribution.
- Each episode ends with one soft CTA — "if your suburb wasn't covered in detail this quarter, comment with where you live and we'll prioritise it next edition." Generates engagement signals + addresses the next-quarter editorial brief simultaneously.

### Social cuts

- Each chart auto-exports to (a) 1080×1080 Instagram square, (b) 1080×1920 Reels/Stories vertical, (c) 1200×627 LinkedIn horizontal. All branded consistently.
- Each cut links to the web edition with `?utm_source=fb&utm_medium=chart&utm_campaign=q2_2026` etc. Tracked per-chart.

### Conversion benchmarks to target

- Web edition → email: aim 4-6% on cold traffic (financial-services landing-page average is 2-3%, soft-gating + value density should beat that).
- Email → print edition request: aim 8-12% of subscribers on first cycle.
- Print edition → consultation booking: aim 5-10%. With 100 print copies that's 5-10 qualified seller conversations per quarter — at any pre-revenue stage that's the ballgame.

---

## 10. Production checklist

### Tooling — recommendation: **Quarto + Typst**

Three options on the table. Verdict: **Quarto with Typst output** for the data-driven flagship report; InDesign reserved only for the print edition's final flourish if a designer is contracted.

| Tool | Pros | Cons | Verdict |
|---|---|---|---|
| **Adobe InDesign** | Industry standard, complete typographic control, designer-friendly | Manual chart placement, no data binding, requires a designer's hourly rate quarterly, file lock-in | Use only if budget allows a contracted designer for cover + section openers |
| **Figma** | Easy collaboration, web-native, good for prototyping web edition | Not a long-form typesetting tool, no data binding, weak for 30+ page documents | Use for web edition mocks only |
| **Quarto + Typst** | Markdown source, charts rendered live from Python/R against the database, Typst gives near-InDesign typography quality at minutes-to-render speeds, version-controlled in git, free | Steeper learning curve than Word; custom templates take initial investment | **Recommended primary.** When the next quarter's data lands, the report regenerates. |
| **LaTeX** | Mature, every typographic option | Slow renders, hostile syntax, dated visual defaults | Skip. Typst is what LaTeX should have become. |

Posit added Typst support to Quarto in 1.4 (2024). The combination produces print-grade PDFs, supports custom templates matching the spec in §4, and — critically — lets the report be a living artefact: rebuild it nightly as data updates.

### File specifications

- **Trim size:** A4 (210×297mm) for print; same proportions for screen PDF.
- **Resolution:** 300dpi for print images, sRGB → CMYK conversion at export.
- **Bleed:** 3mm on print edition.
- **Fonts:** Embed all (Tiempos family + Söhne or Inter). License Tiempos via Klim direct purchase ($300-500 one-off for a small business); Inter is free.
- **PDF/X-1a:2001** for print edition export. Standard PDF for web download.
- **File size target:** Under 8MB for the web-downloadable PDF (compressed images, subset fonts). Print-quality version separate, 30-60MB.

### Print specifications (when ordered)

- **Paper:** 120-150gsm uncoated matte text stock; 300-350gsm uncoated matte cover stock. Colorplan, Munken Pure, or Mohawk Superfine if budget allows; a standard premium offset uncoated otherwise.
- **Binding:** Saddle-stitched up to 32 pages; perfect-bound from 36+ pages. Saddle stitch costs less and lies flatter.
- **Print run:** Start at 100 copies (under $15/copy at most Australian printers — Pagination, Currie Group, or local Gold Coast trade printers). Scale to 200-300 only if the first cycle generates demand.
- **Distribution:** Australia Post Express Parcel for high-value leads (the box is part of the experience); standard satchel for general subscribers.

### Pre-publication checklist

- [ ] Every chart has source + N + date in caption
- [ ] Every "fact" claim is sourced in appendix
- [ ] No forbidden words (stunning, nestled, boasting, rare opportunity, robust market) — search-and-find pass
- [ ] No advice language (you should, consider, now is a good time) — manual editorial pass
- [ ] No predictive language (will, going to) — replaced with conditional ("if X holds, indicators suggest Y")
- [ ] All numbers in `$1,250,000` format, no abbreviations
- [ ] All suburbs capitalised
- [ ] Last-quarter conviction tracker reconciled
- [ ] Methodology box visible on every spread
- [ ] Editor's letter signed by Will, dated, with email
- [ ] Appendix sample sizes match body chart captions
- [ ] Two independent reads (Will + one external) with red-pen pass
- [ ] PDF accessibility checked (alt text on charts, tagged headings)
- [ ] Web edition Lighthouse score > 90 on mobile
- [ ] Audio edition has accurate transcript
- [ ] All UTM parameters set on outbound links
- [ ] Print proofs reviewed under daylight + tungsten before press run

---

## Top-line summary (3 sentences)

The Fields Market Report should look and read like a piece of data journalism produced by a one-person research desk — restrained Tiempos serif on cream uncoated paper, FT Visual Vocabulary chart discipline, every figure sourced and N-stamped, a single proprietary "Fields Index" headline number, and roughly 32 pages of original suburb-level visualisations no other Gold Coast operator can produce because no one else has joined cadastral, sales, photo, and valuation data. Format should be a tiered hybrid: free ungated web edition first (soft email-gate at the 50% mark), email-gated PDF, mailed print edition for qualified seller leads only, plus a 20-25 minute audio episode and per-chart social cuts — funnelling cold traffic into qualified consultation conversations at a target ~5-10 per print cycle. Build it in Quarto + Typst against the live database so each quarterly edition regenerates from updated data rather than being manually re-typeset, and use Will's local photography only at section openers — observational, never promotional — to mark place and personal accountability without slipping into real-estate marketing register.
