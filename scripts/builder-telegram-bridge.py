#!/home/fields/venv/bin/python3
"""
Telegram bridge for the local builder/assistant Codex instance on this VM.

Flow:
1. Poll Telegram Bot API for inbound messages.
2. Persist session/message state in system_monitor.
3. Run a local Codex task in /home/fields/Fields_Orchestrator.
4. Return the Codex response to Telegram.

Required env vars:
  BUILDER_TELEGRAM_BOT_TOKEN
  BUILDER_TELEGRAM_ALLOWED_CHAT_IDS
  COSMOS_CONNECTION_STRING

Optional env vars:
  BUILDER_TELEGRAM_MODEL
  BUILDER_TELEGRAM_ROLE
  BUILDER_TELEGRAM_POLL_SECONDS
  BUILDER_TELEGRAM_TIMEOUT_SECONDS
  BUILDER_TELEGRAM_HISTORY_LIMIT
  BUILDER_TELEGRAM_CODEX_UNSANDBOXED
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from pymongo import MongoClient, ReturnDocument


ROOT = Path("/home/fields/Fields_Orchestrator")
ENV_PATH = ROOT / ".env"
IMPLEMENTATION_RUNS_DIR = ROOT / "artifacts" / "implementation-runs"
LATEST_CEO_RUN_PATH = ROOT / "artifacts" / "ceo-runs" / "LATEST_RUN.txt"
FOUNDER_REQUESTS_DIR = ROOT / "ceo-founder-requests"
AEST = ZoneInfo("Australia/Brisbane")
STATE_ID = "builder"
SESSION_COLL = "builder_chat_sessions"
MESSAGE_COLL = "builder_chat_messages"
STATE_COLL = "builder_chat_bridge_state"
JOB_COLL = "builder_chat_jobs"
MAX_TELEGRAM_MESSAGE = 4000
TELEGRAM_TIMEOUT_SECONDS = 35
JOB_HEARTBEAT_SECONDS = 15
JOB_LOG_TAIL_CHARS = 1600
MODEL_ALIASES = {
    "gpt-5.4-codex": "gpt-5.4",
}
DEFAULT_BUILDER_MODEL = "gpt-5.4"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(ENV_PATH)


def parse_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}: {raw}") from exc


def parse_bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean for {name}: {raw}")


def parse_chat_ids(raw: str) -> set[int]:
    values = set()
    for piece in raw.split(","):
        token = piece.strip()
        if token:
            values.add(int(token))
    if not values:
        raise RuntimeError("BUILDER_TELEGRAM_ALLOWED_CHAT_IDS is empty")
    return values


def resolve_builder_model(raw: str) -> str:
    requested = raw.strip()
    if not requested:
        return DEFAULT_BUILDER_MODEL
    return MODEL_ALIASES.get(requested, requested)


BOT_TOKEN = os.environ.get("BUILDER_TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_IDS = parse_chat_ids(os.environ["BUILDER_TELEGRAM_ALLOWED_CHAT_IDS"]) if os.environ.get("BUILDER_TELEGRAM_ALLOWED_CHAT_IDS") else set()
COSMOS_URI = os.environ.get("COSMOS_CONNECTION_STRING", "").strip()
BUILDER_MODEL = resolve_builder_model(os.environ.get("BUILDER_TELEGRAM_MODEL", DEFAULT_BUILDER_MODEL))
BUILDER_ROLE = os.environ.get("BUILDER_TELEGRAM_ROLE", "builder").strip() or "builder"
POLL_SECONDS = parse_int_env("BUILDER_TELEGRAM_POLL_SECONDS", 2)
RUN_TIMEOUT_SECONDS = parse_int_env("BUILDER_TELEGRAM_TIMEOUT_SECONDS", 1800)
HISTORY_LIMIT = parse_int_env("BUILDER_TELEGRAM_HISTORY_LIMIT", 12)
CODEX_UNSANDBOXED = parse_bool_env("BUILDER_TELEGRAM_CODEX_UNSANDBOXED", False)

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [builder-telegram] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("builder-telegram")


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


def normalize_workflow_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def detect_plaintext_workflow_action(
    session: dict[str, Any], text: str
) -> tuple[str, str] | None:
    normalized = normalize_workflow_text(text)
    if not normalized:
        return None

    if normalized == "review" or normalized.startswith("review "):
        return "review", text.strip()

    if normalized.startswith("revise plan:"):
        return "revise", text.split(":", 1)[1].strip()

    if normalized == "revise" or normalized.startswith("revise "):
        remainder = text.strip()[len("revise") :].strip(" :")
        return ("revise", remainder) if remainder else None

    if normalized in {"cancel", "cancel plan"}:
        return "cancel", "cancel plan"

    pending = get_pending_plan(session)
    if not pending:
        if normalized in {"approve", "approve plan"} or normalized.startswith("implement items"):
            return "approve", text.strip()
        return None

    approve_patterns = (
        r"approve(?: plan)?[.!]?",
        r"implement(?: the)?(?: approved)?(?: plan| scope| changes| fix(?:es)?)?[.!]?",
        r"implement items?\b.*",
        r"(?:please )?proceed(?: with)?(?: the)?(?: implementation| approved scope| approved plan| development| dev work| coding)?[.!]?",
        r"(?:please )?go ahead(?: and)?(?: implement| proceed| start(?: development| implementation| coding)?| do it)?[.!]?",
        r"(?:yes[, ]+)?(?:do it|start(?: development| implementation| coding)?)[.!]?",
    )
    deny_tokens = ("don't", "do not", "stop", "hold", "wait", "not yet", "cancel")
    if any(token in normalized for token in deny_tokens):
        return None
    if any(re.fullmatch(pattern, normalized) for pattern in approve_patterns):
        return "approve", text.strip()
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
            [{"text": "/status"}, {"text": "/reset"}],
            [{"text": "/review"}, {"text": "/revise"}],
            [{"text": "/approve"}, {"text": "/cancelplan"}],
            [{"text": "/task"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Chat normally, or tap a workflow command",
    }


def register_bot_commands() -> None:
    commands = [
        {"command": "start", "description": "Show chat and workflow help"},
        {"command": "help", "description": "Show chat and workflow help"},
        {"command": "status", "description": "Show bot or job status"},
        {"command": "reset", "description": "Start a new chat session"},
        {"command": "task", "description": "Create a founder request from chat"},
        {"command": "review", "description": "Create a review plan only"},
        {"command": "revise", "description": "Revise the pending plan"},
        {"command": "approve", "description": "Implement the pending plan"},
        {"command": "cancelplan", "description": "Cancel the pending plan"},
    ]
    try:
        telegram_call("setMyCommands", {"commands": commands}, timeout=30)
    except Exception as exc:
        log.warning("Failed to register builder bot commands: %s", exc)


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
        "bot": "builder",
        "last_update_id": None,
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
    session_id = f"builder_{chat['id']}_{timestamp}"
    now = iso_now()
    doc = {
        "_id": session_id,
        "platform": "telegram",
        "status": "active",
        "role": BUILDER_ROLE,
        "telegram_chat_id": chat["id"],
        "chat_type": chat.get("type"),
        "telegram_user_id": user.get("id"),
        "telegram_username": user.get("username"),
        "telegram_first_name": user.get("first_name"),
        "telegram_last_name": user.get("last_name"),
        "message_count": 0,
        "history_tail": [],
        "error_todo_items": [],
        "active_job_id": None,
        "created_at": now,
        "updated_at": now,
        "last_message_at": None,
        "last_run_status": None,
        "last_run_at": None,
    }
    sm[SESSION_COLL].insert_one(doc)
    return doc


def get_or_create_active_session(sm, chat: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    session = sm[SESSION_COLL].find_one(
        {
            "platform": "telegram",
            "telegram_chat_id": chat["id"],
            "status": "active",
        }
    )
    return session or create_session(sm, chat, user)


def reset_session(sm, chat: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    now = iso_now()
    sm[SESSION_COLL].update_many(
        {
            "platform": "telegram",
            "telegram_chat_id": chat["id"],
            "status": "active",
        },
        {"$set": {"status": "archived", "updated_at": now, "closed_at": now}},
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

    sm[MESSAGE_COLL].insert_one(
        {
            "session_id": session_id,
            "sequence": updated["message_count"],
            "platform": "telegram",
            "role": role,
            "text": text,
            "created_at": now,
            "metadata": metadata,
        }
    )
    return updated


def latest_ceo_run_dir() -> str:
    if LATEST_CEO_RUN_PATH.exists():
        raw = LATEST_CEO_RUN_PATH.read_text(encoding="utf-8", errors="replace").strip()
        if raw:
            return raw
    return str(ROOT / "artifacts" / "ceo-runs")


def create_implementation_run_dir(mode: str) -> tuple[str, Path]:
    run_id = f"{aest_now().strftime('%Y-%m-%d_%H%M%S')}_{mode}"
    run_dir = IMPLEMENTATION_RUNS_DIR / aest_now().strftime("%Y-%m-%d") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def create_job(
    sm,
    *,
    session: dict[str, Any],
    mode: str,
    founder_message: str,
    prompt: str,
    pending_plan: str | None = None,
) -> dict[str, Any]:
    run_id, run_dir = create_implementation_run_dir(mode)
    now = iso_now()
    job_id = f"{run_id}_{mode}"
    doc = {
        "_id": job_id,
        "session_id": session["_id"],
        "telegram_chat_id": session["telegram_chat_id"],
        "mode": mode,
        "status": "queued",
        "founder_message": founder_message,
        "prompt": prompt,
        "pending_plan": pending_plan,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "output_name": "review.md" if mode in {"review", "revise"} else "execution.md",
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "last_heartbeat_at": None,
        "pid": None,
        "last_log_tail": "",
        "progress_message": "Queued for execution.",
        "final_reply": None,
        "error_text": None,
    }
    sm[JOB_COLL].insert_one(doc)
    sm[SESSION_COLL].update_one(
        {"_id": session["_id"]},
        {
            "$set": {
                "active_job_id": job_id,
                "updated_at": now,
            }
        },
    )
    return doc


def write_implementation_artifact(
    run_id: str,
    run_dir: Path,
    mode: str,
    session_id: str,
    founder_message: str,
    prompt: str,
    reply: str,
    pending_plan: str | None = None,
) -> None:
    (run_dir / "request.txt").write_text(founder_message + "\n", encoding="utf-8")
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    output_name = "review.md" if mode in {"review", "revise"} else "execution.md"
    (run_dir / output_name).write_text(reply + "\n", encoding="utf-8")
    metadata = {
        "run_id": run_id,
        "mode": mode,
        "session_id": session_id,
        "created_at": iso_now(),
        "founder_message": founder_message,
        "pending_plan_present": bool(pending_plan),
        "latest_ceo_run_dir": latest_ceo_run_dir(),
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_dir = IMPLEMENTATION_RUNS_DIR
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "LATEST_RUN.txt").write_text(str(run_dir) + "\n", encoding="utf-8")


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


def pending_plan_summary(plan_text: str | None) -> str:
    if not plan_text:
        return "none"
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:160]
    return "pending review ready"


def append_error_todo(sm, session_id: str, summary: str) -> None:
    now = iso_now()
    sm[SESSION_COLL].update_one(
        {"_id": session_id},
        {
            "$push": {
                "error_todo_items": {
                    "$each": [{"summary": summary, "created_at": now}],
                    "$slice": -20,
                }
            },
            "$set": {"updated_at": now},
        },
    )


def founder_display_name(session: dict[str, Any]) -> str:
    first_name = (session.get("telegram_first_name") or "").strip()
    username = (session.get("telegram_username") or "").strip()
    if first_name:
        return first_name
    if username:
        return username
    return "Will"


def error_todo_summary(session: dict[str, Any]) -> str:
    items = session.get("error_todo_items", []) or []
    if not items:
        return "none"
    latest = items[-1]
    return f"{len(items)} item(s), latest: {str(latest.get('summary', ''))[:120]}"


def read_text_tail(path: Path, max_chars: int = JOB_LOG_TAIL_CHARS) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:].strip()


def build_codex_command(prompt_path: Path, output_path: Path, log_path: Path) -> list[str]:
    launch_mode = (
        "--dangerously-bypass-approvals-and-sandbox"
        if CODEX_UNSANDBOXED
        else "--full-auto"
    )
    command = (
        f"codex exec -m {shlex.quote(BUILDER_MODEL)} "
        f"--skip-git-repo-check {launch_mode} "
        f"-o {shlex.quote(str(output_path))} "
        f"\"$(cat {shlex.quote(str(prompt_path))})\" "
        f"> {shlex.quote(str(log_path))} 2>&1"
    )
    return ["bash", "-lc", command]


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


def infer_progress(job: dict[str, Any], log_tail: str) -> str:
    mode_label = {
        "review": "Running the implementation review",
        "revise": "Revising the pending plan",
        "execute": "Implementing the approved scope",
        "chat": "Working on the request",
    }.get(job.get("mode"), "Working on the request")
    if log_tail:
        lines = [line.strip() for line in log_tail.splitlines() if line.strip()]
        if lines:
            return f"{mode_label}. Latest activity: {lines[-1][:220]}"
    return f"{mode_label}. No detailed log output yet."


def build_job_status_text(session: dict[str, Any], job: dict[str, Any]) -> str:
    lines = [
        f"Active job: {job.get('mode', 'unknown')}",
        f"Status: {job.get('status', 'unknown')}",
        f"Started: {job.get('started_at') or 'queued'}",
        f"Elapsed: {elapsed_label(job.get('started_at'))}",
        f"Progress: {job.get('progress_message') or 'No progress message yet.'}",
    ]
    last_heartbeat = job.get("last_heartbeat_at")
    if last_heartbeat:
        lines.append(f"Last heartbeat: {last_heartbeat}")
    pending = get_pending_plan(session)
    if pending:
        lines.append(f"Pending plan: {pending_plan_summary(pending['text'])}")
    log_tail = (job.get("last_log_tail") or "").strip()
    if log_tail:
        lines.append("")
        lines.append("Recent log tail:")
        lines.append(log_tail[-900:])
    return "\n".join(lines)


def get_pending_plan(session: dict[str, Any]) -> dict[str, Any] | None:
    if not session.get("pending_plan_text"):
        return None
    return {
        "text": session.get("pending_plan_text"),
        "artifact_dir": session.get("pending_plan_artifact_dir"),
        "created_at": session.get("pending_plan_created_at"),
        "source_message": session.get("pending_plan_source_message"),
        "run_id": session.get("pending_plan_run_id"),
    }


def set_pending_plan(sm, session_id: str, *, plan_text: str, artifact_dir: Path, source_message: str, run_id: str) -> None:
    sm[SESSION_COLL].update_one(
        {"_id": session_id},
        {
            "$set": {
                "pending_plan_text": plan_text,
                "pending_plan_artifact_dir": str(artifact_dir),
                "pending_plan_created_at": iso_now(),
                "pending_plan_source_message": source_message,
                "pending_plan_run_id": run_id,
            }
        },
    )


def clear_pending_plan(sm, session_id: str) -> None:
    sm[SESSION_COLL].update_one(
        {"_id": session_id},
        {
            "$unset": {
                "pending_plan_text": "",
                "pending_plan_artifact_dir": "",
                "pending_plan_created_at": "",
                "pending_plan_source_message": "",
                "pending_plan_run_id": "",
            }
        },
    )


def build_prompt(session: dict[str, Any], latest_user_message: str) -> str:
    history_lines = []
    for item in session.get("history_tail", [])[-HISTORY_LIMIT:]:
        role = item.get("role", "unknown").upper()
        text = (item.get("text") or "").strip()
        if text:
            history_lines.append(f"{role}: {text}")

    history_block = "\n".join(history_lines) if history_lines else "No prior conversation."
    now_aest = aest_now().strftime("%Y-%m-%d %H:%M AEST")

    return f"""You are the Fields Implementer Telegram bot running Codex locally on the orchestrator VM.

