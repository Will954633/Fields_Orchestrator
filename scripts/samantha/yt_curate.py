#!/usr/bin/env python3
"""
Relevance curation for YouTube transcripts, between `transcribe` and `chunk`.

Why this exists
---------------
Transcripts are free and fast (525 videos in ~18 minutes). ANNOTATION is the
only real cost — ~2.4 minutes per 10-unit batch, so Keller Williams' 410 hours
would be ~12 hours of Max CLI time. Curating before annotation therefore buys
back the expensive resource, not the cheap one.

What the corpus actually taught us
----------------------------------
Measured on the 1,633-unit eXp Realty corpus: only **1%** of units came from
videos whose TITLE reads as recruiting. The config had predicted a poor
signal-to-noise ratio and it was right about the ratio but wrong about the
shape. The corpus is dominated by long recorded sessions — a 104-unit video,
"Level Up", "The Lab", "Big Agent Meeting REPLAY" — which interleave
housekeeping, announcements, chatter and genuine method in one stream.

So the noise is INSIDE long videos, not spread across bad ones, and curation
runs at two levels: a video-level relevance score, and a chunk-level pass that
drops only clearly non-teaching passages.

And note the annotator cannot help here: it produces plausible structured output
from any input, so eXp's topic tags look excellent whether or not the source was
worth ingesting. A corpus cannot self-report its own noise. That is the whole
argument for filtering BEFORE annotation rather than pruning after.

Design rules
------------
1. **Never delete a transcript.** Only annotation is gated. A rejected video is
   recoverable by flipping a flag — no re-scraping, no re-spend.
2. **Record every decision with its score and reason** (`curation` on the video
   doc). Without this, "why isn't X in the brain?" is unanswerable and absence
   cannot be told apart from rejection — the Rule 8 trap in a new place.
3. **Conservative at chunk level.** Ambiguous stays in. Severing setup from
   payoff is a worse failure than carrying some housekeeping.
4. **Calibrate before trusting.** `--sample` prints accept/reject calls for a
   human to check. An uncalibrated judge applied to 1,338 videos is not a
   filter, it is a random editor.

Usage
-----
    python3 scripts/samantha/yt_curate.py triage --library "Keller Williams (US)"
    python3 scripts/samantha/yt_curate.py sample  --library "Keller Williams (US)" -n 20
    python3 scripts/samantha/yt_curate.py stats   --library "Keller Williams (US)"
"""

import argparse
import base64  # noqa: F401  (kept: parity with sibling ingesters' vertex helper)
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

from shared.db import get_client   # noqa: E402
from shared.env import load_env    # noqa: E402
from job_status import job_run     # noqa: E402

MODEL = os.environ.get("CURATE_MODEL", "gemini-2.5-flash")
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT_ID", "fields-estate")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "global")

KEEP_SCORE = int(os.environ.get("CURATE_KEEP_SCORE", "4"))   # video-level gate
WORDS_PER_UNIT = 1200        # MUST match youtube_brain_ingest.WORDS_PER_UNIT
MAX_TRANSCRIPT_WORDS = 24000  # ~32k tokens; longer sessions are sampled

# The rubric. Confirmed with Will 2026-08-16: seller conversion, prospecting and
# market-data communication are in scope; leadership/scaling/mindset is NOT —
# it is abundant on KW's "Empire Building" series and further from a sole
# operator's day-to-day need than it looks.
RUBRIC = """\
Fields Real Estate is a property-intelligence business on the Gold Coast,
Australia. Sole operator. Buyer-first and seller-funded: it builds a buyer
audience with free data and valuations, and earns from sellers (pre-sale
reports, appraisals) and from agents.

IN SCOPE — score these highly:
  - Seller conversion and listing method: listing presentations, pricing
    conversations, objection handling, delivering an appraisal or CMA, winning
    the instruction.
  - Prospecting and lead generation: farming, follow-up, scripts, database
    work, converting an enquiry into an appointment.
  - Market analysis and communicating data to clients: explaining conditions,
    using statistics in a conversation, commentary technique.

OUT OF SCOPE — score these low:
  - Team building, leadership, hiring, culture, scaling a brokerage.
  - Personal development and mindset content with no transferable technique.
  - Brokerage recruiting, revenue share, commission splits, agent attraction.
  - Company events, awards, announcements, product or tool promotion.
  - Generic AI/technology hype with no concrete method.

Also note: this is US content for an Australian operator. Scripts, psychology
and conversational technique transfer. Pricing, regulation, contract mechanics
and seasonality do NOT — a video that is ONLY US-specific regulation is low
value even if it is technically about selling.
"""

