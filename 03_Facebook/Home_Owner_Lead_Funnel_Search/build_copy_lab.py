#!/usr/bin/env python3
"""
build_copy_lab.py — the CTR "Copy Lab": a fast, cheap hook/creative test that runs the
same 7 hooks as TRAFFIC (link-click) ads across South-East Queensland (Brisbane-led, ~4x
the GC audience), so we rank hooks in HOURS without burning the GC audience or harvesting
leads we won't serve. Winners' fundamentals get promoted into the GC served lead funnel.

Honest geo: SEQ viewers see GC/QLD stats that are true and locally relevant.
No lead forms here (no PII) — pure cost-per-click / CTR signal → PostHog behaviour bonus.

Reuses the image_hashes already uploaded by build_campaign.py (launch_ids.json).
Everything PAUSED. Activate: python3 build_copy_lab.py --activate
"""
import os, sys, json, requests
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")

ACT="act_1463563608441065"; PAGE="889412530933297"; API="https://graph.facebook.com/v21.0"
TOKEN=os.environ["FACEBOOK_ADS_TOKEN"]
HERE=os.path.dirname(os.path.abspath(__file__))
LAUNCH=json.load(open(os.path.join(HERE,"launch_ids.json")))
IDS_FILE=os.path.join(HERE,"copylab_ids.json")
DEST="https://fieldsestate.com.au/analyse-your-home"
DAILY=1000  # A$10/day per lab ad

# reuse uploaded image hashes (key = ad key from build_campaign)
IMG=LAUNCH["images"]

# 7 distinct hooks (short punchy traffic copy — CTR test). headline = link 'name'.
LAB=[
 {"key":"CL1_honest89","img":IMG["AN1_honest89"],
  "headline":"89% of Gold Coast online home estimates were overvalued.",
  "text":"We tested 1,689 of them against real sale prices. See what the comparable sales actually say a home like yours is worth — as a range, not a guess."},
 {"key":"CL2_missmillion","img":IMG["AN2_missmillion"],
  "headline":"An online tool valued a home at $1,440,000. It sold for $2,500,000.",
  "text":"\"High confidence\" — and wrong by over a million. How far off is the number for a home like yours?"},
 {"key":"CL3_neighbour","img":IMG["AN3_neighbour"],
  "headline":"A home near you sold for $55,000 more — and 59 days faster.",
  "text":"Two near-identical homes, same suburb. The difference wasn't the house. See what the recent sales near you say."},
 {"key":"CL5_national","img":IMG["AN5_national"],
  "headline":"The market is \"crashing\" — nationally. Your street may say otherwise.",
  "text":"1 in 5 homes is being pulled from sale nationally. On the southern Gold Coast the discount is 0.4-2.3% vs 3.6%. See which story your data tells."},
 {"key":"CL6_gap","img":IMG["AN6_gap"],
  "headline":"There's often a five-figure gap between an agent's quote and the comparables.",
  "text":"Sometimes above, sometimes below. We show you the recent comparable sales — as a range. You draw the conclusion."},
 {"key":"CL7_soldalerts","img":IMG["AN7_soldalerts"],
  "headline":"Get your Queensland suburb's real sold prices — the day they settle.",
  "text":"The sale prices that never hit the headlines, sent to you free. No pitch — just the numbers."},
 {"key":"CL8_differentnumber","img":IMG["AN8_differentnumber"],
  "headline":"Every agent gives you a different number. Get a data-only one instead.",
  "text":"Most tell you what you want to hear. Get a read on a home like yours from real comparable sales. No sales pitch."},
]

# SEQ: Brisbane centroid, 45mi radius (covers Brisbane, Ipswich, GC, Sunshine Coast fringe)
TARGETING={"geo_locations":{"custom_locations":[
             {"latitude":-27.4705,"longitude":153.0260,"radius":45,"distance_unit":"mile"}]},
           "publisher_platforms":["facebook","instagram"]}
CAMPAIGN_NAME="Copy Lab: Home Owner Hooks — SEQ CTR v1"

def post(path,payload):
    payload={k:(json.dumps(v) if isinstance(v,(dict,list)) else v) for k,v in payload.items()}
    payload["access_token"]=TOKEN
    return requests.post(f"{API}/{path}",data=payload,timeout=40).json()

def build():
    st={"campaign":None,"adsets":{},"ads":{}}
    c=post(f"{ACT}/campaigns",{"name":CAMPAIGN_NAME,"objective":"OUTCOME_TRAFFIC",
        "special_ad_categories":["HOUSING"],"is_adset_budget_sharing_enabled":False,"status":"PAUSED"})
    if "id" not in c: raise SystemExit(f"campaign fail: {c}")
    st["campaign"]=c["id"]; print("campaign",c["id"])
    for v in LAB:
        aset=post(f"{ACT}/adsets",{"name":f"{v['key']} — SEQ — A$10/day","campaign_id":st["campaign"],
            "optimization_goal":"LINK_CLICKS","billing_event":"IMPRESSIONS",
            "bid_strategy":"LOWEST_COST_WITHOUT_CAP","daily_budget":DAILY,
            "targeting":TARGETING,"status":"PAUSED"})
        if "id" not in aset: raise SystemExit(f"adset fail {v['key']}: {aset}")
        st["adsets"][v["key"]]=aset["id"]
        story={"page_id":PAGE,"link_data":{"image_hash":v["img"],"message":v["text"],
            "name":v["headline"],"link":DEST,"call_to_action":{"type":"LEARN_MORE"}}}
        cre=post(f"{ACT}/adcreatives",{"name":f"{v['key']}-cre","object_story_spec":story})
        if "id" not in cre: raise SystemExit(f"creative fail {v['key']}: {cre}")
        a=post(f"{ACT}/ads",{"name":v["key"],"adset_id":aset["id"],
            "creative":{"creative_id":cre["id"]},"status":"PAUSED"})
        if "id" not in a: raise SystemExit(f"ad fail {v['key']}: {a}")
        st["ads"][v["key"]]=a["id"]; print(f"  {v['key']}: adset {aset['id']} ad {a['id']}")
    json.dump(st,open(IDS_FILE,"w"),indent=2)
    print(f"\nAll PAUSED. IDs -> {IDS_FILE}")

def set_status(status):
    st=json.load(open(IDS_FILE)); post(st["campaign"],{"status":status})
    for a in st["adsets"].values(): post(a,{"status":status})
    for a in st["ads"].values(): post(a,{"status":status})
    print(f"copy lab -> {status}")

if __name__=="__main__":
    if "--activate" in sys.argv: set_status("ACTIVE")
    elif "--pause" in sys.argv: set_status("PAUSED")
    else: build()
