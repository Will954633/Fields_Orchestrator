# Lead Attribution Record — 25–30 Aug 2026

_Authoritative, timestamped reattribution of every Telegram lead over the analysis
period, corrected for the ads that were **actually live at the moment each lead
arrived**. Generated 2026-08-31 from Meta Ads API delivery data + `system_monitor`
lead stores + PostHog. Supersedes ad-hoc attribution in earlier tables._

Source of truth for raw leads: [`All_Telegram_Leads.md`](./All_Telegram_Leads.md)

---

## 1. Why this document exists

During 26–30 Aug, ads were switched off and replaced mid-window (Owner Market ran
three different creatives; Reel3, Easthill and Owner Market each had a same-day
pivot). A lead's real source is the ad that was **delivering at its timestamp**, not
whatever creative currently sits in the campaign folder. This record pins each lead
to the correct ad *generation* using delivery timing.

**Key reconciliation fact:** every Meta Instant-Form lead is stamped by Meta with the
exact `ad_id` that produced it at submission time — so those are switch-proof and were
already correct. All 16 form leads reconcile 1:1 against Meta delivery (Meta's headline
"leads" count double-counts `lead` + `onsite_conversion.lead_grouped`; halved, it equals
our `fb_leads` exactly — nothing missing). **All corrections below are on the
address-entry / website-funnel leads, which carry only coarse source tags.**

### Method for the weakly-attributed leads
1. **Delivery window** — an ad that spent money on day D was live on day D (Meta ad-level daily insights). A lead cannot come from an ad not yet created or already paused.
2. **First-touch UTM** — `property_reports.owner.attribution.first_touch.utm_content/campaign` where present.
3. **Time-proximity + concurrency** — with site traffic at 0–1 concurrent visitors, an anonymous address entry pins to the single person on site at that minute; a contact-lead submitted seconds earlier is the same person. Validated with PostHog per-minute active-user counts.
4. **Suburb match** — address suburb vs the suburb-specific ad variant.

---

## 2. Ad live-timeline (what was actually ON, by day)

All ad IDs are Meta ad-level. "Live days" = days with delivery (spend > 0), 25–31 Aug.

### Owner Market — Find Your Home  (THREE generations, distinct windows)
| Ad | Ad ID | Live days | Spend | Collects |
|----|-------|-----------|-------|----------|
| Carousel · Robina | `120252421179130134` | 08-26, 08-27 | $17.46 | → leadpage |
| Carousel · Varsity Lakes | `120252421180250134` | 08-26, 08-27 | $16.98 | → leadpage |
| Carousel · Burleigh Waters | `120252421181490134` | 08-26, 08-27 | $18.01 | → leadpage |
| **LEADPAGE `/find` · Robina** | `120252450438480134` | **08-28 only** | $9.78 | address (detour) |
| **LEADPAGE `/find` · Varsity Lakes** | `120252450439010134` | **08-28 only** | $10.94 | address (detour) |
| **LEADPAGE `/find` · Burleigh Waters** | `120252450439530134` | **08-28 only** | $10.11 | address (detour) |
| FORM autofill · Robina | `120252423822300134` | 08-26 → 08-29 | $40.27 | name+email+phone |
| FORM autofill · Varsity Lakes | `120252423823960134` | 08-26 → 08-30 | $68.82 | name+email+phone |
| FORM autofill · Burleigh Waters | `120252423825770134` | 08-26 → 08-30 | $58.75 | name+email+phone |

> The **LEADPAGE `/find` detour** (separate campaign "LEAD PAGE / pixel Lead") was built
> and reversed on **08-28 only** — it is the true source of the 08-28 address entries
> previously logged as generic "ownermarketleadpage".

### Easthill Valuation Reel  (THREE generations)
| Ad | Ad ID | Live days | Spend | Collects |
|----|-------|-----------|-------|----------|
| TRAFFIC (`/what-the-comps-say`) | `120252439584010134` | 08-27, 08-28, 08-29 | $11.15 | click-through |
| On-ad Form | `120252441136990134` | **08-28 only** | $11.46 | name+phone |
| LEADPAGE (`/what-the-comps-say`) | `120252455020290134` | 08-28, 08-29, 08-30 | $25.51 | address→name+phone |

### Reel3 Trust Test  (TWO generations)
| Ad | Ad ID | Live days | Spend | Collects |
|----|-------|-----------|-------|----------|
| On-ad LEADS form | `120252426727770134` | 08-26, 08-27, 08-28 | $25.56 | name+phone |
| Click-to-Site (`/your-home-evidence`) | `120252450888860134` | 08-28, 08-29, 08-30 | $30.38 | address→name+phone |

