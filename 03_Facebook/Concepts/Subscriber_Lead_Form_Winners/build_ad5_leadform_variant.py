#!/usr/bin/env python3
"""
build_ad5_leadform_variant.py — the AUTOFILL-FORM arm of the /exclusive-access A/B.

Background: the Advantage+ "Houses for sale" winner (source 120243619699320134) was cloned
verbatim into a TRAFFIC ad pointing at the manual /exclusive-access Name+Email gate
(build_ad5_lookalike.py). That gate captured 0 subscribers from 33 clicks. Will's call
(2026-08-28): run the SAME creative as a Meta Instant (lead) ad with a PREFILLED form and
compare cost-per-subscriber head-to-head.

Meta requires a single flattened creative for Instant Forms, so we cannot keep the Advantage+
asset_feed (per-placement crops). The 4 "images" in the source all share ONE image hash
(9f80727ae1f203b051083d8aec204677) — they are just crops — so flattening is lossless on the
image: one image + the one body + LEARN_MORE. This is the deliberate creative-vs-capture
confound Will accepted: the two arms differ in BOTH creative format (dynamic vs flat) and
capture (web gate vs prefilled form). The metric that decides is cost-per-captured-subscriber.

Form: FULL_NAME + EMAIL + PHONE, all prefilled from the Meta profile. NB Meta has no native
"optional field" for a standard prefilled question — PHONE is one-tap prefilled but must be
submitted; true skippability isn't supported without a non-prefilled custom question.

Objective OUTCOME_LEADS / LEAD_GENERATION / destination_type=ON_AD. Targeting + daily budget
copied VERBATIM from the source ad set, so it is an equal-budget, equal-targeting test.
Leads are auto-captured by scripts/fb-lead-puller.py (runs every 3 min): its generic buyer
branch stores to system_monitor.fb_leads, alerts Will on Telegram, and CRM-syncs — no puller
change needed (phone is stored in field_data regardless of which notify() renders it).

Everything is built PAUSED. --activate flips it live (into Meta review).

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 build_ad5_leadform_variant.py            # build PAUSED
  python3 build_ad5_leadform_variant.py --activate # set campaign+adset+ad ACTIVE
"""
import os, sys, json, requests

TOK  = os.environ["FACEBOOK_ADS_TOKEN"]
ACT  = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(HERE, "ad5_leadform_variant_ids.json")

SOURCE_AD = "120243619699320134"
# Both arms hand off to the SAME final page after capture, so the post-conversion
# experience matches the control's "continue to /for-sale-v4b".
FINAL_DEST = "https://fieldsestate.com.au/for-sale-v4b"
PRIVACY = "https://fieldsestate.com.au/privacy"
FORM_HEADLINE = "Fields exclusive access for subscribers only"
BASE = "Subscriber Lookalike LEADFORM — Houses for sale"


def _call(method, path, token, **fields):
    payload = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in fields.items()}
    payload["access_token"] = token
    kw = {"params": payload} if method == "GET" else {"data": payload}
    r = requests.request(method, f"{B}/{path}", timeout=120, **kw)
    j = r.json()
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        raise RuntimeError(f"{method} {path} FAILED: {json.dumps(j.get('error', j))}")
    return j


def page_token():
    return _call("GET", PAGE, TOK, fields="access_token")["access_token"]


def load_ids():
    return json.load(open(IDS_PATH)) if os.path.exists(IDS_PATH) else {}


def save_ids(d):
    json.dump(d, open(IDS_PATH, "w"), indent=1)


def flatten_source():
    """Pull the source Advantage+ creative and reduce to a single image + body + cta."""
    ad = _call("GET", SOURCE_AD, TOK,
               fields="adset_id,creative{asset_feed_spec}")
    afs = ad["creative"]["asset_feed_spec"]
    hashes = {i["hash"] for i in afs.get("images", []) if i.get("hash")}
    assert len(hashes) == 1, f"expected one image hash, got {hashes} — flattening not lossless"
    image_hash = hashes.pop()
    body = afs["bodies"][0]["text"]
    ctas = afs.get("call_to_action_types") or ["LEARN_MORE"]
    return ad["adset_id"], image_hash, body, ctas[0]


