#!/usr/bin/env python3
"""
Shared MongoDB connection factory for Fields Orchestrator.

Provides a single source of truth for:
  - URI resolution (env var → config YAML → fallback)
  - Client creation with Cosmos DB-compatible options
  - Cosmos DB 16500 (TooManyRequests) retry logic
  - Database accessor helpers

Usage in scripts:
    from src.mongo_client_factory import get_mongo_client, get_database, cosmos_retry

    client = get_mongo_client()
    db = get_database("Gold_Coast")
    coll = db["robina"]

    # For operations that may hit Cosmos RU limits:
    result = cosmos_retry(lambda: coll.find_one({"address": "..."}))

Usage as decorator:
    @cosmos_retry_decorator
    def fetch_property(coll, address):
        return coll.find_one({"address": address})
"""

import os
import re
import time
import functools
from typing import Optional, Callable, TypeVar, Any

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import OperationFailure

T = TypeVar("T")

# ---------------------------------------------------------------------------
# URI resolution
# ---------------------------------------------------------------------------

_URI_ENV_KEYS = ("COSMOS_CONNECTION_STRING", "MONGODB_URI")
_DEFAULT_CONFIG_PATH = "/home/fields/Fields_Orchestrator/config/settings.yaml"

_cached_client: Optional[MongoClient] = None


def _resolve_uri(uri: Optional[str] = None, config_path: Optional[str] = None) -> str:
    """Resolve MongoDB URI with fallback chain:
    1. Explicit parameter
    2. COSMOS_CONNECTION_STRING env var
    3. MONGODB_URI env var
    4. settings.yaml mongodb.uri (with ${VAR} expansion)
    """
    if uri:
        return uri

    for key in _URI_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            return val

    # Fall back to settings.yaml
    cfg_path = config_path or _DEFAULT_CONFIG_PATH
    if os.path.exists(cfg_path):
        try:
            import yaml
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f)
            raw_uri = cfg.get("mongodb", {}).get("uri", "")
            if raw_uri:
                # Expand ${VAR_NAME} references
                def _expand(match):
                    return os.environ.get(match.group(1), match.group(0))
                return re.sub(r"\$\{(\w+)\}", _expand, raw_uri)
        except Exception:
            pass

    raise RuntimeError(
        "No MongoDB URI found. Set COSMOS_CONNECTION_STRING or MONGODB_URI, "
        "or ensure config/settings.yaml has mongodb.uri."
    )


# ---------------------------------------------------------------------------
# Client / database accessors
# ---------------------------------------------------------------------------

def get_mongo_client(uri: Optional[str] = None, fresh: bool = False) -> MongoClient:
    """Return a cached MongoClient (singleton). Pass fresh=True to force a new connection."""
    global _cached_client
    if _cached_client is not None and not fresh:
        return _cached_client

    resolved = _resolve_uri(uri)
    client = MongoClient(
        resolved,
        retryWrites=False,          # Cosmos DB does not support retryable writes
        maxIdleTimeMS=120000,
        serverSelectionTimeoutMS=30000,
        socketTimeoutMS=60000,
        connectTimeoutMS=30000,
    )
    _cached_client = client
    return client


def get_database(name: str = "Gold_Coast", uri: Optional[str] = None) -> Database:
    """Shortcut: get_mongo_client().db(name)."""
    return get_mongo_client(uri)[name]


def close_client() -> None:
    """Close and discard the cached client."""
    global _cached_client
    if _cached_client is not None:
        _cached_client.close()
        _cached_client = None


# ---------------------------------------------------------------------------
# Cosmos DB retry helpers
# ---------------------------------------------------------------------------

def cosmos_retry(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 5,
    backoff_factor: float = 1.5,
    base_delay: float = 1.0,
    **kwargs: Any,
) -> T:
    """Execute *fn* with automatic retry on Cosmos DB 16500 (TooManyRequests).

    Parses RetryAfterMs from the error when available, otherwise uses
    exponential backoff: base_delay * backoff_factor^attempt.
    """
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except OperationFailure as exc:
            if exc.code != 16500 or attempt == max_retries:
                raise
            # Try to parse Cosmos-suggested wait time
            msg = str(exc)
            match = re.search(r"RetryAfterMs=(\d+)", msg)
            if match:
                wait = int(match.group(1)) / 1000.0 + 0.05
            else:
                wait = base_delay * (backoff_factor ** attempt)
            time.sleep(wait)
    # unreachable, but keeps mypy happy
    raise RuntimeError("cosmos_retry: exhausted retries")


def cosmos_retry_decorator(
    max_retries: int = 5,
    backoff_factor: float = 1.5,
    base_delay: float = 1.0,
):
    """Decorator form of cosmos_retry.

    Usage:
        @cosmos_retry_decorator()
        def update_doc(coll, doc_id, patch):
            coll.update_one({"_id": doc_id}, {"$set": patch})
    """
    def wrapper(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            return cosmos_retry(
                fn, *args,
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                base_delay=base_delay,
                **kwargs,
            )
        return inner
    return wrapper


# ---------------------------------------------------------------------------
# Target suburbs (single source of truth for orchestrator scripts)
# ---------------------------------------------------------------------------

TARGET_SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes",
    "burleigh_heads", "mudgeeraba", "reedy_creek",
    "merrimac", "worongary", "carrara",
]

FEATURED_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]


# ---------------------------------------------------------------------------
# Suburb normalization helpers
# ---------------------------------------------------------------------------

def normalize_suburb(name: str) -> str:
    """Normalize suburb name to DB collection key.
    "Robina" → "robina", "Varsity Lakes" → "varsity_lakes", "Burleigh-Waters" → "burleigh_waters"
    """
    import re
    return re.sub(r"[\s-]+", "_", name.strip().lower())


def suburb_display_name(key: str) -> str:
    """Convert DB key to display name: "varsity_lakes" → "Varsity Lakes"."""
    return key.replace("_", " ").title()
