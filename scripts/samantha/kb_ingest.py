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

# --- CURATION + CONFIDENTIALITY signals -----------------------------------------
# The firewall axis is CONFIDENTIALITY (public-safe vs private), NOT authorship. Two filters:
#   (A) CURATION  — is this genuine KNOWLEDGE, or storage junk / sensitive records to DROP?
#   (B) CONFIDENTIALITY — of what's kept: PUBLIC-SAFE vs PRIVATE.
# HARD_PRIVATE = sensitive records (invoices, statements, bank, tax): DROPPED entirely (never
# ingested — both sensitive and worthless as knowledge). Overrides the LLM. Fail CLOSED.
HARD_PRIVATE = re.compile(r"\binvoice\b|\bstatement\b|\bbank\b|\btax\b|\breceipt\b|payslip|"
                          r"\bpayment\b|acc[:_ ]\d|_fy\d|\bpaid\b|remittance|payroll", re.I)
# storage junk: scanned files with no real words (all-digits / date-range / opaque codes)
JUNK_NAME = re.compile(r"^[\d _\-\.]+$|^\w{0,4}_?\d{6,}|_\d{8}_\d{8}|^[a-f0-9]{6,}\.", re.I)
# public-safe published knowledge
PUB_PATH = re.compile(r"kindle_scraper|/books?/", re.I)
PUB_TITLE = re.compile(r"\bevidence from\b|\bjournal\b|\b- 20\d\d - ch\b|\bproceedings\b|"
                       r"\bquarterly\b|\breview of\b|\bhandbook\b|blueprint|\bact 20\d\d\b|"
                       r"effects of|impact of|analysis of|\bstudy\b", re.I)
# clearly-internal (private) business knowledge worth KEEPING behind the firewall
PRIV_CATS = {"meeting_notes", "internal_projects", "operational", "strategy", "project", "code"}
PRIV_TITLE = re.compile(r"working doc|business partner|1% agent|listing presentation g|"
                        r"\bfields\b|our (strategy|plan)|standup|stand-up|roadmap|slackthread|session_", re.I)


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
    """Return one of: 'drop_private' | 'drop_junk' | 'public' | 'private' | None (ambiguous)."""
    blob = f"{d['orig']} {d['fname']} {d['doc_type']}"
    base = os.path.basename(d["orig"] or d["fname"])
    # (A) CURATION first — drop sensitive records + storage junk before anything else
    if HARD_PRIVATE.search(blob):
        return "drop_private"
    if JUNK_NAME.search(base):
        return "drop_junk"
    # (B) CONFIDENTIALITY of the remaining knowledge
    if d["cat"] == "book" or d["doc_type"].upper() == "BOOK" or PUB_PATH.search(blob):
        return "public"
    if PUB_TITLE.search(blob):
        return "public"
    if d["cat"] in PRIV_CATS or PRIV_TITLE.search(blob):
        return "private"
    return None  # ambiguous -> Haiku (public-safe vs private, default private)


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
    """Confidentiality classify ambiguous knowledge docs. Returns {idx: 'public'|'private'}."""
    listing = "\n".join(
        json.dumps({"i": i, "file": d["orig"] or d["fname"], "type": d["doc_type"],
                    "desc": d["desc"], "snippet": d["snip"][:180]})
        for i, d in batch)
    p = ("For each real-estate knowledge-base document decide PUBLIC_SAFE vs PRIVATE — this gates a "
         "confidentiality firewall, so err toward PRIVATE.\n"
         "PUBLIC_SAFE = already-published, non-confidential material safe to quote in public content: "
         "books, academic papers, journal articles, legislation, public industry reports/news.\n"
         "PRIVATE = anything confidential to this company (Fields, a Gold Coast agency): internal "
         "strategy/plans, meeting/partner notes, financial records, client data, unpublished drafts, "
         "code, operational docs. If there is ANY doubt it could be confidential, choose PRIVATE.\n\n"
         f"DOCUMENTS:\n{listing}\n\n"
         'Return ONLY a JSON object mapping index -> "public" or "private", e.g. {"0":"public"}.')
    try:
        out = claude(p)
        m = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
        return {int(k): ("public" if str(v).lower().startswith("pub") else "private")
                for k, v in m.items()}
    except Exception as e:
        sys.stderr.write(f"[haiku] FAIL-CLOSED (batch->private): {e}\n")
        return {i: "private" for i, _ in batch}  # fail to the SAFE side (firewall)


