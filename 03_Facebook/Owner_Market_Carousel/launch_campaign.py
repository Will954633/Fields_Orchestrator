#!/usr/bin/env python3
"""
launch_campaign.py — build the Owner-Market carousel campaign via the Meta Marketing API.

Three GEOFENCED ad sets (one per suburb, each targeting ONLY its own suburb), each a
5-card website carousel driving to that suburb's /find/<slug> landing page. Everything
is created PAUSED. Nothing spends until someone runs --activate (we will not).

Structure (aligned to fb_ads_experimentation_playbook.md):
  Campaign  OUTCOME_TRAFFIC, ABO (per-adset budget), PAUSED
  Ad set    $15/day, optimize for LANDING_PAGE_VIEWS — people who actually land on the
            /find page (Will, 2026-08-26), geofenced to the one suburb by Meta
            NEIGHBORHOOD key (home residents), broad + Advantage Audience (learning #8), PAUSED
  Creative  object_story_spec.link_data carousel, 5 child_attachments (cards 01-05),
            multi_share_optimized/end_card = False so card ORDER is preserved and no
            auto end-card is appended (our card 05 IS the CTA). No standard_enhancements.
  Ad        PAUSED

Env: FACEBOOK_ADS_TOKEN (system user), FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_campaign.py            # build everything PAUSED
  python3 launch_campaign.py --activate # (DO NOT RUN without Will's go-ahead)
"""
import os, sys, json, requests

TOK  = os.environ["FACEBOOK_ADS_TOKEN"]
ACT  = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
PIXEL = "1491613936314260"                       # Fields primary pixel (the only one)
V, B = "v20.0", "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(HERE, "cards")
IDS_PATH = os.path.join(HERE, "campaign_ids.json")

DAILY_BUDGET_CENTS = 1500  # AUD $15.00 per ad set (Will, 2026-08-26)

# Each ad set targets ONLY its suburb (residents), by Meta NEIGHBORHOOD key
# (adgeolocation search, AU). Cleaner than radius pins and no bleed into neighbours.
SUBURBS = {
    "robina":   {"name": "Robina",          "slug": "robina",          "geo_key": "2687074"},
    "varsity":  {"name": "Varsity Lakes",   "slug": "varsity-lakes",   "geo_key": "2674227"},
    "burleigh": {"name": "Burleigh Waters", "slug": "burleigh-waters", "geo_key": "2719184"},
}
ORDER = ["robina", "varsity", "burleigh"]

def landing(slug):
    return (f"https://fieldsestate.com.au/find/{slug}"
            f"?utm_source=facebook&utm_medium=paid_social"
            f"&utm_campaign=owner_market_carousel&utm_content={slug}")

def primary_text(name):
    return (
        "Sydney and Melbourne have turned. Brisbane has slipped. The Gold Coast is still "
        "holding — but some of the early warning signs are beginning to change.\n\n"
        f"We tracked the estimated value of {name} homes over the past 18 months, set each "
        "against the wider market, and examined the indicators that tend to move before prices do.\n\n"
        "See exactly where your home sits. Search your address at fieldsestate.com.au — no sign-up."
    )

# Short headline under each carousel card (name). Card 03 (portrait) left blank.
CARD_NAMES = {
    "01": "Prices are falling. Is your home next?",
    "02": "Your home, traced over 18 months",
    "03": "",
    "04": "Three questions, answered",
    "05": "See where your home stands",
}

