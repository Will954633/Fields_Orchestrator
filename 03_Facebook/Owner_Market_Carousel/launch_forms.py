#!/usr/bin/env python3
"""
launch_forms.py — the LEAD-FORM A/B arm of Owner Market.

Parallel to launch_campaign.py (the website/landing-page campaign, which keeps running).
This builds a SECOND campaign whose ads open a Meta Instant Form IN-APP asking for the
homeowner's ADDRESS + name + phone. We then resolve that address to its /off-market/<slug>
page and TEXT the link (see lead_sms_responder.py). One geofenced ad set + one form per
suburb. Everything PAUSED. Nothing spends or texts until we say so.

Why a separate campaign: Instant-Form lead ads need OUTCOME_LEADS + LEAD_GENERATION +
destination ON_AD — they can't live in the OUTCOME_TRAFFIC landing-page campaign. Running
both lets us compare cost-per-resolved-address head to head (Will, 2026-08-26).

⚠ Special Ad Category: real-estate lead ads can be flagged HOUSING by Meta, which forces a
>=15mi radius and would break the per-suburb neighborhood geofence. Built the tight way
(special_ad_categories=[]); if an ad is disapproved for Housing, that's the cause.

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_forms.py            # build everything PAUSED
  python3 launch_forms.py --activate # (DO NOT run without Will's go-ahead)
"""
import os, sys, json, requests

TOK  = os.environ["FACEBOOK_ADS_TOKEN"]
ACT  = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(HERE, "cards")
IDS_PATH = os.path.join(HERE, "forms_ids.json")

DAILY_BUDGET_CENTS = 1500  # AUD $15/day per ad set

SUBURBS = {
    "robina":   {"name": "Robina",          "slug": "robina",          "geo_key": "2687074"},
    "varsity":  {"name": "Varsity Lakes",   "slug": "varsity-lakes",   "geo_key": "2674227"},
    "burleigh": {"name": "Burleigh Waters", "slug": "burleigh-waters", "geo_key": "2719184"},
}
ORDER = ["robina", "varsity", "burleigh"]

def primary_text(name):
    return (
        "Sydney and Melbourne have turned. Brisbane has slipped. The Gold Coast is still "
        "holding — but some of the early warning signs are beginning to change.\n\n"
        f"We tracked the estimated value of {name} homes over the past 18 months. Enter your "
        "address to see where your home sits—and the four market signals we're watching."
    )

# Button label on the ad + every carousel card. Changed 2026-08-28 (Will): was SIGN_UP
# ("Sign Up"). Will asked for "Get Started" but Meta's lead-form carousel enum doesn't
# offer it — LEARN_MORE ("Learn More") chosen as the closest available label.
CTA_TYPE = "LEARN_MORE"

CARD_NAMES = {"01": "Prices are falling. Is your home next?",
              "02": "Your home, traced over 18 months",
              "03": "",
              "04": "Three questions, answered",
              "05": "Get your home's link by text"}

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

def create_form(ptok, sub):
    """One Instant Form per suburb. Address is a CUSTOM free-text field (their OWN home's
    address, not their Meta profile mailing address). Consent to the SMS is stated on the
    card; every SMS also identifies Fields + offers STOP (Spam Act 2003, per responder)."""
    s = SUBURBS[sub]
    questions = [
        {"type": "CUSTOM", "key": "home_address",
         "label": f"Your {s['name']} home's street address"},
        {"type": "FULL_NAME"},
        {"type": "PHONE"},
    ]
    context_card = {
        "style": "PARAGRAPH_STYLE",
        "title": f"Your {s['name']} home's analysis — texted to you",
        "content": [
            "Enter your address and mobile. We'll text you a private link to the analysis "
            "prepared for your home: its estimated value over 18 months, where it sits in "
            f"{s['name']}, and the leading indicators we're watching. Compiled from public "
            "sale records. General information only, not financial advice. By submitting you "
            "agree to receive a text with your link; reply STOP to opt out anytime."],
        "button_text": "Text me my link",
    }
    thank_you = {
        "title": "On its way by text.",
        "body": "We're preparing the link to your home's analysis and will text it to you "
                "shortly. In the meantime, see the latest data for your suburb.",
        "button_type": "VIEW_WEBSITE",
        "website_url": f"https://fieldsestate.com.au/find/{s['slug']}",
        "button_text": "See your suburb's data",
    }
    resp = _call("POST", f"{PAGE}/leadgen_forms", ptok,
                 name=f"Owner Market — {s['name']} home analysis (SMS link)",
                 questions=questions,
                 privacy_policy={"url": "https://fieldsestate.com.au/privacy", "link_text": "Privacy Policy"},
                 context_card=context_card,
                 thank_you_page=thank_you,
                 follow_up_action_url=f"https://fieldsestate.com.au/find/{s['slug']}",
                 locale="en_US")
    return resp["id"]

