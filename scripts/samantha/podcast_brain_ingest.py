#!/usr/bin/env python3
"""
Podcast RSS -> audio -> transcript -> Brain 1 units.

Three stages, each independently resumable and each safe to re-run:

  discover     read a show's RSS feed and register the new episodes   (direct)
  transcribe   pull audio, segment it, ASR each segment via Vertex    (Gemini)
  chunk        write transcribed episodes out as Brain 1 batch files  (local)

State lives in `system_monitor.podcast_episodes`, one document per episode,
keyed on the feed's GUID. `status` walks pending -> transcribed -> chunked, and
an episode that fails records the reason and is retried on the next run up to
MAX_ATTEMPTS.

Usage
-----
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a

    python3 scripts/samantha/podcast_brain_ingest.py discover
    python3 scripts/samantha/podcast_brain_ingest.py transcribe --limit 5
    python3 scripts/samantha/podcast_brain_ingest.py chunk
    python3 scripts/samantha/podcast_brain_ingest.py status

Then annotate and let the nightly rebuild pick it up:

    python3 scripts/samantha/brain1_annotate.py --base /home/fields/brain1_build/Spotify

WHY RSS AND NOT SPOTIFY
-----------------------
Spotify publishes no transcript API and its show pages are a JS app behind bot
protection. Every Spotify-hosted show, however, also serves an open RSS feed
with the complete episode list and a direct, unauthenticated audio enclosure.
The feed is the authoritative source anyway: it carries the real publish date,
duration and episode description, which the Spotify page does not expose
cleanly. No credentials and no proxy are involved in discovery or download.

WHY GEMINI-VIA-VERTEX FOR ASR
-----------------------------
The two cheaper routes are both dead as of 2026-08-15 and were measured, not
assumed:
  * YouTube captions (the `youtube_brain_ingest.py` path) — this show is also on
    YouTube, but the VM's GCP IP is blocked by YouTube and the Bright Data
    unlocker zone now fails auth (407 / `zone_not_found`), so no caption route
    works at all right now.
  * OpenAI `gpt-4o-mini-transcribe` — the account returns
    `insufficient_quota: credit_balance_exhausted`.
Vertex bills to the GCP `fields-estate` account, which is healthy, and is the
same backend the property vision pipeline already uses. Measured ~22x realtime.

DISK
----
This VM runs at ~95% full. A 2-hour episode is ~60 MB of source audio and the
16 kHz mono re-encode is ~29 MB, so audio is downloaded, transcoded, segmented,
transcribed and DELETED one episode at a time inside a `finally`. Peak
additional disk is one episode, never the show. Transcripts (text) are what
persist.

UNIT IDS
--------
Units are numbered from U_ID_BASE (800000) as `u800000`, `u800001`, ... The `u`
prefix is deliberate: `brain1_deep.py`'s citation regex only recognises u/k/i
ids, so a `p`-prefixed namespace would make every podcast citation invisible to
the verifier. 800000 sits above the ~3,084 units of the original corpus and
below the 900000 YouTube base, so no namespace can collide.
"""

import argparse
import base64
import collections
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
import yaml

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

from shared.db import get_client   # noqa: E402
from shared.env import load_env    # noqa: E402
from job_status import job_run     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/fields/Fields_Orchestrator"
FEEDS_YAML = f"{ROOT}/config/podcast_feeds.yaml"
BASE = os.environ.get("PODCAST_BRAIN_BASE", "/home/fields/brain1_build/Spotify")

U_ID_BASE = 800_000
WORDS_PER_UNIT = 1200        # brain1_annotate truncates a unit at 1500 words
UNITS_PER_BATCH = 10         # matches the original corpus build
MIN_TRANSCRIPT_WORDS = 150   # below this it is a trailer/promo, not a teaching unit
MAX_ATTEMPTS = 3

SEGMENT_SECONDS = 600        # 10 min -> ~3,200 words -> well inside maxOutputTokens
MAX_SPLIT_DEPTH = 3          # 10min -> 5 -> 2.5 -> 1.25min before giving up
# Repetition-loop guards. Real speech measured ~1.000 unique 10-grams across 146
# episodes; the three degenerate ones came in at 0.43-0.79. Thresholds sit well
# below the healthy floor so genuine repetition (a chant, a recited list) passes.
SEGMENT_UNIQ_MIN = 0.75      # per ASR call -> triggers a split
EPISODE_UNIQ_MIN = 0.85      # whole transcript -> refuses to store
ASR_MODEL = os.environ.get("PODCAST_ASR_MODEL", "gemini-2.5-flash")
# Used only when splitting has failed at every depth. A repetition loop is a
# property of one model's decoding on one piece of audio, so a different model is
# the move once re-cutting the input has stopped working. Set empty to disable.
ASR_FALLBACK_MODEL = os.environ.get("PODCAST_ASR_FALLBACK_MODEL", "gemini-2.5-pro")
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT_ID", "fields-estate")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "global")
MIN_FREE_DISK_MB = 1500      # refuse to start an episode below this

