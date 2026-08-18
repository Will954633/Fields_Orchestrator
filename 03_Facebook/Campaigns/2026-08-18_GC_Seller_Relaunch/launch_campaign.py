#!/usr/bin/env python3
"""
launch_campaign.py — builds and manages the GC Seller Relaunch ads on Meta.

This is the code that actually created what went live on 2026-08-18. Reconstructed and made
re-runnable so future edits are a copy-change-rerun rather than a rebuild from memory.

    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a

    python3 launch_campaign.py status                  # what is live right now
    python3 launch_campaign.py build --dry-run         # show what WOULD change
    python3 launch_campaign.py build                   # upload imgs, make creatives, swap in
    python3 launch_campaign.py enable                  # campaign + the 3 adsets/ads ACTIVE
    python3 launch_campaign.py pause                   # the 3 adsets back to PAUSED
    python3 launch_campaign.py geo                     # (re)apply the 3-suburb targeting

Copy lives in ADS below — edit it there, then `build` to push new creatives. Meta creatives
are immutable, so `build` always mints new ones and re-points the ads; the old creative is
left behind (harmless, and it preserves the history).

⚠ NEVER run `enable` on the campaign's other adsets. AN1 and AN4 sit in this same campaign
carrying the "1,689 estimates / 89% overvalued" claim, which is hindsight-contaminated
(91.8% of those estimates were captured AFTER the sale; clean subset n=21). Enable ads
individually, never the campaign wholesale.

⚠ HOUSING special ad category: radius targeting has a 17km MINIMUM (error #2909052). Named
neighbourhoods have no minimum, which is the only way to target single suburbs. Do not
"simplify" GEO back to a lat/lon radius.
"""
import argparse, json, os, sys, urllib.error, urllib.parse, urllib.request, uuid

API = "https://graph.facebook.com/v21.0"
ACCT = "act_1463563608441065"
PAGE = "889412530933297"
FORM = "1961613607744103"          # Fields — Seller Intent (report) v1 — name+email+phone
CAMPAIGN = "120251770885910134"    # Leads: Home Owner Funnel — Seller Intent GC v1
LINK = "https://fieldsestate.com.au/analyse-your-home"
CARDS = "/home/fields/Fields_Orchestrator/03_Facebook/Home_Owner_Lead_Funnel_Search/creatives_gc_relaunch"

# Robina 2687074 · Varsity Lakes 2674227 · Burleigh Waters 2719184
# location_types home-only: excludes tourists, which matters a great deal on the Gold Coast.
GEO = {"neighborhoods": [{"key": "2687074"}, {"key": "2674227"}, {"key": "2719184"}],
       "location_types": ["home"]}

DESC = "Recent comparable sales near you, as a range. No pitch."

# ── The three arms. `adset`/`ad` are the live objects; None means "create it".
ADS = {
    "GC2_missmillion": {
        "adset": "120251770889000134", "ad": "120251770889610134",
        "adset_name": "GC2_missmillion — Robina/Varsity/Burleigh Waters — A$15/day",
        "image": "GC2_missmillion_light.png",
        "headline": "An online estimate said $1,440,000. It sold for $2,500,000.",
        "body": (
            "An online estimate valued a Burleigh Waters home at $1,440,000. It sold for "
            "$2,500,000.\n\n"
            "The estimate carried a published range of $1,240,000 to $1,640,000, and was "
            "rated “high confidence.” The sale came in $860,000 above the top of it.\n\n"
            "These tools have never walked through your home. They read what is on paper.\n\n"
            "Curious what the comparable sales near you actually say about a home like "
            "yours? We’ll show you the range."),
    },
    "GC3_neighbourpair": {
        "adset": "120251770891620134", "ad": "120251770892710134",
        "adset_name": "GC3_neighbourpair — Robina/Varsity/Burleigh Waters — A$15/day",
        "image": "GC3_neighbourpair_dark.png",
        "headline": "Same suburb, same house, same land. $120,000 apart.",
        "body": (
            "Two homes in Varsity Lakes. Both three bedrooms, two bathrooms, two car "
            "spaces. Both on exactly 350 square metres.\n\n"
            "One sold in 4 days for $1,400,000. The other took 61 days and sold for "
            "$1,280,000.\n\n"
            "They sold three weeks apart, so the market barely moved between them. The "
            "difference wasn’t the market — and on paper, it wasn’t the house either.\n\n"
            "Curious what the recent sales near you actually say about a home like yours? "
            "We’ll show you the range."),
    },
    "GC5_thechoice": {
        "adset": "120252303732870134", "ad": "120252303736070134",
        "adset_name": "GC5_thechoice — Robina/Varsity/Burleigh Waters — A$15/day",
        "image": "GC5_thechoice_dark.png",
        "headline": "Two honest agents can be $469,000 apart.",
        "body": (
            "Three comparable sales. That is the standard method for valuing a home — and "
            "it is more fragile than it looks.\n\n"
            "We took 512 homes that later sold and enumerated every reasonable set of three "
            "comparable sales that could have been selected before the result was known. "
            "For the typical home, the gap between the highest and lowest defensible "
            "three-sale estimate was $469,000.\n\n"
            "That does not mean one answer was dishonest. It means choosing only a few "
            "sales makes the answer highly sensitive to which ones happen to be chosen.\n\n"
            "Curious what the full comparable set says about a home like yours? We’ll show "
            "you the range."),
    },
}


