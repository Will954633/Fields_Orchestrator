#!/usr/bin/env python3
"""
Fields Voice Agent — Backend API

Two-tier architecture:
  - Router (Haiku CLI, no tools, ~2-5s): handles all user messages, decides
    whether to respond directly or spawn a background task.
  - Workers (Opus CLI, full tools): up to 3 concurrent background tasks.
  - SSE: pushes task lifecycle events to connected clients.

All Claude calls go through the CLI binary → Max subscription billing.

Endpoints:
  POST /api/voice           — audio in, audio + text out
  POST /api/chat            — text in, text out
  GET  /api/events          — SSE stream (task notifications)
  GET  /api/tasks           — list tasks
  GET  /api/tasks/{id}      — task detail
  POST /api/tasks/{id}/cancel — cancel a task
  GET  /api/health          — health check
  GET  /api/history         — conversation history
  DELETE /api/history       — clear conversation history
"""

import os
import sys
import json
import time
import base64
import asyncio
import logging
import tempfile
import mimetypes
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

# Local modules
from sse import SSEBroadcaster
from task_manager import TaskManager
from router import route_message, opus_full, _opus_email as opus_email
from gpt_agent import gpt_full, gpt_converse, GPT54_MODEL, GPT54_MINI_MODEL

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VOICE_AGENT_TOKEN = os.getenv("VOICE_AGENT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

ORCHESTRATOR_DIR = "/home/fields/Fields_Orchestrator"

STT_MODEL = "gpt-4o-mini-transcribe"
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "nova"

AEST = timezone(timedelta(hours=10))
MAX_HISTORY = 50
CONV_COLL = "voice_agent_conversations"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"{ORCHESTRATOR_DIR}/logs/voice-agent.log"),
    ],
)
log = logging.getLogger("voice-agent")

# ---------------------------------------------------------------------------
# App + shared state
# ---------------------------------------------------------------------------

app = FastAPI(title="Fields Voice Agent", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialised in lifespan (after event loop is ready)
sse_broadcaster: Optional[SSEBroadcaster] = None
task_manager: Optional[TaskManager] = None
_db_client = None

# Model lock: "auto" (router decides), "opus" (always Opus), "haiku" (always direct),
# "gpt54" (GPT-5.4 full agent), "gpt54mini" (GPT-5.4-mini full agent)
model_lock: str = "gpt54mini"
LOCKED_GPT_SYNC_TIMEOUT = 90  # Keep browser requests comfortably under proxy timeout
LOCKED_GPT_ROUTE_TIMEOUT = 8  # Short task-detection pass for GPT lock
VOICE_DEFAULT_MODEL_LOCK = "gpt54mini"


def _get_db():
    """Lazy-init MongoDB client."""
    global _db_client
    if _db_client is None:
        sys.path.insert(0, ORCHESTRATOR_DIR)
        from shared.db import get_client
        _db_client = get_client()
    return _db_client


@app.on_event("startup")
async def startup():
    global sse_broadcaster, task_manager
    sse_broadcaster = SSEBroadcaster()
    client = _get_db()
    task_manager = TaskManager(client, sse_broadcaster)
    log.info("Voice Agent v2.0 started — router + task manager ready")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def verify_token(authorization: Optional[str] = Header(None)):
    if not VOICE_AGENT_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    if authorization.split(" ", 1)[1] != VOICE_AGENT_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


# ---------------------------------------------------------------------------
# Conversation history (MongoDB-backed)
# ---------------------------------------------------------------------------

def _get_conversation_id() -> str:
    """One conversation per day (AEST). Resets at midnight."""
    return f"conv_{datetime.now(AEST).strftime('%Y%m%d')}"


def _load_history() -> list[dict]:
    """Load conversation history from MongoDB."""
    sm = _get_db()["system_monitor"]
    doc = sm[CONV_COLL].find_one({"_id": _get_conversation_id()})
    if doc:
        return doc.get("messages", [])
    return []


def _append_history(role: str, content: str):
    """Append a message to conversation history in MongoDB."""
    sm = _get_db()["system_monitor"]
    conv_id = _get_conversation_id()
    msg = {"role": role, "content": content, "ts": time.time()}

    sm[CONV_COLL].update_one(
        {"_id": conv_id},
        {
            "$push": {
                "messages": {
                    "$each": [msg],
                    "$slice": -MAX_HISTORY * 2,  # Keep last N messages
                }
            },
            "$set": {"updated_at": datetime.now(AEST).isoformat()},
            "$setOnInsert": {"created_at": datetime.now(AEST).isoformat()},
        },
        upsert=True,
    )


async def _load_history_safe(timeout: float = 2.0) -> list[dict]:
    """Best-effort history load. Never let Cosmos block the live voice path."""
    started = time.perf_counter()
    try:
        history = await asyncio.wait_for(asyncio.to_thread(_load_history), timeout=timeout)
        log.info(f"History load: {time.perf_counter() - started:.2f}s ({len(history)} messages)")
        return history
    except Exception as e:
        log.warning(f"History load skipped after {time.perf_counter() - started:.2f}s: {e}")
        return []


async def _append_history_safe(role: str, content: str, timeout: float = 2.0):
    """Best-effort history write. Do not block replies on Cosmos latency."""
    started = time.perf_counter()
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_append_history, role, content),
            timeout=timeout,
        )
        log.info(f"History append ({role}): {time.perf_counter() - started:.2f}s")
    except Exception as e:
        log.warning(f"History append skipped for {role} after {time.perf_counter() - started:.2f}s: {e}")