def _asr_prompt(roster):
    """Speaker-labelled transcription, constrained to a known roster.

    Blind diarization ("Speaker A/B") is useless here: the labels cannot stay
    consistent across independently-transcribed segments, so Speaker A in segment
    3 need not be Speaker A in segment 4. Supplying the actual participant names
    solves that — the label is an identity, not a per-segment index — and it is
    also what makes the corpus answer "who said this", which for an interview
    show is the difference between a claim by the host and a claim by an invited
    expert.
    """
    names = ", ".join(roster) if roster else "(unknown — use \"Unknown:\")"
    return (
        "Transcribe this podcast audio verbatim in English.\n\n"
        f"The people speaking in this episode are, and these are the ONLY names "
        f"you may use:\n{names}\n\n"
        "Rules:\n"
        "- Output ONLY the transcript text. No preamble, no commentary, no summary.\n"
        "- Do NOT add timestamps.\n"
        "- Prefix every speaker turn with the speaker's name and a colon, "
        "e.g. \"Jane Smith: \".\n"
        "- Use ONLY names from the list above. If you cannot tell who is "
        "speaking, use \"Unknown:\". NEVER invent a name.\n"
        "- Start a new line at every speaker change.\n"
        "- Transcribe what is actually said. Do not paraphrase, summarise, tidy "
        "up or omit. If a passage is inaudible, write [inaudible].\n"
        "- If the audio contains no speech at all, output exactly: [no speech]"
    )


# Episode numbers are NOT reliably in the feed: `itunes:episode` is present on
# only 18 of the 152 Bothsides episodes, so the title is the real source. These
# cover the formats actually observed ("EP 150| ...", "EP 149 | ...",
# "... - #152", "... Jack Henderson #151", "BSOTF | Ep. 1 ...").
_EP_PATTERNS = [
    re.compile(r"\bEP\.?\s*#?\s*(\d{1,4})\b", re.I),
    re.compile(r"#\s*(\d{1,4})\b"),
    re.compile(r"\bEpisode\s+(\d{1,4})\b", re.I),
]


def _episode_number(title, item_ep=None):
    """Return an int episode number, or None. None is a legitimate answer —
    trailers and one-off specials genuinely have no number, and inventing one
    would be worse than leaving it unset."""
    if item_ep:
        try:
            return int(str(item_ep).strip())
        except (TypeError, ValueError):
            pass
    for pat in _EP_PATTERNS:
        m = pat.search(title or "")
        if m:
            return int(m.group(1))
    return None


def _log(msg):
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def _coll():
    return get_client()["system_monitor"]["podcast_episodes"]


def _feeds(only_slug=None):
    with open(FEEDS_YAML) as fh:
        feeds = (yaml.safe_load(fh) or {}).get("feeds") or []
    if only_slug:
        feeds = [f for f in feeds if f.get("slug") == only_slug]
    return feeds


def _dirs():
    for d in ("transcripts", "batches"):
        os.makedirs(f"{BASE}/{d}", exist_ok=True)


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------
_ITUNES_NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}


def _parse_duration(raw):
    """itunes:duration is either seconds, MM:SS or HH:MM:SS."""
    if not raw:
        return 0
    raw = raw.strip()
    if ":" not in raw:
        try:
            return int(float(raw))
        except ValueError:
            return 0
    parts = [int(float(p)) for p in raw.split(":")]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


def discover(only_slug=None):
    _dirs()
    coll = _coll()
    total_new = 0
    for feed in _feeds(only_slug):
        lib, slug = feed["library"], feed["slug"]
        _log(f"discover: {lib} <- {feed['rss']}")
        r = requests.get(feed["rss"], timeout=90,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; FieldsBrain/1.0)"})
        r.raise_for_status()
        items = ET.fromstring(r.content).findall("./channel/item")
        _log(f"  {len(items)} episodes in feed")
        new = 0
        for it in items[: int(feed.get("max_backfill", 500))]:
            enc = it.find("enclosure")
            if enc is None or not enc.get("url"):
                continue
            guid = (it.findtext("guid") or enc.get("url") or "").strip()
            if not guid:
                continue
            ep_id = f"{slug}:{guid}"
            if coll.count_documents({"episode_id": ep_id}, limit=1):
                continue
            pub = it.findtext("pubDate")
            try:
                pub_dt = parsedate_to_datetime(pub).astimezone(timezone.utc) if pub else None
            except Exception:
                pub_dt = None
            dur_el = it.find("itunes:duration", _ITUNES_NS)
            ep_el = it.find("itunes:episode", _ITUNES_NS)
            se_el = it.find("itunes:season", _ITUNES_NS)
            title = (it.findtext("title") or "").strip()
            coll.insert_one({
                "episode_id": ep_id,
                "guid": guid,
                "slug": slug,
                "library": lib,
                "country": feed.get("country"),
                "spotify_show": feed.get("spotify_show"),
                "title": title,
                "episode_number": _episode_number(
                    title, ep_el.text if ep_el is not None else None),
                "season": int(se_el.text) if (se_el is not None and (se_el.text or "").isdigit()) else None,
                "hosts": list(feed.get("hosts") or []),
                "description": re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:2000].strip(),
                "published_at": pub_dt,
                "duration": _parse_duration(dur_el.text if dur_el is not None else None),
                "audio_url": enc.get("url"),
                "audio_type": enc.get("type"),
                "discovered_at": datetime.now(timezone.utc),
                "status": "pending",
                "attempts": 0,
            })
            new += 1
        _log(f"  registered {new} new")
        total_new += new
    return total_new


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------
_VERTEX_CREDS = None


