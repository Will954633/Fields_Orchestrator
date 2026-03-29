"""
SSE (Server-Sent Events) broadcaster for the Fields Voice Agent.

Single-user system — one queue, no fan-out complexity.
Pushes task lifecycle events to connected web/app clients.
"""

import asyncio
import json
import time
import logging
from typing import AsyncGenerator

log = logging.getLogger("voice-agent.sse")


class SSEBroadcaster:
    """Manages SSE event broadcasting to connected clients."""

    def __init__(self):
        self._queues: list[asyncio.Queue] = []

    def broadcast(self, event_type: str, data: dict) -> None:
        """Push an event to all connected clients."""
        data["ts"] = time.time()
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        dead = []
        for q in self._queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._queues.remove(q)
            log.warning("Dropped slow SSE client")

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings for a single client connection."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._queues.append(q)
        log.info(f"SSE client connected ({len(self._queues)} total)")
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30)
                    yield payload
                except asyncio.TimeoutError:
                    # Keep-alive to prevent proxy/browser timeouts
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in self._queues:
                self._queues.remove(q)
            log.info(f"SSE client disconnected ({len(self._queues)} total)")