Operating context:
- Repo root: /home/fields/Fields_Orchestrator
- Current role: {BUILDER_ROLE}
- Current time: {now_aest}
- The repository includes AGENTS.md with mandatory local workflow rules. Follow them.

Behavior:
- Treat the Telegram user as the founder/operator.
- Keep the tone warm, upbeat, and encouraging while staying concise and useful.
- Greet the founder naturally when it fits, especially on simple conversational turns.
- If the message asks for code or operational work, do the work in the repository rather than only describing it.
- Be concise in the final response, but include concrete outcomes, blockers, or next actions.
- Do not reveal secrets from env files, tokens, or credentials.
- Avoid destructive actions unless explicitly requested.
- If you changed files, the local workflow requires fix-history logging and GitHub backup via gh api.

Conversation history:
{history_block}

Latest founder message:
{latest_user_message}
"""


def build_review_prompt(session: dict[str, Any], latest_user_message: str, pending_plan: str | None = None) -> str:
    history_lines = []
    for item in session.get("history_tail", [])[-HISTORY_LIMIT:]:
        role = item.get("role", "unknown").upper()
        text = (item.get("text") or "").strip()
        if text:
            history_lines.append(f"{role}: {text}")
    history_block = "\n".join(history_lines) if history_lines else "No prior conversation."
    prior_plan = pending_plan.strip() if pending_plan else "None."
    error_todos = session.get("error_todo_items", []) or []
    error_block = "\n".join(
        f"- {item.get('summary')} ({item.get('created_at')})" for item in error_todos[-5:]
    ) if error_todos else "None."

    return f"""You are the Fields Implementor review gate running locally on the orchestrator VM.

