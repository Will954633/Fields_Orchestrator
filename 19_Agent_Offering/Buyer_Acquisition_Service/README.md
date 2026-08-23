# Buyer Acquisition Service — the Fields Conjunction Program

**Read this first.** The single place to understand what we do here and how to process the next
property. Every tool referenced was built and validated on the first property, **93 Burleigh Street,
Burleigh Waters** ([`listings/93-burleigh-street-burleigh-waters/`](listings/93-burleigh-street-burleigh-waters/)).

---

## 0. Folder layout (organised for multiple listings, 2026-08-22)

```
Buyer_Acquisition_Service/
├── README.md                  ← this file (program overview + workflow)
├── _program/                  ← listing-agnostic program docs + shared tools
│   ├── CONJUNCTION_PROGRAM_BUILD_PLAN.md   (rationale for each tool)
│   ├── CONJUNCTION_PROGRAM_BUILT.md        (full inventory + commits)
│   ├── INCIDENT_agent_listing_disparagement.md
│   └── tools/
│       ├── photos/            (shared photo-enhance pipeline — run per address)
│       ├── council_data/      (§5) council/state data catalog — council_catalog.py + catalog.json
│       └── dd/                (§5) due-diligence: dd_pull.py, flood_reality.py, dd_pack.py
├── _templates/LISTING/        ← copy this to start a new listing
└── listings/
    └── <slug>/                ← one dossier per property
        ├── README.md          (the listing index — start here)
        ├── PLAN.md  BUYER_THESIS.md  INSPECTION_BRIEF.md  CAMPAIGN_COPY.md
        ├── photos/{original,twilight}/
        ├── handouts/          (buyer info-pack PDF etc.)
        ├── dd/                (§5) dd_data.json + Flood Reality + Due-Diligence Pack PDFs
        └── ads/{mockups/, AD_IDS.md}
```

The **shared tooling is in `scripts/` and `shared/`** at the orchestrator root (not here); this folder
holds the program docs, the templates, and the per-listing dossiers + buyer-facing assets.

### Onboard a new listing
```bash
cd 19_Agent_Offering/Buyer_Acquisition_Service
SLUG=<address-slug>            # e.g. 14-example-street-robina
cp -r _templates/LISTING listings/$SLUG
# then work the 9-step workflow below; fill listings/$SLUG/README.md as the index
```

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
- **Attribute the listing agent** on *every* public asset — landing page, info pack **and ad copy**.
- **No Fields valuation figure** presented as the home's worth. A listing price is a fact; our
  comparable-sales model does not produce a defensible single figure for most of these homes.
- **All editorial rules apply** (CLAUDE.md Rule 5): no advice, no predictions, no forbidden words,
  exact numbers, suburbs capitalised, no single valuation in a headline.

Background & pitch language: the listing's `PLAN.md` §1; the incident that shaped the guards:
[`_program/INCIDENT_agent_listing_disparagement.md`](_program/INCIDENT_agent_listing_disparagement.md).

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
Fix anything HIGH before you build on it (floor-area, alfresco, car-spaces, stale "under contract").

### Step 2 — the definitive comparable set + test the story
```bash
python3 scripts/comparable_set.py --slug <slug> --min-land 800 \
  --claim "the scarcity/value sentence you want to publish"
```
Tight comps + an **adversarial claim test** that tells you which wording survives. ⚠ It also shows
where a price-floor claim is sensitive to the beach-distance cutoff — heed its caveats. **Use this for
any comps you publish** (the info pack too), not an ad-hoc query.

### Step 3 — who to call before spending a dollar on ads
```bash
python3 scripts/reverse_prospect_map.py --slug <slug>
```
The agents who recently sold the closest comps hold the under-bidders (a targeting count, **never** a
performance rating — POA ss207-9). Highest-probability channel.

### Step 4 — the planning position (only if a development angle is plausible)
```bash
# A human downloads the Council property report from the "City Plan online" link, then:
python3 scripts/ingest_cityplan_report.py --pdf "<report.pdf>" --slug <slug> --store
python3 scripts/dual_occ_precedents.py --slug <slug>
```
**Never advertise a development claim the verdict doesn't support**; never state a buyer "can" build.

