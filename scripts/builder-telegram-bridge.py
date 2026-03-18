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
import tempfile
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
MAX_TELEGRAM_MESSAGE = 4000
TELEGRAM_TIMEOUT_SECONDS = 35


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


def parse_chat_ids(raw: str) -> set[int]:
    values = set()
    for piece in raw.split(","):
        token = piece.strip()
        if token:
            values.add(int(token))
    if not values:
        raise RuntimeError("BUILDER_TELEGRAM_ALLOWED_CHAT_IDS is empty")
    return values


BOT_TOKEN = os.environ.get("BUILDER_TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_IDS = parse_chat_ids(os.environ["BUILDER_TELEGRAM_ALLOWED_CHAT_IDS"]) if os.environ.get("BUILDER_TELEGRAM_ALLOWED_CHAT_IDS") else set()
COSMOS_URI = os.environ.get("COSMOS_CONNECTION_STRING", "").strip()
BUILDER_MODEL = os.environ.get("BUILDER_TELEGRAM_MODEL", "gpt-5.1-codex").strip() or "gpt-5.1-codex"
BUILDER_ROLE = os.environ.get("BUILDER_TELEGRAM_ROLE", "builder").strip() or "builder"
POLL_SECONDS = parse_int_env("BUILDER_TELEGRAM_POLL_SECONDS", 2)
RUN_TIMEOUT_SECONDS = parse_int_env("BUILDER_TELEGRAM_TIMEOUT_SECONDS", 1800)
HISTORY_LIMIT = parse_int_env("BUILDER_TELEGRAM_HISTORY_LIMIT", 12)

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


def send_message(chat_id: int, text: str) -> None:
    for chunk in chunk_text(text):
        telegram_call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )


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


def pending_plan_summary(plan_text: str | None) -> str:
    if not plan_text:
        return "none"
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:160]
    return "pending review ready"


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


def classify_workflow_command(text: str) -> dict[str, str] | None:
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.startswith("review ceo") or lowered.startswith("review founder issue") or lowered.startswith("review today"):
        return {"action": "review", "instruction": stripped}
    if lowered.startswith("revise plan:"):
        return {"action": "revise", "instruction": stripped.split(":", 1)[1].strip()}
    if lowered.startswith("revise plan "):
        return {"action": "revise", "instruction": stripped[len("revise plan ") :].strip()}
    if lowered in {"approve plan", "approve"} or lowered.startswith("approve plan ") or lowered.startswith("implement items"):
        return {"action": "approve", "instruction": stripped}
    if lowered in {"cancel plan", "cancel review", "cancel"}:
        return {"action": "cancel", "instruction": stripped}
    return None


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

    return f"""You are the Fields Implementor review gate running locally on the orchestrator VM.

Mode: review only
Hard rule: do not change code, files, services, ads, cron, databases, or infrastructure in this mode.

Your job:
1. Review the latest CEO team recommendations and founder request threads.
2. Validate, invalidate, defer, or mark items as needing founder input.
3. Produce a proposed implementation plan for the founder to review in Telegram.
4. Do not implement anything yet.

Required review inputs:
- Latest CEO run artifacts: {latest_ceo_run_dir()}
- Founder requests: {FOUNDER_REQUESTS_DIR / 'open'}
- CEO replies: {FOUNDER_REQUESTS_DIR / 'responses'}
- Repo root: {ROOT}
- AGENTS.md workflow rules in this repository

Prior pending plan:
{prior_plan}

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

Conversation history:
{history_block}

Execution requirements:
- Validate CEO suggestions against the live repo before editing.
- Implement only what is approved.
- Follow all local workflow rules, including fix-history logging and GitHub backup via gh api if files change.
- In the final response, summarize what was implemented, what was rejected, verification, and any remaining blockers.
"""


