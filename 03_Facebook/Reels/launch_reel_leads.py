#!/usr/bin/env python3
"""
launch_reel_leads.py — Reel Three "trust test" as a Meta LEAD ad (Instant Form).

One campaign (OUTCOME_LEADS) · one ad set geofenced to Robina + Varsity Lakes +
Burleigh Waters · one VIDEO ad (the News/PROPERTY ALERT reel) opening an in-app
Instant Form that prefills FIRST NAME + PHONE from the viewer's Meta profile, so
they just tap submit. Thank-you screen sends them to /analyse-your-home as the
optional address second step.

Everything is created PAUSED. Nothing spends until --activate (with Will's go-ahead).

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_reel_leads.py            # build everything PAUSED
  python3 launch_reel_leads.py --activate # DO NOT run without Will's go-ahead
"""
import os, sys, json, time, requests

TOK = os.environ["FACEBOOK_ADS_TOKEN"]
ACT = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(HERE, "renders", "reel3_news_draft.mp4")
THUMB = os.path.join(HERE, "renders", "reel3_news_thumb.png")
IDS_PATH = os.path.join(HERE, "reel_leads_ids.json")

DAILY_BUDGET_CENTS = 1500  # AUD $15/day
SUBURB_KEYS = ["2687074", "2674227", "2719184"]  # Robina, Varsity Lakes, Burleigh Waters
LANDING = "https://fieldsestate.com.au/analyse-your-home"
PRIVACY = "https://fieldsestate.com.au/privacy"

PRIMARY_TEXT = (
    "Three websites valued the same Gold Coast home hundreds of thousands apart.\n\n"
    "In our test of 512 homes, the typical gap was over $215,000. See the evidence behind "
    "your home's value — takes 30 seconds."
)
HEADLINE = "Can your estimate be trusted?"


def _call(method, path, token, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = token
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=120, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j


def page_token():
    return _call("GET", PAGE, TOK, fields="access_token")["access_token"]


def create_form(ptok):
    """Instant Form: FIRST_NAME + PHONE only — both prefill from the Meta profile.
    Methodology + disclaimer live in the context card (Rule 5 $-claim pre-flight).
    Thank-you screen = the optional address second step (/analyse-your-home)."""
    questions = [{"type": "FIRST_NAME"}, {"type": "PHONE"}]
    context_card = {
        "style": "PARAGRAPH_STYLE",
        "title": "Can your home's estimate be trusted?",
        "content": [
            "Different websites can value the same Gold Coast home hundreds of thousands apart. "
            "In our test of 512 homes, the typical gap between defensible estimates was over "
            "$215,000. Leave your name and mobile and we'll show you the actual comparable sales "
            "and adjustments behind your home's value.\n\n"
            "Figures: Fields' analysis of 512 sold houses ($1M-$2M) across Robina, Varsity Lakes "
            "and Burleigh Waters. The 'gap' is the spread between the highest and lowest "
            "defensible three-comparable estimate - a measure of spread, not an error rate. "
            "Estimates are guides, not formal valuations. Compiled from public sale records."],
        "button_text": "See my home's evidence",
    }
    thank_you = {
        "title": "You're all set.",
        "body": "One optional step - enter your home's address to see the actual comparable "
                "sales and per-feature adjustments behind its value.",
        "button_type": "VIEW_WEBSITE",
        "website_url": LANDING,
        "button_text": "Enter my address",
    }
    resp = _call("POST", f"{PAGE}/leadgen_forms", ptok,
                 name="Reel3 Trust Test — name+phone (prefilled)",
                 questions=questions,
                 privacy_policy={"url": PRIVACY, "link_text": "Privacy Policy"},
                 context_card=context_card,
                 thank_you_page=thank_you,
                 follow_up_action_url=LANDING,
                 locale="en_US")
    return resp["id"]


def upload_video():
    with open(VIDEO, "rb") as fh:
        r = requests.post(f"{B}/{ACT}/advideos",
                          data={"access_token": TOK, "name": "Reel3 News PROPERTY ALERT 215k"},
                          files={"source": fh}, timeout=300)
    j = r.json()
    if j.get("error"): raise RuntimeError(f"advideo FAILED: {j['error']}")
    vid = j["id"]
    # poll until processed
    for _ in range(60):
        s = _call("GET", vid, TOK, fields="status")
        st = (s.get("status") or {}).get("video_status")
        print(f"   video {vid} status={st}")
        if st == "ready":
            return vid
        if st == "error":
            raise RuntimeError(f"video processing error: {s}")
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
                 name="Reel3 Trust Test — LEADS (News/PROPERTY ALERT, Aug 2026)",
                 objective="OUTCOME_LEADS", special_ad_categories=[],
                 is_adset_budget_sharing_enabled=False,
                 status="PAUSED")["id"]


