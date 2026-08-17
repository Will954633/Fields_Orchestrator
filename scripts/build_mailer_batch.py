#!/usr/bin/env python3
"""
build_mailer_batch.py — turn lead addresses into mailer-ready property reports.

The pipeline for a mail-out is: lead address -> Gold_Coast subject -> minted stub
-> full build -> passes the mailer_v2 gate -> PDF. This script does the middle
three for a batch and reports the YIELD, which is the number we actually need:
how many addresses must be built to land N mailable ones.

Selection (all four must hold, and each exists for a reason):
  * on the Live Leads Tracker "All Leads" tab           — a real lead, post-prune
  * NOT source "Listing Nearing Expiry"                 — those are ON the market
                                                          by design and have their
                                                          own process
  * resolves to a Gold_Coast doc with a floor area      — the comps engine EXCLUDES
                                                          a subject with no floor
                                                          area, which forces
                                                          valuation method='thin'
                                                          and leaves comps pending.
                                                          Measured 2026-08-17: this
                                                          is the single biggest
                                                          determinant of whether a
                                                          build can pass the gate.
  * property_type == "House" exactly                    — the valuation design
                                                          envelope is detached
                                                          houses. ⚠ Do NOT use
                                                          `"house" in type`; that
                                                          matches "Townhouse".

Builds run in `no_llm` (V1.5 deterministic) mode — the CURRENT shipped path, live
and default since 2026-08-16. Zero model calls, ~20-40 s per build instead of ~8 min.

⚠ The earlier claim that "0 of 38 no_llm reports ever passed the gate" was wrong: 32
of those 38 were minted stubs that had never been BUILT. Of the 8 genuinely built,
seven failed on one thing only — "no aerial" — because the resolver skipped the
satellite slot wholesale in deterministic mode. The aerials were already stored
under `aerial_boundary_url` (18,808 of them). Fixed in slot_resolver; pass
--mode full only if you deliberately want the deprecated AI path.

Usage
  python3 scripts/build_mailer_batch.py --limit 5 --dry-run   # show the picks
  python3 scripts/build_mailer_batch.py --limit 5             # build 5, report yield
  python3 scripts/build_mailer_batch.py --limit 60 --workers 3
"""
from __future__ import annotations
import argparse
import importlib.util
import os
import re
import subprocess
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = "/home/fields/venv/bin/python3"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from shared.db import get_client                       # noqa: E402
from live_leads_to_sheet import (                      # noqa: E402
    LIVE_SPREADSHEET_ID, GC_DB, get_sheets, set_env_from_file, resolve_gc_doc,
)

