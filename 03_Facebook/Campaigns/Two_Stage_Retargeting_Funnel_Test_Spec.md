# Two-Stage Retargeting Funnel — Test Spec

_Written 2026-08-31. Hypothesis test: does a **warm sequence** (cheap high-reach content →
retarget the engagers with a capture ad) beat a **cold single-touch** capture ad? Grounded in
the 25–31 Aug analysis. Companion to [`Lead_Attribution_Record_2026-08-25_to_30.md`](./Lead_Attribution_Record_2026-08-25_to_30.md)._

---

## 1. Hypothesis

A person retargeted after engaging with high-reach content converts on a form/address ad at a
**materially lower cost per lead** than a cold prospect hitting the same ad first-touch.
Established benchmark: warm audiences convert ~2–5× cold. **Test target: retargeted CPL below
~$4** vs the cold benchmark **$7.85** (Subscriber Lookalike LEADFORM).

## 2. Why now — the evidence and the gap

- **We have NEVER run retargeting.** Every ad to date used broad targeting (`custom_audiences: None`). So this is an untested lever, not a proven one — treat it as an experiment.
- **The warm pools now exist** (25–31 Aug, Meta):
  | Seed | Size | Use |
  |------|------|-----|
  | Video-viewers ≥25% of the reels | ~1,051 | ✅ primary retargeting seed |
  | Post/ad engagers | ~1,612 | ✅ retargeting seed |
  | All unique people reached | ~8,913 | ✅ broad warm pool |
  | Website visitors (pixel) | ~996 | ❌ too small for site-based retargeting yet |
- **We were already building these pools and throwing them away.** The cheapest-attention ads — Advantage+ ($0.27/click) and On-site GATE ($0.18/click) — got 0 direct leads but warmed ~1,700 people we never retargeted. Those are Stage-1 pool-builders, not failures.
- **Indirect support:** the full-capture cases (Jennifer, Trish) — ad → form → *then* address — show a warmed second touch extracts more than a single event. Chain > single, observed organically.
- **Addressable pool:** ~24,000 (Meta estimate, 3 suburbs, 30–65). Retargeting re-touches a *subset* of this for higher conversion — it is an **efficiency play, not a reach play.**

## 3. Prerequisites (do first)

1. **Settle the ~$254.08 unsettled account balance** (`account_status: 3`). Nothing delivers until billing clears.
2. Ensure the **Meta pixel + CAPI** fire the intended conversion events (form Lead; on-site address entry for the seller arm). Video-view + engagement custom audiences need no pixel — they build from Meta-native data.

## 4. Audiences to create (Meta custom audiences)

| # | Audience | Definition | Notes |
|---|----------|------------|-------|
| A1 | **Reel video-viewers** | Watched ≥25% (or ThruPlay) of ANY Fields video ad, last 365 days | Primary warm seed (~1,051 and growing) |
| A2 | **Page/ad engagers** | Everyone who engaged with the FB Page or IG account, last 365 days | ~1,612+; broadest cheap warm pool |
| A3 | **Website visitors** | All `fieldsestate.com.au` visitors, last 180 days | Hold until pool > ~1,000 (currently ~996) |
| A4 | **Lead excluders** | Everyone already in `fb_leads` / submitted a form | **Exclude** from Stage 2 so we don't pay to re-capture existing leads |

Combined warm audience for Stage 2 = **(A1 OR A2 OR A3) MINUS A4.**

## 5. Structure

```
── STAGE 1 · COLD REACH (pool-builders) ───────────────────────────
Campaign: "Stage1 — Reach/VideoViews" · objective OUTCOME_AWARENESS or VIDEO_VIEWS
└─ Ad set: 3 suburbs, 25–65, broad, optimize THRUPLAY / REACH (cheap)
   ├─ "Houses for sale" creative (9% CTR winner)
   ├─ Reel3 / Easthill / Price-Your-Home reels (video → builds A1)
   Goal: cheap attention, refill the warm pool. NOT judged on leads.

── STAGE 2 · WARM RETARGET (capture) ──────────────────────────────
Campaign: "Stage2 — Retarget LEADS" · objective OUTCOME_LEADS
└─ Ad set: audience = (A1 OR A2 OR A3) MINUS A4 · optimize LEAD_GENERATION
   ├─ Subscriber Lookalike LEADFORM  (proven $7.85 cold — the A/B control creative)
   └─ Carousel florabella            (proven volume)
   Goal: capture name+email+phone from warmed people. Judged on CPL.
```

Keep this **separate from the cold buyer campaign** (the existing Lookalike+Carousel cold ad set)
so the A/B is clean: **same creatives, cold audience vs warm audience → compare CPL.**

## 6. Budgets (within safety caps: $50/day/campaign, $500/mo total)

- Stage 1: ~$5–10/day (cheap reach; the whole point is low cost-per-engaged-view).
- Stage 2: ~$10–15/day once A1/A2 exceed ~1,000 people (Meta needs scale to deliver a retarget set).
- Do not start Stage 2 until the warm audience is ≳1,000; below that Meta under-delivers.

## 7. Success criteria & measurement

**Primary:** Stage-2 (warm) CPL vs cold benchmark.
| | Cold (control) | Warm (test) | Verdict |
|---|---|---|---|
| Lookalike LEADFORM CPL | $7.85 | _measure_ | Win if warm < ~$5–6 |

- **Secondary:** Stage-2 CTR and click→lead rate vs cold; pool growth rate (A1/A2 size per week).
- **Attribution:** Stage-2 leads land in `fb_leads` with the retarget ad's `ad_id` (switch-proof). Tag Stage-1 links with `utm_content={{ad.id}}` if any drive to site.
- **Run length:** ≥2 weeks or until Stage 2 has ≥15–20 leads (thin-sample caution — current CPLs rest on 1–4 leads each; do not call a winner on <10).

## 8. Caveats

- **Efficiency, not reach.** The warm pool is a subset of the finite ~24k. Retargeting lowers CPL on people already touched; it does not add new prospects. Stage 1 must run continuously to refill.
- **Small-scale slow burn.** Only a few hundred fresh video-viewers/week — the retarget layer is small-but-cheap, compounding over months.
- **Frequency discipline.** In a 24k pool, watch retarget frequency (refresh creative past ~3–4); a warm audience fatigues faster because it is small.
- **Exclude existing leads (A4)** or you will pay to re-serve people who already converted.

## 9. One-line summary

Stop discarding the warm audience the cheap-reach ads already build. Point the proven $7.85
LEADFORM creative at video-viewers + engagers (minus existing leads), and measure whether warm
CPL beats cold. That single comparison decides whether sequenced funnels become the model.

---

_Data basis: Meta Ads API (ad-level insights + video/engagement actions, 25–31 Aug),
audience estimate `delivery_estimate`, PostHog project 348370 (site pools), `system_monitor.fb_leads`._