# ── BENCH. Built, verified, rendered — not live. Promote by moving an entry into ADS,
# creating its adset (clone an existing one), then `build` + `enable`.
# ⚠ Do NOT run a bench arm as a 4th concurrent arm: A$45/day across four arms drops each to
# ~210 reach/day, and the retirement rule below already needs ~3 weeks per arm at three.
BENCH = {
    "GC6_thesplit": {
        "adset": None, "ad": None,
        "adset_name": "GC6_thesplit — Robina/Varsity/Burleigh Waters — A$15/day",
        "image": "GC6_thesplit_dark.png",
        "headline": "The top quarter sold above asking. The bottom quarter took 5% less.",
        "body": (
            "Two homes, same suburb, same kind of house. One sells for more than the owner "
            "asked. The other takes 5% less than the number on the sign.\n\n"
            "Across 48 recent private-treaty sales in Robina, Varsity Lakes and Burleigh "
            "Waters, the top quarter achieved about 102% of their advertised price. The "
            "bottom quarter got about 95%. On a $1,500,000 home that spread is roughly "
            "$110,000.\n\n"
            "Auctions are excluded — there is no advertised price to measure against.\n\n"
            "Curious what the recent sales near you actually say about a home like yours? "
            "We\u2019ll show you the range."),
    },
}


def tok():
    t = os.environ.get("FACEBOOK_ADS_TOKEN")
    if not t:
        sys.exit("FACEBOOK_ADS_TOKEN not set — `set -a && source .env && set +a`")
    return t


def get(node, fields):
    q = urllib.parse.urlencode({"fields": fields, "access_token": tok()})
    return json.load(urllib.request.urlopen(f"{API}/{node}?{q}"))


def post(node, params, dry=False):
    if dry:
        show = {k: (v[:70] + "…" if isinstance(v, str) and len(v) > 70 else v)
                for k, v in params.items()}
        print(f"    DRY POST {node}: {show}")
        return {"id": "DRY"}
    data = urllib.parse.urlencode({**params, "access_token": tok()}).encode()
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(f"{API}/{node}", data=data)))
    except urllib.error.HTTPError as e:
        err = json.load(e)["error"]
        sys.exit(f"    FAIL {node}: {err.get('error_user_msg') or err.get('message')}")


