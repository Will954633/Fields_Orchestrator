# Content Modules — The Building Blocks

This document defines every reusable content block the Fields Appraisal Report can compose. Each module names: (a) what it asserts, (b) what data it needs, (c) where the data lives, (d) the editorial template for rendering, (e) when to include / when to omit.

A module is included in a report only if its data inputs exist *and* its assertion serves one of the three reader sub-questions (Truth / Competence / Care, see `00_strategy.md` §2).

---

## How to read this document

Each module has the following fields:

```
### M{N} · Module name
**Asserts:** what the seller learns by reading this.
**Inputs:** named data fields from our pipeline.
**Source:** which collection / script.
**Voice:** the editorial register for this module.
**Length:** target word/element count.
**Where it appears:** page references in the blueprint.
**Skip when:** explicit conditions for omission.
**Template:** prose template with substitution variables.
```

---

# Section A — TRUTH modules (analytical core)

### M1 · The Verdict
**Asserts:** "Based on N adjusted comparable sales, your home's most-likely selling range is $X–$Y."
**Inputs:** `valuation_data.summary.selling_range_low/high`, `valuation_data.metadata.comparable_count`, top 3 comparables, primary value drivers (top 3 from `value_equations`).
**Source:** `precompute_valuations.py` → `properties_for_sale.valuation_data`.
**Voice:** declarative, numerical, structural ("Based on", "ranging from", "supported by").
**Length:** 90–110 words.
**Where it appears:** page 2 (Digital), page 6 (Print).
**Skip when:** never — this is the core verdict and is mandatory.
**Template:**
> Based on {{N}} adjusted comparable sales — {{comp1.address}}, {{comp2.address}}{% if comp3 %}, and {{comp3.address}}{% endif %} — ranging from ${{adj_low}} to ${{adj_high}}, we estimate a most-likely selling range of ${{range_low}} to ${{range_high}}, with a recommended listing range of ${{list_low}} to ${{list_high}}, subject to property analyst inspection. The primary value drivers are {{driver_1}}, {{driver_2}}, and {{driver_3}}.

**Editorial rule:** must lead with "Based on N adjusted comparable sales". Must name at least 2 comparable addresses. Must end with a sentence naming the top 3 drivers.

---

### M2 · The Specs Pills
**Asserts:** the home's measurable shape, in one glance.
**Inputs:** bedroom_count, bathroom_count, land_area_sqm, internal_floor_area_sqm, condition_score, has_pool, has_dual_living.
**Source:** `Gold_Coast.<suburb>` document.
**Voice:** cardinal numbers + units.
**Length:** 5–7 pills.
**Where it appears:** page 2 (Digital), page 6 (Print).
**Skip when:** never.
**Template:**
> {{bd}}bd{% if has_study %} + Study{% endif %}  ·  {{ba}}ba  ·  {{land_sqm}} m²  ·  {{floor_sqm}} m² internal  ·  {{condition_score}}/10 condition{% if has_pool %}  ·  Pool{% endif %}{% if has_dual_living %}  ·  Dual Living{% endif %}

---

### M3 · The Comparable Card
**Asserts:** "This sold property, adjusted, supports the valuation range above."
**Inputs:** comparable address, sale date, sale price, specs, line-item adjustments to subject, time adjustment, adjusted-to-subject value.
**Source:** `valuation_data.comparables[i]`.
**Voice:** forensic. Every adjustment named and signed.
**Length:** 1 card per comparable. Adjustments shown as a 2-column table.
**Where it appears:** page 3 (Digital, 3 cards), page 8–9 (Print, 5–7 cards as small multiples).
**Skip when:** never if comp count ≥ 3.
**Required line items:** land_area, internal_floor, bedrooms, bathrooms, car_spaces, condition, renovation_level, view, school_catchment_delta, time_adj_to_today.
**Adjustment naming rule:** every line item must include the *direction in plain language*. Not "+$57,375" but "Land area +153 m² → +$57,375". The seller should be able to see *why* an adjustment exists without reading the methodology.

