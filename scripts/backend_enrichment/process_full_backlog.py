#!/usr/bin/env python3
"""
process_full_backlog.py
========================
Processes the ENTIRE remaining for-sale House editorial backlog across the
3 core target suburbs (Robina, Burleigh Waters, Varsity Lakes) — not just
PostHog-viewed listings (see process_viewed_for_sale.py for that narrower
demand-ranked runner).

Selection: listing_status=for_sale, property_type=House, in {robina,
burleigh_waters, varsity_lakes}, ai_analysis.status in {needs_review,
failed_factcheck, missing}.

Config (2026-07-21, Will's go-ahead after reviewing Tranche A + the
always-verify fix): OpenRouter backend, Sonnet 5, Lever 1 (COMPACT_COMPARABLES)
+ Lever 2 (PROMPT_CACHE) on, THINKING_MODE=adaptive/medium, AUTO_PUBLISH=1
(gated in generate_property_ai_analysis.py to only auto-publish
_verify_outcome in {clean, minor_flags} — max_retries_with_failures and
failed_factcheck are held back for manual review).

Usage:
  python3 process_full_backlog.py                       # list only
  python3 process_full_backlog.py --process --limit 76  # run the batch
"""
import os, sys, argparse, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.db import get_gold_coast_db

GEN = str(Path(__file__).resolve().parent / "generate_property_ai_analysis.py")
CORE_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
NEEDS = {"needs_review", "failed_factcheck", None, "NONE"}


def worklist(allowed_types=("House",)):
    db = get_gold_coast_db()
    rows = []
    for c in CORE_SUBURBS:
        for d in db[c].find(
            {"listing_status": "for_sale", "property_type": {"$in": list(allowed_types)}},
            {"url_slug": 1, "address": 1, "ai_analysis.status": 1, "property_type": 1},
        ):
            ai = (d.get("ai_analysis") or {}).get("status")
            if ai not in NEEDS:
                continue
            slug = d.get("url_slug")
            if not slug:
                continue
            rows.append({"slug": slug, "suburb": c, "address": d.get("address"),
                         "ai_status": ai or "none", "ptype": d.get("property_type")})
    return rows


def _backend_env():
    env = dict(os.environ)
    env["ANTHROPIC_BACKEND"] = "openrouter"
    env["USE_CLAUDE_MAX"] = "0"
    env["EDITORIAL_MODEL"] = env.get("EDITORIAL_MODEL", "anthropic/claude-sonnet-5")
    env["COMPACT_COMPARABLES"] = "1"
    env["PROMPT_CACHE"] = "1"
    env["THINKING_MODE"] = env.get("THINKING_MODE", "adaptive")
    env["THINKING_EFFORT"] = env.get("THINKING_EFFORT", "medium")
    env["AUTO_PUBLISH"] = "1"
    env["CLAUDE_MAX_CLI_TIMEOUT"] = env.get("CLAUDE_MAX_CLI_TIMEOUT", "600")
    return env


def run_one(slug):
    env = _backend_env()
    p = subprocess.run(["python3", GEN, "--slug", slug, "--force"],
                        env=env, capture_output=True, text=True, timeout=3600)
    out = p.stdout + "\n" + p.stderr
    meter = [ln for ln in out.splitlines() if "[METER]" in ln]
    status = [ln for ln in out.splitlines()
              if ln.startswith("[OK] Stored") or "failed_factcheck" in ln
              or "Pipeline complete" in ln or "_verify_outcome" in ln]
    return p.returncode, meter, status, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", action="store_true")
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--types", default="House")
    A = ap.parse_args()
    allowed = tuple(t.strip() for t in A.types.split(",") if t.strip())

    wl = worklist(allowed_types=allowed)
    print(f"=== Full backlog ({'/'.join(CORE_SUBURBS)}, types={allowed}) — {len(wl)} total ===")
    for r in wl:
        print(f"  {r['suburb']:>16} {r['ai_status']:>15}  {r['address']}")

    if not A.process:
        print("\n(list only — pass --process --limit N to generate)")
        return

    todo = wl[:A.limit]
    print(f"\n=== Processing {len(todo)} on OPENROUTER (AUTO_PUBLISH=1) ===")
    ok, fail = 0, 0
    for i, r in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {r['address']} ...", flush=True)
        rc, meter, status, _ = run_one(r["slug"])
        for ln in status:
            print("   ", ln)
        for ln in meter:
            print("   ", ln)
        print(f"    exit={rc}")
        if rc == 0:
            ok += 1
        else:
            fail += 1
    print(f"\n=== DONE: {ok} ok, {fail} failed (of {len(todo)}) ===")


if __name__ == "__main__":
    main()
