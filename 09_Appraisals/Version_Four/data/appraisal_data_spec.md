# Appraisal Report — Data Spec

**Purpose:** Catalogue every concrete data point in the V4 appraisal report (`preview.html`), map each one to its source, and define the contract between the data pipeline and the report template.

**Source document:** `09_Appraisals/Version_Four/preview.html` (19 pages, hand-coded for 13 Terrace Court, Merrimac).

**Date:** 2026-05-12

---

## Categorisation legend

Every data point in the report falls into one of six categories:

| Code | Meaning | Example |
|------|---------|---------|
| **P** | Property-specific — varies per property | Address, recommended list price, comp set |
| **S** | Suburb / catchment-specific — varies per suburb cluster (POA 4220+4226+4227 etc.) | Catchment household count, cohort median price, top-decile income |
| **U** | Universal — identical across all reports | Fields tagline, Roy Morgan 5% trust stat, six-forces structure |
| **C** | Computed — derived from other data | $85,000–$135,000 gap between list and target |
| **A** | AI-generated — produced by the AI editorial system | Persona narratives, property-specific advantage prose |
| **H** | Human-supplied — Will's judgement or seller-supplied | Target sale price, willingness-to-pay bands, "Prepared for {name}" |

## Source key

| Source | Description |
|--------|-------------|
| `Gold_Coast.{suburb}` | Cosmos property collection (e.g. `Gold_Coast.robina`, `Gold_Coast.merrimac`) |
| `property_data.properties_for_sale` | Enriched property document with `valuation_data` |
| `Fields valuation engine` | Output of `precompute_valuations.py` — comp set, adjustments, reconciled range, confidence |
| `system_monitor.valuation_accuracy` | Most recent backtest results (MAE) |
| `system_monitor.precomputed_market_charts` | Cohort medians, lifts, n-counts by bedroom band |
| `system_monitor.precomputed_indexed_prices` | Suburb price indexes |
| `ABS Census 2021 GCP` | Persisted in `09_Appraisals/Version_Four/data/abs_census_2021/` |
| `ai_analysis` | Field on property document (output of `generate_property_ai_analysis.py`) |
| `constants` | Static report content (tagline, philosophy lines, six-force descriptions) |

---

## Page-by-page data inventory

### Page 1 — Outer Cover

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Cover hero image | P | Photography (Will or property pages) | High-res landscape; design needs aspect ratio defined |
| Address (line breaks) | P | `Gold_Coast.{suburb}.address` | "13 Terrace Court" — multi-line styling |
| Suburb + state + postcode | P | `Gold_Coast.{suburb}` | "MERRIMAC, QLD 4226" |
| Doc title | U | constants | "Property Positioning Report" |
| "Prepared for {name}" | H | Seller intake form | "Prepared for Dee" |
| URL | U | constants | "fieldsestate.com.au" |
| Date | C | `datetime.now()` | "MAY 2026" |
| Fields logo + tagline | U | constants + asset | "Smarter with data" |

### Page 2 — Inside Front Cover

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Philosophy lines (2) | U | constants | "The question is not only what the home is worth…" |
| "Prepared for {name}" | H | Seller intake | "Dee" |
| Address (full) | P | `Gold_Coast.{suburb}` | "13 Terrace Court / Merrimac, QLD 4226" |
| Date | C | `datetime.now()` | "May 2026" |

### Page 3 — Opening Thesis (Six Forces)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Eyebrow with address + suburb | P | `Gold_Coast.{suburb}` | "For 13 Terrace Court · Merrimac" |
| Six-forces headline + lead | U | constants | Identical across reports |
| Six force labels + descriptions | U | constants | Scarcity / Buyer fit / Valuation / Campaign reach / Presentation / Trust |
| Thesis-close line | U | constants | "Together, they form the sale strategy…" |

### Pages 4–5 — Section 01 (Scarcity) — currently locked PNGs

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Page 4: locked_p01.png | P+A | Section 01 left page — scarcity thesis with property-specific attribute count | Currently rendered from V3 as flattened PNG; needs un-flattening into HTML for templating |
| Page 5: locked_p02.png | P+A | "1 of only 4" stat + annotated satellite | Includes property-specific scarcity calc (how many similar homes exist in catchment) and the V2-style satellite image |
| **Scarcity stat** ("1 of only 4") | C | Computed from `Gold_Coast.{suburb}` cohort | Needs query: count of homes in suburb matching subject's feature set |
| **Annotated satellite image** | P | Generated separately | V2 annotation style — currently a static PNG. To templatise, needs an image-generation pipeline or hand-built per property |
| Fields Advantage 01 prose | A | AI editorial system | Property-specific scarcity narrative |

