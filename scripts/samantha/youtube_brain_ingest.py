#!/usr/bin/env python3
"""
YouTube channel -> transcript -> Brain 1 units.

Three stages, each independently resumable and each safe to re-run:

  discover     list a channel's videos and register the new ones   (direct, no proxy)
  transcribe   fetch captions for registered videos                (via Bright Data)
  chunk        write transcribed videos out as Brain 1 batch files (local)

State lives in `system_monitor.youtube_videos`, one document per video, keyed on
the 11-char YouTube id. `status` walks pending -> transcribed -> chunked, and a
video that fails transcription records the reason and is retried on the next run
up to MAX_ATTEMPTS.

Usage
-----
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a

    python3 scripts/samantha/youtube_brain_ingest.py discover
    python3 scripts/samantha/youtube_brain_ingest.py transcribe --limit 25
    python3 scripts/samantha/youtube_brain_ingest.py chunk
    python3 scripts/samantha/youtube_brain_ingest.py status

Then annotate and rebuild the unified graph:

    python3 scripts/samantha/brain1_annotate.py --base /home/fields/brain1_yt
    python3 scripts/samantha/brain1_graph.py \
        --in /home/fields/brain1_build/annotations.jsonl \
        --merge /home/fields/brain1_yt/annotations.jsonl \
        --outdir /home/fields/brain1_build

WHY THE PROXY
-------------
YouTube blocks this VM's GCP IP for anything that touches the video player:
`youtube-transcript-api` returns RequestBlocked and `yt-dlp` on a watch URL gets
"Sign in to confirm you're not a bot". Channel *tab* listings are not blocked,
which is why discover runs direct and only transcribe pays for Bright Data.
Captions are recovered by fetching the watch page through Web Unlocker, reading
`captionTracks` out of the embedded player response, and fetching the timedtext
URL through the same route.

UNIT IDS
--------
Units are numbered from U_ID_BASE (900000) as `u900000`, `u900001`, ... The `u`
prefix is deliberate: `brain1_deep.py`'s citation regex only recognises u/k/i
ids, so a `y`-prefixed namespace would make every YouTube citation invisible to
the verifier. 900000 sits far above the ~3,071 units of the original corpus, so
the two namespaces cannot collide.
"""

import argparse
import glob
import html as html_mod
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

import yaml  # noqa: E402

from shared.env import load_env  # noqa: E402
from shared.db import get_client  # noqa: E402
from job_status import job_run  # noqa: E402

CONFIG = "/home/fields/Fields_Orchestrator/config/youtube_channels.yaml"
YT_BASE = "/home/fields/brain1_yt"
BATCH_DIR = f"{YT_BASE}/batches"
TRANSCRIPT_DIR = f"{YT_BASE}/transcripts"

U_ID_BASE = 900_000
WORDS_PER_UNIT = 1200      # brain1_annotate truncates a unit at 1500 words
UNITS_PER_BATCH = 10       # matches the original corpus build
MAX_ATTEMPTS = 3           # transcription attempts before a video is given up on
MIN_TRANSCRIPT_WORDS = 150  # below this it is a trailer/short, not a teaching unit
MAX_DEFERRALS = 8          # premiere re-checks before it counts as a real failure

# A handful of genuinely unplayable videos (private, removed, region-locked) is
# normal and must not hold the job red forever. A caption *outage* looks nothing
# like that: it retires whole swathes of the corpus. Alert on the shape of the
# second, not the first — a floor so a small corpus cannot trip on noise, and a
# share so the threshold scales as the corpus grows.
GIVE_UP_ALERT_FLOOR = 10   # never alert below this many given-up videos
GIVE_UP_ALERT_SHARE = 0.05  # ...nor below this share of everything registered


def _log(msg):
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}", flush=True)


def _coll():
    return get_client()["system_monitor"]["youtube_videos"]


def _channels():
    with open(CONFIG) as f:
        return yaml.safe_load(f)["channels"]


# --------------------------------------------------------------------------- #
# stage 1: discover
# --------------------------------------------------------------------------- #

