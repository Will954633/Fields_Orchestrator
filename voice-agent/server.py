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
from router import route_message

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

    response = client.audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        input=text[:4096],
        response_format="mp3",
        instructions="Speak clearly and naturally. You are a helpful business and technical assistant.",
    )

    audio_bytes = response.content
    log.info(f"TTS: {len(audio_bytes)} bytes for {len(text)} chars")
    return audio_bytes


# ---------------------------------------------------------------------------
# Core message handler
# ---------------------------------------------------------------------------

async def handle_message(user_text: str) -> dict:
    """
    Handle a user message through the router.

    Returns:
        {"reply": str, "task_id": str | None}
    """
    history = _load_history()
    active_tasks = task_manager.get_active_tasks()
    completed_unnotified = task_manager.get_unnotified_completed()

    # Route through Haiku (fast, no tools)
    decision = await route_message(user_text, history, active_tasks, completed_unnotified)

    reply = decision["reply"]
    task_id = None

    # Spawn background task if router decided to
    if decision.get("spawn_task"):
        spawn = decision["spawn_task"]
        task_id = task_manager.spawn_task(
            title=spawn["title"],
            prompt=spawn["prompt"],
            user_message=user_text,
        )
        log.info(f"Task spawned: {task_id} — {spawn['title']}")

    # Mark completed tasks as notified (router has incorporated them into reply)
    if completed_unnotified:
        task_manager.mark_notified([t["_id"] for t in completed_unnotified])

    # Store conversation
    _append_history("user", user_text)
    _append_history("assistant", reply)

    return {"reply": reply, "task_id": task_id}


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

    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(400, "Audio too short")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio too large (max 25MB)")

    log.info(f"Voice request: audio={len(audio_bytes)} bytes")

    # 1. Speech-to-Text
    transcript = await speech_to_text(audio_bytes, audio.filename or "audio.wav")
    if not transcript:
        return JSONResponse({"error": "Could not transcribe audio", "transcript": ""})

    # 2. Router (fast ~2-5s)
    result = await handle_message(transcript)

    # 3. Text-to-Speech
    tts_audio = await text_to_speech(result["reply"])
    audio_b64 = base64.b64encode(tts_audio).decode()

    return JSONResponse({
        "transcript": transcript,
        "reply": result["reply"],
        "task_id": result["task_id"],
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
        "task_id": result["task_id"],
    })


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
