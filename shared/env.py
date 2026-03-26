#!/usr/bin/env python3
"""
Unified environment loading for all Fields Orchestrator scripts.

Usage:
    from shared.env import load_env
    load_env()  # loads .env, activates all vars
"""

from __future__ import annotations

import os
import sys

_loaded = False

ENV_PATH = "/home/fields/Fields_Orchestrator/.env"


def load_env(env_path: str | None = None) -> None:
    """Load environment variables from the .env file.

    Idempotent — safe to call multiple times; only the first call has
    side-effects.  Prints a warning to stderr if COSMOS_CONNECTION_STRING
    is still missing after loading.
    """
    global _loaded
    if _loaded:
        return

    path = env_path or ENV_PATH

    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
    except ImportError:
        # Fallback: parse the file manually (key=value, skip comments/blanks)
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = value

    _loaded = True

    if not os.environ.get("COSMOS_CONNECTION_STRING"):
        print(
            "WARNING: COSMOS_CONNECTION_STRING not found after loading env",
            file=sys.stderr,
        )