def discover(only_library=None):
    """List each channel's videos via yt-dlp and register the ones we haven't seen.

    Uses --flat-playlist, which reads the channel tab and never touches a video
    player, so it works from this IP without the proxy.
    """
    import subprocess

    coll = _coll()
    registered = 0
    seen_total = 0
    per_channel = {}

    for ch in _channels():
        if only_library and ch["library"] != only_library:
            continue
        url = f"https://www.youtube.com/channel/{ch['channel_id']}/videos"
        _log(f"discover: {ch['library']} <- {url}")
        proc = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--dump-json", "--no-warnings",
             "--playlist-end", str(ch.get("max_backfill", 250)), url],
            capture_output=True, text=True, timeout=900,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"yt-dlp failed for {ch['library']}: {proc.stderr.strip()[:300]}")

        entries = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        # Rule 7b: yt-dlp exits 0 on a channel tab it could read but that yielded
        # nothing (bot check, channel restructure, id changed). That is a failure
        # to list, not an empty channel — and because seen_total is a SUM, one
        # dead channel is otherwise fully masked by the other still working.
        if not entries:
            raise RuntimeError(
                f"listed 0 videos for {ch['library']} ({url}) — yt-dlp exited 0 "
                f"but returned nothing; the channel tab is not readable")
        seen_total += len(entries)
        per_channel[ch["library"]] = len(entries)
        _log(f"  {len(entries)} videos listed")

        for e in entries:
            vid = e.get("id")
            if not vid or len(vid) != 11:
                continue
            doc = {
                "video_id": vid,
                "library": ch["library"],
                "country": ch.get("country", ""),
                "channel_id": ch["channel_id"],
                "title": e.get("title"),
                "duration": e.get("duration"),
                "view_count": e.get("view_count"),
                "url": e.get("url") or f"https://www.youtube.com/watch?v={vid}",
                "discovered_at": datetime.now(timezone.utc),
            }
            res = coll.update_one(
                {"video_id": vid},
                {"$setOnInsert": {**doc, "status": "pending", "attempts": 0}},
                upsert=True,
            )
            if res.upserted_id is not None:
                registered += 1

    if not per_channel:
        raise RuntimeError(
            f"no channel matched --library {only_library!r} in {CONFIG}")

    # Per-channel counts alongside the sum: the sum alone cannot show which
    # channel contributed, so a channel that quietly drops to a fraction of its
    # listing is invisible in `channels_listed` while the total still looks fine.
    out = {"channels_listed": seen_total, "newly_registered": registered}
    for lib, n in per_channel.items():
        out[f"listed_{re.sub(r'[^a-z0-9]+', '_', lib.lower()).strip('_')}"] = n
    return out


# --------------------------------------------------------------------------- #
# stage 2: transcribe
# --------------------------------------------------------------------------- #

PREFERRED_LANGS = ["en", "en-AU", "en-US", "en-GB"]

# youtube_transcript_api reports an unreleased premiere as VideoUnplayable with
# the scheduled reason in the message ("Premieres in 2 days", "Live in 3 hours").
_PREMIERE_RE = re.compile(r"premieres? in |live in |premiere will begin",
                          re.IGNORECASE)

_proxy_pw_cache = {}