def emit_batches(prov):
    """Kept (public/private) chunks -> Brain-1-format batch files in brain3_build/batches_<pool>/,
    + units_manifest.json (unit_id -> file/chunk/provenance) for citation + quote-verify."""
    kept = sorted((f, v) for f, v in prov.items() if v["class"] in ("public", "private"))
    manifest, uid = {}, 0
    for pool in ("public", "private"):
        bdir = f"{OUT}/batches_{pool}"
        os.makedirs(bdir, exist_ok=True)
        for old in glob.glob(f"{bdir}/b_*.txt"):
            os.remove(old)
        units = []
        for f, v in kept:
            if v["class"] != pool:
                continue
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            m = d.get("metadata", {})
            fname = os.path.basename(str(m.get("original_file", "") or m.get("filename", "") or f))
            for c in d.get("chunks", []):
                content = " ".join(str(c.get("content", "")).split()[:1200]).strip()
                if len(content) < 40:
                    continue  # skip empty/tiny chunks
                u = f"k{uid:05d}"; uid += 1
                desc = " ".join(str(c.get("description", "")).split())[:140]
                units.append({"unit_id": u, "lib": f"{pool}:{v['cat']}",
                              "header": f"{fname} | {desc}", "text": content})
                manifest[u] = {"file": f, "chunk_id": c.get("chunk_id"), "pool": pool,
                               "category": v["cat"], "filename": fname}
        for i in range(0, len(units), 10):
            with open(f"{bdir}/b_{i//10:04d}.txt", "w", encoding="utf-8") as fh:
                for u in units[i:i + 10]:
                    fh.write(f"===== UNIT {u['unit_id']} | LIB: {u['lib']} =====\n")
                    fh.write(f"HEADER: {u['header']}\nTEXT: {u['text']}\n\n")
        sys.stderr.write(f"[emit] {pool}: {len(units)} units -> {(len(units)+9)//10} batches in {bdir}\n")
    json.dump(manifest, open(f"{OUT}/units_manifest.json", "w"), indent=0)
    sys.stderr.write(f"[emit] manifest: {len(manifest)} units -> {OUT}/units_manifest.json\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classify-only", action="store_true")
    ap.add_argument("--emit-only", action="store_true", help="skip classify; emit batches from existing provenance.json")
    ap.add_argument("--batch", type=int, default=20)
    args = ap.parse_args()

    if args.emit_only:
        prov = json.load(open(f"{OUT}/provenance.json"))["provenance"]
        emit_batches(prov)
        return

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
    dc = lambda k: sum(1 for v in prov.values() if v["class"] == k)
    sys.stderr.write(f"[deterministic] drop_private={dc('drop_private')} drop_junk={dc('drop_junk')} "
                     f"public={dc('public')} private={dc('private')} | ambiguous={len(ambiguous)} -> Haiku\n")

    # Haiku confidentiality-classify the ambiguous remainder, batched + parallel
    batches = [ambiguous[i:i + args.batch] for i in range(0, len(ambiguous), args.batch)]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(haiku_classify, batches))
    for batch, res in zip(batches, results):
        for i, d in batch:
            prov[d["file"]] = {"class": res.get(i, "private"), "how": "haiku", "cat": d["cat"]}

    CLASSES = ["public", "private", "drop_private", "drop_junk"]
    counts = {c: dc(c) for c in CLASSES}
    kept = counts["public"] + counts["private"]
    by_cat = {}
    for f, v in prov.items():
        by_cat.setdefault(v["cat"], {c: 0 for c in CLASSES})[v["class"]] += 1

    json.dump({"provenance": prov, "summary": {"total": len(prov), "kept": kept, **counts,
                                               "by_category": by_cat}},
              open(f"{OUT}/provenance.json", "w"), indent=2)

    print(f"\n=== CURATED CONFIDENTIALITY SPLIT ({len(prov)} docs) ===")
    print(f"  KEPT (knowledge): {kept}")
    print(f"    • PUBLIC-SAFE : {counts['public']}   (books/papers/articles — can inform public content)")
    print(f"    • PRIVATE     : {counts['private']}   (internal knowledge — firewalled, Samantha-only)")
    print(f"  DROPPED: {counts['drop_private'] + counts['drop_junk']}")
    print(f"    • sensitive records (invoices/statements/bank/tax): {counts['drop_private']}")
    print(f"    • storage junk (scanned/opaque, no knowledge)     : {counts['drop_junk']}")
    print(f"\n  per category  (public / private / drop_priv / drop_junk):")
    for cat in sorted(by_cat):
        b = by_cat[cat]
        print(f"    {cat:16s}: {b['public']:4d} / {b['private']:4d} / {b['drop_private']:4d} / {b['drop_junk']:4d}")
    print(f"\n  saved -> {OUT}/provenance.json")

    if not args.classify_only:
        emit_batches(prov)


if __name__ == "__main__":
    main()
