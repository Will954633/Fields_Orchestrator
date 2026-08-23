# 93 Burleigh Street, Burleigh Waters — listing dossier

**Status:** live · conjunction with **Tyler Benson (Coomera Realty)** · guide **$1,915,000** · 822 m²
**Slug:** `93-burleigh-street-burleigh-waters` · **Mongo:** `Gold_Coast.burleigh_waters` (`690bd81b8b8f546592617fbb`)

The single index for this listing. Program-level workflow and rules live in
[`../../README.md`](../../README.md); don't duplicate them here.

## Live assets (share these with buyers)
| Asset | Where | Use |
|---|---|---|
| **Landing page (hub)** | https://fieldsestate.com.au/93-burleigh-street/ | default link in DMs — public, lead-capturing, trackable |
| **Buyer info pack (PDF)** | [`handouts/93_Burleigh_St_Information_Pack.pdf`](handouts/93_Burleigh_St_Information_Pack.pdf) | email attachment |
| **Messenger carousel ads** | [`ads/`](ads/) — mockups + [`ads/AD_IDS.md`](ads/AD_IDS.md) | paid top-of-funnel (PAUSED) |

## Thinking artefacts
- [`PLAN.md`](PLAN.md) — master dossier + task list
- [`BUYER_THESIS.md`](BUYER_THESIS.md) — one-page buyer thesis
- [`INSPECTION_BRIEF.md`](INSPECTION_BRIEF.md) — what to document on site
- [`CAMPAIGN_COPY.md`](CAMPAIGN_COPY.md) — Marketplace + group post variants

## Media
- `photos/original/` — listing photos (kept) · `photos/twilight/` — enhanced (light/sky only)
- Full-res enhanced set also in Drive: `folders/1_2JpRLNXgj-FECJgX2ObNf_VNMajQ-Fe`

## Key facts (buyer-facing, verified)
822 m² · ~19.9 m frontage · 220 m² home (4 bed / 3 bath) · downstairs MPR 6.3×5.1 m + kitchenette +
bathroom · **44 m² powered workshop** · built c.1975, **unrenovated** · **~1 km flat walk** to the
sand (947 m straight-line to the nearest coastline — measure to the coast, not a beach POI).

Planning: Low density residential; no RD/min-lot overlay; Dwelling House Overlay + flood assessment
required; Development.i **Nil**. Dual-occ meets density (411 m²/dwelling) but is impact-assessable
(single frontage, no RD1). **Do not advertise duplex/subdivide.** "6 m relaxation" = likely a
front-setback story, unverified — outstanding question for Tyler.

## Comparable range (public sale records, 4-bed Burleigh Waters)
$1,710,000 – $2,350,000 (renovated cluster ~$2,100,000); $1,915,000 sits below the cluster on condition.

## ⚠ Open items / reconciliation
- **Agent attribution:** landing page ✓, info pack PDF ✓ (now names Tyler Benson, Coomera Realty).
  Ad primary text: source copy updated in `launch_messenger_carousel.py`, but the **creatives could
  not be regenerated** — the Meta ad account is **status 3 (unsettled, ~$157 unpaid balance)** and
  blocks writes. Settle the balance in Ads Manager billing, then regenerate creatives + re-point ads.
- **Claim gate:** RUN — see [`dd/CLAIM_GATE_signoff.md`](dd/CLAIM_GATE_signoff.md). Fixed "$2.1M"→
  "$2,100,000"; the single "$1,915,000" is signed off as a **list price, not a valuation**; the comps
  pre-flight is satisfied by the info pack + landing page. Cleared for publish once Tyler + billing OK.
- ⚠ **Ad account blocker:** status 3 / unpaid balance blocks BOTH creative edits AND campaign
  activation until settled.
- **Comps provenance:** the PDF comps were pulled ad-hoc; regenerate via `comparable_set.py` (has the
  adversarial claim test + the beach-distance threshold-sensitivity warning) before the next refresh.
- **Landing config vs live page:** the live page is hand-built. The generator **config**
  (`scripts/conjunction_landing_configs/93-burleigh-street-burleigh-waters.json`) still references the
  far "Burleigh Heads Beach" pin for its rarity/comps analysis — reconcile before any `--write-tree`.
- **Tyler:** confirm the "6 m relaxation" meaning + any survey/approval doc.