def upload_image(path):
    """Multipart upload to /adimages. Returns the image hash."""
    b = open(path, "rb").read()
    bd = "----" + uuid.uuid4().hex
    body = b"".join([
        f'--{bd}\r\nContent-Disposition: form-data; name="access_token"\r\n\r\n{tok()}\r\n'.encode(),
        (f'--{bd}\r\nContent-Disposition: form-data; name="filename"; '
         f'filename="{os.path.basename(path)}"\r\nContent-Type: image/png\r\n\r\n').encode(),
        b, b"\r\n", f"--{bd}--\r\n".encode()])
    req = urllib.request.Request(f"{API}/{ACCT}/adimages", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
    r = json.load(urllib.request.urlopen(req))
    return list(r["images"].values())[0]["hash"]


def cmd_build(dry):
    """Upload images → create creatives → point the ads at them."""
    for key, a in ADS.items():
        path = os.path.join(CARDS, a["image"])
        if not os.path.exists(path):
            sys.exit(f"missing creative: {path} — run render_gc_relaunch_cards.py first")
        h = "DRYHASH" if dry else upload_image(path)
        print(f"  {key}: image {h}")
        spec = {"page_id": PAGE, "link_data": {
            "link": LINK, "message": a["body"], "name": a["headline"], "description": DESC,
            "image_hash": h,
            "call_to_action": {"type": "LEARN_MORE",
                               "value": {"lead_gen_form_id": FORM}}}}
        # NB: do NOT send degrees_of_freedom_spec / standard_enhancements — Meta deprecated
        # it and now rejects the whole creative (error_subcode 3858504).
        cr = post(f"{ACCT}/adcreatives",
                  {"name": f"{key} v1 (GC relaunch)", "object_story_spec": json.dumps(spec)}, dry)
        print(f"  {key}: creative {cr['id']}")
        if a["ad"]:
            post(a["ad"], {"creative": json.dumps({"creative_id": cr["id"]}),
                           "name": f"{key} — GC relaunch v1"}, dry)
            print(f"  {key}: ad {a['ad']} re-pointed")
        else:
            print(f"  {key}: no ad id in ADS — create the adset/ad manually, then record it")


def cmd_geo(dry):
    for key, a in ADS.items():
        tg = get(a["adset"], "targeting")["targeting"]
        tg["geo_locations"] = GEO
        post(a["adset"], {"targeting": json.dumps(tg), "name": a["adset_name"]}, dry)
        print(f"  {key}: geo -> 3 suburbs, home-only")


def cmd_status():
    c = get(CAMPAIGN, "name,effective_status,objective,special_ad_categories")
    print(f"CAMPAIGN [{c['effective_status']}] {c['name']}  {c['objective']}  "
          f"special={c.get('special_ad_categories')}\n")
    live = 0
    for s in get(f"{CAMPAIGN}/adsets", "name,effective_status,daily_budget,targeting,id")["data"]:
        ours = s["id"] in {a["adset"] for a in ADS.values()}
        geo = s["targeting"].get("geo_locations", {})
        loc = ("neighborhoods " + ",".join(n["key"] for n in geo["neighborhoods"])
               if "neighborhoods" in geo else "custom_locations/radius")
        bud = int(s.get("daily_budget") or 0) / 100
        if s["effective_status"] in ("ACTIVE", "IN_PROCESS"):
            live += bud
        print(f"{'►' if ours else ' '} [{s['effective_status']:12}] ${bud:6.2f}/day  {s['name'][:52]}")
        if ours:
            print(f"      {loc}  types={geo.get('location_types')}")
            for ad in get(f"{s['id']}/ads", "name,effective_status,creative{id}")["data"]:
                print(f"      AD [{ad['effective_status']:12}] creative "
                      f"{ad.get('creative', {}).get('id')}  {ad['name'][:40]}")
    print(f"\nLIVE SPEND: A${live:.2f}/day")


def cmd_set_status(state, dry):
    if state == "ACTIVE":
        post(CAMPAIGN, {"status": "ACTIVE"}, dry)
        print(f"  campaign ACTIVE")
    for key, a in ADS.items():
        post(a["adset"], {"status": state}, dry)
        if a["ad"]:
            post(a["ad"], {"status": state}, dry)
        print(f"  {key}: adset+ad {state}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["status", "build", "geo", "enable", "pause"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "build":
        cmd_build(args.dry_run)
    elif args.cmd == "geo":
        cmd_geo(args.dry_run)
    elif args.cmd == "enable":
        cmd_set_status("ACTIVE", args.dry_run)
    elif args.cmd == "pause":
        cmd_set_status("PAUSED", args.dry_run)


if __name__ == "__main__":
    main()