---

### M4 · The Comparable-Adjusted Valuation Banner
**Asserts:** the numerical answer, with confidence band.
**Inputs:** range_low, range_high, list_low, list_high, confidence_level, adjustment_count.
**Source:** `valuation_data.summary`.
**Voice:** quiet, confident, restrained.
**Length:** 2 figures, 1 disclaimer line, 1 footer.
**Where it appears:** page 3 (Digital), page 8 (Print).
**Layout:** two pill-shapes side by side, *Most Likely Selling Range* and *Recommended Listing Range*. Confidence as a small badge.
**Footer rule:** "Adjustment rates derived from {{N_suburb_sales}} sold properties in {{suburb}}." This is the trust statement that justifies the figure above.

---

### M5 · The Honest Assessment Panel
**Asserts:** "We name what works against your property, before what works for it. And then we explain why the trade-off works."
**Inputs:** value_equations array (5–7 entries each with title, body, reframe, polarity).
**Source:** `generate_appraisal_report.py` editorial agent output.
**Voice:** plainspoken, dollar-quantified, concluding-sentence reframe in bold.
**Length:** 6–7 panels. Each panel: 50–80 word body + 15–25 word bold reframe.
**Where it appears:** page 5 (Digital), page 10–11 (Print).
**Skip when:** never. This is the page that earns trust.

**Editorial template per panel:**
> **{{feature_title}}: {{measurement}}**
> {{comp_a.address}} sold on {{comp_a.measurement}} and {{comp_b.address}} on {{comp_b.measurement}}. At ${{rate_per_unit}}/{{unit}} in {{suburb}}, that's ${{adj_low}}–${{adj_high}} less {{factor}} value. But the {{compensating_feature}} on this property — {{compensating_detail}} — would cost ${{cost_low}}–${{cost_high}} to replicate.
> **{{bold_reframe_sentence}}**

**Polarity rule:** at least 2 of the 6–7 panels must lead with a *trade-off* (downward adjustment). Panels that are all positive read as marketing.

---

### M6 · Limits of Our Evidence (NEW vs v2)
**Asserts:** "Here is what we did not see, and how it might change the answer."
**Inputs:** static text + dynamic estimates of how each unseen factor moves the range.
**Source:** new section to add to editorial prompt.
**Voice:** vulnerability + competence.
**Length:** 4 bullets + 2 sentences of context.
**Where it appears:** page 11 of Print only (not Digital — too candid for the unread-skim layer).
**Skip when:** can be omitted on the directional-only edition.
**Template:**
> **What we did not see, and how it might move the range.**
> - **Interior condition** — our score is from photos. An in-person inspection that finds {{condition_minus_signal}} would lower the range by {{X}}–{{Y}}%.
> - **Recent build defects** — we have no record of repairs to roof / waterproofing / structural elements. A pest-and-building report finding issues would change the range materially.
> - **Neighbour disputes / fence lines** — not visible from our data.
> - **Body corporate / strata health** (units only) — we read the most recent strata search if available; we did not. The next page lists what we *did* check.
> The first two are why we always recommend our property analyst inspection before signing.

---

### M7 · Property Through Our Eyes (Room Cards)
**Asserts:** "We have looked carefully at every room. Here is what we saw."
**Inputs:** 6 room cards — Overall Condition, Kitchen, Exterior, Main Bathroom, Outdoor & Pool, Notable Features. Each with `/10 score`, 1-sentence material list.
**Source:** `property_valuation_data.condition_summary` + `floor_plan_analysis` + photo analysis.
**Voice:** plain, named-materials.
**Length:** 6 cards × ~15 words each.
**Where it appears:** page 4 (Digital), page 12–14 (Print).
**Skip when:** never.

**Card template:**
> **{{score}}/10 — {{room_name}}**
> {{2-3 named details, e.g. "Stone benchtops. Modern cabinetry. Island bench. Premium appliances. Excellent natural light."}}

---