def _vertex_token():
    """Same credential path as shared/claude_vision.py: explicit key file if one
    is configured, else the VM metadata service account via ADC."""
    global _VERTEX_CREDS
    from google.auth.transport.requests import Request as _GARequest
    if _VERTEX_CREDS is None:
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        keyfile = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "/home/fields/.gcp-vertex-key.json"
        if os.path.exists(keyfile):
            from google.oauth2 import service_account
            _VERTEX_CREDS = service_account.Credentials.from_service_account_file(keyfile, scopes=scopes)
        else:
            import google.auth
            _VERTEX_CREDS, _ = google.auth.default(scopes=scopes)
    if not _VERTEX_CREDS.valid:
        _VERTEX_CREDS.refresh(_GARequest())
    return _VERTEX_CREDS.token


class TruncatedResponse(RuntimeError):
    """The model hit maxOutputTokens.

    Kept distinct from transient errors because it must NOT be retried as-is. The
    call is deterministic (temperature=0), so an identical retry fails identically
    — the first backfill spent four attempts per segment discovering that. The
    caller's correct response is to change the input (transcribe a shorter slice),
    not to ask again.
    """


def _vertex_generate(parts, max_tokens=32768, attempt_budget=4, model=None):
    """POST one generateContent call to Vertex, with retry on transient status."""
    model = model or ASR_MODEL
    host = ("aiplatform.googleapis.com" if VERTEX_REGION == "global"
            else f"{VERTEX_REGION}-aiplatform.googleapis.com")
    url = (f"https://{host}/v1/projects/{VERTEX_PROJECT}/locations/{VERTEX_REGION}"
           f"/publishers/google/models/{model}:generateContent")
    gen = {"maxOutputTokens": max_tokens, "temperature": 0}
    if "flash" in model:   # pro rejects thinkingBudget=0
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
    last = None
    for attempt in range(attempt_budget):
        try:
            r = requests.post(url, json=body, timeout=600, headers={
                "Authorization": f"Bearer {_vertex_token()}",
                "Content-Type": "application/json"})
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                time.sleep(min(60, 5 * (2 ** attempt)))
                continue
            r.raise_for_status()
            cand = (r.json().get("candidates") or [{}])[0]
            fr = cand.get("finishReason")
            if fr == "MAX_TOKENS":
                # A truncated response is a FAILURE, not a partial win: keeping it
                # would splice a half-transcribed segment into the corpus with no
                # signal that anything was lost. Raised out of the retry loop
                # rather than through it — see TruncatedResponse.
                raise TruncatedResponse("response truncated at maxOutputTokens")
            txt = "".join(p.get("text", "")
                          for p in (cand.get("content", {}).get("parts") or [])).strip()
            if not txt:
                raise RuntimeError(f"empty candidate (finishReason={fr})")
            return txt
        except TruncatedResponse:
            raise
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            time.sleep(min(60, 5 * (2 ** attempt)))
    raise RuntimeError(f"vertex call failed after {attempt_budget} attempts: {last}")


def _extract_guests(doc):
    """Identify the episode's guests from its title and description.

    Kept separate from the audio call on purpose: the roster has to be known
    BEFORE transcription so it can be handed to the transcriber, and title +
    description state the guest explicitly far more reliably than voice alone
    could establish a name.
    """
    hosts = doc.get("hosts") or []
    prompt = (
        "Below are a podcast episode's title and description. List the GUESTS "
        "appearing in this episode — the people interviewed, not the hosts.\n\n"
        f"Known hosts (exclude these): {', '.join(hosts) or 'none'}\n\n"
        f"TITLE: {doc.get('title')}\n\nDESCRIPTION: {doc.get('description') or ''}\n\n"
        "Reply with ONLY the guest full names, one per line. Use the name exactly "
        "as written in the text. If the episode has no guest (a solo or host-only "
        "episode), reply with exactly: NONE"
    )
    try:
        out = _vertex_generate([{"text": prompt}], max_tokens=512, attempt_budget=2)
    except Exception as e:
        _log(f"    guest extraction failed ({str(e)[:80]}) — continuing hosts-only")
        return []
    if out.strip().upper().startswith("NONE"):
        return []
    guests = []
    for line in out.splitlines():
        n = line.strip().lstrip("-*0123456789. ").strip()
        # Guard against the model returning a sentence instead of a name.
        if n and len(n) < 60 and n.upper() != "NONE" and n not in hosts:
            guests.append(n)
    return guests[:6]


