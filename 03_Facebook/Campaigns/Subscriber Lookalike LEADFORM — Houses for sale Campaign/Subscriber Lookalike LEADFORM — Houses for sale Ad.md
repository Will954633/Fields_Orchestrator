# Subscriber Lookalike LEADFORM — Houses for sale Ad

_Auto-generated 2026-08-29 from the Meta Ads API. Edit freely — notes below are yours._

| | |
|---|---|
| **Ad ID** | `120252455742200134` |
| **Status** | ACTIVE |
| **Created** | 2026-08-28T21:44 |

## Campaign
- **Name:** Subscriber Lookalike LEADFORM — Houses for sale Campaign
- **ID:** `120252455741540134`
- **Objective:** OUTCOME_LEADS

## Ad set
- **Name:** Subscriber Lookalike LEADFORM — Houses for sale Ad set
- **ID:** `120252455741750134`
- **Daily budget:** $10.00/day
- **Optimization:** LEAD_GENERATION
- **Targeting:** Varsity Lakes, Robina, Burleigh Waters · age 30-65

## Creative / destination
- **Type:** SHARE
- **Destination:** `https://fieldsestate.com.au/for-sale-v4b`
- **CTA:** SEE_DETAILS

## History & intent

**Why we created it** (Arm 1 of the three-arm "Houses for sale" capture test)
- Native Instant Form capture-first: on tap, before the website, Meta opens an autofilled form (**FULL_NAME + EMAIL + PHONE**, form `1017406421335871`), thank-you "Continue" → `/for-sale-v4b`.
- The Instant Form is the native mechanism that delivers exactly what we wanted — the already-authenticated Facebook identity, autofilled — sidestepping OAuth, popups, WebView redirects, privacy-policy validation, and App Review for `email` (all web-login-only hurdles). It grew out of flattening the winning Advantage+ "Houses for sale" creative and running it as a prefilled Instant Form.

**What changed (pivots)**
- Set up (2026-08-28) as an **A/B: autofill lead-form vs the manual `/exclusive-access` gate** — which had converted **0 of 33 clicks**. Runs at equal budget/targeting against that (now-paused) control.
- Emerged as "Arm 1" once web Facebook Login was abandoned as unworkable in the FB iOS in-app WKWebView (see `03_Facebook/instant_form_vs_web_login_decision.md`).

**What we're looking for now**
- Cost-per-captured-subscriber vs the other arms. Early signal on day 1 was 19 form-opens → 0 leads (noted as early). LIVE at $10/day since 28 Aug; leads auto-captured by `fb-lead-puller.py` into `fb_leads` + CRM.

## Notes / hypothesis / performance
_(add observations, what this ad is testing, results)_

---

## 📊 Performance Findings — 28–31 Aug 2026 (analysis 2026-08-31)

**Verdict: this was the single best-performing ad in the entire account** — the cheapest
lead of all 33 delivering ads. Full method + cross-ad comparison in
[`../Lead_Attribution_Record_2026-08-25_to_30.md`](../Lead_Attribution_Record_2026-08-25_to_30.md).

### Headline result
| Metric | Value |
|--------|-------|
| Spend | $23.54 |
| Leads (name+email+phone) | **3** (Helen Montgomery, Peg Tough, Audrey Mondon) |
| **Cost per lead** | **$7.85** ← cheapest in the account |
| Live days | 08-28, 08-29, 08-30 |

### Why it won — it hits the sweet spot two other failure modes miss
| Ad | CPM | CTR | $/click | click→lead | $/lead |
|----|-----|-----|---------|-----------|--------|
| **THIS AD** | **$33.9** | **9.06%** | **$0.62** | 7.9% | **$7.85** |
| Carousel florabella | $60.6 | 6.37% | $1.79 | 11.8% | $15.22 |
| Subscriber Tailored | $36.5 | 3.56% | $1.50 | — | $22.53 |
| Subscriber Traffic v4b | $34.4 | 2.93% | $1.86 | — | $22.31 |
| Advantage+ (traffic sibling) | $3.1 | 1.58% | $0.27 | **0%** | — |
| Houses On-site GATE | $4.9 | 3.57% | $0.18 | **0%** | — |

The account has two failure modes; this ad avoids both:
- **Cheap clicks, zero conversion** — Advantage+ and GATE bought clicks at $0.18–0.27 but converted **0** (no native form / on-site gate friction).
- **Good conversion, expensive clicks** — Carousel converts best (11.8%) but its $60 CPM makes each lead 2× as costly.

This ad sits in the middle: **moderate CPM + native autofill form = cheap clicks that actually convert.**

### The three drivers (all data-confirmed)
1. **Highest CTR in the account — 9.06%**, ~3× the other landing-page ads (2.9–3.6%). The creative is a scroll-stopper: a specific number + concrete differentiator + named-competitor gap — _"**44 properties for sale in Robina right now.** Every listing has floor plan analysis, room dimensions, valuation data, and comparable sales — **things you won't find on Domain or realestate.com.au.**"_ High engagement is why clicks are cheap despite an ordinary CPM (Meta rewards CTR with cheaper delivery).
2. **Native LEADFORM with autofill** (`LEAD_GENERATION` optimization; one-tap prefilled FULL_NAME + EMAIL + PHONE, form `1017406421335871`). Minimal click→lead friction. The cheap-click ads lacking this converted nobody. Confirms learning #7 (OFFSITE/lead is the #1 lever).
3. **Fresh audience, low frequency (1.4).** The Advantage+ sibling ran at frequency **4.2** — fatiguing a small pool into 0 leads. This ad reached fresh people.

### ⚠️ IMPORTANT — the name is misleading: this is NOT a lookalike
Live targeting pulled from Meta (2026-08-31) is **broad geo + age only** — Varsity Lakes /
Robina / Burleigh Waters neighbourhoods, age 30–65. **No custom audience, no lookalike spec.**
So the lever is **not** a subscriber lookalike; it is **broad local targeting + native leadform
+ a specific, differentiated creative** — i.e. learning #8 (broad beats custom) confirmed again.

**Implication for scaling:** do **not** build a real lookalike audience expecting that to be the
magic. To replicate the win, **clone the creative formula** (specific count + "you won't find this
on Domain/realestate" differentiator) onto more native leadform ads with broad local targeting.
The ad should be renamed — "Lookalike" actively misdescribes why it works.

### Recommendation
Keep this live and use it as the **template** for buyer-side capture. Pair with **Carousel Lead v1 —
C (florabella)** (best lead *volume*, 4 leads) — the two together are the cheapest + highest-volume
buyer performers respectively; all seven other buyer ads did worse (several spent with 0 leads).

_Sample caveat: 3 leads over 3 days on $23.54 — directionally strong but thin; treat as a
confirmed template to scale-test, not a settled CPL._
