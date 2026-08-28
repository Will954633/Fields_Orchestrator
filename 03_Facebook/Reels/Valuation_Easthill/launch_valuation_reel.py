#!/usr/bin/env python3
"""
launch_valuation_reel.py — Fields "What the comps say" valuation reel as a Meta
TRAFFIC ad (video, vertical Reels/Stories) driving to /analyse-your-home.

Deliberately NOT a lead form: the creative promises "no email, no sales call", so
capturing name+phone in an Instant Form would contradict it. The landing page is
address-only and already carries the methodology + confidence disclaimer (Rule 5
$-claim pre-flight). Optimised for LANDING_PAGE_VIEWS via the Fields pixel.

One campaign (OUTCOME_TRAFFIC) · one ad set geofenced to Robina + Varsity Lakes +
Burleigh Waters, vertical placements · one VIDEO ad. Everything PAUSED until
--activate (Will's go-ahead).

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_valuation_reel.py             # build everything PAUSED
  python3 launch_valuation_reel.py --activate  # flip live ($15/day)
"""
import os, sys, json, time, requests, datetime

TOK  = os.environ["FACEBOOK_ADS_TOKEN"]
ACT  = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
PIXEL = os.environ.get("FACEBOOK_PIXEL_ID", "1491613936314260")
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(HERE, "renders", "easthill_valuation_reel.mp4")
THUMB = os.path.join(HERE, "renders", "thumb.png")
IDS_PATH = os.path.join(HERE, "valuation_reel_ids.json")

DAILY_BUDGET_CENTS = 1500  # AUD $15/day (matches the proven Reel3 test)
SUBURB_KEYS = ["2687074", "2674227", "2719184"]  # Robina, Varsity Lakes, Burleigh Waters
# Dedicated reel-matched landing page (forest-green, continues the end card with a
# live address field). Address-only, same submit funnel as /analyse-your-home, and
# already carries the methodology + confidence disclaimer (Rule 5 $-claim pre-flight).
LANDING = "https://fieldsestate.com.au/what-the-comps-say"

PRIMARY_TEXT = (
    "This Robina home sold $76,000 above its guide — and the comparable sales suggested why.\n\n"
    "We've analysed 230 Robina house sales over the last year, adjusting the relevant ones for "
    "size, land and condition. Enter your address and we'll build the comparable-sales breakdown "
    "for your own home, live. Free — no email, and no sales call unless you ask."
)
HEADLINE = "See what the comps say about your home"
DESC = "Free · no email · no sales call · fieldsestate.com.au"


def _call(method, path, token, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = token
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=120, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j


def upload_video():
    with open(VIDEO, "rb") as fh:
        r = requests.post(f"{B}/{ACT}/advideos",
                          data={"access_token": TOK, "name": "Easthill Valuation Reel — $76k above guide"},
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


def upload_thumb():
    with open(THUMB, "rb") as fh:
        r = requests.post(f"{B}/{ACT}/adimages", data={"access_token": TOK},
                          files={"thumb.png": fh}, timeout=120)
    j = r.json()
    if j.get("error"): raise RuntimeError(f"adimage FAILED: {j['error']}")
    return list(j["images"].values())[0]["hash"]


def create_campaign():
    return _call("POST", f"{ACT}/campaigns", TOK,
                 name="Easthill Valuation Reel — TRAFFIC (What the comps say, Aug 2026)",
                 objective="OUTCOME_TRAFFIC", special_ad_categories=[],
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
                 name="Easthill Valuation · Robina+Varsity+Burleigh",
                 campaign_id=campaign_id,
                 daily_budget=DAILY_BUDGET_CENTS,
                 billing_event="IMPRESSIONS",
                 optimization_goal="LINK_CLICKS",
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 destination_type="WEBSITE",
                 targeting=targeting,
                 status="PAUSED")["id"]


def create_creative(video_id, thumb_hash):
    oss = {"page_id": PAGE, "video_data": {
        "video_id": video_id,
        "image_hash": thumb_hash,
        "message": PRIMARY_TEXT,
        "title": HEADLINE,
        "link_description": DESC,
        "call_to_action": {"type": "LEARN_MORE", "value": {"link": LANDING}},
    }}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name="Easthill Valuation Reel creative", object_story_spec=oss)["id"]


def create_ad(adset_id, creative_id):
    return _call("POST", f"{ACT}/ads", TOK,
                 name="Easthill Valuation Reel Ad",
                 adset_id=adset_id, creative={"creative_id": creative_id}, status="PAUSED")["id"]


def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    if not state.get("video_id"):
        print("· uploading video (may take a few min)"); state["video_id"] = upload_video(); _save(state)
    if not state.get("thumb_hash"):
        state["thumb_hash"] = upload_thumb(); print("· thumb:", state["thumb_hash"][:12]); _save(state)
    if not state.get("campaign_id"):
        state["campaign_id"] = create_campaign(); print("· campaign:", state["campaign_id"]); _save(state)
    if not state.get("adset_id"):
        state["adset_id"] = create_adset(state["campaign_id"]); print("· adset:", state["adset_id"]); _save(state)
    if not state.get("creative_id"):
        state["creative_id"] = create_creative(state["video_id"], state["thumb_hash"])
        print("· creative:", state["creative_id"]); _save(state)
    if not state.get("ad_id"):
        state["ad_id"] = create_ad(state["adset_id"], state["creative_id"]); print("· ad:", state["ad_id"]); _save(state)
    print("\nBUILT — ALL PAUSED. IDs ->", IDS_PATH)
    return state


def _save(state):
    json.dump(state, open(IDS_PATH, "w"), indent=2)


def _log_ad_decision(dtype, title, extra=None):
    try:
        from shared.db import get_client
        doc = {"date": datetime.date.today().isoformat(), "type": dtype, "title": title,
               "hypothesis": "Outcome-first valuation reel (verified $76k-above-guide sale + real comps + "
                             "230-sales proof) driving address-only /analyse-your-home views converts owners "
                             "wanting a valuation better than a generic single-card CTA.",
               "findings": ["159 Easthill Dr sold $1,425,000 vs $1,349,000 guide (+$76,000)",
                            "230 Robina house sales trailing 12 months",
                            "LP is address-only, no contact wall, disclaimer present"],
               "data_snapshot": json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {},
               "tags": ["facebook_ads", "reel", "valuation", "traffic"],
               "reasoning": "Creative promises 'no email, no sales call' so a lead form would contradict it; "
                            "sent to site instead. $15/day, 3 target suburbs, vertical placements.",
               "created_at": datetime.datetime.utcnow().isoformat() + "Z"}
        if extra: doc.update(extra)
        get_client()["system_monitor"]["ad_decisions"].insert_one(doc)
        print("· logged ad_decision:", dtype)
    except Exception as e:
        print("!! ad_decision log failed:", e)


def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("campaign ACTIVE")
    _call("POST", ids["adset_id"], TOK, status="ACTIVE"); print("adset ACTIVE")
    _call("POST", ids["ad_id"], TOK, status="ACTIVE"); print("ad ACTIVE — $15/day LIVE")
    _log_ad_decision("new_campaign", "Easthill Valuation Reel activated ($15/day, 3 suburbs, Reels/Stories)")


if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