def _call(method, path, token, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = token
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=60, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j

def upload_images():
    """Upload all 15 cards; Meta dedupes by content hash so the shared 03/04/05 collapse."""
    hashes = {}
    for sub in ORDER:
        for num in ["01", "02", "03", "04", "05"]:
            p = os.path.join(CARDS, f"{sub}_card{num}.png")
            with open(p, "rb") as fh:
                r = requests.post(f"{B}/{ACT}/adimages",
                                  data={"access_token": TOK}, files={f"{sub}_{num}.png": fh}, timeout=120)
            j = r.json()
            if j.get("error"): raise RuntimeError(f"adimage {sub}_{num} FAILED: {j['error']}")
            img = list(j["images"].values())[0]
            hashes[f"{sub}_{num}"] = img["hash"]
            print(f"  uploaded {sub}_{num} -> {img['hash'][:12]}…")
    return hashes

def create_campaign():
    return _call("POST", f"{ACT}/campaigns", TOK,
                 name="Owner Market — Find Your Home (carousel, Aug 2026)",
                 objective="OUTCOME_TRAFFIC", special_ad_categories=[],
                 is_adset_budget_sharing_enabled=False,
                 status="PAUSED")["id"]

def create_adset(campaign_id, sub):
    s = SUBURBS[sub]
    targeting = {
        "geo_locations": {
            "neighborhoods": [{"key": s["geo_key"]}],   # the suburb itself
            "location_types": ["home"],                 # people who LIVE here (homeowners)
        },
        "age_min": 25,                             # light owner skew; advantage_audience treats as suggestion
        "targeting_automation": {"advantage_audience": 1},   # broad wins (learning #8)
    }
    return _call("POST", f"{ACT}/adsets", TOK,
                 name=f"Owner Market · {s['name']}",
                 campaign_id=campaign_id,
                 daily_budget=DAILY_BUDGET_CENTS,
                 billing_event="IMPRESSIONS",
                 optimization_goal="LANDING_PAGE_VIEWS",        # people who actually land on the page (Will)
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 destination_type="WEBSITE",
                 targeting=targeting,
                 status="PAUSED")["id"]

def create_creative(sub, hashes):
    s = SUBURBS[sub]; url = landing(s["slug"])
    children = []
    for num in ["01", "02", "03", "04", "05"]:
        child = {
            "image_hash": hashes[f"{sub}_{num}"],
            "link": url,
            "call_to_action": {"type": "LEARN_MORE", "value": {"link": url}},
        }
        if CARD_NAMES[num]:
            child["name"] = CARD_NAMES[num]
        children.append(child)
    oss = {"page_id": PAGE, "link_data": {
        "link": url,
        "message": primary_text(s["name"]),
        "multi_share_optimized": False,
        "multi_share_end_card": False,
        "child_attachments": children,
        "call_to_action": {"type": "LEARN_MORE", "value": {"link": url}},
    }}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name=f"Owner Market creative · {s['name']}", object_story_spec=oss)["id"]

def create_ad(sub, adset_id, creative_id):
    s = SUBURBS[sub]
    return _call("POST", f"{ACT}/ads", TOK,
                 name=f"Owner Market Ad · {s['name']}",
                 adset_id=adset_id, creative={"creative_id": creative_id},
                 status="PAUSED")["id"]

def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    print("· uploading 15 cards (idempotent by hash)"); hashes = upload_images()
    if state.get("campaign_id"):
        camp = state["campaign_id"]; print("· reusing campaign:", camp)
    else:
        print("· campaign"); camp = create_campaign(); print("   campaign:", camp)
    state["campaign_id"] = camp
    state.setdefault("arms", {})
    for sub in ORDER:
        a = state["arms"].get(sub, {})
        if a.get("ad_id"):
            print(f"· {sub}: already built ({a['ad_id']})"); continue
        print(f"· {sub}: adset / creative / ad")
        a["adset_id"] = a.get("adset_id") or create_adset(camp, sub)
        a["creative_id"] = a.get("creative_id") or create_creative(sub, hashes)
        a["ad_id"] = create_ad(sub, a["adset_id"], a["creative_id"])
        state["arms"][sub] = a
        json.dump(state, open(IDS_PATH, "w"), indent=2)
        print(f"   {sub}: adset {a['adset_id']} · creative {a['creative_id']} · ad {a['ad_id']}")
    print("\nBUILT (all PAUSED). IDs ->", IDS_PATH)
    return state

def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("campaign ACTIVE")
    for sub, o in ids["arms"].items():
        _call("POST", o["adset_id"], TOK, status="ACTIVE")
        _call("POST", o["ad_id"], TOK, status="ACTIVE")
        print(f"{sub} ACTIVE (adset {o['adset_id']}, ad {o['ad_id']})")
    print("\nCAMPAIGN IS LIVE — $45/day total ($15 × 3 suburbs).")

if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
