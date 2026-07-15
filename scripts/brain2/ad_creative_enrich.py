#!/usr/bin/env python3
"""
ad_creative_enrich.py — Brain 2 Layer 1: correct + enrich ad creative structure.

The nightly fb-metrics-collector only requested creative{...object_story_spec},
which is EMPTY for ads built from an existing page post or from Advantage+/
dynamic (asset_feed_spec) creative. That made format detection fall through to
'single_image' / 'catalog' — 50 of 92 ads were mislabelled (videos stored as
single_image, dynamic-creative stored as catalog).

This script re-pulls every ad's creative with the authoritative fields
(object_type, video_id, asset_feed_spec{ad_formats,videos,images,bodies,titles,
descriptions,link_urls,call_to_action_types}, object_story_spec) and writes a
corrected, fully-detailed creative_structured block back onto ad_profiles.

Format truth table:
  video       : video_id | asset_feed_spec.videos | object_story_spec.video_data | object_type VIDEO
  carousel    : asset_feed_spec.ad_formats contains CAROUSEL | link_data.child_attachments
  single_image: everything else
  dynamic_creative flag: >1 candidate image OR ad_formats contains AUTOMATIC_FORMAT
    (FB optimises which single asset shows per placement — NOT a user-facing carousel)

Usage:
  python3 scripts/brain2/ad_creative_enrich.py --dry-run     # report diffs, write nothing
  python3 scripts/brain2/ad_creative_enrich.py               # enrich + write ad_profiles
  python3 scripts/brain2/ad_creative_enrich.py --id <AD_ID>  # single ad

Env: FACEBOOK_ADS_TOKEN (System User token), COSMOS_CONNECTION_STRING
"""
import os, sys, json, argparse, urllib.parse, urllib.request, time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

TOK = os.environ["FACEBOOK_ADS_TOKEN"]
ACC = "act_1463563608441065"
GRAPH = "https://graph.facebook.com/v21.0"

CREATIVE_FIELDS = (
    "id,name,object_type,video_id,thumbnail_url,image_url,image_hash,"
    "call_to_action_type,effective_object_story_id,"
    "asset_feed_spec,object_story_spec"
)
AD_FILTER = json.dumps([{
    "field": "effective_status", "operator": "IN",
    "value": ["ACTIVE", "PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED",
              "PENDING_REVIEW", "WITH_ISSUES", "DISAPPROVED", "ARCHIVED"],
}])


