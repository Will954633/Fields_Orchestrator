#!/usr/bin/env python3
"""
batch_render.py — render the V4 flow across a random sample of off-market homes
and report the COVERAGE DISTRIBUTION.

Everything we know about coverage rests on n=2. This answers: across real
addresses, how often does each section actually render?

For each sampled home it will, if needed:
  1. run the production valuation (correct for an unsold subject — no sale to leak)
  2. mint a `property_reports` stub so the competitor matcher / change log can run
  3. render the V4 markdown and record which blocks fired

Caches (sold catchment, coordinates, timelines, medians, street premiums) are
built ONCE and shared — that is the slow part, ~25s. Per-property valuation is
~100ms after that.

    python3 batch_render.py --n 30
    python3 batch_render.py --n 30 --suburb robina --keep      # keep the .md files
"""
import argparse
import json
import os
import random
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = "/home/fields/Fields_Orchestrator"
for p in (ORCH, os.path.join(ORCH, "scripts"),
          os.path.join(ORCH, "15_Off-Market/Page_Redesign_V2"),
          "/home/fields/Feilds_Website/07_Valuation_Comps", HERE):
    sys.path.insert(0, p)

from dotenv import load_dotenv
from src.mongo_client_factory import get_mongo_client

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
SEED = 20260806