### M8 · Photography Audit (NEW; Print only)
**Asserts:** "Here is what photography would change."
**Inputs:** existing listing photos (when prior listing exists in `property_listings.photo_history`), or paired same-suburb example photos.
**Source:** `property_images` + a curated suburb sample.
**Voice:** specific, technical, restrained.
**Length:** 1 spread; 4 callouts on a single image, or 2 paired images side-by-side.
**Where it appears:** page 14 (Print only).
**Skip when:** if no prior listing photos exist *and* no clean paired example is available.
**Editorial example:**
> **What twilight photography reveals.** This image shot at 11am loses the pool deck to flat shadow. A 7pm twilight shoot, with the deck lights on and the pool uplit, would carry the campaign — peak-end research (Kahneman) shows the *last* visual a buyer sees disproportionately shapes their willingness to pay.

---

# Section B — EVIDENCE modules (data layer)

### M9 · Location & Lifestyle
**Asserts:** "We know your street, not just your suburb."
**Inputs:** satellite analysis, POI cards (schools, parks, cafes, supermarkets, childcare, secondary schools), flood status.
**Source:** `nearby_pois.by_category`, `satellite_analysis`, `flood_assessment`.
**Voice:** named-everything. Walking distances. School names. Park names.
**Length:** 6–8 POI cards + setting & street position cards + flood panel + 1 paragraph street-level prose.
**Where it appears:** page 6 (Digital), page 16–17 (Print spread).
**Skip when:** never.
**Editorial enhancement vs v2:** add the street-level paragraph. Example:
> *"This pocket of cul-de-sacs off Highfield Drive is unusual in Merrimac — the Kingary Wetland creates a permanent green boundary that cannot be built out, and the cul-de-sac configuration eliminates through-traffic. Across the last 36 months, eight homes have transacted within 800m, all at a premium to the wider Merrimac median."*

This single paragraph, added to every report, is the moment the seller realises we read the geography in addition to the data.

---

### M10 · The Buyer Pool
**Asserts:** "These are the specific buyers who will pay you most for this home."
**Inputs:** 3 buyer profiles (primary, secondary, tertiary), Not Ideal For panel, scarcity statement.
**Source:** editorial agent's `buyer_profiles` array.
**Voice:** named personas, school anchors, lifestyle anchors.
**Length:** 3 cards × 60 words + Not Ideal For panel.
**Where it appears:** page 7 (Digital), page 18–19 (Print spread).
**Skip when:** never.

### M11 · "A Saturday morning in this home" — Narrative Transportation Page (NEW; Print only)
**Asserts:** induce the seller to imagine a buyer feeling exactly what they felt at first inspection.
**Inputs:** key buyer profile + key features + lifestyle narrative.
**Source:** editorial agent extension.
**Voice:** present-tense, sensory, restrained, no advice or opinion.
**Length:** 200–250 words. One full page. Substantial whitespace.
**Where it appears:** Print page 19 (paired with buyer profile spread).
**Skip when:** Digital-only edition.
**Editorial constraints:**
- Cannot reference "you" the seller — narrator is a buyer.
- Cannot make claims ("This is the perfect home") — only describe.
- Must end on a quiet image, not a conclusion. (Peak-end.)
- Must reference at least one named POI, one named feature, one named time of day.

**Example seed sentence:** *"Saturday morning, half-past seven. The kettle is on, and through the kitchen window the pool already has its first patch of sun on it…"*

This is the hardest module to write well. Allow up to 3 reflection passes. Any version that drifts into advice gets rejected.

---

### M12 · Market Context
**Asserts:** "Here is the suburb's behaviour, specifically right now."
**Inputs:** scarcity stat, median house price, houses sold (12m), currently listed, seasonality, demand-bracket map.
**Source:** `system_monitor.precomputed_market_charts` + `Gold_Coast.<suburb>` aggregations.
**Voice:** numerical, factual, no predictions.
**Length:** Hero scarcity stat (1 line, large) + 3 stat tiles + seasonality panel + 1 paragraph.
**Where it appears:** page 7 (Digital, integrated with buyer profile), page 20–21 (Print spread).
**Skip when:** never.

