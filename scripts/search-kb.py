#!/usr/bin/env python3
"""
search-kb.py — Search the Fields Knowledge Base.

Called by Claude Opus workers to find relevant documents, strategies,
meeting notes, book insights, and operational knowledge.

Usage:
    python3 scripts/search-kb.py "query terms"
    python3 scripts/search-kb.py "query" --type strategy --max 5
    python3 scripts/search-kb.py --list-categories
    python3 scripts/search-kb.py --tag "real-estate" --max 10
    python3 scripts/search-kb.py --chunk chunk_0042 --file path/to/index.json

Data: 1,644 indexed documents across 11 categories from Azure Blob.
Location: /home/fields/knowledge-base/
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

KB_DIR = Path("/home/fields/knowledge-base")


def load_all_indexes(doc_type: str = None) -> list[dict]:
    """Load all JSON index files, optionally filtered by document type."""
    indexes = []
    for json_file in KB_DIR.rglob("*.json"):
        try:
            with open(json_file) as f:
                data = json.load(f)
            # Skip raw ingests (no chunks)
            if "chunks" not in data or not data["chunks"]:
                continue
            # Add file path for reference
            data["_index_file"] = str(json_file.relative_to(KB_DIR))
            data["_category"] = json_file.parent.name
            # Filter by type if requested
            if doc_type:
                classification = data.get("metadata", {}).get("ai_classification", {})
                if classification.get("document_type", "").upper() != doc_type.upper():
                    continue
            indexes.append(data)
        except (json.JSONDecodeError, Exception):
            continue
    return indexes


def search_text(query: str, doc_type: str = None, max_results: int = 10) -> list[dict]:
    """Full-text search across all KB chunks. Returns ranked results."""
    indexes = load_all_indexes(doc_type)
    query_lower = query.lower()
    keywords = query_lower.split()

    results = []
    for idx in indexes:
        filename = idx.get("metadata", {}).get("filename", "unknown")
        category = idx.get("_category", "unknown")
        classification = idx.get("metadata", {}).get("ai_classification", {})

        for chunk in idx.get("chunks", []):
            score = 0
            raw_desc = chunk.get("description") or ""
            desc = (raw_desc if isinstance(raw_desc, str) else str(raw_desc)).lower()
            raw_content = chunk.get("content") or ""
            content = (raw_content if isinstance(raw_content, str) else str(raw_content)).lower()
            raw_tags = chunk.get("tags") or []
            tags = [str(t).lower() for t in raw_tags if isinstance(t, (str, int, float))]

            for kw in keywords:
                if kw in desc:
                    score += 10
                if kw in tags:
                    score += 5
                score += content.count(kw)

            if score > 0:
                results.append({
                    "score": score,
                    "document": filename,
                    "category": category,
                    "document_type": classification.get("document_type", "GENERAL"),
                    "chunk_id": chunk.get("chunk_id", ""),
                    "description": chunk.get("description", ""),
                    "tags": chunk.get("tags", []),
                    "content_preview": (chunk.get("content") or "")[:400],
                    "index_file": idx.get("_index_file", ""),
                    # Type-specific metadata
                    "key_concepts": chunk.get("key_concepts", []),
                    "actionable_insights": chunk.get("actionable_insights", []),
                    "key_initiatives": chunk.get("key_initiatives", []),
                    "key_decisions": chunk.get("key_decisions", []),
                    "key_points": chunk.get("key_points", []),
                })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:max_results]


def search_by_tag(tag: str, max_results: int = 10) -> list[dict]:
    """Search chunks by tag."""
    indexes = load_all_indexes()
    tag_lower = tag.lower()
    results = []

    for idx in indexes:
        filename = idx.get("metadata", {}).get("filename", "unknown")
        tag_index = idx.get("tag_index", {})

        # Check tag_index for matching tags
        for idx_tag, chunk_ids in tag_index.items():
            if tag_lower in idx_tag.lower():
                for chunk in idx.get("chunks", []):
                    if chunk.get("chunk_id") in chunk_ids:
                        results.append({
                            "document": filename,
                            "category": idx.get("_category", ""),
                            "chunk_id": chunk.get("chunk_id", ""),
                            "matched_tag": idx_tag,
                            "description": chunk.get("description", ""),
                            "tags": chunk.get("tags", []),
                            "content_preview": (chunk.get("content") or "")[:400],
                        })

    return results[:max_results]


def list_categories() -> dict:
    """List all categories with document counts and summaries."""
    stats = defaultdict(lambda: {"documents": 0, "chunks": 0, "files": []})

    for json_file in KB_DIR.rglob("*.json"):
        try:
            with open(json_file) as f:
                data = json.load(f)
            if "chunks" not in data:
                continue
            category = json_file.parent.name
            filename = data.get("metadata", {}).get("filename", json_file.name)
            classification = data.get("metadata", {}).get("ai_classification", {})
            stats[category]["documents"] += 1
            stats[category]["chunks"] += len(data.get("chunks", []))
            stats[category]["files"].append({
                "filename": filename,
                "type": classification.get("document_type", "GENERAL"),
                "description": classification.get("document_description", "")[:100],
                "chunks": len(data.get("chunks", [])),
            })
        except Exception:
            continue

    return dict(stats)


def get_chunk(chunk_id: str, index_file: str) -> dict:
    """Get a specific chunk by ID from an index file."""
    path = KB_DIR / index_file
    if not path.exists():
        return {"error": f"Index file not found: {index_file}"}

    with open(path) as f:
        data = json.load(f)

    for chunk in data.get("chunks", []):
        if chunk.get("chunk_id") == chunk_id:
            return {
                "document": data.get("metadata", {}).get("filename", "unknown"),
                "chunk_id": chunk_id,
                "description": chunk.get("description", ""),
                "tags": chunk.get("tags", []),
                "content": chunk.get("content", ""),
                "token_count": chunk.get("token_count", 0),
                **{k: v for k, v in chunk.items() if k.startswith("key_") or k.startswith("actionable")},
            }

    return {"error": f"Chunk {chunk_id} not found in {index_file}"}


def main():
    parser = argparse.ArgumentParser(description="Search the Fields Knowledge Base")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--type", help="Filter by document type (BOOK, STRATEGY, CODE, etc.)")
    parser.add_argument("--max", type=int, default=10, help="Max results (default: 10)")
    parser.add_argument("--tag", help="Search by tag instead of text")
    parser.add_argument("--list-categories", action="store_true", help="List all categories")
    parser.add_argument("--chunk", help="Get specific chunk by ID")
    parser.add_argument("--file", help="Index file for --chunk lookup")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if args.list_categories:
        cats = list_categories()
        if args.json:
            print(json.dumps(cats, indent=2))
        else:
            total_docs = sum(c["documents"] for c in cats.values())
            total_chunks = sum(c["chunks"] for c in cats.values())
            print(f"Knowledge Base: {total_docs} documents, {total_chunks} chunks\n")
            for cat, info in sorted(cats.items()):
                print(f"  {cat}: {info['documents']} docs, {info['chunks']} chunks")
                for f in info["files"][:3]:
                    print(f"    - {f['filename']}: {f['description']}")
                if len(info["files"]) > 3:
                    print(f"    ... and {len(info['files']) - 3} more")
        return

    if args.chunk:
        if not args.file:
            print("Error: --file required with --chunk", file=sys.stderr)
            sys.exit(1)
        result = get_chunk(args.chunk, args.file)
        print(json.dumps(result, indent=2))
        return

    if args.tag:
        results = search_by_tag(args.tag, max_results=args.max)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Tag search: '{args.tag}' — {len(results)} results\n")
            for r in results:
                print(f"  [{r['category']}] {r['document']} ({r['matched_tag']})")
                print(f"    {r['description'][:120]}")
                print()
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    results = search_text(args.query, doc_type=args.type, max_results=args.max)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Search: '{args.query}' — {len(results)} results\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r['category']}] {r['document']} (score: {r['score']})")
            print(f"   Type: {r['document_type']} | Chunk: {r['chunk_id']}")
            print(f"   {r['description'][:150]}")
            if r.get("key_concepts"):
                print(f"   Concepts: {', '.join(r['key_concepts'][:3])}")
            if r.get("key_initiatives"):
                print(f"   Initiatives: {', '.join(r['key_initiatives'][:3])}")
            if r.get("actionable_insights"):
                print(f"   Insights: {', '.join(r['actionable_insights'][:2])}")
            print()


if __name__ == "__main__":
    main()
