# Facebook Ad Creative Creation Script — Scope Only (2026-07-23)

**Status: scoped, not built.** Self-audit point 8 named this as a real capability gap: every existing
FB script either reads data (`facebook-ads-insights.py`, `fb-lead-puller.py`, `fb-attribution-builder.py`)
or posts organic content (`fb-page-post.py`, `fb-content-scheduler.py`) — nothing creates a new AD
CREATIVE or a new AD object. When a genuinely new ad test is needed (not just new copy on an existing
creative, which just means editing `ad_profiles` fields directly), there's no tested path to do it
safely; it would currently mean either manual work in Ads Manager or a hand-rolled, untested API call.

## What already exists to build on (verified, not assumed)
- **Auth:** `FACEBOOK_ADS_TOKEN` env var, `graph.facebook.com/v18.0` base, plain `requests` calls (no
  SDK) — the pattern every FB script already uses (`facebook-ads-insights.py`).
- **Content upload precedent:** `fb-page-post.py`'s `post_photo_to_page()`/`post_photo_url_to_page()`
  already POST an image to `{PAGE_ID}/photos` and get back a media ID — the same mechanic an ad
  creative's image needs, just targeting a different endpoint (`act_{AD_ACCOUNT_ID}/adimages` for ad
  creative images specifically, not the page's own photo album).
- **Safety-rail precedent:** `google_ads_manager.py` is the direct sibling to mirror — one function per
  discrete action (`create_campaign`, `create_ad_group`, `add_keywords`, `set_campaign_status`, etc.),
  a single `main()` CLI dispatch, and (per CLAUDE.md) **every campaign starts PAUSED** regardless of
  what's requested. A new FB script should copy this shape exactly, not invent a new one.

## The two functions actually needed (Marketing API, v18.0)
1. **Upload creative asset:** `POST act_{ad_account_id}/adimages` (image) — returns an image hash to
   reference. (Video ads would need `act_{ad_account_id}/advideos` instead — out of scope for v1, the
   account's proven top performers are image-based per this session's ad_downstream check.)
2. **Create the ad creative:** `POST act_{ad_account_id}/adcreatives` with an `object_story_spec`
   (page_id + link_data: message, link, image_hash, call_to_action) — this is the reusable "creative"
   object, separate from the ad itself.
3. **Create the ad, attached to an EXISTING adset:** `POST act_{ad_account_id}/ads` with
   `adset_id` (an already-approved, already-targeted, already-capped adset — e.g. the current AYH
   adset) + the new `creative_id` from step 2, **`status: PAUSED`** always, regardless of any
   `--force-active` flag someone might be tempted to add.

**Deliberately NOT in v1 scope:** creating new campaigns or adsets (targeting/budget/geo decisions
stay manual in Ads Manager, same as today), video creative, carousel-format creative (the buyer-brief
carousel concept is still just a concept — this script would only need to support it once that's
approved and ready to build), and anything that flips a real ad to ACTIVE — that stays a separate,
explicit, already-established action (`set_campaign_status`-equivalent, which already exists as a
pattern to copy from `google_ads_manager.py` if/when needed for FB).

## Safety rails carried over from the existing autonomy rules
- New ad creative/ads **always start PAUSED** — matches the Google Ads convention already in CLAUDE.md,
  and the existing DOER-tier rule that ad launches must respect the $15/day/$500-week caps before ever
  going active.
- Every create action logs to `system_monitor.ad_decisions` (CLAUDE.md rule 3) — same as every existing
  ad action.
- If used for a measurable copy/format test, log to `change_ledger.py` with a baseline metric before
  activating, same discipline as every other test this session.

## Why this is scope-only right now, not a build
Building this means writing real Marketing API calls that, once used, touch live ad creative and real
account structure — Will asked specifically for scoping only today, with the actual build left for a
dedicated session where it can be tested properly (a test image upload against the real ad account,
confirming the creative renders correctly before it's trusted for anything real).
