#!/usr/bin/env python3
"""
generate_schema_snapshot.py
Inventories every MongoDB collection and writes two artifacts:

  SCHEMA_SNAPSHOT.md  — readable orientation: top-level fields + fill counts.
  SCHEMA_PATHS.tsv    — the complete, greppable path index (all depths).

Run daily via cron (03:00 AEST).

WHY THE REWRITE (2026-08-09): the previous version sampled each collection with
`collection.find({}).limit(5)` — the five OLDEST documents, not a random draw —
and walked only the top level, capping nested objects at 10 subkeys. In a mixed
collection like `Gold_Coast.robina` (12,092 docs: ~40K cadastral stubs plus a
few hundred enriched listings) the first five documents are all one shape, so
the file listed 75 fields where live listings carry 233 top-level keys and 2,523
total paths. The omission was biased toward exactly the enrichment fields people
ask about. A field could be absent from this file and present on thousands of
documents, which is how "no aerials exist" got reported for a database holding
14,531 of them. See logs/fix-history/2026-08-09.md.

The fix is `shared/doc_shape.py`: random `$sample`, full recursion through
nested objects and arrays, and a FILL COUNT on every path so "listed" and
"present on 1 of 300 documents" are distinguishable.
"""

import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pymongo import MongoClient

from shared.doc_shape import sample_shape, type_name
from shared.env import load_env
from scripts.job_status import job_run

load_env()

CONN = os.environ.get("COSMOS_CONNECTION_STRING")
ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_MD = os.path.join(ROOT, "SCHEMA_SNAPSHOT.md")
OUTPUT_TSV = os.path.join(ROOT, "SCHEMA_PATHS.tsv")

SAMPLE_SIZE = 300

TARGET_DBS = [
    "Gold_Coast_Currently_For_Sale",
    "Gold_Coast_Recently_Sold",
    "Gold_Coast",
    "Target_Market_Sold_Last_12_Months",
    "property_data",
    "system_monitor",
]

SUBURB_KEYWORDS = [
    "burleigh", "robina", "varsity", "coolangatta", "carrara", "merrimac",
    "mudgeeraba", "reedy", "worongary", "palm_beach", "miami", "mermaid",
]

HEADER = """# Database Schema Snapshot

**Generated:** {now}
**Source:** {host}
**Script:** `generate_schema_snapshot.py` (daily via cron, 03:00 AEST)
**Sample:** random `$sample` of up to {sample} documents per collection

> ## Claude: this file is ORIENTATION, not the authority.
>
> It lists **top-level fields only**, with a fill count (`n/N` = documents in the
> sample carrying that field). Nested paths are NOT here — they are in
> `SCHEMA_PATHS.tsv`, one path per line, all depths, every collection:
>
> ```bash
> grep -i aerial SCHEMA_PATHS.tsv          # does anything about X exist, anywhere?
> ```
>
> **A query returning zero is not evidence a field is absent.** Before writing or
> reporting any negative result, probe the live documents:
>
> ```bash
> python3 scripts/db_fields.py Gold_Coast robina --grep aerial
> python3 scripts/db_fields.py Gold_Coast robina --check aerial_image_url
> ```
>
> `--check` prints the fill count for the exact name AND every related path that
> does exist, so a guessed field name cannot silently read as "no such data".

---

"""


