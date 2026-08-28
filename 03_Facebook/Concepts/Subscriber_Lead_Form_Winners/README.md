# Subscriber Lead-Form Winners — duplicate proven traffic ads as pre-filled lead ads

Take our highest-performing **link-click / traffic** ads and re-run each as a Meta **Instant
Form (lead) ad**. The creative, headline, primary text, image/video — **everything stays
exactly the same**. The *only* change is one added step inserted between the creative and the
landing page: a minimal in-app form that asks for **name + email, both pre-filled** from the
viewer's Meta profile, behind a single statement. After they submit, the form's thank-you
screen sends them to **the same landing page the original ad pointed to** — so the funnel is
identical, plus we now capture a subscriber on the way through.

## The form (identical across all five)

- **Fields:** Full Name + Email — nothing else. Both pre-fill from the Meta profile, so the
  viewer just taps Submit.
- **No intro card. No custom questions.** Straight to the two pre-filled fields.
- **The one statement** (replaces Meta's required "Description — how the information will be
  used or shared"): **"Fields exclusive access for subscribers only"**.
- **Privacy policy:** `https://fieldsestate.com.au/privacy` (Meta-mandatory, unavoidable).
- **Thank-you screen:** button → the original ad's landing page (`VIEW_WEBSITE` +
  `follow_up_action_url`), preserving the original flow.

> ⚠ **Where the statement is placed in the form:** Meta's API has no single field literally
> labelled "Description". It's set as `question_page_custom_headline` (the line shown directly
> above the pre-filled fields). If Will wants it as the intro description or a consent
> disclaimer instead, it's a one-line change — but the form is only editable until it takes its
> first lead, so review before spend.

## The five source ads (confirmed by exact click + CPC match)

| # | Will's name | Source ad ID | Creative | Landing page | Lifetime |
|---|-------------|-------------|----------|--------------|----------|
| 1 | Traffic for homes | `120244615219210134` | VIDEO (reel `876449345413933`) | **⚠ UNKNOWN — need from Will** | 283 clicks @ $0.54 |
| 2 | Tailored: Buyer Landing Page Test | `120245339779970134` | Image link | `/for-sale-v3` | 88 @ $0.49 |
| 3 | Who buys a home for $1,550,000…? | `120244636404650134` | PHOTO | **⚠ UNKNOWN — need from Will** | 537 @ $0.13 |
| 4 | Traffic: Buyer Landing Page:v4b | `120245347869800134` | Image link | `/for-sale-v4b` | 40 @ $0.41 |
| 5 | Houses for sale — Robina, Varsity Lakes, Burleigh Waters | `120243619699320134` | Advantage+ asset_feed | `/for-sale-v4b` | 1,228 @ $0.25 |

### Per-creative reproduction notes
- **#2, #4** — single-image link ads. Faithful byte-for-byte (same `image_hash`, message,
  headline, description); CTA swapped to open the form.
- **#1 (video reel)** — reproduced via `video_data` reusing the same `video_id` + thumbnail +
  copy. Needs the original **destination URL** (not exposed by the API; it's a promoted reel).
- **#3 (photo)** — reproduced via `link_data` reusing the same image + the full "Who buys…"
  body. This one was an **engagement** ad (pixel CONTENT_VIEW), not traffic; needs its
  destination URL.
- **#5 (asset_feed / Advantage+)** — this is the one creative that **cannot be byte-identical**
  as a lead ad: it uses placement-customised Advantage+ assets (4 crops, per-placement rules).
  Reproduced as a single-image link ad using its primary asset (`9f80727ae1f2…`) + the Robina
  body + `/for-sale-v4b`. Flagged for Will — if exact Advantage+ behaviour matters here, we
  keep it as-is and skip the lead-form version, or accept the single-image reproduction.

## Structure created per ad (mirrors the source)
- New campaign `OUTCOME_LEADS`, `special_ad_categories=[]` (⚠ HOUSING-flag risk — see
  `../../Owner_Market_Carousel/launch_forms.py` header; if disapproved for Housing the
  neighborhood geofence breaks).
- New ad set: `optimization_goal=LEAD_GENERATION`, `destination_type=ON_AD`,
  `promoted_object={page_id}`, **same targeting** (age band + Robina/Varsity/Burleigh
  neighborhoods) and **same daily budget** as the source ($10/day).
- One Instant Form + the reproduced creative + the ad.

## Build / run
`launch_subscriber_lead_forms.py` — data-driven over the five `SOURCES`. Builds everything
**PAUSED**; `--activate` flips to live (Meta review). Writes IDs to `lead_form_ids.json`.

## Compliance / ops
- Editorial: creative is unchanged from already-approved ads; no new $ claims introduced.
- Log each activation to `system_monitor.ad_decisions` (CLAUDE.md §3).
- Lead field keys on webhook: `full_name`, `email` (see memory `fb_lead_field_name_mismatches`).
