# Amendments & Operating Framework — Property Intelligence Without Absolute Scarcity Claims

**Prepared:** 2026-05-15 · **For:** Will Simpson (Fields Estate)
**Status:** Operational implementation of [`00_README.md`](00_README.md) — the legal review's five fixes, plus the strategic pivot from "scarcity metrics" to "irreplaceability / substitutability" framing.
**Inputs synthesised:**
- [02_claim_audit.md](02_claim_audit.md) — every existing comparative claim, risk-rated
- [03_safe_language_playbook.md](03_safe_language_playbook.md) — eight operational rules + rewrites
- [04_disclaimer_library.md](04_disclaimer_library.md) — ready-to-use disclaimer text
- External consultant memo, 2026-05-15 — strategic reframe to "replacement difficulty" / "irreplaceability"
- Findings from review of [Version_Four/preview.pdf](../Version_Four/preview.pdf) and [11_House_Mini_Site/](../../11_House_Mini_Site/) docs

---

## 0. The Strategic Pivot in One Line

> The data pipeline does not exist to produce slogans. It exists to identify the strongest sale strategy.

We move the load-bearing concept from **scarcity** (a legal claim about the market we cannot complete) to **irreplaceability** (a strategic positioning concept about what the right buyer will struggle to substitute).

"Scarcity" becomes a numeric absolute the moment it leaves the office. "Difficult to replace" stays a positioning judgement supported by data. The pipeline's outputs do not change. The vocabulary, the publication discipline, and the public framing do.

---

## 1. The Two-Track Model (the spine of everything that follows)

Every output of the property intelligence pipeline now sits on one of two tracks. Different audiences, different standards, different language registers.

### Track 1 — Internal intelligence (rich, detailed, unconstrained)

Fields' systems may still calculate, store and reason over:

- feature combinations and combinatorial position within active and sold sets
- likely substitutability against the live competing market
- buyer-fit strength per persona
- presentation priorities and feature-emphasis ordering
- pricing sensitivities and adjustment magnitudes
- competitive set composition
- likely buyer objections
- recommended campaign hooks and angle scores
- value drivers ranked by cohort evidence
- named trade-offs and how to surface them

These outputs inform appraisals, walk-throughs, listing copy, campaign briefs, photography direction and negotiation strategy. They are **not** published verbatim. The internal field names never appear on a public surface.

### Track 2 — Client-facing positioning (translated, scoped, substantiated)

What leaves the office — to sellers in an appraisal, to buyers on a property page, to either in mini-site copy — is the *translation*, governed by the rules in §4 below. The translation:

- never uses absolute language ("only", "largest", "first", "rarest", "no agency", "most agents") unscoped
- always discloses universe + as-at date in equal prominence to any comparative headline
- replaces named-competitor quantitative comparisons with same-sample evidence or observational reframes
- replaces universal negatives with "we have not seen…" observations
- links to a public `/methodology` surface for every quantitative claim

**The rule:** if Track 1 produces *"this property scores 0.91 on internal replacement-difficulty index against the active 142-listing set"* — Track 2 publishes *"the strongest combination this campaign should carry: six-bedroom scale, dual-living flexibility, pool, cul-de-sac position and permanent bushland boundary."*

The buyer cannot replicate the analysis. The seller cannot reverse-engineer the dataset. The agent gets the strategic clarity. Nobody gets a claim they can sue on.

---

## 2. Internal-language renames (pipeline-wide)

The internal field names currently push writers toward Track-1 vocabulary leaking into Track-2 surfaces. Rename them so the next dev who reads the code can't accidentally publish a Track-1 phrase.

