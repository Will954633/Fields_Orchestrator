#!/usr/bin/env python3
"""
Build curated audio podcast from hand-written episode scripts.

Reads .txt files from /home/fields/audio_library/scripts/, generates one MP3
per script using edge-tts en-AU-NatashaNeural, writes podcast RSS feed.
Filename pattern: NN_title.txt (NN = 2-digit order prefix).
"""
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path

import edge_tts
from feedgen.feed import FeedGenerator

VOICE = "en-AU-NatashaNeural"
ROOT = Path("/home/fields/audio_library")
SCRIPTS_DIR = ROOT / "scripts"
TOKEN = (ROOT / ".token").read_text().strip()
MP3_DIR = ROOT / "mp3" / TOKEN
FEED_FILE = MP3_DIR / "feed.xml"
FEED_BASE_URL = f"https://vm.fieldsestate.com.au/audio/{TOKEN}"


async def synth(text: str, out_path: Path):
    comm = edge_tts.Communicate(text, VOICE, rate="+0%")
    await comm.save(str(out_path))


def title_from(path: Path) -> str:
    name = re.sub(r"^\d+_", "", path.stem).replace("_", " ").replace("-", " ")
    return name


async def process(path: Path, base_pub: datetime, idx: int):
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    mp3_name = path.stem + ".mp3"
    mp3_path = MP3_DIR / mp3_name
    print(f"  → {path.name} ({len(text):,} chars)")
    await synth(text, mp3_path)
    pub = base_pub - timedelta(minutes=idx)  # earlier episodes get later pub so newer apps order ascending
    return {
        "title": title_from(path),
        "filename": mp3_name,
        "url": f"{FEED_BASE_URL}/{mp3_name}",
        "size": mp3_path.stat().st_size,
        "pub": format_datetime(pub),
        "order": idx,
        "desc": text[:300].replace("\n", " ") + "...",
    }


def build_feed(entries):
    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title("Fields Estate — Strategy & Research")
    fg.link(href=f"{FEED_BASE_URL}/feed.xml", rel="self")
    fg.link(href="https://fieldsestate.com.au", rel="alternate")
    fg.description("Synthesised audio of the Fields property-research library: academic papers, mini-site strategy, and applied marketing thinking. Narrated by Claude (Opus 4.7).")
    fg.language("en-AU")
    fg.author({"name": "Fields Estate", "email": "will@fieldsestate.com.au"})
    fg.podcast.itunes_category("Business")
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_author("Fields Estate")
    fg.podcast.itunes_summary("Audio briefing of Fields' property research library — academic papers in plain language, with applied marketing implications.")
    for e in sorted(entries, key=lambda x: x["order"]):
        fe = fg.add_entry()
        fe.id(e["url"])
        fe.title(f"Episode {e['order']:02d} — {e['title']}")
        fe.description(e["desc"])
        fe.enclosure(e["url"], str(e["size"]), "audio/mpeg")
        fe.published(e["pub"])
    fg.rss_file(str(FEED_FILE))


async def main():
    MP3_DIR.mkdir(parents=True, exist_ok=True)
    scripts = sorted(SCRIPTS_DIR.glob("*.txt"))
    if not scripts:
        print("No scripts found.")
        return
    print(f"Found {len(scripts)} scripts to render.")
    base_pub = datetime.now(timezone.utc)
    # Render in parallel batches of 4 to avoid throttling edge-tts
    entries = []
    batch_size = 4
    for i in range(0, len(scripts), batch_size):
        batch = scripts[i:i+batch_size]
        results = await asyncio.gather(*[
            process(p, base_pub, i + j + 1)
            for j, p in enumerate(batch)
        ])
        entries.extend([r for r in results if r])
        print(f"Batch {i//batch_size + 1} done ({len(entries)}/{len(scripts)})")
    build_feed(entries)
    (ROOT / "index.json").write_text(json.dumps(entries, indent=2))
    total_size = sum(e["size"] for e in entries)
    print(f"\nDone. {len(entries)} MP3s, {total_size/1e6:.1f} MB total.")
    print(f"Feed: {FEED_BASE_URL}/feed.xml")


if __name__ == "__main__":
    asyncio.run(main())