def _apply_voice_model_policy():
    """Keep live voice on the lower-latency GPT model."""
    global model_lock
    if model_lock == "gpt54":
        model_lock = VOICE_DEFAULT_MODEL_LOCK
        log.info("Model lock → gpt54mini (voice safety downgrade from gpt54)")


def _sniff_audio_extension(audio_bytes: bytes) -> str | None:
    """Infer a safe temp-file extension from common audio container signatures."""
    if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return ".wav"
    if audio_bytes[:4] == b"OggS":
        return ".ogg"
    if audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    if len(audio_bytes) >= 8 and audio_bytes[4:8] == b"ftyp":
        return ".mp4"
    if audio_bytes[:3] == b"ID3" or (len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0):
        return ".mp3"
    return None


def _extension_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    normalized = content_type.split(";", 1)[0].strip().lower()
    manual = {
        "audio/webm": ".webm",
        "video/webm": ".webm",
        "audio/ogg": ".ogg",
        "video/ogg": ".ogg",
        "audio/mp4": ".mp4",
        "video/mp4": ".mp4",
        "audio/x-m4a": ".mp4",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
    }
    return manual.get(normalized) or mimetypes.guess_extension(normalized)


def _resolve_audio_filename(upload: UploadFile, audio_bytes: bytes) -> tuple[str, str | None]:
    sniffed_ext = _sniff_audio_extension(audio_bytes)
    content_type_ext = _extension_from_content_type(upload.content_type)
    original_name = (upload.filename or "").strip()
    original_ext = Path(original_name).suffix.lower() if original_name else ""
    chosen_ext = sniffed_ext or content_type_ext or original_ext or ".wav"
    return f"audio{chosen_ext}", sniffed_ext


# ---------------------------------------------------------------------------
# OpenAI helpers (STT / TTS)
# ---------------------------------------------------------------------------

async def speech_to_text(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribe audio using OpenAI STT."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    suffix = Path(filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        with open(tmp_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                model=STT_MODEL,
                file=audio_file,
                language="en",
            )
        transcript = result.text.strip()
        log.info(f"STT: '{transcript[:100]}...' ({len(audio_bytes)} bytes)")
        return transcript
    finally:
        os.unlink(tmp_path)


