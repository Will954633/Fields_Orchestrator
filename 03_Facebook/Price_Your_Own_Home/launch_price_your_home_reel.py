#!/usr/bin/env python3
"""
launch_price_your_home_reel.py — "Could you accurately price your own home?" reel as a
CLICK-TO-SITE ad → https://fieldsestate.com.au/price-your-home

Optimises for the pixel `Lead` event the page fires on submit. Geo-targeted to the 3 core
suburbs, $10/day, Reels + Stories, Facebook + Instagram. EVERYTHING IS CREATED PAUSED.

Modeled on 03_Facebook/Reels/launch_reel_click_to_site.py (same geo keys, same OFFSITE_CONVERSIONS
+ LEAD optimisation). Unlike that one, this uploads a FRESH video + thumbnail (this reel).

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_price_your_home_reel.py            # upload video + build everything PAUSED
  python3 launch_price_your_home_reel.py --activate # DO NOT run without Will's go-ahead
"""
import os, sys, json, time, subprocess, requests

TOK = os.environ["FACEBOOK_ADS_TOKEN"]
ACT = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
PIXEL = "1491613936314260"  # Fields primary pixel (the only one)
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(HERE, "fields_price_your_home_reel.mp4")
THUMB = os.path.join(HERE, "reel_thumb.jpg")
IDS_PATH = os.path.join(HERE, "price_your_home_ad_ids.json")

DAILY_BUDGET_CENTS = 1000  # AUD $10/day (Will, 2026-08-28)
SUBURB_KEYS = ["2687074", "2674227", "2719184"]  # Robina, Varsity Lakes, Burleigh Waters
LANDING = ("https://fieldsestate.com.au/price-your-home"
           "?utm_source=facebook&utm_medium=paid_social&utm_campaign=price_your_own_home_reel")

PRIMARY_TEXT = (
    "How accurately could you price your own home?\n\n"
    "Pick the recent sales you believe are genuinely comparable to your home — and watch your "
    "estimate move. Fields gives you the evidence; you make the assessment.\n\n"
    "Enter your address to analyse your home using recent local sales."
)
HEADLINE = "Analyse your home with real local sales"
CTA_TYPE = "LEARN_MORE"


def _call(method, path, token, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = token
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=120, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j


def _save(state):
    json.dump(state, open(IDS_PATH, "w"), indent=2)


def upload_video():
    with open(VIDEO, "rb") as f:
        r = requests.post(f"{B}/{ACT}/advideos", timeout=600,
                          data={"access_token": TOK, "name": "Price Your Own Home reel"},
                          files={"source": f})
    j = r.json()
    if r.status_code >= 400 or j.get("error"):
        raise RuntimeError(f"video upload FAILED: {json.dumps(j.get('error', j))}")
    return j["id"]


def wait_video_ready(video_id, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = _call("GET", video_id, TOK, fields="status")["status"]
        vs = st.get("video_status") if isinstance(st, dict) else st
        print("  video status:", vs)
        if vs == "ready":
            return True
        if vs == "error":
            raise RuntimeError(f"video processing error: {st}")
        time.sleep(10)
    raise RuntimeError("video not ready within timeout")


def upload_thumb():
    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:02", "-i", VIDEO, "-frames:v", "1",
                    "-q:v", "3", THUMB], check=True, capture_output=True)
    with open(THUMB, "rb") as f:
        r = requests.post(f"{B}/{ACT}/adimages", timeout=120,
                          data={"access_token": TOK}, files={"filename": f})
    j = r.json()
    if r.status_code >= 400 or j.get("error"):
        raise RuntimeError(f"thumb upload FAILED: {json.dumps(j.get('error', j))}")
    return list(j["images"].values())[0]["hash"]


def create_campaign():
    return _call("POST", f"{ACT}/campaigns", TOK,
                 name="Price Your Own Home — CLICK-TO-SITE (price-your-home, Aug 2026)",
                 objective="OUTCOME_LEADS", special_ad_categories=[],
                 is_adset_budget_sharing_enabled=False,
                 status="PAUSED")["id"]


def create_adset(campaign_id):
    targeting = {
        "geo_locations": {"neighborhoods": [{"key": k} for k in SUBURB_KEYS],
                          "location_types": ["home"]},
        "age_min": 25,
        "targeting_automation": {"advantage_audience": 1},
        "publisher_platforms": ["facebook", "instagram"],
        "facebook_positions": ["facebook_reels", "story"],
        "instagram_positions": ["reels", "story"],
    }
    return _call("POST", f"{ACT}/adsets", TOK,
                 name="Price Your Own Home · Robina+Varsity+Burleigh",
                 campaign_id=campaign_id,
                 daily_budget=DAILY_BUDGET_CENTS,
                 billing_event="IMPRESSIONS",
                 optimization_goal="OFFSITE_CONVERSIONS",
                 destination_type="WEBSITE",
                 promoted_object={"pixel_id": PIXEL, "custom_event_type": "LEAD"},
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 targeting=targeting,
                 status="PAUSED")["id"]


def create_creative(video_id, thumb_hash, cta_type=CTA_TYPE):
    oss = {"page_id": PAGE, "video_data": {
        "video_id": video_id,
        "image_hash": thumb_hash,
        "message": PRIMARY_TEXT,
        "title": HEADLINE,
        "call_to_action": {"type": cta_type, "value": {"link": LANDING}},
    }}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name="Price Your Own Home creative", object_story_spec=oss)["id"]


def create_ad(adset_id, creative_id):
    return _call("POST", f"{ACT}/ads", TOK,
                 name="Price Your Own Home Ad — Click to Site",
                 adset_id=adset_id, creative={"creative_id": creative_id}, status="PAUSED")["id"]


def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    if not state.get("video_id"):
        print("· uploading video …"); state["video_id"] = upload_video(); _save(state)
        print("  video_id:", state["video_id"])
    wait_video_ready(state["video_id"])
    if not state.get("thumb_hash"):
        state["thumb_hash"] = upload_thumb(); print("· thumb_hash:", state["thumb_hash"]); _save(state)
    if not state.get("campaign_id"):
        state["campaign_id"] = create_campaign(); print("· campaign:", state["campaign_id"]); _save(state)
    if not state.get("adset_id"):
        state["adset_id"] = create_adset(state["campaign_id"]); print("· adset:", state["adset_id"]); _save(state)
    if not state.get("creative_id"):
        state["creative_id"] = create_creative(state["video_id"], state["thumb_hash"])
        print("· creative:", state["creative_id"]); _save(state)
    if not state.get("ad_id"):
        state["ad_id"] = create_ad(state["adset_id"], state["creative_id"]); print("· ad:", state["ad_id"]); _save(state)
    print("\nBUILT — ALL PAUSED. $%.0f/day · CTA %s → %s\nIDs -> %s" %
          (DAILY_BUDGET_CENTS / 100, CTA_TYPE, LANDING, IDS_PATH))
    return state


def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("campaign ACTIVE")
    _call("POST", ids["adset_id"], TOK, status="ACTIVE"); print("adset ACTIVE")
    _call("POST", ids["ad_id"], TOK, status="ACTIVE")
    print("ad ACTIVE — $%.0f/day LIVE → %s" % (DAILY_BUDGET_CENTS / 100, LANDING))


if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
