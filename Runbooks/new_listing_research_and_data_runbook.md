# New Listing — Research & Data Collation Runbook

**Purpose:** a repeatable process to collate *all* research and data on a new listing
(especially a conjunction/off-market or a property with a development angle) before we
write copy, build ads, or brief a buyer. Worked example throughout: **93 Burleigh Street,
Burleigh Waters** (listed 2026-08, $1,915,000, conjunction with Tyler).

**How to read this:** each phase says **what** we're establishing, the **website/URL**,
**who does it** (🧑 = Will, in a browser / logged-in tool · 🤖 = Claude/VM), the **output**
we keep, and **gotchas**. The last section is a fill-in **Listing Data Record** template —
copy it per property.

> Golden rule (Rule 8): a search returning "nothing" is evidence about the *name you typed*,
> not proof the thing doesn't exist. Report a zero as "no field/record called X — related
> is A, B, C", never "it doesn't exist", until you've looked at what the source actually holds.

---

## Inputs you need to start
- **Street address** (e.g. 93 Burleigh Street, Burleigh Waters)
- **Lot / Plan number** (e.g. **Lot 187 RP128164**) — this is the key that unlocks every
  Council record. If you only have the address, the Council land search (Phase 1) gives you
  the lot/plan.

---

## Phase 1 — Identify the parcel (Council land record) 🧑
**Establish:** legal parcel, land area, and whether any applications are attached.

- **Site:** Gold Coast **Development.i** land search.
- **URL pattern (by lot/plan):**
  `https://developmenti.goldcoast.qld.gov.au/Home/FilterDirect?filters=LandNumber=<LOTPLAN>`
  e.g. `...LandNumber=187RP128164`
- **Do:** open the parcel; read the header (address, **Lot/Plan**, **area m²**) and the
  **"Applications Associated with this Property"** panel.
- **Output:** land area (822 m²), confirmed lot/plan, and the DA-association result.
  - `Nil` = no development/referral/building applications on record here (still not proof
    none *ever* existed — see Phase 2 note).
- **Also on this screen:** a right-hand **"More details"** with a **City Plan online** link →
  used in Phase 3. And the **downloadable Property Details PDF** — save it.
- **Gotcha:** Council warns Development.i does **not** replace official property searches;
  building approvals, planning/flood certificates may reveal more. Pre-electronic approvals
  (older homes, e.g. 1975 builds) can sit in Council's paper file, not here.

## Phase 2 — Development history (Development.i application search) 🧑
**Establish:** any past/current DA, referral-agency assessment (RAA), or building approval.

- **Site:** Development.i main search — `https://developmenti.goldcoast.qld.gov.au/`
- **Do:** search the address / lot-plan; look for `RAA/…`, `COM/…`, `ROL/…` (reconfig/
  1-into-2), `MCU/…`, building applications.
- **Output:** list every application (type, number, date, decision) — or record **Nil**.
- **Why it matters:** an approved duplex/subdivision/siting relaxation sitting here changes
  the whole story. For 93 Burleigh: **Nil** — which *removed* the "hidden approved duplex"
  hypothesis rather than confirming a development angle.

## Phase 3 — Current planning controls (City Plan property report) 🧑 ⭐
**Establish:** the *current* zone + every mapped overlay. This is the single most valuable
free document.

- **Site:** **City Plan online** (`https://cityplan.goldcoast.qld.gov.au/`), reached via the
  **"City Plan online"** link in Phase 1's "More details".
- **Do:** load the parcel → find **Property Report / Print Report / Download PDF** → generate
  and **save the PDF** (note the **City Plan version + "current as at" date**, e.g. V13,
  20 Aug 2026).
- **Output — record each layer:**
  - **Zone** (e.g. *Low density residential*) + **precinct** if any
  - **Residential Density overlay** — RD1/RD2/…, or **absent** (absent → default benchmark
    **1 dwelling / 400 m²** applies)
  - **Minimum Lot Size overlay** — present/absent (LDR default min lot **600 m²**)
  - **Building height**, **Dwelling House Overlay**, **Flood — flood assessment required**,
    **acid sulfate soils** (≤5 m AHD / ≤20 m AHD), airport/infrastructure layers
