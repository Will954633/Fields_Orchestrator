#!/usr/bin/env python3
"""
Build an audio library + podcast RSS feed from local strategy docs.

Reads markdown + PDF files from configured source dirs, converts each to an
MP3 via edge-tts (Australian female voice), and writes a podcast-compatible
RSS feed. Cached by content hash — re-runs only regenerate changed files.
"""
import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import edge_tts
from feedgen.feed import FeedGenerator

VOICE = "en-AU-NatashaNeural"
SOURCES = [
    Path("/home/fields/Fields_Orchestrator/11_House_Mini_Site"),
    Path("/home/fields/Fields_Orchestrator/12_Marketing"),
]
OUT_ROOT = Path("/home/fields/audio_library")
TOKEN = (OUT_ROOT / ".token").read_text().strip()
MP3_DIR = OUT_ROOT / "mp3" / TOKEN
INDEX_FILE = OUT_ROOT / "index.json"
FEED_FILE = MP3_DIR / "feed.xml"
FEED_BASE_URL = f"https://vm.fieldsestate.com.au/audio/{TOKEN}"

# Skip patterns — only top-level index READMEs and index/not-found files
SKIP_PATHS = {
    "/home/fields/Fields_Orchestrator/12_Marketing/README.md",
    "/home/fields/Fields_Orchestrator/11_House_Mini_Site/README.md",
}
SKIP_NAMES = {"_NOT_FOUND.md", "_PAPERS_INDEX.md"}
MIN_CHARS = 400  # skip tiny stub files


def clean_markdown(text: str) -> str:
    """Strip markdown syntax so TTS reads natural prose."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)  # code blocks
    text = re.sub(r"`([^`]+)`", r"\1", text)                  # inline code
    text = re.sub(r"!\[.*?\]\([^)]+\)", "", text)             # images
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)      # links → text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE) # heading marks
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE) # bullets
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)            # bold
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)   # italic
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)  # table rows
    text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)    # hr
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(path: Path) -> str:
    """Extract text from PDF, clean up academic-paper artefacts."""
    try:
        text = subprocess.check_output(
            ["pdftotext", "-layout", str(path), "-"],
            stderr=subprocess.DEVNULL, timeout=120,
        ).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    # Strip references section onward — long, unreadable
    text = re.split(r"\n\s*References\s*\n", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"-\n", "", text)  # hyphenated line breaks
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def title_for(path: Path) -> str:
    name = path.stem
    parent = path.parent.name
    if path.suffix == ".pdf":
        return name.replace("_", " ")
    if name in ("00_book_extract",):
        return f"{parent.replace('_', ' ')} — Book Extract"
    if name in ("references",):
        return f"{parent.replace('_', ' ')} — References"
    return name.replace("_", " ").replace("-", " ")


def collect_docs():
    docs = []
    for root in SOURCES:
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".md", ".pdf"):
                continue
            if p.name in SKIP_NAMES:
                continue
            if str(p) in SKIP_PATHS:
                continue
            docs.append(p)
    return docs


def load_index():
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text())
    return {}


def save_index(idx):
    INDEX_FILE.write_text(json.dumps(idx, indent=2))


async def synth(text: str, out_path: Path):
    comm = edge_tts.Communicate(text, VOICE)
    await comm.save(str(out_path))


def build_text(path: Path) -> str:
    if path.suffix == ".pdf":
        body = extract_pdf(path)
    else:
        body = clean_markdown(path.read_text(encoding="utf-8", errors="ignore"))
    if len(body) < MIN_CHARS:
        return ""
    # Cap very long docs — edge-tts handles long input but huge papers slow things down
    # 60K chars ≈ ~70 min audio, plenty per file
    if len(body) > 60000:
        body = body[:60000] + "\n\n... document truncated for audio."
    preamble = f"{title_for(path)}. From {path.parent.name}.\n\n"
    return preamble + body


def file_id(path: Path, text: str) -> tuple[str, str]:
    """Stable filename based on path + content hash for cache invalidation."""
    rel = path.relative_to(path.parents[len(path.parents) - 2])
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(rel)).strip("_")[:80]
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return slug, h


def generate_feed(entries):
    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title("Fields Strategy & Research")
    fg.link(href=FEED_BASE_URL + "/feed.xml", rel="self")
    fg.link(href="https://fieldsestate.com.au", rel="alternate")
    fg.description("Internal strategy docs, marketing research, and academic papers — audio.")
    fg.language("en-AU")
    fg.author({"name": "Fields Estate", "email": "will@fieldsestate.com.au"})
    fg.podcast.itunes_category("Business")
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_author("Fields Estate")

    for e in entries:
        fe = fg.add_entry()
        fe.id(e["url"])
        fe.title(e["title"])
        fe.description(e["source"])
        fe.enclosure(e["url"], str(e["size"]), "audio/mpeg")
        fe.published(e["pub"])
    fg.rss_file(str(FEED_FILE))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Only process N files (test mode)")
    ap.add_argument("--feed-only", action="store_true", help="Regenerate feed from existing MP3s")
    args = ap.parse_args()

    MP3_DIR.mkdir(parents=True, exist_ok=True)
    index = load_index()
    docs = collect_docs()
    print(f"Found {len(docs)} source files. Existing in index: {len(index)}.")

    if args.feed_only:
        entries = sorted(index.values(), key=lambda e: e["pub"], reverse=True)
        generate_feed(entries)
        print(f"Wrote feed: {FEED_FILE}")
        return

    processed = 0
    for i, p in enumerate(docs, 1):
        if args.limit and processed >= args.limit:
            break
        text = build_text(p)
        if not text:
            continue
        slug, h = file_id(p, text)
        mp3_name = f"{slug}__{h}.mp3"
        mp3_path = MP3_DIR / mp3_name
        key = str(p)
        cached = index.get(key)
        if cached and cached["filename"] == mp3_name and mp3_path.exists():
            continue
        print(f"[{i}/{len(docs)}] {p.name} ({len(text):,} chars) → {mp3_name}")
        try:
            await synth(text, mp3_path)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue
        # Clean up old version if hash changed
        if cached and cached["filename"] != mp3_name:
            old = MP3_DIR / cached["filename"]
            if old.exists():
                old.unlink()
        size = mp3_path.stat().st_size
        index[key] = {
            "title": title_for(p),
            "source": str(p),
            "filename": mp3_name,
            "url": f"{FEED_BASE_URL}/{mp3_name}",
            "size": size,
            "pub": format_datetime(datetime.now(timezone.utc)),
        }
        save_index(index)
        processed += 1

    entries = sorted(index.values(), key=lambda e: e["pub"], reverse=True)
    generate_feed(entries)
    print(f"\nDone. {processed} new MP3s. Total in feed: {len(entries)}.")
    print(f"Feed URL: {FEED_BASE_URL}/feed.xml")


if __name__ == "__main__":
    asyncio.run(main())
