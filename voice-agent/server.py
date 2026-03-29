#!/usr/bin/env python3
"""
Fields Voice Agent — Backend API
Receives audio from Android app, processes through STT → LLM → TTS pipeline.

Modes:
  - "work"     → Claude Code (full VM access, memory, tools)
  - "strategy" → GPT-5.4 (1M context frontier reasoning)

Endpoints:
  POST /api/voice       — audio in, audio + text out
  POST /api/chat        — text in, text out (for testing)
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
GPT_MODEL = "gpt-5.4"

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

# In-memory conversation history (per mode)
conversation_history: dict[str, list[dict]] = {"work": [], "strategy": []}
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


def _build_system_prompt_work() -> str:
    """Build system prompt for Claude work mode with full VM context."""
    docs = _load_context_docs()

    return f"""You are the Fields Estate operations agent, responding to voice commands from Will Simpson (founder).
You have full access to the VM at /home/fields/Fields_Orchestrator via Claude Code.
Keep responses concise and conversational — this is a voice interface, not a text chat.
Aim for 2-3 sentences unless asked for detail.

Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}

=== PROJECT INSTRUCTIONS (CLAUDE.md) ===
{docs.get('claude_md', 'Not available')}

=== PERSISTENT MEMORY INDEX ===
{docs.get('memory_md', 'Not available')}

=== MEMORY FILES ===
{docs.get('memory_files', 'Not available')}

=== LIVE OPS STATUS ===
{docs.get('ops_status', 'Not available')}"""


def _build_system_prompt_strategy() -> str:
    """Build system prompt for GPT-5.4 strategy mode with full business context."""
    docs = _load_context_docs()

    return f"""You are a senior business strategist and technical advisor for Fields Real Estate, speaking directly with founder Will Simpson.
Keep responses concise and conversational — this is a voice interface. Aim for 2-3 sentences unless asked for detail. Be direct, no fluff.

Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}

Below is the full project context — the business, systems, data, and current state. Use this to give informed, specific advice rather than generic strategy talk.

=== PROJECT INSTRUCTIONS (CLAUDE.md) ===
{docs.get('claude_md', 'Not available')}

=== PERSISTENT MEMORY INDEX ===
{docs.get('memory_md', 'Not available')}

=== MEMORY FILES ===
{docs.get('memory_files', 'Not available')}

=== LIVE OPS STATUS ===
{docs.get('ops_status', 'Not available')}"""


async def llm_claude_work(user_text: str) -> str:
    """Route to Claude Code with full VM access."""
    history = conversation_history["work"]

    # Build conversation context from recent history
    context_lines = []
    for msg in history[-10:]:  # Last 10 exchanges
        role = msg["role"]
        context_lines.append(f"{role}: {msg['content'][:500]}")

    prompt_parts = []
    if context_lines:
        prompt_parts.append("Recent conversation:\n" + "\n".join(context_lines))
    prompt_parts.append(f"User (voice): {user_text}")
    prompt_parts.append("\nRespond concisely (this is voice output). If a task requires running commands, do it and report results.")

    full_prompt = "\n\n".join(prompt_parts)

    # Build supplementary system prompt with memory files
    # (Claude Code already loads CLAUDE.md from cwd, but we add memory files explicitly)
    docs = _load_context_docs()
    append_prompt = f"""This is a voice interface — keep responses to 2-3 sentences unless asked for detail.
Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}

=== PERSISTENT MEMORY ===
{docs.get('memory_md', '')}

=== MEMORY FILES ===
{docs.get('memory_files', '')}