Mode: review only
Hard rule: do not change code, files, services, ads, cron, databases, or infrastructure in this mode.

Your job:
1. Review the latest CEO team recommendations and founder request threads.
2. Validate, invalidate, defer, or mark items as needing founder input.
3. Produce a proposed implementation plan for the founder to review in Telegram.
4. Do not implement anything yet.
5. If you encounter any error, missing dependency, missing evidence, or blocked step during review, add it as an explicit TODO item in Proposed Plan.

Required review inputs:
- Latest CEO run artifacts: {latest_ceo_run_dir()}
- Founder requests: {FOUNDER_REQUESTS_DIR / 'open'}
- CEO replies: {FOUNDER_REQUESTS_DIR / 'responses'}
- Repo root: {ROOT}
- AGENTS.md workflow rules in this repository

Evidence policy:
- Use the synced CEO artifacts and local files as the default source of truth for this review.
- Do not query live MongoDB, Cosmos, or the `fields-ceo-briefing` path unless the founder explicitly asks or the local artifacts are genuinely insufficient.
- If live DB access fails but the local CEO artifacts are present, treat that as a non-blocking fallback, not a review error.
- Do not mention transient DB/DNS failures in the final review unless they materially block the founder's request.

Prior pending plan:
{prior_plan}

Open implementor error TODOs:
{error_block}