**v2 version is solid; the Print expansion adds:**
- A monthly sale-price-index heatmap for the suburb (drawn from 13,585 GC sales seasonal model).
- A demand-bracket map: the listing range as a portal-search bracket and the count of competitors in that bracket.

---

### M13 · Risk + Protection Panel (NEW; Print only)
**Asserts:** "We have already checked everything a buyer's first three Google searches will turn up."
**Inputs:** flood overlay, AHD ground level, ICA flood zone, school catchment status, council DAs within 500m, infrastructure plans, easements/encumbrances, body corp summary (units only).
**Source:** `flood_assessment`, `nearby_pois`, `council_data` (where available), title-search summary.
**Voice:** factual, sourced, concluding "what this means for your buyer".
**Length:** 1 page. Each risk gets 1 row: name → status → source.
**Where it appears:** Print page 22.
**Skip when:** never on Print.

This page is the single most underrated competitive moat. **No competitor includes it.** It is the antidote to the buyer's first three Google searches and it dramatically reduces the post-inspection objection rate.

---

### M14 · Methodology + Sources
**Asserts:** "Every claim in this report can be traced."
**Inputs:** static methodology + suburb-specific adjustment-rate table + "what we did not model".
**Source:** `precompute_valuations.py` rates + curated bibliography.
**Voice:** academic, neutral, sourced.
**Length:** 1 page (Print) / 0.5 page (Digital footer).
**Where it appears:** Print page 23, Digital page 12.
**Skip when:** never.

---

# Section C — ACTION modules (path forward)

### M15 · Pricing Strategy — 4 Cards
**Asserts:** "Here are four price options. Each is anchored in your comp evidence."
**Inputs:** 4 pricing cards (Aspirational, Competitive, Strategic, Floor) with ranges + rationale.
**Source:** editorial agent `pricing_cards` array.
**Voice:** strategy register; specific dollar reasoning per card.
**Length:** 4 cards × ~50 words.
**Where it appears:** page 8 (Digital), page 26 (Print).
**Skip when:** never.

### M16 · Pricing Research Sidebar
**Asserts:** academic backing for the precision and range pricing recommendations.
**Inputs:** static citations.
**Source:** `01_psychology_principles.md` §8 + `seller_book_draft_v4.md` Chapter 4.
**Voice:** confident, sourced.
**Length:** 4 mini-panels, each ~80 words.
**Where it appears:** Print page 27 (paired with pricing cards).
**Sub-panels:**
- Why precise numbers, not round figures (Cardella & Seiler 2016, n=538)
- Why list with a range (Nikiforou et al. 2022, n=538)
- Private treaty vs auction (Frino, Peat & Wright 2012, n=1.2M; REA 2014)
- Getting the price right from day one (Taylor 1999; Anglin/Rutherford/Springer 2003; Knight 2002; Zillow 2019, n=25,000)

### M17 · Feature Positioning
**Asserts:** "Here is how each feature contributes to the campaign."
**Inputs:** 5–6 feature panels, each with feature name + dollar impact + 2-sentence positioning + photography note.
**Source:** editorial agent `feature_positioning` array.
**Voice:** strategy + execution.
**Length:** 5–6 panels.
**Where it appears:** page 9 (Digital), page 28 (Print).

### M18 · Pre-Sale Recommendations Sidebar (NEW)
**Asserts:** "Here is what could be done (or not) before listing, with ROI estimates."
**Inputs:** suburb-specific pre-sale ROI lookup (paint, re-grout, declutter/styling, floor refinish, garden tidy, twilight photo session) + property-specific applicability (e.g. only show floor-refinish if condition_score < 8 on flooring).
**Source:** new `pre_sale_roi.{suburb}` lookup table to be created. Initial values from seller-book Chapter 5 data.
**Voice:** practical, dollar-specific, "we would" not "you should".
**Length:** 4–6 line items.
**Where it appears:** Print page 28 (paired with feature positioning).

