#!/usr/bin/env python3
"""
generate_sale_narrative.py — the "Evidence → Meaning → Sale decision" layer.

The mini-site proves we hold deep data on a home, but the data alone doesn't
tell the seller the COMMERCIAL CONSEQUENCE. This generator writes the missing
interpretive layer, per-property, from the report's own already-resolved data:

  • section_implications — a short "What this means for the sale" close for each
    evidence section (aerial, street, floor plan, photos). [feedback item #4]
  • lead_buyer — the single buyer group most likely to carry the price, named
    with the reason, for the opening decision panel. [feedback item #9]
  • thesis — one sentence stating what kind of sale this is. [feedback item #10]

It does NOT invent facts: the model is given the resolved inputs (inventory,
the vision narratives, positioning personas, scarcity, competition) and asked to
INTERPRET them. Editorial rules (no advice, value framing, no forbidden words,
no fabricated figures) are enforced in the system prompt + validation.

Writes `sale_narrative` (+ `slot_status.sale_narrative = "pending"`) to the
report doc in system_monitor.property_reports. The frontend renders it as a
draft pending Will's sign-off.

Usage:
    python3 -m scripts.property_reports.generate_sale_narrative --slug <slug> [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("generate_sale_narrative")

MODEL = "claude-opus-4-7"
MAX_TOKENS = 2000
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 5, 10]

SYSTEM_PROMPT = """You are a property strategist writing the interpretive layer of a private seller's appraisal mini-site for Fields Real Estate (Gold Coast, Australia). The seller already sees their property data — photos, floor plan, aerial and street imagery, comparable homes. Your job is to tell them what that data MEANS for selling their home: not "here is the data" but "here is why it matters and how it shapes the sale".

You write for the homeowner. "Your home", "the campaign", "buyers" are the right register. This is private (not a public listing), so speaking plainly about selling their property is correct.

HARD EDITORIAL RULES (a violation fails the output):
- No advice. Never tell the reader what to DO ("you should", "consider", "now is a good time"). State what the evidence implies; let them draw conclusions.
- No predictions. No "prices will rise/fall". Use conditional, evidence-anchored language.
- Trade-offs are value, never flaws. Frame every limitation as a positioning fact, anchored to the buyer who values this home.
- No fabricated numbers. Use ONLY figures present in the inputs. Prefer qualitative interpretation over citing a specific square-metre or dollar figure (floor-area definitions are still being reconciled — do not state a specific internal-area number).
- Forbidden words: stunning, nestled, boasting, rare opportunity, robust market.
- Be specific to THIS home and its data. No generic real-estate filler. Every sentence must be defensible from the inputs.

OUTPUT: return ONLY valid JSON, no markdown fence, in exactly this shape:
{
  "section_implications": {
    "aerial":     "1-2 sentences: what the block's position/surrounds/aspect mean for the sale.",
    "street":     "1-2 sentences: what the kerb impression means for how the campaign should lead.",
    "floor_plan": "1-2 sentences: what the layout means for which buyer it suits and how it lives.",
    "photos":     "1-2 sentences: what the interior/condition evidence means for presentation and buyer confidence."
  },
  "lead_buyer": {
    "headline": "<=8 words naming the buyer group that most likely carries the price, e.g. 'Family buyers carry the price'",
    "body": "1-2 sentences: the features that point to this buyer, framed as why they compete hardest for this home."
  },
  "thesis": "One sentence stating what kind of sale this is (the positioning spine), e.g. what the home leads on and what it does not pretend to be."
}

Each section_implications value MUST open with the meaning, not a restatement of the data. If an input section is missing, still write a defensible implication from the rest of the home's profile."""


# --------------------------------------------------------------------------- #
# Input assembly
# --------------------------------------------------------------------------- #
def _g(d: Optional[Dict[str, Any]], *path, default=None):
    cur = d or {}
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default


