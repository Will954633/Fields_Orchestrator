# Fields Conjunction Program — process & code build plan

**Purpose:** turn everything we did by hand for 93 Burleigh Street into a repeatable workflow, so
the *next* conjunction property takes hours, not a day — and so the mistakes we hit this session
cannot recur silently.

**Status:** PLAN ONLY. Nothing here is built. Awaiting Will's approval + prioritisation.

**Scope note:** the 93 Burleigh campaign proceeds regardless — it does not wait on any of this. The
Tier 0 items below also directly improve 93.

---

## What the workflow actually is (what we just did manually)

For one conjunction property, in order:

1. Assemble every scrap of intelligence we hold on the property
2. Detect where our own data contradicts itself before it reaches a buyer
3. Enrich with council planning controls (zone, density, overlays, setbacks)
4. Build a *tight* comparable set (not "800m²+ suburb") and test each claim adversarially
5. Write a one-page buyer thesis, every component proven or disproven
6. Build a buyer landing page (not a listing clone) + capture + measure which thesis converts
7. Reverse-prospect the agents who sold the closest comps, before any cold spend
8. Protect the listing-agent relationship at every step — do no harm to their listing

We did all eight ad hoc. Every one is a candidate to systematise. Below, grouped by dependency, so we
don't build clever comp tools on top of contaminated data.

---

## Tier 0 — Data-integrity prerequisites (fix first, or we rebuild on sand)

These are defects this session exposed. Everything downstream reads them.