class DegenerateResponse(RuntimeError):
    """The model fell into a repetition loop but finished before the token cap.

    This is the SILENT form of the truncation failure and the more dangerous one.
    A truncated response at least raises; a degenerate-but-complete response looks
    like a clean success and lands in the corpus. Measured across the first 146
    episodes: the median transcript has a 1.000 unique-10-gram ratio and three
    came back at 0.43-0.79, one of them claiming 470 words/minute of speech.

    Word rate alone does NOT catch it — a 0.584 transcript sat at a plausible-
    looking 235 wpm. n-gram uniqueness does.
    """


def _shingle_uniqueness(text, n=10):
    """Fraction of distinct n-word sequences. ~1.0 for real speech, low for a loop."""
    w = re.findall(r"\w+", text.lower())
    if len(w) < n + 200:      # too short to judge; do not fail it on noise
        return 1.0
    sh = [" ".join(w[i:i + n]) for i in range(len(w) - n)]
    return len(set(sh)) / len(sh)


def _audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, timeout=120)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _asr_segment(path, roster, context, depth=0, model=None):
    """Transcribe one audio segment with speaker labels.

    On truncation, halve the audio and recurse rather than retrying. The model
    occasionally falls into a repetition loop on a particular passage and emits
    tokens until the cap; because the call is deterministic, asking again is
    guaranteed to reproduce it. Re-cutting the audio changes the input and breaks
    the loop. Observed on 8 of 152 episodes, and NOT correlated with length — a
    162-minute episode succeeded while a 39-minute one failed.
    """
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    try:
        txt = _vertex_generate([
            {"inline_data": {"mime_type": "audio/mpeg", "data": data}},
            {"text": f"{_asr_prompt(roster)}\n\nContext (for names and jargon only, "
                     f"do not transcribe this line): {context}"},
        ], model=model)
        if txt.strip() == "[no speech]":
            return ""
        uniq = _shingle_uniqueness(txt)
        if uniq < SEGMENT_UNIQ_MIN:
            # Same disease as truncation, caught before it can pass as success.
            raise DegenerateResponse(f"repetition loop: {uniq:.2f} unique 10-grams")
        return txt
    except (TruncatedResponse, DegenerateResponse) as e:
        dur = _audio_duration(path)
        can_split = depth < MAX_SPLIT_DEPTH and dur >= 60
        if can_split:
            half = dur / 2
            _log(f"    {type(e).__name__} at {dur/60:.1f}m (depth {depth}) — splitting in half")
            try:
                out = []
                for i, (ss, t) in enumerate([(0, half), (half, dur - half)]):
                    piece = f"{path}.d{depth}p{i}.mp3"
                    subprocess.run(
                        ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{ss:.3f}",
                         "-t", f"{t:.3f}", "-i", path, "-c", "copy", piece],
                        check=True, timeout=600)
                    try:
                        out.append(_asr_segment(piece, roster, context, depth + 1, model))
                    finally:
                        if os.path.exists(piece):
                            os.remove(piece)
                return "\n\n".join(x for x in out if x)
            except (TruncatedResponse, DegenerateResponse):
                # Splitting did not rescue it. Fall through to the model swap
                # below — but only at the top, so one stubborn episode costs a
                # single pro-tier pass rather than one per failed leaf.
                if not (depth == 0 and model is None and ASR_FALLBACK_MODEL):
                    raise
        # Last resort: a DIFFERENT model. Re-cutting the audio has stopped
        # helping, but a repetition loop is a property of THIS model's decoding on
        # THIS audio; another model does not inherit it.
        if depth == 0 and model is None and ASR_FALLBACK_MODEL:
            _log(f"    unrecoverable by splitting — retrying on {ASR_FALLBACK_MODEL}")
            return _asr_segment(path, roster, context, depth=0,
                                model=ASR_FALLBACK_MODEL)
        # Give up rather than return a partial or looped transcript: a silent gap
        # (or 20 repetitions) mid-episode is worse than a visibly failed episode.
        raise


