#!/usr/bin/env python3
"""Build teasers for the top-engaged Google off-market-report leads, netting 50
mailable. Full mailing guards ON (PropRadar + live off-market page check + the
holding-band copy guard). Writes per-address <slug>.teaser.pdf into the batch dir.
"""
import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "pronto_batch_2026-08-26")
os.makedirs(BATCH, exist_ok=True)
LIST = json.load(open("/tmp/teaser_build_list_all98.json"))
WORKERS = 2  # keep VM load in check (4 cores; each build spawns article + chrome)
VENV = "/home/fields/venv/bin/python3"
GEN = os.path.join(HERE, "build_owner_mailer.py")

def build(item):
    addr = item["address"]
    p = subprocess.run(
        [VENV, GEN, "--teaser", "--address", addr, "--out-dir", BATCH],
        capture_output=True, text=True, timeout=300, cwd=HERE)
    ok = p.returncode == 0
    tail = (p.stdout + p.stderr).strip().splitlines()
    why = tail[-1][:120] if tail else ""
    return {"slug": item["slug"], "address": addr, "ok": ok, "rc": p.returncode, "why": why}

results = []
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = {ex.submit(build, it): it for it in LIST}
    for fut in as_completed(futs):
        r = fut.result()
        results.append(r)
        flag = "OK " if r["ok"] else f"rc{r['rc']}"
        print(f"  {flag}  {r['address'][:40]:40}  {'' if r['ok'] else r['why']}", flush=True)

# preserve rank order from LIST for the successes
order = {it["slug"]: i for i, it in enumerate(LIST)}
built = sorted([r for r in results if r["ok"]], key=lambda r: order[r["slug"]])
json.dump(results, open(os.path.join(BATCH, "_build_results.json"), "w"), indent=1)
json.dump([r["slug"] for r in built], open(os.path.join(BATCH, "_built_slugs.json"), "w"))
print(f"\nBUILT {len(built)} / {len(LIST)} attempted.  (need 50)")
print("batch dir:", BATCH)