### 0.1 Floor-area resolver root fix *(deferred from this session — reverts tonight)*
`get_floor_area()` silently degrades internal→total→room-sum; `suburb_statistics` builds its
percentile scale from a different field again. Only 10.2% of listings are measured on the same
quantity they're ranked against. Fix: remove the total fallbacks, add Domain/onthehouse internal
sources, rebuild `suburb_statistics` from one shared resolver, store `building_area_sqm` separately.
**Blast radius: changes published figures site-wide incl. valuations — needs a measured dry-run
first.** Prerequisite for the comp builder (0 point comparing internal areas that aren't internal).

### 0.2 Waterfront detection gap
`detect_waterfront()` returns False for canal-side docs that have no listing text / no vision pass.
I patched it with a 35m OSM-water heuristic inside the comp agent; it belongs in
`shared/waterfront.py`. Without it, any comp set silently admits canal sales (a $5.1M waterfront sat
in 93's own valuation pool).

### 0.3 Cadastral polygon backfill
Only 40 of 417 in-window sold docs carry `cadastral_polygon.rings`. Block geometry — frontage,
depth, rectangularity — is central to the 93 story and missing on most comps. Build a one-off
backfill (point-in-polygon from the 4,342-polygon index) + fold it into the nightly pipeline.

---

## Tier 1 — Make "conjunction property" a first-class object

Right now 93 Burleigh is just a normal `for_sale` doc, and our own systems treated it as a seller to
prospect and a listing to adjudicate. Both are relationship-ending with the agent.

### 1.1 Conjunction register
A record per conjunction property: listing agent + agency, fee basis, approval status (has Tyler
cleared the page?), campaign status, landing URL, lead source tag, key dates (inspection, agreement
expiry). Either a `system_monitor.conjunction_properties` collection or a typed block on the listing
doc.

### 1.2 Guards driven off the register — the "do no harm" layer, encoded once
- **Seller-prospecting exclusion.** Our lead worklist flagged 93 `on_market_expiring` with "PRIME
  approach window: pitch a re-list" — on the property we're partnering on. Hold any conjunction
  address off the seller-prospecting / came-to-market sweep.
- **Editorial do-no-harm.** Never render a positioning verdict or adverse pricing claim on a
  conjunction listing (this session we found 51 listings site-wide doing exactly that; the
  conjunction set must be permanently exempt, not just fixed once).
- **Campaign wiring.** Landing page + `campaign-lead` read the register so a new property is config,
  not a rebuild.

---

## Tier 2 — Reusable intelligence & comparable tooling

### 2.1 Property dossier + contradiction report
One command → the full dossier **and** a contradictions report. For 93 this would have auto-surfaced,
on day one: floor area 203 vs 220 vs 331; `alfresco_present:false` vs a drawn alfresco;
`fence_type:none` vs "Fenced Grass Yard"; car spaces 2 vs 4; stale `agents_description`. We found all
of these by eye. A validator that cross-checks fields against the floor plan and against each other
turns that into a printed list.

### 2.2 Definitive comparable-set builder
Subject in → tight comps out: walkability-to-beach, block geometry, internal area (via the corrected
resolver), non-waterfront, recency, $/m² land **and** internal. With the **adversarial claim-tester
baked in** — it names every property that beats the subject and states which wording survives. This
is the single highest-reuse tool; we ran it once by hand and it killed the "best combination" claim
and produced the defensible one.

### 2.3 Block-geometry library
Frontage, max depth, rectangularity from cadastral rings (relies on 0.3). Reusable everywhere;
settles "rectangular vs wedge" as fact, not estimate.

### 2.4 Reverse-prospect agent map
Subject in → agencies ranked by closest comps sold in band, withdrawn/expired listings whose vendors
may still want to sell, current competitor snapshot with days-on-market. This is Will's #1 channel
("someone who bid $1.9m six months ago beats 1,000 impressions") and we built it once by hand.

---

## Tier 3 — Council planning enrichment

You did an enormous amount of this by hand for 93 (Development.i → City Plan V13 → zone, RD overlay
absence, min-lot overlay absence, dwelling-house overlay, flood, ASS, the 1-dwelling/400m² density
benchmark, the dual-occ locational gate, the 6m front-setback origin of the "6m relaxation"). It is
exactly repeatable.

### 3.1 City Plan property-report ingest
Given lot/plan: capture the Council property report (the parcel UI 403s automated access, so this
stays a **fetch-the-PDF-then-parse** step, semi-manual by design), parse the layers, store to
`zoning_data`, and **compute the derived signals**: density-per-dwelling maths, whether the easy
dual-occ pathway exists (dual frontage or RD1+), min-lot subdivision test. Our current `zoning_data`
holds only zone + flood — this is where the "is there a development angle?" question gets answered
without a day of manual portal work.

### 3.2 Nearby-precedent finder
Every dual-occupancy/duplex within ~1km: lot size, frontage, RD mapping, assessment type, approval.
"820m² single-frontage LDR, no RD overlay → dual-occ approved nearby" is worth more than any planning
theory. Feeds the developer-outreach pack only, never consumer ads.

---

## Tier 4 — Campaign assembly & measurement

### 4.1 Landing-page generator
Templatise the 93 page: sections driven from dossier + thesis + comps + planning + flood; Rule 5
valuation-disclaimer pre-flight baked in; `noindex`-until-approved as the default. Next property = new
config, not new HTML.

### 4.2 Campaign-lead reporting
Which-thesis-converts view off `campaign_leads.interest` (built the capture this session; not yet the
reporting). This is how we learn whether land, shed, downstairs or renovation is the real hook —
across properties, not just anecdotally.

### 4.3 Claim / fact-check gate
A checklist (and where possible a script) every $ or superlative claim passes before publish:
adversarial refutation + Rule 5 pre-flight + "does a source document exist" (the Res B lesson). Turns
the discipline we applied by hand into a gate that can't be skipped under time pressure.

---

## Suggested build order

1. **Tier 0** (0.1 floor-area, 0.2 waterfront, 0.3 geometry) — unblocks everything and fixes live defects
2. **Tier 1** (conjunction register + guards) — stops us harming the agent relationship; small
3. **Tier 2.2 + 2.1** (comp builder + dossier/contradictions) — highest reuse, directly reusable next property
4. **Tier 3.1** (planning ingest) — biggest manual-effort saving
5. **Tier 4.1 + 2.4** (landing generator + agent map)
6. **Tier 3.2, 4.2, 4.3** — refinements

Tiers 0–2 are the ones that pay for themselves on property #2. Tiers 3–4 are the difference between a
repeatable side-experiment and an actual Fields Conjunction Program.

---

## What I'd reuse vs build new
- **Reuse:** the comp-agent logic, the reverse-prospect agent, `campaign-lead.mjs` + `campaign_leads`,
  the landing-page HTML, `resolve_internal_floor_area()`, `shared/waterfront.py`, the cadastral
  polygon index — all exist from this session as one-offs; the work is generalising them.
- **Build new:** the conjunction register + guards, the contradiction validator, the City Plan ingest
  + derived planning signals, the landing-page generator, the claim gate, the reporting view.

## Explicitly NOT in scope
- No ad spend, no publishing, no vendor contact — all remain manual/Will-controlled.
- No agent scorecard or ranking (POA ss207-9) — the reverse-prospect map is internal targeting only.
