#!/usr/bin/env python3
"""
batch.py — run the Discovery Experience over a random sample of real homes.

  python3 batch.py                 # 10 random enriched core-suburb homes, seed 7
  python3 batch.py --n 15 --seed 3
  python3 batch.py --slugs a,b,c   # explicit set

Pipeline per property:  fact_bundle.build() -> bundles/<slug>.json (cached)
                        assemble()          -> output/<slug>.md
Then writes output/INDEX.md — one row per home (lead story, cards shown, gaps)
so Will can scan the whole batch and see which stories reveal themselves.
"""
import sys
import json
import random
import argparse
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))          # Fields_Orchestrator
sys.path.insert(0, str(HERE.parent.parent / "scripts"))

import fact_bundle
import assemble as asm
from src.mongo_client_factory import get_mongo_client

CORE = ["robina", "varsity_lakes", "burleigh_waters"]
OUT_DIR = HERE / "output"
OUT_DIR.mkdir(exist_ok=True)


def random_slugs(n, seed):
    """Standalone HOUSES only — no units / duplex-halves / townhouses.
    Filter: property_type House + real land size + no unit separator in address."""
    gc = get_mongo_client()["Gold_Coast"]
    pool = []
    for s in CORE:
        q = {
            "url_slug": {"$exists": True},
            "valuation_data": {"$exists": True},
            "property_type": "House",
            "land_size_sqm": {"$gt": 0},
            "address": {"$not": {"$regex": r"/"}},   # exclude "1/3", "20/1-15" etc.
        }
        for d in gc[s].find(q, {"url_slug": 1, "address": 1, "_id": 0}):
            pool.append((s, d["url_slug"]))
    random.seed(seed)
    return random.sample(pool, min(n, len(pool)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--slugs", default=None, help="comma-separated slugs (skips random)")
    ap.add_argument("--no-positioning", action="store_true")
    args = ap.parse_args()

    if args.slugs:
        pairs = [(None, s.strip()) for s in args.slugs.split(",") if s.strip()]
    else:
        pairs = random_slugs(args.n, args.seed)

    rows = []
    combined = []
    for suburb, slug in pairs:
        try:
            bundle = fact_bundle.build(slug, suburb, with_positioning=not args.no_positioning)
            (fact_bundle.BUNDLE_DIR / f"{slug}.json").write_text(json.dumps(bundle, indent=2, default=str))
            md = asm.assemble(slug)
            (OUT_DIR / f"{slug}.md").write_text(md)
            combined.append(md)
            disc = asm.detect_discovery(bundle)
            shown = sum(1 for _, fn in asm.CARDS if fn(bundle, asm.load_copy()) is not None)
            rows.append({
                "slug": slug,
                "address": bundle["address_short"],
                "suburb": bundle["suburb_display"],
                "lead": disc["angle"],
                "cards": shown,
                "gaps": len(bundle.get("gaps") or []),
            })
            print(f"  ✓ {slug:48} lead={disc['angle']:16} cards={shown}/10 gaps={len(bundle.get('gaps') or [])}", file=sys.stderr)
        except Exception:
            traceback.print_exc()
            print(f"  ✗ {slug} FAILED", file=sys.stderr)

    # index
    idx = ["# Discovery Experience — batch review index\n",
           f"{len(rows)} homes · random seed {args.seed}\n",
           "| # | Home | Suburb | Lead story | Cards | Gaps | File |",
           "|---|------|--------|-----------|-------|------|------|"]
    for i, r in enumerate(rows, 1):
        idx.append(f"| {i} | {r['address']} | {r['suburb']} | **{r['lead']}** | {r['cards']}/10 | {r['gaps']} | [{r['slug']}.md]({r['slug']}.md) |")
    (OUT_DIR / "INDEX.md").write_text("\n".join(idx))

    # ALL.md — every home's experience in one document, in index order.
    all_parts = ["# Discovery Experience — full batch\n",
                 f"{len(rows)} houses · random seed {args.seed}\n"]
    for i, (r, md) in enumerate(zip(rows, combined), 1):
        all_parts.append(f"\n\n<br>\n\n═══════════════  {i} / {len(rows)}  ═══════════════\n")
        all_parts.append(md)
    (OUT_DIR / "ALL.md").write_text("\n".join(all_parts))

    print(f"\n→ output/INDEX.md + output/ALL.md  ({len(rows)} homes)", file=sys.stderr)


if __name__ == "__main__":
    main()
