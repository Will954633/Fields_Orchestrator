#!/usr/bin/env python3
"""generate_unit_property_editorial.py — Stage B PROOF (2026-09-15).

A UNIT-native variant of the on-market /property editorial (`ai_analysis`).
It reuses the SAME output schema the frontend already renders
(PropertyVerdictSection + PropertyInsightCard + PropertyFAQV2), but feeds it
from the attached-dwelling stack (unit_valuation / unit_content /
unit_market_series / complexes) and a UNIT buyer persona + voice — not the
house pipeline's land/backyard/subdivision framing.

⚠ PROOF SCOPE: writes a draft to a file for review. It does NOT write to Mongo
and does NOT publish. Model is Opus 4.8 on the Claude Max subscription, same as
the house editorial. Two LLM passes: draft -> self-fact-check-and-correct.

Usage:
    python3 generate_unit_property_editorial.py --address "49/8 Woody Views Way, Robina"
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # .../15_Off-Market/Units/scripts -> Fields_Orchestrator
for p in (str(ROOT), str(ROOT / "scripts"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.env import load_env
load_env()
# Route the editorial through Claude Max Opus 4.8 (same as the house pipeline).
os.environ["USE_CLAUDE_MAX"] = "1"
os.environ.pop("ANTHROPIC_BACKEND", None)

import unit_page_data as upd
from shared.db import get_gold_coast_db
sys.path.insert(0, str(ROOT / "scripts" / "backend_enrichment"))
from claude_max_client import make_client

MODEL = "claude-opus-4-8"


def money(n):
    try:
        return f"${int(round(float(n))):,}"
    except Exception:
        return str(n)


def build_fact_sheet(data, listing, content):
    v = data.get("valuation") or {}
    cx = data.get("complex") or {}
    mkt = data.get("market") or {}
    prox = data.get("proximity") or {}
    lines = []
    A = lines.append
    A(f"ADDRESS: {data['address']}")
    A(f"DWELLING TYPE: {listing.get('property_type','attached dwelling')} "
      f"({data.get('bedrooms')} bed / {data.get('bathrooms')} bath / {data.get('car_spaces')} car)")
    fa = data.get("floor_area")
    if fa and str(fa) != "None":
        A(f"INTERNAL FLOOR AREA: {fa} m² (measured)")
    A("")
    A("== ON-MARKET LISTING (facts that must not be contradicted) ==")
    A(f"Price guide as advertised: {listing.get('price')}")
    A(f"First listed: {listing.get('first_listed_full')} (use this DATE, never a day count)")
    A(f"Marketing agent: {listing.get('agent_name')} — {listing.get('agency')}")
    A("")
    A("== THE COMPLEX ==")
    A(f"Scheme: {cx.get('complex_name')} · community titles scheme {cx.get('cms_number')} · plan {cx.get('plan')}")
    A(f"Scheme size: {data.get('scheme_size')} dwellings; buildings are {cx.get('storeys_band')} (~{cx.get('building_height_m')} m)")
    A(f"Lift: {cx.get('lift_inferred')} ({cx.get('lift_basis')})")
    if content:
        A(f"Homes of THIS size ({content.get('bedrooms')}-bed) in the scheme: {content.get('same_size_in_scheme')} "
          f"of {content.get('scheme_homes')}  <-- NOTE: this size is the DOMINANT type here, NOT rare")
        A(f"Bedroom mix in scheme: {content.get('bed_mix')}")
        A(f"Turnover: ~{content.get('turnover_pct_per_year')}%/yr — {content.get('sales_recent')} sales in the last "
          f"{content.get('sales_window_years')} years (range {money(content.get('recent_low'))}–{money(content.get('recent_high'))})")
    A("")
    A("== VALUATION (same-complex comparable SALES method — NOT the house method) ==")
    if v.get("method") == "same_complex_comparables" and v.get("publishable"):
        A(f"Evidence range: {money(v['low'])} – {money(v['high'])} (centred ~{money(v['point'])}, but the WIDTH is the honest part)")
        A(f"Built from {v['n_comps']} same-scheme, same-bedroom sales ({v['n_available']} available), each index-adjusted to today.")
        acc = v.get("accuracy") or {}
        A(f"Band ±{v['band_pct']}% is the MEASURED P80 error of this method on {acc.get('n')} Robina attached sales "
          f"(median error {acc.get('median')}%, within 10% on {acc.get('within10')}%). It is an EMPIRICAL coverage band, "
          f"NOT a confidence interval — never call it a confidence range.")
        A("The comparable sales it is built from:")
        for c in (v.get("comparables") or [])[:12]:
            A(f"  - {c['address']} · sold {c['date']} for {money(c['sold'])} -> adjusted to today {money(c['adjusted'])} ({c['beds']} bed)")
    else:
        A("NO PUBLISHABLE FIGURE — decline. Do not state a valuation.")
    A("")
    A("== THE ATTACHED MARKET (units/townhouses, NOT houses) ==")
    A(f"Robina attached-dwelling median: {money(mkt.get('latest_rolling_median'))} ({mkt.get('latest_period')}, 12-mo rolling), "
      f"{mkt.get('yoy_pct')}% YoY. Median days on market {mkt.get('median_days_on_market')} (n={mkt.get('dom_sample')}). "
      f"{mkt.get('active_listings')} attached homes for sale now.")
    A("(This median mixes bedroom sizes and moves with the mix — context, not a second estimate of this home.)")
    A("")
    A("== AT THE DOORSTEP (walkable) ==")
    for key, lab in [("primary_school", "School"), ("childcare", "Childcare"),
                     ("supermarket", "Supermarket"), ("park", "Park"), ("beach", "Beach")]:
        p = prox.get(key)
        if p and p.get("name"):
            A(f"  - {lab}: {p['name']} — {p.get('distance_m')} m")
    return "\n".join(lines)


UNIT_SYSTEM = """You are writing the editorial for a Fields Estate on-market property page for an ATTACHED dwelling (unit / townhouse / apartment / villa / duplex). Fields is a buyer-first property-intelligence company on the Gold Coast; tagline "Smarter with data". Your reader is a prospective BUYER weighing this specific home.

