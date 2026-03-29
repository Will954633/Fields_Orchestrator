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
from router import route_message, opus_full
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

    # --- Model lock: GPT modes stay in direct chat path for reliability ---
    if model_lock in ("gpt54", "gpt54mini"):
        history = await _load_history_safe(timeout=1.0)
        task_id = None
        gpt_model = GPT54_MINI_MODEL if model_lock == "gpt54mini" else GPT54_MODEL
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
        await _append_history_safe("user", user_text, timeout=1.0)
        await _append_history_safe("assistant", reply, timeout=1.0)
        return {"reply": reply, "task_id": task_id, "model_lock": model_lock}

    # --- Model lock: opus → full Opus agent with all tools ---
    if model_lock == "opus":
        history = await _load_history_safe()
        reply = await opus_full(user_text, history)
        # Check if Opus wants to self-downgrade
        if _SWITCH_HAIKU_SIGNAL in reply:
            reply = reply.replace(_SWITCH_HAIKU_SIGNAL, "").strip()
            model_lock = "auto"
            log.info("Model lock → auto (Opus self-downgrade)")
        await _append_history_safe("user", user_text)
        await _append_history_safe("assistant", reply)
        return {"reply": reply, "task_id": None, "model_lock": model_lock}

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

    if decision.get("spawn_task"):
        spawn = decision["spawn_task"]
        task_id = task_manager.spawn_task(
            title=spawn["title"],
            prompt=spawn["prompt"],
            user_message=user_text,
        )
        log.info(f"Task spawned: {task_id} — {spawn['title']}")

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

    log.info(f"Voice request: audio={len(audio_bytes)} bytes")

    # 1. Speech-to-Text
    stt_started = time.perf_counter()
    transcript = await speech_to_text(audio_bytes, audio.filename or "audio.wav")
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


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, authorization: Optional[str] = Header(None)):
    """Cancel a running or queued task."""
    verify_token(authorization)
    cancelled = task_manager.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(400, "Task not found or already finished")
    return JSONResponse({"cancelled": True, "task_id": task_id})


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