- **Gotcha:** the parcel-specific City Plan web viewer can **403 automated/headless access** —
  the Will-generated Property Report PDF is the clean way in. 🤖 can then dissect the PDF.
- **Interpretation cheatsheet (LDR, GC City Plan V13):**
  - *Subdivision:* two compliant lots normally need **≥600 m² each**. Sub-400 m² pathway needs
    dual frontage **or** Min-Lot-Size mapping **or** an existing dual-occ — check Phase 3.
  - *Dual occupancy:* passes **density** if area ÷ dwellings ≥ 400 m² (822/2 = 411 ✓), but
    an LDR site that is **single-frontage and not RD1+** falls to **impact assessment**
    (harder DA, public notification) — capable ≠ automatic entitlement.
  - *Setbacks:* LDR front setback benchmark is **6 m** — the likely meaning of a vendor's
    "6 m relaxation" (a setback story, not a density one).

## Phase 4 — Zoning / historical record cross-check 🤖 (with 🧑 subscription access)
**Establish:** confirm the current zone from a second source, and any historical zone label.

- **Sites:** **Cotality** (ex-CoreLogic / RP Data) property record; **Domain.com.au** listing
  (its "zoning" line); optionally **QLD Globe** `https://qldglobe.information.qld.gov.au/`.
- **Do:** compare. Cotality's historical label (e.g. *"RESIDENTIAL A (ALBERT)"*) vs true
  duplex parcels nearby (which read *"RESIDENTIAL B (ALBERT)"*) settles Res A vs Res B claims.
- **Output:** current zone corroborated; historical label noted; any "Res B / duplex block"
  claim confirmed or retired.
- **Editorial rule:** don't repeat a zoning/development claim (e.g. "Res B", "duplex site")
  to a buyer until a **source document** supports it. Public content never names scrape
  sources — say "compiled from public records", never "Domain/onthehouse/Cotality".

## Phase 5 — Physical facts & features 🧑 + 🤖
**Establish:** the numbers we'll advertise.