def _format_inputs(doc: Dict[str, Any]) -> str:
    prop = doc.get("property") or {}
    addr = _g(doc, "address", "line1") or _g(doc, "address") or doc.get("slug", "this home")
    suburb = doc.get("suburb") or _g(doc, "address", "suburb") or ""

    sat = (prop.get("satellite") or {}).get("narrative") or {}
    sv = (prop.get("street_view") or prop.get("streetView") or {}).get("narrative") or {}
    fp = (prop.get("floor_plan") or {}).get("layout") or {}
    photo = prop.get("photo_analysis") or {}
    positioning = doc.get("positioning") or {}
    scarcity = doc.get("scarcity") or {}
    market = doc.get("market") or {}
    pois = doc.get("pois") or []

    # Competition count
    comp = _g(doc, "slots", "competitor_map") or {}
    competitors = comp.get("competitors") or []
    n_true = sum(1 for c in competitors if c.get("combinatorialMatch"))
    n_total = market.get("activeSouthernGcListings") or comp.get("active_in_band")

    personas = positioning.get("personas") or []
    persona_lines = []
    for p in personas[:3]:
        why = p.get("whyThisHome") or []
        persona_lines.append(f"- {p.get('label','?')}: {'; '.join(why[:2]) if why else ''}")

    trade_offs = positioning.get("tradeOffs") or []
    to_lines = [f"- apparent: {t.get('apparent','')} -> reframe: {t.get('reframe','')}" for t in trade_offs[:4]]

    poi_lines = [f"- {p.get('name','?')} ({p.get('category','')}): {p.get('walkMetres','?')} m walk" for p in pois[:6]]

    parts = [
        f"PROPERTY: {addr}, {suburb}",
        f"Bed/Bath/Car: {prop.get('bed','?')}/{prop.get('bath','?')}/{prop.get('car','?')}",
        f"Land: {prop.get('land_area_sqm','?')} m²; property type: {prop.get('property_type','?')}; year built: {prop.get('year_built','?')}",
        f"Condition (overall/kitchen): {_g(prop,'condition','overall','?')}/{_g(prop,'condition','kitchen','?')}; orientation: {prop.get('orientation','?')}",
        "",
        "AERIAL (satellite) narrative:",
        f"  overall setting: {sat.get('overall_setting','(none)')}",
        f"  surrounding land use: {sat.get('surrounding_land_use','(none)')}",
        f"  buyer highlights: {', '.join(sat.get('buyer_highlights',[])[:5]) or '(none)'}",
        "",
        "STREET VIEW narrative:",
        f"  kerb summary: {sv.get('kerb_summary','(none)')}",
        f"  buyer appeal: {', '.join(sv.get('buyer_appeal',[])[:4]) or '(none)'}",
        f"  visible trade-offs: {', '.join(sv.get('visible_trade_offs',[])[:3]) or '(none)'}",
        "",
        "FLOOR PLAN layout:",
        f"  levels: {fp.get('number_of_levels','?')}; rooms read: {len(fp.get('rooms',[]))}",
        f"  room labels: {', '.join(r.get('label','') for r in (fp.get('rooms') or [])[:10]) or '(none)'}",
        "",
        "PHOTO analysis:",
        f"  standout: {', '.join(photo.get('standout',[])[:5]) or '(none)'}",
        f"  noted: {', '.join(photo.get('noted',[])[:4]) or '(none)'}",
        f"  image quality: {_g(photo,'metadata','image_quality','?')}; professional photography: {_g(photo,'metadata','has_professional_photography','?')}",
        "",
        "POSITIONING:",
        f"  frame angle: {_g(positioning,'frame','angle','(none)')}",
        f"  sample paragraph: {positioning.get('sampleParagraph','(none)')}",
        "  personas (most likely buyers, in priority order):",
        *(persona_lines or ["  (none)"]),
        "  trade-offs (already reframed as value):",
        *(to_lines or ["  (none)"]),
        "",
        "SCARCITY / COMPETITION:",
        f"  scarcity headline: {scarcity.get('headline','(none)')}",
        f"  true competitors: {n_true} of {n_total if n_total is not None else '?'} active listings",
        "",
        "WALKING DISTANCE (proximity):",
        *(poi_lines or ["  (none)"]),
    ]
    return "\n".join(str(p) for p in parts)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
FORBIDDEN = ("stunning", "nestled", "boasting", "rare opportunity", "robust market")
ADVICE_FLAGS = ("you should", "we recommend you", "now is a good time", "you ought to")


def _validate_output(parsed: Dict[str, Any]) -> Optional[str]:
    if not isinstance(parsed, dict):
        return "not a dict"
    si = parsed.get("section_implications")
    if not isinstance(si, dict):
        return "section_implications missing"
    for k in ("aerial", "street", "floor_plan", "photos"):
        if not isinstance(si.get(k), str) or len(si.get(k, "").strip()) < 15:
            return f"section_implications.{k} missing/too short"
    lb = parsed.get("lead_buyer")
    if not isinstance(lb, dict) or not lb.get("headline") or not lb.get("body"):
        return "lead_buyer missing headline/body"
    if not isinstance(parsed.get("thesis"), str) or len(parsed["thesis"].strip()) < 15:
        return "thesis missing/too short"
    blob = json.dumps(parsed).lower()
    for w in FORBIDDEN:
        if w in blob:
            return f"forbidden word: {w}"
    for w in ADVICE_FLAGS:
        if w in blob:
            return f"advice phrasing: {w}"
    return None


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def generate_sale_narrative(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping")
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic not installed — skipping")
        return None

    client = Anthropic(api_key=api_key)
    user_prompt = _format_inputs(doc)

    last_error: Optional[str] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as e:
            last_error = f"API error attempt {attempt}: {e}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        try:
            raw = "".join(
                getattr(b, "text", "") for b in response.content
                if getattr(b, "type", None) == "text"
            ).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                if raw.startswith("json\n"):
                    raw = raw[5:].strip()
            parsed = json.loads(raw)
        except (json.JSONDecodeError, KeyError, AttributeError, IndexError) as e:
            last_error = f"parse error attempt {attempt}: {e}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        verr = _validate_output(parsed)
        if verr:
            last_error = f"validation failed attempt {attempt}: {verr}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        return {
            "section_implications": parsed["section_implications"],
            "lead_buyer": parsed["lead_buyer"],
            "thesis": parsed["thesis"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "attempt": attempt,
        }

    logger.error(f"all {MAX_RETRIES} attempts failed — last_error={last_error}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--force", action="store_true", help="Regenerate even if sale_narrative already present")
    parser.add_argument("--dry-run", action="store_true", help="Generate and print, do not write")
    args = parser.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from shared.db import get_client
    client = get_client()
    db = client["system_monitor"]
    coll = db["property_reports"]

    doc = coll.find_one({"slug": args.slug})
    if not doc:
        logger.error(f"no report doc for slug {args.slug}")
        return 1
    if doc.get("sale_narrative") and not args.force and not args.dry_run:
        logger.info("sale_narrative already present — use --force to regenerate")
        return 0

    result = generate_sale_narrative(doc)
    if not result:
        logger.error("generation failed")
        return 2

    print(json.dumps(result, indent=2))
    if args.dry_run:
        logger.info("[DRY] not writing")
        return 0

    coll.update_one(
        {"slug": args.slug},
        {"$set": {"sale_narrative": result, "slot_status.sale_narrative": "pending"}},
    )
    logger.info(f"wrote sale_narrative for {args.slug} (slot_status.sale_narrative=pending)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
