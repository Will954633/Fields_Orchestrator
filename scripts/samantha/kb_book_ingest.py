#!/usr/bin/env python3
"""
Raw book .txt -> Brain 1 units.

The gap this fills
------------------
`kb_ingest.py` only reads `knowledge-base/**/*.json` files that already carry a
`chunks` array. Those JSONs were produced by a chunker that ran on a Mac
(`/Users/projects/Documents/Kindle_Scraper`) which is not on this VM. So a book
that exists only as a raw `.txt` is **invisible to every ingest path** — it sits
in the knowledge base looking present and never reaches a brain.

Audited 2026-08-09: 8 of 18 books in `knowledge-base/book/` were in that state,
~4.1 MB of text, including Sabri Suby's *Sell Like Crazy* — whose absence
silently skewed a give-vs-withhold analysis, because the opposing book
(*The Full Fee Agent*) was present in full at 102 units.

Why a separate namespace instead of re-running kb_ingest
--------------------------------------------------------
`kb_ingest.emit_batches()` **wipes `batches_public/` and renumbers every unit
from `k00000`**. Adding books that way would invalidate every `k#####` citation
in every brief ever written, and force a full re-annotation of the 3,047-unit
public pool. So these books get their own base, their own annotations file and
ids from `K_ID_BASE` (90000), and are merged as an additional graph source —
exactly the pattern the YouTube feed uses.

Usage
-----
    python3 scripts/samantha/kb_book_ingest.py --audit          # what is missing, change nothing
    python3 scripts/samantha/kb_book_ingest.py --chunk          # write Brain 1 batch files
    python3 scripts/samantha/brain1_annotate.py --base /home/fields/brain1_books --workers 8

Then add `/home/fields/brain1_books/annotations.jsonl` to BRAIN1_SOURCES in
`brain_drive_nightly.py` — a corpus merged once but absent from the nightly
rebuild's source list is deleted the next night. See fix-history
[BRAIN1-NIGHTLY-REBUILD-DROPS-SOURCES].
"""

import argparse
import glob
import json
import os
import re
import sys

BOOK_DIR = "/home/fields/knowledge-base/book"
BASE = "/home/fields/brain1_books"
BATCH_DIR = f"{BASE}/batches"
MANIFEST = f"{BASE}/units_manifest.json"

K_ID_BASE = 90_000     # highest live k id is 3046; 90000 cannot collide
WORDS_PER_CHUNK = 1200  # matches kb_ingest.emit_batches' 1200-word truncation
UNITS_PER_BATCH = 10
MIN_TXT_BYTES = 20_000  # below this a "book" is a failed scrape, not a book

# Same-book duplicates. Keeping both would silently double a book's weight in
# every retrieval, which looks like corroboration and is not.
SKIP_EXACT = {
    # 3.5 KB stub of Parker; the full 855 KB scan of the same book is also present
    "B09D777223_Principles and Practice of Property Valuation in Australia_Parker, David.txt",
    # same ASIN as the 695 KB scrape below, shorter capture
    "B0D7DZWQL8_Scaling Up (Revised 2022) How a Few Companies Make It...and Why the Rest Don't (Rockefeller Habits 2.0)_Harnish, Verne.txt",
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())[:40]


def corpus_docs():
    """Docs already represented in the Brain 1 public pool, by normalised name."""
    out = {}
    p = "/home/fields/brain3_build/annotations_public.jsonl"
    if not os.path.exists(p):
        return out
    for line in open(p, encoding="utf-8"):
        try:
            prov = (json.loads(line).get("provenance") or {})
        except json.JSONDecodeError:
            continue
        doc = (prov.get("doc") or "").strip()
        if doc:
            out[_norm(doc)] = out.get(_norm(doc), 0) + 1
    return out


def chunked_json_names():
    """Books that already have a chunked .json (so kb_ingest can see them)."""
    have = {}
    for f in glob.glob(f"{BOOK_DIR}/*.json"):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        meta = d.get("metadata") or {}
        chunks = d.get("chunks") or []
        if not chunks:
            continue
        name = meta.get("filename") or os.path.basename(f)
        have[_norm(name)] = len(chunks)
    return have


def audit():
    have_json = chunked_json_names()
    in_corpus = corpus_docs()
    rows = []
    for t in sorted(glob.glob(f"{BOOK_DIR}/*.txt")):
        b = os.path.basename(t)
        size = os.path.getsize(t)
        k = _norm(b)
        n_chunks = have_json.get(k, 0)
        n_units = in_corpus.get(k, 0)
        if not n_units:  # loose match — corpus doc names are sometimes truncated
            for ck, cn in in_corpus.items():
                if ck[:25] == k[:25]:
                    n_units = cn
                    break
        if b in SKIP_EXACT:
            status = "SKIP (duplicate/stub)"
        elif size < MIN_TXT_BYTES:
            status = "SKIP (too small — failed scrape)"
        elif n_units:
            status = "already in brain"
        else:
            status = "** MISSING — will ingest **"
        rows.append((b, size, n_chunks, n_units, status))
    return rows


