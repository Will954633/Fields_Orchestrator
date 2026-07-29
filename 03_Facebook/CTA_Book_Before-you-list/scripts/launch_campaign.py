#!/usr/bin/env python3
"""
launch_campaign.py — build the "Before You List" 3-arm carousel LEAD campaign via the
Meta Marketing API. Creates the Instant Form, uploads the 18 cards, and builds
campaign -> 3 ad sets -> 3 carousel creatives -> 3 ads, all PAUSED. Saves IDs to
campaign_ids.json. Run with --activate to flip campaign + ad sets + ads to ACTIVE.

Env: FACEBOOK_ADS_TOKEN (system user), FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 scripts/launch_campaign.py            # build everything PAUSED
  python3 scripts/launch_campaign.py --activate # turn the paused campaign ON
"""
import os, sys, json, requests

TOK  = os.environ["FACEBOOK_ADS_TOKEN"]
ACT  = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
V, B = "v20.0", "https://graph.facebook.com/v20.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS_PATH = os.path.join(ROOT, "campaign_ids.json")

DAILY_BUDGET_CENTS = 2500  # AUD $25.00 per ad set
SUBURBS = [  # custom_locations, 5km radius (Will, 2026-07-28)
    {"latitude": -28.0766, "longitude": 153.3899, "radius": 5, "distance_unit": "kilometer"},  # Robina
    {"latitude": -28.0844, "longitude": 153.3689, "radius": 5, "distance_unit": "kilometer"},  # Varsity Lakes
    {"latitude": -28.0889, "longitude": 153.4356, "radius": 5, "distance_unit": "kilometer"},  # Burleigh Waters
]
PRIMARY = {
 "A": "Two homes near $1,900,000. One reached for $2,300,000, dropped, and sold after 61 days. "
      "One priced right and sold for more — in two days. The difference wasn't the house. "
      "We wrote the guide; we'll post you a copy, free.",
 "B": "The free online estimate said this home was worth $2,120,000. It sold for $1,742,000. "
      "These tools miss by more than most sellers realise. Get the guide that shows how the real "
      "number is found — a printed hardcover, posted free.",
 "C": "One home sold in two days. One took sixty-one. Same region, same kind of family home. "
      "The difference wasn't luck — and it wasn't the house. We'll post you the guide, free.",
}
ARM_NAME = {"A": "A · Loss→Proof", "B": "B · Trust", "C": "C · Control"}

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
        {"type": "EMAIL"},
        {"type": "PHONE"},
        {"type": "CUSTOM", "key": "postal_address",
         "label": "Postal address to send your free copy"},
    ]
    context_card = {
        "style": "PARAGRAPH_STYLE",
        "title": "Before You List — free hardcover, posted",
        "content": ["A data-driven guide to pricing, timing and the first ten days on market — "
                    "printed, bound and posted to your door. No sales pitch. Our valuation is an "
                    "evidence-based range from recent comparable sales, not a guaranteed sale price; "
                    "general information only, not financial advice. Tell us where to send it."],
        "button_text": "Get my copy",
    }
    thank_you = {
        "title": "It's on its way to you.",
        "body": "Your copy of Before You List is being posted. While it's in transit, see the real "
                "recent sales behind the numbers for your suburb.",
        "button_type": "VIEW_WEBSITE",
        "website_url": "https://fieldsestate.com.au/analyse-your-home",
        "button_text": "See your suburb's data",
    }
    resp = _call("POST", f"{PAGE}/leadgen_forms", ptok,
                 name="Before You List — free hardcover, posted",
                 questions=questions,
                 privacy_policy={"url": "https://fieldsestate.com.au/privacy", "link_text": "Privacy Policy"},
                 context_card=context_card,
                 thank_you_page=thank_you,
                 follow_up_action_url="https://fieldsestate.com.au/analyse-your-home",
                 locale="en_US")
    return resp["id"]

