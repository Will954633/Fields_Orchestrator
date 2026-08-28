#!/usr/bin/env python3
"""
launch_subscriber_lead_forms.py — duplicate proven TRAFFIC ads as pre-filled LEAD ads.

For each source ad we build a NEW OUTCOME_LEADS campaign whose ad is creative-identical to
the source (same video/image, headline, primary text) but opens a minimal Instant Form:
FULL_NAME + EMAIL only (both prefill from the Meta profile), one headline statement
"Fields exclusive access for subscribers only", no intro card, no extra questions. The
form's thank-you screen sends the subscriber to the SAME landing page as the original ad.

Targeting + daily budget are copied VERBATIM from the source ad set at runtime, so nothing
about who sees it or what it costs changes — only the added form step.

Everything is created PAUSED. `--activate` flips campaigns to ACTIVE (into Meta review).
Idempotency: re-running reuses IDs already saved in lead_form_ids.json (skips rebuild).

Env: FACEBOOK_ADS_TOKEN, FACEBOOK_AD_ACCOUNT_ID, FACEBOOK_PAGE_ID.
Usage:
  python3 launch_subscriber_lead_forms.py            # build all PAUSED
  python3 launch_subscriber_lead_forms.py --only 3   # build only source #3
  python3 launch_subscriber_lead_forms.py --activate # set campaigns ACTIVE (Meta review)
"""
import os, sys, json, time, requests

TOK  = os.environ["FACEBOOK_ADS_TOKEN"]
ACT  = os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_1463563608441065")
if not ACT.startswith("act_"): ACT = "act_" + ACT
PAGE = os.environ.get("FACEBOOK_PAGE_ID", "889412530933297")
B = "https://graph.facebook.com/v20.0"
HERE = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(HERE, "lead_form_ids.json")

PRIVACY = "https://fieldsestate.com.au/privacy"
FORM_HEADLINE = "Fields exclusive access for subscribers only"

# ── The five source ads. #5 is handled separately (lookalike landing page), so 4 here.
#    Each `creative` block reproduces the visible ad exactly; only the CTA is swapped to
#    open the lead form. Targeting + budget are pulled from `source_ad` at runtime.
SOURCES = [
  {
    "n": 1, "label": "Traffic for homes (video)",
    "source_ad": "120244615219210134",
    "landing": "https://fieldsestate.com.au/for-sale-v3",
    "cta": "LEARN_MORE",
    "creative": {
      "kind": "video",
      "video_id": "876449345413933",
      "thumb_url": ("https://scontent-syd2-1.xx.fbcdn.net/v/t15.5256-10/"
                    "664119128_3174330916103676_3857161660800193524_n.jpg"),
      "message": ("What if every property listing came with the data agents don't put in "
                  "the brochure?\n\nComparable sales. Condition scores. Price vs value.\n\n"
                  "That's what we built."),
      "title": "The property data buyers never see",
    },
  },
  {
    "n": 2, "label": "Tailored: Buyer Landing Page Test",
    "source_ad": "120245339779970134",
    "landing": "https://fieldsestate.com.au/for-sale-v3",
    "cta": "SEE_DETAILS",
    "creative": {
      "kind": "image",
      "image_hash": "15a27f9db011c1f46cc2e0a4997ae3c4",
      "message": ("270+ properties for sale across Robina, Burleigh Waters, and Varsity "
                  "Lakes right now. You don't need to look at all of them. \n\nYou need "
                  "the 5 that matter.\n\nEvery Friday, we analyse every listing and send "
                  "you the 5 worth your attention — with comparable sales data you "
                  "can't get on Domain."),
      "name": "See the Full Analysis",
      "description": "5 Property Friday — Free weekly",
    },
  },
  {
    "n": 3, "label": "Who buys a home for $1,550,000 (photo)",
    "source_ad": "120244636404650134",
    "landing": ("https://fieldsestate.com.au/articles/"
                "someone-paid-1550000-burleigh-waters-home-sold-3465000"),
    "cta": "LEARN_MORE",
    "creative": {
      "kind": "image",
      # photo post has no ad image_hash; pull the original-resolution photo (1430x850)
      # via the page token at run time (CDN URLs are short-lived / 403 when hardcoded).
      "photo_id": "122110708707252069",
      "message": ("Who buys a home for $1,550,000 and sells it eighteen months later for "
                  "$3,465,000?\n\nSomeone who saw a 536 sqm lot in Burleigh Waters — "
                  "500 metres from the beach — and knew the land was worth more than "
                  "the house on it.\n\nThe full transaction history goes back to 2012. "
                  "Every sale. Every rental. Every price.\n\nOne property. Four owners. "
                  "A $2.5 million price swing in six years.\n\nFull story below."),
      "name": "",  # photo ad had no headline — keep it caption-only
    },
  },
  {
    "n": 4, "label": "Traffic: Buyer Landing Page v4b",
    "source_ad": "120245347869800134",
    "landing": "https://fieldsestate.com.au/for-sale-v4b",
    "cta": "LEARN_MORE",
    "creative": {
      "kind": "image",
      "image_hash": "30235767111afcf1c8ff733bf3cbc69e",
      "message": ("56 houses for sale in Burleigh Waters right now. Only a handful are "
                  "actually worth your attention.\n\nWe analyse every listing and send "
                  "you the 5 that stand out each Friday."),
      "name": "Property analysis you wont get on realestate.com.au",
    },
  },
]


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
    if os.path.exists(IDS_PATH):
        return json.load(open(IDS_PATH))
    return {}