def _canonical_speakers(text, roster):
    """Normalise speaker labels to canonical roster names; report who spoke.

    Two things go wrong if labels are taken at face value. The transcriber drifts
    between "Daniel" and "Daniel Beardall" across segments, which would enter the
    graph as two different people. And a naive `^(.+):` sweep also matches any
    line that merely contains a colon — an observed run produced speakers named
    "8, 8" and a fragment of a sentence.

    So a label counts as a speaker ONLY if it resolves to a roster name (full
    name or unambiguous first name). Everything else is left as ordinary text.
    `roster` entries arrive as "Full Name (host)".
    """
    names = [re.sub(r"\s*\((host|guest)\)$", "", r).strip() for r in roster]
    names = [n for n in names if n]
    lookup = {n.lower(): n for n in names}
    first_counts = collections.Counter(n.split()[0].lower() for n in names)
    for n in names:  # a first name only resolves if it is unambiguous
        f = n.split()[0].lower()
        if first_counts[f] == 1:
            lookup.setdefault(f, n)

    seen, out = set(), []
    for line in text.split("\n"):
        m = re.match(r"^\s*([^:\n]{1,60}?)\s*:\s*(.*)$", line)
        if m:
            canon = lookup.get(m.group(1).strip().lower())
            if canon:
                seen.add(canon)
                out.append(f"{canon}: {m.group(2)}")
                continue
            if m.group(1).strip().lower() == "unknown":
                out.append(f"Unknown: {m.group(2)}")
                continue
        out.append(line)
    return "\n".join(out), sorted(seen)


def _free_disk_mb(path):
    st = os.statvfs(path)
    return (st.f_bavail * st.f_frsize) / (1024 * 1024)


def _transcribe_one(doc, roster):
    """Download -> transcode+segment -> ASR each segment -> joined transcript.

    Everything under `work` is removed in the finally, whatever happens: this VM
    does not have the disk to leak a single episode's audio.
    """
    if _free_disk_mb(BASE) < MIN_FREE_DISK_MB:
        raise RuntimeError(f"refusing to start: only {_free_disk_mb(BASE):.0f} MB free")

    work = tempfile.mkdtemp(prefix="podcast_asr_")
    try:
        src = f"{work}/src.audio"
        with requests.get(doc["audio_url"], stream=True, timeout=300, headers={
                "User-Agent": "Mozilla/5.0 (compatible; FieldsBrain/1.0)"}) as r:
            r.raise_for_status()
            with open(src, "wb") as fh:
                for blk in r.iter_content(1 << 20):
                    fh.write(blk)
        if os.path.getsize(src) < 10_000:
            raise RuntimeError(f"audio download too small ({os.path.getsize(src)} bytes)")

        # One pass: downmix to 16 kHz mono 32 kbps and cut fixed-length segments.
        # Segments do NOT overlap — an overlap would duplicate sentences into the
        # corpus, which is worse for a knowledge graph than losing a syllable.
        subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", src,
             "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k",
             "-f", "segment", "-segment_time", str(SEGMENT_SECONDS),
             f"{work}/seg_%04d.mp3"],
            check=True, timeout=3600)
        segs = sorted(glob.glob(f"{work}/seg_*.mp3"))
        if not segs:
            raise RuntimeError("ffmpeg produced no segments")

        context = f"Podcast: {doc.get('library')}. Episode: {doc.get('title')}"
        # Segments are independent, so transcribe a few at once — but keep the
        # fan-out small: each request carries several MB of base64 audio.
        with ThreadPoolExecutor(max_workers=3) as ex:
            texts = list(ex.map(lambda p: _asr_segment(p, roster, context), segs))

        text = re.sub(r"\n{3,}", "\n\n", "\n\n".join(t for t in texts if t).strip())
        text, spoke = _canonical_speakers(text, roster)
        # Rule 7b at the episode level: a transcript that assembled cleanly can
        # still be junk. Assert the outcome, do not merely fail to throw.
        uniq = _shingle_uniqueness(text)
        if uniq < EPISODE_UNIQ_MIN:
            raise DegenerateResponse(
                f"transcript is {uniq:.2f} unique 10-grams — repetition loop "
                f"survived segment-level checks; refusing to store it")
        return text, len(segs), spoke
    finally:
        shutil.rmtree(work, ignore_errors=True)


