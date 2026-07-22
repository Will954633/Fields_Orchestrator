"""
Shared Claude client resolution for the property_reports narrative scripts
(market_narrative, case_study_dynamic, buyers_narrative, generate_sale_narrative,
personas_narrative, positioning_narrative, scarcity_narrative, draft_case_analysis).

These scripts previously each built a raw `anthropic.Anthropic(api_key=...)`
client directly against the pay-as-you-go Anthropic API — which fails whenever
that account runs out of credit (as happened 2026-07-20), even though the VM
also has two working alternative backends (scripts/backend_enrichment/
claude_max_client.py, used by the property-editorial pipeline):

  - Claude Max subscription, via the `claude -p` CLI shim (USE_CLAUDE_MAX=1).
    No Anthropic API credit and no Vertex quota needed — already proven
    elsewhere (article generation, migrated 2026-07-15). This is the PREFERRED
    fix for these text-only narrative scripts: model names are mapped to a CLI
    alias (opus/haiku/sonnet) by substring match, so a script's original Opus
    model still resolves to the "opus" CLI alias — no per-script model change,
    no quality-tier downgrade.
  - Google Vertex (ANTHROPIC_BACKEND=vertex), bills to GCP. Only Claude Sonnet 5
    is provisioned in Vertex Model Garden there (Sonnet-5 quota approval was
    still PENDING as of 2026-07-20 — calls may 429 until approved), so the
    model is forced to EDITORIAL_MODEL (default "claude-sonnet-5") on this path.

get_client_and_model() resolves whichever is configured. Precedence: Vertex env
wins if set, else Max if USE_CLAUDE_MAX=1, else the direct Anthropic API (needs
a working ANTHROPIC_API_KEY). Vision/image content (floor_plan_debrand.py,
inline_floor_plan.py) is NOT handled here — the Max CLI shim can't carry image
content, so those two stay on direct Anthropic/Vertex only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

_BACKEND_ENRICHMENT_DIR = str(Path(__file__).resolve().parent.parent / "backend_enrichment")
if _BACKEND_ENRICHMENT_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_ENRICHMENT_DIR)


def _use_max() -> bool:
    return os.environ.get("USE_CLAUDE_MAX", "").strip().lower() in {"1", "true", "yes", "on"}


def get_client_and_model(default_model: str) -> Tuple[Optional[object], Optional[str]]:
    """
    Returns (client, model) ready for `client.messages.create(model=model, ...)`,
    or (None, None) if no backend is usable (mirrors the scripts' previous
    "ANTHROPIC_API_KEY not set — skipping" behaviour).
    """
    backend = os.environ.get("ANTHROPIC_BACKEND", "").strip().lower()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # Nothing at all configured — same "skip" behaviour the scripts had before.
    if backend != "vertex" and not _use_max() and not api_key:
        return None, None

    try:
        from claude_max_client import make_client
    except Exception:
        if not api_key:
            return None, None
        from anthropic import Anthropic
        return Anthropic(api_key=api_key), default_model

    client = make_client(api_key=api_key)
    # Model resolution:
    #   - EDITORIAL_MODEL (if set) wins on EVERY backend — lets the mini-site
    #     build run on claude-sonnet-5 (Max maps it to the "sonnet" alias).
    #   - else Vertex forces sonnet-5 (only model provisioned there); Max/direct
    #     honour the calling script's own tier (default_model). Unset EDITORIAL_MODEL
    #     => byte-identical to the previous behaviour.
    model = os.environ.get("EDITORIAL_MODEL") or (default_model if backend != "vertex" else "claude-sonnet-5")
    return client, model
