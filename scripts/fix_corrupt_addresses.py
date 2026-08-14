#!/usr/bin/env python3
"""fix_corrupt_addresses.py — strip junk tokens from property addresses.

WHAT WAS WRONG
--------------
160 property records carried a placeholder or an id inside the address itself:

    29 THE CRESTWAY XXX ROBINA QLD 4226
    Id 21158261 25 Lake Orr Drive, Robina, QLD 4226

`The Gardenway`, `The Links` and `The Crestway` are real Robina streets; the trailing
`XXX` is junk appended at ingest. These render publicly — `/off-market/<slug>` and
`/property/<slug>` both return 200 with "The Crestway Xxx, Robina" in the page title and
body — on a site positioned on data accuracy.

Found while characterising why 3,526 dwellings matched no onthehouse sitemap URL: the
"street does not exist in their sitemap" bucket turned out to be mostly OUR corrupt
addresses, not their missing coverage.

SCOPE — DELIBERATELY TEXT ONLY
------------------------------
⚠ This rewrites the address FIELDS only. It does NOT touch `url_slug`.
The slugs (`29-the-crestway-xxx-robina`) are already indexed; renaming them would break
160 live URLs and require 301s. That is a separate, outward-facing decision.

⚠ ONLY TWO PATTERNS, ANCHORED. A general "clean the address" regex is how good addresses
get mangled. `XXX` is removed only as a whole word, and the id prefix only at the start.
Anything else is left alone and reported.

Every change keeps the original under `address_fix` so it is auditable and reversible.

DRY RUN BY DEFAULT.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from pymongo import UpdateOne                    # noqa: E402
from shared.db import get_client                 # noqa: E402

FIELDS = ["address", "complete_address", "street_address"]

# ⚠ THIS IS NOT A THREE-SUBURB PROBLEM. It was found in the target suburbs (160 docs) but
# the same ingest junk sits in 4,269 documents across 35 Gold Coast collections —
# `The Esplanade Xxx`, `The Boulevarde Xxx`, `The Concourse Xxx`. `address_search_index` is
# coast-wide and feeds address lookup, so repairing only the three target suburbs would
# leave the search index clean and the property records dirty. Every collection is scanned.
NOT_PROPERTY = {"address_search_index"}

# ⚠ THE ADDRESS IS DENORMALISED INTO FOUR PLACES. Fixing only the property document left
# every public page unchanged, because the deck renders from `offmarket_discovery`, not
# from `Gold_Coast`. Found by searching for the literal string across all databases rather
# than assuming the page read the field we had just fixed.
DENORM = [
    ("Gold_Coast", "address_search_index"),        # incl. street_type == "XXX"
    ("system_monitor", "offmarket_discovery"),     # the public /off-market/<slug> deck
    ("system_monitor", "listing_status_cache"),
]

# ⚠ NEVER rewrite a slug or an id. Those are already indexed; renaming them breaks live
# URLs and needs 301s. `listing_status_cache._id` IS the slug, and is immutable anyway.
SKIP_KEYS = re.compile(r"(^_id$|slug|url|href|link|path)", re.I)

# `XXX` only as a standalone word; the id only as a leading prefix.
RE_XXX = re.compile(r"\s*\bX{3,}\b", re.I)
RE_IDPFX = re.compile(r"^\s*Id\s+\d+\s+", re.I)


def clean(value):
    """(cleaned, reason) or (None, None) when nothing to do."""
    if not isinstance(value, str) or not value.strip():
        return None, None
    out, why = value, []
    if RE_IDPFX.search(out):
        out = RE_IDPFX.sub("", out)
        why.append("id_prefix")
    if RE_XXX.search(out):
        out = RE_XXX.sub("", out)
        why.append("xxx")
    out = re.sub(r"\s{2,}", " ", out).strip(" ,")
    if not why or out == value:
        return None, None
    # A clean-up that empties the address, or strips it below a street number plus a
    # name, is a bug in the pattern — leave the record alone and say so.
    if len(out) < 6 or not re.search(r"[A-Za-z]{3}", out):
        return None, "REFUSED_too_short"
    return out, "+".join(why)


def scrub(value):
    """Junk removed from one string. Returns (new, changed).

    Unlike `clean()` this allows an EMPTY result, because component fields legitimately
    become empty: `address_search_index.street_type` literally held "XXX", the parser
    having read the junk as the street type. Emptying it is correct — guessing a real
    street type for `The Crestway` would be inventing data.
    """
    if not isinstance(value, str) or not value.strip():
        return value, False
    out = RE_IDPFX.sub("", value)
    out = RE_XXX.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,")
    if out == value:
        return value, False
    # Refuse anything that loses real content: only a purely-junk field may end up empty.
    if len(out) < 3 and not re.fullmatch(r"[\sX]*", value, re.I):
        return value, False
    return out, True


def walk_scrub(node, key=""):
    """Recursively scrub strings, skipping any slug/url/id-bearing key."""
    changed = False
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if SKIP_KEYS.search(k):
                continue
            nv, ch = walk_scrub(v, k)
            if ch:
                node[k] = nv
                changed = True
        return node, changed
    if isinstance(node, list):
        for i, v in enumerate(node):
            nv, ch = walk_scrub(v, key)
            if ch:
                node[i] = nv
                changed = True
        return node, changed
    if isinstance(node, str):
        return scrub(node)
    return node, changed


def fix_denorm(cl, apply_):
    """Repair the denormalised copies the public pages actually render from."""
    stats = Counter()
    probe = [{f: {"$regex": r"X{3,}|^\s*Id\s+\d+\s", "$options": "i"}}
             for f in ("address", "complete_address", "street_address",
                       "address_short", "address_display", "street_type")]
    for dbname, coll in DENORM:
        c = cl[dbname][coll]
        ops = []
        for d in c.find({"$or": probe}):
            doc = {k: v for k, v in d.items() if k != "_id"}
            new, changed = walk_scrub(doc)
            if not changed:
                continue
            new["address_fix"] = {
                "reason": "stripped XXX placeholder / Id prefix (denormalised copy)",
                "fixed_at": dt.datetime.utcnow().isoformat(),
                "script": "fix_corrupt_addresses",
                "note": "slug / _id deliberately UNCHANGED — already indexed",
            }
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": new}))
        stats[f"{dbname}.{coll}"] = len(ops)
        if ops and apply_:
            c.bulk_write(ops, ordered=False)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--denorm-only", action="store_true",
                    help="skip the property documents; repair only the denormalised copies")
    args = ap.parse_args()

    cl = get_client()
    gc = cl["Gold_Coast"]
    stats = Counter()
    shown = 0

    probe = {"$or": [{f: {"$regex": r"\bX{3,}\b|^\s*Id\s+\d+\s", "$options": "i"}}
                     for f in FIELDS]}
    subs = [] if args.denorm_only else [c for c in sorted(gc.list_collection_names())
                                        if c not in NOT_PROPERTY]
    for sub in subs:
        ops = []
        proj = {f: 1 for f in FIELDS}
        proj["url_slug"] = 1
        try:
            cursor = gc[sub].find(probe, proj)
        except Exception:                                    # noqa: BLE001
            continue
        for d in cursor:
            setter, changes = {}, []
            refused = False
            for f in FIELDS:
                new, why = clean(d.get(f))
                if why == "REFUSED_too_short":
                    refused = True
                    continue
                if new is None:
                    continue
                setter[f] = new
                changes.append((f, d[f], new, why))
            if refused:
                stats["refused"] += 1
            if not setter:
                continue
            stats["docs_changed"] += 1
            for _, _, _, why in changes:
                stats[f"field_{why}"] += 1
            setter["address_fix"] = {
                "original": {f: d.get(f) for f in FIELDS if f in setter},
                "reason": "stripped XXX placeholder / Id prefix from ingested address",
                "fixed_at": dt.datetime.utcnow().isoformat(),
                "script": "fix_corrupt_addresses",
                "note": "url_slug deliberately UNCHANGED — already indexed",
            }
            if shown < 12:
                shown += 1
                print(f"  {sub}/{d.get('url_slug')}")
                for f, old, new, why in changes:
                    print(f"      {f:17} {old!r}\n      {'':17} -> {new!r}   [{why}]")
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": setter}))
        if ops and args.apply:
            gc[sub].bulk_write(ops, ordered=False)
            stats[f"written_{sub}"] += len(ops)

    dn = fix_denorm(cl, args.apply)
    stats.update({f"denorm_{k}": v for k, v in dn.items()})

    print()
    for k in sorted(stats):
        print(f"  {k:44} {stats[k]:>5,}")
    if not args.apply:
        print("\n  DRY RUN — nothing written. Re-run with --apply.")
        return 0

    if args.denorm_only:
        print(f"\n  wrote {sum(dn.values()):,} denormalised documents")
        return 0

    # Assert an outcome rather than merely not throwing.
    if stats["docs_changed"] == 0:
        print("\n  nothing matched — either already fixed, or the patterns no longer match")
        return 1
    written = sum(v for k, v in stats.items() if k.startswith("written_"))
    if written != stats["docs_changed"]:
        raise RuntimeError(f"identified {stats['docs_changed']} but wrote {written}")
    print(f"\n  wrote {written:,} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