def transcribe(limit=5, only_slug=None):
    _dirs()
    coll = _coll()
    q = {"status": "pending", "attempts": {"$lt": MAX_ATTEMPTS}}
    if only_slug:
        q["slug"] = only_slug
    # Oldest first: the back catalogue is the part that is not going to change.
    docs = list(coll.find(q).sort("published_at", 1).limit(limit))
    if not docs:
        _log("transcribe: nothing pending")
        return {"attempted": 0, "transcribed": 0, "skipped": 0, "failed": 0}

    stats = {"attempted": 0, "transcribed": 0, "skipped": 0, "failed": 0}
    for doc in docs:
        stats["attempted"] += 1
        ep = doc["episode_id"]
        coll.update_one({"episode_id": ep},
                        {"$inc": {"attempts": 1},
                         "$set": {"last_attempt_at": datetime.now(timezone.utc)}})
        t0 = time.time()
        try:
            # Roster before audio: the transcriber needs the names up front so
            # speaker labels are identities that hold across segments.
            hosts = doc.get("hosts") or []
            guests = _extract_guests(doc)
            roster = ([f"{h} (host)" for h in hosts] + [f"{g} (guest)" for g in guests])
            text, n_segs, spoke = _transcribe_one(doc, roster)
        except Exception as e:
            stats["failed"] += 1
            msg = f"{type(e).__name__}: {str(e)[:400]}"
            _log(f"  FAIL {ep} — {msg}")
            coll.update_one({"episode_id": ep}, {"$set": {"last_error": msg}})
            continue

        words = len(text.split())
        if words < MIN_TRANSCRIPT_WORDS:
            stats["skipped"] += 1
            _log(f"  skip  {ep} — only {words} words (trailer/promo)")
            coll.update_one({"episode_id": ep}, {"$set": {
                "status": "skipped_short", "word_count": words,
                "last_error": None}})
            continue

        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", ep)[:120]
        path = f"{BASE}/transcripts/{safe}.txt"
        with open(path, "w") as fh:
            fh.write(text)
        stats["transcribed"] += 1
        _log(f"  ok    {ep} — {words} words, {n_segs} segs, {time.time()-t0:.0f}s")
        # `roster` is who we expected; `speakers` is who the labels show actually
        # spoke. Keeping both stops a guest who never speaks entering the graph.
        coll.update_one({"episode_id": ep}, {"$set": {
            "status": "transcribed", "word_count": words, "n_segments": n_segs,
            "transcript_path": path, "asr_model": ASR_MODEL,
            "guests": guests, "roster": roster, "speakers": spoke,
            "transcribed_at": datetime.now(timezone.utc), "last_error": None}})

    # Rule 7b: a run that tried and produced nothing is a failure, not a quiet
    # success. "Nothing pending" already returned above, so reaching here with
    # zero transcribed and zero legitimately-short means the route is broken.
    if stats["attempted"] and not (stats["transcribed"] or stats["skipped"]):
        raise RuntimeError(
            f"attempted {stats['attempted']} episodes and transcribed 0 — "
            f"ASR or audio fetch is broken, not empty")
    return stats


# ---------------------------------------------------------------------------
# chunk
# ---------------------------------------------------------------------------
def _next_unit_number(coll):
    top = coll.find({"last_unit_number": {"$exists": True}}) \
              .sort("last_unit_number", -1).limit(1)
    for d in top:
        return d["last_unit_number"] + 1
    return U_ID_BASE


def _next_batch_index():
    existing = sorted(glob.glob(f"{BASE}/batches/sp_*.txt"))
    if not existing:
        return 0
    return int(re.search(r"sp_(\d+)\.txt", existing[-1]).group(1)) + 1