def create_adset(campaign_id):
    targeting = {
        "geo_locations": {"neighborhoods": [{"key": k} for k in SUBURB_KEYS],
                          "location_types": ["home"]},
        "age_min": 25,
        "targeting_automation": {"advantage_audience": 1},
        # pinned to vertical placements — a true Reels ad (+ Stories companion), no Feed
        "publisher_platforms": ["facebook", "instagram"],
        "facebook_positions": ["facebook_reels", "story"],
        "instagram_positions": ["reels", "story"],
    }
    return _call("POST", f"{ACT}/adsets", TOK,
                 name="Reel3 Trust Test · Robina+Varsity+Burleigh",
                 campaign_id=campaign_id,
                 daily_budget=DAILY_BUDGET_CENTS,
                 billing_event="IMPRESSIONS",
                 optimization_goal="LEAD_GENERATION",
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 destination_type="ON_AD",
                 promoted_object={"page_id": PAGE},
                 targeting=targeting,
                 status="PAUSED")["id"]


def create_creative(form_id, video_id, thumb_hash):
    oss = {"page_id": PAGE, "video_data": {
        "video_id": video_id,
        "image_hash": thumb_hash,
        "message": PRIMARY_TEXT,
        "title": HEADLINE,
        "call_to_action": {"type": "SIGN_UP",
                           "value": {"link": LANDING, "lead_gen_form_id": form_id}},
    }}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name="Reel3 Trust Test creative", object_story_spec=oss)["id"]


def create_ad(adset_id, creative_id):
    return _call("POST", f"{ACT}/ads", TOK,
                 name="Reel3 Trust Test Ad",
                 adset_id=adset_id, creative={"creative_id": creative_id}, status="PAUSED")["id"]


def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    print("· page token"); ptok = page_token()
    if not state.get("form_id"):
        state["form_id"] = create_form(ptok); print("· form:", state["form_id"]); _save(state)
    if not state.get("video_id"):
        print("· uploading video (may take a few min)"); state["video_id"] = upload_video(); _save(state)
    if not state.get("thumb_hash"):
        state["thumb_hash"] = upload_thumb(); print("· thumb hash:", state["thumb_hash"][:12]); _save(state)
    if not state.get("campaign_id"):
        state["campaign_id"] = create_campaign(); print("· campaign:", state["campaign_id"]); _save(state)
    if not state.get("adset_id"):
        state["adset_id"] = create_adset(state["campaign_id"]); print("· adset:", state["adset_id"]); _save(state)
    if not state.get("creative_id"):
        state["creative_id"] = create_creative(state["form_id"], state["video_id"], state["thumb_hash"])
        print("· creative:", state["creative_id"]); _save(state)
    if not state.get("ad_id"):
        state["ad_id"] = create_ad(state["adset_id"], state["creative_id"]); print("· ad:", state["ad_id"]); _save(state)
    print("\nBUILT — ALL PAUSED. IDs ->", IDS_PATH)
    return state


def _save(state):
    json.dump(state, open(IDS_PATH, "w"), indent=2)


def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("campaign ACTIVE")
    _call("POST", ids["adset_id"], TOK, status="ACTIVE"); print("adset ACTIVE")
    _call("POST", ids["ad_id"], TOK, status="ACTIVE"); print("ad ACTIVE — $15/day LIVE")


if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