def chunk():
    rows = audit()
    todo = [r for r in rows if r[4].startswith("**")]
    if not todo:
        print("nothing to ingest — every book is already in the brain")
        return 0

    os.makedirs(BATCH_DIR, exist_ok=True)
    for old in glob.glob(f"{BATCH_DIR}/b_*.txt"):
        os.remove(old)

    manifest, units, uid = {}, [], K_ID_BASE
    for b, size, _, _, _ in todo:
        path = f"{BOOK_DIR}/{b}"
        text = open(path, encoding="utf-8", errors="ignore").read()
        # Kindle scrapes carry per-page furniture on every page. Left in, it is
        # ~15% of the corpus and it annotates as if it were content.
        text = re.sub(r"^-{20,}$", " ", text, flags=re.M)
        text = re.sub(r"\bPage \d+:", " ", text)
        text = re.sub(r"Kindle Library", " ", text)
        text = re.sub(r"Location \d[\d,\.]* of [\d,\.]+\d?%?", " ", text)
        text = re.sub(r"Page \d+ of \d+[\d\.]*%?", " ", text)
        text = re.sub(r"<FULL_TEXT_(START|END)>", " ", text)
        # The reader's own chrome, OCR'd. Scanned books render "Learning reading
        # speed..." as "Learnina readina sneed...", so an exact match misses it and
        # it survives on EVERY page — pure noise the annotator would treat as text.
        text = re.sub(r"Learn\w{0,4}\s+read\w{0,4}\s+s\w{0,5}d\.*", " ", text, flags=re.I)
        text = re.sub(r"\b\d{1,3}(\.\d+)?%\s*(of\s*\d+)?", " ", text)   # stray page-progress
        text = re.sub(r"^\s*[=:>@©eWGK)(\|~“”\-\s]{6,}$", " ", text, flags=re.M)  # OCR gutter junk
        words = text.split()
        title = re.sub(r"^B[0-9A-Z]{9}_", "", b).replace(".txt", "")
        n_before = len(units)
        for i in range(0, len(words), WORDS_PER_CHUNK):
            body = " ".join(words[i:i + WORDS_PER_CHUNK])
            if len(body) < 200:
                continue
            u = f"k{uid}"
            uid += 1
            part = i // WORDS_PER_CHUNK + 1
            header = f"{title} | book | part {part}"
            units.append({"unit_id": u, "lib": "KB:book", "header": header, "text": body})
            manifest[u] = {"file": path, "title": title, "part": part, "lib": "KB:book"}
        print(f"  {len(units) - n_before:>4} units  {size // 1024:>5} KB  {title[:66]}")

    for i in range(0, len(units), UNITS_PER_BATCH):
        with open(f"{BATCH_DIR}/b_{i // UNITS_PER_BATCH:04d}.txt", "w", encoding="utf-8") as fh:
            for u in units[i:i + UNITS_PER_BATCH]:
                fh.write(f"===== UNIT {u['unit_id']} | LIB: {u['lib']} =====\n")
                fh.write(f"HEADER: {u['header']}\nTEXT: {u['text']}\n\n")

    json.dump(manifest, open(MANIFEST, "w"), indent=0)
    n_batches = (len(units) + UNITS_PER_BATCH - 1) // UNITS_PER_BATCH
    print(f"\n{len(units)} units -> {n_batches} batches in {BATCH_DIR}")
    print(f"manifest: {MANIFEST}")
    # Rule 7b: a chunk run that produced nothing while books were queued is a
    # failure, not an empty queue.
    if not units:
        raise SystemExit("chunked 0 units from {} books queued — aborting".format(len(todo)))
    return len(units)


def stamp_provenance():
    """Overwrite provenance.course on every unit from the manifest.

    The annotator is asked to lift the book title out of the unit header, and it
    does so unreliably: the same book came back as "SELL LIKE CRAZY", "SELL LIKE
    CRAZY How to Get As Many Clients, Cu…" and "Sell Like Crazy: How to Get…" in
    different batches, and **134 of 461 units carried no title at all**. That makes
    a book impossible to filter or attribute — you cannot say "Suby argues X" if a
    third of his units are anonymous.

    The mapping is already known exactly: kb_book_ingest wrote it to the manifest
    at chunk time. So take it from there rather than from the model. Deterministic,
    free, and idempotent.
    """
    if not os.path.exists(MANIFEST):
        raise SystemExit(f"no manifest at {MANIFEST} — run --chunk first")
    man = json.load(open(MANIFEST, encoding="utf-8"))
    ann = f"{BASE}/annotations.jsonl"
    if not os.path.exists(ann):
        raise SystemExit(f"no annotations at {ann} — annotate first")

    import shutil
    shutil.copyfile(ann, ann + ".pre-stamp")
    out, fixed, unknown = [], 0, 0
    for line in open(ann, encoding="utf-8"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = man.get(d.get("unit_id"))
        if not m:
            unknown += 1
            out.append(json.dumps(d, ensure_ascii=False))
            continue
        prov = d.get("provenance") or {}
        if prov.get("course") != m["title"]:
            fixed += 1
        prov["library"] = "KB:book"
        prov["course"] = m["title"]
        prov["module"] = f"part {m['part']}"
        d["provenance"] = prov
        out.append(json.dumps(d, ensure_ascii=False))
    with open(ann, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"stamped {len(out)} units — {fixed} titles corrected, {unknown} not in manifest")
    if unknown:
        print(f"  ⚠ {unknown} units had no manifest entry and were left as-is")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit", action="store_true", help="report only, change nothing")
    ap.add_argument("--chunk", action="store_true", help="write Brain 1 batch files")
    ap.add_argument("--stamp-provenance", action="store_true",
                    help="rewrite provenance.course from the manifest (run after annotating)")
    args = ap.parse_args()

    if args.chunk:
        chunk()
        return
    if args.stamp_provenance:
        stamp_provenance()
        return
    rows = audit()
    print(f"{'BOOK':<62}{'KB':>7}{'chunks':>8}{'units':>7}  STATUS")
    print("-" * 108)
    for b, size, nc, nu, st in rows:
        print(f"{b[:61]:<62}{size // 1024:>7}{nc:>8}{nu:>7}  {st}")
    missing = [r for r in rows if r[4].startswith("**")]
    print(f"\n{len(missing)} of {len(rows)} books missing from the brain "
          f"({sum(r[1] for r in missing) // 1024} KB of text)")


if __name__ == "__main__":
    main()
