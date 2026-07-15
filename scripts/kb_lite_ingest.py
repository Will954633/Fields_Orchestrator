#!/usr/bin/env python3
"""
kb_lite_ingest.py — Lightweight KB ingest (NO external LLM) for Brain 3 coverage.

Chunks source docs into /home/fields/knowledge-base/<category>/ in the format
scripts/search-kb.py already reads. Fixes the coverage blind spots — starting with
the 'Before You List' seller book and the fix-history operational logs — without the
OpenAI classification the old pipeline depends on (that quota is dead).

Run nightly via cron to keep fresh. Extend SOURCES for more coverage later.
"""
import os, json, glob, subprocess
from datetime import datetime
from pathlib import Path

KB = Path("/home/fields/knowledge-base")
KEYWORDS = ["seller", "selling", "listing", "valuation", "market", "price", "agent", "buyer",
            "gold coast", "robina", "burleigh", "varsity", "commission", "appraisal", "auction",
            "negotiation", "data", "flood", "suburb", "comparable", "days on market", "fields",
            "before you list", "vendor", "campaign", "styling", "photography"]


def chunk_words(text, size=600):
    w = text.split()
    return [" ".join(w[i:i + size]) for i in range(0, len(w), size)] or [""]


def make_tags(text):
    low = text.lower()
    return [k.replace(" ", "-") for k in KEYWORDS if k in low][:8]


def build_doc(name, ext, doc_type, category, full_text, label="", fixed_tags=None):
    fixed_tags = fixed_tags or []
    chunks = []
    for i, ct in enumerate(chunk_words(full_text)):
        chunks.append({
            "chunk_id": f"chunk_{i:04d}",
            "document_type": doc_type,
            "description": (f"[{label}] " if label else "") + " ".join(ct.split()[:24])[:150],
            "tags": sorted(set(fixed_tags + make_tags(ct))),
            "token_count": int(len(ct.split()) * 1.33),
            "content": ct,
            "key_concepts": [],
            "actionable_insights": [],
        })
    return {
        "metadata": {
            "original_file": name, "filename": name, "file_extension": ext,
            "processed_date": datetime.utcnow().isoformat(),
            "file_size_chars": len(full_text),
            "file_size_tokens": int(len(full_text.split()) * 1.33),
            "total_chunks": len(chunks),
            "ai_classification": {"document_type": doc_type, "category": category},
        },
        "chunks": chunks, "tag_index": {},
    }


def write_doc(category, slug, doc):
    d = KB / category
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.json").write_text(json.dumps(doc))


def ingest_book():
    pdf = "/home/fields/Fields_Orchestrator/08_Seller-Book/Latest_Copy_26th-May-2026/Fields_book_digital.pdf"
    if not os.path.exists(pdf):
        return "book: source PDF not found, skipped"
    txt = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True).stdout
    if len(txt.split()) < 500:
        return "book: extraction too short, skipped"
    doc = build_doc("Before You List — Fields seller book (physical, hand-delivered to doors)",
                    ".pdf", "BOOK", "book", txt,
                    label="Before You List — Fields physical seller book, hand-delivered to doors",
                    fixed_tags=["before-you-list", "seller-book", "physical-book", "hand-delivered",
                                "before-you-list-book", "fields", "seller", "book"])
    write_doc("book", "before_you_list_seller_book", doc)
    return f"book: {doc['metadata']['total_chunks']} chunks ({doc['metadata']['file_size_tokens']} tokens)"


def ingest_fix_history():
    files = sorted(glob.glob("/home/fields/Fields_Orchestrator/logs/fix-history/*.md"))
    if not files:
        return "fix_history: none found"
    text = "\n\n".join(Path(f).read_text(errors="ignore") for f in files)
    doc = build_doc("Fix history — operational repair log", ".md", "FIX_HISTORY", "operational", text)
    write_doc("operational", "fix_history_all", doc)
    return f"fix_history: {len(files)} files -> {doc['metadata']['total_chunks']} chunks"


if __name__ == "__main__":
    print(datetime.utcnow().isoformat(), "kb_lite_ingest")
    print(" ", ingest_book())
    print(" ", ingest_fix_history())
