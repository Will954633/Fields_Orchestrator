#!/usr/bin/env python3
"""
Launch the refined "I Have A Buyer" 4-card carousel as a NEW ad inside the SAME ad set as
the existing Buyer Brief ad (120252514796700134), with a new low-friction lead form.
Builds everything PAUSED. Activate with --activate.
"""
import os, sys, json, requests

B   = "https://graph.facebook.com/v20.0"
TOK = os.environ["FACEBOOK_ADS_TOKEN"]
ACT = "act_1463563608441065"
PAGE = "889412530933297"

ADSET_ID = "120252514796700134"   # same ad set as "I Have A Buyer — Buyer Brief Ad"

ROOT = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(ROOT, "ihab_v2_ids.json")
CREATIVES = os.path.join(ROOT, "creatives_v2")

PRIMARY = (
    "Your next home might not be listed yet. Over 120 homes are coming to market across "
    "Robina, Varsity Lakes and Burleigh Waters in the next six months. Tell Fields what "
    "you're looking for — and get matched to your perfect home before it's advertised. "
    "Tell us what you want →"
)

CARDS = [
    ("card1.png", "The whole market, today",   "Every house listed, right now"),
    ("card2.png", "The homes you can't see",   "Real homes, not on the market"),
    ("card3.png", "How it works",              "Brief to offer, step by step"),
    ("card4.png", "Let Fields find your home", "Tell us your brief · we find it first"),
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
    # Prefilled contact (mobile is the main field; email auto-prefilled, not manually entered).
    # Native forms are single-select per custom question; "Somewhere nearby" is the flexible catch-all.
    # Tap-select questions FIRST (location leads), prefilled contact LAST — matches the brief and is better UX.
    questions = [
        {"type": "CUSTOM", "key": "suburbs",
         "label": "Where would you consider buying?",
         "options": [
             {"key": "robina", "value": "Robina"},
             {"key": "varsity_lakes", "value": "Varsity Lakes"},
             {"key": "burleigh_waters", "value": "Burleigh Waters"},
             {"key": "merrimac", "value": "Merrimac"},
             {"key": "reedy_creek", "value": "Reedy Creek"},
             {"key": "nearby", "value": "Somewhere nearby"},
         ]},
        {"type": "CUSTOM", "key": "budget",
         "label": "What is your approximate budget?",
         "options": [
             {"key": "u1200", "value": "Under $1.2 million"},
             {"key": "1200_1400", "value": "$1.2–$1.4 million"},
             {"key": "1400_1600", "value": "$1.4–$1.6 million"},
             {"key": "1600_2000", "value": "$1.6–$2 million"},
             {"key": "2000plus", "value": "$2 million+"},
             {"key": "unsure", "value": "Still working it out"},
         ]},
        {"type": "CUSTOM", "key": "bedrooms",
         "label": "How many bedrooms do you need?",
         "options": [
             {"key": "2plus", "value": "2+"},
             {"key": "3plus", "value": "3+"},
             {"key": "4plus", "value": "4+"},
             {"key": "5plus", "value": "5+"},
             {"key": "flexible", "value": "Flexible"},
         ]},
        {"type": "CUSTOM", "key": "timeframe",
         "label": "When would you ideally like to buy?",
         "options": [
             {"key": "asap", "value": "As soon as I find the right home"},
             {"key": "3mo", "value": "Within three months"},
             {"key": "6mo", "value": "Within six months"},
             {"key": "later", "value": "Later this year"},
             {"key": "exploring", "value": "Just exploring"},
         ]},
        {"type": "FULL_NAME"},
        {"type": "PHONE"},
        {"type": "EMAIL"},
    ]
    context_card = {
        "style": "PARAGRAPH_STYLE",
        "title": "Let's see what else is out there.",
        "content": [
            "Tell us roughly what you're looking for — it doesn't need to be a final brief. "
            "Fields will search for suitable homes beyond the major property websites and approach "
            "owners who may be open to selling. If we uncover a promising match, we'll contact you "
            "first. About 30 seconds. No cost, no obligation — we'll only contact you about your "
            "property search and relevant opportunities."
        ],
        "button_text": "Show me more homes",
    }
    thank_you = {
        "title": "Your search just got bigger.",
        "body": "Thanks — we'll review your brief and begin looking for possible matches, including "
                "homes that aren't currently advertised. We'll send you a quick message shortly to "
                "introduce ourselves.",
        "button_type": "VIEW_WEBSITE",
        "website_url": "https://fieldsestate.com.au/for-sale-v4b",
        "button_text": "View current opportunities",
    }
    resp = _call("POST", f"{PAGE}/leadgen_forms", ptok,
                 name="I Have A Buyer — Off-Market Search (v2b)",
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
            r = requests.post(f"{B}/{ACT}/adimages", data={"access_token": TOK},
                              files={fn: fh}, timeout=120)
        j = r.json()
        if j.get("error"): raise RuntimeError(f"adimage {fn} FAILED: {j['error']}")
        img = list(j["images"].values())[0]
        hashes[fn] = img["hash"]
        print(f"  uploaded {fn} -> {img['hash'][:12]}…")
    return hashes


def create_creative(form_id, hashes):
    children = []
    for fn, name, desc in CARDS:
        children.append({
            "image_hash": hashes[fn], "name": name, "description": desc,
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
                 name="I Have A Buyer v2 creative", object_story_spec=oss)["id"]


def create_ad(creative_id):
    return _call("POST", f"{ACT}/ads", TOK,
                 name="I Have A Buyer — Off-Market Search Ad (v2)",
                 adset_id=ADSET_ID, creative={"creative_id": creative_id},
                 status="PAUSED")["id"]


def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    if not state.get("form_id"):
        print("· page token"); ptok = page_token()
        print("· lead form"); state["form_id"] = create_lead_form(ptok); print("   form:", state["form_id"])
        json.dump(state, open(IDS_PATH, "w"), indent=2)
    print("· upload 4 cards"); hashes = upload_images()
    if not state.get("creative_id"):
        print("· creative"); state["creative_id"] = create_creative(state["form_id"], hashes)
        json.dump(state, open(IDS_PATH, "w"), indent=2)
    if not state.get("ad_id"):
        print("· ad"); state["ad_id"] = create_ad(state["creative_id"])
        json.dump(state, open(IDS_PATH, "w"), indent=2)
    state["adset_id"] = ADSET_ID
    json.dump(state, open(IDS_PATH, "w"), indent=2)
    print(f"\nBUILT (PAUSED). ad {state['ad_id']} · creative {state['creative_id']} · form {state['form_id']}")
    print("in ad set", ADSET_ID)
    return state


def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["ad_id"], TOK, status="ACTIVE")
    print(f"LIVE — ad {ids['ad_id']} ACTIVE in ad set {ids['adset_id']}.")


def preview():
    ids = json.load(open(IDS_PATH))
    j = _call("GET", f"{ids['creative_id']}/previews", TOK, ad_format="MOBILE_FEED_STANDARD")
    open(os.path.join(ROOT, "preview_v2.html"), "w").write(j["data"][0]["body"])
    print("preview -> preview_v2.html")


if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    elif "--preview" in sys.argv: preview()
    else: build()
