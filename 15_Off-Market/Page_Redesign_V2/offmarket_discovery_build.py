#!/usr/bin/env python3
"""
offmarket_discovery_build.py — build the render-ready Discovery JSON for a house
and upsert it to system_monitor.offmarket_discovery (read by the React deck).

  python3 offmarket_discovery_build.py --slug 8-corina-close-robina
  python3 offmarket_discovery_build.py --all-bundles --no-rebuild   # seed the test set
  python3 offmarket_discovery_build.py --slug X --print --no-write

Pipeline per house:  fact_bundle.build() -> bundles/<slug>.json  (the expensive,
deterministic harvest) -> emit_json() -> typed card JSON -> Cosmos upsert.
Reuses the whole engine; no LLM. A source_hash lets the nightly --delta skip
unchanged docs. Wrap the nightly batch in job_run (CLAUDE.md Rule 7).
"""
import sys
import json
import time
import hashlib
import argparse
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
# The matrix intro's word field lives in the V3 tree; see _write_intro_tokens().
sys.path.insert(0, str(HERE.parent / "Page_Redesign_V3" / "intro"))

import fact_bundle
import emit_json as EJ

COLLECTION = "offmarket_discovery"


def _mongo():
    from src.mongo_client_factory import get_mongo_client
    return get_mongo_client()["system_monitor"][COLLECTION]


def _hash(doc):
    payload = json.dumps({"cards": doc["cards"], "lead_angle": doc["lead_angle"]},
                         sort_keys=True, ensure_ascii=False)
    return "sha1:" + hashlib.sha1(payload.encode()).hexdigest()


def build_one(slug, suburb=None, rebuild=True):
    """Returns the discovery doc (with metadata), or None if it can't be built."""
    if rebuild:
        bundle = fact_bundle.build(slug, suburb)
        (fact_bundle.BUNDLE_DIR / f"{slug}.json").write_text(
            json.dumps(bundle, indent=2, default=str))
    doc = EJ.emit_json(slug)
    doc["source_hash"] = _hash(doc)
    doc["generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    return doc


def _write_intro_tokens(slug, force=False):
    """Give the deck its matrix-intro word field. Returns True if written.

    DeckV3 skips the intro entirely when `intro_tokens` is absent (no tokens
    would mean raining someone else's streets), so a doc without them ships a
    deck that opens cold on "We found your home." Until 2026-08-05 the ONLY
    producer was Page_Redesign_V3/intro/backfill_intro_tokens.py, run by hand —
    the nightly wrote them nowhere. That was invisible because upsert() $sets
    named fields only, so rebuilds of existing docs preserve whatever the
    backfill wrote; only genuinely NEW homes lost the intro, and there were none
    until the sale-history filter was relaxed. Building them here closes that.

    Called AFTER the upsert on purpose: intro_tokens.build() reads the deck doc
    back out of Mongo for the home's suburb/coords, so it needs the doc to exist.

    Skipped when tokens are already present — they depend on the street grid, not
    the deck content, so recomputing 14k of them nightly is ~0.8s/home of waste.
    Pass force=True to rewrite.

    Never raises: the intro is a flourish, the deck is the point. Note SystemExit
    is caught explicitly — intro_tokens.build() raises it for a missing doc, and
    the nightly's per-home `except Exception` would NOT catch that, so one bad
    home would otherwise abort the entire run. KeyboardInterrupt still propagates.
    """
    coll = _mongo()
    if not force:
        cur = coll.find_one({"slug": slug}, {"intro_tokens": 1})
        if cur and cur.get("intro_tokens"):
            return False
    try:
        import intro_tokens
        tok = intro_tokens.build(slug)
        if not tok:
            return False
        from src.mongo_client_factory import cosmos_retry
        cosmos_retry(lambda: coll.update_one({"slug": slug},
                                             {"$set": {"intro_tokens": tok}}))
        return True
    except (Exception, SystemExit) as exc:
        # Deliberately not re-raised: a deck with no intro is still a good page.
        print(f"  ! intro_tokens {slug}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def upsert(doc, intro=True):
    coll = _mongo()
    from src.mongo_client_factory import cosmos_retry
    cosmos_retry(lambda: coll.update_one({"slug": doc["slug"]},
                                         {"$set": doc}, upsert=True))
    if intro:
        _write_intro_tokens(doc["slug"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug")
    g.add_argument("--all-bundles", action="store_true",
                   help="build every slug that already has a bundle (the test set)")
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--no-rebuild", action="store_true",
                    help="emit from the existing bundle (skip the fact_bundle harvest)")
    ap.add_argument("--no-write", action="store_true", help="don't upsert to Cosmos")
    ap.add_argument("--delta", action="store_true",
                    help="skip upsert when source_hash is unchanged")
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()

    slugs = ([p.stem for p in sorted(fact_bundle.BUNDLE_DIR.glob("*.json"))]
             if args.all_bundles else [args.slug])

    coll = None if args.no_write else _mongo()
    built = skipped = failed = 0
    for slug in slugs:
        try:
            doc = build_one(slug, args.suburb, rebuild=not args.no_rebuild)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ✗ {slug}: {e}", file=sys.stderr)
            failed += 1
            continue
        if args.print:
            print(json.dumps(doc, indent=2, ensure_ascii=False))
        if not args.no_write:
            if args.delta:
                cur = coll.find_one({"slug": slug}, {"source_hash": 1})
                if cur and cur.get("source_hash") == doc["source_hash"]:
                    skipped += 1
                    print(f"  = {slug} (unchanged)", file=sys.stderr)
                    continue
            upsert(doc)
        built += 1
        print(f"  ✓ {slug:44} {len(doc['cards'])} cards · lead={doc['lead_angle']}", file=sys.stderr)
    print(f"\nbuilt={built} skipped={skipped} failed={failed}", file=sys.stderr)


if __name__ == "__main__":
    main()