def chunk(only_slug=None):
    _dirs()
    coll = _coll()
    q = {"status": "transcribed"}
    if only_slug:
        q["slug"] = only_slug
    docs = list(coll.find(q).sort("published_at", 1))
    if not docs:
        _log("chunk: nothing to chunk")
        return {"episodes": 0, "units": 0, "batches": 0}

    unit_no = _next_unit_number(coll)
    batch_ix = _next_batch_index()
    pending, stats = [], {"episodes": 0, "units": 0, "batches": 0}

    def flush():
        nonlocal pending, batch_ix
        if not pending:
            return
        with open(f"{BASE}/batches/sp_{batch_ix:04d}.txt", "w") as fh:
            fh.write("\n\n".join(pending))
        batch_ix += 1
        stats["batches"] += 1
        pending = []

    for doc in docs:
        try:
            with open(doc["transcript_path"]) as fh:
                words = fh.read().split()
        except OSError as e:
            _log(f"  skip {doc['episode_id']} — transcript unreadable: {e}")
            continue
        chunks = [" ".join(words[i:i + WORDS_PER_UNIT])
                  for i in range(0, len(words), WORDS_PER_UNIT)]
        pub = doc.get("published_at")
        date = pub.strftime("%Y-%m-%d") if hasattr(pub, "strftime") else ""
        show_url = (f"https://open.spotify.com/show/{doc['spotify_show']}"
                    if doc.get("spotify_show") else "")
        ids = []
        for i, body in enumerate(chunks, 1):
            uid = f"u{unit_no}"
            unit_no += 1
            ids.append(uid)
            # Byte-compatible with the original corpus and the YouTube feed:
            # brain1_annotate.py parses `===== UNIT (<id>) | LIB: (<lib>) =====`.
            # `|` is the header's field separator, and podcast titles frequently
            # contain one ("BSOTF | Ep. 1 ..."). Left raw, the annotator splits
            # the title across two fields and emits provenance.course = "" —
            # i.e. every unit loses its episode attribution. Substitute first.
            safe_title = doc["title"].replace("|", "-").strip()
            epno = doc.get("episode_number")
            speakers = doc.get("speakers") or doc.get("roster") or []
            header = (
                f"Podcast: {doc['library']} | Market: {doc.get('country') or 'n/a'} "
                f"| Episode: {safe_title}"
                + (f" | Episode number: {epno}" if epno else "")
                + f" | Date: {date}"
                + (f" | Speakers: {', '.join(speakers)}" if speakers else "")
                + f" | Part {i} of {len(chunks)} | {show_url}")
            pending.append(
                f"===== UNIT {uid} | LIB: {doc['library']} =====\n"
                f"HEADER: {header}\n"
                f"TEXT: {header} {body}")
            stats["units"] += 1
            if len(pending) >= UNITS_PER_BATCH:
                flush()
        coll.update_one({"episode_id": doc["episode_id"]}, {"$set": {
            "status": "chunked", "unit_ids": ids,
            "last_unit_number": unit_no - 1,
            "chunked_at": datetime.now(timezone.utc)}})
        stats["episodes"] += 1
    flush()
    _log(f"chunk: {stats}")
    if stats["episodes"] and not stats["units"]:
        raise RuntimeError("chunked episodes but produced 0 units")
    return stats


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------
def provenance(only_slug=None, prune=False):
    """Rewrite `provenance` in annotations.jsonl from Mongo ground truth.

    The annotator infers provenance from the unit header, and that inference is
    label-sensitive: the YouTube feed's `Video: <title>` populates
    `provenance.course`, but this feed's `Episode: <title>` does not — every
    podcast unit came back with `course: ""`, i.e. no episode attribution at all,
    while still looking like a clean successful annotation.

    We already know the exact episode for every unit id (chunk() recorded it), so
    this does not need to be inferred at all. This stage overwrites it from the
    database, which also makes the corpus immune to the annotator changing its
    mind about header labels later.
    """
    path = f"{BASE}/annotations.jsonl"
    if not os.path.exists(path):
        _log(f"provenance: no annotations at {path} — run brain1_annotate first")
        return {"rewritten": 0, "unmapped": 0}

    coll = _coll()
    q = {"unit_ids": {"$exists": True}}
    if only_slug:
        q["slug"] = only_slug
    unit_map = {}
    for d in coll.find(q, {"unit_ids": 1, "title": 1, "library": 1, "published_at": 1,
                           "episode_number": 1, "speakers": 1, "roster": 1}):
        n = len(d["unit_ids"])
        title = d["title"].replace("|", "-").strip()
        epno = d.get("episode_number")
        pub = d.get("published_at")
        # brain1_graph.py reads `date` straight off the annotation row
        # (`u.get("date", "")`), so this is what puts an episode on a timeline.
        date = pub.strftime("%Y-%m-%d") if hasattr(pub, "strftime") else ""
        # Speakers are merged into `entities`, which the graph indexes — that is
        # what makes "who said this" answerable rather than just recorded.
        speakers = [re.sub(r"\s*\((host|guest)\)$", "", s).strip()
                    for s in (d.get("speakers") or d.get("roster") or [])]
        speakers = [s for s in speakers if s and s.lower() != "unknown"]
        for i, uid in enumerate(d["unit_ids"], 1):
            unit_map[uid] = {
                "provenance": {
                    "library": d["library"],
                    "course": f"Ep {epno}: {title}" if epno else title,
                    "module": f"Part {i} of {n}"},
                "date": date,
                "episode_number": epno,
                "speakers": speakers,
            }

    rows, rewritten, unmapped, pruned = [], 0, 0, 0
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if prune and row.get("unit_id") not in unit_map:
                # An orphan: its episode was reset (e.g. by `audit --reset`) and
                # re-chunked under fresh unit ids. Left in place it would ship the
                # OLD degenerate text into the graph alongside the replacement,
                # because the nightly merges this file wholesale.
                pruned += 1
                continue
            meta = unit_map.get(row.get("unit_id"))
            if meta:
                before = (row.get("provenance"), row.get("date"), row.get("speakers"))
                row["provenance"] = meta["provenance"]
                row["date"] = meta["date"]
                row["episode_number"] = meta["episode_number"]
                row["speakers"] = meta["speakers"]
                ents = row.get("entities") or []
                for s in meta["speakers"]:
                    if s not in ents:
                        ents.append(s)
                row["entities"] = ents
                if before != (row["provenance"], row["date"], row["speakers"]):
                    rewritten += 1
            else:
                unmapped += 1
            rows.append(row)

    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    _log(f"provenance: rewrote {rewritten}/{len(rows)} units "
         f"({unmapped} unmapped, {pruned} pruned)")
    # Rule 7b: units we cannot attribute are units the graph will mis-cite. Note
    # this fires only WITHOUT --prune; an orphan is a real signal (usually a reset
    # episode not yet re-chunked) and must be looked at, not silently dropped.
    if unmapped:
        raise RuntimeError(
            f"{unmapped} annotated units have no episode in Mongo — attribution "
            f"would be wrong. Re-run chunk if an episode was reset, or pass "
            f"--prune to drop them deliberately")
    return {"rewritten": rewritten, "unmapped": unmapped, "pruned": pruned}


