#!/usr/bin/env python3
"""
process_viewed_for_sale.py
==========================
Demand-prioritised editorial runner. Processes CURRENT for-sale listings that
people are ACTUALLY viewing (PostHog /property/ pageviews), highest-viewed
first, skipping any that already have a usable page.

Why: Max weekly quota is scarce and the full for-sale backlog is ~109. PostHog
shows only a subset of listings draw real attention. Spend tokens where the
demand is.

Selection:
  - source of demand: $pageview on /property/<slug> over --days (default 120)
  - keep: listing_status == 'for_sale'
  - keep: ai_analysis missing OR status in {needs_review, failed_factcheck}
    (i.e. no usable published/draft page yet)
  - order: by view count desc

Usage:
  # just show the prioritised worklist (no LLM calls):
  python3 process_viewed_for_sale.py

  # process the top N, metering cost, on the API (funded key, prompt caching):
  USE_CLAUDE_MAX=0 python3 process_viewed_for_sale.py --process --limit 1 --api

  # process on Max instead (uses weekly quota):
  python3 process_viewed_for_sale.py --process --limit 1
"""
import os, re, sys, json, argparse, subprocess, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.db import get_gold_coast_db

GEN = str(Path(__file__).resolve().parent / "generate_property_ai_analysis.py")
PID = os.environ.get("POSTHOG_PROJECT_ID")
KEY = os.environ.get("POSTHOG_ALL_ACCESS_KEY") or os.environ.get("POSTHOG_PERSONAL_API_KEY")


def hog(sql):
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode()
    r = urllib.request.Request(f"https://us.posthog.com/api/projects/{PID}/query/", data=body,
                               headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=120).read())["results"]


def viewed_slugs(days):
    rows = hog(f"""SELECT properties.$pathname AS path, count() AS views, count(DISTINCT person_id) AS persons
FROM events WHERE event='$pageview' AND properties.$pathname LIKE '/property/%'
AND timestamp > now() - INTERVAL {int(days)} DAY
GROUP BY path ORDER BY views DESC LIMIT 500""")
    out = []
    for path, views, persons in rows:
        s = path.replace("/property/", "").strip("/").lower()
        # drop junk: raw Objectids and url-encoded tails
        if not s or "%" in s or re.fullmatch(r"[0-9a-f]{24}", s):
            continue
        out.append((s, int(views), int(persons)))
    return out


def build_slug_index(db):
    idx = {}
    for c in db.list_collection_names():
        try:
            for d in db[c].find({"url_slug": {"$exists": True}, "listing_status": "for_sale"},
                                {"url_slug": 1, "listing_status": 1, "property_type": 1,
                                 "ai_analysis.status": 1, "address": 1}):
                idx[(d.get("url_slug") or "").lower()] = (c, d)
        except Exception:
            pass
    return idx


NEEDS = {"needs_review", "failed_factcheck", None, "NONE"}


def worklist(days):
    db = get_gold_coast_db()
    idx = build_slug_index(db)
    rows = []
    seen = set()
    for slug, views, persons in viewed_slugs(days):
        hit = idx.get(slug)
        if not hit or slug in seen:
            continue
        seen.add(slug)
        coll, d = hit
        ai = (d.get("ai_analysis") or {}).get("status")
        if ai in NEEDS:
            rows.append({"slug": slug, "views": views, "persons": persons, "suburb": coll,
                         "address": d.get("address"), "ai_status": ai or "none",
                         "ptype": d.get("property_type")})
    return rows


VERTEX_KEY = "/home/fields/.gcp-vertex-key.json"