TRIAGE_SCHEMA = """\
Reply with ONLY a JSON object, no markdown fence:
{
  "relevance": <integer 0-10, how much IN-SCOPE teaching content this contains>,
  "verdict": "<one sentence, why that score>",
  "topics": ["<up to 5 short in-scope topic labels, [] if none>"],
  "boilerplate": [
     {"chunk": <index>, "evidence": "<5-15 words quoted from THAT chunk which
        show it is non-teaching>"}
  ]
}

Rules for `boilerplate` — read carefully, this is the part most often done badly:
  * A chunk qualifies ONLY if it is genuinely non-teaching: greetings and guest
    introductions, sponsor or event promotion, housekeeping and admin,
    announcements, awards, sign-offs and calls to subscribe.
  * You MUST quote real words from that chunk as `evidence`. If you cannot quote
    something that demonstrates it, the chunk does not qualify. Do not
    paraphrase and do not invent.
  * DO NOT assume the first and last chunks are boilerplate. Many videos open
    directly on substance and end mid-explanation. Judge every chunk on what it
    actually says. Returning exactly the first and last chunk every time is the
    single most common mistake here and is usually wrong.
  * Non-teaching passages in the MIDDLE of long recorded sessions — housekeeping,
    announcements, unrelated Q&A — are the most valuable thing to find. Look for
    those specifically.
  * If nothing clearly qualifies, return an empty list. That is a normal and
    frequent answer. Keeping some filler is far better than cutting an
    explanation in half.
"""

_CREDS = None


def _log(m):
    print(f"{datetime.now(timezone.utc).isoformat()} {m}", flush=True)


def _coll():
    return get_client()["system_monitor"]["youtube_videos"]


def _token():
    global _CREDS
    from google.auth.transport.requests import Request as _R
    if _CREDS is None:
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        kf = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "/home/fields/.gcp-vertex-key.json"
        if os.path.exists(kf):
            from google.oauth2 import service_account
            _CREDS = service_account.Credentials.from_service_account_file(kf, scopes=scopes)
        else:
            import google.auth
            _CREDS, _ = google.auth.default(scopes=scopes)
    if not _CREDS.valid:
        _CREDS.refresh(_R())
    return _CREDS.token


