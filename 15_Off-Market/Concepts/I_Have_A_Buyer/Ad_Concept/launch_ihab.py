#!/usr/bin/env python3
"""
Launch the "I Have A Buyer" off-market carousel + Buyer Brief leadform as a NEW ad set
inside the existing OUTCOME_LEADS campaign (the champion campaign), cloning the champion
ad set's exact targeting. Builds everything PAUSED. Activate with --activate.

Env: FACEBOOK_ADS_TOKEN (system user), loaded from Fields_Orchestrator/.env
"""
import os, sys, json, requests

B   = "https://graph.facebook.com/v20.0"
TOK = os.environ["FACEBOOK_ADS_TOKEN"]
ACT = "act_1463563608441065"
PAGE = "889412530933297"

# Reuse the existing champion CAMPAIGN (OUTCOME_LEADS) — add a sibling ad set to it.
CAMPAIGN_ID = "120252455741540134"

ROOT = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(ROOT, "ihab_ids.json")
CREATIVES = os.path.join(ROOT, "creatives")

DAILY_BUDGET_CENTS = 2500   # $25/day

# Clone the champion ad set's targeting EXACTLY (neighborhoods + age 30-65).
TARGETING = {
    "geo_locations": {
        "location_types": ["home", "recent"],
        "neighborhoods": [
            {"key": "2674227", "country": "AU"},   # Varsity Lakes
            {"key": "2687074", "country": "AU"},   # Robina
            {"key": "2719184", "country": "AU"},   # Burleigh Waters
        ],
    },
    "age_min": 30, "age_max": 65,
    "targeting_automation": {"advantage_audience": 0},
}

PRIMARY = (
    "Can't find the right home in Robina, Varsity Lakes or Burleigh Waters? "
    "You're only seeing what's listed — but far more homes haven't come to market yet. "
    "Tell Fields your brief and we'll match it against every unlisted home in your suburbs — "
    "and tell you before it's advertised, so you're first through the door."
)

# Footer headline / description per carousel card (Meta name/description).
CARDS = [
    ("card1.png", "The whole market, today",        "Every house listed in your suburbs right now"),
    ("card2.png", "The homes you can't see",        "Real homes, not on the market — yet"),
    ("card3.png", "Matched to what you can spend",  "Every home carries a Fields estimate"),
    ("card4.png", "Let Fields find your home",      "Tell us your brief · we find it first"),
]


