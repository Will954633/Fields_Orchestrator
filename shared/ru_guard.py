#!/usr/bin/env python3
"""
ru_guard.py
-----------
Shared helpers for handling Azure Cosmos DB throttling (HTTP 429 / code 16500)
across orchestrator steps.

Features:
    • `cosmos_retry` — wraps any callable and automatically retries when Cosmos
      returns a throttling error. Uses exponential backoff with jitter.
    • `circuit_breaker` — tracks consecutive failures and enforces cooldowns
      when the RU budget is genuinely exhausted.
    • `EmptyWorkSetError` — raised when a step fetches zero documents even
      though work was expected.
    • `sleep_with_jitter` — utility for applying delays between operations.
"""

from __future__ import annotations

import random
import re
import time
from typing import Callable, Optional, TypeVar

from pymongo.errors import OperationFailure, WriteError

T = TypeVar("T")

THROTTLE_CODES = {16500}
RETRY_AFTER_PATTERN = re.compile(r"RetryAfterMs[\":]?\s*(\d+)", re.IGNORECASE)


class EmptyWorkSetError(RuntimeError):
    """Raised when a pipeline step retrieves zero documents unexpectedly."""


# ---------------------------------------------------------------------------
# Circuit breaker — tracks consecutive 429s across calls
# ---------------------------------------------------------------------------

class _CircuitBreaker:
    """
    Tracks consecutive throttle events. When too many happen in a row,
    enforces a longer cooldown to let RU budget recover.
    """
    def __init__(self):
        self.consecutive_failures = 0
        self.last_throttle_time = 0.0
        self.total_throttles = 0

    def record_throttle(self):
        self.consecutive_failures += 1
        self.total_throttles += 1
        self.last_throttle_time = time.time()

    def record_success(self):
        self.consecutive_failures = 0

    def get_cooldown(self) -> float:
        """Return extra cooldown seconds based on consecutive failures."""
        if self.consecutive_failures >= 5:
            # Severe: 30s cooldown
            return 30.0
        elif self.consecutive_failures >= 3:
            # Moderate: 10s cooldown
            return 10.0
        elif self.consecutive_failures >= 2:
            # Light: 3s cooldown
            return 3.0
        return 0.0


# Global circuit breaker instance — shared across all cosmos_retry calls
_breaker = _CircuitBreaker()


def get_throttle_stats() -> dict:
    """Return current throttle statistics for monitoring."""
    return {
        "consecutive_failures": _breaker.consecutive_failures,
        "total_throttles": _breaker.total_throttles,
        "last_throttle_time": _breaker.last_throttle_time,
    }


# ---------------------------------------------------------------------------
# Core retry logic
# ---------------------------------------------------------------------------

def _extract_retry_after_ms(exc: Exception, default_ms: int = 500) -> int:
    """Parse RetryAfterMs from the exception details or fallback to default."""
    details = ""
    if hasattr(exc, "details") and exc.details:
        details = str(exc.details)
    else:
        details = str(exc)

    match = RETRY_AFTER_PATTERN.search(details)
    if match:
        try:
            return max(int(match.group(1)), 50)
        except (TypeError, ValueError):
            return default_ms
    return default_ms


def _is_throttled(exc: Exception) -> bool:
    """Return True if the exception represents a Cosmos throttling event."""
    code = getattr(exc, "code", None)
    message = str(exc).lower()
    return bool(
        (code in THROTTLE_CODES)
        or "toomanyrequests" in message
        or "code 16500" in message
        or "requestratetoolarge" in message
        or ("429" in message and "cosmos" in message.lower())
    )


def cosmos_retry(
    operation: Callable[[], T],
    label: str,
    *,
    max_attempts: int = 7,
    base_sleep: float = 0.5,
    max_sleep: float = 30.0,
    backoff_factor: float = 2.0,
    log: Optional[Callable[[str], None]] = None,
) -> T:
    """
    Execute `operation` with automatic retries when Cosmos throttles.

    Uses exponential backoff with jitter + circuit breaker for sustained throttling.

    Args:
        operation: Callable with no arguments that performs the MongoDB action.
        label:     Identifier used in log messages.
        max_attempts: Maximum attempts before surfacing the exception (default 7).
        base_sleep:  Minimum seconds to wait before first retry (default 0.5s).
        max_sleep:   Maximum seconds to wait before retrying (default 30s).
        backoff_factor: Multiplier for each successive retry (default 2.0x).
        log:         Optional logger callable (e.g. print or logger.warning).
    """
    # Check circuit breaker — if we've been hammered recently, pre-wait
    breaker_cooldown = _breaker.get_cooldown()
    if breaker_cooldown > 0:
        if log:
            log(f"[ru_guard] {label} — circuit breaker: {breaker_cooldown:.0f}s cooldown ({_breaker.consecutive_failures} consecutive 429s)")
        time.sleep(breaker_cooldown)

    attempt = 0
    while True:
        try:
            result = operation()
            _breaker.record_success()
            return result
        except (OperationFailure, WriteError) as exc:
            attempt += 1
            throttled = _is_throttled(exc)
            if (not throttled) or attempt >= max_attempts:
                raise

            _breaker.record_throttle()

            # Exponential backoff: base * factor^attempt + jitter
            retry_ms = _extract_retry_after_ms(exc)
            retry_hint = retry_ms / 1000.0

            # Use the larger of: retry hint or exponential backoff
            exp_sleep = base_sleep * (backoff_factor ** (attempt - 1))
            sleep_seconds = min(max(retry_hint + 0.1, exp_sleep), max_sleep)

            # Add jitter (±20%) to prevent thundering herd
            jitter = sleep_seconds * 0.2 * random.uniform(-1, 1)
            sleep_seconds = max(0.5, sleep_seconds + jitter)

            # Add circuit breaker cooldown on top
            cb_extra = _breaker.get_cooldown()
            if cb_extra > 0:
                sleep_seconds += cb_extra

            if log:
                log(
                    f"[ru_guard] {label} throttled ({attempt}/{max_attempts}); "
                    f"RetryAfterMs={retry_ms}, sleeping {sleep_seconds:.1f}s "
                    f"(breaker: {_breaker.consecutive_failures} consecutive)"
                )
            else:
                # Always print throttle warnings so they're visible in logs
                print(
                    f"  ⚠️  {label} throttled ({attempt}/{max_attempts}), "
                    f"waiting {sleep_seconds:.1f}s"
                )

            time.sleep(sleep_seconds)


def sleep_with_jitter(base_delay: float = 0.3, jitter: float = 0.05) -> None:
    """
    Sleep for the mandated RU cooldown between Cosmos operations.

    Adds a small jitter so multiple parallel workers do not align perfectly.
    """
    delta = random.uniform(-jitter, jitter)
    time.sleep(max(0.0, base_delay + delta))
