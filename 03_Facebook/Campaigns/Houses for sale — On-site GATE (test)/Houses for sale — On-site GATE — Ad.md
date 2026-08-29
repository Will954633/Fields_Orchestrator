# Houses for sale — On-site GATE — Ad

_Auto-generated 2026-08-29 from the Meta Ads API. Edit freely — notes below are yours._

| | |
|---|---|
| **Ad ID** | `120252463819330134` |
| **Status** | ACTIVE |
| **Created** | 2026-08-29T10:46 |

## Campaign
- **Name:** Houses for sale — On-site GATE (test)
- **ID:** `120252463818790134`
- **Objective:** OUTCOME_TRAFFIC

## Ad set
- **Name:** Houses for sale — On-site GATE — Ad set
- **ID:** `120252463818990134`
- **Daily budget:** $10.00/day
- **Optimization:** LINK_CLICKS
- **Targeting:** Varsity Lakes, Robina, Burleigh Waters · age 30-65

## Creative / destination
- **Type:** SHARE
- **Destination:** `https://fieldsestate.com.au/for-sale-v3?gate=1`
- **CTA:** SEE_DETAILS

## History & intent

**Why we created it** (Arm 2 of the three-arm "Houses for sale" capture test, 2026-08-29)
- Value-first buyer capture: land buyers on `/for-sale-v3?gate=1`, let them browse the real feed, then blur it and show a members gate asking for sign-in **after ~20s** — offering **Google + email only**.
- Hypothesis: a value-first, delayed gate should beat the `/exclusive-access` typed wall, which converted **0 subscribers ever**.

**What changed (pivots)**
- Directly replaces the old `/exclusive-access` Traffic ad (`120252450388660134`), which was paused on 2026-08-29 (0 conversions ever from source `fb_ad_v4b_lp`; all 4 site subscribers came from the footer).
- Built PAUSED via API as a clone of the Advantage+ traffic creative, URL repointed to `/for-sale-v3?gate=1`, then enabled to LIVE at $10/day once Will reviewed and approved.
- The gate's **Facebook "Continue with Facebook" button was removed** 2026-08-29 (now Google + email only) after web Facebook Login proved unworkable in the FB in-app browser. Kill switch: PostHog flag `forsale_softgate_v1=false`.

**What we're looking for now**
- Which arm captures more buyers, at what quality. Arm 2's captures are keyed by `lead_signups.source = for_sale_v3_softgate`.

## Notes / hypothesis / performance
_(add observations, what this ad is testing, results)_
