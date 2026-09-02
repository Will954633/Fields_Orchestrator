#!/usr/bin/env python3
"""
mce_common.py — shared plumbing for the Market Context Engine (MCE).

The MCE evolves run_research_cycle.py into a demand-sensing -> psychology -> deep-research
-> suburb-contextualisation pipeline (see ../DEV_MARKET_CONTEXT_ENGINE.md). Every stage
imports from here so the headless-claude recipe, the honesty rules, the QA vocabulary and
the cycle bookkeeping are defined exactly once.

Two invariants inherited from the proven scripts (do not weaken them):
  * Web research bills the Max subscription — we strip ANTHROPIC_API_KEY / CLAUDECODE /
    CLAUDE_CODE_SSE_PORT before invoking `claude -p` (same as run_research_cycle.py and
    refresh_homeowner_mindset.py).
  * Internal ground-truth is SUPPLIED, never recalled — the researcher LLM is handed our
    numbers with reliability flags; it must never look them up. (Stage 0 builds that pack.)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Australia/Brisbane")
except Exception:                                          # pragma: no cover
    TZ = timezone.utc

# ---------------------------------------------------------------- paths
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                               # 14_Articles/Market_Research/
ORCH = "/home/fields/Fields_Orchestrator"
for p in (ORCH, os.path.join(ORCH, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

TOPICS_DIR = os.path.join(ROOT, "topics")
BRIEFS_CUR = os.path.join(ROOT, "briefs", "current")
BRIEFS_ARCH = os.path.join(ROOT, "briefs", "archive")
SUBURB_DIR = os.path.join(ROOT, "suburb_context")
DRAFTS_DIR = os.path.join(ROOT, "drafts")
DATA_DIR = os.path.join(ROOT, "data")
CONFIG = os.path.join(ROOT, "topics.json")
INDEX_MD = os.path.join(ROOT, "INDEX.md")

# ---------------------------------------------------------------- models
# Proven on the Max CLI in run_research_cycle.py. Bare "opus" collapses to a stale tier on
# this Max account, so pin the full id (see CLAUDE.md editorial notes).
MODEL_DEEP = os.environ.get("MCE_MODEL_DEEP", "claude-opus-4-8")
MODEL_FAST = os.environ.get("MCE_MODEL_FAST", "claude-sonnet-5")

# ---------------------------------------------------------------- audience
TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
DISPLAY_NAMES = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
}

# ---------------------------------------------------------------- editorial guardrails
FORBIDDEN_WORDS = ["stunning", "nestled", "boasting", "rare opportunity", "robust market"]

HONESTY_RULES = """\
GROUND RULES (binding — this is for a data-led Australian property intelligence business):
- Reputable sources ONLY (RBA, ABS, Australian Treasury, Cotality/CoreLogic, PropTrack,
  Domain, QGSO, REIQ, Westpac-Melbourne Institute, quality press, academic, major law/
  accounting firms). EVERY claim carries a source + date + URL.
- Separate FACT from COMMENTARY/forecast. Record commentators' forecasts as commentary;
  make NO forecast of your own.
- DO NOT fabricate figures, papers, quotes or policy changes. An unverifiable claim is
  reported as unverifiable, never filled in.
- TEST the premise, don't confirm it. If a headline's implied cause is not supported by
  evidence, say so.
- This output informs public content bound by: NO advice ("now is a good time to sell"),
  NO price predictions, NO single valuation figure in a headline (use ranges), and never
  the words: stunning, nestled, boasting, rare opportunity, robust market.