**Note:** These pages are the biggest unknown for productionising. The scarcity claim ("1 of only 4 homes with X, Y, Z") requires a per-property feature-match query. The satellite image needs production tooling. **For Phase 2, we'll likely rebuild these as HTML pages with dynamic data.**

### Page 6 — Section 02 LEFT (Buyer thesis)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Spread number "02" | U | constants | |
| Headline "The right buyer pays the premium" | U | constants | |
| Body paragraphs (3) | U | constants | |
| Thesis-close | A+P | AI or template | "For 13 Terrace Court, three buyers carry the price." — number of personas may vary |

### Page 7 — Section 02 RIGHT (Buyer personas)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline + subhead | U | constants | |
| **Per-persona (×3):** rank, share %, name, demographics line | A+P | AI editorial agent | Generated per property based on subject features + catchment |
| **Per-persona evidence line** | A+S | AI + catchment data | Cites ABS Census or feature-match logic |
| **Match bars (5 attributes × 5 dots)** | C | Computed per persona | Maps subject features → persona-relative fit |
| **Willingness-to-pay range** | H+A | Will + AI | Currently hand-set; could be computed from cohort + persona weighting |
| Anti-fit line | A+P | AI | "Not for this home: investors, first-home buyers, new-build seekers" — varies by property |
| Source-line | S+U | constants + dates | ABS table refs, Fields backtest counts, today's date |
| Fields Advantage 02 prose | A | AI editorial | References cohort transaction count (P) and qualified resident count (S) |

**Key data inputs:**
- Catchment household counts (S): `abs_census_2021_catchment.md`
- Top-tier income thresholds (S): same source
- Subject feature set (P): `Gold_Coast.{suburb}` — bedrooms, dual-living, pool, etc.
- Persona definitions (currently 3 fixed types): could be a constants file with conditional inclusion

### Page 8 — Section 03 LEFT (Valuation thesis)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Spread number "03" | U | constants | |
| Headline | U | constants | "Valuation — The single most important factor…" |
| Subhead "The valuation is the foundation." | U | constants | |
| Body paragraphs (3) | U | constants | |
| Thesis-close | U | constants | "For 13 Terrace Court, that foundation is derived on the next page." — needs address substitution |

### Page 9 — Section 03 RIGHT (Valuation evidence)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline with range | P | Fields valuation engine | "$1.85M – $2.05M. The range, derived." |
| **Cohort anchor — 4bd median + n** | S | `precomputed_market_charts` or cohort query | "median $1,400,000 (n=698)" |
| **Cohort anchor — 6bd median + n** | S+P | cohort query filtered by subject bedrooms | "median $1,909,000 (n=54)" |
| **Raw lift %** | C | Computed from above | "+36% raw lift" |
| **Evidence stack (6 rows)** | P+S | Fields valuation engine per-attribute | Subject's attributes + signal strength dots + cohort n |
| **Synthesis: derived range** | P | Fields valuation engine | "$1.85M – $2.05M, midpoint $1.95M, 90% CI" |
| Method-note | U | constants | |
| Confidence-row | P | Fields valuation engine | "n=142 comparable transactions… confidence: high" |
| Source-line | S+U | Fields engine output | Cohort POA, sold transaction count, today's date |
| Fields Advantage 03 prose | A+S | AI + cohort | Cites cohort transaction count (varies by suburb cluster) |

### Page 10 — Section 03 RECEIPTS (Comp-by-comp)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline + subhead with range | P | Fields valuation engine | |
| **Per-comp card (×2 shown, ×7 total in cohort):** | P | Fields valuation engine | |
| · Comp number + address | P | comp record | "Comp 01 / 5 Straite Drive, Robina" |
| · Sold price + distance | P | comp record | "$1,950,000 · 4.25 km" |
| · Adjustment rows (6 typical) | P | adjustment engine | floor area, land area, beds, baths, dual-living, etc. with ±$ |
| · Adjusted estimate | P | computed | "$2,028,000" |
| · Weight % | P | weighting algorithm | "Weight 28%" |
| **Cohort summary line** | P | computed | "Two comps shown… five additional… remaining 50%" |
| **MAE stat callout** | U | `system_monitor.valuation_accuracy` | "11.4% MAE vs Domain's 15.0%" |