### Step 5 — gate every claim before it goes anywhere
```bash
python3 scripts/claim_gate.py --slug <slug> --file claims.txt   # exits non-zero on any FAIL
```
Runs Rule 5 checks, superlative/"only"/"every" verification, the $-claim landing-page pre-flight,
planning-source checks, and valuation guardrails. **Gate the ad copy and the info-pack claims too.**

### Step 6 — enhance the photos (optional, agent-approved only)
Relight to twilight — **light and sky only, never the house**. Shared pipeline now lives in
[`_program/tools/photos/`](_program/tools/photos/) and writes an `<address-slug>/` output folder;
move the finished `original/`+`twilight/` sets into `listings/<slug>/photos/`.
```bash
cd _program/tools/photos && python3 enhance_property_photos.py --address "..."   # eyeball contact_sheet.jpg
```
Enhanced images carry a "digitally enhanced" disclosure. Keep originals.

### Step 7 — build the landing page (not a listing clone)
```bash
python3 scripts/generate_conjunction_landing.py --slug <slug>            # review artefact
python3 scripts/generate_conjunction_landing.py --slug <slug> --write-tree  # stage (noindex)
```
The methodology "this is NOT a Fields valuation" block and the listing-agent attribution are
**mandatory and non-removable**. Defaults to `noindex`. ⚠ **The 93 page is hand-built** (the
generator won't overwrite it); the generator config still uses the far "Burleigh Heads Beach" pin for
its rarity/comps radius — reconcile beach distances before any generated page goes public.

### Step 8 — go live (agent-gated, human-only)
1. Send the listing agent the noindex URL; get approval. 2. Remove `noindex`; push. 3. Post to
Marketplace **from a personal profile** (Meta removed real-estate Marketplace for business Pages in
2023). Paid Fields Ads Manager campaigns (e.g. click-to-Messenger carousels) are a separate channel;
still human-activated. Approved copy pattern: the listing's `CAMPAIGN_COPY.md`.

### Step 9 — measure which thesis converts
```bash
python3 scripts/campaign_lead_report.py --slug <slug>     # interest breakdown
```
Leads land in `system_monitor.campaign_leads`. The "what interested you most" field tells us whether
land, shed, downstairs or renovation is pulling — across properties, not just anecdotally.

### Step 10 — assemble the buyer due-diligence pack (full detail in §5)
```bash
python3 _program/tools/dd/dd_pull.py --address "…"                 # -> listings/<slug>/dd/dd_data.json
python3 _program/tools/dd/flood_reality.py --address "…" --out …   # the flood one-pager
python3 _program/tools/dd/dd_pack.py --data listings/<slug>/dd/dd_data.json   # the full DD pack PDF
```
Pulls comprehensive council + state data by lot/plan into buyer-facing documents. **Clear the flood
framing with the listing agent, and `claim_gate.py` the claims, before it reaches any buyer.**

---

## 3. The thinking artefacts (per property)

Blank scaffolds in [`_templates/LISTING/`](_templates/LISTING/); the worked example is
[`listings/93-burleigh-street-burleigh-waters/`](listings/93-burleigh-street-burleigh-waters/):
`PLAN.md` (master dossier), `BUYER_THESIS.md` (one-page thesis), `INSPECTION_BRIEF.md` (on-site),
`CAMPAIGN_COPY.md` (Marketplace + group variants). Buyer-facing outputs go in the listing's
`handouts/` (info-pack PDF) and `ads/` (mockups + `AD_IDS.md`).

---

## 4. The tooling (what's built) — [full inventory + commits](_program/CONJUNCTION_PROGRAM_BUILT.md)

Shared libraries (`shared/`): `floor_area.py`, `block_geometry.py`, `waterfront.py`,
`planning_signals.py`. Scripts (`scripts/`): `conjunction_register.py`, `property_dossier.py`,
`comparable_set.py`, `reverse_prospect_map.py`, `ingest_cityplan_report.py`, `dual_occ_precedents.py`,
`claim_gate.py`, `generate_conjunction_landing.py`, `campaign_lead_report.py`.

**The two guards:** Guard A — a registered conjunction property is dropped from seller-prospecting.
Guard B — it never gets an adverse positioning verdict. Build rationale:
[`_program/CONJUNCTION_PROGRAM_BUILD_PLAN.md`](_program/CONJUNCTION_PROGRAM_BUILD_PLAN.md).

---

## 5. The Buyer Due-Diligence Data System (built 2026-08-23)

The differentiator for the conjunction service: we hand a serious buyer **"everything we could pull
from council + state data so you can do your homework"** — to a depth no listing agent offers, short
of a physical building & pest. It disarms objections (flood especially) with sourced data instead of
leaving them unanswered, and it's a genuine reason for a buyer to give us their details.

### 5.1 How we access council data — there is no master file to download; the *catalog* is the master
Gold Coast City and Queensland state both run **ArcGIS REST servers** whose service directory is
enumerable in one call — that catalogue *is* the master index, and it's **auth-free**, queryable per
parcel by `LOTPLAN` or by geometry.
- **Gold Coast City** (ArcGIS Online org `3vStCH7NDoBOZ5zn`) — **256 FeatureServers**: flood, zoning,
  overlays, sewer/water/stormwater, roads, development applications, bushfire, landslide, heritage,
  cadastre, biodiversity…
- **QLD state spatial** (`spatial-gis.information.qld.gov.au`) — FloodCheck (1% AEP basin studies),
  Historic Flood Lines, Elevation, Environment.
- Non-spatial/bulk: QLD CKAN `data.qld.gov.au/api` and `data.gov.au` (not usually needed for a parcel).

```bash
cd _program/tools/council_data
python3 council_catalog.py                 # crawl both roots -> catalog.json (the master manifest)
python3 council_catalog.py --grep flood    # search the saved catalog by keyword
```
⚠ QLD state services live UNDER their folder — a service URL must be `{root}/{folder}/{name}/{type}`
or it returns a misleading `499 Token Required`. `council_catalog.py` handles this; don't hand-build
QLD URLs without the folder segment.

### 5.2 The tool chain (catalog → pull → render)
```
council_catalog.py ──► catalog.json ──► dd_pull.py ──► dd_data.json ──► dd_pack.py ──► DD Pack PDF
                                            │                        └─► flood_reality.py ─► Flood 1-pager
                                            └─ merges the flood/zoning fields already stored in Mongo
```
All three DD tools are in [`_program/tools/dd/`](_program/tools/dd/); see its README for arguments.

1. **`dd_pull.py --address "…"`** — resolves the authoritative parcel from the GC cadastre by
   `LOTPLAN` (⚠ **not** a geocode — a geocoded point can miss the lot by ~200 m; always query at the
   cadastral centroid), queries **~19 curated DD layers** (flood overlay + designated level + depth +
   ICA insurance-flood model, acid-sulfate, bushfire, landslide, heritage, min-lot, road hierarchy,
   nearby DAs within 400 m, sewer/water/stormwater, QLD FloodCheck 1% AEP + historic flood lines),
   merges the stored flood/zoning fields, and writes `listings/<slug>/dd/dd_data.json` — per-layer
   `{hit, attributes, source_url, as_at, status}`, errors captured per-layer, not fatal.
2. **`flood_reality.py --address "…" --historical "…"`** — the **Flood one-pager** (the centrepiece).
   Reads the stored flood fields and renders the four-layer story: conservative overlay → designated
   vs ground level (m AHD) with a level-diagram → the ICA insurer model → historical/extreme finding →
   the three official searches.
3. **`dd_pack.py --data listings/<slug>/dd/dd_data.json`** — the full **5-section Buyer DD Pack PDF**:
   cover → flood → hazards & overlays → location/services → nearby development → next-steps + sources.

Outputs land in `listings/<slug>/dd/`. Both PDFs are Fields-branded (they copy the palette/header from
`flood_reality.py` / `make_infopack.py`). Offer them to **serious** buyers, not the public feed.

### 5.3 What we can and can't get
| Obtainable | Not obtainable |
|---|---|
| Flood (overlay, designated level, modelled depth), ICA insurer flood model, hazards, overlays, road class, services mains, nearby DAs, zoning, cadastre, historic flood-line extents | **Property-level insurance CLAIM history** — privacy-protected, no public register. Do **not** build on "actual claims made." |
| Human-ordered (guide the buyer): title search (easements — Titles Qld, paid), building-records/final-cert search (Council, paid), Council Flood Search cert, a live **insurance premium quote** ($ = the market pricing the risk) | A **building & pest** — physical inspection. We compensate with the honest condition disclosure + recommend an inspector. |

The **historical-flood** question resolves via QLD FloodCheck / Historic_Flood_Lines: for 93 Burleigh
**no recorded historic floodline reaches the block** (the state lines map other catchments); the only
modelled extent touching it is an **extreme Hinze Dam PMF / dam-failure** scenario — a model, not a
record. Always keep that distinction.

### 5.4 Editorial & conjunction guardrails (non-negotiable for flood)
- **Never assert a property "won't flood."** Present data + source + as-at date, conditional, and keep
  the honest caveats (93's ground sits **−0.15 m below** the designated level, so the yard/downstairs
  is the exposed part — say so).
- **Run `claim_gate.py` (Step 5)** over every DD/marketing claim. The gate can't tell a *listing price*
  from a *valuation* — a lone `$` figure will FAIL; sign it off only if it's the labelled asking price.
- **Clear the flood/DD framing with the listing agent first** (do-no-harm). Template:
  the listing's `dd/NOTE_TO_TYLER_flood_framing.md`.

---

## 6. Hard-won lessons (don't relearn these)

1. **Floor-area field was contaminated** — use `shared.floor_area.resolve_internal_floor_area`.
2. **"Rectangular" is usually wrong** — most blocks are wedges; `block_geometry` measures it.
3. **The sold set is a floor, not a census** — real sales sit in timeline arrays; "only/none/every"
   claims are threshold- and coverage-sensitive; the claim gate makes you prove it.
4. **A scarcity claim beats a valuation claim.**
5. **"Res B / development block" needs a source document.** Ingest the City Plan report first.
6. **Check the live listing copy, don't trust our scrape** — ours can be a day stale.
7. **Measure "walk to the beach" to the nearest point on the coastline, not a named beach POI pin.**
   The sand runs the whole coast; a pin can sit km away and overstate it. 93 Burleigh = 947 m
   straight-line to the nearest coast → a fair **~1 km walk**. Keep ads, PDF and page consistent.
8. **A buyer-facing asset built outside the tools still owes the rules.** This session's info pack +
   ads were drafted fast and skipped `comparable_set.py`/`claim_gate.py` and full agent attribution —
   see the 93 README open items. Run the gates over anything before it goes public.
9. **Query council layers at the cadastral centroid (by `LOTPLAN`), not a geocode.** A geocoded address
   point can sit ~200 m off the lot and miss every polygon (Rule 8). `dd_pull.py` resolves the parcel
   from the cadastre first.
10. **Meta "account_status: 3" (unsettled) freezes ALL writes** — an unpaid balance blocks creating or
    editing ad creatives *and* activating campaigns; it is **not** a policy ban (`disable_reason: 0`).
    If an ad write returns a "Permissions error", check `account_status` before anything else; the fix
    is to settle the balance in Ads Manager → Billing.

---

## 7. Open items carried forward
- Backup gap: `enrich_properties_for_sale.py` + `generate_suburb_statistics.py` (under
  `Feilds_Website`) are **not git-tracked** — fixes are VM-only until they get a repo home.
- 93: attribute the listing agent in the info-pack PDF + ad copy; run `claim_gate.py` over both;
  regenerate the PDF comps via `comparable_set.py`; confirm the "6 m relaxation" with Tyler. See the
  [93 listing README](listings/93-burleigh-street-burleigh-waters/README.md) open-items section.
