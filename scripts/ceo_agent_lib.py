#!/home/fields/venv/bin/python3
"""
Shared helpers for the CEO-agent management scripts.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pymongo import MongoClient


ROOT = Path("/home/fields/Fields_Orchestrator")
ENV_PATH = ROOT / ".env"
FOUNDER_TRUTHS_PATH = ROOT / "config" / "ceo_founder_truths.yaml"
AEST = ZoneInfo("Australia/Brisbane")


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_client() -> MongoClient:
    load_env_file()
    return MongoClient(
        require_env("COSMOS_CONNECTION_STRING"),
        retryWrites=False,
        serverSelectionTimeoutMS=30000,
    )


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def dumps_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), indent=2, sort_keys=True, default=str)


def load_founder_truths() -> dict[str, Any]:
    if not FOUNDER_TRUTHS_PATH.exists():
        return {}
    return yaml.safe_load(FOUNDER_TRUTHS_PATH.read_text(encoding="utf-8")) or {}


def now_aest() -> datetime:
    return datetime.now(AEST)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"