def _proxy_url(session_tag):
    """Bright Data Web Unlocker, addressed through its PROXY interface.

    Not the /request API: `youtube-transcript-api` needs the watch page and the
    timedtext call to share one egress identity, because the timedtext URL is
    signed with an `ei`/`expire` pair bound to the session that issued it. A
    rotating per-request IP yields HTTP 200 with a zero-byte body — which is
    exactly what the /request API produced before this was understood.

    `-session-<tag>` pins one exit IP for the life of the tag.
    """
    import requests

    key = os.environ["BRIGHTDATA_API_KEY"]
    zone = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker2")
    if zone not in _proxy_pw_cache:
        r = requests.get(f"https://api.brightdata.com/zone/passwords?zone={zone}",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        r.raise_for_status()
        _proxy_pw_cache[zone] = r.json()["passwords"][0]
        c = requests.get("https://api.brightdata.com/status",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        _proxy_pw_cache["_customer"] = c.json().get("customer", "fieldsestate")
    cust = _proxy_pw_cache["_customer"]
    return (f"http://brd-customer-{cust}-zone-{zone}-session-{session_tag}"
            f":{_proxy_pw_cache[zone]}@brd.superproxy.io:33335")


def _fetch_transcript(video_id, session_tag):
    """Return (text, language_code, is_generated) or raise."""
    import requests
    import urllib3
    from youtube_transcript_api import YouTubeTranscriptApi

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    sess = requests.Session()
    # Web Unlocker terminates TLS with its own CA, so the chain cannot verify
    # against the system store. The traffic is YouTube captions — public data,
    # no credentials — so the exposure of not verifying is a corrupted
    # transcript, which the word-count gate below would catch anyway.
    sess.verify = False
    p = _proxy_url(session_tag)
    sess.proxies = {"http": p, "https": p}

    api = YouTubeTranscriptApi(http_client=sess)
    tlist = api.list(video_id)
    try:
        track = tlist.find_manually_created_transcript(PREFERRED_LANGS)
    except Exception:
        track = tlist.find_transcript(PREFERRED_LANGS)
    fetched = track.fetch()
    text = re.sub(r"\s+", " ", " ".join(s.text for s in fetched)).strip()
    if not text:
        raise RuntimeError("transcript fetched but empty")
    return text, track.language_code, track.is_generated


def _transcribe_one(doc, session_tag):
    """Worker body. Returns (doc, outcome, payload) — never raises."""
    try:
        text, lang, is_asr = _fetch_transcript(doc["video_id"], session_tag)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"[:300]
        # A scheduled premiere is not a failure to fetch — the video does not
        # exist yet. Charging it an attempt retires it after MAX_ATTEMPTS runs,
        # so a video that premieres later is dropped from the corpus for good,
        # and the retired stubs pile into the given-up count that gates the
        # bulk-outage alert. Defer instead: no attempt spent, retried next run.
        if _PREMIERE_RE.search(msg):
            return doc, "not_yet_released", msg
        return doc, "error", msg
    words = len(text.split())
    if words < MIN_TRANSCRIPT_WORDS:
        return doc, "short", words
    return doc, "ok", (text, lang, is_asr, words)


def transcribe(limit=25, only_library=None, workers=6):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    coll = _coll()
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

    q = {"status": "pending", "attempts": {"$lt": MAX_ATTEMPTS}}
    if only_library:
        q["library"] = only_library
    # Longest first: a 60-minute session carries far more method than a 40-second clip.
    todo = list(coll.find(q).sort("duration", -1).limit(limit))
    _log(f"transcribe: {len(todo)} videos queued (limit {limit}, {workers} workers)")

    ok = failed = skipped_short = deferred = 0
    errors = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            # One sticky session per slot, reused across that slot's videos: a
            # fresh exit IP per video would spend the proxy's session pool for
            # no benefit, since the signing only has to hold within a video.
            pool.submit(_transcribe_one, doc, f"yt{i % workers:02d}"): doc
            for i, doc in enumerate(todo)
        }
        for fut in as_completed(futures):
            doc, outcome, payload = fut.result()
            vid = doc["video_id"]
            done += 1
            tag = f"  [{done}/{len(todo)}] {vid} {(doc.get('title') or '')[:60]}"

            if outcome == "not_yet_released":
                deferred += 1
                # Bounded: a premiere that is cancelled rather than aired would
                # otherwise defer forever and never be counted as anything.
                if doc.get("deferrals", 0) + 1 >= MAX_DEFERRALS:
                    coll.update_one({"video_id": vid},
                                    {"$inc": {"attempts": 1, "deferrals": 1},
                                     "$set": {"last_error": payload,
                                              "last_attempt_at": datetime.now(timezone.utc)}})
                    _log(f"{tag}\n      deferred {MAX_DEFERRALS}x — now counting attempts")
                else:
                    coll.update_one({"video_id": vid},
                                    {"$inc": {"deferrals": 1},
                                     "$set": {"last_error": payload,
                                              "last_attempt_at": datetime.now(timezone.utc)}})
                    _log(f"{tag}\n      not released yet — deferred, no attempt spent")
            elif outcome == "error":
                failed += 1
                errors.append(f"{vid}: {payload}")
                _log(f"{tag}\n      FAIL {payload}")
                coll.update_one({"video_id": vid},
                                {"$inc": {"attempts": 1},
                                 "$set": {"last_error": payload,
                                          "last_attempt_at": datetime.now(timezone.utc)}})
            elif outcome == "short":
                skipped_short += 1
                coll.update_one({"video_id": vid},
                                {"$set": {"status": "skipped_short",
                                          "word_count": payload}})
                _log(f"{tag}\n      skipped — {payload} words")
            else:
                text, lang, is_asr, words = payload
                path = f"{TRANSCRIPT_DIR}/{vid}.txt"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                coll.update_one({"video_id": vid}, {
                    "$set": {"status": "transcribed", "word_count": words,
                             "language_code": lang, "is_generated": is_asr,
                             "transcript_path": path, "last_error": None,
                             "transcribed_at": datetime.now(timezone.utc)},
                })
                ok += 1
                _log(f"{tag}\n      OK — {words:,} words "
                     f"({lang}{', auto' if is_asr else ''})")

    # Rule 7b: videos that burn through MAX_ATTEMPTS keep status "pending" but
    # fall out of the query above forever — never retried, never counted, never
    # reported. A sustained caption outage therefore raises for MAX_ATTEMPTS runs
    # per video and then goes permanently silent with a growing pile of stuck
    # documents. Count them every run so the pile is visible while it grows.
    gq = {"status": "pending", "attempts": {"$gte": MAX_ATTEMPTS}}
    if only_library:
        gq["library"] = only_library
    given_up = coll.count_documents(gq)
    registered_total = coll.count_documents(
        {"library": only_library} if only_library else {})

    return {"attempted": len(todo), "transcribed": ok,
            "failed": failed, "skipped_short": skipped_short,
            "deferred": deferred,
            "given_up": given_up, "registered_total": registered_total,
            "errors": errors[:10]}


# --------------------------------------------------------------------------- #
# stage 3: chunk into Brain 1 batch files
# --------------------------------------------------------------------------- #

def _next_unit_number(coll):
    """Resume after whatever the last chunk run allocated."""
    top = coll.find_one({"unit_ids": {"$exists": True, "$ne": []}},
                        sort=[("last_unit_number", -1)])
    if top and top.get("last_unit_number"):
        return top["last_unit_number"] + 1
    return U_ID_BASE


def _next_batch_index():
    existing = glob.glob(f"{BATCH_DIR}/yt_*.txt")
    if not existing:
        return 0
    return max(int(re.search(r"yt_(\d+)\.txt", p).group(1)) for p in existing) + 1


def chunk(only_library=None):
    """Turn transcribed videos into `===== UNIT uNNNNNN | LIB: X =====` batch files.

    Format is byte-compatible with the original corpus batches so
    `brain1_annotate.py --base /home/fields/brain1_yt` needs no special casing.
    """
    coll = _coll()
    os.makedirs(BATCH_DIR, exist_ok=True)

    q = {"status": "transcribed"}
    if only_library:
        q["library"] = only_library
    todo = list(coll.find(q).sort("video_id", 1))
    _log(f"chunk: {len(todo)} transcribed videos to unitise")
    if not todo:
        return {"videos": 0, "units": 0, "batches": 0}

    unit_no = _next_unit_number(coll)
    batch_no = _next_batch_index()
    pending_units, batches_written, total_units = [], 0, 0

    def flush():
        nonlocal pending_units, batch_no, batches_written
        if not pending_units:
            return
        path = f"{BATCH_DIR}/yt_{batch_no:04d}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(pending_units))
        batch_no += 1
        batches_written += 1
        pending_units = []

    for doc in todo:
        text = open(doc["transcript_path"], encoding="utf-8").read()
        words = text.split()
        chunks = [" ".join(words[i:i + WORDS_PER_UNIT])
                  for i in range(0, len(words), WORDS_PER_UNIT)]
        ids = []
        for n, body in enumerate(chunks, 1):
            uid = f"u{unit_no}"
            unit_no += 1
            ids.append(uid)
            # The market goes in the header because the annotator sees ONLY the
            # header and the text. Without it, a US postage figure and an AU one
            # annotate identically and the graph cannot tell them apart later.
            header = (f"Channel: {doc['library']} | Market: "
                      f"{doc.get('country') or 'unknown'} "
                      f"| Video: {doc.get('title') or ''} "
                      f"| Part {n} of {len(chunks)} | {doc['url']}")
            pending_units.append(
                f"===== UNIT {uid} | LIB: {doc['library']} =====\n"
                f"HEADER: {header}\n"
                f"TEXT: {header} {body}\n"
            )
            total_units += 1
            if len(pending_units) >= UNITS_PER_BATCH:
                flush()
        coll.update_one({"video_id": doc["video_id"]},
                        {"$set": {"status": "chunked", "unit_ids": ids,
                                  "last_unit_number": unit_no - 1,
                                  "chunked_at": datetime.now(timezone.utc)}})
    flush()
    return {"videos": len(todo), "units": total_units, "batches": batches_written}


# --------------------------------------------------------------------------- #

def status():
    coll = _coll()
    pipeline = [{"$group": {"_id": {"library": "$library", "status": "$status"},
                            "n": {"$sum": 1},
                            "words": {"$sum": "$word_count"}}},
                {"$sort": {"_id.library": 1, "_id.status": 1}}]
    rows = list(coll.aggregate(pipeline))
    if not rows:
        print("no videos registered yet — run `discover`")
        return {}
    print(f"{'library':<16}{'status':<18}{'videos':>8}{'words':>12}")
    for r in rows:
        print(f"{r['_id']['library']:<16}{r['_id']['status']:<18}"
              f"{r['n']:>8}{(r.get('words') or 0):>12,}")
    batches = len(glob.glob(f"{BATCH_DIR}/yt_*.txt"))
    print(f"\nbatch files written: {batches}  ({BATCH_DIR})")
    ann = f"{YT_BASE}/annotations.jsonl"
    if os.path.exists(ann):
        print(f"annotated units:     {sum(1 for _ in open(ann))}  ({ann})")
    else:
        print("annotated units:     0 — run brain1_annotate.py --base " + YT_BASE)
    return {"rows": len(rows)}


# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["discover", "transcribe", "chunk", "status", "all"])
    ap.add_argument("--limit", type=int, default=25,
                    help="videos to transcribe this run (each costs Bright Data traffic)")
    ap.add_argument("--workers", type=int, default=6,
                    help="concurrent transcript fetches")
    ap.add_argument("--library", help="restrict to one library from the config")
    ap.add_argument("--no-heartbeat", action="store_true",
                    help="skip the job_run heartbeat (ad-hoc/manual runs)")
    args = ap.parse_args()

    load_env()

    if args.stage == "status":
        status()
        return

    def run_stage(beat=None):
        if args.stage in ("discover", "all"):
            r = discover(args.library)
            _log(f"discover: {r}")
            if beat:
                beat.metrics = {**(beat.metrics or {}), **{f"discover_{k}": v
                                                           for k, v in r.items()}}
        if args.stage in ("transcribe", "all"):
            r = transcribe(args.limit, args.library, args.workers)
            _log(f"transcribe: {r}")
            if beat:
                beat.metrics = {**(beat.metrics or {}),
                                **{f"transcribe_{k}": v for k, v in r.items()
                                   if k != "errors"}}
            # Rule 7b: a run that attempted work and transcribed nothing is a
            # failure, not an empty queue. Silence here would look identical to
            # "all caught up" while Bright Data or the caption format was broken.
            # Deferred premieres are excluded: they are not attempts that could
            # have succeeded, so a queue holding only unreleased videos is "no
            # work to do", not "could not do the work".
            real_attempts = r["attempted"] - r["deferred"]
            if real_attempts > 0 and r["transcribed"] == 0:
                raise RuntimeError(
                    f"attempted {real_attempts} available videos, transcribed 0 "
                    f"— first errors: {r['errors'][:3]}")
            # Rule 7b, second path: the check above only fires while videos are
            # still inside their MAX_ATTEMPTS budget. Once an outage exhausts
            # them they leave the queue and `attempted` falls to 0, so the run
            # goes green while the corpus quietly stops growing. This fires on
            # the pile they leave behind, which does not drain on its own.
            gate = max(GIVE_UP_ALERT_FLOOR,
                       int(r["registered_total"] * GIVE_UP_ALERT_SHARE))
            if r["given_up"] >= gate:
                raise RuntimeError(
                    f"{r['given_up']} of {r['registered_total']} registered "
                    f"videos have exhausted {MAX_ATTEMPTS} attempts and will "
                    f"never be retried (alert threshold {gate}) — captions are "
                    f"failing in bulk, not video-by-video")
        if args.stage in ("chunk", "all"):
            r = chunk(args.library)
            _log(f"chunk: {r}")
            if beat:
                beat.metrics = {**(beat.metrics or {}), **{f"chunk_{k}": v
                                                           for k, v in r.items()}}
                beat.detail = (f"{r['videos']} videos -> {r['units']} units "
                               f"in {r['batches']} batches")

    if args.no_heartbeat:
        run_stage()
    else:
        with job_run("youtube_brain_ingest", cadence_hours=168,
                     title="YouTube -> Brain 1 ingestion") as beat:
            beat.metrics = {}
            run_stage(beat)


if __name__ == "__main__":
    main()
