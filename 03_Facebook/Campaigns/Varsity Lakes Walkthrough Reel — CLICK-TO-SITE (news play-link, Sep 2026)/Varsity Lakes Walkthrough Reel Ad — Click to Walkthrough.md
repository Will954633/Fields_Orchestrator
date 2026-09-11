# Varsity Lakes Walkthrough Reel Ad — Click to Walkthrough

_Created 2026-09-11 by `03_Facebook/Reels/Walkthrough_Reels/launch_walkthrough_reel.py --suburb varsity-lakes`._

| | |
|---|---|
| **Ad ID** | `120252657094840134` |
| **Status** | **PAUSED — awaiting Will's go-ahead** |
| **Created** | 2026-09-11 |

## Campaign
- **Name:** Varsity Lakes Walkthrough Reel — CLICK-TO-SITE (news ?play=1, Sep 2026)
- **ID:** `120252657092560134`
- **Objective:** OUTCOME_SALES (OFFSITE_CONVERSIONS on pixel ViewContent)

## Ad set
- **Name:** Walkthrough Reel · Varsity Lakes only
- **ID:** `120252657093310134`
- **Daily budget:** $15.00/day
- **Optimization:** OFFSITE_CONVERSIONS → pixel `ViewContent` (fired by `startWalk()`)
- **Targeting:** Varsity Lakes neighborhood `2674227` ONLY · age 25+ · Advantage Audience · FB+IG Reels & Stories

## Creative / destination
- **Video:** `Varsity_Lakes_Reel_Captions.mp4` (Will's edit, Drive folder `18kEzAabEHMEVAoAZE_9t4E6SBqdRKqaV`) — 27.9s, 1080×1920, captions burned in (sky-positioned above his head in this framing), QC PASS, video_id `1614581453560247`
- **Cover:** `Varsity_Lakes_Reel_Cover.jpg`, image_hash `c2a5542a215ca6f9556e23b53500a218`
- **CTA:** WATCH_MORE → `https://fieldsestate.com.au/news/varsity-lakes?play=1&utm_source=facebook&utm_medium=paid&utm_campaign=walkthrough_reel_varsity_sep26`
- **Primary text:** follows the reel transcript (Will's words — stronger-performer/flatlined framing kept, directional language kept, no advice/predictions added, no $ claims)

## History & intent
- Third of three per-suburb walkthrough reel campaigns (Robina + Burleigh Waters shipped
  2026-09-11 earlier). Identical structure so per-suburb results are directly comparable.
  See the Robina campaign doc for the `?play=1` deep-link details and the series hypothesis.
- `/news/varsity-lakes?play=1` verified auto-starting live BEFORE the campaign build — the
  Varsity v2 walkthrough (08-Sep re-take) became the default paramless fixture earlier today.

## Measurement
- `scripts/ad-flow-report.py --ad-id 120252657094840134`
- utm_campaign `walkthrough_reel_varsity_sep26`; pixel ViewContent `content_name="walkthrough"`.

## Notes / hypothesis / performance
_(add observations, results)_