async def text_to_speech(text: str, voice: str = TTS_VOICE) -> bytes:
    """Convert text to speech using OpenAI TTS."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    started = time.perf_counter()
    spoken_text = (text or "").strip()
    if not spoken_text:
        spoken_text = "I hit an empty response. Please try again."

    response = client.audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        input=spoken_text[:4096],
        response_format="mp3",
        instructions="Speak clearly and naturally. You are a helpful business and technical assistant.",
    )

    audio_bytes = response.content
    log.info(f"TTS: {time.perf_counter() - started:.2f}s, {len(audio_bytes)} bytes for {len(spoken_text)} chars")
    return audio_bytes


def _sanitize_spoken_text(text: str) -> str:
    spoken = (text or "").strip()
    if not spoken:
        return ""
    spoken = re.sub(r"`+", "", spoken)
    spoken = re.sub(r"\*+", "", spoken)
    spoken = re.sub(r"#+", "", spoken)
    spoken = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", spoken)
    spoken = re.sub(r"\s+", " ", spoken)
    return spoken.strip()


async def summarize_task_for_voice(task: dict) -> str:
    """Generate a short spoken summary for a completed task using the GPT model family."""
    from openai import OpenAI

    task_model = task.get("model")
    if task_model == "gpt54":
        summary_model = GPT54_MODEL
    else:
        summary_model = GPT54_MINI_MODEL

    task_text = (
        task.get("result_full")
        or task.get("result_summary")
        or task.get("error_text")
        or "The task completed, but no detailed result was available."
    )
    status = task.get("status", "completed")
    title = task.get("title", "Background task")
    fallback = _sanitize_spoken_text(task.get("result_summary") or f"{title} {status}.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    system_prompt = (
        "You are preparing a spoken completion update for Will. "
        "Summarize the task result in 1 to 3 short sentences, under 60 words. "
        "Use plain spoken English. Do not use markdown, bullets, code formatting, "
        "backticks, file diffs, or say punctuation aloud. Focus on what was actually done "
        "and any important blocker or outcome."
    )
    user_prompt = (
        f"Task title: {title}\n"
        f"Task status: {status}\n"
        f"Task result:\n{task_text[:6000]}"
    )

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=summary_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=120,
            temperature=0.2,
        )
        spoken = _sanitize_spoken_text(response.choices[0].message.content or "")
        return spoken or fallback or "The task completed."
    except Exception as e:
        log.warning(f"Task voice summary failed for {task.get('_id')}: {e}")
        return fallback or "The task completed."


# ---------------------------------------------------------------------------
# Core message handler
# ---------------------------------------------------------------------------

import re

# Voice trigger patterns (case-insensitive)
_OPUS_TRIGGERS = re.compile(
    r'\b(speak to opus|switch to opus|talk to opus|use opus|opus mode)\b', re.IGNORECASE
)
_HAIKU_TRIGGERS = re.compile(
    r'\b(switch back|back to haiku|switch to haiku|use haiku|haiku mode|back to auto)\b', re.IGNORECASE
)
_GPT54_TRIGGERS = re.compile(
    r'\b(switch to gpt|use gpt|gpt mode|use gpt.?5\.?4\b|switch to gpt.?5\.?4\b)', re.IGNORECASE
)
_GPT54MINI_TRIGGERS = re.compile(
    r'\b(use gpt.?mini|switch to gpt.?mini|gpt.?mini mode|use gpt.?5\.?4.?mini|switch to gpt.?5\.?4.?mini)', re.IGNORECASE
)
# Opus self-downgrade signal
_SWITCH_HAIKU_SIGNAL = "[SWITCH_HAIKU]"
_EMAIL_TASK_PATTERNS = [
    re.compile(r"\b(check|scan|review|search|read|open)\b.*\b(email|emails|inbox|mail)\b", re.IGNORECASE),
    re.compile(r"\b(email|emails|inbox|mail)\b.*\b(check|scan|review|search|read|open)\b", re.IGNORECASE),
    re.compile(r"\bwhat emails\b.*\b(reply|respond)\b", re.IGNORECASE),
    re.compile(r"\bwhich emails\b.*\b(reply|respond)\b", re.IGNORECASE),
    re.compile(r"\bneed to (reply|respond)\b.*\b(email|emails)\b", re.IGNORECASE),
    re.compile(r"\b(draft|reply|respond|send)\b.*\b(email|mail)\b", re.IGNORECASE),
]
_DEV_TASK_PATTERNS = [
    re.compile(r"\b(build|write|edit|change|update|modify|implement|fix|debug|refactor|patch)\b.*\b(code|file|script|app|server|ui|backend|frontend|feature|bug|test|tests)\b", re.IGNORECASE),
    re.compile(r"\b(code|file|script|app|server|ui|backend|frontend|feature|bug|test|tests)\b.*\b(build|write|edit|change|update|modify|implement|fix|debug|refactor|patch)\b", re.IGNORECASE),
    re.compile(r"\b(read|inspect|review)\b.*\b(code|repo|repository|project|files)\b", re.IGNORECASE),
    re.compile(r"\b(run|execute)\b.*\b(test|tests|pytest|script|build)\b", re.IGNORECASE),
    re.compile(r"\b(create|make|mkdir|add|remove|delete|rename|move)\b.*\b(folder|directory|dir|file|files)\b", re.IGNORECASE),
    re.compile(r"\b(folder|directory|dir|file|files)\b.*\b(create|make|mkdir|add|remove|delete|rename|move)\b", re.IGNORECASE),
    re.compile(r"\b(start|continue)\b.*\b(building|coding|developing|implementation)\b", re.IGNORECASE),
    re.compile(r"\bactual code\b", re.IGNORECASE),
    re.compile(r"\bactual dev(?:elopment)? work\b", re.IGNORECASE),
    re.compile(r"\b(code|dev(?:elopment)?)(?:\s+work)?\b.*\b(done|now|immediately|again)\b", re.IGNORECASE),
]
_DEV_APPROVAL_PATTERNS = [
    re.compile(r"^\s*proceed[.!]?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:sure[,.! ]*|yes[,.! ]*|okay[,.! ]*|ok[,.! ]*)*(go ahead|go ahead and do it|go ahead and start)[.!]?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(yes[,.! ]*)?(do it|start now|do that now)[.!]?\s*$", re.IGNORECASE),
    re.compile(r"\btry again\b.*\b(code|dev(?:elopment)?)(?:\s+work)?\b.*\b(now|done)\b", re.IGNORECASE),
]
_DEV_CONTEXT_PATTERNS = [
    *_DEV_TASK_PATTERNS,
    re.compile(r"\bbackground task\b", re.IGNORECASE),
    re.compile(r"\bcode change\b", re.IGNORECASE),
    re.compile(r"\bdev work\b", re.IGNORECASE),
    re.compile(r"\bworking done\b", re.IGNORECASE),
]


def _recent_history_context(history: list[dict], limit: int = 6) -> str:
    recent = []
    for msg in history[-limit:]:
        role = msg.get("role", "user")
        content = (msg.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        recent.append(f"{role}: {content[:600]}")
    return "\n".join(recent)


def _augment_task_prompt(base_prompt: str, history: list[dict]) -> str:
    history_context = _recent_history_context(history)
    if not history_context:
        return base_prompt
    return (
        f"{base_prompt}\n\n"
        "Recent conversation context:\n"
        f"{history_context}\n\n"
        "If the latest request refers to earlier discussion, use that context. "
        "Do the concrete work on the VM rather than only describing a plan."
    )


def _history_mentions_dev_work(history: list[dict], limit: int = 8) -> bool:
    for msg in history[-limit:]:
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if any(pattern.search(content) for pattern in _DEV_CONTEXT_PATTERNS):
            return True
    return False


def _build_contextual_dev_task(user_text: str, history: list[dict]) -> Optional[dict]:
    """Treat short approvals as executable dev requests when recent context is already dev-focused."""
    if not any(pattern.search(user_text) for pattern in _DEV_APPROVAL_PATTERNS):
        return None
    if not _history_mentions_dev_work(history):
        return None

    recent_context = _recent_history_context(history)
    prompt = (
        f"The user just approved or re-authorised previously discussed dev work: {user_text}\n"
        "Infer the concrete coding task from the recent conversation context included below. "
        "Do the actual work on the VM now: inspect the code, make the needed change, verify it, "
        "and report what you actually changed. Do not stay in planning or chat mode.\n\n"
        "Recent conversation context:\n"
        f"{recent_context}\n\n"
        "If the latest request refers to earlier discussion, use that context. "
        "Do the concrete work on the VM rather than only describing a plan."
    )
    return {
        "title": "Continue approved development task",
        "reply": "On it. I’m running the approved dev work on the VM now.",
        "prompt": prompt,
    }


def _build_fast_email_task(user_text: str) -> Optional[dict]:
    """Fast-path clear email intents so GPT voice does not wait on router timeouts."""
    if not any(pattern.search(user_text) for pattern in _EMAIL_TASK_PATTERNS):
        return None

    lowered = user_text.lower()
    if "what emails" in lowered or "which emails" in lowered or "need to reply" in lowered or "need to respond" in lowered:
        title = "Review inbox for replies"
        reply = "On it. I'll check your inbox and identify the emails that need a reply."
        prompt = (
            "Review Will's email inbox using the VM email tooling and identify which emails need a reply. "
            "Use python3 scripts/fields-email.py to inspect the inbox, recent messages, relevant threads, "
            "and the specialized email memory in config/email_memory.json / config/email_memory.md. "
            "Record useful relevance decisions with memory-set-relevance when the signal is clear. "
            "Return a concise shortlist with sender, subject, why it needs a reply, urgency, and whether it is relevant or ignorable. "
            "If a reply is likely needed, say that a recipient-aware draft can be prepared next using recipient-profile and draft-reply. "
            "Do not send anything. Keep all outbound actions in dry-run only."
        )
    elif "search" in lowered:
        title = "Search email"
        reply = "On it. I'll search your email now."
        prompt = (
            f"Handle this email request using python3 scripts/fields-email.py: {user_text}\n"
            "Use the email CLI to search and inspect the relevant messages, and check email memory when relevance is ambiguous. "
            "Summarize the useful results clearly. If the request points toward drafting a reply, "
            "use recipient-profile before draft-reply so the response reflects historical context and recipient style. "
            "Do not send anything unless explicitly requested, and use --dry-run first for any draft/send action."
        )
    else:
        title = "Handle email request"
        reply = "On it. I'll handle that through your email tools now."
        prompt = (
            f"Handle this email request using python3 scripts/fields-email.py: {user_text}\n"
            "Read/search/review the relevant emails and complete the request as far as possible. "
            "Use the specialized email memory in config/email_memory.json and config/email_memory.md to track relevance and recipient preferences. "
            "When drafting or replying, always run recipient-profile first, then use draft-reply so the draft reflects historical emails, recipient-specific tone, and first-contact defaults when there is no history. "
            "Show the draft clearly, and assume it needs to be read back to Will before any send. "
            "For replies or sends, always use --dry-run first and present the draft for approval before any live send."
        )

    return {"title": title, "reply": reply, "prompt": prompt}


def _build_fast_dev_task(user_text: str) -> Optional[dict]:
    """Fast-path clear coding intents so GPT lock launches a worker instead of debating."""
    if not any(pattern.search(user_text) for pattern in _DEV_TASK_PATTERNS):
        return None

    lowered = user_text.lower()
    if any(word in lowered for word in ("run the test", "run tests", "pytest", "test suite", "build the app", "run the build")):
        title = "Run development checks"
        reply = "On it. I'll run the relevant development checks and work through the results."
    elif any(word in lowered for word in ("folder", "directory", "mkdir", "file", "files")) and any(
        word in lowered for word in ("create", "make", "add", "remove", "delete", "rename", "move")
    ):
        title = "Handle VM filesystem task"
        reply = "On it. I'll make that filesystem change on the VM now."
    elif any(word in lowered for word in ("fix", "debug", "patch", "bug")):
        title = "Fix development issue"
        reply = "On it. I'll inspect the code, make the fix, and verify it."
    elif any(word in lowered for word in ("read", "inspect", "review")):
        title = "Review codebase"
        reply = "On it. I'll inspect the relevant code and work from there."
    else:
        title = "Handle development task"
        reply = "On it. I'll start the dev work now."

    prompt = (
        f"Handle this development request on the VM: {user_text}\n"
        "Inspect the relevant code and files, make the necessary changes or run the needed checks, "
        "verify the result, and report what you actually did. If the request is ambiguous, use the "
        "recent conversation context included below to infer the concrete work."
    )
    return {"title": title, "reply": reply, "prompt": prompt}


async def handle_message(user_text: str) -> dict:
    """
    Handle a user message. Checks voice triggers first, then routes.

    Returns:
        {"reply": str, "task_id": str | None, "model_lock": str}
    """
    global model_lock

    # --- Voice trigger detection (skip router entirely) ---
    if _GPT54MINI_TRIGGERS.search(user_text):
        model_lock = "gpt54mini"
        log.info("Model lock → gpt54mini (voice trigger)")
        reply = "Switched to GPT-5.4-mini. Full tools available."
        _append_history("user", user_text)
        _append_history("assistant", reply)
        return {"reply": reply, "task_id": None, "model_lock": model_lock}

    if _GPT54_TRIGGERS.search(user_text):
        model_lock = "gpt54"
        log.info("Model lock → gpt54 (voice trigger)")
        reply = "Switched to GPT-5.4. Full tools available."
        _append_history("user", user_text)
        _append_history("assistant", reply)
        return {"reply": reply, "task_id": None, "model_lock": model_lock}

    if _OPUS_TRIGGERS.search(user_text):
        model_lock = "opus"
        log.info("Model lock → opus (voice trigger)")
        reply = "Switched to Opus. I'm listening."
        _append_history("user", user_text)
        _append_history("assistant", reply)
        return {"reply": reply, "task_id": None, "model_lock": model_lock}

    if _HAIKU_TRIGGERS.search(user_text):
        model_lock = "auto"
        log.info("Model lock → auto (voice trigger)")
        reply = "Switched back. Haiku on routing duty."
        _append_history("user", user_text)
        _append_history("assistant", reply)
        return {"reply": reply, "task_id": None, "model_lock": model_lock}

    # --- Model lock: GPT modes can spawn GPT tasks, otherwise stay in direct chat ---
    if model_lock in ("gpt54", "gpt54mini"):
        history = await _load_history_safe(timeout=1.0)
        task_id = None
        gpt_model = GPT54_MINI_MODEL if model_lock == "gpt54mini" else GPT54_MODEL
        fast_dev_task = _build_fast_dev_task(user_text)
        if fast_dev_task:
            prompt = _augment_task_prompt(fast_dev_task["prompt"], history)
            task_id = task_manager.spawn_task(
                title=fast_dev_task["title"],
                prompt=prompt,
                user_message=user_text,
                model=model_lock,
            )
            reply = fast_dev_task["reply"]
            log.info(f"GPT fast dev task spawned: {task_id} — {fast_dev_task['title']} (model: {model_lock})")
            await _append_history_safe("user", user_text, timeout=1.0)
            await _append_history_safe("assistant", reply, timeout=1.0)
            return {"reply": reply, "task_id": task_id, "model_lock": model_lock}

        contextual_dev_task = _build_contextual_dev_task(user_text, history)
        if contextual_dev_task:
            prompt = _augment_task_prompt(contextual_dev_task["prompt"], history)
            task_id = task_manager.spawn_task(
                title=contextual_dev_task["title"],
                prompt=prompt,
                user_message=user_text,
                model=model_lock,
            )
            reply = contextual_dev_task["reply"]
            log.info(f"GPT contextual dev task spawned: {task_id} — {contextual_dev_task['title']} (model: {model_lock})")
            await _append_history_safe("user", user_text, timeout=1.0)
            await _append_history_safe("assistant", reply, timeout=1.0)
            return {"reply": reply, "task_id": task_id, "model_lock": model_lock}

        fast_email_task = _build_fast_email_task(user_text)
        if fast_email_task:
            # Email requests are handled conversationally by Opus (not background tasks)
            log.info(f"Email request detected (fast-path): routing to opus_email")
            reply = await opus_email(user_text, history)
            if _SWITCH_HAIKU_SIGNAL in reply:
                reply = reply.replace(_SWITCH_HAIKU_SIGNAL, "").strip()
            await _append_history_safe("user", user_text, timeout=1.0)
            await _append_history_safe("assistant", reply, timeout=1.0)
            return {"reply": reply, "task_id": None, "model_lock": model_lock}

        active_tasks = task_manager.get_active_tasks()
        completed_unnotified = task_manager.get_unnotified_completed()

        try:
            decision = await asyncio.wait_for(
                route_message(
                    user_text,
                    history,
                    active_tasks,
                    completed_unnotified,
                    force_direct=True,
                ),
                timeout=LOCKED_GPT_ROUTE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.warning(
                f"Locked GPT task detection timed out after {LOCKED_GPT_ROUTE_TIMEOUT}s "
                f"(model: {model_lock})"
            )
            decision = {"reply": "", "spawn_task": None}

        if decision.get("spawn_task"):
            spawn = decision["spawn_task"]
            prompt = _augment_task_prompt(spawn["prompt"], history)
            task_id = task_manager.spawn_task(
                title=spawn["title"],
                prompt=prompt,
                user_message=user_text,
                model=model_lock,
            )
            reply = decision["reply"]
            log.info(f"GPT task spawned: {task_id} — {spawn['title']} (model: {model_lock})")
            if completed_unnotified:
                task_manager.mark_notified([t["_id"] for t in completed_unnotified])
            await _append_history_safe("user", user_text, timeout=1.0)
            await _append_history_safe("assistant", reply, timeout=1.0)
            return {"reply": reply, "task_id": task_id, "model_lock": model_lock}

        try:
            reply = await asyncio.wait_for(
                gpt_converse(user_text, history, model=gpt_model),
                timeout=LOCKED_GPT_SYNC_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.error(f"Locked GPT sync reply timed out after {LOCKED_GPT_SYNC_TIMEOUT}s (model: {model_lock})")
            reply = (
                "That took too long to answer in-chat. "
                "Please try again or switch to Opus for VM task execution."
            )
        if completed_unnotified:
            task_manager.mark_notified([t["_id"] for t in completed_unnotified])
        await _append_history_safe("user", user_text, timeout=1.0)
        await _append_history_safe("assistant", reply, timeout=1.0)
        return {"reply": reply, "task_id": task_id, "model_lock": model_lock}

    # --- Model lock: opus → dev tasks go to background, chat stays synchronous ---
    if model_lock == "opus":
        history = await _load_history_safe()
        task_id = None

        # Dev tasks → background worker (prevents 5-min blocking + empty stdout)
        fast_dev_task = _build_fast_dev_task(user_text)
        if fast_dev_task:
            prompt = _augment_task_prompt(fast_dev_task["prompt"], history)
            task_id = task_manager.spawn_task(
                title=fast_dev_task["title"],
                prompt=prompt,
                user_message=user_text,
                model="opus",
            )
            reply = fast_dev_task["reply"]
            log.info(f"Opus dev task spawned as background: {task_id} — {fast_dev_task['title']}")
            await _append_history_safe("user", user_text)
            await _append_history_safe("assistant", reply)
            return {"reply": reply, "task_id": task_id, "model_lock": model_lock}

        # Contextual dev approvals → background worker
        contextual_dev_task = _build_contextual_dev_task(user_text, history)
        if contextual_dev_task:
            prompt = _augment_task_prompt(contextual_dev_task["prompt"], history)
            task_id = task_manager.spawn_task(
                title=contextual_dev_task["title"],
                prompt=prompt,
                user_message=user_text,
                model="opus",
            )
            reply = contextual_dev_task["reply"]
            log.info(f"Opus contextual dev task spawned: {task_id} — {contextual_dev_task['title']}")
            await _append_history_safe("user", user_text)
            await _append_history_safe("assistant", reply)
            return {"reply": reply, "task_id": task_id, "model_lock": model_lock}

        # Email → opus_email (conversational with tools)
        fast_email_task = _build_fast_email_task(user_text)
        if fast_email_task:
            log.info("Opus mode email request → opus_email")
            reply = await opus_email(user_text, history)
            if _SWITCH_HAIKU_SIGNAL in reply:
                reply = reply.replace(_SWITCH_HAIKU_SIGNAL, "").strip()
            await _append_history_safe("user", user_text)
            await _append_history_safe("assistant", reply)
            return {"reply": reply, "task_id": None, "model_lock": model_lock}

        # Everything else → synchronous opus_full (conversation, questions, etc.)
        reply = await opus_full(user_text, history)
        if _SWITCH_HAIKU_SIGNAL in reply:
            reply = reply.replace(_SWITCH_HAIKU_SIGNAL, "").strip()
            model_lock = "auto"
            log.info("Model lock → auto (Opus self-downgrade)")
        await _append_history_safe("user", user_text)
        await _append_history_safe("assistant", reply)
        return {"reply": reply, "task_id": task_id, "model_lock": model_lock}

    # --- Model lock: haiku → always direct (no Opus converse) ---
    # (still allows task spawning — that's work, not conversation)

    history = await _load_history_safe()

    # --- Normal routing (auto mode or haiku mode) ---
    active_tasks = task_manager.get_active_tasks()
    completed_unnotified = task_manager.get_unnotified_completed()

    decision = await route_message(
        user_text, history, active_tasks, completed_unnotified,
        force_direct=(model_lock == "haiku"),
    )

    reply = decision["reply"]
    task_id = None
    mode = decision.get("mode", "direct")

    if decision.get("spawn_task"):
        spawn = decision["spawn_task"]
        task_id = task_manager.spawn_task(
            title=spawn["title"],
            prompt=spawn["prompt"],
            user_message=user_text,
        )
        log.info(f"Task spawned: {task_id} — {spawn['title']}")

    # Check for SWITCH_HAIKU signal from email/converse modes
    if mode in ("email", "converse") and _SWITCH_HAIKU_SIGNAL in reply:
        reply = reply.replace(_SWITCH_HAIKU_SIGNAL, "").strip()
        log.info(f"Model lock → auto (Opus self-downgrade from {mode})")

    if completed_unnotified:
        task_manager.mark_notified([t["_id"] for t in completed_unnotified])

    await _append_history_safe("user", user_text)
    await _append_history_safe("assistant", reply)

    return {"reply": reply, "task_id": task_id, "model_lock": model_lock}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.now(AEST).isoformat(),
        "model": {"router": "claude-haiku", "worker": "claude-opus"},
        "active_workers": task_manager.active_count if task_manager else 0,
    }


@app.post("/api/voice")
async def voice_endpoint(
    audio: UploadFile = File(...),
    mode: str = Form("work"),  # backward compat, ignored
    authorization: Optional[str] = Header(None),
):
    """Main voice endpoint: audio in → audio + text out."""
    verify_token(authorization)
    _apply_voice_model_policy()
    request_started = time.perf_counter()

    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(400, "Audio too short")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio too large (max 25MB)")

    resolved_name, sniffed_ext = _resolve_audio_filename(audio, audio_bytes)
    log.info(
        "Voice request: audio=%s bytes filename=%s content_type=%s resolved_name=%s sniffed_ext=%s",
        len(audio_bytes),
        audio.filename or "",
        audio.content_type or "",
        resolved_name,
        sniffed_ext or "",
    )

    # 1. Speech-to-Text
    stt_started = time.perf_counter()
    try:
        transcript = await speech_to_text(audio_bytes, resolved_name)
    except Exception as e:
        error_text = str(e)
        log.warning(f"STT failed for voice request ({len(audio_bytes)} bytes): {error_text[:300]}")
        if "Audio file might be corrupted or unsupported" in error_text:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Audio file might be corrupted or unsupported. Please try again.",
                    "transcript": "",
                },
            )
        return JSONResponse(
            status_code=502,
            content={
                "error": "Speech-to-text failed before the request could be processed.",
                "transcript": "",
            },
        )
    stt_elapsed = time.perf_counter() - stt_started
    if not transcript:
        return JSONResponse({"error": "Could not transcribe audio", "transcript": ""})

    # 2. Router (fast ~2-5s)
    handle_started = time.perf_counter()
    result = await handle_message(transcript)
    handle_elapsed = time.perf_counter() - handle_started
    reply_text = (result.get("reply") or "").strip()
    if not reply_text:
        reply_text = "I hit an empty response. Please try again."
        result["reply"] = reply_text

    # 3. Text-to-Speech
    tts_started = time.perf_counter()
    tts_audio = await text_to_speech(reply_text)
    tts_elapsed = time.perf_counter() - tts_started
    audio_b64 = base64.b64encode(tts_audio).decode()
    total_elapsed = time.perf_counter() - request_started
    log.info(
        f"Voice timing: stt={stt_elapsed:.2f}s handle={handle_elapsed:.2f}s "
        f"tts={tts_elapsed:.2f}s total={total_elapsed:.2f}s model={result.get('model_lock', model_lock)}"
    )

    return JSONResponse({
        "transcript": transcript,
        "reply": result["reply"],
        "task_id": result.get("task_id"),
        "model_lock": result.get("model_lock", model_lock),
        "audio_base64": audio_b64,
        "audio_format": "mp3",
    })


@app.post("/api/chat")
async def chat_endpoint(
    text: str = Form(...),
    mode: str = Form("work"),  # backward compat, ignored
    authorization: Optional[str] = Header(None),
):
    """Text-only endpoint."""
    verify_token(authorization)

    log.info(f"Chat request: text='{text[:100]}'")
    result = await handle_message(text)

    return JSONResponse({
        "reply": result["reply"],
        "task_id": result.get("task_id"),
        "model_lock": result.get("model_lock", model_lock),
    })


# ---------------------------------------------------------------------------
# Model lock endpoint
# ---------------------------------------------------------------------------

@app.post("/api/model")
async def set_model(
    lock: str = Form(...),
    authorization: Optional[str] = Header(None),
):
    """Set model lock: 'auto', 'opus', 'haiku', 'gpt54', or 'gpt54mini'."""
    global model_lock
    verify_token(authorization)

    valid = ("auto", "opus", "haiku", "gpt54", "gpt54mini")
    if lock not in valid:
        raise HTTPException(400, f"lock must be one of: {', '.join(valid)}")

    model_lock = lock
    log.info(f"Model lock set to: {lock}")
    return JSONResponse({"model_lock": lock})


@app.get("/api/model")
async def get_model(authorization: Optional[str] = Header(None)):
    """Get current model lock state."""
    verify_token(authorization)
    return JSONResponse({"model_lock": model_lock})


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------

@app.get("/api/events")
async def sse_endpoint(authorization: Optional[str] = Header(None)):
    """Server-Sent Events stream for task notifications."""
    verify_token(authorization)
    return StreamingResponse(
        sse_broadcaster.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------

@app.get("/api/tasks")
async def list_tasks(authorization: Optional[str] = Header(None)):
    """List active + recent tasks."""
    verify_token(authorization)
    tasks = task_manager.get_recent_tasks(limit=20)
    # Convert ObjectId/datetime for JSON serialization
    for t in tasks:
        t["_id"] = str(t["_id"])
    return JSONResponse({"tasks": tasks})


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, authorization: Optional[str] = Header(None)):
    """Get full task detail including result."""
    verify_token(authorization)
    task = task_manager.get_task_detail(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task["_id"] = str(task["_id"])
    return JSONResponse({"task": task})


@app.get("/api/tasks/{task_id}/voice-summary")
async def get_task_voice_summary(task_id: str, authorization: Optional[str] = Header(None)):
    """Return a spoken task summary using the normal backend voice path."""
    verify_token(authorization)
    task = task_manager.get_task_detail(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    spoken_text = await summarize_task_for_voice(task)
    tts_audio = await text_to_speech(spoken_text)
    audio_b64 = base64.b64encode(tts_audio).decode()
    return JSONResponse({
        "task_id": task_id,
        "spoken_text": spoken_text,
        "audio_base64": audio_b64,
        "audio_format": "mp3",
    })


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, authorization: Optional[str] = Header(None)):
    """Cancel a running or queued task."""
    verify_token(authorization)
    cancelled = task_manager.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(400, "Task not found or already finished")
    return JSONResponse({"cancelled": True, "task_id": task_id})


# ---------------------------------------------------------------------------
# Todo endpoints
# ---------------------------------------------------------------------------

@app.get("/api/todos")
async def list_todos(authorization: Optional[str] = Header(None)):
    """List open todos for the UI panel."""
    verify_token(authorization)
    sm = _get_db()["system_monitor"]
    todos = list(sm["user_todos"].find({"status": "open"}))

    now = datetime.now(AEST)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    result = []
    for t in todos:
        due = t.get("due_date")
        days_left = None
        urgency = ""
        if due:
            if isinstance(due, str):
                due = datetime.fromisoformat(due)
            if due.tzinfo is None:
                due = due.replace(tzinfo=AEST)
            due_day = due.replace(hour=0, minute=0, second=0, microsecond=0)
            days_left = (due_day - today_start).days
            if days_left < 0:
                urgency = f"OVERDUE by {abs(days_left)}d"
            elif days_left == 0:
                urgency = "DUE TODAY"
            elif days_left == 1:
                urgency = "due tomorrow"
            elif days_left <= 7:
                urgency = f"due in {days_left}d"
            else:
                urgency = f"due in {days_left}d"

        result.append({
            "_id": str(t["_id"]),
            "title": t.get("title", ""),
            "priority": t.get("priority", "medium"),
            "due_date": due.isoformat() if due else None,
            "days_left": days_left,
            "urgency": urgency,
            "tags": t.get("tags", []),
            "notes": t.get("notes", ""),
            "source": t.get("source", ""),
            "created_at": t.get("created_at", ""),
        })

    # Sort: overdue first, then priority, then due date
    def sort_key(item):
        d = item["days_left"] if item["days_left"] is not None else 999
        pri = {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item["priority"], 4)
        return (0 if d < 0 else 1, pri, d)

    result.sort(key=sort_key)
    return JSONResponse({"todos": result, "count": len(result)})


@app.post("/api/todos/{todo_id}/done")
async def complete_todo(todo_id: str, authorization: Optional[str] = Header(None)):
    """Mark a todo as done."""
    verify_token(authorization)
    sm = _get_db()["system_monitor"]
    from bson import ObjectId
    try:
        result = sm["user_todos"].update_one(
            {"_id": ObjectId(todo_id)},
            {"$set": {"status": "done", "completed_at": datetime.now(AEST), "updated_at": datetime.now(AEST)}}
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Todo not found")
        return JSONResponse({"completed": True, "todo_id": todo_id})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/todos/{todo_id}/snooze")
async def snooze_todo(
    todo_id: str,
    days: int = Form(3),
    authorization: Optional[str] = Header(None),
):
    """Snooze a todo by N days."""
    verify_token(authorization)
    sm = _get_db()["system_monitor"]
    from bson import ObjectId
    try:
        todo = sm["user_todos"].find_one({"_id": ObjectId(todo_id)})
        if not todo:
            raise HTTPException(404, "Todo not found")

        current_due = todo.get("due_date") or datetime.now(AEST)
        if isinstance(current_due, str):
            current_due = datetime.fromisoformat(current_due)
        if current_due.tzinfo is None:
            current_due = current_due.replace(tzinfo=AEST)

        today = datetime.now(AEST).replace(hour=0, minute=0, second=0, microsecond=0)
        base = max(current_due, today)
        new_due = base + timedelta(days=days)

        sm["user_todos"].update_one(
            {"_id": ObjectId(todo_id)},
            {"$set": {"due_date": new_due, "reminder_sent": False, "updated_at": datetime.now(AEST)}}
        )
        return JSONResponse({"snoozed": True, "todo_id": todo_id, "new_due": new_due.isoformat()})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# History endpoints
# ---------------------------------------------------------------------------

@app.get("/api/history")
async def get_history(authorization: Optional[str] = Header(None)):
    verify_token(authorization)
    return JSONResponse({"history": _load_history()})


@app.delete("/api/history")
async def clear_history(authorization: Optional[str] = Header(None)):
    verify_token(authorization)
    sm = _get_db()["system_monitor"]
    sm[CONV_COLL].delete_one({"_id": _get_conversation_id()})
    return JSONResponse({"cleared": True})


# ---------------------------------------------------------------------------
# Static files — serve web app at /voice/
# ---------------------------------------------------------------------------

WEB_DIR = Path(__file__).parent / "web"
if WEB_DIR.exists():
    app.mount("/voice", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting Fields Voice Agent API v2.0...")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8090,
        log_level="info",
        reload=False,
    )
