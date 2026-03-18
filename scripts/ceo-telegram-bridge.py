#!/home/fields/venv/bin/python3
"""
Telegram bridge for the remote CEO Codex team.

Flow:
1. Poll Telegram Bot API for inbound messages.
2. Persist session/message state in system_monitor.
3. Refresh the CEO context snapshot when stale.
4. SSH to the remote Codex VM, run a single CEO-team response, and return it
   to Telegram.

Required env vars:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_ALLOWED_CHAT_IDS
  COSMOS_CONNECTION_STRING

Optional env vars:
  CEO_TELEGRAM_MODEL
  CEO_TELEGRAM_REMOTE_HOST
  CEO_TELEGRAM_REMOTE_CONTEXT_DIR
  CEO_TELEGRAM_CONTEXT_SYNC_MINUTES
  CEO_TELEGRAM_POLL_SECONDS
  CEO_TELEGRAM_REMOTE_TIMEOUT_SECONDS
  CEO_TELEGRAM_HISTORY_LIMIT
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from pymongo import MongoClient, ReturnDocument


ROOT = Path("/home/fields/Fields_Orchestrator")
ENV_PATH = ROOT / ".env"
FOUNDER_REQUESTS_DIR = ROOT / "ceo-founder-requests"
LOCAL_BROWSER_INSPECTOR = ROOT / "scripts/site-inspector.js"
AEST = ZoneInfo("Australia/Brisbane")
STATE_ID = "telegram"
SESSION_COLL = "ceo_chat_sessions"
MESSAGE_COLL = "ceo_chat_messages"
STATE_COLL = "ceo_chat_bridge_state"
JOB_COLL = "ceo_chat_jobs"
MAX_TELEGRAM_MESSAGE = 4000
JOB_HEARTBEAT_SECONDS = 15
JOB_TYPE_ADVISORY = "advisory_reply"
JOB_TYPE_BATCH = "batch_ceo_run"
MODEL_ALIASES = {
    "gpt-5.4-codex": "gpt-5.4",
}
DEFAULT_CEO_MODEL = "gpt-5.4"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(ENV_PATH)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}: {raw}") from exc


def parse_chat_ids(raw: str) -> set[int]:
    values = set()
    for piece in raw.split(","):
        token = piece.strip()
        if not token:
            continue
        values.add(int(token))
    if not values:
        raise RuntimeError("TELEGRAM_ALLOWED_CHAT_IDS is empty")
    return values


def resolve_ceo_model(raw: str) -> str:
    requested = raw.strip()
    if not requested:
        return DEFAULT_CEO_MODEL
    return MODEL_ALIASES.get(requested, requested)


BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_IDS = parse_chat_ids(os.environ["TELEGRAM_ALLOWED_CHAT_IDS"]) if os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS") else set()
COSMOS_URI = os.environ.get("COSMOS_CONNECTION_STRING", "").strip()
CEO_MODEL = resolve_ceo_model(os.environ.get("CEO_TELEGRAM_MODEL", DEFAULT_CEO_MODEL))
REMOTE_HOST = os.environ.get("CEO_TELEGRAM_REMOTE_HOST", "fields-orchestrator-vm@35.201.6.222").strip()
REMOTE_CONTEXT_DIR = os.environ.get(
    "CEO_TELEGRAM_REMOTE_CONTEXT_DIR",
    "/home/fields-orchestrator-vm/ceo-agents/context",
).strip()
REMOTE_BROWSER_DIR = os.environ.get(
    "CEO_TELEGRAM_REMOTE_BROWSER_DIR",
    "/home/fields-orchestrator-vm/ceo-agents/sandbox/browser-tools",
).strip()
CONTEXT_SYNC_MINUTES = parse_int_env("CEO_TELEGRAM_CONTEXT_SYNC_MINUTES", 30)
POLL_SECONDS = parse_int_env("CEO_TELEGRAM_POLL_SECONDS", 2)
REMOTE_TIMEOUT_SECONDS = parse_int_env("CEO_TELEGRAM_REMOTE_TIMEOUT_SECONDS", 1200)
HISTORY_LIMIT = parse_int_env("CEO_TELEGRAM_HISTORY_LIMIT", 12)
TELEGRAM_TIMEOUT_SECONDS = 35
REMOTE_BROWSER_TIMEOUT_SECONDS = parse_int_env("CEO_TELEGRAM_REMOTE_BROWSER_TIMEOUT_SECONDS", 180)
CEO_BATCH_TIMEOUT_SECONDS = parse_int_env("CEO_TELEGRAM_BATCH_TIMEOUT_SECONDS", 3600)
BROWSER_TRIGGER_TERMS = (
    "website", "site", "browser", "landing page", "landing pages", "ui", "ux", "screenshot",
    "console", "scroll", "for-sale", "for sale", "discover", "analyse", "analyze",
    "fieldsestate.com.au", "/for-sale", "/discover", "/analyse", "recently-sold",
)

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [ceo-telegram] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ceo-telegram")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def aest_now() -> datetime:
    return datetime.now(AEST)


def iso_now() -> str:
    return utc_now().isoformat()


def aest_label() -> str:
    return aest_now().strftime("%Y-%m-%d %H:%M AEST")


def title_from_text(text: str, fallback: str = "Telegram request") -> str:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:100]
    return fallback


def slugify(value: str, fallback: str = "request") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or fallback


def latest_user_message_text(session: dict[str, Any]) -> str | None:
    for item in reversed(session.get("history_tail", [])):
        if item.get("role") != "user":
            continue
        text = (item.get("text") or "").strip()
        if text and not text.startswith("/"):
            return text
    return None


def create_founder_request_file(area: str, text: str, source: str) -> Path:
    open_dir = FOUNDER_REQUESTS_DIR / "open"
    open_dir.mkdir(parents=True, exist_ok=True)

    now_label = aest_label()
    date_label = aest_now().strftime("%Y-%m-%d")
    title = title_from_text(text)
    slug = slugify(title)
    base_name = f"{date_label}-{area}-{slug}"
    path = open_dir / f"{base_name}.md"
    counter = 2
    while path.exists():
        path = open_dir / f"{base_name}-{counter}.md"
        counter += 1

    request_id = path.stem
    body = (
        f"---\n"
        f"id: {request_id}\n"
        f"title: {title}\n"
        f"created_at: {now_label}\n"
        f"owner: will\n"
        f"area: {area}\n"
        f"priority: medium\n"
        f"status: open\n"
        f"type: task\n"
        f"source: {source}\n"
        f"---\n\n"
        f"## {now_label} - Will\n\n"
        f"### Issue\n"
        f"{text.strip()}\n\n"
        f"### What I want investigated or changed\n"
        f"Captured from Telegram. Add follow-up detail in this thread or Telegram if needed.\n\n"
        f"### New standing behaviour\n"
        f"None specified yet.\n\n"
        f"### Constraints\n"
        f"None specified yet.\n\n"
        f"### Success looks like\n"
        f"A clear response, plan, or completed next action tied to this request.\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def get_client() -> MongoClient:
    return MongoClient(COSMOS_URI, retryWrites=False, serverSelectionTimeoutMS=30000)


def telegram_call(method: str, payload: dict[str, Any], timeout: int = TELEGRAM_TIMEOUT_SECONDS) -> dict[str, Any]:
    response = requests.post(
        f"{TELEGRAM_API_BASE}/{method}",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {data}")
    return data


def workflow_reply_markup() -> dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "/status"}, {"text": "/sync"}],
            [{"text": "/task"}, {"text": "/run_ceo"}],
            [{"text": "/reset"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Chat normally, or tap a management command",
    }


def register_bot_commands() -> None:
    commands = [
        {"command": "start", "description": "Show advisory chat help"},
        {"command": "help", "description": "Show advisory chat help"},
        {"command": "status", "description": "Show bridge status"},
        {"command": "sync", "description": "Refresh CEO context now"},
        {"command": "task", "description": "Create a durable founder request"},
        {"command": "run_ceo", "description": "Run a fresh CEO batch review"},
        {"command": "reset", "description": "Start a new CEO chat session"},
    ]
    try:
        telegram_call("setMyCommands", {"commands": commands}, timeout=30)
    except Exception as exc:
        log.warning("Failed to register CEO bot commands: %s", exc)


def send_chat_action(chat_id: int, action: str = "typing") -> None:
    try:
        telegram_call("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=15)
    except Exception as exc:
        log.warning("Failed to send chat action to %s: %s", chat_id, exc)


def chunk_text(text: str, chunk_size: int = MAX_TELEGRAM_MESSAGE) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, chunk_size)
        if split_at < chunk_size // 2:
            split_at = remaining.rfind(" ", 0, chunk_size)
        if split_at < chunk_size // 2:
            split_at = chunk_size
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


def send_message(chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
    markup = reply_markup if reply_markup is not None else workflow_reply_markup()
    chunks = chunk_text(text)
    for index, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if index == 0 and markup is not None:
            payload["reply_markup"] = markup
        telegram_call("sendMessage", payload, timeout=30)


def get_bridge_state(sm) -> dict[str, Any]:
    doc = sm[STATE_COLL].find_one({"_id": STATE_ID})
    if doc:
        return doc

    created = {
        "_id": STATE_ID,
        "platform": "telegram",
        "last_update_id": None,
        "last_context_sync_at": None,
        "last_poll_at": iso_now(),
        "created_at": iso_now(),
        "updated_at": iso_now(),
    }
    sm[STATE_COLL].insert_one(created)
    return created


def update_bridge_state(sm, updates: dict[str, Any]) -> None:
    updates["updated_at"] = iso_now()
    sm[STATE_COLL].update_one({"_id": STATE_ID}, {"$set": updates}, upsert=True)


def create_session(sm, chat: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    timestamp = aest_now().strftime("%Y%m%d_%H%M%S")
    session_id = f"telegram_{chat['id']}_{timestamp}"
    now = iso_now()
    doc = {
        "_id": session_id,
        "platform": "telegram",
        "status": "active",
        "telegram_chat_id": chat["id"],
        "chat_type": chat.get("type"),
        "telegram_user_id": user.get("id"),
        "telegram_username": user.get("username"),
        "telegram_first_name": user.get("first_name"),
        "telegram_last_name": user.get("last_name"),
        "message_count": 0,
        "history_tail": [],
        "created_at": now,
        "updated_at": now,
        "last_message_at": None,
        "last_remote_status": None,
        "last_remote_run_at": None,
        "active_job_id": None,
    }
    sm[SESSION_COLL].insert_one(doc)
    return doc


def get_or_create_active_session(sm, chat: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    session = sm[SESSION_COLL].find_one({
        "platform": "telegram",
        "telegram_chat_id": chat["id"],
        "status": "active",
    })
    if session:
        return session
    return create_session(sm, chat, user)


def reset_session(sm, chat: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    sm[SESSION_COLL].update_many(
        {
            "platform": "telegram",
            "telegram_chat_id": chat["id"],
            "status": "active",
        },
        {
            "$set": {
                "status": "archived",
                "updated_at": iso_now(),
                "closed_at": iso_now(),
            }
        },
    )
    return create_session(sm, chat, user)


def append_message(
    sm,
    session_id: str,
    role: str,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    now = iso_now()
    updated = sm[SESSION_COLL].find_one_and_update(
        {"_id": session_id},
        {
            "$inc": {"message_count": 1},
            "$set": {"updated_at": now, "last_message_at": now},
            "$push": {
                "history_tail": {
                    "$each": [{"role": role, "text": text, "created_at": now}],
                    "$slice": -20,
                }
            },
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise RuntimeError(f"Session not found: {session_id}")

    message_doc = {
        "session_id": session_id,
        "sequence": updated["message_count"],
        "platform": "telegram",
        "role": role,
        "text": text,
        "created_at": now,
        "metadata": metadata,
    }
    sm[MESSAGE_COLL].insert_one(message_doc)
    return updated


def get_active_job(sm, session: dict[str, Any]) -> dict[str, Any] | None:
    job_id = session.get("active_job_id")
    if not job_id:
        return None
    job = sm[JOB_COLL].find_one({"_id": job_id})
    if not job:
        return None
    if job.get("status") in {"completed", "failed", "cancelled"}:
        return None
    return job


def create_job(
    sm,
    session: dict[str, Any],
    founder_message: str,
    *,
    job_type: str = JOB_TYPE_ADVISORY,
    progress_message: str | None = None,
) -> dict[str, Any]:
    now = iso_now()
    job_id = f"{session['_id']}_{aest_now().strftime('%H%M%S')}"
    if progress_message is None:
        progress_message = "Queued for CEO response." if job_type == JOB_TYPE_ADVISORY else "Queued for full CEO batch run."
    doc = {
        "_id": job_id,
        "session_id": session["_id"],
        "telegram_chat_id": session["telegram_chat_id"],
        "job_type": job_type,
        "status": "queued",
        "founder_message": founder_message,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "last_heartbeat_at": None,
        "progress_message": progress_message,
        "error_text": None,
    }
    sm[JOB_COLL].insert_one(doc)
    sm[SESSION_COLL].update_one(
        {"_id": session["_id"]},
        {"$set": {"active_job_id": job_id, "updated_at": now}},
    )
    return doc


def update_job(sm, job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    updates["updated_at"] = iso_now()
    updated = sm[JOB_COLL].find_one_and_update(
        {"_id": job_id},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise RuntimeError(f"Job not found: {job_id}")
    return updated


def clear_active_job(sm, session_id: str, job_id: str) -> None:
    sm[SESSION_COLL].update_one(
        {"_id": session_id, "active_job_id": job_id},
        {"$set": {"active_job_id": None, "updated_at": iso_now()}},
    )


def elapsed_label(started_at: str | None) -> str:
    if not started_at:
        return "not started"
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return "unknown"
    elapsed = max(int((utc_now() - started).total_seconds()), 0)
    minutes, seconds = divmod(elapsed, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def build_job_status_text(job: dict[str, Any]) -> str:
    label = "CEO batch run" if job.get("job_type") == JOB_TYPE_BATCH else "CEO team job"
    return (
        f"{label} status: {job.get('status', 'unknown')}\n"
        f"Started: {job.get('started_at') or 'queued'}\n"
        f"Elapsed: {elapsed_label(job.get('started_at'))}\n"
        f"Progress: {job.get('progress_message') or 'Waiting for status.'}"
    )


def launch_background_job(job_id: str) -> None:
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--run-job", job_id],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )


def should_refresh_context(last_sync_at: str | None, force: bool) -> bool:
    if force or not last_sync_at:
        return True
    try:
        last_sync = datetime.fromisoformat(last_sync_at)
    except ValueError:
        return True
    age_seconds = (utc_now() - last_sync).total_seconds()
    return age_seconds >= CONTEXT_SYNC_MINUTES * 60


def run_local_command(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )


def ssh_run(command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", REMOTE_HOST, command],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )


def sync_remote_browser_inspector() -> tuple[bool, str]:
    if not LOCAL_BROWSER_INSPECTOR.exists():
        return False, f"Local browser inspector missing: {LOCAL_BROWSER_INSPECTOR}"

    remote_script = f"{REMOTE_BROWSER_DIR}/scripts/site-inspector.js"
    mkdir_result = ssh_run(f"mkdir -p {shlex.quote(REMOTE_BROWSER_DIR)}/scripts", timeout=30)
    if mkdir_result.returncode != 0:
        detail = (mkdir_result.stderr or mkdir_result.stdout or "Remote browser-tools mkdir failed")[-1200:]
        return False, detail

    upload_result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", REMOTE_HOST, f"cat > {shlex.quote(remote_script)}"],
        input=LOCAL_BROWSER_INSPECTOR.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )
    if upload_result.returncode != 0:
        detail = (upload_result.stderr or upload_result.stdout or "Remote browser inspector upload failed")[-1200:]
        return False, detail

    chmod_result = ssh_run(f"chmod 755 {shlex.quote(remote_script)}", timeout=30)
    if chmod_result.returncode != 0:
        detail = (chmod_result.stderr or chmod_result.stdout or "Remote browser inspector chmod failed")[-1200:]
        return False, detail

    return True, remote_script


def maybe_refresh_context(sm, force: bool = False) -> tuple[bool, str]:
    state = get_bridge_state(sm)
    if not should_refresh_context(state.get("last_context_sync_at"), force):
        return True, "Context still fresh."

    export_result = run_local_command([sys.executable, str(ROOT / "scripts/ceo-context-export.py")], timeout=900)
    if export_result.returncode != 0:
        msg = (export_result.stderr or export_result.stdout or "CEO context export failed")[-1200:]
        log.error("Context export failed: %s", msg)
        return False, msg

    remote_result = ssh_run(
        f"cd {shlex.quote(REMOTE_CONTEXT_DIR)} && GH_CONFIG_DIR=~/.config/gh git pull --ff-only origin main",
        timeout=120,
    )
    if remote_result.returncode != 0:
        msg = (remote_result.stderr or remote_result.stdout or "Remote context pull failed")[-1200:]
        log.error("Remote context pull failed: %s", msg)
        return False, msg

    update_bridge_state(sm, {"last_context_sync_at": iso_now()})
    return True, "Context refreshed."


def build_prompt(
    session: dict[str, Any],
    latest_user_message: str,
    context_warning: str | None = None,
    browser_context_note: str | None = None,
) -> str:
    history_lines = []
    for item in session.get("history_tail", [])[-HISTORY_LIMIT:]:
        role = item.get("role", "unknown").upper()
        text = (item.get("text") or "").strip()
        if text:
            history_lines.append(f"{role}: {text}")

    history_block = "\n".join(history_lines) if history_lines else "No prior conversation."
    now_aest = aest_now().strftime("%Y-%m-%d %H:%M AEST")
    context_warning_block = f"\nContext sync note:\n{context_warning}\n" if context_warning else ""
    browser_note_block = f"\nLive browser note:\n{browser_context_note}\n" if browser_context_note else ""

    return f"""You are the Fields Estate CEO team responding to the founder inside Telegram.