=== LIVE OPS STATUS ===
{docs.get('ops_status', '')}"""

    try:
        result = await asyncio.create_subprocess_exec(
            CLAUDE_BIN, "-p", full_prompt,
            "--output-format", "text",
            "--model", "sonnet",
            "--max-budget-usd", "0.50",
            "--allowedTools", "Bash Read Glob Grep",
            "--append-system-prompt", append_prompt,
            cwd=ORCHESTRATOR_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY},
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=120)
        response = stdout.decode().strip()

        if not response:
            log.warning(f"Claude returned empty. stderr: {stderr.decode()[:500]}")
            response = "I wasn't able to process that. Could you try again?"

        # Store in history
        history.append({"role": "user", "content": user_text, "ts": time.time()})
        history.append({"role": "assistant", "content": response, "ts": time.time()})
        if len(history) > MAX_HISTORY * 2:
            history[:] = history[-MAX_HISTORY * 2:]

        log.info(f"Claude response: {len(response)} chars")
        return response

    except asyncio.TimeoutError:
        log.error("Claude timed out after 120s")
        return "That command is taking too long. I've timed out after two minutes."
    except Exception as e:
        log.error(f"Claude error: {e}")
        return f"I hit an error running that command: {str(e)[:200]}"


async def llm_gpt_strategy(user_text: str) -> str:
    """Route to GPT-5.4 for strategy discussions."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    history = conversation_history["strategy"]

    messages = [{"role": "system", "content": _build_system_prompt_strategy()}]

    # Add conversation history
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_text})

    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            max_completion_tokens=1000,  # Keep responses concise for voice
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()

        # Store in history
        history.append({"role": "user", "content": user_text, "ts": time.time()})
        history.append({"role": "assistant", "content": reply, "ts": time.time()})
        if len(history) > MAX_HISTORY * 2:
            history[:] = history[-MAX_HISTORY * 2:]

        log.info(f"GPT-5.4 response: {len(reply)} chars")
        return reply

    except Exception as e:
        log.error(f"GPT-5.4 error: {e}")
        return f"I hit an error with the strategy model: {str(e)[:200]}"

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.now(AEST).isoformat(),
        "models": {"stt": STT_MODEL, "tts": TTS_MODEL, "work": "claude-sonnet", "strategy": GPT_MODEL},
    }


@app.post("/api/voice")
async def voice_endpoint(
    audio: UploadFile = File(...),
    mode: str = Form("work"),
    authorization: Optional[str] = Header(None),
):
    """Main voice endpoint: audio in → audio + text out."""
    verify_token(authorization)

    if mode not in ("work", "strategy"):
        raise HTTPException(400, "Mode must be 'work' or 'strategy'")

    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(400, "Audio too short")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio too large (max 25MB)")

    log.info(f"Voice request: mode={mode}, audio={len(audio_bytes)} bytes")

    # 1. Speech-to-Text
    transcript = await speech_to_text(audio_bytes, audio.filename or "audio.wav")
    if not transcript:
        return JSONResponse({"error": "Could not transcribe audio", "transcript": ""})

    # 2. LLM
    if mode == "work":
        reply = await llm_claude_work(transcript)
    else:
        reply = await llm_gpt_strategy(transcript)

    # 3. Text-to-Speech
    tts_audio = await text_to_speech(reply)
    audio_b64 = base64.b64encode(tts_audio).decode()

    return JSONResponse({
        "transcript": transcript,
        "reply": reply,
        "audio_base64": audio_b64,
        "audio_format": "mp3",
        "mode": mode,
    })


@app.post("/api/chat")
async def chat_endpoint(
    text: str = Form(...),
    mode: str = Form("work"),
    authorization: Optional[str] = Header(None),
):
    """Text-only endpoint for testing without audio."""
    verify_token(authorization)

    if mode not in ("work", "strategy"):
        raise HTTPException(400, "Mode must be 'work' or 'strategy'")

    log.info(f"Chat request: mode={mode}, text='{text[:100]}'")

    if mode == "work":
        reply = await llm_claude_work(text)
    else:
        reply = await llm_gpt_strategy(text)

    return JSONResponse({
        "reply": reply,
        "mode": mode,
    })


@app.get("/api/history")
async def get_history(
    mode: str = "work",
    authorization: Optional[str] = Header(None),
):
    verify_token(authorization)
    return JSONResponse({"history": conversation_history.get(mode, []), "mode": mode})


@app.delete("/api/history")
async def clear_history(
    mode: str = "work",
    authorization: Optional[str] = Header(None),
):
    verify_token(authorization)
    conversation_history[mode] = []
    return JSONResponse({"cleared": True, "mode": mode})

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
