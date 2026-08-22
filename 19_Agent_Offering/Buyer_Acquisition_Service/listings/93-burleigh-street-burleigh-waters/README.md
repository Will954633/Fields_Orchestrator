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
$1,710,000 – $2,350,000 (renovated cluster ~$2.1M); $1,915,000 sits below the cluster on condition.

## ⚠ Open items / reconciliation
- **Agent attribution:** the landing page names Tyler Benson / Coomera Realty. Confirm the **info
  pack PDF** and **ad copy** also attribute the listing agent (program rule: attribute on *every*
  public asset). Currently they say "working alongside the listing agent" without the name — fix.
- **Claim gate:** run `claim_gate.py --slug 93-burleigh-street-burleigh-waters` over the ad + PDF
  claims; they were drafted outside the gate this session.
- **Comps provenance:** the PDF comps were pulled ad-hoc; regenerate via `comparable_set.py` (has the
  adversarial claim test + the beach-distance threshold-sensitivity warning) before the next refresh.
- **Landing config vs live page:** the live page is hand-built. The generator **config**
  (`scripts/conjunction_landing_configs/93-burleigh-street-burleigh-waters.json`) still references the
  far "Burleigh Heads Beach" pin for its rarity/comps analysis — reconcile before any `--write-tree`.
- **Tyler:** confirm the "6 m relaxation" meaning + any survey/approval doc.
