"""
Agent Message Poller — Surfaces CEO agent messages and approvals in the Chat Agent.

Polls system_monitor.agent_messages for pending items and:
  - Broadcasts new messages via SSE to connected clients
  - Makes messages available for router context injection
  - Handles approval responses from the chat UI

Replaces Telegram spam with in-app notifications.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger("voice-agent.agent-poller")

AEST = timezone(timedelta(hours=10))
POLL_INTERVAL = 15  # seconds
COLLECTION = "agent_messages"


class AgentPoller:
    """Polls MongoDB for agent messages and broadcasts via SSE."""

    def __init__(self, db_client, sse_broadcaster):
        self._client = db_client
        self._sse = sse_broadcaster
        self._db = db_client["system_monitor"]
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Cache of pending messages for router context injection
        self._pending_messages: list[dict] = []
        # Session cache — keeps delivered messages so router can still reference them
        # for conversational approval (e.g. Will says "approve" after viewing)
        self._session_messages: list[dict] = []

    async def start(self):
        """Start the polling loop."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        log.info("Agent poller started (every %ds)", POLL_INTERVAL)

    async def stop(self):
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("Agent poller stopped")

    def get_pending_messages(self) -> list[dict]:
        """Return cached pending messages for router context injection."""
        return list(self._pending_messages)

    def get_session_messages(self) -> list[dict]:
        """Return all session messages (pending + recently delivered) for router context.
        This ensures the router can still reference messages after they've been viewed."""
        # Merge pending + session, dedup by _id
        seen = set()
        result = []
        for m in self._pending_messages + self._session_messages:
            mid = str(m.get("_id", ""))
            if mid not in seen:
                seen.add(mid)
                result.append(m)
        return result

    def get_pending_approvals(self) -> list[dict]:
        """Return only messages that need approval."""
        return [m for m in self._pending_messages if m.get("type") == "deploy_approval"]

    async def respond_to_approval(self, message_id: str, approved: bool) -> dict:
        """Handle an approval/denial response from Will."""
        from bson import ObjectId
        try:
            oid = ObjectId(message_id)
        except Exception:
            return {"ok": False, "error": "Invalid message ID"}

        msg = self._db[COLLECTION].find_one({"_id": oid})
        if not msg:
            return {"ok": False, "error": "Message not found"}

        if msg.get("status") not in ("pending", "pending_approval", "delivered"):
            return {"ok": False, "error": f"Already handled (status: {msg.get('status')})"}

        new_status = "approved" if approved else "denied"
        self._db[COLLECTION].update_one(
            {"_id": oid},
            {"$set": {
                "status": new_status,
                "responded_at": datetime.now(AEST).isoformat(),
            }},
        )

        # Broadcast the response
        self._sse.broadcast("agent_approval_response", {
            "message_id": message_id,
            "agent": msg.get("agent", "unknown"),
            "approved": approved,
            "description": msg.get("manifest", {}).get("description", ""),
        })

        # If approved, trigger the implementation bridge
        if approved and msg.get("type") in ("deploy_approval", "mid_session_message"):
            asyncio.create_task(self._trigger_bridge(msg))

        # Refresh cache
        await self._refresh_pending()

        action = "Approved" if approved else "Denied"
        log.info("Approval %s for %s: %s", action.lower(), msg.get("agent"), message_id)
        return {"ok": True, "status": new_status}

    async def mark_delivered(self, message_id: str):
        """Mark a non-approval message as delivered (Will has seen it).
        Keeps it in session cache so router can still reference it for conversational approval."""
        from bson import ObjectId
        try:
            oid = ObjectId(message_id)
        except Exception:
            return

        # Capture the message into session cache before it leaves pending
        for m in self._pending_messages:
            if str(m.get("_id")) == message_id:
                m_copy = dict(m)
                m_copy["status"] = "delivered"
                # Avoid duplicates in session cache
                session_ids = {str(s.get("_id")) for s in self._session_messages}
                if message_id not in session_ids:
                    self._session_messages.append(m_copy)
                break

        self._db[COLLECTION].update_one(
            {"_id": oid, "status": "pending"},
            {"$set": {"status": "delivered", "delivered_at": datetime.now(AEST).isoformat()}},
        )
        await self._refresh_pending()

        # Cap session cache to last 20 messages
        if len(self._session_messages) > 20:
            self._session_messages = self._session_messages[-20:]

    async def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                await self._refresh_pending()
            except Exception as exc:
                log.error("Agent poller error: %s", exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _refresh_pending(self):
        """Fetch pending messages from DB and broadcast new ones."""
        try:
            # Sort by _id (always indexed in Cosmos DB) instead of created_at
            cursor = self._db[COLLECTION].find(
                {"status": {"$in": ["pending", "pending_approval"]}},
            ).sort("_id", 1)
            messages = list(cursor)
        except Exception as exc:
            log.error("Failed to query agent_messages: %s", exc)
            return

        # Find genuinely new messages (not in our cache)
        cached_ids = {str(m.get("_id")) for m in self._pending_messages}
        new_messages = [m for m in messages if str(m.get("_id")) not in cached_ids]

        # Broadcast new ones via SSE
        for msg in new_messages:
            event_type = "agent_approval_needed" if msg.get("type") == "deploy_approval" else "agent_message"
            self._sse.broadcast(event_type, {
                "message_id": str(msg["_id"]),
                "agent": msg.get("agent", "unknown"),
                "message": msg.get("message", ""),
                "type": msg.get("type", "info"),
                "manifest": _safe_manifest(msg.get("manifest")),
                "created_at": msg.get("created_at", ""),
            })
            log.info("Broadcast %s from %s", event_type, msg.get("agent"))

        # Update cache
        self._pending_messages = messages

    async def _trigger_bridge(self, msg: dict):
        """Trigger the implementation bridge for an approved deployment."""
        import subprocess, os
        try:
            orch_dir = "/home/fields/Fields_Orchestrator"
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            env["GH_CONFIG_DIR"] = "/home/projects/.config/gh"
            subprocess.Popen(
                ["/home/fields/venv/bin/python3", f"{orch_dir}/scripts/agent-implementation-bridge.py"],
                cwd=orch_dir, env=env,
                stdout=open(f"{orch_dir}/logs/implementation-bridge.log", "a"),
                stderr=open(f"{orch_dir}/logs/implementation-bridge.log", "a"),
            )
            log.info("Implementation bridge launched for approved deploy (%s)", msg.get("agent"))
        except Exception as exc:
            log.error("Failed to launch bridge: %s", exc)


def _safe_manifest(manifest: Optional[dict]) -> Optional[dict]:
    """Strip non-serializable fields from manifest for SSE."""
    if not manifest:
        return None
    return {k: v for k, v in manifest.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