MINT = os.path.join(ROOT, "15_Off-Market/Page_Redesign_V4/Prototypes/mint_offmarket_report.py")
BUILD_MODE = os.environ.get("MAILER_BATCH_BUILD_MODE", "no_llm")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def slugify(addr):
    a = re.sub(r",?\s*QLD\s*\d{4}\s*$", "", addr, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", a.lower()).strip("-")


def suburb_key_for(doc, slug, known):
    """Which Gold_Coast collection holds this property.

    ⚠ Read it off the ADDRESS, not the slug tail. `doc["suburb"]` is None on
    cadastral stubs, and the obvious fallback — slug.rsplit("-", 1)[-1] — yields
    "lakes" for `67-azzurra-drive-varsity-lakes`, a collection that does not
    exist, so the mint fails with a subject-not-found that looks like missing data.
    """
    addr = doc.get("address") or ""
    tail = re.sub(r"\s+QLD\s*\d{4}\s*$", "", addr, flags=re.I).strip()
    cand = tail.rsplit(",", 1)[-1].strip().lower().replace(" ", "_")
    if cand in known:
        return cand
    # Fall back to the longest known suburb name the slug actually ends with.
    matches = [k for k in known if slug.endswith("-" + k.replace("_", "-"))]
    return max(matches, key=len) if matches else None


def candidates(svc, sm, gc, resolve_floor_area, limit):
    rows = svc.spreadsheets().values().get(
        spreadsheetId=LIVE_SPREADSHEET_ID,
        range="'All Leads'!A2:O10000").execute().get("values", [])
    known_suburbs = set(gc.list_collection_names())
    seen, out = set(), []
    for r in rows:
        addr = (r[7] if 7 < len(r) else "").strip()
        src = (r[1] if 1 < len(r) else "").strip()
        if not addr or not re.match(r"^\s*\d", addr) or "Listing Nearing Expiry" in src:
            continue
        slug = slugify(addr)
        if slug in seen:
            continue
        seen.add(slug)
        # ⚠ a junk hex token on the end of a slug ("...-robina-2e6f") will not
        # resolve; skip rather than mint a stub that can never build.
        if re.search(r"-[0-9a-f]{4}$", slug):
            continue
        if sm["property_reports"].find_one({"slug": slug}):
            continue
        d = resolve_gc_doc(gc, slug)
        if d is None or (d.get("property_type") or "").strip() != "House":
            continue
        if not resolve_floor_area(d):
            continue
        sub = suburb_key_for(d, slug, known_suburbs)
        if not sub:
            continue
        out.append({"slug": slug, "address": d.get("address"),
                    "suburb_key": sub, "lead_source": src})
        if len(out) >= limit:
            break
    return out


def build_one(c):
    """mint (as full) -> build -> report. Returns a result dict, never raises."""
    slug, sub = c["slug"], c["suburb_key"]
    env = dict(os.environ)
    t0 = datetime.now()
    col = get_client()["system_monitor"]["property_reports"]
    try:
        # Idempotent: mint only if there is no stub yet, so a re-run finishes what a
        # previous run left half-done (minted-but-unbuilt, or stuck in "building"
        # after a kill) instead of erroring on "already exists".
        if col.find_one({"slug": slug}) is None:
            m = subprocess.run([PY, MINT, "--slug", slug, "--suburb", sub],
                               cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
            if m.returncode != 0:
                return {**c, "ok": False, "stage": "mint",
                        "err": (m.stderr or m.stdout)[-200:]}
        # ⚠ NEVER close this client. shared.db.get_client() is a cached SINGLETON, so
        # a .close() here tears the connection down for the main thread and every
        # other worker — which surfaces several steps later as an unrelated-looking
        # "Cannot use MongoClient after close" and killed 2 of 5 in the first pilot.
        # `build_state` is unset (not just overwritten) so a doc stranded in
        # "building" by a killed run is eligible again.
        col.update_one({"slug": slug},
                       {"$set": {"build_mode": BUILD_MODE}, "$unset": {"build_state": ""}})
        b = subprocess.run([PY, "-m", "scripts.property_reports.build_property_report",
                            "--slug", slug, "--force"],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=2400)
        if b.returncode != 0:
            return {**c, "ok": False, "stage": "build", "err": (b.stderr or "")[-200:]}
    except subprocess.TimeoutExpired:
        return {**c, "ok": False, "stage": "timeout", "err": "exceeded timeout"}
    except Exception as e:  # noqa: BLE001
        return {**c, "ok": False, "stage": "exception", "err": str(e)[:200]}
    return {**c, "ok": True, "secs": (datetime.now() - t0).total_seconds()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--workers", type=int, default=3,
                    help="concurrent builds; each is network-heavy, keep modest")
    ap.add_argument("--mode", choices=["no_llm", "full"], default="no_llm",
                    help="no_llm = V1.5 deterministic (default, 0 model calls)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--slugs", nargs="+", default=[],
                    help="build these exact slugs instead of auto-selecting "
                         "(use to finish a part-done batch)")
    args = ap.parse_args()

    global BUILD_MODE
    BUILD_MODE = args.mode
    set_env_from_file()
    pv = _load("pv", "/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py")
    gm = _load("gm", os.path.join(
        ROOT, "11_House_Mini_Site/_shared/mailer_v2/generate_mailers_v2.py"))
    svc = get_sheets()
    cl = get_client()
    sm, gc = cl["system_monitor"], cl[GC_DB]

    if args.slugs:
        known = set(gc.list_collection_names())
        picks = []
        for slug in args.slugs:
            d = resolve_gc_doc(gc, slug)
            if d is None:
                print(f"   !! {slug}: not in Gold_Coast — skipped")
                continue
            picks.append({"slug": slug, "address": d.get("address"),
                          "suburb_key": suburb_key_for(d, slug, known),
                          "lead_source": "(explicit)"})
    else:
        picks = candidates(svc, sm, gc, pv.resolve_floor_area, args.limit)

    # Stock check. Building a report costs nothing, but a batch sized past the
    # envelopes on Pronto's floor produces artwork that cannot be posted — and the
    # shortfall would surface at the mail house rather than here. Warn only: the
    # build itself is harmless and a bigger ready pool is often deliberate.
    try:
        from fulfilment_stock import position
        pos, _, _, _ = position(sm)
        binding = min(pos.items(), key=lambda kv: kv[1]["pieces_possible"])
        if binding[1]["pieces_possible"] < len(picks):
            print(f"\n⚠ STOCK: {len(picks)} candidate(s) selected but only "
                  f"{binding[1]['pieces_possible']} piece(s) can be POSTED — "
                  f"{binding[0]} is the binding item "
                  f"({binding[1]['available']} available). Build is fine; the "
                  f"mail-out will need more stock.\n")
    except Exception as e:  # noqa: BLE001 — never let the stock read block a build
        print(f"(stock check skipped: {e})")
    print(f"{len(picks)} candidate(s) selected:\n")
    for c in picks:
        print(f"   {c['slug']:<48} {c['lead_source'][:24]}")
    if args.dry_run or not picks:
        cl.close()
        return

    per = "~20-40 s" if BUILD_MODE == "no_llm" else "~8 min"
    print(f"\nbuilding {len(picks)} in {BUILD_MODE} mode, {args.workers} worker(s) — "
          f"{per} each...\n", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(build_one, c): c for c in picks}
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            tag = "ok" if r["ok"] else f"FAILED@{r['stage']}: {r.get('err','')[:90]}"
            print(f"   [{len(results)}/{len(picks)}] {r['slug']:<46} {tag}", flush=True)

    # Yield is the whole point — re-read each doc and run the REAL gate.
    print(f"\n{'slug':<48}{'gate'}")
    print("-" * 78)
    ready = blocked = 0
    from collections import Counter
    why = Counter()
    for r in results:
        if not r["ok"]:
            blocked += 1
            why[f"build failed @ {r['stage']}"] += 1
            print(f"{r['slug']:<48}build failed @ {r['stage']}")
            continue
        d = sm["property_reports"].find_one({"slug": r["slug"]})
        errs = gm.check_ready(d) if d else ["no doc"]
        if errs:
            blocked += 1
            for e in errs:
                why[e] += 1
            print(f"{r['slug']:<48}{len(errs)} blocker(s): {errs[0][:40]}")
        else:
            ready += 1
            print(f"{r['slug']:<48}READY")
    n = len(results)
    print(f"\nYIELD: {ready}/{n} = {ready / n:.0%}" if n else "no results")
    if ready:
        print(f"to land 50 mailable, expect to build ~{round(50 * n / ready)} addresses")
    print("\nblocker frequency:")
    for k, v in why.most_common(10):
        print(f"   {v:>3}  {k[:66]}")
    cl.close()


if __name__ == "__main__":
    main()
