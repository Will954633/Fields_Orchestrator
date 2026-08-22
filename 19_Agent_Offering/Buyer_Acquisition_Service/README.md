# Buyer Acquisition Service — the Fields Conjunction Program

**Read this first.** The single place to understand what we do here and how to process the next
property. Every tool referenced was built and validated on the first property, **93 Burleigh Street,
Burleigh Waters** ([`listings/93-burleigh-street-burleigh-waters/`](listings/93-burleigh-street-burleigh-waters/)).

---

## 0. Folder layout (organised for multiple listings, 2026-08-22)

```
Buyer_Acquisition_Service/
├── README.md                  ← this file (program overview + workflow)
├── _program/                  ← listing-agnostic program docs
│   ├── CONJUNCTION_PROGRAM_BUILD_PLAN.md   (rationale for each tool)
│   ├── CONJUNCTION_PROGRAM_BUILT.md        (full inventory + commits)
│   ├── INCIDENT_agent_listing_disparagement.md
│   └── tools/photos/          (shared photo-enhance pipeline — run per address)
├── _templates/LISTING/        ← copy this to start a new listing
└── listings/
    └── <slug>/                ← one dossier per property
        ├── README.md          (the listing index — start here)
        ├── PLAN.md  BUYER_THESIS.md  INSPECTION_BRIEF.md  CAMPAIGN_COPY.md
        ├── photos/{original,twilight}/
        ├── handouts/          (buyer info-pack PDF etc.)
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

## 5. Hard-won lessons (don't relearn these)

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

---

## 6. Open items carried forward
- Backup gap: `enrich_properties_for_sale.py` + `generate_suburb_statistics.py` (under
  `Feilds_Website`) are **not git-tracked** — fixes are VM-only until they get a repo home.
- 93: attribute the listing agent in the info-pack PDF + ad copy; run `claim_gate.py` over both;
  regenerate the PDF comps via `comparable_set.py`; confirm the "6 m relaxation" with Tyler. See the
  [93 listing README](listings/93-burleigh-street-burleigh-waters/README.md) open-items section.