def _backend_env(mode):
    """mode: 'vertex' (Sonnet 5 via GCP), 'api' (direct Anthropic), or 'max'."""
    env = dict(os.environ)
    env["COMPACT_COMPARABLES"] = env.get("COMPACT_COMPARABLES", "1")
    env["CLAUDE_MAX_CLI_TIMEOUT"] = env.get("CLAUDE_MAX_CLI_TIMEOUT", "600")
    if mode == "vertex":
        env["ANTHROPIC_BACKEND"] = "vertex"
        env["USE_CLAUDE_MAX"] = "0"
        env["EDITORIAL_MODEL"] = env.get("EDITORIAL_MODEL", "claude-sonnet-5")
        env["PROMPT_CACHE"] = "1"
        env["VERTEX_PROJECT_ID"] = env.get("VERTEX_PROJECT_ID", "fields-estate")
        env["VERTEX_REGION"] = env.get("VERTEX_REGION", "global")
        env.setdefault("GOOGLE_APPLICATION_CREDENTIALS", VERTEX_KEY)
    elif mode == "api":
        env["ANTHROPIC_BACKEND"] = ""
        env["USE_CLAUDE_MAX"] = "0"
        env["PROMPT_CACHE"] = "1"
    else:  # max
        env["USE_CLAUDE_MAX"] = "1"
    return env


def preflight(mode):
    """One tiny call to confirm the backend is live (e.g. Vertex quota landed)."""
    env = _backend_env(mode)
    code = ("import os,sys\n"
            "sys.path.insert(0,os.path.dirname(%r))\n"
            "from claude_max_client import make_client\n"
            "c=make_client(api_key=os.environ.get('ANTHROPIC_API_KEY',''), use_max=False)\n"
            "m=c.messages.create(model=os.environ.get('EDITORIAL_MODEL','claude-sonnet-5'),max_tokens=20,"
            "messages=[{'role':'user','content':'Reply with exactly: READY'}])\n"
            "print('PREFLIGHT:', m.content[0].text.strip())\n" % GEN)
    p = subprocess.run(["python3", "-c", code], env=env, capture_output=True, text=True, timeout=120)
    ok = "READY" in (p.stdout or "")
    return ok, (p.stdout + p.stderr).strip()[-400:]


def run_one(slug, mode):
    env = _backend_env(mode)
    p = subprocess.run(["python3", GEN, "--slug", slug, "--force"],
                       env=env, capture_output=True, text=True, timeout=3600)
    out = p.stdout + "\n" + p.stderr
    meter = [ln for ln in out.splitlines() if "[METER]" in ln]
    status = [ln for ln in out.splitlines() if ln.startswith("[OK] Stored") or "failed_factcheck" in ln or "Pipeline complete" in ln]
    return p.returncode, meter, status, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--process", action="store_true", help="actually generate (else just list)")
    ap.add_argument("--limit", type=int, default=1, help="max properties to process")
    ap.add_argument("--vertex", action="store_true", help="run Sonnet 5 via Google Vertex (GCP billing)")
    ap.add_argument("--api", action="store_true", help="run on the funded direct Anthropic API")
    ap.add_argument("--preflight", action="store_true", help="just test the backend is live (quota landed) and exit")
    A = ap.parse_args()

    mode = "vertex" if A.vertex else "api" if A.api else "max"

    if A.preflight:
        ok, detail = preflight(mode)
        print(f"[{mode}] preflight: {'✅ READY' if ok else '❌ not ready'}")
        print(detail)
        return

    wl = worklist(A.days)
    print(f"\n=== Viewed for-sale listings needing editorial (last {A.days}d) — {len(wl)} total ===")
    print(f"{'views':>5} {'ppl':>4} {'ai_status':>15}  {'type':>6}  address")
    for r in wl:
        print(f"{r['views']:>5} {r['persons']:>4} {r['ai_status']:>15}  {str(r['ptype'])[:6]:>6}  {r['address']}")

    if not A.process:
        print(f"\n(list only — pass --process --limit N [--api] to generate)")
        return

    todo = wl[:A.limit]
    print(f"\n=== Processing top {len(todo)} on {mode.upper()} ===")
    for i, r in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {r['address']} ({r['views']} views) ...")
        rc, meter, status, _ = run_one(r["slug"], mode)
        for ln in status:
            print("   ", ln)
        for ln in meter:
            print("   ", ln)
        print(f"    exit={rc}")


if __name__ == "__main__":
    main()