### M19 · Campaign Structure
**Asserts:** "Here is the campaign as a designed thing, not a checklist."
**Inputs:** week-by-week timeline; photography strategy; open home strategy; digital targeting.
**Source:** editorial agent.
**Voice:** strategy + specifics.
**Length:** 3 panels (Campaign / Photography / Open Home), 70 words each.
**Where it appears:** page 10 (Digital), page 29 (Print).

### M20 · The First Seven Days (NEW; Print only)
**Asserts:** "Demand is concentrated in the first seven days. Here's how we pre-load it."
**Inputs:** static template + suburb-specific demand-concentration figures from `seller_book_draft_v4.md` Chapter 7.
**Voice:** strategy register, sourced.
**Length:** 1 page; 1 chart (demand-density curve), 200 words of prose.
**Where it appears:** Print page 30.

### M21 · Negotiation Plan (NEW; Print only)
**Asserts:** "We have already thought about offer day."
**Inputs:** 3 offer scenarios — early high (week 1), mid-range cluster (week 2–3), late low (week 4+) — with our recommended response framework for each, specific to this property's likely buyer pool.
**Source:** editorial agent extension.
**Voice:** consulting register. "If X happens, we would Y."
**Length:** 3 scenarios × 80 words.
**Where it appears:** Print page 31.

This module is the kind of thinking sellers expect from a $50K consulting engagement, not a free appraisal. Including it is a deliberate over-deliver.

### M22 · Outcome Projection (NEW; Print only)
**Asserts:** "Here is the financial reality of the choice."
**Inputs:** two scenarios — *correctly priced day-one campaign* vs *overpriced + reduce-after-X-days*. Numbers drawn from the overpricing-penalty research, scaled to the property's range.
**Source:** new calculator script using Taylor 1999 + Zillow 2019 effect-size data.
**Voice:** numerical comparison, not advisory.
**Length:** Side-by-side table; net-to-vendor figures with marketing costs itemised.
**Where it appears:** Print page 32.

This is loss-aversion in action. The seller sees the dollar cost of *not getting it right*. **Critical:** never frame as a threat. Frame as "two paths forward" with the data shown.

### M23 · Why Fields (single page)
**Asserts:** authority signal.
**Inputs:** 4 panels (sold-properties-analysed-for-this-report; transparent methodology; research-backed strategy; local market intelligence).
**Source:** static + suburb-specific count from comparable selection.
**Voice:** restrained.
**Length:** 4 short panels.
**Where it appears:** page 11 (Digital), page 33 (Print).
**Skip when:** never.

**Editorial rule:** the credentialing line (Will Simpson, Harvard Negotiation Program graduate, 6 years GC market analysis) appears as a footnote-style line at the bottom, not as a hero claim.

### M24 · Next Steps (Three-Step Ladder)
**Asserts:** soft default architecture, choice support, reactance avoidance.
**Inputs:** static.
**Voice:** invitational, not insistent.
**Length:** 3 steps × 1 sentence each.
**Where it appears:** page 11 (Digital), page 34 (Print).
**Template:**
> **1. Review this report.** Take your time. We want you to understand every figure.
> **2. Have a conversation.** No pressure, no pitch. We'll walk through the data and answer your questions.
> **3. Decide on your terms.** If you'd like to explore selling with Fields, we'll build a tailored campaign. If not, this report is yours to keep.

The third step is the load-bearing sentence. Never edited. Never softened.

### M25 · A Final Note (Print only)
**Asserts:** peak-end warmth.
**Inputs:** Will writes one per report (or per batch).
**Source:** Will, manually.
**Voice:** human, signed, named.
**Length:** 30–60 words.
**Where it appears:** Print inside back cover.

---

# Section D — Front matter / object-level modules

### M26 · The Cover
**Asserts:** halo effect on first page-flip.
**Inputs:** address, suburb, postcode, prepared-for, date, hero photograph (twilight wherever achievable).
**Source:** address record + photographer's twilight shot.
**Voice:** restrained typography. Earth-tone copper callout. No gloss.
**Where it appears:** page 1.