def upload_images():
    hashes = {}
    for sub in ORDER:
        for num in ["01", "02", "03", "04", "05"]:
            p = os.path.join(CARDS, f"{sub}_card{num}.png")
            with open(p, "rb") as fh:
                r = requests.post(f"{B}/{ACT}/adimages",
                                  data={"access_token": TOK}, files={f"{sub}_{num}.png": fh}, timeout=120)
            j = r.json()
            if j.get("error"): raise RuntimeError(f"adimage {sub}_{num} FAILED: {j['error']}")
            hashes[f"{sub}_{num}"] = list(j["images"].values())[0]["hash"]
    return hashes

def create_campaign():
    return _call("POST", f"{ACT}/campaigns", TOK,
                 name="Owner Market — Find Your Home (LEAD FORM / SMS link, Aug 2026)",
                 objective="OUTCOME_LEADS", special_ad_categories=[],
                 is_adset_budget_sharing_enabled=False, status="PAUSED")["id"]

def create_adset(campaign_id, sub):
    s = SUBURBS[sub]
    targeting = {
        "geo_locations": {"neighborhoods": [{"key": s["geo_key"]}], "location_types": ["home"]},
        "age_min": 25,
        "targeting_automation": {"advantage_audience": 1},
    }
    return _call("POST", f"{ACT}/adsets", TOK,
                 name=f"Owner Market FORM · {s['name']}",
                 campaign_id=campaign_id,
                 daily_budget=DAILY_BUDGET_CENTS,
                 billing_event="IMPRESSIONS",
                 optimization_goal="LEAD_GENERATION",
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 destination_type="ON_AD",
                 promoted_object={"page_id": PAGE},
                 targeting=targeting,
                 status="PAUSED")["id"]

def create_creative(sub, form_id, hashes):
    s = SUBURBS[sub]
    children = []
    for num in ["01", "02", "03", "04", "05"]:
        child = {"image_hash": hashes[f"{sub}_{num}"],
                 "link": f"https://fieldsestate.com.au/find/{s['slug']}",
                 "call_to_action": {"type": CTA_TYPE, "value": {"lead_gen_form_id": form_id}}}
        if CARD_NAMES[num]:
            child["name"] = CARD_NAMES[num]
        children.append(child)
    oss = {"page_id": PAGE, "link_data": {
        "link": f"https://fieldsestate.com.au/find/{s['slug']}",
        "message": primary_text(s["name"]),
        "multi_share_optimized": False,
        "multi_share_end_card": False,
        "child_attachments": children,
        "call_to_action": {"type": CTA_TYPE, "value": {"lead_gen_form_id": form_id}},
    }}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name=f"Owner Market FORM creative · {s['name']}", object_story_spec=oss)["id"]

def create_ad(sub, adset_id, creative_id):
    s = SUBURBS[sub]
    return _call("POST", f"{ACT}/ads", TOK,
                 name=f"Owner Market FORM Ad · {s['name']}",
                 adset_id=adset_id, creative={"creative_id": creative_id}, status="PAUSED")["id"]

def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    print("· page token"); ptok = page_token()
    print("· uploading 15 cards (idempotent)"); hashes = upload_images()
    if state.get("campaign_id"):
        camp = state["campaign_id"]; print("· reusing campaign:", camp)
    else:
        camp = create_campaign(); print("· campaign:", camp)
    state["campaign_id"] = camp; state.setdefault("arms", {})
    for sub in ORDER:
        a = state["arms"].get(sub, {})
        if a.get("ad_id"):
            print(f"· {sub}: already built"); continue
        a["form_id"] = a.get("form_id") or create_form(ptok, sub)
        a["adset_id"] = a.get("adset_id") or create_adset(camp, sub)
        a["creative_id"] = a.get("creative_id") or create_creative(sub, a["form_id"], hashes)
        a["ad_id"] = create_ad(sub, a["adset_id"], a["creative_id"])
        state["arms"][sub] = a
        json.dump(state, open(IDS_PATH, "w"), indent=2)
        print(f"   {sub}: form {a['form_id']} · adset {a['adset_id']} · ad {a['ad_id']}")
    print("\nBUILT (all PAUSED). IDs ->", IDS_PATH)
    return state

def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("campaign ACTIVE")
    for sub, o in ids["arms"].items():
        _call("POST", o["adset_id"], TOK, status="ACTIVE")
        _call("POST", o["ad_id"], TOK, status="ACTIVE")
        print(f"{sub} ACTIVE")
    print("\nFORM CAMPAIGN LIVE — $45/day ($15 × 3). Ensure lead_sms_responder is armed.")

if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
