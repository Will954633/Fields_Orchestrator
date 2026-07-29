#!/usr/bin/env python3
"""
build_campaign.py — Build the Home Owner Lead Funnel launch batch on Facebook.
Creates ONE OUTCOME_LEADS campaign (HOUSING special category) + N isolated $15/day
ad sets (LEAD_GENERATION, on-Facebook Instant Form) + one single-image ad each.

EVERYTHING IS CREATED PAUSED. Review, then activate with:
    python3 build_campaign.py --activate

Isolated ad sets (one creative each) = clean per-angle signal (the AYH lesson: shared
ad sets let Meta starve variants). GC-wide 25mi radius under HOUSING (no demo targeting).

Writes all IDs to launch_ids.json.
"""
import os, sys, json, requests
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")

ACT = "act_1463563608441065"
PAGE = "889412530933297"
API = "https://graph.facebook.com/v21.0"
TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
HERE = os.path.dirname(os.path.abspath(__file__))
IMGDIR = os.path.join(HERE, "creatives_launch")
IDS_FILE = os.path.join(HERE, "launch_ids.json")

FORM_REPORT  = "1961613607744103"
FORM_ALERTS  = "1689297792302611"
FORM_ADDRESS = "1307646261451971"

DEST = "https://fieldsestate.com.au/analyse-your-home"  # placeholder link + $-claim disclaimer page

# ---- The 8 launch ads (copy from 02_AD_COPY.md; top-ranked headline each) ----
ADS = [
 {"key":"AN1_honest89","img":"01_honest89.png","form":FORM_REPORT,
  "headline":"89% of Gold Coast online estimates were overvalued. See the real range.",
  "desc":"Comparable sales near you, shown as a range. No pitch.",
  "text":("We tested 1,689 online home-value estimates on the Gold Coast against what the homes actually "
          "sold for.\n\n89% were overvalued — by 11.4% on average.\n\nThat's the number a homeowner checks "
          "at 11pm before they tell anyone they're thinking of selling. It quietly sets the whole plan on a "
          "figure that was never real.\n\nAn automated estimate reads bedroom counts and old sales. It has "
          "never walked through your home. So we do it the other way: real comparable sales near you, "
          "adjusted for what makes your home different — shown as a range, not a guess. No pitch.")},

 {"key":"AN2_missmillion","img":"02_missmillion.png","form":FORM_REPORT,
  "headline":"An online tool valued a Gold Coast home at $1,440,000. It sold for $2,500,000.",
  "desc":"See the real comparable-sales range for a home like yours.",
  "text":("An online tool valued a Burleigh Waters home at $1,440,000. It sold for $2,500,000.\n\nThe same "
          "kind of tool valued another home at $2,120,000. It sold for $1,742,000.\n\nBoth were rated "
          "\"high confidence.\" One missed by more than a million dollars.\n\nThese tools have never seen "
          "inside your home. So what is a home like yours worth — not the guess, the evidence? Real "
          "comparable sales near you, shown as a range.")},

 {"key":"AN3_neighbour","img":"03_neighbour.png","form":FORM_REPORT,
  "headline":"A home near you sold for $55,000 more — and 59 days faster — than a near-identical one.",
  "desc":"See what the recent sales near you say about a home like yours.",
  "text":("A home near you sold recently for $55,000 more than a near-identical one two streets away — and "
          "it sold 59 days faster.\n\nSame suburb. Same kind of home. The difference wasn't the house.\n\n"
          "One launched on a number the market didn't support, sat 61 days, and came down. The other was "
          "priced to the evidence and was gone in two days — for more.\n\nCurious what the recent sales "
          "near you actually say about a home like yours? We'll show you the comparable range.")},

 {"key":"AN4_honest89_addr","img":"01_honest89.png","form":FORM_ADDRESS,
  "headline":"89% of Gold Coast online estimates were overvalued. See what yours should be.",
  "desc":"Tell us your address — we'll match the right comparable sales.",
  "text":("We tested 1,689 online home-value estimates on the Gold Coast. 89% were overvalued — by 11.4% "
          "on average.\n\nAn automated estimate has never walked through your home. So tell us your address "
          "and we'll match the recent comparable sales near you, adjusted for your home — shown as a range, "
          "not a guess. No pitch.")},

 {"key":"AN5_national","img":"05_national.png","form":FORM_REPORT,
  "headline":"Nationally, 1 in 5 homes is being pulled from sale. On the southern Gold Coast: 0.4–2.3% vs 3.6%.",
  "desc":"See what your street's data actually says.",
  "text":("You're reading that the market is crashing. Nationally, the headlines have a point: listings are "
          "at a six-year high, and roughly 1 in 5 auctions is being withdrawn.\n\nYour street may be telling "
          "a different story. On the southern Gold Coast, the gap between asking and selling price has been "
          "running 0.4%–2.3% — against 3.6% nationally.\n\nNational numbers and your suburb's numbers are two "
          "different things. See which one a home like yours sits in — the recent comparable sales near you, "
          "as a range.")},

 {"key":"AN6_gap","img":"06_gap.png","form":FORM_REPORT,
  "headline":"There's often a five-figure gap between an agent's quote and what the comparables support.",
  "desc":"See the gap for a home like yours. Data only.",
  "text":("There's often a five-figure gap between the first number an agent quotes and what the comparable "
          "sales actually support.\n\nSometimes it's above. Sometimes below. Either way, it's the difference "
          "between a plan built on evidence and one built on a number someone thought you wanted to hear.\n\n"
          "We don't quote a number we think you'll like. We show you the recent comparable sales near you, "
          "adjusted for your home — as a range. You draw the conclusion.")},

 {"key":"AN7_soldalerts","img":"07_soldalerts.png","form":FORM_ALERTS,
  "headline":"Get your Gold Coast suburb's real sold prices — the day they settle.",
  "desc":"Free. No pitch — just the numbers.",
  "text":("Every week, homes on the Gold Coast sell for prices that never make the headlines — and often "
          "settle before they're updated on the portals.\n\nWe track them: the real sale price, days on "
          "market, and how it compared to the suburb, the day it settles.\n\nWant your suburb's sold prices "
          "sent to you as they happen? Free. No pitch — just the numbers, so you always know what a home "
          "like yours is really doing.")},

 {"key":"AN8_differentnumber","img":"08_differentnumber.png","form":FORM_REPORT,
  "headline":"Every agent gives you a different number. Get a data-only one instead.",
  "desc":"From the comparable sales — not from someone trying to win a listing.",
  "text":("Every agent gives you a different number. Most are telling you what you want to hear — a high one "
          "to win the listing, or a low one for a quick sale.\n\nWe're a data service, not a call centre. So "
          "here's a different offer: a data-only read on a home like yours, from real comparable sales near "
          "you. Shown as a range. No sales pitch.\n\nIf you want to talk it through, we're here. If you just "
          "want the numbers, take them.")},
]