Conversation history:
{history_block}

Founder request:
{latest_user_message}

Return plain text with exactly these sections:
Implementation Review
Validated
Invalidated
Deferred
Needs Founder Input
Proposed Plan
Approval Options

In Approval Options, tell the founder to reply with one of:
- approve plan
- implement items ...
- revise plan: ...
- cancel plan
"""


def build_execute_prompt(session: dict[str, Any], founder_message: str, pending_plan: str) -> str:
    history_lines = []
    for item in session.get("history_tail", [])[-HISTORY_LIMIT:]:
        role = item.get("role", "unknown").upper()
        text = (item.get("text") or "").strip()
        if text:
            history_lines.append(f"{role}: {text}")
    history_block = "\n".join(history_lines) if history_lines else "No prior conversation."
    error_todos = session.get("error_todo_items", []) or []
    error_block = "\n".join(
        f"- {item.get('summary')} ({item.get('created_at')})" for item in error_todos[-5:]
    ) if error_todos else "None."

    return f"""You are the Fields Implementor running locally on the orchestrator VM.

Mode: approved implementation
Hard rule: implement only the approved scope below. Do not expand scope without explicit founder approval.

Approved review plan:
{pending_plan}

Founder approval message:
{founder_message}

Required inputs:
- Latest CEO run artifacts: {latest_ceo_run_dir()}
- Founder requests: {FOUNDER_REQUESTS_DIR / 'open'}
- CEO replies: {FOUNDER_REQUESTS_DIR / 'responses'}
- Repo root: {ROOT}
- AGENTS.md workflow rules in this repository

