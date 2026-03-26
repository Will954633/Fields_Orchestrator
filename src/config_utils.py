#!/usr/bin/env python3
"""
Configuration utilities for Fields Orchestrator.

Extracted from task_executor.py to reduce its size and provide reusable
config-loading functions.
"""

import os
import re
import yaml
from pathlib import Path
from typing import List, Optional

from .logger import get_logger


def resolve_env_vars(value: str, logger=None) -> str:
    """Expand ${VAR_NAME} and $VAR_NAME patterns in a string.

    YAML doesn't do shell variable expansion, so this resolves environment
    variable references in values loaded from settings.yaml.
    """
    if not isinstance(value, str):
        return value

    _logger = logger or get_logger()

    def replace_var(match):
        var_name = match.group(1) or match.group(2)
        env_value = os.environ.get(var_name, "")
        if not env_value:
            _logger.warning(f"Environment variable '{var_name}' is not set")
        return env_value

    return re.sub(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)", replace_var, value)


def load_settings(base_dir: Optional[Path] = None) -> dict:
    """Load and return the parsed settings.yaml, with env vars resolved in mongodb.uri."""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent
    settings_path = base_dir / "config" / "settings.yaml"
    if not settings_path.exists():
        return {}
    with open(settings_path, "r") as f:
        settings = yaml.safe_load(f) or {}
    # Resolve env vars in the mongo URI
    raw_uri = settings.get("mongodb", {}).get("uri", "")
    if raw_uri:
        settings.setdefault("mongodb", {})["uri"] = resolve_env_vars(raw_uri)
    return settings


def get_mongo_uri(base_dir: Optional[Path] = None) -> str:
    """Return the resolved MongoDB URI from settings or environment."""
    settings = load_settings(base_dir)
    uri = settings.get("mongodb", {}).get("uri", "")
    if uri:
        return uri
    # Fallback to env vars
    return os.environ.get("COSMOS_CONNECTION_STRING", os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/"))


def get_target_suburb_slugs(base_dir: Optional[Path] = None) -> List[str]:
    """Return target suburb slugs from settings.yaml.

    e.g. ["robina", "varsity_lakes", "burleigh_waters"]
    """
    settings = load_settings(base_dir)
    suburbs_raw = settings.get("target_market", {}).get("suburbs", [])
    return [s.split(":")[0].strip().lower().replace(" ", "_") for s in suburbs_raw]