| Current (retire) | New (adopt) | Where it lives |
|---|---|---|
| `scarcity_score` | `replacement_difficulty` | `calculate_property_insights.py`, DB writes, mini-site slot registry |
| `rarity_insights[]` | `position_insights[]` | property document field name |
| `only_one` (insight type) | `combination_position` | insight type enum |
| `top_n` (insight type) | `ordinal_position` | insight type enum |
| `percentile` (insight type) | unchanged — already cohort-relative | — |
| "only-one badges" | "combination position badges" | frontend component naming |
| "rarity label" | "position label" | frontend component naming |
| "scarcity claim" | "positioning observation" | documentation, slot names |
| (new field) | `buyer_fit_signal` | per-persona score, internal only |
| (new field) | `feature_emphasis_priority` | ranked list, internal only |
| (new field) | `substitutability_risk` | per-attribute score, internal only |
| (new field) | `campaign_angle_score` | per-angle ranking, internal only |
| (new field) | `evidence_confidence` | numeric, low/med/high, internal only |

Keep the old fields readable for one release cycle, then drop. Document the new vocabulary in a glossary file alongside `SCHEMA_SNAPSHOT.md`.

---

## 3. Immediate amendments

Specific edits, named by file and page, owned and prioritised. **P0 = before next appraisal issues / before any new mini-site code is written. P1 = within 30 days. P2 = next quarter.**

### 3.1 Appraisal Version Four (`09_Appraisals/Version_Four/`)

Source PDF: [`preview.pdf`](../Version_Four/preview.pdf). HTML source: [`preview.html`](../Version_Four/preview.html).

| # | Page | Current (audit ID) | Amendment | Priority |
|---|---|---|---|---|
| 1 | Cover & TOC (p3) | "01 Scarcity — what makes the home difficult to replace" | Rename: **"01 Irreplaceability — what the right buyer may struggle to find again"** | P0 |
| 2 | p4 (Section 01 opener) | "Scarcity changes what buyers are willing to pay." | Replace with: **"Buyers pay more for what they cannot easily replace."** Body copy per §5 below. | P0 |
| 3 | p5 ("1 of only 4") | Entire page — headline, body, advantage box | Replace with the "combination that carries the campaign" page per §5. Remove the "1 of only 4" frame entirely. Caption stays as substantiation: dataset + suburbs + as-at date. | P0 |
| 4 | p5 advantage box (B-audit ref) | "No other agency maintains this depth of data across every listing" | Rewrite to the new Fields Advantage 01 per §5 (no competitor reference). | P0 |
| 5 | p7 (B4) | "the only configuration in the market that fits this household" | Rewrite: **"the only configuration we observed in our 12-month sold cohort (n=42) that fits this household."** | P0 |
| 6 | p7 advantage box (B6) | "No agency in the southern Gold Coast operates this analysis on a per-listing basis." | Drop the comparison. Replace with a Track-2 statement describing what Fields does, no negative reference to other agencies. Template in §5. | P0 |
| 7 | p7 willingness-to-pay ranges | $1.85M–$2.05M etc. per persona | Keep. Add substantiation requirement (§3.3) — file saved at issue time. | P1 |
| 8 | p9 advantage box (B13) | "Most appraisals rely on a handful of comparable sales. Fields runs the full cohort." | Drop "most appraisals". Describe Fields' method only: **"Fields' valuation runs the full cohort, then narrows the evidence to the homes most relevant to yours."** | P0 |
| 9 | p10 Domain comparison (B14) | "11.4% mean absolute error … Domain's equivalent on the same market: 15.0%. Fields publishes its accuracy. Domain does not." | **Remove from the next issue.** Replace with a Fields-only statement: **"Fields publishes a per-cohort backtest. Our last published mean absolute error against 1,270 GC sales was 11.4%. The methodology is at fieldsestate.com.au/methodology."** Same-sample backtest with Domain remains a P2 option if Will wants to re-introduce the comparison legitimately. | P0 |
| 10 | p11, p18 (recommended price + target sale price) | Forward-looking ranges with no disclosed substantiation file | Keep the numbers. Add P1 workflow: appraisal-generation script saves the substantiation file (reconciled comp set + adjustment table + 90% CI computation + named comps + cohort medians) at issue, retained 7 years. Not visible to the reader. | P1 |
| 11 | p13 campaign reach forecast | 40,000–60,000 impressions etc. | Keep. Confirm the 90-day campaign-benchmark file is live and queryable. Cite it in the source line: "Industry campaign benchmarks · Fields campaign archive · last 90 days · 2026-MM-DD." | P1 |
| 12 | p15 (+118% photography) | Cites "Before You List Ch 4 · Fields Research (n=1,475)" | Keep. Add public `/methodology` page (P1) with the photography-vs-phone-grade methodology, n, controls, definition of "online views". Until that page exists, this claim is medium-risk. | P1 |
| 13 | p17 (+9.6% relationship premium) | Cites "Before You List Ch 6 · Fields Research (n=1,475)" | Same as #12 — needs `/methodology` entry. | P1 |
| 14 | Every page footer | No standing disclaimer | Add the **cover-page disclaimer** from [`04_disclaimer_library.md`](04_disclaimer_library.md) §3 to page 2, and the per-page footnote from §4 to every numbered page footer. | P0 |
| 15 | Final page | No data-currency footer | Add: **"Comparative observations in this report were valid against Fields' dataset at the date of issue. Markets change. The substantiation file for this appraisal is retained and available on request."** | P0 |