SECTIONS = ["§0 last-sale fact", "§1 range", "§2 adjusted comparables",
            "§2 obvious comparable", "§2 scarcity", "§5 trajectory",
            "§7 competitors", "§7 change log", "§7 market indicators", "§8 exposure"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    load_dotenv(os.path.join(ORCH, ".env"))
    rng = random.Random(SEED)
    client = get_mongo_client()
    gc = client["Gold_Coast"]
    reports = client["system_monitor"]["property_reports"]

    # ── sample ──────────────────────────────────────────────────────────────
    subs = [args.suburb] if args.suburb else SUBURBS
    pool = []
    for s in subs:
        for d in gc[s].find({"listing_status": {"$exists": False}, "property_type": "House"},
                            {"address": 1, "valuation_data.confidence": 1}):
            pool.append((s, d["_id"], d.get("address"), bool(d.get("valuation_data"))))
    rng.shuffle(pool)
    sample = pool[:args.n]
    print(f"Sampling {len(sample)} of {len(pool):,} off-market houses "
          f"(seed {SEED})\n")

    # ── shared caches, built once ───────────────────────────────────────────
    t0 = time.time()
    print("Building shared caches …")
    import precompute_valuations as pv
    sold_by_suburb = pv.load_sold_comparables(client) if hasattr(pv, "load_sold_comparables") \
        else pv._load_sold_comparables(client)
    keys = list(sold_by_suburb.keys())
    coords = pv.preload_gc_coordinates(client, keys) if hasattr(pv, "preload_gc_coordinates") \
        else pv._preload_gc_coordinates(client, keys)
    timelines = pv.preload_gc_timelines(client, keys) if hasattr(pv, "preload_gc_timelines") \
        else pv._preload_gc_timelines(client, keys)
    mc = pv.build_suburb_median_cache(sold_by_suburb) if hasattr(pv, "build_suburb_median_cache") \
        else pv._build_suburb_median_cache(sold_by_suburb)
    sc = pv.build_street_premium_cache(sold_by_suburb, mc) if hasattr(pv, "build_street_premium_cache") \
        else pv._build_street_premium_cache(sold_by_suburb, mc)
    print(f"  done in {time.time()-t0:.0f}s\n")

    import fact_bundle
    import build_v4_report as v4
    from refresh_property_reports import refresh_comparables_for_doc

    rows = []
    fired = Counter()
    for i, (suburb, _id, address, had_val) in enumerate(sample, 1):
        slug = None
        rec = {"address": address, "suburb": suburb, "had_valuation": had_val}
        try:
            # 1. valuation, if missing
            doc = gc[suburb].find_one({"_id": _id})
            # ⚠ The engine resolves its comparable pool from
            # `subject_doc['_collection']` or `subject_doc['suburb']` — and `suburb`
            # is NULL on every off-market doc. Without `_collection` the pool is
            # empty and every valuation returns insufficient_data. This is what
            # `run_subject_valuation.py` sets and an earlier version of this batch
            # did not, which understated §2 coverage badly.
            doc["_collection"] = suburb
            vd_now = doc.get("valuation_data") or {}
            if not vd_now or not vd_now.get("adjusted_comparables"):
                vd = pv.precompute_property_valuation(
                    gc, doc, gc[suburb], sold_by_suburb, coords, timelines, mc, sc)
                if vd:
                    gc[suburb].update_one({"_id": _id}, {"$set": {"valuation_data": vd}})
                    doc = gc[suburb].find_one({"_id": _id})
            rec["valuation"] = bool(doc.get("valuation_data"))

            # 2. slug — derive the same way the deck does
            from offmarket_intel_poller import _find_subject  # noqa
            # "41/55 Paradise Springs Avenue, Robina QLD 4226" -> 41-55-paradise-...
            slug = (address or "").lower().replace(",", "").replace(".", "").replace("/", "-")
            slug = "-".join(slug.split()[:-2]) if slug else None
            slug = slug.replace("--", "-").strip("-")

            # 3. report stub + competitor refresh
            if not reports.find_one({"slug": slug}):
                reports.insert_one({"slug": slug, "address": address,
                                    "suburb": suburb.replace("_", " ").title(),
                                    "suburb_key": suburb, "property_id": str(_id),
                                    "state": "offmarket", "source": "offmarket_v4_mint",
                                    "build_mode": "no_llm", "schema_version": 1})
            rdoc = reports.find_one({"slug": slug})
            try:
                refresh_comparables_for_doc(reports, gc, rdoc, False)
            except Exception:
                pass

            # 4. render — reuse the generator's own section functions
            v4.MISSING.clear()
            b = fact_bundle.build(slug, suburb)
            v4.globals_ = None
            ac = ((doc.get("valuation_data") or {}).get("adjusted_comparables")) or []
            v4.__dict__["_PERSISTED"] = [
                {"address": c.get("address"), "raw": c.get("sale_price"),
                 "adj": c.get("adjusted_price"), "pct": c.get("total_adjustment_pct"),
                 "when": (str(c.get("sale_date"))[:7] if c.get("sale_date") else None)}
                for c in ac if c.get("adjusted_price")]
            v4.__dict__["_MS"] = v4.market_snapshot(suburb)
            v4.__dict__["_REPORT"] = reports.find_one({"slug": slug}) or {}
            ls = v4.last_sale(gc, suburb, b["address"])
            parts = [v4.s0_arrival(b, ls), v4.s1_range(b),
                     v4.s2_working(b, v4.__dict__["_PERSISTED"]), v4.s3_method(),
                     v4.s4_dispersion(),
                     v4.s5_gain(ls, v4.__dict__["_MS"], b["suburb_display"]),
                     v4.s6_lender(b), v4.s7_moving(b), v4.s8_exposure(b), v4.s9_control(b)]
            md = "\n\n---\n\n".join(parts)
            missing = {m[0] for m in v4.MISSING}
            rec["missing"] = sorted(missing)
            rec["n_missing"] = len(missing)
            rec["words"] = len(md.split())
            for sec in SECTIONS:
                if sec not in missing:
                    fired[sec] += 1
            if args.keep:
                open(os.path.join(HERE, f"batch_{slug}.md"), "w").write(md)
        except SystemExit as e:
            rec["error"] = f"subject not resolvable: {e}"
            rec["n_missing"] = None
        except Exception as e:
            import traceback
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["trace"] = traceback.format_exc().splitlines()[-3:]
            rec["n_missing"] = None
        rows.append(rec)
        status = rec.get("error") or f"{rec['n_missing']}/10 missing · {rec['words']} words"
        print(f"  [{i:>2}/{len(sample)}] {str(address)[:44]:<44} {status}")

    # ── report ──────────────────────────────────────────────────────────────
    ok = [r for r in rows if r.get("n_missing") is not None]
    print(f"\n{'='*72}\nCOVERAGE — {len(ok)} rendered, {len(rows)-len(ok)} errored\n{'='*72}")
    print(f"{'section':<28}{'rendered':>10}{'':>4}{'%':>6}")
    for sec in SECTIONS:
        n = fired[sec]
        print(f"  {sec:<26}{n:>8} / {len(ok):<4}{n/len(ok)*100 if ok else 0:>5.0f}%")
    if ok:
        dist = Counter(r["n_missing"] for r in ok)
        print(f"\n  blocks missing per property:")
        for k in sorted(dist):
            print(f"    {k} missing: {'█'*dist[k]} {dist[k]}")
        w = sorted(r["words"] for r in ok)
        print(f"\n  word count: min {w[0]} · median {w[len(w)//2]} · max {w[-1]}")
    out = os.path.join(HERE, "batch_coverage.json")
    json.dump(rows, open(out, "w"), indent=1, default=str)
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
