#!/usr/bin/env python3
"""
build_listed_property.py — on-demand single-address listing builder (#2, 2026-08-01).

When a buyer opens an /off-market page for a home that PropRadar confirms is
CURRENTLY LISTED but we don't yet hold (the 6 Joy Avenue incident window: it
listed today, our nightly scrape hasn't run), the website loader enqueues a
build request. This drainer picks it up within a couple of minutes and:

  1. Scrapes THAT one Domain listing via the suburb scraper (creates the
     `for_sale` doc → /property renders the real listing: price, agent, photos,
     and the off-market loader's for_sale redirect gate now fires).
  2. Kicks editorial generation for the address (best-effort; if enrichment
     prerequisites aren't ready yet, nightly step 120 completes it).

The interim `/building/:slug` page the buyer sees polls until the `for_sale`
doc exists, then sends them to `/property/:slug`.

Queue: system_monitor.property_build_requests
  { _id, slug, address, suburb_key, postcode, status: pending|building|done|failed,
    requested_at, started_at, built_at, result_slug, error, attempts }

Run (cron every ~3 min):
    python3 scripts/build_listed_property.py --drain
    python3 scripts/build_listed_property.py --drain --once   # one pass, for testing
    python3 scripts/build_listed_property.py --address "6 Joy Avenue" --suburb burleigh_waters --postcode 4220
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import os
import re
import subprocess
import sys

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

from shared.db import get_client, cosmos_retry  # noqa: E402
from shared.env import load_env  # noqa: E402
from job_status import job_run  # noqa: E402

# Load .env HERE rather than trusting the caller. The cron line invoked this as
# `source .env && python3 …` with no `set -a`, so nothing in .env was ever
# EXPORTED into the child process. `shared.db` still connected (it falls back to
# config/settings.yaml), which is exactly what made this invisible — but
# BRIGHTDATA_API_KEY was absent, so run_curlffi_suburb_scrape.py:271
# (`use_unlocker = bool(os.environ.get('BRIGHTDATA_API_KEY'))`) fetched Domain
# directly from this Akamai-blocked VM IP, discovery returned 0 URLs, and every
# queued build failed with "address not found among 0 live listings" — 11 for 11,
# while job_run recorded success. See fix-history [BUILDER-ENV-EXPORT-GAP].
load_env()

SCRAPER_DIR = ("/home/fields/Property_Data_Scraping/03_Gold_Coast/"
               "Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold")
SCRAPER_PATH = f"{SCRAPER_DIR}/run_curlffi_suburb_scrape.py"
# The scraper resolves html_parser + its debug-log dir via CWD-RELATIVE
# sys.path.append() calls (they only work when run from SCRAPER_DIR). We import
# it from a different CWD, so make those imports resolvable by absolute path.
HTML_PARSER_DIR = ("/home/fields/Property_Data_Scraping/07_Undetectable_method/"
                   "00_Production_System/02_Individual_Property_Google_Search")
for _p in (SCRAPER_DIR, HTML_PARSER_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
EDITORIAL = "/home/fields/Fields_Orchestrator/scripts/backend_enrichment/generate_property_ai_analysis.py"
MAX_ATTEMPTS = 3
QUEUE = "property_build_requests"

# Suburb name lookups so a request only needs the suburb_key.
SUBURB_NAMES = {
    "robina": ("Robina", "4226"), "burleigh_waters": ("Burleigh Waters", "4220"),
    "varsity_lakes": ("Varsity Lakes", "4227"), "merrimac": ("Merrimac", "4226"),
    "mudgeeraba": ("Mudgeeraba", "4213"), "reedy_creek": ("Reedy Creek", "4227"),
    "worongary": ("Worongary", "4213"), "burleigh_heads": ("Burleigh Heads", "4220"),
    "palm_beach": ("Palm Beach", "4221"), "miami": ("Miami", "4220"),
}


def _load_scraper():
    spec = importlib.util.spec_from_file_location("curlffi_scraper", SCRAPER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _addr_key(text: str):
    """Same canonical (leading-number, street) key the scraper uses to match a
    listed address against a listing-URL slug."""
    t = (text or "").split(",")[0].lower().replace("-", " ").replace("/", " ")
    t = re.sub(r"\bunit\b|\bid:\d+\b", " ", t)
    lead = re.match(r"\s*(\d+)", t)
    street = re.sub(r"^[\s\d]+", "", t).strip()
    return (lead.group(1) if lead else "", street)


def _forsale_doc(gc, suburb_key: str, address: str):
    """The for_sale doc for this address, if it now exists (build success signal)."""
    coll = gc[suburb_key]
    key = _addr_key(address)
    for d in coll.find({"listing_status": "for_sale"},
                       {"address": 1, "complete_address": 1, "url_slug": 1}):
        if _addr_key(d.get("address") or d.get("complete_address") or "") == key:
            return d
    return None


def build_one(client, suburb_key: str, postcode: str, address: str) -> dict:
    """Scrape the specific listing + kick editorial. Returns {ok, slug, detail}."""
    gc = client["Gold_Coast"]
    name, default_pc = SUBURB_NAMES.get(suburb_key, (suburb_key.replace("_", " ").title(), postcode))
    postcode = postcode or default_pc

    # Already there? (e.g. nightly scrape beat us to it, or a duplicate request)
    existing = _forsale_doc(gc, suburb_key, address)
    if existing:
        return {"ok": True, "slug": existing.get("url_slug"), "detail": "already for_sale"}

    # 1) Discover the suburb's live listings, find THIS address's Domain URL.
    scr = _load_scraper()
    scraper = scr.CurlCffiSuburbScraper(name, postcode)
    scraper.discover()
    key = _addr_key(address)
    match_url = None
    for u in scraper.discovered_urls:
        slug = re.sub(r"-\d{7,12}$", "", u.rstrip("/").split("/")[-1]).replace(f"-{scraper.suburb_slug}", "")
        if _addr_key(slug) == key:
            match_url = u
            break
    if not match_url:
        # ZERO discovered URLs is an INFRASTRUCTURE failure, not a fact about the
        # address. A suburb we cover always has dozens of live listings, so an empty
        # discovery means the scrape itself failed (Bright Data key missing, Akamai
        # block, Domain layout change). Conflating the two is what let 11 consecutive
        # failures read as "these addresses just aren't listed" for a week.
        if not scraper.discovered_urls:
            return {"ok": False, "slug": None, "infra": True,
                    "detail": f"DISCOVERY FAILED for {name} — 0 live listings returned. "
                              f"The scrape is broken, not the address. Check "
                              f"BRIGHTDATA_API_KEY is exported and Domain is reachable."}
        return {"ok": False, "slug": None,
                "detail": f"address not found among {len(scraper.discovered_urls)} live listings "
                          f"(may be under offer / just withdrawn / different suburb)"}

    # 2) Detail-scrape + save → creates the for_sale doc.
    data = scraper.scrape_property(match_url, 1, 1)
    if not data:
        return {"ok": False, "slug": None, "detail": f"detail scrape failed for {match_url}"}
    scraper.save_to_mongodb(data)

    doc = _forsale_doc(gc, suburb_key, address)
    slug = (doc or {}).get("url_slug") or data.get("url_slug")
    if not doc:
        return {"ok": False, "slug": slug, "detail": "scrape saved but no for_sale doc resolved"}

    # 3) Kick editorial DETACHED (it takes 10-25 min — must not block the drainer;
    # the interim page already forwards to /property the moment this for_sale doc
    # exists, and nightly step 120 is the backstop if this detached run fails).
    editorial_note = "editorial launched (detached); nightly is backstop"
    try:
        env = dict(os.environ)
        env["USE_CLAUDE_MAX"] = "1"
        env.pop("ANTHROPIC_BACKEND", None)
        log = open(f"/home/fields/Fields_Orchestrator/logs/ondemand_editorial_{slug}.log", "ab")
        subprocess.Popen(
            [sys.executable, EDITORIAL, "--slug", slug, "--force"],
            cwd="/home/fields/Fields_Orchestrator", env=env,
            stdout=log, stderr=log, start_new_session=True)
    except Exception as e:
        editorial_note = f"editorial not launched ({type(e).__name__}); nightly will build"

    return {"ok": True, "slug": slug, "detail": f"listing scraped; {editorial_note}"}


def process_request(client, req) -> dict:
    sm = client["system_monitor"]
    coll = sm[QUEUE]
    _id = req["_id"]
    attempts = req.get("attempts", 0) + 1
    cosmos_retry(lambda: coll.update_one(
        {"_id": _id}, {"$set": {"status": "building", "started_at": datetime.datetime.utcnow(),
                                "attempts": attempts}}), f"build-start:{_id}")
    try:
        res = build_one(client, req["suburb_key"], req.get("postcode", ""), req["address"])
    except Exception as e:
        res = {"ok": False, "slug": None, "detail": f"{type(e).__name__}: {e}"}

    if res["ok"]:
        cosmos_retry(lambda: coll.update_one({"_id": _id}, {"$set": {
            "status": "done", "built_at": datetime.datetime.utcnow(),
            "result_slug": res["slug"], "detail": res["detail"], "error": None}}),
            f"build-done:{_id}")
        print(f"[build] DONE {req['address']} -> /property/{res['slug']} ({res['detail']})")
    else:
        terminal = attempts >= MAX_ATTEMPTS
        cosmos_retry(lambda: coll.update_one({"_id": _id}, {"$set": {
            "status": "failed" if terminal else "pending",
            "error": res["detail"], "detail": res["detail"]}}),
            f"build-fail:{_id}")
        print(f"[build] {'FAILED' if terminal else 'retry'} {req['address']}: {res['detail']}")
    return res


def drain(once: bool = False) -> dict:
    client = get_client()
    sm = client["system_monitor"]
    coll = sm[QUEUE]
    processed = 0
    infra_failures = []
    while True:
        req = coll.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "claimed", "claimed_at": datetime.datetime.utcnow()}},
            sort=[("requested_at", 1)])
        if not req:
            break
        res = process_request(client, req) or {}
        if res.get("infra"):
            infra_failures.append(f"{req.get('address')} ({req.get('suburb_key')})")
        processed += 1
        if once:
            break
    print(f"[build] drain complete — {processed} request(s) processed, "
          f"{len(infra_failures)} infrastructure failure(s)")
    return {"processed": processed, "infra_failures": infra_failures}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drain", action="store_true", help="Process the pending build queue (cron mode)")
    ap.add_argument("--once", action="store_true", help="With --drain: one request then exit")
    ap.add_argument("--address", help="Build a single address directly (manual)")
    ap.add_argument("--suburb", help="suburb_key for --address (e.g. burleigh_waters)")
    ap.add_argument("--postcode", default="", help="postcode for --address")
    args = ap.parse_args()

    if args.address:
        client = get_client()
        res = build_one(client, args.suburb, args.postcode, args.address)
        print(res)
        return 0 if res["ok"] else 1

    # Drain mode always heartbeats (Rule 7) so a stopped cron is visible.
    with job_run("listed_property_builder", cadence_hours=1,
                 title="On-Demand Listed-Property Builder") as beat:
        summary = drain(once=args.once)
        infra = summary["infra_failures"]
        beat.metrics = {"processed": summary["processed"], "infra_failures": len(infra)}
        if infra:
            # RAISE so the heartbeat records ERROR on the health board. Previously this
            # block set detail="queue drained" unconditionally, so 11 consecutive
            # discovery failures were reported as success for a week. A heartbeat that
            # cannot distinguish "did the work" from "ran to completion" is not
            # monitoring — it is a liveness check wearing Rule 7's clothes.
            raise RuntimeError(
                f"Listing discovery returned 0 URLs for {len(infra)} request(s) — the scrape "
                f"is broken, not the addresses: {', '.join(infra[:5])}"
                + (f" (+{len(infra) - 5} more)" if len(infra) > 5 else ""))
        beat.detail = f"queue drained — {summary['processed']} request(s), no discovery failures"
    return 0


if __name__ == "__main__":
    sys.exit(main())
