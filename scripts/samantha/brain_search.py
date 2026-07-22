#!/usr/bin/env python3
"""
brain_search.py — Samantha's unified, FAST retrieval surface over the Brains.

Answers "what do we have about X?" across the brain graphs with ZERO LLM cost (lexical score
+ 1-hop graph expansion), so Samantha's runs and the voice agent can call it freely for
grounding. For a full synthesised answer (expensive: sonnet-5 + judge, ~minutes/$), hand off
to `brain1_deep.py --package <pkg>` — this tool prints that command under --deep.

Brains:
  --brain 3   Brain 3 — internal OPERATIONAL knowledge (fix-logs, CEO memory, articles, focus,
              ad decisions, seller book). What Fields has decided/built/learned. [default]
  --brain 1   Brain 1 — external knowledge (coaching corpus + KB books/papers).
  --brain all Both, results tagged by brain.

Usage:
  python3 scripts/samantha/brain_search.py "seller acquisition strategy" [--brain 3|1|all]
          [--max 8] [--json] [--deep]
"""
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain1_query as bq

PACKAGES = {
    "1": ("Brain 1 (external: coaching + KB books)", "/home/fields/brain1_build/package.json"),
    "3": ("Brain 3 (internal ops)", "/home/fields/brain3_ops/package.json"),
}


def search_one(pkg_path, query, k):
    bq.PACKAGE = pkg_path
    pkg = bq.load()
    scored = bq.score_units(pkg, query)
    top = [u for _, u in scored[:k]]
    top_ids = {u["id"] for u in top}
    neigh_ids, _ = bq.expand(pkg, top, top_ids)
    by_id = {u["id"]: u for u in pkg["units"]}
    neigh = [by_id[i] for i in list(neigh_ids)[:max(0, k // 2)] if i in by_id]
    return [
        {"id": u["id"], "source": u["src"].get("lib", ""), "date": u.get("date", ""),
         "doc": u["src"].get("course", ""),
         "concepts": u.get("concepts", [])[:4],
         "quote": (u.get("quotes") or [""])[0][:220],
         "answers": (u.get("asks") or [""])[0][:140]}
        for u in top + neigh
    ], len(scored)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--brain", choices=["1", "3", "all"], default="3")
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--deep", action="store_true", help="print the deep-synthesis command instead")
    args = ap.parse_args()

    brains = ["1", "3"] if args.brain == "all" else [args.brain]

    if args.deep:
        for b in brains:
            _, path = PACKAGES[b]
            print(f'env -u CLAUDECODE python3 scripts/samantha/brain1_deep.py "{args.query}" '
                  f'--package {path}')
        return

    out = {}
    for b in brains:
        label, path = PACKAGES[b]
        if not os.path.exists(path):
            sys.stderr.write(f"[warn] {label} package missing: {path}\n")
            continue
        results, matched = search_one(path, args.query, args.max)
        out[b] = {"brain": label, "matched": matched, "results": results}

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    for b, d in out.items():
        print(f"\n=== {d['brain']} — {d['matched']} units matched, top {len(d['results'])} ===")
        for r in d["results"]:
            src = r["source"].replace("internal:", "").replace("KB:", "KB/")
            datestr = f" ({r['date']})" if r.get("date") else ""
            print(f"  [{src}] {r['id']}{datestr}  {r['doc'][:60]}")
            if r["quote"]:
                print(f"     “{r['quote']}”")
            if r["concepts"]:
                print(f"     concepts: {', '.join(r['concepts'])}")
    print(f"\n(for a full synthesised answer: add --deep to get the brain1_deep command)")


if __name__ == "__main__":
    main()
