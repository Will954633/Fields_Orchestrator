#!/usr/bin/env python3
"""Emit the 57 downturn-study KB docs (saved today) as an ISOLATED Brain-1 corpus.

Why isolated and not the normal kb_ingest public pipeline: that pipeline re-keys
every unit by global sorted filepath and the annotator tracks done-ness by batch
FILENAME, so inserting new financial/ docs shifts ids and would either skip the
new papers (they fall in already-"done" low batches) or force a full re-annotation
of the entire book corpus. This corpus gets its own namespace (d#####), its own
build dir, its own annotations file added to BRAIN1_SOURCES — exactly the pattern
used for the YouTube and podcast corpora.

Batch format is byte-identical to what brain3_annotate.parse_batch() expects:
    ===== UNIT d00001 | LIB: downturn:study =====
    HEADER: <filename> | <desc>
    TEXT: <content>
"""
import os, glob, json

KB = "/home/fields/knowledge-base/financial"
BASE = "/home/fields/brain1_downturn"
BDIR = f"{BASE}/batches_downturn"
LIB = "downturn:study"
DATE_TAG = "_20260905_"   # only the docs saved in this session

os.makedirs(BDIR, exist_ok=True)
for old in glob.glob(f"{BDIR}/b_*.txt"):
    os.remove(old)

files = sorted(f for f in glob.glob(f"{KB}/*.json") if DATE_TAG in os.path.basename(f))
units, manifest, uid = [], {}, 1
for f in files:
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    m = d.get("metadata", {})
    fname = os.path.basename(str(m.get("original_file", "") or m.get("filename", "") or f))
    for c in d.get("chunks", []):
        content = " ".join(str(c.get("content", "")).split()[:1200]).strip()
        if len(content) < 40:
            continue
        u = f"d{uid:05d}"; uid += 1
        desc = " ".join(str(c.get("description", "")).split())[:140]
        units.append({"unit_id": u, "header": f"{fname} | {desc}", "text": content})
        manifest[u] = {"file": f, "chunk_id": c.get("chunk_id"),
                       "lib": LIB, "filename": fname, "date": ""}

for i in range(0, len(units), 10):
    with open(f"{BDIR}/b_{i//10:04d}.txt", "w", encoding="utf-8") as fh:
        for u in units[i:i + 10]:
            fh.write(f"===== UNIT {u['unit_id']} | LIB: {LIB} =====\n")
            fh.write(f"HEADER: {u['header']}\nTEXT: {u['text']}\n\n")

json.dump(manifest, open(f"{BASE}/units_manifest.json", "w"), indent=0)
print(f"emitted {len(units)} units from {len(files)} docs -> {(len(units)+9)//10} batches in {BDIR}")