You represent three perspectives at once:
- Engineering
- Growth
- Product

Work in read-only mode. Use the local `context/` directory as the source of truth for company state. If a local `browser_artifacts/` directory is present, treat it as fresh live website evidence gathered immediately before this reply. Read files as needed before answering. Do not create proposals, branches, commits, or code changes. This is a direct advisory response, not a batch proposal run.

Response style:
- Be concise, direct, and operational.
- Answer the founder's message first.
- Where useful, separate Engineering / Growth / Product views.
- End with the single best next action.
- If you are missing evidence, say exactly what is missing.
- Maximum 700 words.

Current time: {now_aest}
Telegram session: {session["_id"]}
{context_warning_block}
{browser_note_block}

Conversation history:
{history_block}

Latest founder message:
{latest_user_message}
"""


def is_simple_greeting(text: str) -> bool:
    normalized = re.sub(r"[^a-z]+", "", text.lower())
    return normalized in {"hi", "hello", "hey", "helli", "hiya", "yo"}


def message_needs_browser_artifacts(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in BROWSER_TRIGGER_TERMS)


def browser_urls_for_message(text: str) -> list[str]:
    lowered = text.lower()
    urls: list[str] = []
    candidates = [
        (("/for-sale", "for sale"), "/for-sale"),
        (("/discover", "discover"), "/discover"),
        (("/analyse", "/analyze", "analyse", "analyze"), "/analyse"),
        (("home page", "homepage", "home"), "/"),
    ]
    for terms, url in candidates:
        if any(term in lowered for term in terms) and url not in urls:
            urls.append(url)
    if not urls:
        urls = ["/for-sale", "/discover"]
    return urls[:3]


def prepare_remote_browser_artifacts(latest_user_message: str) -> dict[str, Any] | None:
    if not message_needs_browser_artifacts(latest_user_message):
        return None

    synced, sync_detail = sync_remote_browser_inspector()
    if not synced:
        return {
            "status": "sync_failed",
            "detail": sync_detail,
        }

    run_token = uuid.uuid4().hex[:10]
    urls = browser_urls_for_message(latest_user_message)
    remote_dir = f"{REMOTE_BROWSER_DIR}/artifacts/telegram-inspections/{run_token}"
    log_path = f"/tmp/ceo_browser_{run_token}.log"
    remote_script = f"""
