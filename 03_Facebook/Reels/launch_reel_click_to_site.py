#!/usr/bin/env python3
"""
launch_reel_click_to_site.py — Reel3 "Trust Test" as a CLICK-TO-SITE ad (not a lead form).

The pivot (Will, 2026-08-28): instead of Meta's on-ad Instant Form, the "Get Started" CTA
takes the viewer to https://fieldsestate.com.au/your-home-evidence — an immersive, reel-styled
landing page where they type their address, see an instant home card (beds/baths/living/land),
then leave name + phone. We SMS them their /off-market link (reel3_evidence_sms.py). Optimises
for the pixel `Lead` event the page fires on submit.

Same reel video + geo-targeting as the lead-form version; reuses the already-uploaded
video_id + thumb_hash from reel_leads_ids.json. Everything is created PAUSED — the existing
lead-form campaign keeps running until Will swaps.

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_reel_click_to_site.py            # build everything PAUSED
  python3 launch_reel_click_to_site.py --activate # DO NOT run without Will's go-ahead
"""
import os, sys, json, requests

TOK = os.environ["FACEBOOK_ADS_TOKEN"]
ACT = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
PIXEL = "1491613936314260"  # Fields primary pixel (the only one)
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
LEADS_IDS = os.path.join(HERE, "reel_leads_ids.json")     # source of video_id + thumb_hash
IDS_PATH = os.path.join(HERE, "reel_click_to_site_ids.json")

DAILY_BUDGET_CENTS = 1500  # AUD $15/day
SUBURB_KEYS = ["2687074", "2674227", "2719184"]  # Robina, Varsity Lakes, Burleigh Waters
LANDING = "https://fieldsestate.com.au/your-home-evidence"

PRIMARY_TEXT = (
    "Three websites valued the same Gold Coast home hundreds of thousands apart.\n\n"
    "In our test of 512 homes, the typical gap was over $215,000. See how the estimates "
    "compare—and which evidence you should trust."
)
HEADLINE = "Can your estimate be trusted?"
CTA_TYPE = "GET_STARTED"   # Will's pick; falls back to LEARN_MORE if the ad account rejects it


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


def create_campaign():
    return _call("POST", f"{ACT}/campaigns", TOK,
                 name="Reel3 Trust Test — CLICK-TO-SITE (your-home-evidence, Aug 2026)",
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
                 name="Reel3 Click-to-Site · Robina+Varsity+Burleigh",
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
                 name="Reel3 Click-to-Site creative", object_story_spec=oss)["id"]


def create_ad(adset_id, creative_id):
    return _call("POST", f"{ACT}/ads", TOK,
                 name="Reel3 Trust Test Ad — Click to Site",
                 adset_id=adset_id, creative={"creative_id": creative_id}, status="PAUSED")["id"]


def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    src = json.load(open(LEADS_IDS))
    state.setdefault("video_id", src["video_id"])
    state.setdefault("thumb_hash", src["thumb_hash"])
    if not state.get("campaign_id"):
        state["campaign_id"] = create_campaign(); print("· campaign:", state["campaign_id"]); _save(state)
    if not state.get("adset_id"):
        state["adset_id"] = create_adset(state["campaign_id"]); print("· adset:", state["adset_id"]); _save(state)
    if not state.get("creative_id"):
        try:
            state["creative_id"] = create_creative(state["video_id"], state["thumb_hash"])
        except RuntimeError as e:
            if "GET_STARTED" in str(e) or "call_to_action" in str(e):
                print("  GET_STARTED rejected → falling back to LEARN_MORE"); state["cta"] = "LEARN_MORE"
                state["creative_id"] = create_creative(state["video_id"], state["thumb_hash"], "LEARN_MORE")
            else:
                raise
        print("· creative:", state["creative_id"]); _save(state)
    if not state.get("ad_id"):
        state["ad_id"] = create_ad(state["adset_id"], state["creative_id"]); print("· ad:", state["ad_id"]); _save(state)
    print("\nBUILT — ALL PAUSED. CTA:", state.get("cta", CTA_TYPE), "→", LANDING, "\nIDs ->", IDS_PATH)
    return state


def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("campaign ACTIVE")
    _call("POST", ids["adset_id"], TOK, status="ACTIVE"); print("adset ACTIVE")
    _call("POST", ids["ad_id"], TOK, status="ACTIVE"); print("ad ACTIVE — $15/day LIVE →", LANDING)


if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