Evidence policy:
- Use the synced CEO artifacts and local repository state as the default source of truth.
- Do not query live MongoDB, Cosmos, or the `fields-ceo-briefing` path unless the approved work explicitly requires it.
- If live DB access fails but the approved implementation can proceed from local repo/artifact evidence, continue without surfacing that as a primary blocker.

Conversation history:
{history_block}

Open implementor error TODOs:
{error_block}

Execution requirements:
- Validate CEO suggestions against the live repo before editing.
- Implement only what is approved.
- Follow all local workflow rules, including fix-history logging and GitHub backup via gh api if files change.
- In the final response, summarize what was implemented, what was rejected, verification, and any remaining blockers.
- If you hit any execution error or blocked step, convert it into an explicit TODO item in your final response instead of burying it in narrative.
"""


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

        run_dir = Path(job["run_dir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = run_dir / "prompt.txt"
        output_path = run_dir / "output.txt"
        log_path = run_dir / "codex.log"
        prompt_path.write_text(job["prompt"], encoding="utf-8")
        (run_dir / "request.txt").write_text(job["founder_message"] + "\n", encoding="utf-8")

        cmd = build_codex_command(prompt_path, output_path, log_path)
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            text=True,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        update_job(
            sm,
            job_id,
            {
                "status": "running",
                "pid": proc.pid,
                "started_at": iso_now(),
                "last_heartbeat_at": iso_now(),
                "progress_message": (
                    "Job started in unsandboxed Codex mode."
                    if CODEX_UNSANDBOXED
                    else "Job started in sandboxed Codex mode."
                ),
            },
        )

        start_ts = time.time()
        last_heartbeat_sent = start_ts
        while True:
            return_code = proc.poll()
            now_ts = time.time()
            if now_ts - start_ts > RUN_TIMEOUT_SECONDS:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                log_tail = read_text_tail(log_path)
                error_text = (
                    f"The {job['mode']} run timed out after {RUN_TIMEOUT_SECONDS} seconds before a reply came back.\n"
                    f"Error: {(log_tail or 'Timed out without detailed log output.')[-1200:]}"
                )
                append_error_todo(sm, session["_id"], f"{job['mode']} timed out after {RUN_TIMEOUT_SECONDS}s")
                append_message(sm, session["_id"], "system", error_text)
                sm[SESSION_COLL].update_one(
                    {"_id": session["_id"]},
                    {"$set": {"last_run_status": "failed", "last_run_at": iso_now()}},
                )
                update_job(
                    sm,
                    job_id,
                    {
                        "status": "failed",
                        "finished_at": iso_now(),
                        "last_heartbeat_at": iso_now(),
                        "last_log_tail": log_tail,
                        "progress_message": "Job timed out.",
                        "error_text": error_text,
                    },
                )
                clear_active_job(sm, session["_id"], job_id)
                send_message(job["telegram_chat_id"], error_text)
                return
            if now_ts - last_heartbeat_sent >= JOB_HEARTBEAT_SECONDS:
                log_tail = read_text_tail(log_path)
                update_job(
                    sm,
                    job_id,
                    {
                        "last_heartbeat_at": iso_now(),
                        "last_log_tail": log_tail,
                        "progress_message": infer_progress(job, log_tail),
                    },
                )
                last_heartbeat_sent = now_ts
            if return_code is not None:
                break
            time.sleep(1)

        log_tail = read_text_tail(log_path)
        if proc.returncode != 0:
            detail = (log_tail or "Local Codex run failed").strip()
            error_text = f"The {job['mode']} run failed before a reply came back.\nError: {detail[-1200:]}"
            append_error_todo(sm, session["_id"], f"{job['mode']} failed: {detail[:300]}")
            append_message(sm, session["_id"], "system", error_text)
            sm[SESSION_COLL].update_one(
                {"_id": session["_id"]},
                {"$set": {"last_run_status": "failed", "last_run_at": iso_now()}},
            )
            update_job(
                sm,
                job_id,
                {
                    "status": "failed",
                    "finished_at": iso_now(),
                    "last_heartbeat_at": iso_now(),
                    "last_log_tail": log_tail,
                    "progress_message": "Job failed.",
                    "error_text": error_text,
                },
            )
            clear_active_job(sm, session["_id"], job_id)
            send_message(job["telegram_chat_id"], error_text)
            return

        reply = output_path.read_text(encoding="utf-8", errors="replace").strip() if output_path.exists() else ""
        if not reply:
            error_text = f"The {job['mode']} run finished without producing a reply."
            append_error_todo(sm, session["_id"], error_text[:300])
            append_message(sm, session["_id"], "system", error_text)
            sm[SESSION_COLL].update_one(
                {"_id": session["_id"]},
                {"$set": {"last_run_status": "failed", "last_run_at": iso_now()}},
            )
            update_job(
                sm,
                job_id,
                {
                    "status": "failed",
                    "finished_at": iso_now(),
                    "last_heartbeat_at": iso_now(),
                    "last_log_tail": log_tail,
                    "progress_message": "Job finished without output.",
                    "error_text": error_text,
                },
            )
            clear_active_job(sm, session["_id"], job_id)
            send_message(job["telegram_chat_id"], error_text)
            return

        write_implementation_artifact(
            job["run_id"],
            run_dir,
            job["mode"],
            session["_id"],
            job["founder_message"],
            job["prompt"],
            reply,
            pending_plan=job.get("pending_plan"),
        )

        if job["mode"] in {"review", "revise"}:
            set_pending_plan(
                sm,
                session["_id"],
                plan_text=reply,
                artifact_dir=run_dir,
                source_message=job["founder_message"],
                run_id=job["run_id"],
            )
        elif job["mode"] == "execute":
            clear_pending_plan(sm, session["_id"])

        append_message(sm, session["_id"], "assistant", reply, {"mode": job["mode"], "artifact_dir": str(run_dir)})
        sm[SESSION_COLL].update_one(
            {"_id": session["_id"]},
            {"$set": {"last_run_status": "success", "last_run_at": iso_now()}},
        )
        update_job(
            sm,
            job_id,
            {
                "status": "completed",
                "finished_at": iso_now(),
                "last_heartbeat_at": iso_now(),
                "last_log_tail": log_tail,
                "progress_message": "Job completed.",
                "final_reply": reply,
            },
        )
        clear_active_job(sm, session["_id"], job_id)
        send_message(job["telegram_chat_id"], reply)
    finally:
        client.close()


def format_status(sm, session: dict[str, Any]) -> str:
    state = get_bridge_state(sm)
    pending = get_pending_plan(session)
    active_job = get_active_job(sm, session)
    active_job_summary = "none"
    if active_job:
        active_job_summary = f"{active_job.get('mode')} ({active_job.get('status')}, {elapsed_label(active_job.get('started_at'))})"
    return (
        f"Fields Implementer bot is live.\n"
        f"Role: {BUILDER_ROLE}\n"
        f"Model: {BUILDER_MODEL}\n"
        f"Session: {session['_id']}\n"
        f"Messages in session: {session.get('message_count', 0)}\n"
        f"Active job: {active_job_summary}\n"
        f"Pending plan: {pending_plan_summary(pending['text']) if pending else 'none'}\n"
        f"Error TODOs: {error_todo_summary(session)}\n"
        f"Last poll: {state.get('last_poll_at', 'never')}\n"
        f"Last run: {session.get('last_run_at', 'never')}"
    )


def run_workflow_action(sm, session: dict[str, Any], chat_id: int, action: str, instruction: str) -> None:
    active_job = get_active_job(sm, session)
    pending = get_pending_plan(session)
    founder_name = founder_display_name(session)

    if action == "cancel":
        clear_pending_plan(sm, session["_id"])
        reply = "Cancelled the pending implementation plan. No code was changed."
        append_message(sm, session["_id"], "assistant", reply, {"mode": "cancel"})
        send_message(chat_id, reply)
        return

    if action == "review":
        if active_job:
            reply = "There is already an active job running. Ask for `/status` or wait for it to finish before starting a new review."
            append_message(sm, session["_id"], "assistant", reply, {"mode": "review_blocked", "job_id": active_job["_id"]})
            send_message(chat_id, reply)
            return
        send_message(chat_id, f"Hey, {founder_name}! I’m reviewing it now and I’ll send back a plan before I change anything.")
        prompt = build_review_prompt(session, instruction)
        job = create_job(sm, session=session, mode="review", founder_message=instruction, prompt=prompt)
        launch_background_job(job["_id"])
        return

    if action == "revise":
        if not pending:
            reply = "There is no pending plan to revise. Start with `/review ...`."
            append_message(sm, session["_id"], "assistant", reply, {"mode": "revise_missing"})
            send_message(chat_id, reply)
            return
        if active_job:
            reply = "There is already an active job running. Wait for it to finish before revising the plan."
            append_message(sm, session["_id"], "assistant", reply, {"mode": "revise_blocked", "job_id": active_job["_id"]})
            send_message(chat_id, reply)
            return
        send_message(chat_id, f"Hey, {founder_name}! I’m tightening up the plan now. No code changes in this step.")
        founder_message = f"Revise the pending implementation plan using this founder amendment:\n{instruction}"
        prompt = build_review_prompt(session, founder_message, pending_plan=pending["text"])
        job = create_job(
            sm,
            session=session,
            mode="revise",
            founder_message=founder_message,
            prompt=prompt,
            pending_plan=pending["text"],
        )
        launch_background_job(job["_id"])
        return

    if action == "approve":
        if not pending:
            reply = "There is no approved candidate plan waiting. Start with `/review ...`."
            append_message(sm, session["_id"], "assistant", reply, {"mode": "approve_missing"})
            send_message(chat_id, reply)
            return
        if active_job:
            reply = "There is already an active job running. Wait for it to finish before starting another implementation run."
            append_message(sm, session["_id"], "assistant", reply, {"mode": "approve_blocked", "job_id": active_job["_id"]})
            send_message(chat_id, reply)
            return
        send_message(chat_id, f"Love it, {founder_name}. I’m on it and I’ll stick to the approved scope, then report back here.")
        prompt = build_execute_prompt(session, instruction or "approve plan", pending["text"])
        job = create_job(
            sm,
            session=session,
            mode="execute",
            founder_message=instruction or "approve plan",
            prompt=prompt,
            pending_plan=pending["text"],
        )
        launch_background_job(job["_id"])
        return

    raise RuntimeError(f"Unsupported workflow action: {action}")


def handle_command(sm, chat: dict[str, Any], user: dict[str, Any], text: str) -> bool:
    stripped = text.strip()
    command, _, remainder = stripped.partition(" ")
    command = command.lower()
    remainder = remainder.strip()
    session = get_or_create_active_session(sm, chat, user)
    founder_name = founder_display_name(session)

    if command in {"/start", "/help"}:
        send_message(
            chat["id"],
            f"Hey, {founder_name}! Fields Implementer is live on the VM and ready to help.\n"
            "Plain text messages stay in chat mode.\n"
            "Workflow actions also accept plain text: `review ...`, `revise plan: ...`, `approve plan`, `implement items ...`, `cancel plan`.\n"
            "Slash commands still work too: `/review ...`, `/revise ...`, `/approve`, `/cancelplan`.\n"
            "Create a durable founder request with `/task ...`.\n"
            "Other commands: `/status`, `/reset`.",
        )
        return True

    if command == "/status":
        active_job = get_active_job(sm, session)
        send_message(chat["id"], build_job_status_text(session, active_job) if active_job else format_status(sm, session))
        return True

    if command == "/reset":
        new_session = reset_session(sm, chat, user)
        send_message(chat["id"], f"Fresh start, {founder_name}. New builder session: {new_session['_id']}")
        return True

    if command == "/task":
        task_text = remainder or latest_user_message_text(session)
        if not task_text:
            send_message(chat["id"], "Provide task text after `/task ...`, or send the task in chat first and then reply with `/task`.")
            return True
        path = create_founder_request_file("engineering", task_text, "telegram_builder")
        reply = (
            f"Created founder request `{path.name}` in `ceo-founder-requests/open`.\n"
            "It will persist for future CEO and implementor review cycles."
        )
        append_message(sm, session["_id"], "assistant", reply, {"mode": "task_create", "path": str(path)})
        send_message(chat["id"], reply)
        return True

    if command == "/review":
        instruction = remainder or latest_user_message_text(session)
        if not instruction:
            send_message(chat["id"], "Provide review scope after `/review ...`, or send the issue in chat first and then run `/review`.")
            return True
        run_workflow_action(sm, session, chat["id"], "review", instruction)
        return True

    if command == "/revise":
        if not remainder:
            send_message(chat["id"], "Provide the amendment after `/revise ...`.")
            return True
        run_workflow_action(sm, session, chat["id"], "revise", remainder)
        return True

    if command in {"/approve", "/implement"}:
        run_workflow_action(sm, session, chat["id"], "approve", remainder or "approve plan")
        return True

    if command in {"/cancelplan", "/cancel"}:
        run_workflow_action(sm, session, chat["id"], "cancel", "cancel plan")
        return True

    return False


def handle_text_message(sm, update: dict[str, Any], message: dict[str, Any], text: str) -> None:
    chat = message["chat"]
    user = message.get("from", {})
    chat_id = chat["id"]

    if chat_id not in ALLOWED_CHAT_IDS:
        log.warning("Ignoring Telegram message from unauthorized chat_id=%s", chat_id)
        return

    if text.startswith("/") and handle_command(sm, chat, user, text):
        return

    session = get_or_create_active_session(sm, chat, user)
    workflow_action = detect_plaintext_workflow_action(session, text)
    if workflow_action:
        session = append_message(
            sm,
            session["_id"],
            "user",
            text,
            {
                "telegram_update_id": update.get("update_id"),
                "telegram_message_id": message.get("message_id"),
                "workflow_action": workflow_action[0],
            },
        )
        run_workflow_action(sm, session, chat_id, workflow_action[0], workflow_action[1])
        return

    founder_name = founder_display_name(session)
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
    active_job = get_active_job(sm, session)

    if active_job:
        reply = (
            "There is already an active job running for this chat. "
            "Ask for `/status` or wait for the current run to finish before sending a new request."
        )
        append_message(sm, session["_id"], "assistant", reply, {"mode": "busy", "job_id": active_job["_id"]})
        send_message(chat_id, reply)
        return

    send_message(chat_id, f"Hey, {founder_name}! I’m on it here on the VM. I’ll send the result back in this chat.")
    prompt = build_prompt(session, text)
    job = create_job(sm, session=session, mode="chat", founder_message=text, prompt=prompt)
    launch_background_job(job["_id"])


def extract_message_text(update: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return None, None
    text = message.get("text") or message.get("caption")
    return message, text


def poll_once(sm) -> int:
    state = get_bridge_state(sm)
    payload: dict[str, Any] = {"timeout": 30, "allowed_updates": ["message", "edited_message"]}
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
        if not message:
            update_bridge_state(sm, {"last_update_id": update_id})
            continue

        chat_id = message.get("chat", {}).get("id")
        if chat_id not in ALLOWED_CHAT_IDS:
            log.warning("Skipping unauthorized update_id=%s chat_id=%s", update_id, chat_id)
            update_bridge_state(sm, {"last_update_id": update_id})
            continue

        if not text:
            send_message(chat_id, "Text messages only for now.")
            update_bridge_state(sm, {"last_update_id": update_id})
            processed += 1
            continue

        handle_text_message(sm, update, message, text.strip())
        update_bridge_state(sm, {"last_update_id": update_id})
        processed += 1

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram bridge for the local builder Codex bot")
    parser.add_argument("--once", action="store_true", help="Poll Telegram once, then exit")
    parser.add_argument("--run-job", help="Run a single queued builder job by id, then exit")
    args = parser.parse_args()

    missing = []
    if not BOT_TOKEN:
        missing.append("BUILDER_TELEGRAM_BOT_TOKEN")
    if not ALLOWED_CHAT_IDS:
        missing.append("BUILDER_TELEGRAM_ALLOWED_CHAT_IDS")
    if not COSMOS_URI:
        missing.append("COSMOS_CONNECTION_STRING")
    if missing:
        parser.error(f"Missing required environment variable(s): {', '.join(missing)}")

    log.info("Builder Telegram bridge starting")
    log.info("Allowed chat IDs: %s", ",".join(str(v) for v in sorted(ALLOWED_CHAT_IDS)))
    log.info("Model: %s", BUILDER_MODEL)
    log.info("Role: %s", BUILDER_ROLE)
    register_bot_commands()

    client = get_client()
    sm = client["system_monitor"]
    try:
        if args.run_job:
            process_job(args.run_job)
            return
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
        log.info("Builder Telegram bridge stopped")


if __name__ == "__main__":
    main()
