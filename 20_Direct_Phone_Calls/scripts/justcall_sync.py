#!/usr/bin/env python3
"""
justcall_sync.py — nightly reconciliation of JustCall calls + AI transcripts into the CRM.

WHY THIS JOB IS MANDATORY, NOT A NICETY
    The JustCall API exposes **only the last 3 months** of call history. A call that is
    not ingested inside that window is unrecoverable except by emailing their support.
    So a silent failure here is not "we'll pick it up tomorrow" — it is permanent data
    loss with a 90-day fuse. Everything below is shaped by that:

      * the watermark lives in Mongo (`system_monitor.job_watermarks`), never a local
        file, and is advanced ONLY on a run that succeeded (CLAUDE.md rule 7b #2);
      * a run that sees calls in the window and ingests none RAISES (rule 7b) — it is
        not the same thing as a quiet night with no calls;
      * the webhook (`justcall-call-webhook.mjs`) is the fast path, this is the
        backstop. Neither is trusted alone.

WHAT IT DOES
    1. GET /v2.1/calls over [watermark|now-N days, now]  — paged, 100/page.
    2. GET /v2.1/calls_ai?fetch_transcription=true over the same window — paged, 20/page
       (that per_page cap is the API's, not ours). fetch_transcription DEFAULTS TO FALSE;
       omitting it returns a 200 with no transcript and looks exactly like "not
       entitled", which is why --test-transcription exists.
    3. Upsert both into `system_monitor.call_activity`, keyed on `call_sid` (stable
       across the webhook and this job; the numeric `id` is not guaranteed to be).
    4. Join each call to the campaign row in `system_monitor.call_queue` and stamp that
       row status="called". Two paths, tried in this order:
         a. BY `metadata` — exact. The sheet's call panel
            (20_Direct_Phone_Calls/apps_script/) stamps the queue row's _id into the
            JustCall dialer deep link, and JustCall echoes it back. A match here is
            proof, not inference.
         b. BY PHONE NUMBER — heuristic fallback (digits-only, AU prefix variance
            handled). Covers calls placed outside the sheet, e.g. from Will's handset.
       Which path matched is stored per call (`queue_match`) and counted, because a row
       joined on an exact id is stronger evidence than one joined on folded digits.
       AN UNMATCHED CALL IS A FACT, NOT A FAILURE — it is recorded as such (Will dialling
       someone by hand is a legitimate unmatched call), and counted so a join that breaks
       wholesale is visible as a number rather than as silence.

TRANSCRIPTION ENTITLEMENT IS UNPROVEN ON OUR PLAN
    We are on Team. JustCall's blog says transcription is included from Team; third-party
    pricing analyses call it an add-on; the developer docs are silent. Therefore a missing
    transcript is stored as an EXPLICIT STATE (`transcript_state`), never as an absent
    field:

        pending        — no AI record for this call yet (may still be generating)
        available      — transcript text present
        empty          — AI record returned, transcript array empty (recorded but nothing said,
                         or not entitled — indistinguishable from one call, distinguishable in bulk)
        not_entitled   — the calls_ai endpoint refused us (401/403)
        no_recording   — call was not recorded, so a transcript was never possible

    Fallback if entitlement fails: download the MP3 (--download-recordings) and transcribe
    with Gemini via Vertex, already wired at VISION_BACKEND=gemini_vertex.

USAGE
    python3 20_Direct_Phone_Calls/scripts/justcall_sync.py --test-transcription
    python3 20_Direct_Phone_Calls/scripts/justcall_sync.py --since 2
    python3 20_Direct_Phone_Calls/scripts/justcall_sync.py --since 7 --download-recordings
    python3 20_Direct_Phone_Calls/scripts/justcall_sync.py --dry-run

READ-ONLY AGAINST JUSTCALL. Every request this file makes is a GET. It never places a
call, never sends a text, never registers a webhook.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
_DOMAIN = os.path.dirname(_HERE)                    # 20_Direct_Phone_Calls
_REPO = os.path.dirname(_DOMAIN)                    # Fields_Orchestrator
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from shared.db import get_client                    # noqa: E402
from job_status import job_run                      # noqa: E402

try:                                                # py3.9+
    from zoneinfo import ZoneInfo
except ImportError:                                 # pragma: no cover
    ZoneInfo = None  # type: ignore

BASE = "https://api.justcall.io/v2.1"
BRISBANE = ZoneInfo("Australia/Brisbane") if ZoneInfo else timezone(timedelta(hours=10))

DB = "system_monitor"
COLL_ACTIVITY = "call_activity"
COLL_QUEUE = "call_queue"
COLL_WATERMARK = "job_watermarks"
WATERMARK_ID = "justcall_sync"

RECORDINGS_DIR = os.path.join(_DOMAIN, "recordings")

# Team plan: 1800 req/hr, 30/min burst. One request per 2s is 30/min exactly at the
# burst ceiling, so back off a hair under it and stay inside both limits with room.
MIN_INTERVAL_S = 2.0

# The API's own retention. We clamp any watermark older than this because asking for
# data outside it returns nothing and would let us "catch up" over a gap that is in fact
# permanently gone — the run must SAY that, not paper over it.
API_RETENTION_DAYS = 90


# ─────────────────────────────────────────────────────────────────────────────
# env
# ─────────────────────────────────────────────────────────────────────────────
def set_env_from_file() -> None:
    """Load our own environment (CLAUDE.md rule 7 #3). A cron line missing `set -a`
    exports nothing, and shared.db would still connect via config/settings.yaml — so the
    job would look healthy while every credential-dependent call 401'd."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO, ".env"), override=False)


def jc_auth() -> str:
    key = os.environ.get("JUSTCALL_API_KEY")
    secret = os.environ.get("JUSTCALL_API_SECRET")
    if not key or not secret:
        raise RuntimeError(
            "JUSTCALL_API_KEY / JUSTCALL_API_SECRET missing from the environment "
            "(expected in Fields_Orchestrator/.env)")
    # Not Basic, not Bearer, no base64 — JustCall wants the pair raw and colon-separated.
    # Same convention as the shipped netlify/functions/justcall-sms.mjs.
    return f"{key}:{secret}"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP: one throttled, 429-aware GET used by everything
# ─────────────────────────────────────────────────────────────────────────────
class JustCall:
    def __init__(self, verbose: bool = True):
        self.auth = jc_auth()
        self.session = requests.Session()
        self.verbose = verbose
        self._last_request = 0.0
        self.requests_made = 0

    def _throttle(self) -> None:
        wait = MIN_INTERVAL_S - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    @staticmethod
    def _reset_wait(resp: "requests.Response", attempt: int) -> float:
        """How long to wait after a 429. X-Rate-Limit-Reset is documented loosely enough
        that it may be an epoch OR a seconds-remaining, so handle both rather than
        sleeping until 2055."""
        raw = (resp.headers.get("X-Rate-Limit-Reset")
               or resp.headers.get("x-rate-limit-reset")
               or resp.headers.get("Retry-After"))
        try:
            val = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return min(60.0, 5.0 * (2 ** attempt))
        if val > 1_000_000_000:                      # looks like a unix epoch
            val = val - time.time()
        return max(1.0, min(300.0, val + 1.0))

    def get(self, path: str, params: dict | None = None, *, stream: bool = False,
            raise_for_status: bool = True) -> "requests.Response":
        url = f"{BASE}{path}"
        for attempt in range(5):
            self._throttle()
            resp = self.session.get(
                url,
                params=params,
                headers={"Authorization": self.auth, "Accept": "application/json"},
                timeout=90,
                stream=stream,
            )
            self._last_request = time.time()
            self.requests_made += 1

            if resp.status_code == 429:
                wait = self._reset_wait(resp, attempt)
                if self.verbose:
                    print(f"  429 rate-limited on {path} — sleeping {wait:.0f}s "
                          f"(attempt {attempt + 1}/5)")
                time.sleep(wait)
                continue
            if resp.status_code >= 500 and attempt < 4:
                wait = min(60.0, 5.0 * (2 ** attempt))
                if self.verbose:
                    print(f"  {resp.status_code} on {path} — retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
            if raise_for_status and not resp.ok:
                raise RuntimeError(
                    f"GET {path} -> HTTP {resp.status_code}: {resp.text[:400]}")
            return resp
        raise RuntimeError(f"GET {path} exhausted retries (last status {resp.status_code})")


# ─────────────────────────────────────────────────────────────────────────────
# phone normalisation — the join key
# ─────────────────────────────────────────────────────────────────────────────
def phone_key(raw: Any) -> str | None:
    """Reduce any AU number to a comparable key.

    JustCall reports numbers bare and inconsistently ("61416529481", "+61416529481",
    "0416 529 481", "(07) 5555 1234"); ID4ME and our own queue store them differently
    again. Everything collapses to the national 9 digits after the leading 0 / +61, which
    is what actually identifies the line. Returns None for anything that cannot be one.
    """
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if not digits:
        return None
    if digits.startswith("0011"):
        digits = digits[4:]
    if digits.startswith("61") and len(digits) >= 11:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) >= 10:
        digits = digits[1:]
    if len(digits) < 8:
        return None
    return digits[-9:] if len(digits) >= 9 else digits


# ─────────────────────────────────────────────────────────────────────────────
# fetching
# ─────────────────────────────────────────────────────────────────────────────
def fmt_dt(dt: datetime) -> str:
    """The API wants `yyyy-mm-dd hh:mm:ss` IN THE ACCOUNT USER'S TIMEZONE
    (Australia/Brisbane for this account), not UTC and not ISO-8601."""
    return dt.astimezone(BRISBANE).strftime("%Y-%m-%d %H:%M:%S")


def _unwrap(payload: Any) -> list[dict]:
    """JustCall nests its list under `data` on v2.1, but has shipped bare arrays and
    `{"data": {"calls": [...]}}` in places. A parser that knows one shape is a parser that
    silently returns zero when they change it — and zero here is indistinguishable from
    a quiet night."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "calls", "results", "items"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
            if isinstance(val, dict):
                inner = _unwrap(val)
                if inner:
                    return inner
    return []


def fetch_calls(jc: JustCall, start: datetime, end: datetime,
                max_pages: int = 60) -> tuple[list[dict], int | None]:
    """Returns (rows, total_count).

    `total_count` is the SERVER'S OWN count for the window and is the load-bearing half:
    it is what lets rule 7b's assertion distinguish "the account made no calls" from "the
    account made calls and our parser returned none". Comparing our row count against a
    number we also derived from the same parse would prove nothing.
    """
    out: list[dict] = []
    total: int | None = None
    for page in range(1, max_pages + 1):
        resp = jc.get("/calls", {
            "from_datetime": fmt_dt(start),
            "to_datetime": fmt_dt(end),
            "page": page,
            "per_page": 100,          # API maximum
            "order": "desc",
        })
        payload = resp.json()
        if page == 1 and isinstance(payload, dict):
            tc = payload.get("total_count")
            if isinstance(tc, int):
                total = tc
        rows = _unwrap(payload)
        out.extend(rows)
        if jc.verbose:
            print(f"  /calls page {page}: {len(rows)} row(s)"
                  + (f" (server total_count={total})" if page == 1 and total is not None else ""))
        if len(rows) < 100:
            break
    return out, total


def fetch_calls_ai(jc: JustCall, start: datetime, end: datetime,
                   max_pages: int = 100) -> tuple[list[dict], str | None]:
    """Returns (rows, entitlement_error).

    entitlement_error is a human-readable string when the endpoint REFUSED us (401/403/
    402) — that is a different fact from "returned nothing" and the caller must be able
    to tell them apart, because one is a plan problem and the other is a quiet night.
    """
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        resp = jc.get("/calls_ai", {
            "from_datetime": fmt_dt(start),
            "to_datetime": fmt_dt(end),
            # DEFAULTS TO FALSE. Omit it and you get a 200 with no transcript, which is
            # exactly what "not entitled" looks like. This single param is the difference
            # between the feature working and appearing not to exist.
            "fetch_transcription": "true",
            "fetch_summary": "true",
            "fetch_ai_insights": "true",
            "page": page,
            "per_page": 20,           # API maximum for this endpoint, not a choice
        }, raise_for_status=False)

        if resp.status_code in (401, 402, 403):
            return rows, (f"HTTP {resp.status_code} from /calls_ai — "
                          f"{resp.text[:300]}")
        if not resp.ok:
            raise RuntimeError(f"GET /calls_ai -> HTTP {resp.status_code}: {resp.text[:400]}")

        page_rows = _unwrap(resp.json())
        rows.extend(page_rows)
        if jc.verbose:
            print(f"  /calls_ai page {page}: {len(page_rows)} row(s)")
        if len(page_rows) < 20:
            break
    return rows, None


# ─────────────────────────────────────────────────────────────────────────────
# shaping
# ─────────────────────────────────────────────────────────────────────────────
def pick(d: dict, *names, default=None):
    for n in names:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return default


def call_sid_of(row: dict) -> str | None:
    sid = pick(row, "call_sid", "callSid", "sid", "call_id", "id")
    return str(sid) if sid not in (None, "") else None


def recording_url_of(row: dict) -> str | None:
    val = pick(row, "recording_url", "call_recording", "recording", "call_recording_url")
    if isinstance(val, dict):
        val = pick(val, "url", "link", "recording_url")
    return str(val) if val else None


# Keys JustCall might carry the deep-link `metadata` under. The dialer deep link
# built by the sheet's call panel (20_Direct_Phone_Calls/apps_script/) puts the
# call_queue _id here, so a call can be joined to its campaign row by an EXACT key
# instead of by normalised phone digits.
#
# WHICH KEY IS REAL IS NOT DOCUMENTED for the /calls list response — the deep-link
# guide only promises metadata "in webhook payload for all event triggers". So this
# guesses a list rather than one name, AND the caller counts how many calls matched
# this way. A wrong guess therefore shows up as `matched_by_metadata: 0` in the
# heartbeat metrics — a number we can see — not as a silent fallback to the old
# behaviour. (CLAUDE.md rule 8: a zero is a fact about the name you typed.)
_METADATA_KEYS = ("metadata", "custom_metadata", "call_metadata", "meta_data")


def metadata_call_id_of(row: dict) -> str | None:
    """The call_queue _id we stamped into the dialer deep link, if it came back."""
    for key in _METADATA_KEYS:
        val = row.get(key)
        if isinstance(val, dict):
            val = pick(val, "call_id", "callId", "id", "value")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def transcript_from_ai(ai: dict | None) -> tuple[str, list, str | None]:
    """(state, segments, plain_text). See module docstring for the state vocabulary."""
    if not ai:
        return "pending", [], None
    segs = pick(ai, "call_transcription", "transcription", "transcript", default=[])
    if isinstance(segs, dict):
        segs = _unwrap(segs) or []
    if not isinstance(segs, list):
        segs = []
    if not segs:
        return "empty", [], None
    parts = []
    for s in segs:
        if isinstance(s, dict):
            who = pick(s, "speaker", "speaker_id", "agent", default="?")
            txt = pick(s, "text", "sentence", "transcript", default="")
            if txt:
                parts.append(f"{who}: {txt}")
        elif isinstance(s, str):
            parts.append(s)
    return ("available" if parts else "empty"), segs, ("\n".join(parts) or None)


def build_doc(call: dict, ai: dict | None, entitlement_error: str | None) -> dict:
    sid = call_sid_of(call)
    rec_url = recording_url_of(call)
    state, segs, text = transcript_from_ai(ai)

    if entitlement_error and state in ("pending", "empty"):
        state = "not_entitled"
    elif not rec_url and state in ("pending", "empty"):
        # No recording was ever made, so no transcript was ever possible. Saying
        # "pending" here would leave a row waiting forever for something that cannot
        # arrive — recording is a per-number dashboard toggle with no API.
        state = "no_recording"

    doc = {
        "call_sid": sid,
        "justcall_id": pick(call, "id", "call_id"),
        "dialer_metadata": metadata_call_id_of(call),
        "contact_number": pick(call, "contact_number", "client_number", "contact"),
        "contact_name": pick(call, "contact_name", "friendly_name"),
        "justcall_number": pick(call, "justcall_number", "justcall_line"),
        "agent_id": pick(call, "agent_id", "user_id"),
        "agent_name": pick(call, "agent_name", "user_name"),
        "call_date": pick(call, "call_date"),
        "call_time": pick(call, "call_time"),
        "direction": (pick(call, "call_direction", "direction", default="") or "").lower(),
        "call_type": pick(call, "call_type", "type"),
        "disposition": pick(call, "disposition", "call_info", "call_disposition"),
        "notes": pick(call, "notes", "call_notes"),
        "total_duration": pick(call, "total_duration", "call_duration"),
        "conversation_time": pick(call, "conversation_time"),
        "recording_url": rec_url,
        "voicemail_transcription": pick(call, "voicemail_transcription"),
        "transcript_state": state,
        "transcript_segments": segs or None,
        "transcript_text": text,
        "ai_summary": pick(ai or {}, "call_summary", "summary"),
        "ai_score": pick(ai or {}, "call_score", "score"),
        "ai_sentiment": pick(ai or {}, "customer_sentiment", "sentiment"),
        "ai_insights": pick(ai or {}, "ai_insights", "call_ai_insights"),
        "source": "api_sync",
        "raw_call": call,
        "last_synced_at": datetime.now(timezone.utc),
    }
    if entitlement_error:
        doc["transcript_error"] = entitlement_error
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# campaign join
# ─────────────────────────────────────────────────────────────────────────────
def build_queue_index(db) -> tuple[dict[str, dict], dict[str, dict]]:
    """Returns (phone_key -> call_queue doc, _id -> call_queue doc).

    Two indexes because there are two join paths, and they are not equally good:

      * BY _id — exact. The sheet's call panel stamps the queue row's _id into the
        JustCall dialer deep link as `metadata`, and JustCall relays it back. When
        this matches, the call provably belongs to that row.
      * BY PHONE — a heuristic. It cannot tell two people who share a landline
        apart, and it silently fails whenever a number is stored in a shape
        phone_key() does not fold. It is the fallback, not the primary.

    `call_queue` is written by build_call_list.py, which is a sibling of this script and
    may not have run yet. A MISSING QUEUE IS NOT A FAILURE OF THE SYNC — the calls are
    still real and must still be ingested — but it IS reported, so "every call unmatched"
    is never mistaken for a broken join.
    """
    if COLL_QUEUE not in db.list_collection_names():
        return {}, {}
    index: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for row in db[COLL_QUEUE].find(
            {}, {"phone": 1, "phones": 1, "contact_phone": 1, "mobile": 1,
                 "address": 1, "suburb": 1, "track": 1, "status": 1, "name": 1}):
        by_id[str(row["_id"])] = row
        candidates: list[Any] = [row.get("phone"), row.get("contact_phone"), row.get("mobile")]
        extra = row.get("phones")
        if isinstance(extra, list):
            candidates.extend(extra)
        for cand in candidates:
            if isinstance(cand, dict):
                cand = cand.get("number") or cand.get("phone")
            key = phone_key(cand)
            if key:
                index.setdefault(key, row)
    return index, by_id


# ─────────────────────────────────────────────────────────────────────────────
# recordings
# ─────────────────────────────────────────────────────────────────────────────
def download_recording(jc: JustCall, doc: dict) -> dict | None:
    sid = doc["call_sid"]
    jc_id = doc.get("justcall_id") or sid
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    path = os.path.join(RECORDINGS_DIR, f"{sid}.mp3")

    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()
        return {"path": path, "sha256": sha, "bytes": os.path.getsize(path),
                "downloaded_at": datetime.now(timezone.utc), "reused": True}

    resp = jc.get(f"/calls/{jc_id}/recording/download", stream=True,
                  raise_for_status=False)
    if not resp.ok:
        print(f"  ! recording download failed for {sid}: HTTP {resp.status_code}")
        return None
    body = resp.content
    if not body:
        print(f"  ! recording download for {sid} returned 0 bytes")
        return None
    with open(path, "wb") as fh:
        fh.write(body)
    return {"path": path, "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body), "downloaded_at": datetime.now(timezone.utc)}


# ─────────────────────────────────────────────────────────────────────────────
# the entitlement probe
# ─────────────────────────────────────────────────────────────────────────────
def test_transcription(jc: JustCall) -> int:
    """The 10-minute test that decides the architecture.

    Its whole job is to be IMPOSSIBLE TO MISREAD. A previous probe returned 200 with zero
    calls and was nearly taken as evidence of entitlement; it proved nothing at all. So
    every terminal state below names itself in capitals and says what it does and does
    not prove.
    """
    print("=" * 72)
    print("JUSTCALL TRANSCRIPTION ENTITLEMENT PROBE")
    print("=" * 72)

    end = datetime.now(BRISBANE)
    start = end - timedelta(days=API_RETENTION_DAYS)
    print(f"Window: {fmt_dt(start)} -> {fmt_dt(end)}  (Australia/Brisbane, "
          f"the full {API_RETENTION_DAYS}-day API retention)")

    calls, total = fetch_calls(jc, start, end)
    print(f"\nCalls found in the API window: {len(calls)} "
          f"(server total_count={total})")

    if not calls:
        print("\n" + "-" * 72)
        print("VERDICT: INCONCLUSIVE — NO CALLS EXIST TO TEST WITH.")
        print("-" * 72)
        print("This proves NOTHING about entitlement. The account has made no calls in")
        print("the last 3 months, so calls_ai has nothing to return either way.")
        print("NEXT STEP: turn recording ON for the JustCall number (dashboard ->")
        print("Phone Numbers -> Advanced Settings; there is NO API for this), make one")
        print("real recorded call, wait ~5 minutes, then re-run this probe.")
        return 2

    calls.sort(key=lambda c: (str(pick(c, "call_date", default="")),
                             str(pick(c, "call_time", default=""))), reverse=True)
    newest = calls[0]
    sid = call_sid_of(newest)
    print(f"Most recent call: sid={sid} id={pick(newest, 'id')} "
          f"date={pick(newest, 'call_date')} {pick(newest, 'call_time')} "
          f"dir={pick(newest, 'call_direction', 'direction')} "
          f"dur={pick(newest, 'total_duration')}")
    rec = recording_url_of(newest)
    print(f"Recording present on that call: {'YES' if rec else 'NO'}")

    ai_rows, err = fetch_calls_ai(jc, start, end, max_pages=3)

    if err:
        print("\n" + "-" * 72)
        print("VERDICT: NOT ENTITLED — THE calls_ai ENDPOINT REFUSED US.")
        print("-" * 72)
        print(f"  {err}")
        print("Transcription is NOT available on this plan via the API.")
        print("FALLBACK: --download-recordings + transcribe the MP3 with Gemini via")
        print("Vertex (VISION_BACKEND=gemini_vertex, already wired).")
        return 3

    print(f"\ncalls_ai returned {len(ai_rows)} AI record(s) (HTTP 200, "
          f"fetch_transcription=true).")

    with_text = []
    for row in ai_rows:
        state, segs, text = transcript_from_ai(row)
        if state == "available":
            with_text.append((call_sid_of(row), len(segs), text))

    if with_text:
        sid_t, nseg, text = with_text[0]
        print("\n" + "-" * 72)
        print("VERDICT: ENTITLED — A REAL TRANSCRIPT CAME BACK.")
        print("-" * 72)
        print(f"  {len(with_text)} of {len(ai_rows)} AI record(s) carry transcript text.")
        print(f"  Example call_sid={sid_t}, {nseg} segment(s). First 300 chars:")
        print("  " + (text or "")[:300].replace("\n", "\n  "))
        print("\nARCHITECTURE DECISION: use JustCall's own transcripts. No Gemini "
              "fallback needed.")
        return 0

    print("\n" + "-" * 72)
    if not ai_rows:
        print("VERDICT: INCONCLUSIVE — 200 OK, BUT ZERO AI RECORDS.")
        print("-" * 72)
        print("The endpoint works and did NOT refuse us, but returned no AI records for")
        print(f"the {len(calls)} call(s) in the window. Both of these produce this exact")
        print("output and CANNOT be told apart from here:")
        print("  (a) transcription is not enabled/entitled, and JustCall silently")
        print("      returns an empty set rather than a 403;")
        print("  (b) no call in the window was RECORDED (recording is off on the number),")
        print("      so there was no audio to transcribe.")
        print(f"Recording present on the newest call: {'YES' if rec else 'NO'} "
              f"<- if NO, fix that first; it is (b).")
    else:
        print("VERDICT: INCONCLUSIVE — AI RECORDS EXIST BUT CARRY NO TRANSCRIPT TEXT.")
        print("-" * 72)
        print(f"{len(ai_rows)} AI record(s) came back with an empty/absent")
        print("call_transcription array. That is either a plan restriction returned as")
        print("empty rather than as a 403, or calls with no speech (voicemail, no-answer).")
        keys = sorted({k for r in ai_rows for k in r.keys()})
        print(f"Keys actually present on the AI records: {', '.join(keys[:25])}")
    print("\nDO NOT RECORD THIS AS 'ENTITLED'. Re-run after one deliberately recorded")
    print("call with real two-way speech; that run is the one that decides it.")
    return 4


# ─────────────────────────────────────────────────────────────────────────────
# sync
# ─────────────────────────────────────────────────────────────────────────────
def run_sync(args) -> dict:
    client = get_client()
    db = client[DB]
    activity = db[COLL_ACTIVITY]
    now = datetime.now(BRISBANE)

    # ── window ────────────────────────────────────────────────────────────────
    wm_doc = db[COLL_WATERMARK].find_one({"_id": WATERMARK_ID}) or {}
    wm = wm_doc.get("last_synced_to")
    if isinstance(wm, datetime) and wm.tzinfo is None:
        wm = wm.replace(tzinfo=timezone.utc)

    start = now - timedelta(days=args.since)
    gap_warning = None
    if wm:
        # Re-cover everything since the last SUCCESSFUL run, not just --since days: a
        # night that failed must be picked up by the next one, or the 3-month window
        # eats it. Overlap is free (upserts are idempotent); a gap is not.
        if wm < start:
            start = wm - timedelta(hours=1)
        floor = now - timedelta(days=API_RETENTION_DAYS)
        if start < floor:
            gap_warning = (
                f"watermark {wm.isoformat()} is older than the {API_RETENTION_DAYS}-day "
                f"API retention — calls before {floor.date()} are PERMANENTLY "
                f"UNRECOVERABLE via the API")
            print(f"!! {gap_warning}")
            start = floor

    print(f"Window: {fmt_dt(start)} -> {fmt_dt(now)} (Australia/Brisbane)")

    jc = JustCall()

    # ── fetch ─────────────────────────────────────────────────────────────────
    calls, server_total = fetch_calls(jc, start, now)
    calls_seen = len(calls)
    print(f"Calls parsed: {calls_seen}  (server total_count={server_total})")

    ai_by_sid: dict[str, dict] = {}
    entitlement_error: str | None = None
    if calls_seen:
        ai_rows, entitlement_error = fetch_calls_ai(jc, start, now)
        for row in ai_rows:
            sid = call_sid_of(row)
            if sid:
                ai_by_sid[sid] = row
        if entitlement_error:
            print(f"!! calls_ai refused: {entitlement_error}")
        print(f"AI records matched by call_sid: {len(ai_by_sid)}")

    queue_index, queue_by_id = build_queue_index(db)
    print(f"call_queue index: {len(queue_index)} phone key(s), "
          f"{len(queue_by_id)} id(s)"
          + ("  (collection absent — every call will be recorded as unmatched)"
             if not queue_index else ""))

    # ── upsert ────────────────────────────────────────────────────────────────
    ingested = transcripts = recordings = unmatched = matched = skipped = 0
    by_metadata = by_phone = metadata_seen = metadata_unknown = 0

    for call in calls:
        sid = call_sid_of(call)
        if not sid:
            skipped += 1
            print(f"  ! call with no usable id/sid, skipped: {str(call)[:150]}")
            continue

        doc = build_doc(call, ai_by_sid.get(sid), entitlement_error)
        if doc["transcript_state"] == "available":
            transcripts += 1

        key = phone_key(doc.get("contact_number"))
        doc["phone_key"] = key

        # EXACT JOIN FIRST. The dialer deep link carried the queue row's _id, so if
        # it came back we know which row this call belongs to rather than inferring
        # it. Phone matching stays as the fallback for calls placed outside the
        # sheet (Will dialling from his handset), which is a legitimate case.
        meta_id = doc.get("dialer_metadata")
        qrow = None
        match_path = None
        if meta_id:
            metadata_seen += 1
            qrow = queue_by_id.get(meta_id)
            if qrow:
                match_path = "matched_metadata"
                by_metadata += 1
            else:
                # Metadata came back but names a row we do not have. That is a real
                # anomaly (a deleted queue row, or a stale link), not a reason to
                # pretend the metadata was absent — so it is counted and recorded.
                metadata_unknown += 1
        if qrow is None and key:
            qrow = queue_index.get(key)
            if qrow:
                match_path = "matched_phone"
                by_phone += 1

        if qrow:
            matched += 1
            doc["call_queue_id"] = qrow.get("_id")
            doc["matched_address"] = qrow.get("address")
            doc["matched_suburb"] = qrow.get("suburb")
            doc["matched_track"] = qrow.get("track")
            # Kept as the literal path, not a bare "matched": a row joined by an
            # exact id is stronger evidence than one joined by folded phone digits,
            # and anything downstream deserves to be able to tell them apart.
            doc["queue_match"] = match_path
        else:
            unmatched += 1
            # An unmatched call is a FACT, not an error: Will dialling someone by hand
            # is legitimate. Stored explicitly so "no match" is a value, not a silence.
            doc["call_queue_id"] = None
            doc["queue_match"] = (
                "no_queue_collection" if not queue_index
                else "metadata_unknown_id" if meta_id
                else "no_matching_number")

        if args.download_recordings and doc.get("recording_url"):
            rec = download_recording(jc, doc)
            if rec:
                doc["recording_local"] = rec
                recordings += 1

        if args.dry_run:
            ingested += 1
            print(f"  [dry-run] {sid} {doc['call_date']} {doc['call_time']} "
                  f"{doc['direction']} {doc['contact_number']} "
                  f"transcript={doc['transcript_state']} match={doc['queue_match']}")
            continue

        activity.update_one(
            {"call_sid": sid},
            {"$set": doc,
             # first_seen must survive every later re-sync — it is how we know when the
             # row entered the CRM as opposed to when JustCall last changed it.
             "$setOnInsert": {"first_seen": datetime.now(timezone.utc)}},
            upsert=True,
        )
        ingested += 1

        if qrow and not args.dry_run:
            db[COLL_QUEUE].update_one(
                {"_id": qrow["_id"]},
                {"$set": {"status": "called",
                          "last_call_sid": sid,
                          "last_call_at": datetime.now(timezone.utc),
                          "last_call_direction": doc["direction"],
                          "last_call_duration": doc.get("total_duration")},
                 "$addToSet": {"call_sids": sid}},
            )

    print(f"\ningested={ingested} transcripts={transcripts} recordings={recordings} "
          f"matched={matched} (metadata={by_metadata} phone={by_phone}) "
          f"unmatched={unmatched} skipped={skipped} "
          f"api_requests={jc.requests_made}")

    # The metadata field name on /calls is NOT documented — we guess a list of keys
    # (_METADATA_KEYS). Say plainly which way it went, so a wrong guess is a visible
    # line rather than a silent, permanent fallback to the weaker phone join.
    if ingested and not metadata_seen:
        print("   note: no call carried dialer metadata. Either none were placed from "
              "the sheet's call panel, or /calls does not echo it under any key in "
              "_METADATA_KEYS — check a call you know you placed from the panel.")
    if metadata_unknown:
        print(f"   !! {metadata_unknown} call(s) carried metadata naming a call_queue "
              f"row that no longer exists")

    # ── RULE 7b: assert an OUTCOME, not merely that nothing threw ─────────────
    # "No calls to sync" is success. "Calls existed and we ingested none" is failure,
    # and the two must never produce the same heartbeat.
    expected = server_total if isinstance(server_total, int) else calls_seen
    if expected > 0 and ingested == 0:
        raise RuntimeError(
            f"/calls reports {expected} call(s) in {fmt_dt(start)}..{fmt_dt(now)} but we "
            f"ingested 0 (parsed {calls_seen}) — the response shape or the id field has "
            f"changed upstream. Watermark NOT advanced; this window is still owed. "
            f"The API keeps only {API_RETENTION_DAYS} days, so this must be fixed before "
            f"the window closes.")
    if isinstance(server_total, int) and 0 < calls_seen < server_total:
        # Partial parse. Not zero, so the assertion above lets it through — but silently
        # keeping 40 of 300 calls and then advancing the watermark loses the other 260
        # permanently, which is the same failure with a smaller number on it.
        raise RuntimeError(
            f"parsed {calls_seen} of {server_total} call(s) the server reports for this "
            f"window — pagination or parsing is dropping rows. Watermark NOT advanced.")

    if not args.dry_run:
        # Advance ONLY here, on the success path, and never in the exception path above.
        # A dropped night inside a 90-day window becomes permanent data loss the moment
        # a failed run tells the next one it has nothing to do.
        db[COLL_WATERMARK].update_one(
            {"_id": WATERMARK_ID},
            {"$set": {"last_synced_to": now.astimezone(timezone.utc),
                      "last_success_at": datetime.now(timezone.utc),
                      "calls_seen": calls_seen, "calls_ingested": ingested}},
            upsert=True,
        )

    return {
        "calls_seen": calls_seen,
        "calls_ingested": ingested,
        "transcripts_ingested": transcripts,
        "recordings": recordings,
        "unmatched": unmatched,
        "matched": matched,
        "matched_by_metadata": by_metadata,
        "matched_by_phone": by_phone,
        "metadata_present": metadata_seen,
        "metadata_unknown_id": metadata_unknown,
        "skipped_no_sid": skipped,
        "transcript_entitlement": ("refused" if entitlement_error
                                   else ("proven" if transcripts else "unproven")),
        "gap_warning": gap_warning,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", type=int, default=2,
                    help="days back to reconcile (default 2). The stored watermark "
                         "widens this automatically if the last success is older.")
    ap.add_argument("--download-recordings", action="store_true",
                    help="also fetch each call's MP3 to 20_Direct_Phone_Calls/recordings/ "
                         "(gitignored) and store its local path + sha256. Off by default.")
    ap.add_argument("--test-transcription", action="store_true",
                    help="entitlement probe only — no writes, no watermark, no heartbeat.")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and join, print what would be written, write nothing.")
    args = ap.parse_args()

    set_env_from_file()

    if args.test_transcription:
        # Deliberately OUTSIDE job_run: this is a manual diagnostic, and an inconclusive
        # probe must not be able to mark the nightly job green or red.
        return test_transcription(JustCall())

    with job_run("justcall_sync", cadence_hours=24,
                 title="JustCall call+transcript sync") as beat:
        metrics = run_sync(args)
        beat.metrics = metrics
        beat.detail = (
            f"{metrics['calls_ingested']}/{metrics['calls_seen']} calls, "
            f"{metrics['transcripts_ingested']} transcript(s), "
            f"{metrics['matched']} matched / {metrics['unmatched']} unmatched"
            + (f" — {metrics['gap_warning']}" if metrics.get("gap_warning") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