def save_ids(d):
    json.dump(d, open(IDS_PATH, "w"), indent=1)


def upload_image_from_url(url, ptok):
    """Download the source image and upload to the ad account -> returns image hash."""
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    up = requests.post(f"{B}/{ACT}/adimages", data={"access_token": TOK},
                       files={"src.jpg": r.content}, timeout=120)
    j = up.json()
    if j.get("error"):
        raise RuntimeError(f"adimage upload FAILED: {j['error']}")
    return list(j["images"].values())[0]["hash"]


def video_thumb_hash(video_id, ptok):
    """The video's own preferred thumbnail -> uploaded to the ad account as an image hash."""
    j = _call("GET", f"{video_id}/thumbnails", ptok, fields="uri,is_preferred")
    thumbs = j.get("data", [])
    pref = next((t for t in thumbs if t.get("is_preferred")), thumbs[0] if thumbs else None)
    if not pref:
        return None
    return upload_image_from_url(pref["uri"], ptok)


def largest_photo_url(photo_id, ptok):
    j = _call("GET", photo_id, ptok, fields="images")
    imgs = sorted(j.get("images", []), key=lambda i: i.get("width", 0), reverse=True)
    return imgs[0]["source"]


def create_form(ptok, landing, form_name):
    """Minimal Instant Form: FULL_NAME + EMAIL (both prefill), one headline statement,
    no intro card, no custom questions. Thank-you -> the original landing page.
    (Form names are globally unique per page and cannot be reused — leadgen forms can't be
    hard-deleted — so callers pass a unique name.)"""
    thank_you = {
        "title": "You're in.",
        "body": "Opening your exclusive subscriber access now.",
        "button_type": "VIEW_WEBSITE",
        "website_url": landing,
        "button_text": "Continue",
    }
    return _call("POST", f"{PAGE}/leadgen_forms", ptok,
                 name=form_name,
                 questions=[{"type": "FULL_NAME"}, {"type": "EMAIL"}],
                 question_page_custom_headline=FORM_HEADLINE,
                 privacy_policy={"url": PRIVACY, "link_text": "Privacy Policy"},
                 thank_you_page=thank_you,
                 follow_up_action_url=landing,
                 locale="en_US")["id"]


def build_creative(src, form_id, ptok):
    c = src["creative"]
    cta = {"type": src["cta"], "value": {"lead_gen_form_id": form_id}}
    if c["kind"] == "video":
        video_data = {
            "video_id": c["video_id"],
            "message": c["message"],
            "title": c["title"],
            "call_to_action": cta,
        }
        th = video_thumb_hash(c["video_id"], ptok)
        if th:
            video_data["image_hash"] = th
        oss = {"page_id": PAGE, "video_data": video_data}
    else:
        img_hash = c.get("image_hash")
        if not img_hash:
            url = c.get("image_url") or largest_photo_url(c["photo_id"], ptok)
            img_hash = upload_image_from_url(url, ptok)
        link_data = {
            "link": src["landing"],
            "message": c["message"],
            "image_hash": img_hash,
            "call_to_action": cta,
        }
        if c.get("name"):
            link_data["name"] = c["name"]
        if c.get("description"):
            link_data["description"] = c["description"]
        oss = {"page_id": PAGE, "link_data": link_data}
    return _call("POST", f"{ACT}/adcreatives", TOK,
                 name=f"Lead form — {src['label']}",
                 object_story_spec=oss,
                 degrees_of_freedom_spec={"creative_features_spec": {}})["id"]