set -e
if [ ! -f {shlex.quote(REMOTE_BROWSER_DIR)}/scripts/site-inspector.js ]; then
  printf '%s\\n' '{{{{"status":"missing_tools","detail":"browser-tools/scripts/site-inspector.js not found"}}}}'
  exit 0
fi
mkdir -p {shlex.quote(remote_dir)}
if [ ! -d {shlex.quote(REMOTE_BROWSER_DIR)}/node_modules ]; then
  printf '%s\\n' '{{{{"status":"missing_dependencies","detail":"browser-tools/node_modules missing","remote_dir":"{remote_dir}"}}}}'
  exit 0
fi
RC=0
node {shlex.quote(REMOTE_BROWSER_DIR)}/scripts/site-inspector.js --url {shlex.quote(",".join(urls))} --wait 1500 --output-dir {shlex.quote(remote_dir)} >{shlex.quote(log_path)} 2>&1 || RC=$?
export CEO_BROWSER_RC="$RC"
export CEO_BROWSER_REMOTE_DIR={shlex.quote(remote_dir)}
export CEO_BROWSER_LOG_PATH={shlex.quote(log_path)}
python3 - <<'PY'
import json
import os
from pathlib import Path

remote_dir = Path(os.environ["CEO_BROWSER_REMOTE_DIR"])
summary_path = remote_dir / "summary.json"
log_path = Path(os.environ["CEO_BROWSER_LOG_PATH"])
payload = dict(
    status="ok" if summary_path.exists() else "failed",
    remote_dir=str(remote_dir),
    summary_path=str(summary_path),
    log_path=str(log_path),
    exit_code=int(os.environ.get("CEO_BROWSER_RC", "1")),
)
if summary_path.exists():
    try:
        payload["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        payload["status"] = "failed"
        payload["detail"] = "Failed to parse summary.json: " + str(exc)
else:
    payload["detail"] = "summary.json not written"

if log_path.exists():
    payload["log_tail"] = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]