def build(client, tsv_rows, md_lines, beat_counts):
    for db_name in TARGET_DBS:
        db = client[db_name]
        try:
            all_cols = db.list_collection_names()
        except Exception as e:
            md_lines.append(f"## {db_name}\n\n_Error listing collections: {e}_\n\n---\n")
            continue
        if not all_cols:
            continue

        md_lines.append(f"## Database: `{db_name}`\n")
        utility = [c for c in all_cols if not any(s in c for s in SUBURB_KEYWORDS)]
        suburb = [c for c in all_cols if c not in utility]

        for col_name in sorted(utility) + sorted(suburb):
            col = db[col_name]
            try:
                count = col.estimated_document_count()
            except Exception:
                count = "?"

            md_lines.append(f"### `{col_name}` ({count} documents)\n")
            if count == 0:
                md_lines.append("_Empty collection._\n")
                continue

            try:
                paths, n = sample_shape(col, sample=SAMPLE_SIZE)
            except Exception as e:
                md_lines.append(f"_Error sampling: {e}_\n")
                continue
            if not paths:
                md_lines.append("_No documents sampled._\n")
                continue

            beat_counts["collections"] += 1
            beat_counts["paths"] += len(paths)

            # Full inventory -> TSV (the searchable artifact).
            for path in sorted(paths):
                e = paths[path]
                tsv_rows.append(
                    f"{db_name}\t{col_name}\t{path}\t{e['count']}/{n}\t"
                    f"{'/'.join(sorted(e['types']))}"
                )

            # Top level only -> markdown (the readable artifact).
            top = {p: e for p, e in paths.items() if "." not in p and "[]" not in p}
            deeper = len(paths) - len(top)
            md_lines.append(f"_Sampled {n} documents at random. "
                            f"{len(top)} top-level fields, {deeper} nested paths "
                            f"(nested in `SCHEMA_PATHS.tsv`)._\n")
            md_lines.append("| Field | Fill | Type(s) |")
            md_lines.append("|-------|------|---------|")
            for path in sorted(top):
                e = top[path]
                pct = round(100 * e["count"] / n) if n else 0
                types = "/".join(sorted(e["types"]))
                md_lines.append(f"| `{path}` | {e['count']}/{n} ({pct}%) | {types} |")
            md_lines.append("")

        md_lines.append("---\n")


def main():
    if not CONN:
        print("ERROR: COSMOS_CONNECTION_STRING not set", file=sys.stderr)
        sys.exit(1)

    # 7b: a run that documents nothing, or far less than last time, is a
    # FAILURE — not a quiet success. The whole point of this file is that its
    # blind spots are invisible from its own output, so the run must assert
    # its coverage rather than merely finish.
    prev_rows = 0
    if os.path.exists(OUTPUT_TSV):
        with open(OUTPUT_TSV) as f:
            prev_rows = sum(1 for _ in f) - 1  # minus header

    with job_run("schema_snapshot", cadence_hours=24,
                 title="DB Schema Snapshot + Path Index") as beat:
        client = MongoClient(CONN, serverSelectionTimeoutMS=10000)
        host = CONN.split("@")[-1].split("/")[0]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        md_lines = [HEADER.format(now=now, host=host, sample=SAMPLE_SIZE)]
        tsv_rows = []
        counts = {"collections": 0, "paths": 0}
        start = time.time()

        build(client, tsv_rows, md_lines, counts)

        beat.metrics = {
            "collections": counts["collections"],
            "paths": counts["paths"],
            "prev_paths": prev_rows,
            "sample_size": SAMPLE_SIZE,
        }

        if counts["collections"] == 0:
            raise RuntimeError(
                "documented 0 collections — the connection or DB list is broken, "
                "not empty; refusing to overwrite the existing snapshot")

        if prev_rows and counts["paths"] < prev_rows * 0.6:
            raise RuntimeError(
                f"path coverage collapsed: {counts['paths']} paths this run vs "
                f"{prev_rows} last run (<60%). Sampling is degraded — refusing "
                f"to overwrite a good snapshot with a blind one")

        with open(OUTPUT_MD, "w") as f:
            f.write("\n".join(md_lines))
        with open(OUTPUT_TSV, "w") as f:
            f.write("database\tcollection\tpath\tfill\ttypes\n")
            f.write("\n".join(tsv_rows) + "\n")

        client.close()
        beat.detail = (f"{counts['collections']} collections, "
                       f"{counts['paths']} paths in {time.time() - start:.0f}s")
        print(f"Wrote {OUTPUT_MD}")
        print(f"Wrote {OUTPUT_TSV}  ({counts['paths']} paths, "
              f"{counts['collections']} collections)")


if __name__ == "__main__":
    main()
