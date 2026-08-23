#!/usr/bin/env python3
"""
launch_messenger_carousel.py — 93 Burleigh Street click-to-Messenger CAROUSEL campaign.

Builds campaign -> 3 ad sets -> 3 carousel creatives -> 3 ads, ALL PAUSED, then saves
IDs to campaign_ids.json. --activate flips campaign + ad sets + ads to ACTIVE.

Style matches the $4,150,000 Sandpiper carousel: clean photos, argument in the primary
text (link_data.message) + per-card name/description, Send Message CTA into Messenger.

HOUSING special ad category (a home-for-sale listing ad): no age/gender targeting,
geo by named suburb keys (housing enforces a radius minimum) — same pattern as the
GC seller campaign. Destination/optimization per Meta CTM docs:
  objective=OUTCOME_ENGAGEMENT, optimization_goal=CONVERSATIONS,
  destination_type=MESSENGER, promoted_object={page_id}, billing_event=IMPRESSIONS.

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
"""
import os, sys, json, requests

TOK  = os.environ["FACEBOOK_ADS_TOKEN"]
ACT  = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
CLEAN = os.path.join(HERE, "cards_clean")
IDS_PATH = os.path.join(HERE, "campaign_ids.json")
PAGE_URL = f"https://www.facebook.com/{PAGE}"

WELCOME = ("Hi — thanks for your interest in 93 Burleigh Street, Burleigh Waters. "
           "What would you like me to send you?")

BUDGET = {"A": 2000, "B": 2500, "C": 2000}   # AUD cents/day
GEO = {
 "A": [112800, 115634, 116499, 2726128, 2718787],           # Mudgeeraba belt
 "B": [2719184, 2673725, 2724616, 107937],                   # Southern GC
 "C": [114925],                                              # Sydney (city/metro)
}
ARM_NAME = {"A": "AcreageMovers", "B": "LocalSGC", "C": "Sydney"}

PRIMARY = {
 "A": ("Want to move closer to Burleigh without giving up your space? 93 Burleigh Street is "
       "822m² — proper backyard, a 7×6.2m powered workshop, a 220m² home — and a 1km walk from "
       "Burleigh Beach. It's unrenovated, which is exactly why it's $1,915,000. Message me for "
       "the full property pack. Marketed in conjunction with Tyler Benson, Coomera Realty."),
 "B": ("Buy the things you can't renovate. 93 Burleigh Street, Burleigh Waters: 822m², ~19.9m "
       "frontage, a 1km walk to the beach — and a 44m² powered workshop. The kitchen and bathroom "
       "are original, which is exactly why it's $1,915,000. Change the house; keep the land and "
       "location for good. Message me for the property pack. Marketed in conjunction with Tyler Benson, Coomera Realty."),
 "C": ("What does $1,915,000 buy walking distance to Burleigh Beach? 93 Burleigh Street, Burleigh "
       "Waters: 822m² of land, a 220m² home (4 bed, 3 bath), a 7×6.2m workshop and a big backyard "
       "— a 1km walk from the sand. The catch? It hasn't been renovated, so you're not paying for "
       "someone else's. Message me for the floorplan, data + a video walkthrough. "
       "Marketed in conjunction with Tyler Benson, Coomera Realty."),
}

# card = (image filename stem in cards_clean/<arm>/, name/headline, description)
CARDS = {
 "A": [("A1_01_Hero","822m² in Burleigh Waters","A 1km walk to the beach"),
       ("A2_25","7×6.2m powered workshop","Room for the tools, boat + projects"),
       ("A3_26","220m² family home","Four bedrooms upstairs"),
       ("A4_22t","A separate downstairs zone","Its own kitchenette + bathroom"),
       ("A5_09t","Unrenovated — priced for it","$1,915,000"),
       ("A6_02","93 Burleigh Street","Message me for the property pack")],
 "B": [("B1_01_Hero","822m² · ~19.9m frontage","1km walk to Burleigh Beach"),
       ("B2_25","44m² powered workshop","Hard to find this close to Burleigh"),
       ("B3_26","220m² · 4 bed · 3 bath","Solid family home on the block"),
       ("B4_09t","Original kitchen","Shown honestly"),
       ("B5_21t","Original bathroom","That's why it's $1,915,000"),
       ("B6_02","Change the house, keep the land","Message me for the property pack")],
 "C": [("C1_01_Hero","$1,915,000 in Burleigh Waters","822m², 1km to the beach"),
       ("C2_26","220m² · 4 bed · 3 bath","A full house, not an apartment"),
       ("C3_25","7×6.2m workshop + backyard","Space that's hard to buy down south"),
       ("C4_12t","Room to spread out","Living upstairs and down"),
       ("C5_09t","Not renovated","So you're not paying for someone else's"),
       ("C6_01_Hero","93 Burleigh Street","Message me for floorplan + video")],
}