print(json.dumps(payload))
PY
"""
    result = ssh_run(remote_script, timeout=REMOTE_BROWSER_TIMEOUT_SECONDS)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Remote browser preparation failed")[-1200:]
        return {"status": "failed", "detail": detail, "urls": urls}

    raw = (result.stdout or "").strip()
    if not raw:
        return {"status": "failed", "detail": "Remote browser preparation returned no output", "urls": urls}

    try:
        payload = json.loads(raw.splitlines()[-1])
    except json.JSONDecodeError:
        payload = {"status": "failed", "detail": raw[-1200:]}
    payload["urls"] = urls
    return payload


def run_remote_ceo_reply(prompt: str, browser_context: dict[str, Any] | None = None) -> str:
    remote_token = uuid.uuid4().hex
    prompt_path = f"/tmp/ceo_telegram_prompt_{remote_token}.txt"
    quoted_prompt_path = shlex.quote(prompt_path)
    browser_copy_block = ""
    if browser_context and browser_context.get("remote_dir"):
        browser_copy_block = (
            'mkdir -p "$WORKDIR/browser_artifacts"\n'
            f'cp -r {shlex.quote(str(browser_context["remote_dir"]))}/. "$WORKDIR/browser_artifacts"/ 2>/dev/null || true\n'
        )

    upload = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", REMOTE_HOST, f"cat > {quoted_prompt_path}"],
        input=prompt,
        text=True,
        capture_output=True,
        timeout=30,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )
    if upload.returncode != 0:
        detail = (upload.stderr or upload.stdout or "Remote prompt upload failed")[-1200:]
        raise RuntimeError(detail)

    remote_script = f"""