### Buyer / Subscriber suite
| Ad | Ad ID | Live days | Spend |
|----|-------|-----------|-------|
| Carousel Lead v1 — C (florabella) → Buyer Brief v3 | `120251749295410134` | 08-28, 08-29, 08-30 | $60.88 |
| Subscriber Lookalike LEADFORM — Houses for sale | `120252455742200134` | 08-28, 08-29, 08-30 | $23.54 |
| Subscriber Lead — Tailored: Buyer Landing v3 | `120252450159150134` | 08-28, 08-29, 08-30 | $22.53 |
| Subscriber Lead — Traffic: Buyer Landing v4b | `120252450169210134` | 08-28, 08-29, 08-30 | $22.31 |
| Subscriber Lead — Traffic for homes (video) | `120252450156760134` | 08-28, 08-29, 08-30 | $24.23 |
| Subscriber Lead — Who buys $1.55M (photo) | `120252450166760134` | 08-28, 08-29, 08-30 | $23.18 |
| Subscriber Lookalike — Houses for sale (Advantage+) | `120252450388660134` | 08-28, 08-29 | $11.65 |
| Houses for sale — On-site GATE | `120252463819330134` | 08-29, 08-30 | $9.40 |
| Houses for sale — Instant Form Add-On | `120252463821610134` | **08-30 only** | $3.42 |
| Price Your Own Home — Click to Site | `120252451447470134` | 08-28, 08-29, 08-30 | $20.08 |

### Property Narratives (GC test) — Instant-Form ads (owner-intent)
| Ad | Ad ID | Live days | Spend |
|----|-------|-----------|-------|
| Price Reduction — Form | `120252404487750134` | 08-25, 08-26, 08-27 | $20.13 |
| Value Gap — Form | `120252404486900134` | 08-25, 08-26, 08-27 | $22.78 |
| Nearby Sold — Form | `120252404490070134` | 08-25, 08-26, 08-27 | $19.36 |
| Scarcity — Form | `120252404488590134` | 08-25, 08-26, 08-27 | $19.52 |
| (+ WhatsApp / WA-Status variants, 08-26/27, 0 leads) | — | — | — |

---

## 3. Lead ledger — timestamped, reattributed

Confidence: ✅ certain (Meta-stamped or concurrency=1) · 🟡 strong (time+suburb+delivery) · 🔴 weak.