### Page 11 — Pricing Recommendation

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline with address | P | `Gold_Coast.{suburb}` | "Our recommendation for 13 Terrace Court" |
| **Recommended listing price** | H+C | Will's judgement + protocol | "$1,915,000" — derived from valuation range with precise-pricing protocol |
| · Rationale line | A+H | template fill-in | Notes about portal bracket, round-number positioning |
| **Target sale price (range)** | H+C | Will's judgement | "$2,000,000 – $2,050,000" |
| · Rationale line | A+H | template | "Upper end of derived range, reached through buyer competition" |
| **Strategy body paragraph** | C+H | template fill-in | Includes gap calculation, derived range reference |
| Four conditions checklist | U+C | constants + computed | Three universal labels, one verifies subject (condition / editorial / photography presence) |
| **Inspection caveat note** | U | constants | "Subject to physical inspection by Will Simpson…" — universal but references cohort count (P/S) |
| Thesis-close | U | constants | "The strategy is engineered. The next step is yours." |

### Page 12 — Section 04 LEFT (Campaign thesis)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Spread number "04" | U | constants | |
| Headline | U | constants | "Premium pricing requires reaching the buyer who isn't currently searching." |
| Body paragraphs (3) | U+P | constants + substitution | Last paragraph mentions "For 13 Terrace Court, Fields targets the buyer avatars from Section 02…" |
| Competition callout | U | constants | "Premium prices come from competition between two or more passionate buyers…" |
| Thesis-close | U | constants | "Portals capture demand that already exists. Fields creates and redirects demand." |

### Page 13 — Section 04 RIGHT (Three buyer modes)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline | U | constants | "Active buyers find listings. Passive buyers we find for you." |
| Three mode cards (active / passive / retargeting) | U | constants | Channel lists are universal |
| **28-day campaign model figures** | U+C | constants (range-based) | 40,000–60,000 impressions, 75–120 engagements, 35–50 inspections — universal modelled targets |
| Source-line | U+S | constants | ABS Census catchment, campaign window |
| Fields Advantage 04 prose | U | constants | Now standardised wording |

### Page 14 — Section 05 LEFT (Presentation thesis)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Spread number "05" | U | constants | |
| Headline + body | U | constants | "Buyers feel the home before they value it" + 3 paragraphs |
| Thesis-close | P | template | "For 13 Terrace Court, the presentation strategy is built around that moment." |

### Page 15 — Section 05 RIGHT (Image comparison + levers)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline + subhead | U | constants | |
| **Image comparison (×2)** | P | Photography | One standard, one twilight — paired from same room |
| · Captions | U | constants | |
| **+118% photography stat** | U | `Before You List Ch. 4` constant | |
| **Three levers (story / imagery / buyer emphasis)** | A+P | AI editorial | Property-specific copy in "sample" callouts; persona lines map to Section 02 personas |
| Fields Advantage 05 prose | U | constants | |

### Page 16 — Section 06 LEFT (Trust thesis)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Spread number "06" | U | constants | |
| Headline + subhead | U | constants | "Buyers discount what they cannot verify." / "Transparency builds confidence…" |
| Body paragraphs (3) | U | constants | |
| **5% trust stat** | U | Roy Morgan Image of Professions | Universal Australian-wide data |
| Thesis-close | U | constants | "Reducing the asymmetry is the work." |

### Page 17 — Section 06 RIGHT (Trust applied)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline + subhead | U | constants | |
| Three trust cards (price traceable / trade-offs named / method open) | U+P | template | Card 02 has property-specific trade-off prose ("13 Terrace Court has scale, privacy, bushland boundary — but is not new-build…") |
| **+9.6% trust premium stat** | U | `Before You List Ch. 6` constant | |
| Fields Advantage 06 prose | U | constants | |

### Page 18 — Recommendation (Synthesis)

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline + subhead | P | template | "Our recommendation for 13 Terrace Court" / "Six forces, one strategy, one specific recommendation." |
| Synthesis paragraph | A+P | AI editorial | References six forces, premium buyer, cohort data |
| **List price** | H+C | Will + protocol | Matches page 11 |
| **Target sale price (range)** | H+C | Will | Matches page 11 |
| **Campaign duration (range)** | U | constants | 25–45 days (standardised range) |
| **Estimated inspections (range)** | U | constants | 30–45 (standardised range) |
| Thesis-close | U | constants | "The strategy is engineered. The next step is yours." |

### Page 19 — The Plan + Next Steps

| Field | Cat. | Source | Notes |
|-------|------|--------|-------|
| Headline | U | constants | "From strategy to the right buyer." |
| Subhead | U | constants | "The campaign, and the three steps that begin it." |
| **Campaign sequence (5 phases × 3 fields each)** | U | constants | All phases are universal blueprint copy |
| **Three next steps (×3)** | U | constants | Walk-through / Agency agreement / Pre-launch |
| **Will's note + signature** | U+H | constants + signature | "This report was built for {address} and for {seller_name}…" |
| Contact block | U | constants | Will Simpson · Fields Estate · email · URL |

