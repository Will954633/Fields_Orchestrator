#!/usr/bin/env python3
"""
save-to-kb.py — Save documents to the Fields Knowledge Base.

Ingests content, classifies it, chunks it, extracts metadata, saves the
JSON index locally and uploads to Azure Blob for persistence.

Usage:
    # Save a file
    python3 scripts/save-to-kb.py --file /path/to/doc.md

    # Save with explicit category (skip AI classification)
    python3 scripts/save-to-kb.py --file /path/to/doc.md --category strategy

    # Save raw text content
    python3 scripts/save-to-kb.py --text "Meeting notes from today..." --title "Meeting 2026-03-30" --category meeting_notes

    # Save from stdin (pipe email thread, task result, etc.)
    cat email_thread.txt | python3 scripts/save-to-kb.py --stdin --title "Email thread with agent" --category conversations

    # Save with custom tags
    python3 scripts/save-to-kb.py --file doc.md --tags "marketing,facebook,gold-coast"

    # Dry run (classify + chunk but don't save)
    python3 scripts/save-to-kb.py --file doc.md --dry-run

    # Skip AI classification/extraction (fast, just chunk and save)
    python3 scripts/save-to-kb.py --file doc.md --category strategy --skip-ai
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

AEST = timezone(timedelta(hours=10))
KB_DIR = Path("/home/fields/knowledge-base")
CHUNK_SIZE_TOKENS = 800

DOCUMENT_TYPES = [
    "BOOK", "CODE", "MARKETING", "STRATEGY", "PROJECT",
    "MEETING_NOTES", "FINANCIAL", "OPERATIONAL", "INTERNAL_PROJECTS",
    "GENERAL", "CONVERSATIONS"
]

CATEGORY_MAP = {
    "BOOK": "book", "CODE": "code", "MARKETING": "marketing",
    "STRATEGY": "strategy", "PROJECT": "project",
    "MEETING_NOTES": "meeting_notes", "FINANCIAL": "financial",
    "OPERATIONAL": "operational", "INTERNAL_PROJECTS": "internal_projects",
    "GENERAL": "general", "CONVERSATIONS": "conversations",
}


def count_tokens(text: str) -> int:
    """Estimate token count. Uses tiktoken if available, else ~4 chars/token."""
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model("gpt-4")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def extract_text_from_file(filepath: Path) -> tuple[str, str]:
    """Extract text from supported file types."""
    ext = filepath.suffix.lower()

    if ext in (".txt", ".md"):
        return filepath.read_text(errors="ignore"), ext

    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(str(filepath))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip()), ext
        except Exception as e:
            print(f"Warning: DOCX extraction failed: {e}", file=sys.stderr)
            return "", ext

    if ext == ".pdf":
        try:
            import PyPDF2
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages), ext
        except Exception as e:
            print(f"Warning: PDF extraction failed: {e}", file=sys.stderr)
            return "", ext

    # Fallback: try reading as text
    try:
        return filepath.read_text(errors="ignore"), ext
    except Exception:
        return "", ext


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE_TOKENS) -> list[str]:
    """Split text into chunks by paragraph grouping within token budget."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        candidate = (current + "\n\n" + para) if current else para
        if count_tokens(candidate) > chunk_size and current:
            chunks.append(current.strip())
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current.strip())
    return chunks