### 3.2 House mini-site planning docs (`11_House_Mini_Site/`)

Source docs: [`Concept.md`](../../11_House_Mini_Site/Concept.md), [`Content-Plan.md`](../../11_House_Mini_Site/Content-Plan.md), [`Design.md`](../../11_House_Mini_Site/Design.md). All edits are pre-build; no code yet.

| # | File | Section | Amendment | Priority |
|---|---|---|---|---|
| 16 | `Concept.md` | "Scarcity" tab in tab list | Rename to **"Position"** (preferred) or **"Irreplaceability"** (alternative). Update tab content to lead with sold-cohort framing ("how many homes with this combination sold in 6/12 months") not active-listing rarity. | P0 |
| 17 | `Design.md` §3.2 | Tab order: `#home → #valuation → #buyers → #positioning → #market → #process → #next` | Add a new tab **`#position`** between `#valuation` and `#buyers`, OR fold the position content into `#positioning`. (Recommend separate `#position` — keep `#positioning` for *how* we sell, `#position` for *what makes the home difficult to replace*.) | P0 |
| 18 | `Design.md` §4 (all blocks) | Block-level data discipline | **Add universal requirement:** every block making a comparative claim renders an inline "scope strip" — *"Comparison set: [N] active listings in [suburbs] · refreshed [datetime] · methodology"* — in equal prominence to the headline, not buried as a footer caption. | P0 |
| 19 | `Design.md` §4.1 | Auto-generated blocks | **Add render-time revalidation requirement:** every comparative claim carries `valid_until`, re-queries live dataset at render, suppresses (does not render) if claim no longer holds. Wire the revalidator into the same component that renders the badge. | P0 |
| 20 | `Content-Plan.md` Fear #6 (Valuation) | Subhead: "We tested 1,689 Domain estimates against actual sale prices on the Gold Coast. 89% were over by an average of 11.4%." | Match the P0 appraisal decision (#9 above). Drop the Domain quantitative comparison from the subhead. New subhead: **"We tested our valuation method against 1,689 actual sale prices on the Gold Coast. Our last published mean absolute error was 11.4%. The methodology is at fieldsestate.com.au/methodology."** | P0 |
| 21 | `Content-Plan.md` Fear #1 (Agent Selection) | "Specialist agents (5-15 sales/year in a single suburb) outperformed by 2.8%" | Keep. Add explicit cohort + methodology reference in the citation strip. The /methodology page must document agent-cohort definition, controls (property, timing), and how outperformance is measured. | P1 |
| 22 | `Content-Plan.md` §4.6 Process tab Fear #15 ("+9.6% premium") | Same source as appraisal P17 | Resolve once at `/methodology`; both surfaces inherit. | P1 |
| 23 | `Content-Plan.md` §4.4 Positioning block | "Forbidden-word audit: 'We will never write the words…'" | Soften to **"We avoid words like…"**. Universal commitments are reliance bait. | P0 |
| 24 | `Design.md` §4.3 Buyers tab | Persona "willingness to pay" ranges | Require per-persona substantiation file generated at render time (cohort, n, premium calculation). Block hides if file is missing or stale. | P1 |
| 25 | `Concept.md` content list | "Scarcity: all uniqueness assets we have derived from analysis…" line | Rewrite to: **"Position: the combination of features and location signals this home would be hardest to replace on, with sold-cohort evidence of how often comparable combinations have transacted in 6 and 12 months."** | P0 |
| 26 | All docs | `/methodology` linking | Every block citing a quantitative claim has a link to `/methodology` from its citation strip. Add to Design.md §2 (three-readers model) as a layout convention. | P0 |

