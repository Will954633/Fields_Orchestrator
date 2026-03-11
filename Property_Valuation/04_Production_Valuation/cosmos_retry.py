"""
Cosmos DB Retry Utility
========================

Provides a retry wrapper for pymongo operations that handles Cosmos DB
429 (Request Rate Too Large) errors by parsing RetryAfterMs from the
error message and sleeping before retrying.

Error code 16500 is Cosmos DB's equivalent of HTTP 429.

Author: Fields Estate Operations
Date: 11 March 2026
"""

import re
import time
import logging
import functools
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
DEFAULT_RETRY_MS = 1000  # 1 second fallback if RetryAfterMs not found


def _parse_retry_after_ms(error_message: str) -> int:
    """Extract RetryAfterMs value from Cosmos DB error message.

    Cosmos DB 429 errors include a header like:
        RetryAfterMs=34
    in the error details string.
    """
    match = re.search(r'RetryAfterMs[=:]?\s*(\d+)', str(error_message))
    if match:
        return int(match.group(1))
    return DEFAULT_RETRY_MS


def cosmos_retry(func):
    """Decorator that retries a function on Cosmos DB 429 (code 16500) errors.

    - Parses RetryAfterMs from the error message
    - Sleeps for RetryAfterMs milliseconds (or 1 second if not found)
    - Retries up to 5 times with exponential backoff (RetryAfterMs * 1.5 each retry)
    - Logs each retry attempt
    - Re-raises after max retries

    Usage:
        @cosmos_retry
        def my_db_operation():
            return collection.find_one(query)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except OperationFailure as e:
                if e.code == 16500:
                    last_exception = e
                    if attempt >= MAX_RETRIES:
                        logger.error(
                            f"Cosmos DB 429: max retries ({MAX_RETRIES}) exceeded "
                            f"for {func.__name__}. Giving up."
                        )
                        raise

                    retry_ms = _parse_retry_after_ms(str(e))
                    # Exponential backoff: multiply by 1.5 for each subsequent attempt
                    backoff_ms = retry_ms * (1.5 ** attempt)
                    sleep_seconds = backoff_ms / 1000.0

                    logger.warning(
                        f"Cosmos DB 429 (attempt {attempt + 1}/{MAX_RETRIES}): "
                        f"{func.__name__} — RetryAfterMs={retry_ms}, "
                        f"sleeping {sleep_seconds:.1f}s"
                    )
                    time.sleep(sleep_seconds)
                else:
                    # Not a 429 error — re-raise immediately
                    raise
        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
    return wrapper


def cosmos_retry_call(func, *args, **kwargs):
    """Functional form of cosmos_retry for wrapping arbitrary callables.

    Usage:
        result = cosmos_retry_call(collection.find_one, {"_id": some_id})
        results = list(cosmos_retry_call(collection.find, query))
    """
    @cosmos_retry
    def _inner():
        return func(*args, **kwargs)
    return _inner()