CAMPAIGN_NAME = "Leads: Home Owner Funnel — Seller Intent GC v1"
# GC-wide 25mi radius (HOUSING floor is 15mi; covers all of the Gold Coast)
TARGETING = {"geo_locations":{"custom_locations":[
                {"latitude":-28.0167,"longitude":153.4000,"radius":25,"distance_unit":"mile"}]},
             "publisher_platforms":["facebook","instagram"]}

def post(path, payload):
    payload = {k:(json.dumps(v) if isinstance(v,(dict,list)) else v) for k,v in payload.items()}
    payload["access_token"] = TOKEN
    return requests.post(f"{API}/{path}", data=payload, timeout=40).json()

def upload_image(path):
    with open(path,"rb") as fh:
        r = requests.post(f"{API}/{ACT}/adimages", data={"access_token":TOKEN},
                          files={os.path.basename(path):fh}, timeout=60).json()
    imgs = r.get("images",{})
    if not imgs:
        raise SystemExit(f"image upload failed for {path}: {r}")
    return list(imgs.values())[0]["hash"]

def build():
    state = {"campaign":None,"adsets":{},"creatives":{},"ads":{},"images":{}}
    # 1) campaign (paused)
    c = post(f"{ACT}/campaigns", {"name":CAMPAIGN_NAME,"objective":"OUTCOME_LEADS",
             "special_ad_categories":["HOUSING"],"is_adset_budget_sharing_enabled":False,
             "status":"PAUSED"})
    if "id" not in c: raise SystemExit(f"campaign create failed: {c}")
    state["campaign"] = c["id"]; print(f"campaign {c['id']}")
    # 2) per-angle adset + creative + ad
    for ad in ADS:
        img_hash = upload_image(os.path.join(IMGDIR, ad["img"]))
        state["images"][ad["key"]] = img_hash
        aset = post(f"{ACT}/adsets", {
            "name":f"{ad['key']} — GC 25mi — A$15/day","campaign_id":state["campaign"],
            "optimization_goal":"LEAD_GENERATION","billing_event":"IMPRESSIONS",
            "bid_strategy":"LOWEST_COST_WITHOUT_CAP",
            "destination_type":"ON_AD","daily_budget":1500,
            "promoted_object":{"page_id":PAGE},"targeting":TARGETING,"status":"PAUSED"})
        if "id" not in aset: raise SystemExit(f"adset failed {ad['key']}: {aset}")
        state["adsets"][ad["key"]] = aset["id"]
        story = {"page_id":PAGE,"link_data":{
            "image_hash":img_hash,"message":ad["text"],"name":ad["headline"],
            "description":ad["desc"],"link":DEST,
            "call_to_action":{"type":"LEARN_MORE","value":{"lead_gen_form_id":ad["form"]}}}}
        cre = post(f"{ACT}/adcreatives", {"name":f"{ad['key']}-creative",
                   "object_story_spec":story})
        if "id" not in cre: raise SystemExit(f"creative failed {ad['key']}: {cre}")
        state["creatives"][ad["key"]] = cre["id"]
        a = post(f"{ACT}/ads", {"name":ad["key"],"adset_id":aset["id"],
                 "creative":{"creative_id":cre["id"]},"status":"PAUSED"})
        if "id" not in a: raise SystemExit(f"ad failed {ad['key']}: {a}")
        state["ads"][ad["key"]] = a["id"]
        print(f"  {ad['key']}: adset {aset['id']} ad {a['id']}")
    json.dump(state, open(IDS_FILE,"w"), indent=2)
    print(f"\nAll PAUSED. IDs -> {IDS_FILE}")

def set_status(status):
    state = json.load(open(IDS_FILE))
    post(state["campaign"], {"status":status})
    for key,aid in state["adsets"].items():
        post(aid, {"status":status})
    for key,aid in state["ads"].items():
        post(aid, {"status":status})
    print(f"campaign + {len(state['ads'])} adsets/ads -> {status}")

if __name__ == "__main__":
    if "--activate" in sys.argv: set_status("ACTIVE")
    elif "--pause" in sys.argv: set_status("PAUSED")
    else: build()