# ---------------------------------------------------------------------------
def audit(only_slug=None, reset=False):
    """Re-check stored transcripts for repetition loops.

    Exists because the guards were added AFTER a backfill had already run: three
    degenerate transcripts were sitting in the corpus looking like clean
    successes. Run this after any bulk transcription, and after changing the ASR
    model or prompt.

    `reset=True` sends the offenders back to `pending` and deletes the bad
    transcript so the next transcribe run redoes them.
    """
    coll = _coll()
    q = {"transcript_path": {"$exists": True}}
    if only_slug:
        q["slug"] = only_slug
    bad = []
    n = 0
    for d in coll.find(q, {"episode_id": 1, "title": 1, "transcript_path": 1,
                           "duration": 1, "word_count": 1, "unit_ids": 1}):
        try:
            text = open(d["transcript_path"]).read()
        except OSError:
            continue
        n += 1
        uniq = _shingle_uniqueness(text)
        if uniq < EPISODE_UNIQ_MIN:
            dur = (d.get("duration") or 0) / 60
            bad.append((uniq, d))
            _log(f"  DEGENERATE {uniq:.3f} uniq | "
                 f"{(d.get('word_count') or 0)/dur if dur else 0:.0f} wpm | "
                 f"{d['title'][:44]}")
    _log(f"audit: {len(bad)}/{n} transcripts below {EPISODE_UNIQ_MIN} unique 10-grams")
    if bad and reset:
        for uniq, d in bad:
            try:
                os.remove(d["transcript_path"])
            except OSError:
                pass
            coll.update_one({"episode_id": d["episode_id"]}, {
                "$set": {"status": "pending", "attempts": 0,
                         "last_error": f"degenerate transcript ({uniq:.2f} uniq) — reset"},
                "$unset": {"transcript_path": "", "word_count": "", "unit_ids": "",
                           "last_unit_number": "", "chunked_at": "", "speakers": ""}})
        _log(f"audit: reset {len(bad)} episodes to pending")
        _log("      NOTE: units for these episodes are still in annotations.jsonl — "
             "re-run chunk + annotate + provenance, then prune stale unit ids")
    return {"checked": n, "degenerate": len(bad)}


def status():
    coll = _coll()
    _log(f"base: {BASE}  ({_free_disk_mb(BASE):.0f} MB free)")
    for slug in sorted({d["slug"] for d in coll.find({}, {"slug": 1})}):
        counts = {}
        for st in coll.distinct("status", {"slug": slug}):
            counts[st] = coll.count_documents({"slug": slug, "status": st})
        secs = sum(d.get("duration") or 0 for d in coll.find({"slug": slug}, {"duration": 1}))
        words = sum(d.get("word_count") or 0 for d in coll.find({"slug": slug}, {"word_count": 1}))
        _log(f"  {slug}: {counts} | {secs/3600:.1f}h audio | {words:,} words transcribed")
    errs = list(coll.find({"last_error": {"$ne": None}}, {"episode_id": 1, "last_error": 1}).limit(5))
    for e in errs:
        _log(f"  ERR {e['episode_id']}: {e['last_error'][:160]}")
    _log(f"  transcripts on disk: {len(glob.glob(f'{BASE}/transcripts/*.txt'))}"
         f" | batches: {len(glob.glob(f'{BASE}/batches/sp_*.txt'))}")


def main():
    load_env()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["discover", "transcribe", "chunk",
                                      "provenance", "audit", "status", "all"])
    ap.add_argument("--reset", action="store_true",
                    help="audit only: send degenerate transcripts back to pending")
    ap.add_argument("--prune", action="store_true",
                    help="provenance only: drop annotation rows whose episode no "
                         "longer claims them (orphans left by audit --reset)")
    ap.add_argument("--slug", help="restrict to one feed from config/podcast_feeds.yaml")
    ap.add_argument("--limit", type=int, default=5, help="episodes per transcribe run")
    ap.add_argument("--no-heartbeat", action="store_true",
                    help="skip the job_runs heartbeat (for ad-hoc/manual runs)")
    a = ap.parse_args()

    def run_stage():
        if a.stage in ("discover", "all"):
            discover(a.slug)
        if a.stage in ("transcribe", "all"):
            transcribe(a.limit, a.slug)
        if a.stage in ("chunk", "all"):
            chunk(a.slug)
        if a.stage == "provenance":
            provenance(a.slug, prune=a.prune)
        if a.stage == "audit":
            audit(a.slug, reset=a.reset)
        if a.stage == "status":
            status()

    if a.stage == "status" or a.no_heartbeat:
        run_stage()
        return
    with job_run("podcast_brain_ingest", cadence_hours=168,
                 title="Podcast -> Brain 1 ingest") as beat:
        run_stage()
        coll = _coll()
        beat.metrics = {
            "episodes": coll.count_documents({}),
            "transcribed": coll.count_documents({"status": {"$in": ["transcribed", "chunked"]}}),
            "chunked": coll.count_documents({"status": "chunked"}),
            "pending": coll.count_documents({"status": "pending"}),
        }
        beat.detail = (f"{beat.metrics['chunked']}/{beat.metrics['episodes']} episodes "
                       f"in Brain 1")


if __name__ == "__main__":
    main()