def _call(method, path, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = TOK
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=60, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j

def upload_image(arm, stem):
    p = os.path.join(CLEAN, arm, stem + ".png")
    with open(p, "rb") as fh:
        r = requests.post(f"{B}/{ACT}/adimages", data={"access_token": TOK},
                          files={stem + ".png": fh}, timeout=120)
    j = r.json()
    if j.get("error"): raise RuntimeError(f"adimage {stem} FAILED: {j['error']}")
    return list(j["images"].values())[0]["hash"]

def create_campaign():
    return _call("POST", f"{ACT}/campaigns",
                 name="93 Burleigh St — Messenger Carousel",
                 objective="OUTCOME_ENGAGEMENT",
                 special_ad_categories=["HOUSING"],
                 special_ad_category_country=["AU"],
                 is_adset_budget_sharing_enabled=False,
                 status="PAUSED")["id"]

def create_adset(camp, arm):
    targeting = {
        "geo_locations": {"cities": [], "neighborhoods": [],
                          "custom_locations": []},
        "targeting_automation": {"advantage_audience": 1},
    }
    # split keys by type: Sydney is a city, the rest neighborhoods
    cities = [{"key": str(k), "radius": 30, "distance_unit": "kilometer"} for k in GEO[arm] if k == 114925]
    hoods  = [{"key": str(k)} for k in GEO[arm] if k != 114925]
    targeting["geo_locations"] = {}
    if cities: targeting["geo_locations"]["cities"] = cities
    if hoods:  targeting["geo_locations"]["neighborhoods"] = hoods
    return _call("POST", f"{ACT}/adsets",
                 name=f"93Burleigh_{ARM_NAME[arm]}_MSG",
                 campaign_id=camp,
                 daily_budget=BUDGET[arm],
                 billing_event="IMPRESSIONS",
                 optimization_goal="CONVERSATIONS",
                 destination_type="MESSENGER",
                 bid_strategy="LOWEST_COST_WITHOUT_CAP",
                 promoted_object={"page_id": PAGE},
                 targeting=targeting,
                 status="PAUSED")["id"]

def create_creative(arm, hashes):
    children = []
    for stem, name, desc in CARDS[arm]:
        children.append({
            "image_hash": hashes[stem],
            "name": name,
            "description": desc,
            "link": PAGE_URL,
            "call_to_action": {"type": "MESSAGE_PAGE", "value": {"app_destination": "MESSENGER"}},
        })
    oss = {"page_id": PAGE, "link_data": {
        "link": PAGE_URL,
        "message": PRIMARY[arm],
        "multi_share_optimized": False,
        "multi_share_end_card": False,
        "child_attachments": children,
        "call_to_action": {"type": "MESSAGE_PAGE", "value": {"app_destination": "MESSENGER"}},
        "page_welcome_message": WELCOME,
    }}
    return _call("POST", f"{ACT}/adcreatives",
                 name=f"93Burleigh creative {arm}", object_story_spec=oss)["id"]

def create_ad(arm, adset_id, creative_id):
    return _call("POST", f"{ACT}/ads",
                 name=f"93Burleigh Ad {ARM_NAME[arm]}",
                 adset_id=adset_id, creative={"creative_id": creative_id},
                 status="PAUSED")["id"]

def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    print("· uploading clean images (idempotent by hash)")
    hashes = {}
    for arm in "ABC":
        for stem, *_ in CARDS[arm]:
            if stem not in hashes:
                hashes[stem] = upload_image(arm, stem)
                print(f"   {stem} -> {hashes[stem][:12]}…")
    camp = state.get("campaign_id") or create_campaign()
    print("· campaign:", camp)
    state["campaign_id"] = camp; state.setdefault("arms", {})
    json.dump(state, open(IDS_PATH, "w"), indent=2)
    for arm in "ABC":
        a = state["arms"].get(arm, {})
        if a.get("ad_id"):
            print(f"· arm {arm}: already built ({a['ad_id']})"); continue
        a["adset_id"] = a.get("adset_id") or create_adset(camp, arm)
        a["creative_id"] = a.get("creative_id") or create_creative(arm, hashes)
        a["ad_id"] = create_ad(arm, a["adset_id"], a["creative_id"])
        state["arms"][arm] = a
        json.dump(state, open(IDS_PATH, "w"), indent=2)
        print(f"· arm {arm}: adset {a['adset_id']} · creative {a['creative_id']} · ad {a['ad_id']}")
    print("\nBUILT (all PAUSED). IDs ->", IDS_PATH)
    return state

def activate():
    ids = json.load(open(IDS_PATH))
    _call("POST", ids["campaign_id"], status="ACTIVE"); print("campaign ACTIVE")
    for arm, o in ids["arms"].items():
        _call("POST", o["adset_id"], status="ACTIVE")
        _call("POST", o["ad_id"], status="ACTIVE")
        print(f"arm {arm} ACTIVE")
    print("\nLIVE — $65/day total ($20 A + $25 B + $20 C).")

if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