def _call(method, path, token, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = token
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=60, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j


def page_token():
    return _call("GET", PAGE, TOK, fields="access_token")["access_token"]


def create_lead_form(ptok):
    questions = [
        {"type": "FULL_NAME"},
        {"type": "PHONE"},
        {"type": "CUSTOM", "key": "suburb",
         "label": "Which suburb are you looking in?",
         "options": [
             {"key": "robina", "value": "Robina"},
             {"key": "varsity_lakes", "value": "Varsity Lakes"},
             {"key": "burleigh_waters", "value": "Burleigh Waters"},
             {"key": "all_three", "value": "All three"},
         ]},
        {"type": "CUSTOM", "key": "bedrooms",
         "label": "How many bedrooms do you need?",
         "options": [
             {"key": "2", "value": "2"},
             {"key": "3", "value": "3"},
             {"key": "4", "value": "4"},
             {"key": "5plus", "value": "5 or more"},
         ]},
        {"type": "CUSTOM", "key": "budget",
         "label": "What's your budget?",
         "options": [
             {"key": "u1000", "value": "Under $1,000,000"},
             {"key": "1000_1200", "value": "$1,000,000 – $1,200,000"},
             {"key": "1200_1400", "value": "$1,200,000 – $1,400,000"},
             {"key": "1400_1600", "value": "$1,400,000 – $1,600,000"},
             {"key": "1600_1800", "value": "$1,600,000 – $1,800,000"},
             {"key": "1800plus", "value": "$1,800,000+"},
         ]},
    ]
    context_card = {
        "style": "PARAGRAPH_STYLE",
        "title": "Let Fields find your home",
        "content": [
            "You're seeing the homes that are listed. There are far more that aren't — yet. "
            "Tell us your brief and Fields matches it against every unlisted home in your suburbs, "
            "then tells you before it's advertised. Our estimates are evidence-based ranges from "
            "recent comparable sales, not a guaranteed sale price — general information only."
        ],
        "button_text": "Find my home",
    }
    thank_you = {
        "title": "We're on it.",
        "body": "Fields will match your brief against the homes that haven't listed yet — and let "
                "you know first. While you wait, see what's on the market now.",
        "button_type": "VIEW_WEBSITE",
        "website_url": "https://fieldsestate.com.au/for-sale-v4b",
        "button_text": "See homes for sale",
    }
    resp = _call("POST", f"{PAGE}/leadgen_forms", ptok,
                 name="I Have A Buyer — Buyer Brief",
                 questions=questions,
                 privacy_policy={"url": "https://fieldsestate.com.au/privacy", "link_text": "Privacy Policy"},
                 context_card=context_card,
                 thank_you_page=thank_you,
                 follow_up_action_url="https://fieldsestate.com.au/for-sale-v4b",
                 locale="en_US")
    return resp["id"]


def upload_images():
    hashes = {}
    for fn, _, _ in CARDS:
        p = os.path.join(CREATIVES, fn)
        with open(p, "rb") as fh:
            r = requests.post(f"{B}/{ACT}/adimages",
                              data={"access_token": TOK}, files={fn: fh}, timeout=120)
        j = r.json()
        if j.get("error"): raise RuntimeError(f"adimage {fn} FAILED: {j['error']}")
        img = list(j["images"].values())[0]
        hashes[fn] = img["hash"]
        print(f"  uploaded {fn} -> {img['hash'][:12]}…")
    return hashes


def create_adset():
    return _call("POST", f"{ACT}/adsets", TOK,
                 name="I Have A Buyer — Buyer Brief Ad set",
                 campaign_id=CAMPAIGN_ID,
                 daily_budget=DAILY_BUDGET_CENTS,
                 billing_event="IMPRESSIONS",
                 optimization_goal="LEAD_GENERATION",
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 destination_type="ON_AD",
                 promoted_object={"page_id": PAGE},
                 targeting=TARGETING,
                 status="PAUSED")["id"]


def create_creative(form_id, hashes):
    children = []
    for fn, name, desc in CARDS:
        children.append({
            "image_hash": hashes[fn],
            "name": name,
            "description": desc,
            "link": "https://fieldsestate.com.au/for-sale-v4b",
            "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": form_id}},
        })
    oss = {"page_id": PAGE, "link_data": {
        "link": "https://fieldsestate.com.au/for-sale-v4b",
        "message": PRIMARY,
        "multi_share_optimized": False,
        "multi_share_end_card": False,
        "child_attachments": children,
        "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": form_id}},
    }}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name="I Have A Buyer creative", object_story_spec=oss)["id"]


def create_ad(adset_id, creative_id):
    return _call("POST", f"{ACT}/ads", TOK,
                 name="I Have A Buyer — Buyer Brief Ad",
                 adset_id=adset_id, creative={"creative_id": creative_id},
                 status="PAUSED")["id"]


def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    if state.get("form_id"):
        form_id = state["form_id"]; print("· reusing form:", form_id)
    else:
        print("· page token"); ptok = page_token()
        print("· lead form");  form_id = create_lead_form(ptok); print("   form:", form_id)
        state["form_id"] = form_id; json.dump(state, open(IDS_PATH, "w"), indent=2)
    print("· uploading 4 cards (idempotent by hash)"); hashes = upload_images()
    state["campaign_id"] = CAMPAIGN_ID
    if not state.get("adset_id"):
        print("· adset"); state["adset_id"] = create_adset(); print("   adset:", state["adset_id"])
        json.dump(state, open(IDS_PATH, "w"), indent=2)
    if not state.get("creative_id"):
        print("· creative"); state["creative_id"] = create_creative(form_id, hashes)
        json.dump(state, open(IDS_PATH, "w"), indent=2)
    if not state.get("ad_id"):
        print("· ad"); state["ad_id"] = create_ad(state["adset_id"], state["creative_id"])
        json.dump(state, open(IDS_PATH, "w"), indent=2)
    print(f"\nBUILT (PAUSED). adset {state['adset_id']} · creative {state['creative_id']} · ad {state['ad_id']}")
    print("IDs ->", IDS_PATH)
    return state


def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["adset_id"], TOK, status="ACTIVE")
    _call("POST", ids["ad_id"], TOK, status="ACTIVE")
    print(f"LIVE — ad set {ids['adset_id']} + ad {ids['ad_id']} ACTIVE at $25/day.")


def preview():
    ids = json.load(open(IDS_PATH))
    j = _call("GET", f"{ids['creative_id']}/previews", TOK, ad_format="MOBILE_FEED_STANDARD")
    body = j["data"][0]["body"]
    open(os.path.join(ROOT, "preview.html"), "w").write(body)
    print("preview iframe saved -> preview.html")


if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    elif "--preview" in sys.argv: preview()
    else: build()
