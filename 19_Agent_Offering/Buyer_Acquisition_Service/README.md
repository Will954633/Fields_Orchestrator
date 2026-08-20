# Buyer Acquisition Service — the Fields Conjunction Program

**Read this first.** It is the single place to understand what we do here and how to process the
next property. Every tool referenced was built and validated on the first property, **93 Burleigh
Street, Burleigh Waters**, and the deeper docs are linked throughout.

---

## 1. The model (what this is)

Fields finds a **buyer** for a property another agency has **listed**. We are not taking the listing
and not touching the vendor — we add a buyer-acquisition channel alongside the listing agent's
campaign, under a simple conjunction arrangement (agreed share of the selling commission if our
introduced buyer purchases; nothing if not).

**The one principle everything hangs on:** *do no harm to the listing agent.* We are alongside them,
not evaluating them. This is not just etiquette — our own systems have twice tried to undermine a
partner agent (poaching the vendor as a "re-list" lead; publishing an "Overpriced" verdict on their
listing). Those are now blocked by code (§4, Guard A/B), but the posture is the point.

Rules we never break:
- **Never contact the vendor.** The listing agent owns that relationship.
- **Clear anything we publish about the property with the listing agent first.**
- **Attribute the listing agent** on every public asset.
- **No Fields valuation figure** presented as the home's worth. A listing price is a fact; our
  comparable-sales model does not produce a defensible single figure for most of these homes.
- **All editorial rules apply** (CLAUDE.md Rule 5): no advice, no predictions, no forbidden words,
  exact numbers, suburbs capitalised, no single valuation in a headline.

Background & pitch language: [`93_Burleigh_Street_PLAN.md`](93_Burleigh_Street_PLAN.md) §1;
the incident that shaped the guards: [`INCIDENT_agent_listing_disparagement.md`](INCIDENT_agent_listing_disparagement.md).

---

## 2. The workflow for a new property — do it in this order

Everything below is a command. `source /home/fields/venv/bin/activate && set -a && source
/home/fields/Fields_Orchestrator/.env && set +a` first. Run from `/home/fields/Fields_Orchestrator`.

### Step 0 — register it (this is what protects the agent relationship)
```bash
python3 scripts/conjunction_register.py --add \
  property_slug=<slug> property_id=<mongo _id> address="..." \
  listing_agent="..." listing_agency="..." landing_url="" \
  lead_source_tag=campaign_landing_<slug> campaign_status=draft
python3 scripts/conjunction_register.py --show <slug>
```
The moment a property is registered it is **excluded from seller-prospecting** and **exempt from any
positioning verdict** (§4). Do this before anything else.

### Step 1 — understand the property, and catch our own bad data
```bash
python3 scripts/property_dossier.py --slug <slug>          # facts + a CONTRADICTION REPORT
```
The contradiction report is the point: it auto-flags the data problems we found by eye on 93
(floor-area 203-vs-220-vs-331, alfresco_present=false vs the plan, car spaces 2-vs-4, stale
"under contract" copy). Fix anything HIGH before you build on it.

### Step 2 — the definitive comparable set + test the story
```bash
python3 scripts/comparable_set.py --slug <slug> --min-land 800 \
  --claim "the scarcity/value sentence you want to publish"
```
Tight comps (walk-to-beach, geometry, internal area via the corrected resolver, non-waterfront,
recency, $/m²), plus an **adversarial claim test** that tells you which wording survives. It killed
"one of the best combination of location, land AND house size" on 93 (house-size is a weakness) and
proposed the scarcity + condition-gap wording instead. ⚠ It also showed the price-floor claim is
sensitive to the beach-distance cutoff — heed its caveats.

### Step 3 — who to call before spending a dollar on ads
```bash
python3 scripts/reverse_prospect_map.py --slug <slug>
```
The agents who recently sold the closest comps hold the under-bidders. This ranks them by relevant
recent transactions (a targeting count, **never** a performance rating — POA ss207-9), plus
withdrawn listings and current competitors. This is the highest-probability channel.

