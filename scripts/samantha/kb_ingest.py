#!/usr/bin/env python3
"""
Brain 3 — KB ingest + PROVENANCE classifier.

The KB is MIXED internal + external, and provenance is PER-DOCUMENT not per-folder
(e.g. `financial/` holds academic papers, `book/` holds Kindle scrapes, `meeting_notes/`
is ours). The confidentiality firewall keys off the per-doc class, so classification is
step one. See scripts/samantha/brain3_kb_extension_scope.md.

Two phases:
  --classify-only : label every doc EXTERNAL vs INTERNAL. Deterministic path/filename
                    signals first; Haiku (on Max, batched, parallel) only for the
                    ambiguous remainder. Writes brain3_build/provenance.json + prints counts.
  (default)       : + emit Brain-1-style unit records (one per chunk) into brain3_build/,
                    tagging each with its provenance class. [built after classify is validated]

100% Anthropic on Max — no embeddings, no paid API.
"""
import os, re, sys, json, glob, argparse
from concurrent.futures import ThreadPoolExecutor

KB = "/home/fields/knowledge-base"
OUT = "/home/fields/brain3_build"
HAIKU = "claude-haiku-4-5-20251001"
WORKERS = 6

# strong deterministic signals ---------------------------------------------------
EXT_PATH = re.compile(r"kindle_scraper|/books/|/book/", re.I)
EXT_TITLE = re.compile(r"\bevidence from\b|\bjournal\b|\b- 20\d\d - ch\b|\bproceedings\b|"
                       r"\bquarterly\b|\breview of\b|\bhandbook\b|blueprint", re.I)
INT_CATS = {"meeting_notes", "internal_projects", "code", "operational", "conversations"}
INT_TITLE = re.compile(r"working doc|business partner|1% agent|listing presentation g|"
                       r"\bfields\b|our (strategy|plan)|internal|standup|stand-up|roadmap", re.I)


def load_docs():
    docs = []
    for f in glob.glob(f"{KB}/**/*.json", recursive=True):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        m = d.get("metadata", {})
        cat = os.path.basename(os.path.dirname(f))
        chunks = d.get("chunks", [])
        snip = " ".join(str(c.get("content", "")) for c in chunks[:1])[:300]
        desc = " ".join(str(c.get("description", "")) for c in chunks[:2])[:200]
        docs.append({"file": f, "cat": cat,
                     "orig": str(m.get("original_file", "")),
                     "fname": str(m.get("filename", "")),
                     "doc_type": str(m.get("ai_classification", {}).get("document_type", "")) if isinstance(m.get("ai_classification"), dict) else "",
                     "desc": desc, "snip": snip, "n_chunks": len(chunks)})
    return docs


def deterministic(d):
    """Return 'external' | 'internal' | None (ambiguous)."""
    blob = f"{d['orig']} {d['fname']} {d['doc_type']}"
    if d["cat"] == "book" or d["doc_type"].upper() == "BOOK" or EXT_PATH.search(blob):
        return "external"
    if d["cat"] in INT_CATS:
        return "internal"
    if EXT_TITLE.search(blob):
        return "external"
    if INT_TITLE.search(blob):
        return "internal"
    return None


def claude(prompt, timeout=120):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")}
    import subprocess
    r = subprocess.run(["claude", "-p", "--model", HAIKU],
                       input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr[:200]}")
    return r.stdout.strip()


def haiku_classify(batch):
    """Classify a batch of ambiguous docs. Returns {idx: 'external'|'internal'}."""
    listing = "\n".join(
        json.dumps({"i": i, "file": d["orig"] or d["fname"], "type": d["doc_type"],
                    "desc": d["desc"], "snippet": d["snip"][:180]})
        for i, d in batch)
    p = ("Classify each real-estate knowledge-base document as EXTERNAL or INTERNAL.\n"
         "EXTERNAL = published/third-party material NOT created by this company: books, academic "
         "papers, journal articles, industry reports, external blog posts, market research.\n"
         "INTERNAL = created by/for THIS company (Fields, a Gold Coast agency): meeting notes, our "
         "strategy/plans, working docs, financials, code, internal projects, partner discussions.\n"
         "When genuinely unsure, default to INTERNAL (safer for the confidentiality firewall).\n\n"
         f"DOCUMENTS:\n{listing}\n\n"
         'Return ONLY a JSON object mapping index -> "external" or "internal", e.g. {"0":"external"}.')
    try:
        out = claude(p)
        m = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
        return {int(k): ("external" if str(v).lower().startswith("e") else "internal")
                for k, v in m.items()}
    except Exception as e:
        sys.stderr.write(f"[haiku] FAIL-CLOSED (batch->internal): {e}\n")
        return {i: "internal" for i, _ in batch}  # fail to the SAFE side (firewall)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classify-only", action="store_true")
    ap.add_argument("--batch", type=int, default=20)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    docs = load_docs()
    sys.stderr.write(f"[kb] loaded {len(docs)} docs / {sum(d['n_chunks'] for d in docs)} chunks\n")

    prov, ambiguous = {}, []
    for i, d in enumerate(docs):
        c = deterministic(d)
        if c:
            prov[d["file"]] = {"class": c, "how": "deterministic", "cat": d["cat"]}
        else:
            ambiguous.append((i, d))
    det_ext = sum(1 for v in prov.values() if v["class"] == "external")
    det_int = sum(1 for v in prov.values() if v["class"] == "internal")
    sys.stderr.write(f"[deterministic] external={det_ext} internal={det_int} | ambiguous={len(ambiguous)} -> Haiku\n")

    # Haiku-classify the ambiguous remainder, batched + parallel
    batches = [ambiguous[i:i + args.batch] for i in range(0, len(ambiguous), args.batch)]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(haiku_classify, batches))
    # haiku_classify keys results by each doc's GLOBAL index i (the "i" field in the listing)
    for batch, res in zip(batches, results):
        for i, d in batch:
            prov[d["file"]] = {"class": res.get(i, "internal"), "how": "haiku", "cat": d["cat"]}

    # summary
    ext = [f for f, v in prov.items() if v["class"] == "external"]
    intr = [f for f, v in prov.items() if v["class"] == "internal"]
    by_cat = {}
    for f, v in prov.items():
        by_cat.setdefault(v["cat"], {"external": 0, "internal": 0})[v["class"]] += 1

    json.dump({"provenance": prov,
               "summary": {"total": len(prov), "external": len(ext), "internal": len(intr),
                           "by_category": by_cat}},
              open(f"{OUT}/provenance.json", "w"), indent=2)

    print(f"\n=== PROVENANCE SPLIT ({len(prov)} docs) ===")
    print(f"  EXTERNAL (public-safe): {len(ext)}")
    print(f"  INTERNAL (firewalled) : {len(intr)}")
    print(f"\n  per category  (external / internal):")
    for cat in sorted(by_cat):
        b = by_cat[cat]
        print(f"    {cat:16s}: {b['external']:4d} ext / {b['internal']:4d} int")
    print(f"\n  saved -> {OUT}/provenance.json")

    if not args.classify_only:
        sys.stderr.write("[ingest] unit emission not built yet — run --classify-only for now.\n")


if __name__ == "__main__":
    main()