---

## Summary — Data sources needed for any appraisal

To produce one report for any property, the production pipeline needs:

### From `Gold_Coast.{suburb}` (property record)

- Address (with line breaks for cover)
- Suburb / state / postcode
- Bedrooms / bathrooms / car spaces / floor area / land area
- Feature flags: pool, dual-living, cul-de-sac, bushland boundary, outlook, condition rating
- Property photography URLs (cover + interior + twilight versions)

### From Fields valuation engine

- Reconciled valuation range (low / midpoint / high)
- Cohort metadata: total cohort n, POA list, transaction date range
- Comp set (top 7-10 with adjustments):
  - For each: address, sold price, distance, ±$ adjustments per attribute, adjusted estimate, weight %
- Per-attribute evidence strength (1–5 scale) + cohort n for each attribute
- Confidence level (high / medium / low)

### From `system_monitor.valuation_accuracy`

- Most recent Fields MAE
- Comparison MAE (currently Domain at 15.0%)

### From `system_monitor.precomputed_market_charts`

- Subject-bedroom-band cohort median + n
- 4-bedroom baseline cohort median + n (for the "+36% lift" anchor)

### From ABS Census 2021 GCP (persisted)

- Catchment household counts (by POA)
- Owned-outright dwellings count
- Top-decile / top-quintile household income thresholds + counts
- 50–65 age cohort count

### From AI editorial system (`ai_analysis` field)

- Persona narratives (×3 personas) — name, demographics line, evidence line
- Anti-fit line
- Scarcity claim ("1 of only 4")
- Property-specific Fields Advantage prose (sections 01, 02, 03)
- Property-specific lever copy (story, imagery, buyer-emphasis samples)
- Trade-offs paragraph for trust card 02
- Synthesis paragraph for page 18

### From human input (seller intake)

- Seller name (for "Prepared for {name}")
- Recommended listing price (Will's judgement, post-inspection)
- Target sale price range (Will's judgement)
- Willingness-to-pay ranges per persona (Will's judgement)

### Universal constants (one constants file)

- Tagline, philosophy lines, six-forces structure
- All section thesis copy (headlines, body paragraphs, thesis-close lines)
- Stat references (Roy Morgan 5%, +118%, +9.6%, +36%)
- Campaign sequence blueprint
- Three next steps
- Fields Advantage standardised copy (sections 04, 05, 06)
- Will's note + contact block

---

## Open questions for Phase 2 build

1. **Locked pages 4–5 (Section 01 — Scarcity).** Currently flattened PNGs from V3. To templatise, we need to rebuild these as HTML with dynamic data: the "1 of only 4" stat (computed from cohort feature-match) and the annotated satellite image. **Decision needed: rebuild these as HTML pages now, or accept that they require a designer pass first?**

2. **Persona generation.** Three personas with shares of 35% / 30% / 20% (anti-fit 15%) are currently hand-set for 13 Terrace Court. For any property, we need either: (a) a rules engine that picks 2–4 personas from a fixed catalogue based on subject features, or (b) an AI agent that proposes the personas + shares. **Recommendation: build (a) first with a catalogue of 6–8 persona archetypes, with AI generating only the property-specific narrative within each.**

3. **Match bars (5 dots × 5 attributes per persona).** Currently hand-set. For any property, these should be computed by mapping persona feature priorities against subject features. **Needs:** a persona-attribute weighting matrix (each persona scores 0–5 on each attribute) and subject feature flags.

4. **Willingness-to-pay bands.** Currently hand-set per persona. Could be computed from cohort-derived range + persona-specific lift factor (e.g. multi-gen +5%, downsizer median, relocator -3%). **Worth deciding: hand-set per property, or computed?**

5. **Twilight photography.** Page 15 requires a paired (standard vs twilight) photo. For properties without twilight photography, we'd need a stand-in (existing photo with editorial caption) or to skip the comparison. **Decision needed.**

6. **The image comparison page (15)** — this might be reframed in V5 design. Hold off on automating until V5 lands.

7. **AI editorial system extension.** The current `generate_property_ai_analysis.py` produces the property page editorial. The appraisal needs additional content: persona narratives, scarcity claim, anti-fit line, trade-offs prose. **Needs a new AI agent or pipeline extension.**

---

## File this spec produces (Phase 2 deliverable)

`appraisal_data.json` — one JSON document per property containing every field listed above, in a structure that the V5 HTML template can consume. Schema and example to be designed in the data-pull script (next task).