THE UNIT BUYER — write to them, NOT to a detached-house buyer:
- They are choosing between near-identical homes in the same building/complex, so the honest question is "how does THIS one compare inside its own scheme", not "how rare is it in the suburb".
- What they optimise for: lock-and-leave / low-maintenance living, floor level and aspect, secure parking, the body-corporate levy and what it covers, walkability and proximity, and — for investors — yield and liquidity (how easily it re-sells).
- NEVER promise land, a backyard, a block, a yard, subdivision potential, "single-level", or "no neighbour behind". Those are house concepts and are FALSE for a unit. There is common property, not private land.

HARD EDITORIAL RULES (liability — non-negotiable):
- NO ADVICE. Never tell the reader what to do — no "you should", "now is a good time", "consider buying". Present data; the reader draws the conclusion.
- NO PREDICTIONS. Report indicators; use conditional language. Never "prices will rise/fall".
- NO SINGLE VALUATION FIGURE IN THE HEADLINE. Ranges/gaps only in the headline. The point estimate may appear in body text, always beside the range.
- The band is a MEASURED empirical coverage band, never a "confidence range".
- Every property trade-off is framed as VALUE, not a flaw. A seller should read this and feel we positioned their home honestly.
- Use the LISTING DATE, never a live day count (a hardcoded day number goes stale in Google snippets).
- FORBIDDEN WORDS: stunning, nestled, boasting, rare opportunity, robust market. Suburbs capitalised. Money as $1,250,000 not $1.25m.
- Only claim what the fact sheet supports. If a fact is absent (e.g. levy amount, pool, lift confirmed), do not invent it — either omit or state it as unknown.

THIS HOME'S HONEST ANGLE: it is one of many near-identical same-bedroom homes in its scheme. That is not a weakness to hide — it is LIQUIDITY and PRICE TRANSPARENCY: a thick record of same-building sales means the range is unusually well-evidenced and the home is easy to re-sell. Lean into that, not into manufactured scarcity.

