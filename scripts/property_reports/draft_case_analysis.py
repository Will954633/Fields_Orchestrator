#!/usr/bin/env python3
"""
draft_case_analysis — Opus drafts the written analysis for a case study from the
VERIFIED data scaffold built by build_case_study.py.

The narrative is the one part the data can't auto-verify, so it is generated
under hard constraints: the model is given ONLY the verified exhibits we hold,
told to cite nothing it wasn't given, and the output is validated against the
editorial rules (no advice, no forecasts, no forbidden words) before it is
merged. The merged record stays published=false until a human flips it.

Sections (business-school case structure):
  setup        — the home + the market it launched into
  decision     — how it was priced / the method chosen / positioning
  what_happened — the timeline outcome, factually
  analysis     — WHY it played out that way, tied to Fields principles + research
  lesson       — what a vendor takes from it (data only, no instruction)

Usage:
  python3 -m scripts.property_reports.draft_case_analysis --case-id overpricing-1-yawl-place-varsity-lakes
  python3 -m scripts.property_reports.draft_case_analysis --case-id ... --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_client  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("draft_case_analysis")

MODEL = "claude-opus-4-8"
MAX_TOKENS = 3000
MAX_RETRIES = 3
BACKOFF = [2, 5, 12]

FORBIDDEN_WORDS = [
    "stunning", "nestled", "boasting", "rare opportunity", "robust market",
]
# Advice / forecast tells — editorial rules forbid telling the reader what to do
# or predicting prices.
ADVICE_PATTERNS = [
    r"\byou should\b", r"\byou must\b", r"\bwe recommend\b", r"\bconsider (buying|selling)\b",
    r"\bnow is a good time\b", r"\bwill (rise|fall|increase|drop|grow)\b",
    r"\bprices will\b", r"\bis going to\b", r"\bguaranteed\b",
]

SYSTEM_PROMPT = """You are writing one editorial real-estate case study for Fields Estate, a Gold Coast property-intelligence firm whose entire brand is "every claim is verifiable."

You will be given a VERIFIED data scaffold for ONE real, sold home: its facts, its sale outcome, its full Domain sale timeline, the suburb market it sold into, and (only when present) a Domain estimate-vs-reality exhibit. These are the ONLY facts you may state. You must not invent any number, date, feature, motive, or quote. If you do not have a fact, do not imply it.

Write a business-school-style case study in FIVE sections. Return STRICT JSON with exactly these string keys: "setup", "decision", "what_happened", "analysis", "lesson". No other keys, no markdown fences.

Section intent:
- setup: The home and the market it launched into. Concrete, from the scaffold.
- decision: How the home was taken to market — the price it sold at, the method, what the sale timeline shows. Frame the asking strategy ONLY from what the data supports (days on market, sale vs any contemporaneous estimate). Never claim a specific asking price or price reduction unless it is in the scaffold.
- what_happened: The factual outcome — time on market, final price, method — stated plainly.
- analysis: WHY it likely played out this way, tied to general principles (pricing to the evidence, the first-ten-days dynamic, ambiguity aversion, the asking price as a marketing tool). You may reference that these principles are documented in Fields' book "Before You List" and in the research literature, but cite NO specific study or statistic you were not given.
- lesson: What the data illustrates for a vendor — stated as a principle the reader draws their own conclusion from. NEVER tell the reader what to do.

HARD RULES (a violation means the whole draft is rejected):
- No advice: never "you should", "consider selling", "now is the time".
- No forecasts: never predict prices or say what "will" happen.
- No single-figure valuations presented as a prediction; report the actual sale figure as the historical fact it is.
- Banned words: stunning, nestled, boasting, rare opportunity, robust market.
- Money as "$1,250,000" (never "$1.25m"). Suburbs capitalised. Exact figures from the scaffold only.
- Trade-offs are framed as value, not flaws.
- Factual, calm, specific. This is a teaching document, not an advertisement.
- If the scaffold has no contemporaneous Domain estimate, do NOT discuss Domain's estimate at all.

Each section: 2–5 sentences. Total under 600 words."""


def _scaffold_for_prompt(rec: Dict[str, Any]) -> str:
    """Hand the model ONLY verified fields, clearly labelled."""
    facts = rec.get("facts") or {}
    out = rec.get("outcome") or {}
    payload = {
        "concept_being_taught": rec.get("concept"),
        "address": rec.get("address"),
        "suburb": rec.get("suburb"),
        "home": {k: v for k, v in facts.items() if v is not None},
        "sale_outcome": {k: v for k, v in out.items() if v is not None},
        "full_sale_timeline": rec.get("sale_timeline"),
        "market_when_it_sold": rec.get("market_at_listing"),
        "domain_estimate_vs_reality": rec.get("domain_vs_reality"),  # None if not contemporaneous
        "condition_read": rec.get("condition"),
        "agent_listing_copy_excerpt": (rec.get("agent_description") or "")[:600] or None,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    return (
        "Here is the verified data scaffold. State only these facts.\n\n"
        + json.dumps(payload, indent=1, default=str)
    )


def _validate(sections: Dict[str, Any]) -> Optional[str]:
    need = {"setup", "decision", "what_happened", "analysis", "lesson"}
    if set(sections.keys()) != need:
        return f"wrong keys: {sorted(sections.keys())}"
    blob = " ".join(str(sections[k]) for k in need).lower()
    for w in FORBIDDEN_WORDS:
        if w in blob:
            return f"forbidden word: {w}"
    for pat in ADVICE_PATTERNS:
        if re.search(pat, blob):
            return f"advice/forecast pattern: {pat}"
    if re.search(r"\$\d+(\.\d+)?\s*m\b", blob):
        return "shorthand money ($1.25m) — must be full format"
    for k in need:
        if not str(sections[k]).strip():
            return f"empty section: {k}"
    return None


def draft(case_id: str, dry_run: bool) -> Optional[Dict[str, Any]]:
    coll = get_client()["system_monitor"]["case_study_library"]
    rec = coll.find_one({"case_id": case_id})
    if not rec:
        log.error(f"case not found: {case_id}")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return None
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    user_prompt = _scaffold_for_prompt(rec)
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = "".join(getattr(b, "text", "") for b in resp.content
                           if getattr(b, "type", None) == "text").strip()
            text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
            sections = json.loads(text)
        except Exception as e:
            last_err = f"attempt {attempt}: {e}"
            log.warning(f"  {last_err}")
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF[min(attempt - 1, len(BACKOFF) - 1)])
            continue

        err = _validate(sections)
        if err:
            last_err = f"attempt {attempt} validation: {err}"
            log.warning(f"  {last_err}")
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF[min(attempt - 1, len(BACKOFF) - 1)])
            continue

        analysis = {
            **sections,
            "model": MODEL,
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "attempt": attempt,
        }
        log.info(f"  ✓ analysis drafted (attempt {attempt})")
        for k in ("setup", "decision", "what_happened", "analysis", "lesson"):
            log.info(f"\n— {k} —\n{sections[k]}")
        if dry_run:
            log.info("\n  DRY RUN — not saved.")
            return analysis
        coll.update_one({"case_id": case_id},
                        {"$set": {"analysis": analysis, "published": False}})
        log.info(f"\n  ✓ saved analysis to {case_id} (published=False — review then flip)")
        return analysis

    log.error(f"  all attempts failed: {last_err}")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return 0 if draft(args.case_id, args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