def upload_images():
    hashes = {}
    for arm in "ABC":
        for i in range(1, 7):
            p = os.path.join(ROOT, "creatives", arm, f"{arm}{i}.png")
            with open(p, "rb") as fh:
                r = requests.post(f"{B}/{ACT}/adimages",
                                  data={"access_token": TOK}, files={f"{arm}{i}.png": fh}, timeout=120)
            j = r.json()
            if j.get("error"): raise RuntimeError(f"adimage {arm}{i} FAILED: {j['error']}")
            img = list(j["images"].values())[0]
            hashes[f"{arm}{i}"] = img["hash"]
            print(f"  uploaded {arm}{i} -> {img['hash'][:12]}…")
    return hashes

def create_campaign():
    return _call("POST", f"{ACT}/campaigns", TOK,
                 name="Before You List — Seller Book (3-arm test)",
                 objective="OUTCOME_LEADS", special_ad_categories=[],
                 is_adset_budget_sharing_enabled=False,
                 status="PAUSED")["id"]

def create_adset(campaign_id, arm):
    targeting = {
        "geo_locations": {"custom_locations": SUBURBS, "location_types": ["home", "recent"]},
        "age_min": 35, "age_max": 65,
        "targeting_automation": {"advantage_audience": 0},
    }
    return _call("POST", f"{ACT}/adsets", TOK,
                 name=f"BYL {ARM_NAME[arm]}",
                 campaign_id=campaign_id,
                 daily_budget=DAILY_BUDGET_CENTS,
                 billing_event="IMPRESSIONS",
                 optimization_goal="LEAD_GENERATION",
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 destination_type="ON_AD",
                 promoted_object={"page_id": PAGE},
                 targeting=targeting,
                 status="PAUSED")["id"]

def create_creative(arm, form_id, hashes):
    children = []
    for i in range(1, 7):
        children.append({
            "image_hash": hashes[f"{arm}{i}"],
            "link": "https://fieldsestate.com.au/analyse-your-home",
            "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": form_id}},
        })
    oss = {"page_id": PAGE, "link_data": {
        "link": "https://fieldsestate.com.au/analyse-your-home",
        "message": PRIMARY[arm],
        "multi_share_optimized": False,
        "multi_share_end_card": False,
        "child_attachments": children,
        "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": form_id}},
    }}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name=f"BYL creative {arm}", object_story_spec=oss)["id"]

def create_ad(arm, adset_id, creative_id):
    return _call("POST", f"{ACT}/ads", TOK,
                 name=f"BYL Ad {ARM_NAME[arm]}",
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
    print("· uploading 18 cards (idempotent by hash)"); hashes = upload_images()
    if state.get("campaign_id"):
        camp = state["campaign_id"]; print("· reusing campaign:", camp)
    else:
        print("· campaign"); camp = create_campaign(); print("   campaign:", camp)
    state.update({"campaign_id": camp, "form_id": form_id})
    state.setdefault("arms", {})
    for arm in "ABC":
        a = state["arms"].get(arm, {})
        if a.get("ad_id"):
            print(f"· arm {arm}: already built ({a['ad_id']})"); continue
        print(f"· arm {arm}: adset / creative / ad")
        a.setdefault("adset_id") or a.update(adset_id=create_adset(camp, arm))
        a["creative_id"] = a.get("creative_id") or create_creative(arm, form_id, hashes)
        a["ad_id"] = create_ad(arm, a["adset_id"], a["creative_id"])
        state["arms"][arm] = a
        json.dump(state, open(IDS_PATH, "w"), indent=2)   # persist after each arm
        print(f"   {arm}: adset {a['adset_id']} · creative {a['creative_id']} · ad {a['ad_id']}")
    print("\nBUILT (all PAUSED). IDs ->", IDS_PATH)
    return state

def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("campaign ACTIVE")
    for arm, o in ids["arms"].items():
        _call("POST", o["adset_id"], TOK, status="ACTIVE")
        _call("POST", o["ad_id"], TOK, status="ACTIVE")
        print(f"arm {arm} ACTIVE (adset {o['adset_id']}, ad {o['ad_id']})")
    print("\nCAMPAIGN IS LIVE — $75/day total ($25 × 3 arms).")

if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