### Step 4 — the planning position (only if a development angle is plausible)
```bash
# A human downloads the Council property report from the "City Plan online" link
# (the parcel UI 403s automated access), then:
python3 scripts/ingest_cityplan_report.py --pdf "<report.pdf>" --slug <slug> --store
python3 scripts/dual_occ_precedents.py --slug <slug>
```
Produces the derived verdict (density-per-dwelling, dual-occ pathway, the 6m-setback origin of a
vendor's "6m relaxation") — the analysis Will did by hand on 93, now automatic. It stores to
`zoning_data.cityplan`. **Never advertise a development claim the verdict doesn't support**, and
never state a buyer "can" build anything.

### Step 5 — gate every claim before it goes anywhere
```bash
python3 scripts/claim_gate.py --slug <slug> --file claims.txt   # exits non-zero on any FAIL
```
Runs Rule 5 lexical checks, superlative/"only"/"every" verification, the $-claim landing-page
pre-flight, planning-source checks (cross-referenced against `zoning_data.cityplan`), and valuation
guardrails. If it FAILs, do not publish that claim.

### Step 6 — enhance the photos (optional, agent-approved only)
The listing photos are usually harsh daylight. We relight them to twilight — **light and sky only,
never the house** (that would destroy the honest-condition thesis). Full guide:
[`photos/README.md`](photos/README.md).
```bash
cd photos && python3 enhance_property_photos.py --address "..."   # then eyeball contact_sheet.jpg
```
Enhanced images carry a "digitally enhanced" disclosure. Keep originals.

### Step 7 — build the landing page (not a listing clone)
```bash
python3 scripts/generate_conjunction_landing.py --slug <slug>            # review artefact
python3 scripts/generate_conjunction_landing.py --slug <slug> --write-tree  # stage into website (noindex)
```
Section-driven from the dossier + comps + planning + register. The "this is NOT a Fields valuation"
methodology block and the listing-agent attribution are **mandatory and non-removable**; it fails
loudly if the register has no agent. Defaults to `noindex` — it stays noindex until the listing
agent has cleared the page.

### Step 8 — go live (agent-gated, human-only)
1. Send the listing agent the noindex URL; get approval.
2. Remove the `noindex` meta tag; push the page.
3. Post to Facebook Marketplace / groups **from a personal profile** (Meta removed real-estate
   Marketplace for business Pages in 2023). Approved copy pattern:
   [`93_Burleigh_CAMPAIGN_COPY.md`](93_Burleigh_CAMPAIGN_COPY.md).
   Ads/publishing/vendor-contact are never automated.

### Step 9 — measure which thesis converts
```bash
python3 scripts/campaign_lead_report.py --slug <slug>     # interest breakdown
```
Leads land in `system_monitor.campaign_leads` (via `netlify/functions/campaign-lead.mjs`). The
"what interested you most" field tells us whether land, shed, downstairs or renovation is pulling —
across properties, not just anecdotally.

---

## 3. The thinking artefacts (per property)

For 93 Burleigh, these are the templates to copy:
- [`93_Burleigh_Street_PLAN.md`](93_Burleigh_Street_PLAN.md) — the master dossier + task list
- [`93_Burleigh_BUYER_THESIS.md`](93_Burleigh_BUYER_THESIS.md) — the one-page buyer thesis (land +
  location + price-gap-to-renovated-stock; house-size and "best-of" disproven)
- [`93_Burleigh_INSPECTION_BRIEF.md`](93_Burleigh_INSPECTION_BRIEF.md) — what to document on site
  (data contradictions to settle, "dated vs needs money", why-hasn't-it-sold)
- [`93_Burleigh_CAMPAIGN_COPY.md`](93_Burleigh_CAMPAIGN_COPY.md) — Marketplace + 5 group variants

---

## 4. The tooling (what's built) — [full inventory + commits](CONJUNCTION_PROGRAM_BUILT.md)

Shared libraries (`shared/`): `floor_area.py` (internal area, never a total), `block_geometry.py`
(frontage/depth/rectangularity — catches "rectangular" overclaims), `waterfront.py` (geometric
fallback), `planning_signals.py` (the V13 development reasoning).

Scripts (`scripts/`): `conjunction_register.py`, `property_dossier.py`, `comparable_set.py`,
`reverse_prospect_map.py`, `ingest_cityplan_report.py`, `dual_occ_precedents.py`, `claim_gate.py`,
`generate_conjunction_landing.py`, `campaign_lead_report.py`, `backfill_cadastral_polygons.py`.

**The two guards, so you know they're there:**
- **Guard A** — a registered conjunction property is dropped from seller-prospecting (worklist +
  came-to-market), so we never pitch the vendor a re-list.
- **Guard B** — a registered conjunction property never gets an adverse positioning verdict
  generated or published.

Build plan (the rationale for each piece): [`CONJUNCTION_PROGRAM_BUILD_PLAN.md`](CONJUNCTION_PROGRAM_BUILD_PLAN.md).

---

## 5. Hard-won lessons (don't relearn these)

1. **Our floor-area field was contaminated** — it stored carport-and-alfresco totals as "internal",
   inflating percentiles. Always use `shared.floor_area.resolve_internal_floor_area`. The dossier
   will flag it if a property is still wrong.
2. **"Rectangular" is usually wrong.** Most blocks are wedges. `block_geometry` measures it; 93 is
   0.908 rectangularity = "regular", not rectangular.
3. **The sold set is a floor, not a census.** Real sales sit only in timeline arrays (114 Burleigh
   St had `listing_status: null`). Any "only/none/every" claim is threshold- and coverage-sensitive
   — the claim gate makes you prove it.
4. **A scarcity claim beats a valuation claim.** Counts and medians are checkable; a valuation isn't
   defensible here and isn't allowed in a headline anyway.
5. **"Res B / development block" needs a source document.** On 93 the public evidence was Res A and
   Low Density Residential; the "6m relaxation" is almost certainly a front-setback story, not
   density. Ingest the City Plan report before making any planning claim.
6. **Check the live listing copy, don't trust our scrape** — ours can be a day stale (93's said
   "under contract" after that had lapsed). Fetch via `shared/domain_fetch.py` (Bright Data).

---

## 6. Open items carried forward
- Backup gap: `enrich_properties_for_sale.py` + `generate_suburb_statistics.py` (under
  `Feilds_Website`) are **not git-tracked** — fixes are VM-only until they get a repo home.
- 93 landing page: the "$2,196,785 floor within 1.7km" line is threshold-sensitive (148 Burleigh
  St, same street, $2,050,000, sits at 1.86km) — soften before public launch.
