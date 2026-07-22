#!/usr/bin/env python3
"""
offmarket_intel_poller.py — fast, NO-LLM "intel" for the off-market swipe deck.

Consumes `system_monitor.offmarket_intel` requests written by the website's
`offmarket-intel.mjs` (status="pending"), computes the DETERMINISTIC scarcity +
competition numbers for the subject address by reusing the existing mini-site
resolvers (no Opus, no vision — Mongo-only, ~1-4s), and writes the result back
(status="done"). The deck polls the same endpoint and streams the numbers into
its "how rare your home is" card.

Pattern mirrors the other VM pollers (offmarket_order_processor.py). Runs as
systemd service `fields-offmarket-intel-poller`.
"""
import argparse
import sys
import time
import traceback
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")  # repo root -> scripts.*, shared.*

from shared.db import get_client  # noqa: E402
from scripts.property_reports.inline_features import derive_features_basic  # noqa: E402
from scripts.property_reports.scarcity_features import resolve_scarcity_features  # noqa: E402
from scripts.property_reports.competitor_matcher import resolve_competitor_map  # noqa: E402

# Gold_Coast suburb collections a slug might live in (mirrors db.server TARGET_SUBURBS).
TARGET_SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes", "burleigh_heads",
    "mudgeeraba", "reedy_creek", "merrimac", "worongary", "carrara",
]
POLL_SECONDS = 3
FRESH_DAYS = 14


def _now():
    return datetime.now(timezone.utc).isoformat()


def _find_subject(gc, suburb, slug):
    """Load the Gold_Coast doc by url_slug — try the given suburb first, then scan."""
    tried = set()
    order = ([suburb] if suburb else []) + TARGET_SUBURBS
    for s in order:
        if not s or s in tried:
            continue
        tried.add(s)
        try:
            d = gc[s].find_one({"url_slug": slug})
        except Exception:
            d = None
        if d:
            d.setdefault("suburb_key", s)
            return d, s
    return None, None


def compute_intel(gc, suburb, slug):
    """Return the deck-shaped intel dict (all deterministic, no LLM)."""
    subject, matched = _find_subject(gc, suburb, slug)
    if not subject:
        return None, "subject_not_found"

    # Scarcity — derives features.basic internally; None if no bed/bath/land/floor.
    try:
        scarcity = resolve_scarcity_features(subject, gc)
    except Exception:
        traceback.print_exc()
        scarcity = None

    # Price anchor: engine reconciled-range midpoint if the doc already carries
    # one, else None (matcher ranks on physical attributes; price guard off).
    rng = ((subject.get("valuation_data") or {}).get("confidence") or {}).get("range") or {}
    price_anchor = None
    try:
        if rng.get("low") and rng.get("high"):
            price_anchor = int((rng["low"] + rng["high"]) / 2)
    except Exception:
        price_anchor = None

    try:
        features_basic = derive_features_basic(subject)
    except Exception:
        features_basic = None

    try:
        comp = resolve_competitor_map(
            subject, gc, features_basic,
            price_anchor=price_anchor,
            active_listings_total=(scarcity or {}).get("active_listings_total"),
            geocode_missing=True,
        )
    except Exception:
        traceback.print_exc()
        comp = None

    funnel = ((comp or {}).get("ranked_comparison") or {}).get("funnel") or {}
    notable = []
    for f in (scarcity or {}).get("notable_features", []) or []:
        lbl = (f or {}).get("label") or (f or {}).get("value")
        if lbl:
            notable.append(str(lbl))

    result = {
        "scarcity": {
            "active_total": (scarcity or {}).get("active_listings_total"),
            "active_matching": (scarcity or {}).get("active_matching_full_stack"),
            "notable": notable[:5],
            "query": (scarcity or {}).get("active_matching_query"),
        },
        "competition": {
            "n_compete": funnel.get("close_tier"),
            "n_total": funnel.get("active_total"),
        },
        "matched_suburb": matched,
    }
    return result, None


def run_once(client):
    sysdb = client["system_monitor"]
    gc = client["Gold_Coast"]
    col = sysdb["offmarket_intel"]
    pending = list(col.find({"status": "pending"}).sort("requested_at", 1).limit(10))
    for doc in pending:
        slug = doc.get("slug") or doc.get("_id")
        suburb = doc.get("suburb") or ""
        try:
            result, err = compute_intel(gc, suburb, slug)
            if err:
                col.update_one({"_id": doc["_id"]},
                               {"$set": {"status": "error", "error": err, "computed_at": _now()}})
                print(f"[intel] {slug}: ERROR {err}")
            else:
                col.update_one({"_id": doc["_id"]},
                               {"$set": {"status": "done", "result": result, "computed_at": _now()},
                                "$unset": {"error": ""}})
                sc = result["scarcity"]; cp = result["competition"]
                print(f"[intel] {slug}: active_match={sc['active_matching']}/{sc['active_total']} "
                      f"compete={cp['n_compete']}/{cp['n_total']}")
        except Exception as e:
            traceback.print_exc()
            col.update_one({"_id": doc["_id"]},
                           {"$set": {"status": "error", "error": str(e)[:300], "computed_at": _now()}})
    return len(pending)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single pass then exit")
    ap.add_argument("--interval", type=int, default=POLL_SECONDS)
    ap.add_argument("--slug", help="compute a single slug ad-hoc (test) and print")
    ap.add_argument("--suburb", default="", help="suburb hint for --slug")
    args = ap.parse_args()

    client = get_client()

    if args.slug:
        result, err = compute_intel(client["Gold_Coast"], args.suburb, args.slug)
        print("ERR:", err) if err else __import__("json").dump(result, sys.stdout, indent=2, default=str)
        print()
        return

    if args.once:
        n = run_once(client)
        print(f"[intel] processed {n} pending")
        return

    print(f"[intel] poller started (interval={args.interval}s)")
    while True:
        try:
            run_once(client)
        except Exception:
            traceback.print_exc()
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
