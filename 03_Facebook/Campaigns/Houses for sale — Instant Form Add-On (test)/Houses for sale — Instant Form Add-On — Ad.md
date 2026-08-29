# Houses for sale — Instant Form Add-On — Ad

_Auto-generated 2026-08-29 from the Meta Ads API. Edit freely — notes below are yours._

| | |
|---|---|
| **Ad ID** | `120252463821610134` |
| **Status** | ACTIVE |
| **Created** | 2026-08-29T10:47 |

## Campaign
- **Name:** Houses for sale — Instant Form Add-On (test)
- **ID:** `120252463821300134`
- **Objective:** OUTCOME_TRAFFIC

## Ad set
- **Name:** Houses for sale — Instant Form Add-On — Ad set
- **ID:** `120252463821390134`
- **Daily budget:** $10.00/day
- **Optimization:** LINK_CLICKS
- **Targeting:** Varsity Lakes, Robina, Burleigh Waters · age 30-65

## Creative / destination
- **Type:** SHARE
- **Destination:** `https://fieldsestate.com.au/for-sale-v3`
- **CTA:** LEARN_MORE

## History & intent

**Why we created it** (Arm 3 of the three-arm "Houses for sale" capture test, 2026-08-29)
- Buyer-facing traffic ad. Land buyers on plain `/for-sale-v3`, then Meta's **Instant Form Browser Add-On** pops a native, autofilled instant form from inside the FB/IG in-app browser **on first scroll**; if ignored it minimises to a footer.
- The appeal: "browse-first then frictionless capture" without any of the web-login problems — no website code (Meta renders the form), no OAuth/popup/WebView redirect. Will found the Browser Add-On feature on 2026-08-29, which is what added this third arm.

**What changed (pivots)**
- Descends from two dead ends: the `/exclusive-access` typed name+email wall (0 subscribers ever) and an attempt at web "Continue with Facebook", abandoned because Facebook Login can't work reliably in the iOS in-app WKWebView. See `03_Facebook/instant_form_vs_web_login_decision.md`.
- Clean separation from Arm 2 (same landing page): the on-site gate is armed ONLY by `?gate=1`. Arm 3 uses **plain** `/for-sale-v3` so our gate stays dormant and only Meta's add-on fires — they must never share a URL or they'd double-gate.

**What we're looking for now**
- Which of the three arms captures more buyers, and at what quality (Arm 3 leads carry `fields_arm=browser_addon`).
- ⚠ Per the decision record (§7a), as of 2026-08-29 the add-on form (`934428149716778`) was built + published but **not yet attached to the ad**, so the arm was held until the Browser Add-On toggle is enabled in Ads Manager (not reliably settable via the Marketing API) — until then it would spend with zero capture.

## Notes / hypothesis / performance
_(add observations, what this ad is testing, results)_