def run_local_builder_reply(prompt: str) -> str:
    with tempfile.TemporaryDirectory(prefix="builder-telegram-") as tmp_dir:
        prompt_path = Path(tmp_dir) / "prompt.txt"
        output_path = Path(tmp_dir) / "output.txt"
        log_path = Path(tmp_dir) / "codex.log"

        prompt_path.write_text(prompt, encoding="utf-8")
        cmd = [
            "bash",
            "-lc",
            (
                f"codex exec -m {shlex.quote(BUILDER_MODEL)} "
                f"--skip-git-repo-check --full-auto "
                f"-o {shlex.quote(str(output_path))} "
                f"\"$(cat {shlex.quote(str(prompt_path))})\" "
                f"> {shlex.quote(str(log_path))} 2>&1"
            ),
        ]
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )

        if result.returncode != 0:
            log_tail = ""
            if log_path.exists():
                log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            detail = (log_tail or result.stderr or result.stdout or "Local Codex run failed").strip()
            raise RuntimeError(detail)

        reply = output_path.read_text(encoding="utf-8", errors="replace").strip() if output_path.exists() else ""
        if not reply:
            raise RuntimeError("Local Codex returned an empty response")
        return reply


def format_status(sm, session: dict[str, Any]) -> str:
    state = get_bridge_state(sm)
    pending = get_pending_plan(session)
    return (
        f"Fields Implementer bot is live.\n"
        f"Role: {BUILDER_ROLE}\n"
        f"Model: {BUILDER_MODEL}\n"
        f"Session: {session['_id']}\n"
        f"Messages in session: {session.get('message_count', 0)}\n"
        f"Pending plan: {pending_plan_summary(pending['text']) if pending else 'none'}\n"
        f"Last poll: {state.get('last_poll_at', 'never')}\n"
        f"Last run: {session.get('last_run_at', 'never')}"
    )


