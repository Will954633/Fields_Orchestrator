# Burleigh Waters Walkthrough Reel Ad — Click to Walkthrough

_Created 2026-09-11 by `03_Facebook/Reels/Walkthrough_Reels/launch_walkthrough_reel.py --suburb burleigh-waters`._

| | |
|---|---|
| **Ad ID** | `120252656855010134` |
| **Status** | **PAUSED — awaiting Will's go-ahead** |
| **Created** | 2026-09-11 |

## Campaign
- **Name:** Burleigh Waters Walkthrough Reel — CLICK-TO-SITE (news ?play=1, Sep 2026)
- **ID:** `120252656854380134`
- **Objective:** OUTCOME_SALES (OFFSITE_CONVERSIONS on pixel ViewContent)

## Ad set
- **Name:** Walkthrough Reel · Burleigh Waters only
- **ID:** `120252656854530134`
- **Daily budget:** $15.00/day
- **Optimization:** OFFSITE_CONVERSIONS → pixel `ViewContent` (fired by `startWalk()`)
- **Targeting:** Burleigh Waters neighborhood `2719184` ONLY · age 25+ · Advantage Audience · FB+IG Reels & Stories

## Creative / destination
- **Video:** `Burleigh_Waters_Reel_Captions.mp4` (Will's edit, Drive folder `18kEzAabEHMEVAoAZE_9t4E6SBqdRKqaV`) — 25.3s, 1080×1920, captions burned in, QC PASS, video_id `1039428352298773`
- **Cover:** `Burleigh_Waters_Reel_Cover.jpg`, image_hash `40e83da8333221cf7992b5dab82ad4a7`
- **CTA:** WATCH_MORE → `https://fieldsestate.com.au/news/burleigh-waters?play=1&utm_source=facebook&utm_medium=paid&utm_campaign=walkthrough_reel_burleigh_sep26`
- **Primary text:** follows the reel transcript (Will's words — Dec 2025 peak/flatlining framing kept as-is, directional language kept, no advice/predictions added, no $ claims)

## History & intent
- Second of three per-suburb walkthrough reel campaigns (Robina shipped 2026-09-11 earlier;
  Varsity Lakes pending Will's edit). Identical structure to Robina so per-suburb results are
  directly comparable. See the Robina campaign doc for the `?play=1` deep-link details and the
  series hypothesis.
- `/news/burleigh-waters?play=1` verified auto-starting live (fixture default = v2 cut with the
  re-recorded data-analyst intro) BEFORE the campaign was built.

## Measurement
- `scripts/ad-flow-report.py --ad-id 120252656855010134`
- utm_campaign `walkthrough_reel_burleigh_sep26`; pixel ViewContent `content_name="walkthrough"`.

## Notes / hypothesis / performance
_(add observations, results)_