def build_one(src, ptok, ids):
    key = str(src["n"])
    rec = ids.get(key, {})
    # copy targeting + budget from the source ad set (verbatim)
    ad = _call("GET", src["source_ad"], TOK, fields="adset_id,name")
    adset = _call("GET", ad["adset_id"], TOK,
                  fields="targeting,daily_budget,billing_event,bid_strategy")
    targeting = dict(adset["targeting"])
    # Lead campaigns default Advantage+ audience ON, which caps age_min at 25 and would
    # override the source's exact age band. Preserve the source: keep advantage_audience
    # where it set it (#3 used 1), else pin it OFF so the age band copies verbatim.
    ta = dict(targeting.get("targeting_automation", {}))
    if "advantage_audience" not in ta:
        ta["advantage_audience"] = 0
    targeting["targeting_automation"] = ta
    daily = adset.get("daily_budget") or "1000"

    base = f"Subscriber Lead — {src['label']}"
    def _persist():
        ids[key] = rec; save_ids(ids)

    if not rec.get("campaign_id"):
        rec["campaign_id"] = _call("POST", f"{ACT}/campaigns", TOK,
            name=f"{base} Campaign", objective="OUTCOME_LEADS",
            special_ad_categories=[], status="PAUSED",
            is_adset_budget_sharing_enabled=False)["id"]
        _persist(); print(f"   #{src['n']} campaign {rec['campaign_id']}")
    if not rec.get("form_id"):
        rec["form_id"] = create_form(ptok, src["landing"],
            f"Subscriber access #{src['n']} — {src['landing'].rsplit('/',1)[-1]}")
        _persist(); print(f"   #{src['n']} form {rec['form_id']}")
    if not rec.get("adset_id"):
        rec["adset_id"] = _call("POST", f"{ACT}/adsets", TOK,
            name=f"{base} Ad set", campaign_id=rec["campaign_id"],
            optimization_goal="LEAD_GENERATION", billing_event="IMPRESSIONS",
            bid_strategy="LOWEST_COST_WITHOUT_CAP", daily_budget=daily,
            destination_type="ON_AD", promoted_object={"page_id": PAGE},
            targeting=targeting, status="PAUSED")["id"]
        _persist(); print(f"   #{src['n']} adset {rec['adset_id']} (budget {daily}c)")
    if not rec.get("creative_id"):
        rec["creative_id"] = build_creative(src, rec["form_id"], ptok)
        _persist(); print(f"   #{src['n']} creative {rec['creative_id']}")
    if not rec.get("ad_id"):
        rec["ad_id"] = _call("POST", f"{ACT}/ads", TOK,
            name=f"{base} Ad", adset_id=rec["adset_id"],
            creative={"creative_id": rec["creative_id"]}, status="PAUSED")["id"]
        _persist(); print(f"   #{src['n']} ad {rec['ad_id']}")
    return rec


def activate(ids, only=None):
    # All three levels must be ACTIVE to deliver. Order: adset + ad first, campaign last.
    for key, rec in sorted(ids.items()):
        if only and key != str(only): continue
        for lvl in ("adset_id", "ad_id", "campaign_id"):
            oid = rec.get(lvl)
            if oid:
                _call("POST", oid, TOK, status="ACTIVE")
        print(f"   #{key} campaign {rec.get('campaign_id')} + adset + ad -> ACTIVE")


def main():
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    ids = load_ids()
    if "--activate" in sys.argv:
        activate(ids, only)
        return
    ptok = page_token()
    for src in SOURCES:
        if only and str(src["n"]) != str(only): continue
        print(f"\n== Building #{src['n']}: {src['label']} ==")
        build_one(src, ptok, ids)
    print("\nAll built PAUSED. Review, then: python3 launch_subscriber_lead_forms.py --activate")


if __name__ == "__main__":
    main()
