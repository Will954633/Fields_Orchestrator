#!/usr/bin/env python3
"""
db_fields.py — look at what is ACTUALLY in the documents before claiming a
field does or does not exist.

    # what fields exist here at all?
    python3 scripts/db_fields.py Gold_Coast robina

    # anything about aerials?
    python3 scripts/db_fields.py Gold_Coast robina --grep aerial

    # is `aerial_image_url` real?  <-- run this BEFORE reporting any absence
    python3 scripts/db_fields.py Gold_Coast robina --check aerial_image_url

    # scope to live listings rather than the whole cadastral pile
    python3 scripts/db_fields.py Gold_Coast robina --grep image \\
        --query '{"listing_status": "for_sale"}'

    # across every collection in a database
    python3 scripts/db_fields.py Gold_Coast --all --grep aerial

WHY: on 2026-08-09 a query for `aerial_image_url` returned zero, and zero was
reported as "no aerials exist in the database". 14,531 documents held one, under
`satellite_analysis.satellite_image_url` and other names. The guessed label had
never existed. A zero result is only evidence about the NAME YOU GUESSED — never
about the data.

So `--check` refuses to answer "not found" on its own: whenever a path has zero
fill it prints every related path that DOES exist, in the same output, and exits
non-zero. The absence and its rebuttal cannot be separated.
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_client
from shared.doc_shape import DEFAULT_SAMPLE, near_misses, sample_shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSV = os.path.join(ROOT, "SCHEMA_PATHS.tsv")

# The vocabulary gap is the actual failure mode. `aerial_image_url` returned zero
# and so did `grep -i aerial SCHEMA_PATHS.tsv` — because this database calls that
# thing SATELLITE. The word in your head is not the word in the schema, so a
# literal search for your own word confirms your own wrong assumption.
SYNONYMS = [
    {"aerial", "satellite", "overhead", "birdseye", "drone", "nearmap", "sat"},
    {"image", "images", "img", "photo", "photos", "picture", "thumbnail", "media", "url"},
    {"floorplan", "floor_plan", "plan", "plans", "layout", "blueprint"},
    {"coord", "coords", "coordinate", "coordinates", "latitude", "longitude",
     "lat", "lng", "lon", "geo", "geocode", "georeference", "point", "location"},
    {"price", "prices", "value", "valuation", "amount", "cost", "sold", "sale"},
    {"address", "street", "suburb", "postcode", "state", "unit"},
    {"date", "time", "timestamp", "at", "when", "updated", "created", "scraped"},
    {"area", "sqm", "size", "land", "lot", "floor", "building"},
    {"bed", "beds", "bedroom", "bedrooms"},
    {"bath", "baths", "bathroom", "bathrooms"},
    {"car", "cars", "garage", "parking", "carspaces"},
    {"agent", "agency", "lister", "listing", "vendor"},
    {"desc", "description", "summary", "narrative", "text", "body", "content"},
    {"status", "state", "stage", "phase"},
]


def expand(term):
    """Term -> the vocabulary this database might actually use for it."""
    tokens = {t for t in term.lower().replace(".", "_").split("_") if len(t) > 2}
    tokens.add(term.lower())
    out = set(tokens)
    for group in SYNONYMS:
        if tokens & group:
            out |= group
    return out


def find_in_index(term, min_fill=0):
    """Search the whole-database path index with vocabulary expansion."""
    if not os.path.exists(TSV):
        print(f"{TSV} not found — run: python3 generate_schema_snapshot.py",
              file=sys.stderr)
        sys.exit(2)

    tokens = expand(term)
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(TSV))
    print(f"Searching SCHEMA_PATHS.tsv (generated {age.days}d "
          f"{age.seconds // 3600}h ago) for '{term}'")
    print(f"Vocabulary expanded to: {', '.join(sorted(tokens))}\n")

    exact, related = [], []
    with open(TSV) as f:
        next(f, None)
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 5:
                continue
            db, col, path, fill, types = parts
            low = path.lower()
            if min_fill:
                got, tot = (int(x) for x in fill.split("/"))
                if tot and 100 * got / tot < min_fill:
                    continue
            if term.lower() in low:
                exact.append((db, col, path, fill, types))
            elif any(t in low for t in tokens):
                related.append((db, col, path, fill, types))

    def dump(rows, cap=60):
        # Collapse the same path repeated across suburb collections.
        seen = {}
        for db, col, path, fill, types in rows:
            seen.setdefault((db, path, types), []).append((col, fill))
        for (db, path, types), cols in sorted(seen.items())[:cap]:
            where = cols[0][0] if len(cols) == 1 else f"{len(cols)} collections"
            fills = ", ".join(f"{c}:{fl}" for c, fl in cols[:3])
            print(f"  {db}.{path}")
            print(f"      {types:<14} {where:<16} {fills}"
                  + (" ..." if len(cols) > 3 else ""))
        if len(seen) > cap:
            print(f"  ... {len(seen) - cap} more")
        return len(seen)

    if exact:
        print(f"── Paths literally containing '{term}' ──")
        dump(exact)
        print()
    if related:
        print(f"── Paths in the same vocabulary (this is where the data usually is) ──")
        dump(related)
        print()
    if not exact and not related:
        print(f"  Nothing in the index relates to '{term}'.")
        print(f"  The index is a SAMPLE — a field on <1% of documents can be absent")
        print(f"  from it. Probe a specific collection live before concluding:")
        print(f"    python3 scripts/db_fields.py <DB> <COLLECTION> --grep {term}")
        return 1
    if not exact:
        print(f"  ⚠ No path is actually named '{term}'. It is not a field in this")
        print(f"    database — the data is under the names above, if at all.")
    return 0


def fmt(path, entry, n, width=62):
    pct = round(100 * entry["count"] / n) if n else 0
    types = "/".join(sorted(entry["types"]))
    return f"  {path:<{width}} {entry['count']:>5}/{n} ({pct:>3}%)  {types}"


def collect(client, db_name, collections, sample, query):
    """Merge shapes across one or more collections -> (paths, per_collection)."""
    merged = {}
    per_col = {}
    for col_name in collections:
        try:
            paths, n = sample_shape(client[db_name][col_name], sample=sample, query=query)
        except Exception as e:
            print(f"  ! {col_name}: {e}", file=sys.stderr)
            continue
        if not n:
            continue
        per_col[col_name] = (paths, n)
        for path, entry in paths.items():
            m = merged.setdefault(path, {"types": set(), "count": 0, "n": 0,
                                         "collections": set()})
            m["types"] |= entry["types"]
            m["count"] += entry["count"]
            m["n"] += n
            m["collections"].add(col_name)
    return merged, per_col


def main():
    ap = argparse.ArgumentParser(
        description="Show the key paths that actually exist in a MongoDB collection.")
    ap.add_argument("database", nargs="?")
    ap.add_argument("collection", nargs="?",
                    help="collection name; omit with --all to scan the database")
    ap.add_argument("--find", metavar="TERM",
                    help="search EVERY database via SCHEMA_PATHS.tsv, expanding "
                         "TERM into the vocabulary this schema actually uses "
                         "(aerial -> satellite, photo -> image, ...). Start here.")
    ap.add_argument("--all", action="store_true",
                    help="scan every collection in the database")
    ap.add_argument("--grep", metavar="TERM",
                    help="only paths whose name relates to TERM")
    ap.add_argument("--check", metavar="FIELD",
                    help="verify one exact path; on zero fill, print what does exist")
    ap.add_argument("--query", metavar="JSON",
                    help='scope the sample, e.g. \'{"listing_status": "for_sale"}\'')
    ap.add_argument("--sample", type=int, default=DEFAULT_SAMPLE,
                    help=f"documents to sample per collection (default {DEFAULT_SAMPLE})")
    ap.add_argument("--min-fill", type=int, default=0, metavar="PCT",
                    help="hide paths present on fewer than PCT%% of sampled docs")
    args = ap.parse_args()

    if args.find:
        sys.exit(find_in_index(args.find, min_fill=args.min_fill))

    if not args.database:
        ap.error("give a database (and collection), or --find TERM to search everything")
    if not args.collection and not args.all:
        ap.error("give a collection name, or --all to scan the whole database")

    query = json.loads(args.query) if args.query else None
    client = get_client()

    if args.all:
        collections = sorted(client[args.database].list_collection_names())
        print(f"Scanning {len(collections)} collections in `{args.database}` "
              f"({args.sample} docs each)...\n")
    else:
        collections = [args.collection]

    merged, per_col = collect(client, args.database, collections, args.sample, query)
    if not merged:
        print("No documents sampled — check the database/collection name and --query.")
        sys.exit(2)

    scope = f"`{args.database}`" + ("" if args.all else f".`{collections[0]}`")
    total_n = max(m["n"] for m in merged.values())
    if query:
        scope += f"  filtered by {json.dumps(query)}"

    # ---- --check: an absence must arrive with its own rebuttal ----------------
    if args.check:
        target = args.check
        entry = merged.get(target)
        print(f"Checking `{target}` in {scope}\n")
        if entry and entry["count"]:
            n = entry["n"]
            pct = round(100 * entry["count"] / n)
            print(f"  EXISTS — {entry['count']}/{n} sampled documents ({pct}%), "
                  f"type {'/'.join(sorted(entry['types']))}")
            if args.all:
                cols = sorted(entry["collections"])
                print(f"  in {len(cols)} collections: {', '.join(cols[:10])}"
                      + (" ..." if len(cols) > 10 else ""))
            sys.exit(0)

        related = near_misses(merged, target, limit=25)
        print(f"  `{target}` is not present on any of {total_n} sampled documents.\n")
        print("  ⚠ THIS IS A FACT ABOUT THE NAME, NOT ABOUT THE DATA.")
        if related:
            print(f"  {len(related)} related paths DO exist — the data you were "
                  f"looking for is probably one of these:\n")
            for path in related:
                print(fmt(path, merged[path], merged[path]["n"]))
            print("\n  Do not report this field as missing data. Report it as a "
                  "wrong field name\n  until you have checked the paths above.")
        else:
            print("  No related paths either. Widen the search before concluding:")
            print(f"    grep -i {target.split('_')[0]} SCHEMA_PATHS.tsv")
            print(f"    python3 scripts/db_fields.py {args.database} --all "
                  f"--grep {target.split('_')[0]}")
        sys.exit(1)

    # ---- listing / --grep ----------------------------------------------------
    paths = sorted(merged)
    if args.grep:
        paths = near_misses(merged, args.grep, limit=10_000)
    if args.min_fill:
        paths = [p for p in paths
                 if 100 * merged[p]["count"] / merged[p]["n"] >= args.min_fill]

    header = f"{scope} — {len(merged)} distinct key paths"
    if args.grep:
        header += f", {len(paths)} matching '{args.grep}'"
    print(header + "\n")

    if not paths:
        print(f"  Nothing matches '{args.grep}' in this collection.")
        print(f"  Before concluding the data is absent, search everywhere:")
        print(f"    grep -i {args.grep} SCHEMA_PATHS.tsv")
        print(f"    python3 scripts/db_fields.py {args.database} --all --grep {args.grep}")
        sys.exit(1)

    for path in paths:
        entry = merged[path]
        line = fmt(path, entry, entry["n"])
        if args.all:
            line += f"  [{len(entry['collections'])} col]"
        print(line)


if __name__ == "__main__":
    main()