def fb(path, **params):
    params["access_token"] = TOK
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            return json.loads(urllib.request.urlopen(url, timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 613) and attempt < 3:
                time.sleep(2 ** attempt); continue
            raise


_PAGE_TOK = None


def page_token():
    """Page access token (System User manages the page) — for reading post copy."""
    global _PAGE_TOK
    if _PAGE_TOK is None:
        r = fb("889412530933297", fields="access_token")
        _PAGE_TOK = r.get("access_token", "")
    return _PAGE_TOK


def fetch_post_text(story_id):
    """Recover copy for ads built from an existing page post (video ads mostly)."""
    tok = page_token()
    if not tok or not story_id:
        return {}
    try:
        url = (f"{GRAPH}/{story_id}?"
               + urllib.parse.urlencode({"fields": "message",
                                         "access_token": tok}))
        d = json.loads(urllib.request.urlopen(url, timeout=60).read())
        return d
    except Exception:
        return {}


def fetch_all_ads():
    ads, after = [], None
    while True:
        p = {"fields": f"id,name,creative{{{CREATIVE_FIELDS}}}",
             "limit": 50, "filtering": AD_FILTER}
        if after:
            p["after"] = after
        d = fb(f"{ACC}/ads", **p)
        ads += d.get("data", [])
        after = d.get("paging", {}).get("cursors", {}).get("after")
        if not d.get("paging", {}).get("next"):
            break
    return ads


def _texts(assets):
    """Pull distinct .text values from an asset_feed_spec list."""
    out = []
    for a in assets or []:
        t = (a.get("text") or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def structure_creative(cr):
    """Return a fully-detailed, corrected creative block."""
    afs = cr.get("asset_feed_spec") or {}
    oss = cr.get("object_story_spec") or {}
    ld = oss.get("link_data") or {}
    vd = oss.get("video_data") or {}
    ad_formats = [f.upper() for f in (afs.get("ad_formats") or [])]

    # --- format ---
    is_video = bool(cr.get("video_id") or afs.get("videos") or vd
                    or (cr.get("object_type") or "").upper() == "VIDEO")
    is_carousel = ("CAROUSEL" in ad_formats) or bool(ld.get("child_attachments"))
    if is_video:
        fmt = "video"
    elif is_carousel:
        fmt = "carousel"
    else:
        fmt = "single_image"

    n_images = len(afs.get("images", []) or [])
    n_videos = len(afs.get("videos", []) or [])
    dynamic = (n_images > 1) or ("AUTOMATIC_FORMAT" in ad_formats)

    # --- every text variant (asset_feed_spec can hold many) ---
    bodies = _texts(afs.get("bodies")) or ([ld.get("message")] if ld.get("message")
                                           else [vd.get("message")] if vd.get("message")
                                           else [cr.get("body")] if cr.get("body") else [])
    titles = _texts(afs.get("titles")) or ([cr.get("title")] if cr.get("title")
                                           else [ld.get("name")] if ld.get("name") else [])
    descs = _texts(afs.get("descriptions")) or ([ld.get("description")]
                                                if ld.get("description") else [])
    ctas = [c.upper() for c in (afs.get("call_to_action_types") or [])]
    if not ctas:
        c = cr.get("call_to_action_type") or ld.get("call_to_action", {}).get("type") \
            or vd.get("call_to_action", {}).get("type")
        if c:
            ctas = [c.upper()]
    link_urls = _texts(afs.get("link_urls")) if afs.get("link_urls") else []
    if not link_urls:
        lu = ld.get("link") or cr.get("link_url")
        if lu:
            link_urls = [lu]

    primary_body = max(bodies, key=lambda b: len(b or "")) if bodies else ""
    return {
        "creative_id": cr.get("id", ""),
        "format": fmt,
        "object_type": cr.get("object_type", ""),
        "video_id": cr.get("video_id"),
        "dynamic_creative": dynamic,
        "ad_formats": ad_formats,
        "optimization_type": afs.get("optimization_type"),
        "n_media": {"images": n_images or (1 if cr.get("image_url") else 0),
                    "videos": n_videos or (1 if cr.get("video_id") else 0)},
        "bodies": bodies,
        "titles": titles,
        "descriptions": descs,
        "ctas": ctas,
        "link_urls": link_urls,
        "primary_body": primary_body,
        "primary_title": titles[0] if titles else "",
        "primary_cta": ctas[0] if ctas else "",
        "n_body_variants": len(bodies),
        "n_title_variants": len(titles),
        "effective_object_story_id": cr.get("effective_object_story_id", ""),
        "thumbnail_url": cr.get("thumbnail_url", ""),
        "image_url": cr.get("image_url", ""),
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id", help="single ad id")
    args = ap.parse_args()

    if args.id:
        cid = fb(args.id, fields="creative").get("creative", {}).get("id")
        cr = fb(cid, fields=CREATIVE_FIELDS)
        ads = [{"id": args.id, "name": fb(args.id, fields="name").get("name", ""),
                "creative": cr}]
    else:
        ads = fetch_all_ads()

    db = get_client()["system_monitor"]
    stored = {d["_id"]: (d.get("creative", {}) or {}).get("format")
              for d in db.ad_profiles.find({}, {"creative.format": 1})}

    changed, from_fmt, written, missing = [], {}, 0, 0
    for a in ads:
        aid = a["id"]
        s = structure_creative(a.get("creative", {}) or {})
        # Post-based ads (video mostly) carry copy in the page post, not the
        # creative spec — recover it via the page token.
        if not s["bodies"] and s["effective_object_story_id"]:
            post = fetch_post_text(s["effective_object_story_id"])
            msg = (post.get("message") or "").strip()
            if msg:
                s["bodies"] = [msg]
                s["primary_body"] = msg
                s["n_body_variants"] = 1
                s["copy_source"] = "page_post"
            if not s["titles"] and post.get("name"):
                s["titles"] = [post["name"]]
                s["primary_title"] = post["name"]
        old = stored.get(aid)
        if old and old != s["format"]:
            changed.append((aid, a.get("name", "")[:50], old, s["format"]))
            from_fmt[f"{old}->{s['format']}"] = from_fmt.get(f"{old}->{s['format']}", 0) + 1
        if not args.dry_run:
            res = db.ad_profiles.update_one(
                {"_id": aid},
                {"$set": {"creative_structured": s,
                          "creative.format": s["format"],
                          "creative.video_id": s["video_id"],
                          "creative.dynamic_creative": s["dynamic_creative"]}},
            )
            if res.matched_count:
                written += 1
            else:
                missing += 1

    print(f"ads processed: {len(ads)}")
    print(f"format corrections: {len(changed)}  {json.dumps(from_fmt)}")
    for c in changed[:60]:
        print(f"  {c[0]}  {c[1]:<50} {c[2]} -> {c[3]}")
    if args.dry_run:
        print("\n[dry-run] nothing written")
    else:
        print(f"\nwrote creative_structured to {written} ad_profiles"
              f" ({missing} FB ads had no ad_profiles doc yet)")


if __name__ == "__main__":
    main()
