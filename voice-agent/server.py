#!/usr/bin/env python3
"""
Fields Voice Agent — Backend API
Receives audio/text from web or Android app, processes through STT → LLM → TTS pipeline.
Single unified agent: Claude Code (Opus) with full VM access — same as terminal.

Endpoints:
  POST /api/voice       — audio in, audio + text out
  POST /api/chat        — text in, text out
  GET  /api/health      — health check
  GET  /api/history     — conversation history
  DELETE /api/history   — clear conversation history
"""

import os
import sys
import json
import time
import base64
import asyncio
import logging
import tempfile
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VOICE_AGENT_TOKEN = os.getenv("VOICE_AGENT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

CLAUDE_BIN = "/usr/bin/claude"
ORCHESTRATOR_DIR = "/home/fields/Fields_Orchestrator"
MEMORY_DIR = "/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory"

STT_MODEL = "gpt-4o-mini-transcribe"
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "nova"  # Clear, friendly voice

AEST = timezone(timedelta(hours=10))

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
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Fields Voice Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory conversation history
conversation_history: list[dict] = []
MAX_HISTORY = 50

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def verify_token(authorization: Optional[str] = Header(None)):
    if not VOICE_AGENT_TOKEN:
        return  # No token configured = open (dev mode)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    if authorization.split(" ", 1)[1] != VOICE_AGENT_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

# ---------------------------------------------------------------------------
# OpenAI helpers
# ---------------------------------------------------------------------------

async def speech_to_text(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribe audio using OpenAI STT."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Write to temp file (OpenAI SDK needs a file-like object)
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
        input=text[:4096],  # TTS has input length limits
        response_format="mp3",
        instructions="Speak clearly and naturally. You are a helpful business and technical assistant.",
    )

    audio_bytes = response.content
    log.info(f"TTS: {len(audio_bytes)} bytes for {len(text)} chars")
    return audio_bytes

# ---------------------------------------------------------------------------
# LLM backends
# ---------------------------------------------------------------------------

def _load_context_docs() -> dict:
    """Load shared context documents that both modes use."""
    docs = {}

    # CLAUDE.md — full project instructions
    claude_md_path = Path(ORCHESTRATOR_DIR) / "CLAUDE.md"
    if claude_md_path.exists():
        docs["claude_md"] = claude_md_path.read_text()

    # MEMORY.md — persistent memory index
    memory_path = Path(MEMORY_DIR) / "MEMORY.md"
    if memory_path.exists():
        docs["memory_md"] = memory_path.read_text()

    # Load individual memory files referenced in MEMORY.md
    memory_details = []
    memory_dir = Path(MEMORY_DIR)
    if memory_dir.exists():
        for f in sorted(memory_dir.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            content = f.read_text().strip()
            if content:
                memory_details.append(f"### {f.stem}\n{content}")
    docs["memory_files"] = "\n\n".join(memory_details) if memory_details else ""

    # OPS_STATUS.md — live system status
    ops_path = Path(ORCHESTRATOR_DIR) / "OPS_STATUS.md"
    if ops_path.exists():
        docs["ops_status"] = ops_path.read_text()

    return docs


def _build_append_prompt() -> str:
    """Build supplementary context prompt with memory and ops status."""
    docs = _load_context_docs()

    return f"""This is a voice/chat interface — keep responses to 2-3 sentences unless asked for detail.
Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}

=== PERSISTENT MEMORY ===
{docs.get('memory_md', '')}

=== MEMORY FILES ===
{docs.get('memory_files', '')}

=== LIVE OPS STATUS ===
{docs.get('ops_status', '')}"""


async def llm_claude(user_text: str) -> str:
    """Route to Claude Code (Opus) with full VM access — no restrictions."""
    # Build conversation context from recent history
    context_lines = []
    for msg in conversation_history[-10:]:  # Last 10 exchanges
        role = msg["role"]
        context_lines.append(f"{role}: {msg['content'][:500]}")

    prompt_parts = []
    if context_lines:
        prompt_parts.append("Recent conversation:\n" + "\n".join(context_lines))
    prompt_parts.append(f"User: {user_text}")
    prompt_parts.append("\nRespond concisely (this is voice/chat output). If a task requires running commands, do it and report results.")

    full_prompt = "\n\n".join(prompt_parts)
    append_prompt = _build_append_prompt()

    try:
        result = await asyncio.create_subprocess_exec(
            CLAUDE_BIN, "-p", full_prompt,
            "--output-format", "text",
            "--model", "opus",
            "--append-system-prompt", append_prompt,
            cwd=ORCHESTRATOR_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY},
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=300)
        response = stdout.decode().strip()

        if not response:
            log.warning(f"Claude returned empty. stderr: {stderr.decode()[:500]}")
            response = "I wasn't able to process that. Could you try again?"

        # Store in history
        conversation_history.append({"role": "user", "content": user_text, "ts": time.time()})
        conversation_history.append({"role": "assistant", "content": response, "ts": time.time()})
        if len(conversation_history) > MAX_HISTORY * 2:
            conversation_history[:] = conversation_history[-MAX_HISTORY * 2:]

        log.info(f"Claude response: {len(response)} chars")
        return response

    except asyncio.TimeoutError:
        log.error("Claude timed out after 300s")
        return "That's taking too long. I've timed out after five minutes."
    except Exception as e:
        log.error(f"Claude error: {e}")
        return f"I hit an error: {str(e)[:200]}"

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.now(AEST).isoformat(),
        "model": "claude-opus",
    }


@app.post("/api/voice")
async def voice_endpoint(
    audio: UploadFile = File(...),
    mode: str = Form("work"),  # Kept for backward compat, ignored
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

    # 2. LLM
    reply = await llm_claude(transcript)

    # 3. Text-to-Speech
    tts_audio = await text_to_speech(reply)
    audio_b64 = base64.b64encode(tts_audio).decode()

    return JSONResponse({
        "transcript": transcript,
        "reply": reply,
        "audio_base64": audio_b64,
        "audio_format": "mp3",
    })


@app.post("/api/chat")
async def chat_endpoint(
    text: str = Form(...),
    mode: str = Form("work"),  # Kept for backward compat, ignored
    authorization: Optional[str] = Header(None),
):
    """Text-only endpoint."""
    verify_token(authorization)

    log.info(f"Chat request: text='{text[:100]}'")
    reply = await llm_claude(text)

    return JSONResponse({"reply": reply})


@app.get("/api/history")
async def get_history(
    authorization: Optional[str] = Header(None),
):
    verify_token(authorization)
    return JSONResponse({"history": conversation_history})


@app.delete("/api/history")
async def clear_history(
    authorization: Optional[str] = Header(None),
):
    verify_token(authorization)
    conversation_history.clear()
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
    log.info("Starting Fields Voice Agent API...")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8090,
        log_level="info",
        reload=False,
    )