def _gen(prompt, max_tokens=2048, budget=4):
    host = ("aiplatform.googleapis.com" if VERTEX_REGION == "global"
            else f"{VERTEX_REGION}-aiplatform.googleapis.com")
    url = (f"https://{host}/v1/projects/{VERTEX_PROJECT}/locations/{VERTEX_REGION}"
           f"/publishers/google/models/{MODEL}:generateContent")
    gen = {"maxOutputTokens": max_tokens, "temperature": 0}
    if "flash" in MODEL:
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": gen}
    last = None
    for a in range(budget):
        try:
            r = requests.post(url, json=body, timeout=300, headers={
                "Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(min(45, 4 * (2 ** a)))
                continue
            r.raise_for_status()
            c = (r.json().get("candidates") or [{}])[0]
            if c.get("finishReason") == "MAX_TOKENS":
                raise RuntimeError("truncated")
            t = "".join(p.get("text", "") for p in (c.get("content", {}).get("parts") or [])).strip()
            if not t:
                raise RuntimeError(f"empty candidate ({c.get('finishReason')})")
            return t
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(min(45, 4 * (2 ** a)))
    raise RuntimeError(f"vertex failed after {budget}: {last}")


def _chunk_words(text):
    w = text.split()
    return [w[i:i + WORDS_PER_UNIT] for i in range(0, len(w), WORDS_PER_UNIT)]


def _build_prompt(doc, text):
    """Present the transcript already split on the SAME boundaries `chunk` will
    use, so a returned index maps 1:1 onto a real unit. Guessing offsets from a
    continuous transcript would silently misalign."""
    chunks = _chunk_words(text)
    total_words = sum(len(c) for c in chunks)
    parts, budget = [], MAX_TRANSCRIPT_WORDS
    for i, c in enumerate(chunks):
        # Long sessions: show the head of each chunk rather than dropping whole
        # chunks, so every index is still judged on real content.
        per = max(120, budget // max(1, len(chunks)))
        parts.append(f"[CHUNK {i}]\n" + " ".join(c[:per]))
    return (
        f"{RUBRIC}\n"
        f"Assess this YouTube video for the Fields Brain 1 knowledge corpus.\n\n"
        f"TITLE: {doc.get('title')}\n"
        f"DURATION: {round((doc.get('duration') or 0)/60)} min\n"
        f"TRANSCRIPT WORDS: {total_words} across {len(chunks)} chunks "
        f"(indices 0..{len(chunks)-1})\n\n"
        f"{chr(10).join(parts)}\n\n{TRIAGE_SCHEMA}"
    )


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower())


def _parse(raw, n_chunks, chunks=None):
    """Parse the verdict and VERIFY each boilerplate claim against the chunk.

    Demanding evidence is only worth anything if the evidence is checked. The
    first version of this asked for a judgement and got a positional reflex —
    13 of 14 videos came back as exactly [0, n-1], which is not analysis, it is
    a guess about where intros live. So a flagged chunk is now accepted only if
    the quoted words are really present in that chunk.
    """
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    d = json.loads(raw)
    bp, rejected = [], 0
    for item in (d.get("boilerplate") or []):
        if not isinstance(item, dict):
            continue
        i, ev = item.get("chunk"), item.get("evidence") or ""
        if not isinstance(i, int) or not 0 <= i < n_chunks:
            continue
        if chunks is not None:
            hay = _norm(" ".join(chunks[i]))
            needle = _norm(ev)
            # Require a real, reasonably specific quote to be present verbatim.
            if len(needle) < 12 or needle not in hay:
                rejected += 1
                continue
        bp.append(i)
    # Flagging every chunk means the task was misread, not that the video is
    # worthless — the video-level score already covers that case.
    if len(bp) >= n_chunks:
        bp = []
    return {"score": max(0, min(10, int(d.get("relevance", 0)))),
            "verdict": str(d.get("verdict", ""))[:300],
            "topics": [str(t)[:40] for t in (d.get("topics") or [])][:5],
            "boilerplate_chunks": sorted(set(bp)),
            "evidence_rejected": rejected}


def _triage_one(doc):
    try:
        with open(doc["transcript_path"]) as fh:
            text = fh.read()
    except OSError as e:
        return doc["video_id"], None, f"transcript unreadable: {e}"
    chunks = _chunk_words(text)
    n = len(chunks)
    try:
        res = _parse(_gen(_build_prompt(doc, text)), n, chunks)
    except Exception as e:
        return doc["video_id"], None, f"{type(e).__name__}: {str(e)[:150]}"
    res.update({"include": res["score"] >= KEEP_SCORE, "n_chunks": n,
                "model": MODEL, "at": datetime.now(timezone.utc)})
    return doc["video_id"], res, None


def triage(library, limit=0, workers=8, redo=False):
    coll = _coll()
    q = {"library": library, "status": "transcribed",
         "transcript_path": {"$exists": True}}
    if not redo:
        q["curation"] = {"$exists": False}
    docs = list(coll.find(q).limit(limit) if limit else coll.find(q))
    if not docs:
        _log("triage: nothing to curate")
        return {"triaged": 0, "kept": 0, "dropped": 0, "failed": 0}
    _log(f"triage: {len(docs)} videos on {MODEL} (keep score >= {KEEP_SCORE})")

    st = {"triaged": 0, "kept": 0, "dropped": 0, "failed": 0, "chunks_dropped": 0}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for vid, res, err in ex.map(_triage_one, docs):
            if err:
                st["failed"] += 1
                _log(f"  FAIL {vid} — {err}")
                coll.update_one({"video_id": vid},
                                {"$set": {"curation_error": err}})
                continue
            coll.update_one({"video_id": vid},
                            {"$set": {"curation": res, "curation_error": None}})
            st["triaged"] += 1
            st["kept" if res["include"] else "dropped"] += 1
            if res["include"]:
                st["chunks_dropped"] += len(res["boilerplate_chunks"])
    _log(f"triage: {st}")
    # Rule 7b: attempted work that produced no verdicts is a broken route, not a
    # tidy corpus. Distinguish that from an empty queue, which returned above.
    if docs and st["triaged"] == 0:
        raise RuntimeError(
            f"triaged 0 of {len(docs)} videos — Vertex or the schema is broken")
    return st


def sample(library, n=20):
    """Print accept/reject calls for a human to check BEFORE trusting the filter."""
    coll = _coll()
    docs = list(coll.find({"library": library, "curation": {"$exists": True}},
                          {"title": 1, "duration": 1, "curation": 1}))
    if not docs:
        _log("sample: nothing curated yet")
        return
    docs.sort(key=lambda d: d["curation"]["score"])
    picks = docs[:n // 2] + docs[-(n - n // 2):]      # worst and best
    print(f"\n{'score':>5} {'keep':>5} {'min':>4} {'bp':>3}  title / verdict")
    print("-" * 100)
    for d in picks:
        c = d["curation"]
        print(f"{c['score']:5} {'YES' if c['include'] else 'no':>5} "
              f"{round((d.get('duration') or 0)/60):4} "
              f"{len(c['boilerplate_chunks']):3}  {d['title'][:70]}")
        print(f"{'':17}{c['verdict'][:96]}")
    kept = sum(1 for d in docs if d["curation"]["include"])
    print(f"\n{kept}/{len(docs)} kept ({100*kept/len(docs):.0f}%)")


def stats(library):
    coll = _coll()
    docs = list(coll.find({"library": library, "curation": {"$exists": True}},
                          {"curation": 1, "duration": 1}))
    if not docs:
        _log("stats: nothing curated yet")
        return
    dist = {}
    for d in docs:
        dist[d["curation"]["score"]] = dist.get(d["curation"]["score"], 0) + 1
    kept = [d for d in docs if d["curation"]["include"]]
    units_all = sum(d["curation"]["n_chunks"] for d in docs)
    units_kept = sum(d["curation"]["n_chunks"] - len(d["curation"]["boilerplate_chunks"])
                     for d in kept)
    print(f"curated       : {len(docs)}")
    print(f"score spread  : " + "  ".join(f"{s}:{dist[s]}" for s in sorted(dist)))
    print(f"kept (>= {KEEP_SCORE})  : {len(kept)} ({100*len(kept)/len(docs):.0f}%)")
    print(f"units if ALL  : {units_all}")
    print(f"units if kept : {units_kept}  ({100*units_kept/max(1,units_all):.0f}%)")
    saved = (units_all - units_kept) / 10 * 2.4 / 60
    print(f"annotation saved: ~{saved:.1f} h")


def main():
    load_env()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["triage", "sample", "stats"])
    ap.add_argument("--library", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--redo", action="store_true", help="re-curate already-curated videos")
    ap.add_argument("--no-heartbeat", action="store_true")
    a = ap.parse_args()

    if a.stage == "sample":
        return sample(a.library, a.n)
    if a.stage == "stats":
        return stats(a.library)
    if a.no_heartbeat:
        return triage(a.library, a.limit, a.workers, a.redo)
    with job_run("yt_curate", cadence_hours=168, title="YouTube relevance curation") as beat:
        r = triage(a.library, a.limit, a.workers, a.redo)
        beat.metrics = r
        beat.detail = f"{r['kept']} kept / {r['dropped']} dropped"


if __name__ == "__main__":
    main()
