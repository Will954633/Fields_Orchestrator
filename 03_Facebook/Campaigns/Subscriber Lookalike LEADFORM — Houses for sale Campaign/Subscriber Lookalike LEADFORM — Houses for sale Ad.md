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
