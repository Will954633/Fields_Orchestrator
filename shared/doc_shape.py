#!/usr/bin/env python3
"""
doc_shape.py — describe what is ACTUALLY in a MongoDB collection.

Single source of truth for "what fields exist here", used by both
`generate_schema_snapshot.py` (daily inventory) and `scripts/db_fields.py`
(interactive probe). Never reimplement this walk — if the two ever disagree,
a field claim can be true in one and false in the other.

Why it exists: on 2026-08-09 a query for `aerial_image_url` returned zero and
was reported as "no aerials exist". 14,531 documents had one, under a different
name. SCHEMA_SNAPSHOT.md could not have corrected that — it sampled the FIRST
5 documents of each collection, so for `Gold_Coast.robina` (12,092 docs, mostly
cadastral stubs) it listed 75 of the 230 top-level keys live listings carry,
and the omission was biased toward exactly the enrichment fields being asked
about. See logs/fix-history/2026-08-09.md [SCHEMA-SNAPSHOT-FIRST-5-BLIND].

Two properties make a negative result falsifiable:
  1. every key path is walked, nested and through arrays, not just top level;
  2. every path carries a FILL COUNT, so "listed" and "present on 1 of 400
     documents" are distinguishable.
"""

from collections import defaultdict

MAX_DEPTH = 6
# A dict with more keys than this is treated as a map keyed by data
# (e.g. {address: {...}}), not as a record with named fields. Recursing it
# would emit thousands of junk paths and bury the real schema.
DYNAMIC_KEY_THRESHOLD = 25
# Hard ceiling per collection so one pathological document cannot produce an
# unbounded path list.
MAX_PATHS = 4000

DEFAULT_SAMPLE = 400


def type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        if not value:
            return "array[]"
        return f"array[{type_name(value[0])}]"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def walk(doc, prefix="", depth=0, out=None):
    """Collect every key path in one document as {path: type_string}.

    Arrays of objects recurse under a `field[]` path so that
    `transactions[].price` is discoverable, not hidden behind `array[object]`.
    """
    if out is None:
        out = {}
    if depth > MAX_DEPTH or len(out) >= MAX_PATHS:
        return out

    if isinstance(doc, dict):
        keys = list(doc.keys())
        if depth > 0 and len(keys) > DYNAMIC_KEY_THRESHOLD:
            # Data-keyed map: record its shape once via a representative value.
            out[f"{prefix}.<dynamic>"] = f"object ({len(keys)} data keys)"
            walk(doc[keys[0]], f"{prefix}.<dynamic>", depth + 1, out)
            return out
        for k, v in doc.items():
            path = f"{prefix}.{k}" if prefix else k
            out[path] = type_name(v)
            if isinstance(v, dict):
                walk(v, path, depth + 1, out)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                walk(v[0], f"{path}[]", depth + 1, out)
    return out


def sample_shape(collection, sample=DEFAULT_SAMPLE, query=None):
    """Return (paths, sampled_count).

    paths: {path: {"types": set[str], "count": int}} where count is the number
    of sampled documents containing that path.

    Uses `$sample` for a RANDOM draw rather than `.limit()`. This is the whole
    point: `.limit(n)` returns the n oldest documents, which in a mixed
    collection is one document shape and tells you nothing about the others.
    """
    paths = defaultdict(lambda: {"types": set(), "count": 0})
    n = 0

    if query:
        cursor = collection.aggregate(
            [{"$match": query}, {"$sample": {"size": sample}}], allowDiskUse=True
        )
    else:
        try:
            total = collection.estimated_document_count()
        except Exception:
            total = sample + 1
        if total <= sample:
            cursor = collection.find({})
        else:
            cursor = collection.aggregate([{"$sample": {"size": sample}}])

    for doc in cursor:
        n += 1
        for path, tname in walk(doc).items():
            entry = paths[path]
            entry["types"].add(tname)
            entry["count"] += 1

    return dict(paths), n


def near_misses(paths, term, limit=25):
    """Key paths whose name relates to `term`.

    This is the rebuttal machinery. A query that returns zero must not be able
    to look like an answer, so every zero-result path in the callers runs this
    and prints what DOES exist alongside the nothing that was found.
    """
    t = term.lower().strip()
    if not t:
        return []
    # Split a guessed name into parts so `aerial_image_url` still matches
    # `satellite_analysis.aerial_path` on "aerial" and `domain_hero_image_url`
    # on "image".
    parts = [p for p in t.replace(".", "_").split("_") if len(p) > 2]
    scored = []
    for path in paths:
        low = path.lower()
        if t in low:
            scored.append((100, path))
            continue
        hits = sum(1 for p in parts if p in low)
        if hits:
            scored.append((hits, path))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, p in scored[:limit]]
