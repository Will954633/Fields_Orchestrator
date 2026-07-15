#!/usr/bin/env python3
"""
ad_session_summarize.py — Brain 2 Layer 4b: our own AI session summaries.

PostHog's AI session-summary endpoint rejects personal-API-key access
("This action does not support personal API key access"), so instead of scraping
their feature we generate BETTER summaries ourselves: feed each notable session's
full behaviour (Layer 4a) + the ad that drove it (Layer 2 annotation) to Opus on
Max, and get a funnel-tuned narrative + signal read.

Scope (to keep the Opus run small + high-value): every converter, plus every
non-converter session that showed real engagement (>=3 pages, or an article read
past 50%, or >60s dwell). Durable + idempotent by session_id.

Writes system_monitor.ad_session_summaries.
Usage: python3 scripts/brain2/ad_session_summarize.py [--limit N] [--force]
"""
import os, sys, json, time, argparse, subprocess
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

MODEL = "claude-opus-4-8"
LOG = "/home/fields/Fields_Orchestrator/logs/brain2-session-summarize.log"

PROMPT = """You are analysing a single website visitor session for a property-intelligence company (Fields). The visitor arrived from a specific Facebook ad. Below is (a) the ad that drove them and (b) their exact on-site behaviour, reconstructed from analytics events (pages, articles read with how far they scrolled, feed sections viewed, properties viewed, address searches, dwell time, rage-clicks, and whether they entered their address in the "analyse your home" tool = the conversion).

Produce ONE JSON object with EXACTLY these keys:
- "narrative": 2-4 sentence plain-English story of what this visitor did, start to finish.
- "intent_read": one of "buyer_browsing","seller_curious","seller_high_intent","tyre_kicker","comparison_shopper","unclear".
- "content_that_resonated": array of the specific articles/sections/pages they engaged with most (evidence of interest).
- "friction_signals": array of friction observed (rage-clicks, shallow scrolls, loops, quick exits) — empty if none.
- "converted": boolean.
- "why_converted_or_not": one sentence causal read grounded in the behaviour.
- "ad_to_landing_fit": one of "strong","partial","weak","mismatch" — did the ad's promise match what they did on site?
Output ONLY the JSON object. No prose, no fences."""


def log(m):
    line = f"{datetime.now(timezone.utc).isoformat()} {m}"
    open(LOG, "a").write(line + "\n"); print(line, flush=True)


def notable(s):
    if s.get("converted"):
        return True
    if s.get("n_pages", 0) >= 3:
        return True
    if s.get("dwell_seconds", 0) > 60:
        return True
    for a in s.get("articles_read", []):
        if (a.get("max_scroll_pct") or 0) >= 50:
            return True
    return False


def session_block(s, ann):
    a = (ann or {}).get("annotation", {})
    arts = [(x.get("title") or x.get("key"), str(x.get("max_scroll_pct")) + "% scroll")
            for x in s.get("articles_read", [])]
    lines = [
        "AD THAT DROVE THE VISIT:",
        f"  name: {ann.get('ad_name','') if ann else ''}",
        f"  format: {ann.get('format','') if ann else ''} | lever: {a.get('primary_emotional_lever')} | "
        f"hook: {a.get('hook_type')} | theme: {a.get('message_theme')}",
        f"  promise: {a.get('value_proposition','')}",
        "",
        "ON-SITE BEHAVIOUR:",
        f"  pages ({s.get('n_pages')}): {' > '.join(s.get('pages', [])[:15])}",
        f"  articles read: {arts}",
        f"  feed sections viewed: {s.get('sections_viewed', [])}",
        f"  properties viewed: {[p.get('property_id') for p in s.get('properties_viewed', [])]}",
        f"  address searches: {s.get('n_searches')} | dwell: {s.get('dwell_seconds')}s | rage-clicks: {s.get('rageclicks')}",
        f"  CONVERTED (entered address): {s.get('converted')} ({s.get('conversion_events')})",
    ]
    return "\n".join(lines)


def call_opus(block, timeout=300):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")}
    r = subprocess.run(
        ["claude", "-p", "--model", MODEL, "--effort", "high",
         "--settings", '{"alwaysThinkingEnabled":false}'],
        input=PROMPT + "\n\n===== SESSION =====\n" + block,
        capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {(r.stderr or r.stdout)[:200]}")
    out = r.stdout.strip()
    a, b = out.find("{"), out.rfind("}")
    if a == -1 or b < a:
        raise ValueError("no JSON")
    return json.loads(out[a:b + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    db = get_client()["system_monitor"]
    out = db.ad_session_summaries
    out.create_index("session_id", unique=True)
    ann_by_ad = {d["ad_id"]: d for d in db.ad_semantic_annotations.find({})}

    sessions = [s for s in db.ad_session_behaviour.find({}) if notable(s)]
    done = set(out.distinct("session_id")) if not args.force else set()
    todo = [s for s in sessions if s["session_id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    log(f"START — {len(sessions)} notable, {len(todo)} to summarize")

    ok = err = 0
    for i, s in enumerate(todo, 1):
        try:
            rec = call_opus(session_block(s, ann_by_ad.get(s["ad_id"])))
        except Exception as e:
            log(f"  [{i}/{len(todo)}] {s['session_id'][:12]} failed: {str(e)[:120]}")
            err += 1
            time.sleep(3)
            continue
        out.replace_one({"session_id": s["session_id"]}, {
            "session_id": s["session_id"], "ad_id": s["ad_id"],
            "converted": s.get("converted", False),
            "model": MODEL, "summary": rec,
            "created_at": datetime.now(timezone.utc).isoformat()}, upsert=True)
        ok += 1
        log(f"  [{i}/{len(todo)}] {s['session_id'][:12]} OK — intent={rec.get('intent_read')} "
            f"conv={rec.get('converted')} fit={rec.get('ad_to_landing_fit')}")
    log(f"DONE — {ok} ok, {err} failed")


if __name__ == "__main__":
    main()