OUTPUT — return ONLY valid JSON, no prose around it, this exact shape:
{
  "headline": "<=80 chars, a story/provocation, NO single $ figure",
  "sub_headline": "<=120 chars, the buyer's dilemma in one line, uses listing DATE if timing referenced",
  "verdict": "<=30 words, the line they repeat at dinner",
  "best_for": ["3-4 short buyer types this home genuinely suits"],
  "not_ideal_for": ["2-3 buyer types it honestly does not suit — framed neutrally"],
  "insights": [
    {"h2": "section title", "lifestyle_hook": "1 scannable sentence with a data point",
     "key_points": ["2-4 bullet facts"], "what_this_means": ["2-3 short sentences, EACH a separate array item, connecting data to the buyer's decision"]}
  ],
  "next_steps": ["3-4 specific, data-anchored steps — what to ask the agent, what to inspect, understand the valuation"],
  "cta_valuation": {"hook": "1-2 sentences teasing the same-complex comparable evidence", "label": "Walk through the valuation step by step"},
  "cta_market_buy": {"hook": "1-2 sentences using the attached-market data", "label": "Read the Robina buyer's market briefing", "url": "/market-intelligence/robina#buy"},
  "faqs": [
    {"question": "What is <address> worth?", "answer": "range + comp count + method; point beside range"},
    {"question": "How does this compare to others in <complex>?", "answer": "use scheme facts"},
    {"question": "How long has <address> been on the market?", "answer": "use the listing DATE, never a day count"},
    {"question": "What are the body corporate costs?", "answer": "state honestly that the levy is set by the scheme; if not in the data, say it must be confirmed on the disclosure statement"}
  ]
}
Produce exactly 4 insights covering: (1) the home in its scheme, (2) what the sales evidence says (valuation), (3) the attached market it sits in, (4) location/lifestyle at the doorstep.
"""

FACTCHECK_SYSTEM = """You are the fact-checker for a Fields Estate unit property page. You will be given a FACT SHEET and a DRAFT ai_analysis JSON. Your job:
1. Flag any claim in the draft NOT supported by the fact sheet, any invented number, any HOUSE framing that slipped in (land, backyard, block, yard, subdivision, single-level, "no neighbour behind"), any single $ valuation figure in the headline, any forbidden word (stunning, nestled, boasting, rare opportunity, robust market), any live day-count instead of the listing date, and any "confidence range" wording.
2. Return the CORRECTED full ai_analysis JSON (same shape) with every issue fixed, plus a short "_factcheck_notes" array listing what you changed. Return ONLY the JSON."""


VERIFY_SYSTEM = """You are the final verifier for a Fields Estate UNIT property page, deciding whether it may auto-publish. You are given a FACT SHEET and the corrected ai_analysis JSON. Judge it against the fact sheet and the editorial rules and return ONLY:
{"outcome": "clean|minor_flags|needs_review|failed", "issues": ["..."]}
- "clean": every claim supported by the fact sheet; no house framing (land/backyard/block/yard/subdivision/single-level); no single $ figure in the headline; no forbidden words; listing DATE not day-count; band described as empirical (not a "confidence range"); no advice/prediction.
- "minor_flags": tiny wording/style issues only, still publishable.
- "needs_review": a substantive but non-fabricated problem a human should check.
- "failed": a fabricated number/fact, a house-framing claim false for a unit, advice/prediction, or a $ valuation figure in the headline.
Be strict: default to needs_review if unsure, failed if a rule is broken."""


def call(client, system, user, max_tokens=4000, attempts=4):
    """The Max CLI intermittently exits 1 on larger prompts and then falls back to the
    (unfunded) Anthropic API, which 400s. Retry the whole create() — a fresh CLI invocation
    usually succeeds — rather than letting one flaky call kill the run."""
    last = None
    for i in range(attempts):
        try:
            r = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                                       messages=[{"role": "user", "content": user}])
            txt = r.content[0].text
            if txt and txt.strip():
                return txt
            last = RuntimeError("empty response")
        except Exception as e:  # noqa: BLE001 — includes the API-fallback 400
            last = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"call failed after {attempts} attempts: {last}")


def extract_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON found in model output")
    return json.loads(m.group(0))


def _as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if v in (None, ""):
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(v)) if p.strip()]
    return parts or [str(v)]


def coerce_shape(ai):
    """Force the array fields the frontend renders with .map() to be arrays — the model
    sometimes returns what_this_means/key_points as a single string, which crashes
    PropertyInsightCard (meaning.map is not a function)."""
    for k in ("best_for", "not_ideal_for", "next_steps"):
        ai[k] = _as_list(ai.get(k))
    for ins in ai.get("insights", []) or []:
        ins["key_points"] = _as_list(ins.get("key_points"))
        ins["what_this_means"] = _as_list(ins.get("what_this_means"))
    return ai


def _meta_title(headline, address):
    """Ensure the street number leads the SEO title (matches the house contract)."""
    num = (address or "").split()[0] if address else ""
    h = (headline or "").strip()
    if num and not h.startswith(num):
        return f"{num} {address.split(',')[0].split(' ', 1)[1] if ',' in address else ''} — {h}".strip(" —")
    return h or address


def generate(client, data, listing, content):
    """Draft -> fact-check/correct -> verify. Returns (ai_analysis, verify)."""
    facts = build_fact_sheet(data, listing, content)
    draft = extract_json(call(client, UNIT_SYSTEM,
                              f"FACT SHEET:\n{facts}\n\nWrite the ai_analysis JSON now."))
    final = extract_json(call(client, FACTCHECK_SYSTEM,
                              f"FACT SHEET:\n{facts}\n\nDRAFT:\n{json.dumps(draft, indent=1)}"))
    verify = extract_json(call(client, VERIFY_SYSTEM,
                               f"FACT SHEET:\n{facts}\n\nFINAL:\n{json.dumps(final, indent=1)}"))
    final = coerce_shape(final)
    return final, verify, facts


def store_analysis(db, suburb, slug, address, ai, verify, auto_publish):
    """Write ai_analysis to the listing doc with the same publish gate as the house
    pipeline: clean/minor_flags + AUTO_PUBLISH -> published; anything worse -> needs_review."""
    outcome = (verify or {}).get("outcome", "needs_review")
    now = datetime.now(timezone.utc).isoformat()
    ai = dict(ai)
    ai["meta_title"] = ai.get("meta_title") or _meta_title(ai.get("headline"), address)
    ai["meta_description"] = ai.get("meta_description") or ai.get("sub_headline")
    ai["_verify_outcome"] = outcome
    ai["_verify_issues"] = (verify or {}).get("issues", [])
    ai["engine"] = "unit_editorial_v1"
    ai["generated_at"] = now
    ai["model"] = MODEL
    if auto_publish and outcome in ("clean", "minor_flags"):
        ai["status"] = "published"
        ai["published_at"] = now
    elif outcome == "failed":
        ai["status"] = "failed_factcheck"
    else:
        ai["status"] = "needs_review"
    db[suburb].update_one({"url_slug": slug}, {"$set": {"ai_analysis": ai}})
    return ai["status"]


def write_review_file(data, ai, verify):
    out_dir = HERE.parent / "artifacts" / "unit_property_editorial"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = data["slug"]
    (out_dir / f"{slug}.json").write_text(json.dumps(ai, indent=2, ensure_ascii=False))
    md = [f"# ai_analysis — {data['address']}", "",
          f"> unit /property editorial · Opus 4.8/Max · verify={verify.get('outcome')} · status pending write", "",
          f"**Headline:** {ai.get('headline')}", f"\n**Sub-headline:** {ai.get('sub_headline')}",
          f"\n**Verdict:** {ai.get('verdict')}",
          "\n**Best for:** " + "; ".join(ai.get("best_for", [])),
          "\n**Not ideal for:** " + "; ".join(ai.get("not_ideal_for", []))]
    for i, ins in enumerate(ai.get("insights", []), 1):
        md.append(f"\n## Insight {i}: {ins.get('h2')}")
        md.append(f"*{ins.get('lifestyle_hook')}*")
        md += [f"- {kp}" for kp in ins.get("key_points", [])]
        md.append("\n" + " ".join(ins.get("what_this_means", [])))
    md.append("\n## FAQs")
    for f in ai.get("faqs", []):
        md.append(f"\n**{f.get('question')}**\n\n{f.get('answer')}")
    if verify.get("issues"):
        md.append("\n## Verify issues\n" + "\n".join(f"- {x}" for x in verify["issues"]))
    (out_dir / f"{slug}.md").write_text("\n".join(md))


def _publishable_unit(db, slug):
    uv = db["unit_valuations"].find_one({"_id": slug})
    return bool(uv and uv.get("publishable") is True and uv.get("point") is not None)


def process_one(client, db, address=None, slug=None, write=False, auto_publish=False):
    data = upd.assemble(address=address, slug=slug)
    slug = data["slug"]
    suburb = data["suburb_key"]
    if not _publishable_unit(db, slug):
        return {"slug": slug, "status": "skipped_no_publishable_valuation"}
    listing = db[suburb].find_one({"url_slug": slug}) or {}
    content = db["unit_content"].find_one({"_id": slug})
    ai, verify, _ = generate(client, data, listing, content)
    write_review_file(data, ai, verify)
    if write:
        status = store_analysis(db, suburb, slug, data["address"], ai, verify, auto_publish)
    else:
        status = f"dry_run(verify={verify.get('outcome')})"
    return {"slug": slug, "address": data["address"], "status": status,
            "verify": verify.get("outcome")}


def _target_unit_slugs(db, suburb, force):
    q = {"listing_status": "for_sale", "property_type": {"$ne": "House"}}
    if not force:
        q["ai_analysis"] = {"$exists": False}
    out = []
    for d in db[suburb].find(q, {"url_slug": 1}):
        s = d.get("url_slug")
        if s and _publishable_unit(db, s):
            out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--address")
    g.add_argument("--slug")
    g.add_argument("--suburb", help="all publishable for-sale units in this suburb key")
    g.add_argument("--all-target", action="store_true", help="all publishable units in Robina + Varsity Lakes")
    ap.add_argument("--write", action="store_true", help="write ai_analysis to the DB (default: dry-run to file only)")
    ap.add_argument("--auto-publish", action="store_true", help="publish clean/minor_flags (else needs_review)")
    ap.add_argument("--force", action="store_true", help="regenerate even if ai_analysis exists")
    args = ap.parse_args()

    db = get_gold_coast_db()
    client = make_client(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    if args.address or args.slug:
        r = process_one(client, db, address=args.address, slug=args.slug,
                        write=args.write, auto_publish=args.auto_publish)
        print(json.dumps(r, indent=1))
        return

    # batch — self-monitored (Rule 7/7b)
    from job_status import job_run
    suburbs = ["robina", "varsity_lakes"] if args.all_target else [args.suburb]
    with job_run("unit_editorial_generate", cadence_hours=24, title="Unit /property editorial") as beat:
        slugs = []
        for sub in suburbs:
            slugs += _target_unit_slugs(db, sub, args.force)
        results = []
        for s in slugs:
            try:
                results.append(process_one(client, db, slug=s, write=args.write, auto_publish=args.auto_publish))
            except Exception as e:
                results.append({"slug": s, "status": f"error: {type(e).__name__}: {e}"})
            print(json.dumps(results[-1]))
        published = sum(1 for r in results if r.get("status") == "published")
        review = sum(1 for r in results if r.get("status") == "needs_review")
        errors = sum(1 for r in results if str(r.get("status", "")).startswith("error"))
        beat.metrics = {"candidates": len(slugs), "processed": len(results),
                        "published": published, "needs_review": review, "errors": errors}
        beat.detail = f"{len(results)} processed / {len(slugs)} candidates · {published} published, {review} review, {errors} err"
        # Zero-output assertion (7b): candidates existed but none processed -> upstream broke.
        if slugs and len(results) == errors and errors > 0:
            raise RuntimeError(f"all {errors} unit-editorial generations failed — not an empty queue")
    print(f"\nDONE: {len(results)} processed, {published} published, {review} needs_review, {errors} errors")


if __name__ == "__main__":
    main()