- **Sources:** title/**survey plan** (frontage & dimensions), floor plan, the agent's
  measurements, a site visit.
- **Confirm & record:** **frontage** (19.9 m — from the plan, not eyeballed off an aerial),
  land shape, **internal area** (220 m²), **beds/baths** (4 / 3), notable rooms
  (downstairs MPR 6.3 × 5.1 m + kitchenette + bathroom), **workshop/shed** (7 × 6.2 m ≈ 44 m²,
  powered), parking, **year built** (~1975), renovation status (original / unrenovated).
- **Beach/lifestyle claims:** measure the actual **walking distance** before writing "walk to
  the beach" (93 Burleigh = **1 km**). State the number; don't overclaim.
- **Gotcha (Rule 8 / DB):** for anything we pull from our own database, verify the field name
  before reporting absence — `python3 scripts/db_fields.py --find <word>`.

## Phase 6 — Vendor / agent questions 🧑
**Establish:** resolve every ambiguity the records left open.

- **Do:** send the listing agent (Tyler) *specific* questions, e.g.
  *"When you say the property has a 6 m relaxation — what exactly was relaxed from 6 m to what
  distance, and is there a Council approval or survey showing it?"*
- **Output:** documented answers (or "unresolved — no document"). Keep unverifiable claims out
  of buyer-facing copy.

## Phase 7 — Photography 🧑 → 🤖
**Establish:** the image set we build creatives from.

- **Do:** collect the agent's pro photos; for twilight/enhanced versions use the twilight
  pipeline (nano-banana = `gemini-2.5-flash-image`; enhance the *light/sky*, not the house;
  pull full-res from BLOB not Domain — see memory `twilight_photo_enhancement`).
- **Output:** a **Drive folder** of final images, named/numbered in listing order (hero first).
  93 Burleigh set: `Drive → …/1_2JpRLNXgj-…` (twilight interiors + hero + workshop/rear).

## Phase 8 — List on Facebook Marketplace 🧑
**Establish:** organic Marketplace presence (separate job from paid — see Phase 9).

- **URL:** `https://www.facebook.com/marketplace/create/` (choose **Home for sale/rent** item;
  if it only offers the **rental** template, back out and pick the property-**sale** item type).
- **Tag gotcha:** add tags **one at a time — type, press Enter, repeat.** Pasting
  comma-separated text becomes one giant tag in some Marketplace versions.
- **Note:** a boosted Marketplace listing is **local-radius** by default — do **not** assume it
  reaches Sydney/Melbourne. Interstate reach is the paid campaign's job (Phase 9).

## Phase 9 — Buyer research & paid campaign (Fields Meta) 🤖 build → 🧑 go-live
**Establish:** deliberate buyer pools + creative, as a paid Ads-Manager campaign (not a boost).

- **Audience research:** migration logic from **ABS** interstate/regional data
  (`https://www.abs.gov.au/` — internal migration; QLD net-positive, NSW net-negative feeds
  the Sydney angle). Local hypothesis: acreage belt (Mudgeeraba/Worongary/Tallai/Bonogin)
  downsizing toward Burleigh.
- **Build:** click-to-Messenger **carousel** per audience hypothesis. Tooling + gotchas:
  `03_Facebook/Campaigns/2026-08-20_93Burleigh_Messenger/` (`launch_messenger_carousel.py`,
  `render_native.py`) and fix-history `[93BURLEIGH-MSG-CAROUSEL]` (2026-08-20).
  - HOUSING special ad category is mandatory for a listing ad → no age/gender targeting;
    geo by **named suburb keys**; a **city** target needs radius ≥17 km.
  - Messenger carousels need the **Send-Message CTA on every child card**.
- **Ads Manager:** `https://adsmanager.facebook.com/` · **Business Suite** (Messenger greeting +
  ice-breakers): `https://business.facebook.com/` → **Inbox → Automations**.
- **Rule 3:** log every campaign create/modify to `system_monitor.ad_decisions`. Going live is
  Will's call — never activate unattended.

---

## Website reference (quick table)

| # | What | Website / URL | Who |
|---|------|---------------|-----|
| 1 | Parcel + area + DA-association + Property Details PDF | `developmenti.goldcoast.qld.gov.au/Home/FilterDirect?filters=LandNumber=<LOTPLAN>` | 🧑 |
| 2 | Development-application history (DA/RAA/building) | `developmenti.goldcoast.qld.gov.au/` | 🧑 |
| 3 | **City Plan property report PDF** (zone + overlays) | `cityplan.goldcoast.qld.gov.au/` (via "City Plan online") | 🧑 |
| 4 | Zoning cross-check + historical zone label | Cotality (RP Data) · `domain.com.au` · `qldglobe.information.qld.gov.au` | 🤖/🧑 |
| 5 | Frontage / dimensions | Title / survey plan · floor plan · agent | 🧑 |
| 6 | Resolve open questions | Listing agent (Tyler) | 🧑 |
| 7 | Photos (twilight) | Agent photos → Drive folder | 🧑→🤖 |
| 8 | Organic listing | `facebook.com/marketplace/create/` | 🧑 |
| 9 | Migration data / paid campaign | `abs.gov.au` · `adsmanager.facebook.com` · `business.facebook.com` | 🤖/🧑 |

## Will's task checklist (per new listing)
- [ ] Get the **lot/plan** number (or address → Council land search)
- [ ] Save the **Development.i Property Details PDF** (Phase 1)
- [ ] Check **application history** — record DAs or Nil (Phase 2)
- [ ] Generate + save the **City Plan Property Report PDF** (Phase 3) ⭐
- [ ] Confirm **frontage** from the survey plan (Phase 5)
- [ ] Confirm **beach/lifestyle distances** (measure, don't guess)
- [ ] Send the agent the **specific open questions** (Phase 6)
- [ ] Drop final **photos** in a Drive folder, numbered (Phase 7)
- [ ] List on **Marketplace** (tags one at a time) (Phase 8)
- [ ] Set the **Messenger greeting + ice-breakers** in Business Suite before any paid go-live

---

## Listing Data Record — template (copy per property)

> Filled below with 93 Burleigh Street as the worked example.

**Identity**
- Address: 93 Burleigh Street, Burleigh Waters QLD 4220
- Lot / Plan: Lot 187 RP128164 · Land area: **822 m²** · Frontage: **~19.9 m** (survey)
- List price: **$1,915,000** · Agent: conjunction w/ Tyler · Listed: 2026-08

**Planning (City Plan V13, current 20 Aug 2026)**
- Zone: **Low density residential** (precinct: —)
- Residential Density overlay: **not mapped** → default density **1 dwelling / 400 m²**
- Minimum Lot Size overlay: **not mapped** (LDR default min lot 600 m²)
- Overlays: **Dwelling House Overlay**; **Flood — flood assessment required**; acid sulfate
  soils (≤5 m & ≤20 m AHD)
- Development.i applications: **Nil**
- Interpretation: no simple 1→2 freehold subdivision entitlement; a **dual occupancy** meets
  density (411 m²/dwelling) but is **impact-assessable** (single frontage, no RD1). "6 m
  relaxation" most likely = front-setback story (6 m is the LDR benchmark) — **unverified**,
  awaiting agent document. **Do not advertise** "Res B / duplex / subdivide" — evidence
  supports Res A, not Res B.

**Building & features**
- House: **220 m²**, **4 bed / 3 bath**, built ~1975, **unrenovated** (original kitchen + bath)
- Downstairs: separate zone — MPR 6.3 × 5.1 m + kitchenette + bathroom
- Workshop/shed: **7 × 6.2 m (~44 m²)**, powered · large fenced backyard
- Lifestyle: **1 km walk** to Burleigh Beach; twilight-skyline aerials show coastal setting

**Positioning / Fields angle**
- Lead: *822 m² Burleigh Waters landholding, walk to beach, big workshop, priced for its
  unrenovated condition* — not a development pitch.
- Buyer hypotheses tested: acreage-downsizers (Mudgeeraba belt) · local "buy what you can't
  renovate" · Sydney value migration.

**Assets** (the live page is the hub; everything else is a spoke)
- ⭐ **Live listing page (share this):** `https://fieldsestate.com.au/93-burleigh-street/` — public, lead-capturing, trackable, always current. Config: `scripts/conjunction_landing_configs/93-burleigh-street-burleigh-waters.json`; built file `Feilds_Website/01_Website/public/93-burleigh-street/index.html`.
- **Buyer info pack (PDF, email attachment):** `03_Facebook/Campaigns/2026-08-20_93Burleigh_Messenger/93_Burleigh_St_Information_Pack.pdf` (Drive: `…/folders/14YWteZ7ZLjoZr4-JCNR_gdamfx139Wqw`); regenerate via `make_infopack.py`.
- Photos (Drive): `…/folders/1_2JpRLNXgj-FECJgX2ObNf_VNMajQ-Fe`
- Ad review mockups (Drive): `…/folders/14YWteZ7ZLjoZr4-JCNR_gdamfx139Wqw`
- Paid campaign: `93 Burleigh St — Messenger Carousel` (`120252341379830134`, PAUSED)
- Builder + gotchas: `03_Facebook/Campaigns/2026-08-20_93Burleigh_Messenger/`
- ⚠ **Distance discipline (learned here):** measure "walk to the beach" to the **nearest point on the coastline** (the sand runs the whole coast), not to a named beach POI pin — those sit km away and overstate it. 93 Burleigh = 947 m straight-line to nearest sand → a fair **~1 km walk**. Keep the ads, PDF and live page consistent on it. The page's build-config rarity/comps analysis still references "Burleigh Heads Beach" (far pin) — reconcile if regenerated.
