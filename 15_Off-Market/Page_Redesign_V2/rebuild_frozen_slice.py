#!/usr/bin/env python3
"""Rebuild the RELEASED slice of every frozen suburb.

Freezing a suburb stops it being EXPANDED (no new homes), but its already-released
slugs stay live and in the sitemap by design — so they must still receive content
fixes. The 2026-08-05 rebuild missed them: target_suburbs() excludes frozen
suburbs, so 1,000 indexed Nerang decks kept the orphaned card-05 question and the
pre-fix funnel label while the rest of the fleet was corrected.
"""
import sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import offmarket_discovery_build as ODB
import offmarket_discovery_nightly as N

gc = N._gc()
frozen = N.frozen_suburbs(gc)
slugs = sorted(N.frozen_released_slugs(gc))
print(f"frozen suburbs: {frozen}\nreleased slugs to rebuild: {len(slugs)}", flush=True)

# Resolve each slug's suburb from its existing deck doc (authoritative).
coll = ODB._mongo()
sub_of = {d["slug"]: d.get("suburb_key")
          for d in coll.find({"slug": {"$in": slugs}}, {"slug": 1, "suburb_key": 1})}

built = failed = 0
t0 = time.time()
for i, s in enumerate(slugs, 1):
    try:
        ODB.upsert(ODB.build_one(s, sub_of.get(s), rebuild=True))
        built += 1
    except Exception as e:
        print(f"  x {s}: {e}", flush=True)
        failed += 1
    if i % 200 == 0:
        r = i / max(1e-6, time.time() - t0)
        print(f"  .. {i}/{len(slugs)} built={built} failed={failed} {r:.1f}/s", flush=True)
print(f"\nfrozen-slice rebuild: built={built} failed={failed} in {int(time.time()-t0)}s")