def create_form(ptok):
    thank_you = {
        "title": "You're in.",
        "body": "Opening your exclusive subscriber access now.",
        "button_type": "VIEW_WEBSITE",
        "website_url": FINAL_DEST,
        "button_text": "Continue",
    }
    return _call("POST", f"{PAGE}/leadgen_forms", ptok,
                 name="Subscriber access — Advantage+ leadform (name+email+phone)",
                 questions=[{"type": "FULL_NAME"}, {"type": "EMAIL"}, {"type": "PHONE"}],
                 question_page_custom_headline=FORM_HEADLINE,
                 privacy_policy={"url": PRIVACY, "link_text": "Privacy Policy"},
                 thank_you_page=thank_you,
                 follow_up_action_url=FINAL_DEST,
                 locale="en_US")["id"]


def main():
    ids = load_ids()

    if "--activate" in sys.argv:
        for lvl in ("adset_id", "ad_id", "campaign_id"):
            if ids.get(lvl):
                _call("POST", ids[lvl], TOK, status="ACTIVE")
        print(f"campaign {ids.get('campaign_id')} + adset + ad -> ACTIVE (Meta review)")
        return

    ptok = page_token()
    src_adset_id, image_hash, body, cta_type = flatten_source()
    print(f"flattened source: image {image_hash}, cta {cta_type}")

    # copy targeting + budget verbatim from the source ad set (equal-budget test)
    adset = _call("GET", src_adset_id, TOK,
                  fields="targeting,daily_budget,billing_event,bid_strategy")
    targeting = dict(adset["targeting"])
    ta = dict(targeting.get("targeting_automation", {}))
    if "advantage_audience" not in ta:
        ta["advantage_audience"] = 0  # preserve source age band
    targeting["targeting_automation"] = ta
    daily = adset.get("daily_budget") or "1000"

    if not ids.get("campaign_id"):
        ids["campaign_id"] = _call("POST", f"{ACT}/campaigns", TOK,
            name=f"{BASE} Campaign", objective="OUTCOME_LEADS",
            special_ad_categories=[], status="PAUSED",
            is_adset_budget_sharing_enabled=False)["id"]
        save_ids(ids); print("campaign", ids["campaign_id"])
    if not ids.get("form_id"):
        ids["form_id"] = create_form(ptok)
        save_ids(ids); print("form", ids["form_id"])
    if not ids.get("adset_id"):
        ids["adset_id"] = _call("POST", f"{ACT}/adsets", TOK,
            name=f"{BASE} Ad set", campaign_id=ids["campaign_id"],
            optimization_goal="LEAD_GENERATION", billing_event="IMPRESSIONS",
            bid_strategy=adset.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
            daily_budget=daily, destination_type="ON_AD",
            promoted_object={"page_id": PAGE},
            targeting=targeting, status="PAUSED")["id"]
        save_ids(ids); print(f"adset {ids['adset_id']} (budget {daily}c)")
    if not ids.get("creative_id"):
        link_data = {
            "link": FINAL_DEST,
            "message": body,
            "image_hash": image_hash,
            "call_to_action": {"type": cta_type,
                               "value": {"lead_gen_form_id": ids["form_id"]}},
        }
        ids["creative_id"] = _call("POST", f"{ACT}/adcreatives", TOK,
            name="Advantage+ flattened -> lead form",
            object_story_spec={"page_id": PAGE, "link_data": link_data},
            degrees_of_freedom_spec={"creative_features_spec": {}})["id"]
        save_ids(ids); print("creative", ids["creative_id"])
    if not ids.get("ad_id"):
        ids["ad_id"] = _call("POST", f"{ACT}/ads", TOK,
            name=f"{BASE} Ad", adset_id=ids["adset_id"],
            creative={"creative_id": ids["creative_id"]}, status="PAUSED")["id"]
        save_ids(ids); print("ad", ids["ad_id"])
    print("\nBuilt PAUSED. Review, then: python3 build_ad5_leadform_variant.py --activate")


if __name__ == "__main__":
    main()
