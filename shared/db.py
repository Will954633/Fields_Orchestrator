#!/usr/bin/env python3
"""
Shared MongoDB connection for all Fields Orchestrator scripts.

Provides a singleton MongoClient with Cosmos DB-compatible settings,
database accessor helpers, and re-exports of retry utilities.

Usage:
    from shared.db import get_client, get_db, cosmos_retry

    client = get_client()
    db = get_db("Gold_Coast")
    result = cosmos_retry(lambda: db["robina"].find_one({"listing_status": "for_sale"}), "find_robina")
"""

from __future__ import annotations

import os
import re
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database

# Re-export retry utilities from ru_guard for convenience
from shared.ru_guard import (  # noqa: F401
    cosmos_retry,
    EmptyWorkSetError,
    sleep_with_jitter,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes",
    "burleigh_heads", "mudgeeraba", "reedy_creek",
    "merrimac", "worongary", "carrara",
]

FEATURED_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]

_URI_ENV_KEYS = ("COSMOS_CONNECTION_STRING", "MONGODB_URI")
_DEFAULT_CONFIG_PATH = "/home/fields/Fields_Orchestrator/config/settings.yaml"

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_cached_client: Optional[MongoClient] = None


def _resolve_uri(uri: Optional[str] = None) -> str:
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
    if os.path.exists(_DEFAULT_CONFIG_PATH):
        try:
            import yaml
            with open(_DEFAULT_CONFIG_PATH) as f:
                cfg = yaml.safe_load(f)
            raw_uri = cfg.get("mongodb", {}).get("uri", "")
            if raw_uri:
                def _expand(match):
                    return os.environ.get(match.group(1), match.group(0))
                return re.sub(r"\$\{(\w+)\}", _expand, raw_uri)
        except Exception:
            pass

    raise RuntimeError(
        "No MongoDB URI found. Set COSMOS_CONNECTION_STRING or MONGODB_URI, "
        "or ensure config/settings.yaml has mongodb.uri."
    )


def get_client(uri: Optional[str] = None, fresh: bool = False) -> MongoClient:
    """Return a cached MongoClient (singleton).

    Pass *fresh=True* to force a new connection (closes the old one first).
    """
    global _cached_client
    if _cached_client is not None and not fresh:
        return _cached_client

    resolved = _resolve_uri(uri)
    client = MongoClient(
        resolved,
        retryWrites=False,              # Cosmos DB does not support retryable writes
        maxIdleTimeMS=120000,
        serverSelectionTimeoutMS=30000,
        socketTimeoutMS=60000,
        connectTimeoutMS=30000,
    )
    _cached_client = client
    return client


def get_db(name: str = "Gold_Coast", uri: Optional[str] = None) -> Database:
    """Shortcut: ``get_client()[name]``."""
    return get_client(uri)[name]


def get_gold_coast_db(uri: Optional[str] = None) -> Database:
    """Shortcut for the main Gold_Coast database."""
    return get_db("Gold_Coast", uri)


def close_client() -> None:
    """Close and discard the cached client."""
    global _cached_client
    if _cached_client is not None:
        _cached_client.close()
        _cached_client = None


# ---------------------------------------------------------------------------
# Suburb normalization helpers (forwarded from mongo_client_factory)
# ---------------------------------------------------------------------------

def normalize_suburb(name: str) -> str:
    """Normalize suburb name to DB collection key.
    "Robina" -> "robina", "Varsity Lakes" -> "varsity_lakes"
    """
    return re.sub(r"[\s-]+", "_", name.strip().lower())


def suburb_display_name(key: str) -> str:
    """Convert DB key to display name: "varsity_lakes" -> "Varsity Lakes"."""
    return key.replace("_", " ").title()