set -e
WORKDIR=$(mktemp -d /tmp/ceo-telegram-XXXXXX)
trap 'rm -rf "$WORKDIR" {quoted_prompt_path}' EXIT
cp -r {shlex.quote(REMOTE_CONTEXT_DIR)} "$WORKDIR/context"
{browser_copy_block}
cd "$WORKDIR"
LOGFILE=/tmp/ceo_telegram_codex_{remote_token}.log
if ! codex exec -m {shlex.quote(CEO_MODEL)} --full-auto --skip-git-repo-check -o "$WORKDIR/output.txt" "$(cat {quoted_prompt_path})" >"$LOGFILE" 2>&1; then
  echo "---REMOTE-CODEX-LOG---"
  tail -200 "$LOGFILE"
  exit 1
fi
cat "$WORKDIR/output.txt"
"""
    result = ssh_run(remote_script, timeout=REMOTE_TIMEOUT_SECONDS)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Remote Codex run failed")[-2000:]
        raise RuntimeError(detail)

    reply = (result.stdout or "").strip()
    if not reply:
        raise RuntimeError("Remote Codex returned an empty response")
    return reply


def format_status(sm, session: dict[str, Any]) -> str:
    state = get_bridge_state(sm)
    last_sync = state.get("last_context_sync_at") or "never"
    last_remote = session.get("last_remote_run_at") or "never"
    lines = [
        f"CEO Telegram bridge is live.\n"
        f"Session: {session['_id']}\n"
        f"Messages in session: {session.get('message_count', 0)}\n"
        f"Last context sync: {last_sync}\n"
        f"Last CEO run: {last_remote}"
    ]
    active_job = get_active_job(sm, session)
    if active_job:
        lines.append("")
        lines.append(build_job_status_text(active_job))
    return "\n".join(lines)


def parse_launcher_run_dir(output: str) -> Path | None:
    match = re.search(r"Local artifacts:\s*(.+)", output)
    if match:
        return Path(match.group(1).strip())
    latest_path = ROOT / "artifacts" / "ceo-runs" / "LATEST_RUN.txt"
    if latest_path.exists():
        candidate = latest_path.read_text(encoding="utf-8").strip()
        if candidate:
            return Path(candidate)
    return None


def extract_questions_for_run(markdown_text: str, run_id: str) -> list[str]:
    questions: list[str] = []
    for chunk in re.split(r"(?m)^## ", markdown_text):
        if run_id not in chunk:
            continue
        block = f"## {chunk}" if not chunk.startswith("## ") else chunk
        match = re.search(r"(?ms)^### Questions for Will\s*\n(.*?)(?=^### |\Z)", block)
        if not match:
            continue
        for line in match.group(1).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("- "):
                questions.append(stripped[2:].strip())
            elif not stripped.startswith("#"):
                questions.append(stripped)
    return questions


def collect_batch_run_questions(run_id: str) -> list[tuple[str, list[str]]]:
    responses_dir = FOUNDER_REQUESTS_DIR / "responses"
    if not responses_dir.exists():
        return []

    findings: list[tuple[str, list[str]]] = []
    for path in sorted(responses_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if run_id not in text:
            continue
        questions = extract_questions_for_run(text, run_id)
        if questions:
            findings.append((path.name, questions))
    return findings


def read_batch_run_summary(run_dir: Path) -> tuple[str, str]:
    run_id = run_dir.name
    run_json_path = run_dir / "run.json"
    run_status = "unknown"
    if run_json_path.exists():
        try:
            payload = json.loads(run_json_path.read_text(encoding="utf-8"))
            run_status = str(payload.get("run_status") or run_status)
            run_id = str(payload.get("run_id") or run_id)
        except json.JSONDecodeError:
            pass

    summary_path = run_dir / "summary.md"
    summary_line = "Summary file not found."
    if summary_path.exists():
        for line in summary_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("**Summary:** "):
                summary_line = stripped.replace("**Summary:** ", "", 1)
                break
    return run_id, f"Run status: `{run_status}`\nArtifacts: `{run_dir}`\nSummary: {summary_line}"


def process_batch_run_job(sm, session: dict[str, Any], job: dict[str, Any]) -> None:
    update_job(
        sm,
        job["_id"],
        {
            "last_heartbeat_at": iso_now(),
            "progress_message": "Refreshing CEO context for a full batch run.",
        },
    )
    ok, detail = maybe_refresh_context(sm, force=True)
    if not ok:
        raise RuntimeError(f"CEO context refresh failed before batch run.\n{detail[-1200:]}")

    update_job(
        sm,
        job["_id"],
        {
            "last_heartbeat_at": iso_now(),
            "progress_message": "Running the CEO batch launcher.",
        },
    )
    result = run_local_command([sys.executable, str(ROOT / "scripts/ceo-agent-launcher.py")], timeout=CEO_BATCH_TIMEOUT_SECONDS)
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    if result.returncode != 0:
        raise RuntimeError((combined_output or "CEO batch launcher failed")[-2000:])

    run_dir = parse_launcher_run_dir(combined_output)
    if run_dir is None or not run_dir.exists():
        raise RuntimeError("CEO batch launcher completed but no local artifact directory could be resolved.")

    run_id, summary_text = read_batch_run_summary(run_dir)
    questions = collect_batch_run_questions(run_id)

    reply_lines = [
        "CEO batch run finished.",
        f"Run: `{run_id}`",
        summary_text,
    ]
    reply = "\n".join(reply_lines)
    append_message(
        sm,
        session["_id"],
        "assistant",
        reply,
        {"job_type": JOB_TYPE_BATCH, "run_id": run_id, "artifact_dir": str(run_dir)},
    )
    sm[SESSION_COLL].update_one(
        {"_id": session["_id"]},
        {"$set": {"last_remote_status": "success", "last_remote_run_at": iso_now()}},
    )
    update_job(
        sm,
        job["_id"],
        {
            "status": "completed",
            "finished_at": iso_now(),
            "last_heartbeat_at": iso_now(),
            "progress_message": "CEO batch run finished.",
            "error_text": None,
        },
    )
    clear_active_job(sm, session["_id"], job["_id"])
    send_message(job["telegram_chat_id"], reply)

    if questions:
        blocks = ["Clarification needed from you:"]
        for filename, prompts in questions:
            blocks.append(f"\n{filename}")
            for prompt in prompts:
                blocks.append(f"- {prompt}")
        send_message(job["telegram_chat_id"], "\n".join(blocks))
    else:
        send_message(job["telegram_chat_id"], "No clarification questions were generated in this CEO run.")


def handle_command(sm, chat: dict[str, Any], user: dict[str, Any], text: str) -> bool:
    stripped = text.strip()
    command, _, remainder = stripped.partition(" ")
    command = command.lower()
    remainder = remainder.strip()
    session = get_or_create_active_session(sm, chat, user)

    if command in {"/start", "/help"}:
        send_message(
            chat["id"],
            "CEO Telegram bridge is ready. Plain text messages stay in advisory chat mode.\n"
            "Create a durable founder request with `/task ...`.\n"
            "Commands: `/status`, `/sync`, `/task`, `/run_ceo`, `/reset`.",
        )
        return True

    if command == "/status":
        send_message(chat["id"], format_status(sm, session))
        return True

    if command == "/reset":
        new_session = reset_session(sm, chat, user)
        send_message(chat["id"], f"Started a new CEO chat session: {new_session['_id']}")
        return True

    if command == "/sync":
        send_chat_action(chat["id"])
        ok, detail = maybe_refresh_context(sm, force=True)
        send_message(chat["id"], "Context refreshed." if ok else f"Context refresh failed.\n{detail[-800:]}")
        return True

    if command == "/task":
        task_text = remainder or latest_user_message_text(session)
        if not task_text:
            send_message(chat["id"], "Provide task text after `/task ...`, or send the task in chat first and then reply with `/task`.")
            return True
        path = create_founder_request_file("management", task_text, "telegram_ceo")
        reply = (
            f"Created founder request `{path.name}` in `ceo-founder-requests/open`.\n"
            "It will persist for future CEO review cycles."
        )
        append_message(sm, session["_id"], "assistant", reply, {"mode": "task_create", "path": str(path)})
        send_message(chat["id"], reply)
        return True

    if command == "/run_ceo":
        active_job = get_active_job(sm, session)
        if active_job:
            send_message(
                chat["id"],
                build_job_status_text(active_job) + "\n\nWait for the current job to finish before starting a fresh CEO batch run.",
            )
            return True
        new_session = reset_session(sm, chat, user)
        kickoff = "Run a fresh CEO batch review across all operational data and founder request threads."
        append_message(sm, new_session["_id"], "system", kickoff, {"mode": "batch_run_trigger"})
        job = create_job(sm, new_session, kickoff, job_type=JOB_TYPE_BATCH)
        sm[SESSION_COLL].update_one(
            {"_id": new_session["_id"]},
            {"$set": {"last_remote_status": "queued", "updated_at": iso_now()}},
        )
        send_message(
            chat["id"],
            f"Started a new CEO session: {new_session['_id']}\nRunning a full CEO batch review now. I’ll send the artifact path and any clarification questions here.",
        )
        send_chat_action(chat["id"])
        log.info("Queued CEO batch Telegram job %s for session %s", job["_id"], new_session["_id"])
        launch_background_job(job["_id"])
        return True

    return False


def handle_text_message(sm, update: dict[str, Any], message: dict[str, Any], text: str) -> None:
    chat = message["chat"]
    user = message.get("from", {})
    chat_id = chat["id"]

    if chat_id not in ALLOWED_CHAT_IDS:
        log.warning("Ignoring Telegram message from unauthorized chat_id=%s", chat_id)
        return

    if text.startswith("/"):
        if handle_command(sm, chat, user, text):
            return

    session = get_or_create_active_session(sm, chat, user)
    active_job = get_active_job(sm, session)
    if active_job:
        send_message(
            chat_id,
            build_job_status_text(active_job) + "\n\nThe CEO team is still working on the previous message. Send `/status` to check again.",
        )
        return

    session = append_message(
        sm,
        session["_id"],
        "user",
        text,
        {
            "telegram_update_id": update.get("update_id"),
            "telegram_message_id": message.get("message_id"),
        },
    )

    if is_simple_greeting(text):
        reply = (
            "CEO Telegram bridge is live. Send your question for the management team and I’ll route it through.\n"
            "Use `/status` if you want the current bridge state."
        )
        append_message(
            sm,
            session["_id"],
            "assistant",
            reply,
            {"mode": "local_greeting"},
        )
        send_message(chat_id, reply)
        return

    job = create_job(sm, session, text, job_type=JOB_TYPE_ADVISORY)
    sm[SESSION_COLL].update_one(
        {"_id": session["_id"]},
        {"$set": {"last_remote_status": "queued", "updated_at": iso_now()}},
    )
    send_message(chat_id, "Routing this to the CEO team now. I’ll reply here when the run finishes. Send `/status` any time for progress.")
    send_chat_action(chat_id)
    log.info("Queued CEO Telegram job %s for session %s", job["_id"], session["_id"])
    launch_background_job(job["_id"])


def process_job(job_id: str) -> None:
    client = get_client()
    sm = client["system_monitor"]
    try:
        job = sm[JOB_COLL].find_one({"_id": job_id})
        if not job:
            raise RuntimeError(f"Job not found: {job_id}")
        if job.get("status") not in {"queued", "running"}:
            return

        session = sm[SESSION_COLL].find_one({"_id": job["session_id"]})
        if not session:
            raise RuntimeError(f"Session not found for job {job_id}")

        founder_message = job["founder_message"]
        update_job(
            sm,
            job_id,
            {
                "status": "running",
                "started_at": iso_now(),
                "last_heartbeat_at": iso_now(),
                "progress_message": "Refreshing CEO context." if job.get("job_type") != JOB_TYPE_BATCH else "Starting CEO batch run.",
            },
        )

        if job.get("job_type") == JOB_TYPE_BATCH:
            process_batch_run_job(sm, session, job)
            return

        ok, detail = maybe_refresh_context(sm, force=False)
        context_warning = None
        if not ok:
            state = get_bridge_state(sm)
            last_sync = state.get("last_context_sync_at")
            if last_sync:
                context_warning = (
                    f"Latest context refresh failed, so use the last synced CEO context from {last_sync}. "
                    f"Refresh error: {detail[-400:]}"
                )
                append_message(sm, session["_id"], "system", context_warning)
                send_message(
                    job["telegram_chat_id"],
                    "Context refresh failed, but I’m using the last synced CEO context and continuing.",
                )
            else:
                error_text = (
                    "Context refresh failed and no prior CEO context is available, "
                    "so I did not send this to the CEO team.\n" + detail[-800:]
                )
                append_message(sm, session["_id"], "system", error_text)
                sm[SESSION_COLL].update_one(
                    {"_id": session["_id"]},
                    {"$set": {"last_remote_status": "failed", "last_remote_run_at": iso_now()}},
                )
                update_job(
                    sm,
                    job_id,
                    {
                        "status": "failed",
                        "finished_at": iso_now(),
                        "last_heartbeat_at": iso_now(),
                        "progress_message": "Context refresh failed.",
                        "error_text": error_text,
                    },
                )
                clear_active_job(sm, session["_id"], job_id)
                send_message(job["telegram_chat_id"], error_text)
                return

        update_job(
            sm,
            job_id,
            {
                "last_heartbeat_at": iso_now(),
                "progress_message": "Preparing CEO evidence bundle.",
            },
        )
        browser_context = prepare_remote_browser_artifacts(founder_message)
        browser_note = None
        if browser_context:
            if browser_context.get("status") == "ok":
                browser_note = (
                    f"Fresh browser artifacts were captured immediately before this reply for {', '.join(browser_context.get('urls', []))}. "
                    "Read browser_artifacts/summary.json plus any screenshots, page text, console logs, network logs, and preflight.json."
                )
            else:
                browser_note = (
                    f"Browser artifact capture did not succeed. Status: {browser_context.get('status')}. "
                    f"Detail: {(browser_context.get('detail') or '')[-300:]}"
                )

        prompt = build_prompt(
            session,
            founder_message,
            context_warning=context_warning,
            browser_context_note=browser_note,
        )

        update_job(
            sm,
            job_id,
            {
                "last_heartbeat_at": iso_now(),
                "progress_message": "Waiting for the remote CEO team reply.",
            },
        )
        reply = run_remote_ceo_reply(prompt, browser_context=browser_context)
        append_message(
            sm,
            session["_id"],
            "assistant",
            reply,
            {"model": CEO_MODEL, "source": "remote_codex_vm"},
        )
        sm[SESSION_COLL].update_one(
            {"_id": session["_id"]},
            {"$set": {"last_remote_status": "success", "last_remote_run_at": iso_now()}},
        )
        update_job(
            sm,
            job_id,
            {
                "status": "completed",
                "finished_at": iso_now(),
                "last_heartbeat_at": iso_now(),
                "progress_message": "CEO reply sent.",
                "error_text": None,
            },
        )
        clear_active_job(sm, session["_id"], job_id)
        send_message(job["telegram_chat_id"], reply)
    except Exception as exc:
        error_text = (
            "The CEO team run failed before a reply came back.\n"
            f"Error: {str(exc)[-1200:]}"
        )
        log.exception("CEO team reply failed for job %s", job_id)
        try:
            job = sm[JOB_COLL].find_one({"_id": job_id})
            session_id = job["session_id"] if job else None
            chat_id = job["telegram_chat_id"] if job else None
            if session_id:
                append_message(sm, session_id, "system", error_text)
                sm[SESSION_COLL].update_one(
                    {"_id": session_id},
                    {"$set": {"last_remote_status": "failed", "last_remote_run_at": iso_now()}},
                )
                clear_active_job(sm, session_id, job_id)
            if job:
                update_job(
                    sm,
                    job_id,
                    {
                        "status": "failed",
                        "finished_at": iso_now(),
                        "last_heartbeat_at": iso_now(),
                        "progress_message": "CEO run failed.",
                        "error_text": error_text,
                    },
                )
            if chat_id:
                send_message(chat_id, error_text)
        except Exception:
            log.exception("Failed to record CEO Telegram job failure for %s", job_id)
    finally:
        client.close()


def extract_message_text(update: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return None, None
    text = message.get("text") or message.get("caption")
    return message, text


def poll_once(sm) -> int:
    state = get_bridge_state(sm)
    payload = {
        "timeout": 30,
        "allowed_updates": ["message", "edited_message"],
    }
    if state.get("last_update_id") is not None:
        payload["offset"] = int(state["last_update_id"]) + 1

    response = telegram_call("getUpdates", payload, timeout=TELEGRAM_TIMEOUT_SECONDS)
    updates = response.get("result", [])
    update_bridge_state(sm, {"last_poll_at": iso_now()})

    processed = 0
    for update in updates:
        update_id = update.get("update_id")
        if update_id is None:
            continue

        message, text = extract_message_text(update)
        chat_id = message.get("chat", {}).get("id") if message else None
        try:
            if not message:
                continue

            if chat_id not in ALLOWED_CHAT_IDS:
                log.warning("Skipping unauthorized update_id=%s chat_id=%s", update_id, chat_id)
                continue

            if not text:
                send_message(chat_id, "Text messages only for now.")
                processed += 1
                continue

            handle_text_message(sm, update, message, text.strip())
            processed += 1
        except Exception:
            log.exception("Failed processing update_id=%s chat_id=%s", update_id, chat_id)
            if chat_id in ALLOWED_CHAT_IDS:
                try:
                    send_message(chat_id, "The CEO Telegram bridge hit an internal error before replying.")
                except Exception:
                    log.exception("Failed to send fallback error for update_id=%s", update_id)
        finally:
            update_bridge_state(sm, {"last_update_id": update_id})

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram bridge for the CEO Codex team")
    parser.add_argument("--once", action="store_true", help="Poll Telegram once, then exit")
    parser.add_argument("--run-job", help="Run a queued CEO Telegram job by id")
    args = parser.parse_args()

    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not ALLOWED_CHAT_IDS:
        missing.append("TELEGRAM_ALLOWED_CHAT_IDS")
    if not COSMOS_URI:
        missing.append("COSMOS_CONNECTION_STRING")
    if missing:
        parser.error(f"Missing required environment variable(s): {', '.join(missing)}")

    log.info("CEO Telegram bridge starting")
    log.info("Allowed chat IDs: %s", ",".join(str(v) for v in sorted(ALLOWED_CHAT_IDS)))
    log.info("Remote host: %s", REMOTE_HOST)
    log.info("Model: %s", CEO_MODEL)

    if args.run_job:
        process_job(args.run_job)
        return

    register_bot_commands()

    client = get_client()
    sm = client["system_monitor"]

    try:
        while True:
            try:
                processed = poll_once(sm)
                if args.once:
                    break
                if processed == 0:
                    time.sleep(POLL_SECONDS)
            except KeyboardInterrupt:
                break
            except Exception:
                log.exception("Polling loop error")
                if args.once:
                    raise
                time.sleep(POLL_SECONDS)
    finally:
        client.close()
        log.info("CEO Telegram bridge stopped")


if __name__ == "__main__":
    main()
