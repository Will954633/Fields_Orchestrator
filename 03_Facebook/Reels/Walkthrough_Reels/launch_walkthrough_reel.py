#!/usr/bin/env python3
"""
launch_walkthrough_reel.py — Suburb walkthrough reels → CLICK-TO-SITE into the PLAYING walkthrough.

One campaign per suburb (Will, 2026-09-11: "each will be promoted only in its corresponding
suburb"). The reel is Will's 9:16 market-update teaser (edited on the Mac session, handed off
via Drive folder 18kEzAabEHMEVAoAZE_9t4E6SBqdRKqaV); the CTA links to
https://fieldsestate.com.au/news/<suburb>?play=1 which auto-starts the on-page walkthrough
(engine deep link shipped 2026-09-11, muted-autoplay fallback + tap-for-sound).

Optimises OFFSITE_CONVERSIONS on pixel ViewContent — startWalk() fires ViewContent
(content_name="walkthrough"), so the conversion IS "the walkthrough actually started".
Playbook learning #7: OFFSITE_CONVERSIONS is the #1 lever for website sessions.

Everything is created PAUSED. Activate only on Will's go-ahead.

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_walkthrough_reel.py --suburb robina             # build PAUSED
  python3 launch_walkthrough_reel.py --suburb robina --activate  # only on Will's go-ahead
"""
import os, sys, json, time, argparse, requests

TOK = os.environ["FACEBOOK_ADS_TOKEN"]
ACT = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
PIXEL = "1491613936314260"  # Fields primary pixel (the only one)
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))

DAILY_BUDGET_CENTS = 1500  # AUD $15/day — same as the other reel campaigns
CTA_TYPE = "WATCH_MORE"    # "link into the playing walkthrough"; LEARN_MORE fallback

SUBURBS = {
    "robina": {
        "label": "Robina",
        "neighborhood_key": "2687074",
        "video": os.path.join(HERE, "assets", "Robina_Reel_Captions.mp4"),
        "thumb": os.path.join(HERE, "assets", "Robina_Reel_Cover.jpg"),
        "landing": ("https://fieldsestate.com.au/news/robina?play=1"
                    "&utm_source=facebook&utm_medium=paid"
                    "&utm_campaign=walkthrough_reel_robina_sep26"),
        # Post copy follows the reel transcript (Will's words, directional language kept —
        # no advice, no predictions added; CLAUDE.md §5).
        "primary_text": (
            "The Robina property market has seen a gradual decline this year — but one "
            "metric in the data has really shot up in the last couple of months, and it "
            "gives us some insight into what buyer demand looks like right now.\n\n"
            "In my latest Robina market update I walk through that metric, and another "
            "that gives a strong signal on where this market's headed next — chart by "
            "chart, on screen. Tap to watch the full walkthrough."
        ),
        "headline": "Robina Market Update — Guided Walkthrough",
    },
    # Varsity Lakes + Burleigh Waters: Will is still editing those reels (2026-09-11).
    # Add "video"/"thumb" once their finals land in the Drive folder, then run per suburb.
    "varsity-lakes": {
        "label": "Varsity Lakes",
        "neighborhood_key": "2674227",
        "landing": ("https://fieldsestate.com.au/news/varsity-lakes?play=1"
                    "&utm_source=facebook&utm_medium=paid"
                    "&utm_campaign=walkthrough_reel_varsity_sep26"),
    },
    "burleigh-waters": {
        "label": "Burleigh Waters",
        "neighborhood_key": "2719184",
        "landing": ("https://fieldsestate.com.au/news/burleigh-waters?play=1"
                    "&utm_source=facebook&utm_medium=paid"
                    "&utm_campaign=walkthrough_reel_burleigh_sep26"),
    },
}


