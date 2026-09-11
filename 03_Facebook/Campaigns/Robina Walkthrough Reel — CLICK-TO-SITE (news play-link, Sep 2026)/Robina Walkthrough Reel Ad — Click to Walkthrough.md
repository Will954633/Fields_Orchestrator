# Robina Walkthrough Reel Ad — Click to Walkthrough

_Created 2026-09-11 by `03_Facebook/Reels/Walkthrough_Reels/launch_walkthrough_reel.py --suburb robina`._

| | |
|---|---|
| **Ad ID** | `120252656428850134` |
| **Status** | ACTIVE — activated 2026-09-11 on Will's go, $15/day |
| **Created** | 2026-09-11 |

## Campaign
- **Name:** Robina Walkthrough Reel — CLICK-TO-SITE (news ?play=1, Sep 2026)
- **ID:** `120252656427560134`
- **Objective:** OUTCOME_SALES (OFFSITE_CONVERSIONS on pixel ViewContent)

## Ad set
- **Name:** Walkthrough Reel · Robina only
- **ID:** `120252656427940134`
- **Daily budget:** $15.00/day
- **Optimization:** OFFSITE_CONVERSIONS → pixel `ViewContent` (fired by `startWalk()` — the conversion IS "walkthrough actually started")
- **Targeting:** Robina neighborhood `2687074` ONLY (one campaign per suburb, per Will 2026-09-11) · age 25+ · Advantage Audience · FB+IG Reels & Stories

## Creative / destination
- **Video:** `Robina_Reel_Captions.mp4` (Will's edit, Drive folder `18kEzAabEHMEVAoAZE_9t4E6SBqdRKqaV`) — 21.9s, 1080×1920, captions burned in, video_id `1614019167088683`
- **Cover:** `Robina_Reel_Cover.jpg`, image_hash `7e15e9efd94bfcd2d859796427fc711f`
- **CTA:** WATCH_MORE → `https://fieldsestate.com.au/news/robina?play=1&utm_source=facebook&utm_medium=paid&utm_campaign=walkthrough_reel_robina_sep26`
- **Primary text:** follows the reel transcript (Will's words, directional language kept, no advice/predictions added)

## The deep link (`?play=1`)
Shipped 2026-09-11 (website commits `ff38844b`, `8cea7590`): `/news/<suburb>?play=1` auto-starts the
Walkthrough-with-Will on page load. Unmuted autoplay is blocked without a gesture in mobile
browsers (incl. FB/IG in-app webview), so the engine falls back to **muted playback + a
"🔊 Tap for sound" chip**. `startWalk()` now also fires pixel `ViewContent`
(`content_name="walkthrough"`) — the optimization event for this campaign.

## History & intent

**Why we created it**
- Will's reel series (Robina done; Varsity Lakes + Burleigh Waters still being edited) teases
  "my latest Robina property market update report" — this campaign closes the gap between the
  tease and the content by landing viewers directly IN the playing walkthrough.
- Hypothesis: no click gap between creative and content → cheaper walkthrough starts than prior
  click-to-site reels, because the landing keeps the exact promise of the creative.
- One campaign per suburb so spend maps 1:1 to the suburb whose walkthrough it promotes.
  Varsity Lakes (`2674227`) and Burleigh Waters (`2719184`) campaigns launch from the same
  script when Will's edits land in the Drive folder.
- No $ claims in ad copy → no valuation-methodology pre-flight required (Rule 5 check done).

**Measurement**
- `scripts/ad-flow-report.py --ad-id 120252656428850134` for live PostHog flow.
- utm_campaign `walkthrough_reel_robina_sep26`; pixel ViewContent `content_name="walkthrough"`.

## Notes / hypothesis / performance
_(add observations, what this ad is testing, results)_
