#!/usr/bin/env python3
"""
Extract all available data from a YouTube video without needing the Data API.

Layers:
  1. Metadata + stats + (optional) comments  -> yt-dlp
  2. Transcript (timestamped + plain text)   -> youtube-transcript-api

Usage:
  python3 scripts/extract_youtube.py https://www.youtube.com/watch?v=bQ6agzsoaNs
  python3 scripts/extract_youtube.py bQ6agzsoaNs --comments --out video.json
  python3 scripts/extract_youtube.py bQ6agzsoaNs --transcript-only

Requires (already installed in /home/fields/venv):
  pip install yt-dlp youtube-transcript-api
"""
import argparse
import json
import re
import subprocess
import sys


def parse_video_id(s: str) -> str:
    """Accept a bare 11-char ID or any YouTube URL form."""
    s = s.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = re.search(r"(?:v=|/shorts/|/embed/|youtu\.be/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    raise ValueError(f"Could not parse a video ID from: {s!r}")


def get_metadata(video_id: str, with_comments: bool) -> dict:
    """Pull full metadata (and optionally comments) via yt-dlp's JSON dump."""
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--dump-single-json",
        "--no-warnings",
    ]
    if with_comments:
        cmd += ["--write-comments"]
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {proc.stderr.strip()[:500]}")
    raw = json.loads(proc.stdout)

    # Keep the fields that matter; drop the giant format/url lists.
    keep = [
        "id", "title", "description", "channel", "channel_id", "channel_url",
        "uploader", "uploader_id", "upload_date", "timestamp", "duration",
        "duration_string", "view_count", "like_count", "comment_count",
        "average_rating", "categories", "tags", "chapters", "thumbnail",
        "webpage_url", "availability", "age_limit", "live_status", "language",
    ]
    meta = {k: raw.get(k) for k in keep if k in raw}
    if with_comments:
        meta["comments"] = raw.get("comments") or []
    return meta


def get_transcript(video_id: str, languages=("en", "en-US", "en-GB")) -> dict:
    """Fetch the transcript via youtube-transcript-api (1.x instance API)."""
    from youtube_transcript_api import (
        YouTubeTranscriptApi,
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
    )

    api = YouTubeTranscriptApi()
    try:
        # list() lets us report what tracks exist and prefer manual over auto.
        tlist = api.list(video_id)
        available = [
            {
                "language": t.language,
                "language_code": t.language_code,
                "is_generated": t.is_generated,
                "is_translatable": t.is_translatable,
            }
            for t in tlist
        ]
        try:
            transcript = tlist.find_manually_created_transcript(list(languages))
        except NoTranscriptFound:
            transcript = tlist.find_transcript(list(languages))
        fetched = transcript.fetch()
        snippets = [
            {"start": s.start, "duration": s.duration, "text": s.text}
            for s in fetched
        ]
        return {
            "available_tracks": available,
            "language_code": transcript.language_code,
            "is_generated": transcript.is_generated,
            "segments": snippets,
            "text": " ".join(s["text"] for s in snippets),
        }
    except (TranscriptsDisabled, NoTranscriptFound):
        return {"error": "no transcript / captions disabled for this video"}
    except VideoUnavailable:
        return {"error": "video unavailable"}
    except Exception as e:  # network block, PoToken, etc.
        return {"error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser(description="Extract data from a YouTube video.")
    ap.add_argument("video", help="Video URL or 11-char ID")
    ap.add_argument("--comments", action="store_true", help="Also scrape comments (slow)")
    ap.add_argument("--transcript-only", action="store_true", help="Skip metadata")
    ap.add_argument("--out", help="Write JSON to this path instead of stdout")
    args = ap.parse_args()

    video_id = parse_video_id(args.video)
    result = {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}

    if not args.transcript_only:
        try:
            result["metadata"] = get_metadata(video_id, args.comments)
        except Exception as e:
            result["metadata"] = {"error": str(e)}

    result["transcript"] = get_transcript(video_id)

    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        seg = result["transcript"].get("segments")
        print(f"Wrote {args.out}", file=sys.stderr)
        print(f"  title: {result.get('metadata', {}).get('title', 'n/a')}", file=sys.stderr)
        print(f"  transcript: {len(seg) if seg else 0} segments", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
