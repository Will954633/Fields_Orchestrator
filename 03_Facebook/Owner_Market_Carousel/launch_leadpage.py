#!/usr/bin/env python3
"""
launch_leadpage.py — the WEBSITE lead-capture arm of Owner Market.

Replaces the Meta in-app Instant Form (launch_forms.py) with a website campaign whose
ads drive to our own landing page /find/<slug> (FindYourHomePage), where the homeowner
enters address -> name + phone and we text them their link (find_landing_sms.py). This
lets us own the design, analytics and — crucially — optimise on OUR pixel 'Lead' event
(fired on the capture step), which the Instant-Form campaign could not.

Structure:
  Campaign  OUTCOME_LEADS, ABO, PAUSED
  Ad set    $15/day, destination WEBSITE, optimize OFFSITE_CONVERSIONS on the Fields
            pixel 'Lead' custom_event_type, geofenced to the one suburb, PAUSED
  Creative  the SAME 5-card carousel as the other Owner-Market arms -> /find/<slug>,
            CTA LEARN_MORE (Meta's carousel enum has no GET_STARTED)
  Ad        PAUSED

Everything PAUSED. On --activate (Will only) it also PAUSES the Instant-Form campaign
so the two don't double-spend on the same suburbs.

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_leadpage.py            # build everything PAUSED
  python3 launch_leadpage.py --activate # (DO NOT run without Will's go-ahead)
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# reuse the carousel arm's uploader, API caller, and shared constants verbatim
import launch_campaign as lc

TOK, ACT, PAGE, PIXEL = lc.TOK, lc.ACT, lc.PAGE, lc.PIXEL
SUBURBS, ORDER, CARD_NAMES = lc.SUBURBS, lc.ORDER, lc.CARD_NAMES
IDS_PATH = os.path.join(HERE, "leadpage_ids.json")
FORM_CAMPAIGN_ID = "120252423820580134"  # the Instant-Form campaign to pause at switchover
DAILY_BUDGET_CENTS = 1500  # AUD $15/day per ad set


def landing(slug):
    return (f"https://fieldsestate.com.au/find/{slug}"
            f"?utm_source=facebook&utm_medium=paid_social"
            f"&utm_campaign=owner_market_leadpage&utm_content={slug}")


def primary_text(name):
    return (
        "Sydney and Melbourne have turned. Brisbane has slipped. The Gold Coast is still "
        "holding — but some of the early warning signs are beginning to change.\n\n"
        f"We tracked the estimated value of {name} homes over the past 18 months. Enter your "
        "address to see where your home sits—and the four market signals we're watching."
    )


def create_campaign():
    return lc._call("POST", f"{ACT}/campaigns", TOK,
                    name="Owner Market — Find Your Home (LEAD PAGE / pixel Lead, Aug 2026)",
                    objective="OUTCOME_LEADS", special_ad_categories=[],
                    is_adset_budget_sharing_enabled=False, status="PAUSED")["id"]


def create_adset(campaign_id, sub):
    s = SUBURBS[sub]
    targeting = {
        "geo_locations": {"neighborhoods": [{"key": s["geo_key"]}], "location_types": ["home"]},
        "age_min": 25,
        "targeting_automation": {"advantage_audience": 1},
    }
    return lc._call("POST", f"{ACT}/adsets", TOK,
                    name=f"Owner Market LEADPAGE · {s['name']}",
                    campaign_id=campaign_id,
                    daily_budget=DAILY_BUDGET_CENTS,
                    billing_event="IMPRESSIONS",
                    optimization_goal="OFFSITE_CONVERSIONS",
                    bid_strategy="LOWEST_COST_WITHOUT_CAP",
                    destination_type="WEBSITE",
                    promoted_object={"pixel_id": PIXEL, "custom_event_type": "LEAD"},
                    targeting=targeting,
                    status="PAUSED")["id"]


def create_creative(sub, hashes):
    s = SUBURBS[sub]; url = landing(s["slug"])
    children = []
    for num in ["01", "02", "03", "04", "05"]:
        child = {"image_hash": hashes[f"{sub}_{num}"], "link": url,
                 "call_to_action": {"type": "LEARN_MORE", "value": {"link": url}}}
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
    return lc._call("POST", f"{ACT}/adcreatives", TOK,
                    name=f"Owner Market LEADPAGE creative · {s['name']}", object_story_spec=oss)["id"]


def create_ad(sub, adset_id, creative_id):
    s = SUBURBS[sub]
    return lc._call("POST", f"{ACT}/ads", TOK,
                    name=f"Owner Market LEADPAGE Ad · {s['name']}",
                    adset_id=adset_id, creative={"creative_id": creative_id}, status="PAUSED")["id"]


def build():
    state = json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}
    print("· uploading 15 cards (Meta dedupes by hash)"); hashes = lc.upload_images()
    if state.get("campaign_id"):
        camp = state["campaign_id"]; print("· reusing campaign:", camp)
    else:
        camp = create_campaign(); print("· campaign:", camp)
    state["campaign_id"] = camp; state.setdefault("arms", {})
    for sub in ORDER:
        a = state["arms"].get(sub, {})
        if a.get("ad_id"):
            print(f"· {sub}: already built"); continue
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
    lc._call("POST", ids["campaign_id"], TOK, status="ACTIVE"); print("leadpage campaign ACTIVE")
    for sub, o in ids["arms"].items():
        lc._call("POST", o["adset_id"], TOK, status="ACTIVE")
        lc._call("POST", o["ad_id"], TOK, status="ACTIVE")
        print(f"{sub} ACTIVE")
    # switchover: pause the Instant-Form campaign so they don't double-spend
    lc._call("POST", FORM_CAMPAIGN_ID, TOK, status="PAUSED")
    print(f"Instant-Form campaign {FORM_CAMPAIGN_ID} PAUSED (switchover)")
    print("\nLEADPAGE CAMPAIGN LIVE — $45/day ($15 × 3). Ensure find_landing_sms.py is armed (cron).")


if __name__ == "__main__":
    if "--activate" in sys.argv: activate()
    else: build()
