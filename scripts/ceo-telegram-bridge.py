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
AEST = ZoneInfo("Australia/Brisbane")
STATE_ID = "telegram"
SESSION_COLL = "ceo_chat_sessions"
MESSAGE_COLL = "ceo_chat_messages"
STATE_COLL = "ceo_chat_bridge_state"
MAX_TELEGRAM_MESSAGE = 4000


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


BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_IDS = parse_chat_ids(os.environ["TELEGRAM_ALLOWED_CHAT_IDS"]) if os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS") else set()
COSMOS_URI = os.environ.get("COSMOS_CONNECTION_STRING", "").strip()
CEO_MODEL = os.environ.get("CEO_TELEGRAM_MODEL", "gpt-5.1-codex").strip() or "gpt-5.1-codex"
REMOTE_HOST = os.environ.get("CEO_TELEGRAM_REMOTE_HOST", "fields-orchestrator-vm@35.201.6.222").strip()
REMOTE_CONTEXT_DIR = os.environ.get(
    "CEO_TELEGRAM_REMOTE_CONTEXT_DIR",
    "/home/fields-orchestrator-vm/ceo-agents/context",
).strip()
CONTEXT_SYNC_MINUTES = parse_int_env("CEO_TELEGRAM_CONTEXT_SYNC_MINUTES", 30)
POLL_SECONDS = parse_int_env("CEO_TELEGRAM_POLL_SECONDS", 2)
REMOTE_TIMEOUT_SECONDS = parse_int_env("CEO_TELEGRAM_REMOTE_TIMEOUT_SECONDS", 1200)
HISTORY_LIMIT = parse_int_env("CEO_TELEGRAM_HISTORY_LIMIT", 12)
TELEGRAM_TIMEOUT_SECONDS = 35

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


def build_prompt(session: dict[str, Any], latest_user_message: str) -> str:
    history_lines = []
    for item in session.get("history_tail", [])[-HISTORY_LIMIT:]:
        role = item.get("role", "unknown").upper()
        text = (item.get("text") or "").strip()
        if text:
            history_lines.append(f"{role}: {text}")

    history_block = "\n".join(history_lines) if history_lines else "No prior conversation."
    now_aest = aest_now().strftime("%Y-%m-%d %H:%M AEST")

    return f"""You are the Fields Estate CEO team responding to the founder inside Telegram.

You represent three perspectives at once:
- Engineering
- Growth
- Product

Work in read-only mode. Use the local `context/` directory as the source of truth for company state. Read files as needed before answering. Do not create proposals, branches, commits, or code changes. This is a direct advisory response, not a batch proposal run.

Response style:
- Be concise, direct, and operational.
- Answer the founder's message first.
- Where useful, separate Engineering / Growth / Product views.
- End with the single best next action.
- If you are missing evidence, say exactly what is missing.
- Maximum 700 words.

Current time: {now_aest}
Telegram session: {session["_id"]}

Conversation history:
{history_block}

Latest founder message:
{latest_user_message}
"""


def run_remote_ceo_reply(prompt: str) -> str:
    remote_token = uuid.uuid4().hex
    prompt_path = f"/tmp/ceo_telegram_prompt_{remote_token}.txt"
    quoted_prompt_path = shlex.quote(prompt_path)

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
    return (
        f"CEO Telegram bridge is live.\n"
        f"Session: {session['_id']}\n"
        f"Messages in session: {session.get('message_count', 0)}\n"
        f"Last context sync: {last_sync}\n"
        f"Last CEO run: {last_remote}"
    )


def handle_command(sm, chat: dict[str, Any], user: dict[str, Any], text: str) -> bool:
    command = text.strip().split()[0].lower()
    session = get_or_create_active_session(sm, chat, user)

    if command == "/start":
        send_message(
            chat["id"],
            "CEO Telegram bridge is ready. Send any message to route it to the Codex CEO team.\n"
            "Commands: /status, /reset, /sync",
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

    send_message(chat_id, "Routing this to the CEO team. I’ll send the reply back here.")
    send_chat_action(chat_id)

    ok, detail = maybe_refresh_context(sm, force=False)
    if not ok:
        error_text = "Context refresh failed, so I did not send this to the CEO team.\n" + detail[-800:]
        append_message(sm, session["_id"], "system", error_text)
        send_message(chat_id, error_text)
        return

    try:
        prompt = build_prompt(session, text)
        reply = run_remote_ceo_reply(prompt)
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
        send_message(chat_id, reply)
    except Exception as exc:
        error_text = (
            "The CEO team run failed before a reply came back.\n"
            f"Error: {str(exc)[-1200:]}"
        )
        log.exception("CEO team reply failed for session %s", session["_id"])
        append_message(sm, session["_id"], "system", error_text)
        sm[SESSION_COLL].update_one(
            {"_id": session["_id"]},
            {"$set": {"last_remote_status": "failed", "last_remote_run_at": iso_now()}},
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
    parser = argparse.ArgumentParser(description="Telegram bridge for the CEO Codex team")
    parser.add_argument("--once", action="store_true", help="Poll Telegram once, then exit")
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
