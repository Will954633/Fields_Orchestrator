# Reels: organic publishing + post-ID consolidation (paid on existing post)

_Written 2026-09-14. Both methods below were run live and verified on this date._

## The problem this fixes

**Every ad-building script in `03_Facebook` builds a fresh "dark post"** — they all pass an
inline `object_story_spec` to `POST /act_.../adcreatives` (38 references across 10+ launch
scripts, incl. `Reels/Walkthrough_Reels/launch_walkthrough_reel.py:177-185`). None use
`object_story_id`.

Consequence, verified 2026-09-14 across all 10 active/paused reel + lead creatives:
each ad spawned its **own** page post starting at **zero** engagement. The three live
walkthrough reels each carried only 4–6 reactions because each was a separate dark post,
not one post compounding. Organic likes (incl. real named locals) and paid engagement
**never pool**, and re-running a reel as a new ad throws away the likes/plays it already earned.

`object_story_id` (a.k.a. "Use existing post") is the fix: point the ad at ONE published
post so engagement compounds and real social proof ("Lisa + 2 friends like this", real like
count) rides into the paid ad.

---

## Method 1 — Publish a reel organically to the Page (`video_reels` API)

Reels are the one organic format Meta still distributes to **non-followers** (Reels feed),
so organic reels are worth posting even though static page posts are dead. Three-phase flow.

**⚠ Keep the link OUT of the caption.** An external link in a reel caption is the single
biggest organic-reach killer — Meta throttles reels that push people off-platform. Put the
link in the **first comment** instead. Also write the caption so it works for BOTH organic
and (later) paid reuse — i.e. **no "link in the comments" line either**, because a paid ad
built on this post inherits the caption but shows a CTA button, not a comment.

```python
# page token first (system-user FACEBOOK_ADS_TOKEN can't read/write page posts directly)
ptok = GET /v21.0/{PAGE}?fields=access_token          # PAGE = 889412530933297

# 1) START
start = POST /v21.0/{PAGE}/video_reels  {upload_phase:start}
vid, upload_url = start.video_id, start.upload_url

# 2) UPLOAD binary to upload_url (rupload.facebook.com)
#    headers: Authorization: OAuth {ptok} | offset: 0 | file_size: {bytes}
#    body: raw mp4 bytes

# 3) FINISH + publish
POST /v21.0/{PAGE}/video_reels {upload_phase:finish, video_id:vid,
     video_state:PUBLISHED, description:<caption>}
# -> returns post_id (page-post form: {PAGE}_{postid})
```

Then poll `GET /v21.0/{vid}?fields=status` until `video_status=ready`, and post the link
as the first comment:

```python
# ⚠ Comment on the VIDEO id, not the page post_id.
#   POST /{PAGE}_{postid}/comments  -> "(#12) singular statuses API is deprecated"
#   POST /{video_id}/comments       -> works
POST /v21.0/{vid}/comments {message:<link>}
```

Permalink is `https://www.facebook.com/reel/{vid}/`.

**Reference run (Robina walkthrough reel, 2026-09-14):**
- asset: `03_Facebook/Reels/Walkthrough_Reels/assets/Robina_Reel_Captions.mp4` (21.9s, 1080×1920, captions burned in)
- published reel `video_id 1602631378014674`, post_id `889412530933297_122128496295252069`
- permalink https://www.facebook.com/reel/1602631378014674/
- first comment: `https://fieldsestate.com.au/news/robina?play=1&utm_medium=organic`

---

## Method 2 — Build a paid ad on an EXISTING post (`object_story_id`)

**Feasibility PROVEN for reels 2026-09-14**, including a link-CTA override (the
conversion-ad shape). Two probe creatives were created against the live Robina reel post
and both were accepted, then deleted:

```python
# PROBE A — plain existing-post creative: ACCEPTED
POST /act_.../adcreatives {object_story_id: "889412530933297_122128496295252069"}
#   -> object_type VIDEO, effective_object_story_id = the reel post

# PROBE B — existing-post creative WITH link CTA override: ACCEPTED, CTA took
POST /act_.../adcreatives {
    object_story_id: "889412530933297_122128496295252069",
    call_to_action: {"type":"WATCH_MORE","value":{"link":"https://fieldsestate.com.au/news/robina?play=1"}}
}
#   -> readback shows call_to_action present with the link
```

So a conversion (`OFFSITE_CONVERSIONS`) walkthrough ad CAN run on the organic reel post with
its `?play=1` CTA. Attach that creative to an ad set the normal way.

**Caveats:**
- **Caption is inherited, not editable per-ad.** With `object_story_id` the ad's primary
  text = the post's caption. Write reel captions clean enough to serve both uses (see
  Method 1). This Robina reel's caption still has a "link in the comments" line — fine
  organically, slightly off if this exact post is later promoted.
- **What was tested = creative creation + CTA acceptance**, not a full delivering
  conversion ad. That's the key gate and it passed; residual risk (does OFFSITE_CONVERSIONS
  optimise correctly on a reel-placement existing-post ad) is low but unmeasured.
- **⚠ Do NOT use `validate_only`** in this ad account — it actually CREATES ad sets here
  (known gotcha, see memory `fb_ads_validate_only_creates_adsets`). Build paused + delete,
  or create-creative-only as a feasibility probe (inert, no spend).

---

## The strategy (go-forward)

1. **Publish the reel organically first** (Method 1) — free cold reach, seeds the canonical post.
2. **Run all paid ads for that reel on the SAME post** via `object_story_id` (Method 2) —
   engagement compounds on one post; real like count + "friends who liked" ride into paid.
3. **One canonical post per reel, forever.** Every subsequent ad reuses it.
4. **Space multiple reels out** (days apart) so they don't cannibalise reels-feed distribution.

## TODO (not yet done)
- Add an `object_story_id` / "use existing post" path to
  `Reels/Walkthrough_Reels/launch_walkthrough_reel.py` (currently inline-`object_story_spec` only),
  so the consolidated flow is scripted rather than hand-run.
- `FACEBOOK_ADS_TOKEN` (system-user) needs the **page** token to read post-level engagement;
  it has `pages_read_engagement` — the earlier "scope missing" claim was wrong (it was a
  token-type issue).