### 3.3 Live property pages — the active exposure surface

This is the **largest active legal exposure** in the system because the nightly enrichment pipeline auto-generates absolute claims across every active listing in the four target suburbs. Fix here is operationally larger than the appraisal — but the appraisal change can ship in a day, this needs proper engineering.

| # | File / surface | Amendment | Priority |
|---|---|---|---|
| 27 | [`scripts/backend_enrichment/calculate_property_insights.py`](../../scripts/backend_enrichment/calculate_property_insights.py) — string generators at lines ~214, ~269, ~304, ~334 | **Rewrite every generated string to include universe + as-at date inline.** Example: from `"Only property with kitchen over 25m²"` to `"Only property in our active Robina set with kitchen over 25m² · as at 2026-05-15"`. Same pattern for largest-lot, largest-floor, largest-master-bedroom. | P0 |
| 28 | Same file — insight document schema | Add `valid_until` (timestamp), `dataset_scope` (string), `as_at_date` (date), `methodology_ref` (slug into `/methodology`) to every insight written. | P0 |
| 29 | Same file — `only_one` type | Rename internally to `combination_position`. The string output stops using the word "only" without the scope clause. | P0 |
| 30 | [`src/components/PropertyPage.tsx`](../../../Feilds_Website/01_Website/src/components/PropertyPage.tsx) + `rarityUtils.ts` | **Render-time revalidation:** before rendering a position label, re-query the live dataset against the cached insight. If the comparison no longer holds (e.g. a new listing now exceeds the claim), suppress the label. Log the suppression to `system_monitor.position_label_suppressions` so we can audit. | P0 |
| 31 | Same — position label rendering | Every rendered label has a tooltip on hover showing: dataset, geography, as-at date, methodology link. Tooltip is part of equal-prominence disclosure per ACCC v TPG. | P0 |
| 32 | [`scripts/generate_feed_hooks.py`](../../scripts/generate_feed_hooks.py) — exemplar prompts at lines ~46–52 | **Rewrite the exemplars shown to the LLM** to remove "only", "largest" and dollar-specific comparison patterns (F2, F3, F6 in the audit). Replace with the safe-language register. The LLM imitates the exemplars; new exemplars produce safer output by default. | P0 |
| 33 | Same — generated `feed_hook` field | Add `valid_until` and `regenerated_at`. Regenerate on every nightly run, do not let hooks persist past 48 hours. | P1 |
| 34 | **New:** [`/methodology` page](https://fieldsestate.com.au/methodology) | Build this. One public page documenting: comparable-sales valuation method (incl. 1,689-backtest), position-label methodology, agent-cohort analysis methodology, photography-views study, relationship-premium study, campaign-benchmark file definition. Each section names: dataset, n, time window, controls, limitations, last reviewed. | P0 |

### 3.4 Internal documentation

| # | File | Amendment | Priority |
|---|---|---|---|
| 35 | `SCHEMA_SNAPSHOT.md` | Add glossary section documenting the renamed internal fields (§2). | P1 |
| 36 | CLAUDE.md (root + project) | Update §5 ("Editorial Content Rules") with the four bullet additions from §4 of this document. | P0 |
| 37 | `config/property_editorial_prompt.md` | Update the AI property editorial prompt to enforce the safe-language register in generated copy. Add the forbidden-pattern list. | P0 |
| 38 | This file | Linked from `00_README.md` "Implementation status" table so the audit and the operational answer live together. | P0 |

---

## 4. Standing operating framework (the rules going forward)

These nine rules govern every future comparative claim, in every surface — appraisal, mini-site, property page, Facebook ad, article, newsletter, market report. They are the contract between the data pipeline and the public.

### Rule 1 — The Two-Track Principle is non-negotiable

Internal intelligence (Track 1) can be as rich as the data supports. Client-facing claims (Track 2) are always the translation. Never publish Track-1 field names, scores, or raw rarity numbers. If a developer or writer can copy a value from the database straight into public copy, the system is broken.

### Rule 2 — Universe disclosure in equal prominence

Every comparative claim discloses (a) the dataset, (b) the geography, (c) the as-at date, in equal prominence to the headline — not in a footer, not in a tooltip alone, not buried in a caption. If the headline says "*1 of N*", the next visible line says "*in our [dataset] across [geography], as at [date]*". This defeats the ACCC v TPG "dominant message" doctrine.

### Rule 3 — No absolutes without scope

The following words are forbidden in public copy when used in a comparative sense unless the scope is in equal prominence:

- *only, sole, single* (as comparison)
- *largest, biggest, highest, lowest, smallest*
- *first, last, rarest*
- *no, none, never* (as universal negatives about the market or competitors)
- *most, almost all, all, every* (as universal claims about competitors or industry)
- *unique, one-of-a-kind, unmatched, unrivalled*

Prefer cohort-relative language: *"in our set", "of the N we analysed", "in the 12-month cohort", "among the active listings in [suburbs]".*

### Rule 4 — No named-competitor quantitative comparisons without same-sample, methodology-disclosed evidence

A claim of the form *"Competitor X measures Y on metric Z"* requires:

- the same dataset on both sides of the comparison
- the same methodology applied to both
- the methodology disclosed on `/methodology`
- the substantiation file retained 7 years

If any of those is missing, the comparison does not go public. The Fields-only version *"Fields measures Y on metric Z. The methodology is at /methodology"* is always available and always safe.

### Rule 5 — Substantiation file at issue time, retained 7 years

For every forward-looking number — target sale price, willingness-to-pay range, campaign reach forecast, days-on-market projection — the substantiation file is saved **at the moment of issue**, not reconstructed later. The file contains:

- the dataset (snapshot or query that returned it)
- the methodology (named, versioned)
- the n
- the assumptions
- any human adjustments and who made them
- the timestamp

ACL s4 puts the burden of proof on Fields. Reconstruction is not a defence. The 6-year limitation period means a claim made today can be sued on in 2032 — the file needs to survive that long.

### Rule 6 — Render-time revalidation for auto-generated claims

Any comparative claim generated by an automated pipeline must:

- carry a `valid_until` timestamp
- re-query the live dataset at render time
- suppress (do not render) if the live data no longer supports the claim
- log every suppression to an audit table

The cached-then-rendered pattern is the largest ongoing exposure in the current system. Every claim that renders without revalidation is a liability window equal to the interval between regeneration and the next live event.

### Rule 7 — Reframe universal negatives as observations

The pattern *"no agency does X"* / *"most agents do Y"* becomes *"we have not seen another agency do X"* / *"many agents we have observed do Y"*. The observational frame survives the same factual evidence and removes the universal-claim exposure. If the observational reframe is also unsupported, drop the comparison and describe what Fields does without reference to others.

### Rule 8 — `/methodology` is the public substantiation surface

Every quantitative claim links to `/methodology`. The page documents: dataset, n, time window, controls, methodology, limitations, last reviewed. Without this page, citing "Fields Research" in a sales document is a medium-risk position. With it, the same claim is defensible because the reader can audit it in one click.

### Rule 9 — Approval gate for new comparative claim types

Net-new comparative claim types — anything that doesn't fit an existing approved pattern — get reviewed against this framework before they go into the appraisal template, mini-site copy, enrichment pipeline, or any marketing surface. Review = Will + Claude, with reference to the audit and this document. New patterns added to the audit and this document as they're approved.

---

## 5. Revised Section 01 — full replacement copy

The consultant supplied the language; this is the canonical version to drop into the V4 appraisal template (and the corresponding mini-site block). It carries the strategic pivot without making any of the high-risk claims the audit flagged.

### 5.1 Section 01 left page

> **Buyers pay more for what they cannot easily replace.**
>
> A buyer does not value features in isolation. They value combinations.
>
> A bedroom count matters. A pool matters. A quiet street matters. A permanent green boundary matters. The premium is created when those features work together to solve a buyer's problem better than the alternatives.
>
> Fields analyses that combination before the home goes to market — not to make a loose claim of rarity, but to identify the parts of the home that should carry the valuation, the buyer strategy, the presentation and the negotiation.
>
> For 13 Terrace Court, the strongest position is the combination.

### 5.2 Section 01 right page

> **The combination that carries the campaign.**
>
> For 13 Terrace Court, the campaign should be built around five linked advantages:
>
> - **Scale** — six bedrooms and genuine family capacity.
> - **Flexibility** — dual-living configuration for multi-generational households.
> - **Lifestyle** — pool, deck and outdoor entertaining.
> - **Privacy** — cul-de-sac position and no through-traffic.
> - **Permanence** — bushland boundary behind the home.
>
> The buyer does not experience these separately. They experience them as one answer:
>
> *space, separation, privacy and lifestyle — in a home that is already finished.*
>
> That is the positioning advantage Fields would take to market.

**Source caption (small, beneath the page, equal prominence to the page number):**

> *Source: Fields combinatorial analysis · 142 active listings indexed across Merrimac, Robina and Varsity Lakes · 12-month sold cohort n=1,696 · 2026-05-09. Methodology: fieldsestate.com.au/methodology.*

### 5.3 Fields Advantage 01 — new breakout box

> **FIELDS ADVANTAGE — 01**
>
> Fields' data pipeline analyses the ingredients of a home before the campaign is written: floor plan, photography, satellite imagery, land, location, comparable sales, competing stock and buyer demand.
>
> The purpose is not to produce a headline claim. The purpose is to identify the strongest buyer argument: which features matter, which buyer values them, what evidence supports the price, what trade-offs should be named, and how the campaign should be built.
>
> That is the difference between describing a home and positioning it.

### 5.4 Safe-language register (canonical phrases)

Use freely:

- *"Our analysis identified…"*
- *"The campaign should be built around…"*
- *"The strongest positioning angle is…"*
- *"The buyer is likely to value…"*
- *"This combination gives the campaign a clear point of difference."*
- *"These features work together to…"*
- *"This is the part of the home buyers may find hardest to substitute."*
- *"The evidence suggests…"*
- *"Within the properties we analysed…"*
- *"Based on the available data…"*
- *"We have not seen another configuration in our 12-month cohort that…"*
- *"In our active set across [suburbs], as at [date]…"*

Never use (without scope in equal prominence):

- *"only", "largest", "no other", "the most", "the first"*
- *"guaranteed", "the market", "every buyer", "every listing"*
- *"unique", "unrivalled", "unmatched"*
- *"most appraisals", "most agents", "no agency"*
- named-competitor quantitative comparisons (*"Domain's accuracy is X"*) without same-sample substantiation

---

## 6. The six-force framework — rename Force 01 only

The rest of the framework is sound and survives unchanged. Force 01 changes:

| Position | Current | New |
|---|---|---|
| 01 | Scarcity — what makes the home difficult to replace. | **Irreplaceability — what the right buyer may struggle to find again.** |
| 02 | Buyer fit — who values that scarcity most. | Buyer fit — who values that combination most. |
| 03 | Valuation — what the evidence supports. | Unchanged. |
| 04 | Campaign reach — how the buyer is found. | Unchanged. |
| 05 | Presentation — how features become desire. | Unchanged. |
| 06 | Trust — how confidence protects the bid. | Unchanged. |

The narrative line on page 3 — *"Together, they form the sale strategy. The first force is scarcity."* — becomes *"Together, they form the sale strategy. The first force is irreplaceability."*

---

## 7. Governance & review cadence

### 7.1 Approval gate

Any new comparative claim — in an appraisal section, mini-site block, property-page enrichment string, marketing collateral or article — passes through this gate before publication:

1. Does it use any word from the Rule 3 forbidden list? If yes — scope in equal prominence, or rewrite.
2. Does it name a competitor quantitatively? If yes — same-sample evidence on `/methodology`, or rewrite.
3. Is it forward-looking? If yes — substantiation file saved at issue.
4. Is it auto-generated? If yes — `valid_until` + render-time revalidation wired in.
5. Does it cite a quantitative claim? If yes — `/methodology` link in the citation strip.

If any gate fails, the claim doesn't ship.

### 7.2 Quarterly re-audit

Every three months, re-run the claim audit ([`02_claim_audit.md`](02_claim_audit.md) format) against:

- the current appraisal template
- the live property pages (sample 20 listings)
- the active feed hooks
- any new marketing surfaces (articles, Facebook copy, newsletters, mini-sites that have shipped)

New claims found, risk-rated, amended or removed. Audit dated and filed alongside the original.

### 7.3 Annual legal review

The ACL penalty regime doubled on 28 March 2026. Further regulatory change is likely. Re-engage Queensland-admitted counsel annually, and after any significant ACCC enforcement action involving real estate or comparative claims, to review:

- the framework above
- the disclaimer text in [`04_disclaimer_library.md`](04_disclaimer_library.md)
- the same-sample evidence files for any quantitative competitor comparison being made
- the substantiation files for any high-value forward-looking claims (target sale prices, willingness-to-pay ranges)

---

## 8. The selling proposition that replaces "1 of only 4"

The line Fields builds the appraisal around now is not a scarcity claim. It is a judgement claim:

> **Fields does not guess how to sell your home. We use the data to determine what the campaign should be about.**

Premium variant:

> **The data does not replace judgement. It tells us where judgement should be applied.**

Both are true, both are defensible, both are more interesting than rarity. Sellers do not buy raw data; they buy superior judgement. The data pipeline's job is to earn the right to make that judgement claim.

---

## 9. The moat — restated

The moat is not *"we can say your home is one of four."* The moat is:

> *We know which part of your home should carry the price, which buyer is most likely to pay for it, how to reach that buyer, how to make them feel it, and how to defend the price when they make an offer.*

That is a larger advantage than any single comparative headline. It survives every legal constraint above, because none of it requires an absolute claim about the market. It only requires Fields to keep doing the work the pipeline already enables — and to translate that work into language the public can read without giving Fields a problem.

---

## Appendix A — Cross-references

- The audit this implements: [`02_claim_audit.md`](02_claim_audit.md)
- The language rewrites referenced: [`03_safe_language_playbook.md`](03_safe_language_playbook.md)
- The disclaimer text referenced: [`04_disclaimer_library.md`](04_disclaimer_library.md)
- The liability exposure this is designed to reduce: [`05_liability_scenarios.md`](05_liability_scenarios.md)
- Original index and executive summary: [`00_README.md`](00_README.md)

---

*Filed: `09_Appraisals/Scarcity_Legality/07_amendments_and_operating_framework.md` · Owner: Will Simpson · Drafted 2026-05-15 · Next review: 2026-08-15.*