def _call(method, path, token, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = token
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=120, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j


def ids_path(slug): return os.path.join(HERE, f"walkthrough_reel_{slug}_ids.json")


def _save(slug, state): json.dump(state, open(ids_path(slug), "w"), indent=2)


def upload_video(cfg):
    with open(cfg["video"], "rb") as fh:
        r = requests.post(f"{B}/{ACT}/advideos",
                          data={"access_token": TOK,
                                "name": f"{cfg['label']} Walkthrough Reel (Sep 2026)"},
                          files={"source": fh}, timeout=600)
    j = r.json()
    if j.get("error"): raise RuntimeError(f"advideo FAILED: {j['error']}")
    vid = j["id"]
    for _ in range(60):
        s = _call("GET", vid, TOK, fields="status")
        st = (s.get("status") or {}).get("video_status")
        print(f"   video {vid} status={st}")
        if st == "ready": return vid
        if st == "error": raise RuntimeError(f"video processing error: {s}")
        time.sleep(10)
    raise TimeoutError("video not ready after 10 min")


def upload_thumb(cfg):
    with open(cfg["thumb"], "rb") as fh:
        r = requests.post(f"{B}/{ACT}/adimages", data={"access_token": TOK},
                          files={"cover.jpg": fh}, timeout=120)
    j = r.json()
    if j.get("error"): raise RuntimeError(f"adimage FAILED: {j['error']}")
    return list(j["images"].values())[0]["hash"]


def create_campaign(cfg):
    return _call("POST", f"{ACT}/campaigns", TOK,
                 name=f"{cfg['label']} Walkthrough Reel — CLICK-TO-SITE (news ?play=1, Sep 2026)",
                 objective="OUTCOME_SALES", special_ad_categories=[],
                 is_adset_budget_sharing_enabled=False,
                 status="PAUSED")["id"]


def create_adset(cfg, campaign_id):
    targeting = {
        "geo_locations": {"neighborhoods": [{"key": cfg["neighborhood_key"]}],
                          "location_types": ["home"]},
        "age_min": 25,
        "targeting_automation": {"advantage_audience": 1},
        "publisher_platforms": ["facebook", "instagram"],
        "facebook_positions": ["facebook_reels", "story"],
        "instagram_positions": ["reels", "story"],
    }
    return _call("POST", f"{ACT}/adsets", TOK,
                 name=f"Walkthrough Reel · {cfg['label']} only",
                 campaign_id=campaign_id,
                 daily_budget=DAILY_BUDGET_CENTS,
                 billing_event="IMPRESSIONS",
                 optimization_goal="OFFSITE_CONVERSIONS",
                 destination_type="WEBSITE",
                 promoted_object={"pixel_id": PIXEL, "custom_event_type": "CONTENT_VIEW"},
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 targeting=targeting,
                 status="PAUSED")["id"]


def create_creative(cfg, video_id, thumb_hash, cta_type=CTA_TYPE):
    oss = {"page_id": PAGE, "video_data": {
        "video_id": video_id,
        "image_hash": thumb_hash,
        "message": cfg["primary_text"],
        "title": cfg["headline"],
        "call_to_action": {"type": cta_type, "value": {"link": cfg["landing"]}},
    }}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name=f"{cfg['label']} Walkthrough Reel creative", object_story_spec=oss)["id"]


def create_ad(cfg, adset_id, creative_id):
    return _call("POST", f"{ACT}/ads", TOK,
                 name=f"{cfg['label']} Walkthrough Reel Ad — Click to Walkthrough",
                 adset_id=adset_id, creative={"creative_id": creative_id}, status="PAUSED")["id"]


def build(slug):
    cfg = SUBURBS[slug]
    if not cfg.get("video") or not os.path.exists(cfg["video"]):
        raise SystemExit(f"{cfg['label']}: reel asset not staged yet (waiting on Will's edit)")
    state = json.load(open(ids_path(slug))) if os.path.exists(ids_path(slug)) else {}
    if not state.get("video_id"):
        state["video_id"] = upload_video(cfg); print("· video:", state["video_id"]); _save(slug, state)
    if not state.get("thumb_hash"):
        state["thumb_hash"] = upload_thumb(cfg); print("· thumb:", state["thumb_hash"]); _save(slug, state)
    if not state.get("campaign_id"):
        state["campaign_id"] = create_campaign(cfg); print("· campaign:", state["campaign_id"]); _save(slug, state)
    if not state.get("adset_id"):
        state["adset_id"] = create_adset(cfg, state["campaign_id"]); print("· adset:", state["adset_id"]); _save(slug, state)
    if not state.get("creative_id"):
        try:
            state["creative_id"] = create_creative(cfg, state["video_id"], state["thumb_hash"])
        except RuntimeError as e:
            if "WATCH_MORE" in str(e) or "call_to_action" in str(e):
                print("  WATCH_MORE rejected → falling back to LEARN_MORE"); state["cta"] = "LEARN_MORE"
                state["creative_id"] = create_creative(cfg, state["video_id"], state["thumb_hash"], "LEARN_MORE")
            else:
                raise
        print("· creative:", state["creative_id"]); _save(slug, state)
    if not state.get("ad_id"):
        state["ad_id"] = create_ad(cfg, state["adset_id"], state["creative_id"]); print("· ad:", state["ad_id"]); _save(slug, state)
    print(f"\nBUILT — ALL PAUSED. CTA: {state.get('cta', CTA_TYPE)} → {cfg['landing']}\nIDs -> {ids_path(slug)}")
    return state


def activate(slug):
    ids = json.load(open(ids_path(slug)))
    _call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("campaign ACTIVE")
    _call("POST", ids["adset_id"], TOK, status="ACTIVE"); print("adset ACTIVE")
    _call("POST", ids["ad_id"], TOK, status="ACTIVE"); print(f"ad ACTIVE — $15/day LIVE → {SUBURBS[slug]['landing']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", required=True, choices=sorted(SUBURBS))
    ap.add_argument("--activate", action="store_true")
    a = ap.parse_args()
    activate(a.suburb) if a.activate else build(a.suburb)