"""

OUTPUT_DISCIPLINE = """\
OUTPUT DISCIPLINE (critical): You do NOT have file-write access and you are NOT updating any
file — a separate process saves your output. Do NOT attempt to edit or save anything, and do
NOT say you have saved, refreshed or updated a file. Your ENTIRE reply must be the requested
Markdown document and nothing else: no preamble, no "saved in place", no summary of changes,
no closing question or sign-off. The first character of your reply is the document's first
character.
"""

# The mandatory honesty block every synthesized brief must contain.
SECTION9_INSTRUCTION = """\
End with a section headed exactly '## What we deliberately did NOT conclude' listing every
claim that sounded right but failed verification, and anything you could not stand up. This
section is mandatory and OUTRANKS any messaging/implication section: if a suggested line
survives only by ignoring it, drop the line.
"""


# ---------------------------------------------------------------- cycle bookkeeping
def now_tz() -> datetime:
    return datetime.now(TZ)


def cycle_id(now: datetime | None = None) -> str:
    return (now or now_tz()).strftime("%Y-%m-%d")


def is_on_week(now: datetime | None = None) -> bool:
    """Fortnightly parity anchored on ISO week number (even weeks run) — same gate as
    run_research_cycle.py so the two cadences stay aligned."""
    return (now or now_tz()).isocalendar().week % 2 == 0


def cycle_data_dir(cycle: str) -> str:
    d = os.path.join(DATA_DIR, cycle)
    os.makedirs(d, exist_ok=True)
    return d


def save_artifact(cycle: str, name: str, obj) -> str:
    """Persist an intermediate stage artifact as JSON under data/<cycle>/."""
    path = os.path.join(cycle_data_dir(cycle), name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=str)
    return path


def load_artifact(cycle: str, name: str):
    path = os.path.join(cycle_data_dir(cycle), name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- db
def get_sm():
    from shared.db import get_client
    return get_client()["system_monitor"]


def get_gc():
    from shared.db import get_client
    return get_client()["Gold_Coast"]


# ---------------------------------------------------------------- headless claude (Max)
def clean_env() -> dict:
    """Strip the vars that would route `claude -p` to metered API credit instead of Max."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                        "CLAUDECODE", "CLAUDE_CODE_SSE_PORT")}
    env.setdefault("GH_CONFIG_DIR", "/home/projects/.config/gh")
    env.setdefault("CI", "true")
    return env


DEFAULT_TOOLS = "WebSearch,WebFetch,Read,Grep,Glob"


def run_claude(prompt: str, *, model: str | None = None, tools: str = DEFAULT_TOOLS,
               timeout: int = 1200, max_turns: int = 30) -> dict:
    """Invoke the Max CLI in agentic mode and return a normalized result dict:
        {"text": <result string>, "cost": <usd or None>, "turns": <int>, "raw": <parsed>}
    Raises RuntimeError on a non-zero exit or a CLI-reported error. Read-only tools only —
    the caller (parent) writes every file, so a bad model turn can never clobber output."""
    cmd = ["claude", "--model", model or MODEL_DEEP, "-p", prompt,
           "--allowedTools", tools, "--output-format", "json",
           "--max-turns", str(max_turns)]
    proc = subprocess.run(cmd, cwd=ORCH, env=clean_env(),
                          capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exited {proc.returncode}: {(proc.stderr or '')[-600:]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"non-JSON CLI output: {e}: {proc.stdout[:400]}")
    if data.get("is_error") or data.get("subtype") not in (None, "success"):
        raise RuntimeError(f"CLI error: {data.get('subtype')}: {str(data.get('result'))[:500]}")
    return {
        "text": data.get("result", ""),
        "cost": data.get("total_cost_usd"),
        "turns": data.get("num_turns"),
        "raw": data,
    }


# ---------------------------------------------------------------- parsing helpers
def extract_markdown(out: str) -> str:
    """Child should return pure markdown; tolerate a ```markdown fence."""
    m = re.search(r"```(?:markdown)?\s*(.*?)```", out, re.S)
    return (m.group(1).strip() if m else out.strip())


def extract_json(out: str):
    """Pull the last JSON object/array from a model response. Tolerates a ```json fence or
    a bare object/array; returns the parsed value or raises ValueError."""
    # Prefer a fenced json block (take the last one).
    blocks = re.findall(r"```json\s*(.*?)```", out, re.S)
    candidates = [b.strip() for b in blocks]
    if not candidates:
        # Fall back to the outermost [...] or {...} span.
        for opener, closer in (("[", "]"), ("{", "}")):
            i, j = out.find(opener), out.rfind(closer)
            if i != -1 and j > i:
                candidates.append(out[i:j + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"no parseable JSON in model output (first 300 chars): {out[:300]}")


# ---------------------------------------------------------------- QA
def qa_scan(md: str) -> list[str]:
    """Return a list of QA violation strings for a piece of synthesized content. Empty =
    clean. This is the automated Rule-5 / honesty gate from the dev doc (Stage 8)."""
    problems = []
    low = md.lower()
    for w in FORBIDDEN_WORDS:
        if w in low:
            problems.append(f"forbidden word: '{w}'")
    # A single dollar valuation stated as a fact in a heading line (crude heuristic:
    # a markdown heading containing a $ amount that is not a range).
    for line in md.splitlines():
        if line.lstrip().startswith("#") and re.search(r"\$[\d,]{4,}", line):
            if "-" not in line and "–" not in line and "to" not in line.lower():
                problems.append(f"possible single-valuation headline: {line.strip()[:80]}")
    return problems


def has_section9(md: str) -> bool:
    return bool(re.search(r"did NOT conclude", md, re.I))
