#!/usr/bin/env python3
"""
build_ad5_lookalike.py — duplicate the Advantage+ "Houses for sale" ad (#5) UNCHANGED
except that its destination becomes the new /exclusive-access gate page.

Ad #5 (source 120243619699320134) is the only winner that uses placement-customised
dynamic (Advantage+) creative — per-placement crops of the same listings screenshot.
That may be exactly why it worked, so we DON'T flatten it into a lead form. Instead we
clone its asset_feed_spec verbatim (fetched live) and change only link_urls -> /exclusive-access,
which shows the same view behind a Name+Email gate and then continues to /for-sale-v4b.

Targeting + budget are copied verbatim from the source ad set. Objective stays
OUTCOME_TRAFFIC. Everything PAUSED; --activate flips it live (after the LP is verified).

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
"""
import os, sys, json, copy, requests

TOK  = os.environ["FACEBOOK_ADS_TOKEN"]
ACT  = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(HERE, "ad5_lookalike_ids.json")

SOURCE_AD = "120243619699320134"
NEW_DEST  = "https://fieldsestate.com.au/exclusive-access"
OLD_DEST_HOST = "fieldsestate.com.au"


def _call(method, path, token, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = token
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=120, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j


def load_ids():
    return json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}


def save_ids(d):
    json.dump(d, open(IDS_PATH, "w"), indent=1)


def swap_urls(afs):
    """Return a copy of the asset_feed_spec with every website_url pointed at NEW_DEST."""
    afs = copy.deepcopy(afs)
    for lu in afs.get("link_urls", []):
        lu["website_url"] = NEW_DEST
        if "deeplink_url" in lu:
            lu.pop("deeplink_url", None)
    return afs


def main():
    ids = load_ids()

    if "--activate" in sys.argv:
        for lvl in ("adset_id", "ad_id", "campaign_id"):
            if ids.get(lvl):
                _call("POST", ids[lvl], TOK, status="ACTIVE")
        print(f"campaign {ids.get('campaign_id')} + adset + ad -> ACTIVE")
        return

    # pull the source creative (full asset_feed_spec) + adset targeting/budget
    ad = _call("GET", SOURCE_AD, TOK, fields="adset_id,creative{asset_feed_spec,object_story_spec}")
    afs = ad["creative"]["asset_feed_spec"]
    oss = ad["creative"].get("object_story_spec", {"page_id": PAGE})
    adset = _call("GET", ad["adset_id"], TOK,
                  fields="targeting,daily_budget,optimization_goal,billing_event,bid_strategy,promoted_object")

    new_afs = swap_urls(afs)
    dests = {lu["website_url"] for lu in new_afs.get("link_urls", [])}
    print("new destinations:", dests)
    assert dests == {NEW_DEST}, "URL swap incomplete"

    base = "Subscriber Lookalike — Houses for sale (Advantage+)"
    if not ids.get("campaign_id"):
        ids["campaign_id"] = _call("POST", f"{ACT}/campaigns", TOK,
            name=f"{base} Campaign", objective="OUTCOME_TRAFFIC",
            special_ad_categories=[], status="PAUSED",
            is_adset_budget_sharing_enabled=False)["id"]
        save_ids(ids); print("campaign", ids["campaign_id"])
    if not ids.get("adset_id"):
        targeting = dict(adset["targeting"])
        ta = dict(targeting.get("targeting_automation", {}))
        if "advantage_audience" not in ta:
            ta["advantage_audience"] = 0  # preserve source age band (Advantage+ caps age_min at 25)
        targeting["targeting_automation"] = ta
        adset["targeting"] = targeting
        kw = dict(name=f"{base} Ad set", campaign_id=ids["campaign_id"],
                  optimization_goal=adset.get("optimization_goal", "LINK_CLICKS"),
                  billing_event=adset.get("billing_event", "IMPRESSIONS"),
                  bid_strategy=adset.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
                  daily_budget=adset.get("daily_budget", "1000"),
                  targeting=adset["targeting"], status="PAUSED")
        ids["adset_id"] = _call("POST", f"{ACT}/adsets", TOK, **kw)["id"]
        save_ids(ids); print("adset", ids["adset_id"])
    if not ids.get("creative_id"):
        ids["creative_id"] = _call("POST", f"{ACT}/adcreatives", TOK,
            name="Houses for sale (Advantage+) -> /exclusive-access",
            object_story_spec=oss, asset_feed_spec=new_afs)["id"]
        save_ids(ids); print("creative", ids["creative_id"])
    if not ids.get("ad_id"):
        ids["ad_id"] = _call("POST", f"{ACT}/ads", TOK,
            name=f"{base} Ad", adset_id=ids["adset_id"],
            creative={"creative_id": ids["creative_id"]}, status="PAUSED")["id"]
        save_ids(ids); print("ad", ids["ad_id"])
    print("\nBuilt PAUSED. After LP verified live: python3 build_ad5_lookalike.py --activate")


if __name__ == "__main__":
    main()
