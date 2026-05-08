# P04 — How This Report Was Built

A single page. The methodology in plain language, with counts. The reader who cares can read it; the reader who does not can skip it knowing it is here.

---

## Layout

- One page, single column, generous margins.
- Section title in the brand serif (32pt): **How This Report Was Built**.
- Six short sub-sections, each with a heading and 2-4 sentences.
- A small data block at the bottom showing the counts that anchor the report.
- Footer: "Smarter with data" + page number.

---

## Body (draft)

### What we did

Across approximately forty hours of analysis, we processed every photograph, the floor plan, the satellite tile, and the street-view frame for 13 Terrace Court; computed proximity to twenty-three named points of interest within a 1.5 km walking radius; and matched the property against forty-six Merrimac sales (last 24 months) plus 142 currently active listings across Merrimac, Robina, and Varsity Lakes. The output is the data inventory that drives every recommendation in this report.

### Where the data came from

| Source | What we used it for |
|---|---|
| Domain.com.au + realestate.com.au listing scrape (nightly) | Active listings, asking prices, listing copy, listing photographs, floor plans |
| Cotality / Domain transaction records | Sold-cohort prices, dates, attributes |
| Fields satellite imagery (Google Earth Engine) | Orientation, neighbour proximity, tree canopy, pool envelope, bushland boundary |
| Fields photo-analysis pipeline (GPT-4V multimodal) | Room condition scoring, materials catalogue, dated-vs-renovated assessment |
| Fields floor-plan extraction pipeline | Room dimensions, layout flow, dual-living configuration |
| Fields POI dataset | Walking-distance proximity to named schools, parks, cafes, supermarkets, transport |
| Fields buyer-engagement telemetry (PostHog) | Decision-feed visitor counts, article reads, persona signals |
| Australian Bureau of Statistics (2026) | Demographic micro-data, income bands, household composition |

### How we computed the valuation

Six comparable sales drawn from Merrimac's last 18 months. Each comparable line-item-adjusted to 13 Terrace Court using suburb-specific adjustment rates derived from the 46-sale local cohort. The reconciled value is a weighted mean of the six adjusted comparables (weighted by recency, proximity, and condition-confidence). The 90% confidence interval is computed as `1.645 × weighted_std_dev`. Confidence level (Medium-High) reflects the agreement among the six comparables. Full working is shown on Spread 07.

### How we sized the buyer pool

Realestate.com.au and Domain.com.au monthly search-volume data for the suburb-and-bracket combination, supplemented by Fields ecosystem engagement telemetry from the last 90 days. Persona-share estimates are derived from observed buyer flow at Fields-hosted open homes and demographic micro-data from the ABS 2026 census release. Estimated qualified-and-active buyers in the next 30 days: ~380. Full working on Spread 04.

### What we deliberately did not model

- **Interior smells, recent build defects, neighbour disputes** — not visible to remote analysis. An in-person inspection by Will is the standard next step.
- **Buyer financing position** — known only at the offer stage. Spread 09 explains how we read offers as they come in.
- **Macroeconomic shocks** — RBA decisions, employment shocks, regulatory changes are flagged in the daily campaign briefing but cannot be priced in advance.
- **Seller circumstances** — the recommendations on listing month and method are made independently of the seller's personal timeline. Both will be reconciled with your circumstances in conversation.

### What you can audit

Every claim in this report can be traced back to one of three places: a comparable sale in our `Gold_Coast.merrimac` collection, a metric in `system_monitor.precomputed_market_charts`, or a citation to a published study. If a sentence cannot be traced, it does not appear. If you find a claim that does not stand up, write to Will and we will fix it and reissue the report.

---

## Counts at a glance (anchor block)

| | |
|---|---|
| Hours of analysis on this report | ~40 |
| Floor plan rooms identified and dimensioned | 16 |
| Photographs analysed | 47 |
| Distinct data points captured | 1,247 |
| Comparable sales used in the valuation | 6 |
| Merrimac sales drawn from for adjustment rates | 46 |
| Active southern-Gold-Coast listings cross-referenced | 142 |
| Studies cited | 14 academic papers, 60+ industry sources |
| Pipeline runs that fed this report | 30 nightly cycles |

---

## Editorial rules

- **No corporate qualifiers.** Not "comprehensive," "extensive," "robust." Specific numbers or no number.
- **The audit invitation is repeated here.** "If you find a claim that does not stand up, write to Will and we will fix it and reissue the report." Third repetition of the offer.
- **What we did not model is part of the methodology.** Naming the limits of the analysis is what makes the analysis itself credible. Pratfall effect at work.

---

## What changed in V2

V1 had a methodology page in the same slot ([02_report_blueprint.md, P4](../../02_report_blueprint.md)). V2 expands the data-source table and the "what we deliberately did not model" section, both of which load the trust signal harder for the spread-by-spread audit trail that follows. The counts-at-a-glance block is new — it sits at the bottom of the page so the skim-reader leaves with the order-of-magnitude in their head.