def classify_document(filename: str, content: str) -> dict:
    """Classify document type using OpenAI."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    content_sample = content[:2000]
    prompt = (
        "Analyze this document and classify it.\n\n"
        f"Filename: {filename}\n"
        f"Content Sample: {content_sample}\n\n"
        f"You MUST select ONE document type from: {', '.join(DOCUMENT_TYPES)}\n\n"
        "Respond in JSON:\n"
        '{\n'
        '    "document_type": "one of the types above",\n'
        '    "document_description": "Custom description of THIS document (1-2 sentences)",\n'
        '    "extraction_focus": "What to extract from THIS content for maximum value"\n'
        '}'
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at document classification. Always respond with valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        result = json.loads(raw)
        if result.get("document_type") not in DOCUMENT_TYPES:
            result["document_type"] = "GENERAL"
        return result
    except Exception as e:
        return {
            "document_type": "GENERAL",
            "document_description": f"Document: {filename}",
            "extraction_focus": "Extract key information",
            "_error": str(e),
        }


def extract_chunk_metadata(chunk_text: str, chunk_id: str, classification: dict) -> dict:
    """Extract type-specific metadata from a chunk using OpenAI."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    doc_type = classification.get("document_type", "GENERAL")
    if doc_type == "BOOK":
        instructions = "Extract: description (str), tags (list), key_concepts (5-7 principles), actionable_insights (3-5 actions)"
    elif doc_type == "CODE":
        instructions = "Extract: description (str), tags (list), technical_concepts, implementation_notes, usage_examples"
    elif doc_type in ["MARKETING", "STRATEGY"]:
        instructions = "Extract: description (str), tags (list), key_initiatives, success_metrics, target_focus"
    elif doc_type in ["MEETING_NOTES", "CONVERSATIONS"]:
        instructions = "Extract: description (str), tags (list), key_decisions, business_facts, action_items, strategic_insights"
    else:
        instructions = "Extract: description (str), tags (list), key_points, actions"

    prompt = (
        f"Analyzing {doc_type} document chunk {chunk_id}.\n\n"
        f"Context: {classification.get('document_description', '')}\n"
        f"Focus: {classification.get('extraction_focus', '')}\n\n"
        f"{instructions}\n\n"
        f"Content:\n{chunk_text}\n\n"
        "Return valid JSON OBJECT with the requested fields."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Extract information from {doc_type} documents. Return valid JSON OBJECT only."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        result = json.loads(raw)
        if isinstance(result, list):
            result = result[0] if result and isinstance(result[0], dict) else {"description": "Content chunk", "tags": []}
        return result
    except Exception as e:
        return {"description": "Content chunk", "tags": [], "_error": str(e)}


def build_index(
    text: str,
    filename: str,
    source_path: str,
    classification: dict,
    skip_ai: bool = False,
    custom_tags: list[str] = None,
) -> dict:
    """Build the full document index (same schema as samantha KB)."""
    chunks_text = split_into_chunks(text)
    chunks = []
    tag_index = {}

    for i, chunk_text in enumerate(chunks_text):
        chunk_id = f"chunk_{i+1:04d}"

        if skip_ai:
            metadata = {
                "description": f"Chunk {chunk_id} of {filename}",
                "tags": custom_tags or [],
            }
        else:
            metadata = extract_chunk_metadata(chunk_text, chunk_id, classification)
            print(f"  Extracted metadata for {chunk_id} ({count_tokens(chunk_text)} tokens)", file=sys.stderr)

        tags = metadata.get("tags", [])
        if custom_tags:
            tags = list(set(tags + custom_tags))

        chunk_doc = {
            "chunk_id": chunk_id,
            "document_type": classification.get("document_type", "GENERAL"),
            "content": chunk_text,
            "token_count": count_tokens(chunk_text),
            **metadata,
            "tags": tags,
        }
        chunks.append(chunk_doc)

        # Build tag index
        for tag in tags:
            tag_key = str(tag).lower().replace(" ", "-")
            if tag_key not in tag_index:
                tag_index[tag_key] = []
            tag_index[tag_key].append(chunk_id)

    index = {
        "metadata": {
            "original_file": source_path,
            "filename": filename,
            "file_extension": Path(filename).suffix if "." in filename else ".txt",
            "processed_date": datetime.now(AEST).isoformat(),
            "file_size_chars": len(text),
            "file_size_tokens": count_tokens(text),
            "total_chunks": len(chunks),
            "ai_classification": classification,
        },
        "chunks": chunks,
        "tag_index": tag_index,
    }
    return index


def save_index(index: dict, category: str) -> Path:
    """Save index JSON to local KB directory."""
    filename = index["metadata"]["filename"]
    safe_name = re.sub(r"[^\w\-.]", "_", filename)
    ts = datetime.now(AEST).strftime("%Y%m%d_%H%M%S")
    json_name = f"{Path(safe_name).stem}_{ts}.json"

    cat_dir = KB_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    out_path = cat_dir / json_name

    with open(out_path, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    return out_path


def upload_to_blob(local_path: Path, blob_name: str) -> bool:
    """Upload to blob storage via shared.blob_storage (local FS or Azure)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from shared import blob_storage  # type: ignore
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        url = blob_storage.upload("knowledge-base", blob_name, data, content_type="application/json")
        return url is not None
    except Exception as e:
        print(f"Warning: Blob upload failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Save documents to the Fields Knowledge Base")
    parser.add_argument("--file", help="Path to file to ingest")
    parser.add_argument("--text", help="Raw text content to ingest")
    parser.add_argument("--stdin", action="store_true", help="Read content from stdin")
    parser.add_argument("--title", help="Document title (required for --text/--stdin)")
    parser.add_argument("--category", help="Force category (skip AI classification): book, strategy, marketing, code, etc.")
    parser.add_argument("--tags", help="Comma-separated custom tags")
    parser.add_argument("--skip-ai", action="store_true", help="Skip AI classification/extraction (fast mode)")
    parser.add_argument("--dry-run", action="store_true", help="Classify + chunk but don't save")
    parser.add_argument("--no-upload", action="store_true", help="Save locally but skip Azure Blob upload")
    args = parser.parse_args()

    # Resolve content
    if args.stdin:
        text = sys.stdin.read().strip()
        filename = args.title or f"stdin_{datetime.now(AEST).strftime('%Y%m%d_%H%M%S')}"
        source_path = "stdin"
    elif args.text:
        text = args.text
        filename = args.title or f"text_{datetime.now(AEST).strftime('%Y%m%d_%H%M%S')}"
        source_path = "inline"
    elif args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        text, _ = extract_text_from_file(filepath)
        filename = filepath.name
        source_path = str(filepath.absolute())
    else:
        print("Error: provide --file, --text, or --stdin", file=sys.stderr)
        sys.exit(1)

    if not text.strip():
        print("Error: no text content extracted", file=sys.stderr)
        sys.exit(1)

    custom_tags = [t.strip() for t in args.tags.split(",")] if args.tags else []

    print(f"Content: {filename} ({count_tokens(text)} tokens, {len(text)} chars)", file=sys.stderr)

    # Classify
    if args.category and args.skip_ai:
        classification = {
            "document_type": args.category.upper(),
            "document_description": f"Document: {filename}",
            "extraction_focus": "General content",
        }
        print(f"Category: {args.category} (manual, AI skipped)", file=sys.stderr)
    elif args.category:
        # Use manual category but still AI-classify for description
        classification = classify_document(filename, text)
        classification["document_type"] = args.category.upper()
        print(f"Category: {args.category} (manual, AI description: {classification.get('document_description', '')[:80]})", file=sys.stderr)
    else:
        classification = classify_document(filename, text)
        print(f"Category: {classification['document_type']} (AI classified: {classification.get('document_description', '')[:80]})", file=sys.stderr)

    # Determine folder category
    doc_type = classification["document_type"]
    category = args.category or CATEGORY_MAP.get(doc_type, doc_type.lower())

    # Build index
    print(f"Chunking into ~{CHUNK_SIZE_TOKENS} token chunks...", file=sys.stderr)
    index = build_index(text, filename, source_path, classification, skip_ai=args.skip_ai, custom_tags=custom_tags)
    print(f"Chunks: {index['metadata']['total_chunks']}, Tags: {len(index['tag_index'])}", file=sys.stderr)

    if args.dry_run:
        print("\n--- DRY RUN (not saving) ---", file=sys.stderr)
        print(json.dumps({
            "classification": classification,
            "chunks": index["metadata"]["total_chunks"],
            "tokens": index["metadata"]["file_size_tokens"],
            "tags": list(index["tag_index"].keys()),
            "category": category,
        }, indent=2))
        return

    # Save locally
    local_path = save_index(index, category)
    print(f"Saved: {local_path}", file=sys.stderr)

    # Upload to Azure Blob
    if not args.no_upload:
        blob_name = f"{category}/{local_path.name}"
        uploaded = upload_to_blob(local_path, blob_name)
        if uploaded:
            print(f"Uploaded to Azure Blob: knowledge-base/{blob_name}", file=sys.stderr)
        else:
            print("Blob upload skipped or failed", file=sys.stderr)

    # Output the path for programmatic use
    print(str(local_path))


if __name__ == "__main__":
    main()