| # | Timestamp (UTC) | Lead / address | Contact captured | **Attributed ad (live at the time)** | Basis | Conf |
|---|-----------------|----------------|------------------|--------------------------------------|-------|------|
| 1 | 2026-08-26 06:44 | Denise Powe | name+email+phone | Property Narratives — **Price Reduction — Form** `…487750134` | Meta stamp | ✅ |
| 2 | 2026-08-26 07:45 | Teddy | name+email+phone | Property Narratives — **Price Reduction — Form** | Meta stamp | ✅ |
| 3 | 2026-08-26 20:15 | Mike Wales | name+phone | **Owner Market FORM · Burleigh Waters** `…825770134` | Meta stamp | ✅ |
| 4 | 2026-08-26 23:14 | Marjorie Henderson | name+phone | **Owner Market FORM · Burleigh Waters** | Meta stamp | ✅ |
| 5 | 2026-08-26 23:23 | 21 Gardendale Cr (addr) | address | **= Marjorie / Owner Market FORM · Burleigh** | +9 min, Burleigh, FORM live | 🟡 |
| 6 | 2026-08-27 21:28 | Richard Vivian | name+phone | **Owner Market FORM · Burleigh Waters** | Meta stamp | ✅ |
| 7 | 2026-08-27 21:36 | 5 Sugarleaf Ct (addr) | address | **NONE — internal / pre-launch test** | Price-Your-Home ad not live until 08-28; 2 on-site (testing) | ✅ |
| 8 | 2026-08-28 02:16 | Stephen Porter (Sport@lookflash) | name+email+phone | **Carousel Lead v1 — C (florabella)** `…749295410134` | Meta stamp | ✅ |
| 9 | 2026-08-28 04:33 | 65 Burleigh St (addr) | address | **Owner Market LEADPAGE `/find` · Burleigh Waters** `…439530134` | LEADPAGE live 08-28 only; Burleigh | ✅ |
| 10 | 2026-08-28 06:31 | 25 Jabiru Av (addr) | address | **Owner Market LEADPAGE `/find` · Burleigh Waters** | 08-28 only; Burleigh | ✅ |
| 11 | 2026-08-28 07:01 | 1/19 Carina Peak Dr (addr) | address | **Owner Market LEADPAGE `/find` · Varsity Lakes** `…439010134` | `utm_content=varsity`; 08-28 | ✅ |
| 12 | 2026-08-28 08:46 | 14 Eden Circuit (addr) | address | **Owner Market LEADPAGE `/find` · Varsity Lakes** | `utm_content=varsity` | ✅ |
| 13 | 2026-08-28 09:04 | 24 Banff Ct (addr) | address | **Owner Market LEADPAGE `/find` · Robina** `…438480134` | `utm_content=robina` | ✅ |
| 14 | 2026-08-28 09:28 | 196 Dunlin Dr (addr) | address | **Owner Market LEADPAGE `/find` · Burleigh Waters** | 08-28 only; Burleigh | 🟡 |
| 15 | 2026-08-28 10:03 | 89 Riverwalk Av (addr) | address | **Easthill Valuation Reel — TRAFFIC** `…439584010134` | PostHog first-touch = TRAFFIC campaign | ✅ |
| 16 | 2026-08-28 11:15 | Carrie Saunders | name+email+phone | **Subscriber Lead — Traffic v4b** `…450169210134` | Meta stamp | ✅ |
| 17 | 2026-08-28 11:49 | William (+61416529481) | name+phone | **Owner Market LEADPAGE `/find`** (find_landing) | source=fb_find_landing, 08-28 | 🟡 |
| 18 | 2026-08-28 19:35 | Sharon Lansley | name+email+phone | **Carousel Lead v1 — C (florabella)** | Meta stamp | ✅ |
| 19 | 2026-08-28 21:53 | Jennifer Ng | name+email+phone | **Owner Market FORM · Varsity Lakes** `…823960134` | Meta stamp | ✅ |
| 20 | 2026-08-28 21:54 | 25 Palma Cr (addr) | (= #19) | **= Jennifer / Owner Market FORM · Varsity** — FULL CAPTURE | +18 s, concurrency=1 | ✅ |
| 21 | 2026-08-28 22:09 | Michele (mkwoodrick) | name+email+phone | **Subscriber Lead — Tailored** `…450159150134` | Meta stamp | ✅ |
| 22 | 2026-08-28 22:24 | 23 Palma Cr (addr) | address | **NONE — Direct / organic** | PostHog first-touch = `$direct` | ✅ |
| 23 | 2026-08-29 00:19 | Helen Montgomery | name+email+phone | **Subscriber Lookalike LEADFORM** `…455742200134` | Meta stamp | ✅ |
| 24 | 2026-08-29 01:37 | Peg Tough | name+email+phone | **Subscriber Lookalike LEADFORM** | Meta stamp | ✅ |
| 25 | 2026-08-29 07:45 | Wayne Ineson | name+email+phone | **Carousel Lead v1 — C (florabella)** | Meta stamp | ✅ |
| 26 | 2026-08-29 21:00 | Michele (2nd alert) | name+email+phone | **Carousel Lead v1 — C (florabella)** | Meta stamp (dup person of #21) | ✅ |
| 27 | 2026-08-29 23:38 | Trish McCarthy | name+email+phone | **Owner Market FORM · Varsity Lakes** | Meta stamp | ✅ |
| 28 | 2026-08-29 23:39 | 11 Laura Pl (addr) | (= #27) | **= Trish / Owner Market FORM · Varsity** — FULL CAPTURE | +72 s, concurrency=1 | ✅ |
| 29 | 2026-08-30 00:36 | Scott (0405812367) | name+phone+address | **Reel3 Trust Test — Click to Site** `…450888860134` | source=fb_reel3_evidence, live 08-30 | ✅ |
| 30 | 2026-08-30 03:39 | Audrey Mondon | name+email+phone | **Subscriber Lookalike LEADFORM** | Meta stamp | ✅ |

### 5-Property-Friday signups (secondary alerts)
| Timestamp | Signup | Attributed | Note |
|-----------|--------|------------|------|
| 08-28 | sport@lookflash | **= Stephen Porter / Carousel** (#8) | dup person |
| 08-28 | flinny55@bigpond.com | for-sale-v3 ladder — **organic, no ad** | |
| 08-29 | marl.schulz@hotmail.com | for-sale-v3 ladder — **organic, no ad** | |
| 08-29 | mkwoodrick@yahoo.com | **= Michele / Subscriber Tailored** (#21) | dup person |

### Non-leads (excluded from counts)
- 08-28 "address entered on a listing page #4/#5" — 28 Riverwalk (on-site, `/property/93-riverwalk`), not a lead.
- 08-29 10:20–10:21 two abandoned address searches (`/your-home-evidence`, "Beachcomber Ct") — **Reel3 Click-to-Site** traffic that failed the address search; not a lead.

---

## 4. Totals by the ad that was actually live

| Ad (generation-specific) | Contact leads | Address-only | Total |
|--------------------------|:-------------:|:------------:|:-----:|
| Owner Market FORM · Varsity Lakes | 2 (Jennifer, Trish) | +2 own addresses | 2 people / full capture |
| Owner Market FORM · Burleigh Waters | 3 (Mike, Marjorie, Richard) | +1 (Marjorie's addr) | 3 people |
| **Owner Market LEADPAGE `/find` · Burleigh Waters** (08-28 only) | 0 | 3 | 3 |
| **Owner Market LEADPAGE `/find` · Varsity Lakes** (08-28 only) | 0 (+William?) | 2 | 2 |
| **Owner Market LEADPAGE `/find` · Robina** (08-28 only) | 0 | 1 | 1 |
| Carousel Lead v1 — C (florabella) | 4 (Stephen, Sharon, Wayne, Michele) | — | 4 |
| Subscriber Lookalike LEADFORM | 3 (Helen, Peg, Audrey) | — | 3 |
| Subscriber Lead — Tailored | 1 (Michele) | — | 1 |
| Subscriber Lead — Traffic v4b | 1 (Carrie) | — | 1 |
| Property Narratives — Price Reduction Form | 2 (Denise, Teddy) | — | 2 |
| Easthill Valuation Reel — TRAFFIC | 0 | 1 (89 Riverwalk) | 1 |
| Reel3 Trust — Click to Site | 1 (Scott, incl. address) | — | 1 |
| Direct / organic (no ad) | — | 1 (23 Palma) + 2 (5PF) | 3 |
| Internal / pre-launch test (no ad) | — | 1 (5 Sugarleaf) | 1 |

---

## 5. The three material corrections vs. prior tables

1. **The six 08-28 "Owner Market" address entries belong to the LEADPAGE `/find` detour ads** (`…438480134` / `…439010134` / `…439530134`), a separate campaign live for **that one day only** (~$31 spend) before it was reversed. Previously lumped as generic "ownermarketleadpage".
2. **5 Sugarleaf (08-27) is NOT the Price Your Own Home ad** — that ad was created 08-28 14:59, a day later. Reclassified as internal/pre-launch testing (2 concurrent visitors).
3. **Two previously-"unknown" address entries are homeowners who submitted an Owner Market FORM then entered their address ~1 min later** (Jennifer→25 Palma, Trish→11 Laura), confirmed by concurrency=1. These are the full-capture cases (name+email+phone+home address for one lead cost).

---

## 6. Known attribution gaps + fixes (carry-forward)

- **SMS/leadpage links strip the ad id.** The Owner Market funnel tags a *named* `utm_campaign=owner_market_leadpage&utm_content=<suburb>`, not Meta's `{{ad.id}}`. We recover campaign+suburb but not the exact ad id from the URL alone (delivery timing filled the gap here). **Fix:** tag SMS/leadpage links with `utm_content={{ad.id}}`.
- **Sticky first-touch on `property_reports`.** Repeat/known addresses keep their original mint `source`/`distinct_id` and don't record the converting visit's live UTM (e.g. 25 Jabiru, 196 Dunlin minted 08-17). **Fix:** stamp every submit's live UTM + distinct_id even on repeat addresses.
- **No shared key between Meta form leads and on-site address entries.** Form leads have no `distinct_id`; address entries have no contact — they only link via time+concurrency, which holds *only while traffic is thin*. **Fix:** thread a lead token (`?lead=<id>`) through the SMS/landing into the address flow and write it onto the report doc.
- **Time+concurrency method** is reliable here because the site runs 0–1 concurrent visitors. It degrades as volume grows — treat it as a stopgap until the identity-threading fix lands.

---

_Prepared by the ops agent, 2026-08-31. Raw leads: `All_Telegram_Leads.md`. Delivery
data: Meta Ads API ad-level daily insights, 25–31 Aug. Lead stores: `system_monitor.fb_leads`,
`campaign_leads`, `property_reports`, `lead_signups`. Journeys: PostHog project 348370._