### M27 · A Note Before You Read (Print only)
**Asserts:** vulnerability + tone-setter.
**Inputs:** Will's hand-written note (per-batch, not per-property).
**Source:** Will writes 4–6 versions; one is selected per report by sellermark (e.g. first-time seller vs investor-led).
**Length:** 80–120 words.
**Where it appears:** Print page 2 (inside front cover).

### M28 · Contents + How to Read This Report
**Asserts:** default architecture.
**Inputs:** static.
**Length:** 1 page.
**Where it appears:** Print page 3, Digital page 1 footer.

---

# Section E — Living Microsite modules

### M29 · Animated Cover Loop
6–8 second twilight pan loop. Autoplay muted, then pause on still.

### M30 · "Listen to Will" 90-second Video
Will speaks the verdict on camera. 90 seconds. Plain background. Embedded on microsite landing.

### M31 · Live Comparable-Sales Feed
Pushes new comps as they sell. Confidence band live-updates. Demand-bracket count refreshes weekly.

### M32 · "What We Got Wrong" Feedback
Single tap form. Seller corrects any property fact. Triggers re-render of affected pages within 24h.

### M33 · Conversation Calendar
One button: "Book a 30-minute walk-through with Will." Live calendar.

### M34 · Engagement Telemetry → Will's Telegram
Existing infrastructure. Telegram fires on open, view, page-view-X, download, session-end.

---

# Section F — Property-Type Variants

### M35 · Apartment / Townhouse Edition
Add: body corporate health summary, strata levy history, bylaws review note.
Modify: M1 (verdict comp set must be apartment/townhouse, not houses).
Modify: M9 (POIs include same-building amenities).

### M36 · Acreage / Lifestyle Edition
Modify: comp set must be acreage. Different adjustment rate table.
Add: dam/water capacity panel, fencing condition, paddock area, infrastructure (septic, solar, batteries).

### M37 · Investor-Held Property Edition
Add: rental yield analysis, tenancy status, depreciation schedule note.
Add: lease-vs-vacant-possession sale strategy comparison.
Reframe: M1, M5 in investor language ("annualised return on equity if held vs realised gain if sold").

### M38 · Deceased Estate / Probate Edition
Add: probate-process note, valuation-date considerations, estate-tax framing.
Modify: tonal shift across all modules — slower pace, no urgency cues, no peak-end warmth (inappropriate context).
Modify: pricing recommendations include a clear-the-estate option vs market-maximisation option.

### M39 · Pre-revenue / Will's Authority Edition
Until Fields has post-listing testimonials, M23 panel "Local Market Intelligence" replaces a testimonial slot. Once we have 5 sold listings, that slot goes to a quote, not a stat.

---

# Section G — Editorial review checklist

Before any report ships, every page is scored against:

| Check | Pass | Fail |
|---|---|---|
| Every number precise (no rounded $X.YM in body) | ✓ | ✗ |
| Every claim cites a source or comp address | ✓ | ✗ |
| Forbidden words absent (stunning, nestled, boasting, rare opportunity, robust market) | ✓ | ✗ |
| "We would" not "you should" — no advice | ✓ | ✗ |
| Trade-offs reframed as value, not flaws | ✓ | ✗ |
| Headlines include a specific numerical anchor | ✓ | ✗ |
| Adjustments named in plain language ("Land area +153 m² → +$57,375") | ✓ | ✗ |
| Inoculation panel(s) include at least 2 weakness reframes | ✓ | ✗ |
| Citations match `01_psychology_principles.md §8` | ✓ | ✗ |
| Property-type variant rules applied (M35–M38) | ✓ | ✗ |
| Methodology page lists exact suburb-sale-count input to adjustments | ✓ | ✗ |
| Three-reader test passed (5s skim, 60s skim, deep-read) | ✓ | ✗ |

A failing check kills the send.

---

*Owner: Will Simpson · Updated 2026-05-06 · Reading order: read after `03_competitive_audit.md`, before `05_visual_system.md`.*