def handle_command(sm, chat: dict[str, Any], user: dict[str, Any], text: str) -> bool:
    command = text.strip().split()[0].lower()
    session = get_or_create_active_session(sm, chat, user)

    if command == "/start":
        send_message(
            chat["id"],
            "Fields Implementer bot is ready on this VM.\n"
            "Use `review ceo team's recommendations for today` to start a review.\n"
            "Execution requires explicit approval after the plan comes back.\n"
            "Commands: /status, /reset",
        )
        return True

    if command == "/status":
        send_message(chat["id"], format_status(sm, session))
        return True

    if command == "/reset":
        new_session = reset_session(sm, chat, user)
        send_message(chat["id"], f"Started a new builder session: {new_session['_id']}")
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

    workflow = classify_workflow_command(text)
    if workflow:
        action = workflow["action"]
        pending = get_pending_plan(session)

        if action == "cancel":
            clear_pending_plan(sm, session["_id"])
            reply = "Cancelled the pending implementation plan. No code was changed."
            append_message(sm, session["_id"], "assistant", reply, {"mode": "cancel"})
            send_message(chat_id, reply)
            return

        if action == "review":
            send_message(chat_id, "Running an implementation review only. I’ll validate the CEO team’s recommendations and send a plan for approval before any changes.")
            send_chat_action(chat_id)
            mode = "review"
            prompt = build_review_prompt(session, workflow["instruction"])
            try:
                reply = run_local_builder_reply(prompt)
                run_id, run_dir = create_implementation_run_dir(mode)
                write_implementation_artifact(run_id, run_dir, mode, session["_id"], workflow["instruction"], prompt, reply)
                set_pending_plan(
                    sm,
                    session["_id"],
                    plan_text=reply,
                    artifact_dir=run_dir,
                    source_message=workflow["instruction"],
                    run_id=run_id,
                )
                append_message(sm, session["_id"], "assistant", reply, {"mode": mode, "artifact_dir": str(run_dir)})
                sm[SESSION_COLL].update_one(
                    {"_id": session["_id"]},
                    {"$set": {"last_run_status": "success", "last_run_at": iso_now()}},
                )
                send_message(chat_id, reply)
            except Exception as exc:
                error_text = "The implementation review failed before a reply came back.\n" f"Error: {str(exc)[-1200:]}"
                log.exception("Builder review failed for session %s", session["_id"])
                append_message(sm, session["_id"], "system", error_text)
                sm[SESSION_COLL].update_one(
                    {"_id": session["_id"]},
                    {"$set": {"last_run_status": "failed", "last_run_at": iso_now()}},
                )
                send_message(chat_id, error_text)
            return

        if action == "revise":
            if not pending:
                reply = "There is no pending plan to revise. Start with `review ceo team's recommendations for today`."
                append_message(sm, session["_id"], "assistant", reply, {"mode": "revise_missing"})
                send_message(chat_id, reply)
                return
            send_message(chat_id, "Revising the pending implementation plan. No code changes will be made in this step.")
            send_chat_action(chat_id)
            mode = "revise"
            founder_message = f"Revise the pending implementation plan using this founder amendment:\n{workflow['instruction']}"
            prompt = build_review_prompt(session, founder_message, pending_plan=pending["text"])
            try:
                reply = run_local_builder_reply(prompt)
                run_id, run_dir = create_implementation_run_dir(mode)
                write_implementation_artifact(
                    run_id,
                    run_dir,
                    mode,
                    session["_id"],
                    founder_message,
                    prompt,
                    reply,
                    pending_plan=pending["text"],
                )
                set_pending_plan(
                    sm,
                    session["_id"],
                    plan_text=reply,
                    artifact_dir=run_dir,
                    source_message=founder_message,
                    run_id=run_id,
                )
                append_message(sm, session["_id"], "assistant", reply, {"mode": mode, "artifact_dir": str(run_dir)})
                sm[SESSION_COLL].update_one(
                    {"_id": session["_id"]},
                    {"$set": {"last_run_status": "success", "last_run_at": iso_now()}},
                )
                send_message(chat_id, reply)
            except Exception as exc:
                error_text = "The plan revision failed before a reply came back.\n" f"Error: {str(exc)[-1200:]}"
                log.exception("Builder revise failed for session %s", session["_id"])
                append_message(sm, session["_id"], "system", error_text)
                sm[SESSION_COLL].update_one(
                    {"_id": session["_id"]},
                    {"$set": {"last_run_status": "failed", "last_run_at": iso_now()}},
                )
                send_message(chat_id, error_text)
            return

        if action == "approve":
            if not pending:
                reply = "There is no approved candidate plan waiting. Start with `review ceo team's recommendations for today`."
                append_message(sm, session["_id"], "assistant", reply, {"mode": "approve_missing"})
                send_message(chat_id, reply)
                return
            send_message(chat_id, "Approval received. I’m implementing only the approved scope from the pending plan and will report back here.")
            send_chat_action(chat_id)
            mode = "execute"
            prompt = build_execute_prompt(session, workflow["instruction"], pending["text"])
            try:
                reply = run_local_builder_reply(prompt)
                run_id, run_dir = create_implementation_run_dir(mode)
                write_implementation_artifact(
                    run_id,
                    run_dir,
                    mode,
                    session["_id"],
                    workflow["instruction"],
                    prompt,
                    reply,
                    pending_plan=pending["text"],
                )
                clear_pending_plan(sm, session["_id"])
                append_message(sm, session["_id"], "assistant", reply, {"mode": mode, "artifact_dir": str(run_dir)})
                sm[SESSION_COLL].update_one(
                    {"_id": session["_id"]},
                    {"$set": {"last_run_status": "success", "last_run_at": iso_now()}},
                )
                send_message(chat_id, reply)
            except Exception as exc:
                error_text = "The approved implementation run failed before a reply came back.\n" f"Error: {str(exc)[-1200:]}"
                log.exception("Builder execute failed for session %s", session["_id"])
                append_message(sm, session["_id"], "system", error_text)
                sm[SESSION_COLL].update_one(
                    {"_id": session["_id"]},
                    {"$set": {"last_run_status": "failed", "last_run_at": iso_now()}},
                )
                send_message(chat_id, error_text)
            return

    send_message(chat_id, "Working on it here on the VM. I’ll send the result back in this chat.")
    send_chat_action(chat_id)

    try:
        prompt = build_prompt(session, text)
        reply = run_local_builder_reply(prompt)
        append_message(
            sm,
            session["_id"],
            "assistant",
            reply,
            {"model": BUILDER_MODEL, "source": "local_codex_vm"},
        )
        sm[SESSION_COLL].update_one(
            {"_id": session["_id"]},
            {"$set": {"last_run_status": "success", "last_run_at": iso_now()}},
        )
        send_message(chat_id, reply)
    except Exception as exc:
        error_text = (
            "The local builder run failed before a reply came back.\n"
            f"Error: {str(exc)[-1200:]}"
        )
        log.exception("Builder reply failed for session %s", session["_id"])
        append_message(sm, session["_id"], "system", error_text)
        sm[SESSION_COLL].update_one(
            {"_id": session["_id"]},
            {"$set": {"last_run_status": "failed", "last_run_at": iso_now()}},
        )
        send_message(chat_id, error_text)


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
        log.info("Builder Telegram bridge stopped")


if __name__ == "__main__":
    main()
