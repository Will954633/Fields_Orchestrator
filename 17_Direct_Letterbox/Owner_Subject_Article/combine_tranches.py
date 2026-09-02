#!/usr/bin/env python3
"""Merge two teaser build tranches into one lay-up-ready set, in engagement-rank
order. Tranche 1 (top-ranked houses) was built first; tranche 2 (next ranked houses,
built after tranche 1 fell short of 50 on the softened-market copy guard) sits
strictly below it in rank, so t1-order ++ t2-order IS the global engagement order.

Copies t2's teaser PDFs into the tranche-1 dir, writes a combined _built_slugs.json
(rank order, successes only) and a combined candidate list (for addr_by_slug), so
assemble_teaser_layup.py can pick the top 50 straight off it.

    python3 combine_tranches.py  # writes into pronto_batch_2026-09-02/
"""
import json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "pronto_batch_2026-09-02")
T2 = os.path.join(HERE, "pronto_batch_2026-09-02_t2")
CAND1 = os.path.join(HERE, "lead_lists", "PD-0003_candidates.json")
CAND2 = os.path.join(HERE, "lead_lists", "PD-0003_tranche2.json")
COMBINED_LIST = os.path.join(HERE, "lead_lists", "PD-0003_combined.json")

built1 = set(json.load(open(os.path.join(MAIN, "_built_slugs.json"))))
built2 = set(json.load(open(os.path.join(T2, "_built_slugs.json")))) if os.path.exists(
    os.path.join(T2, "_built_slugs.json")) else set()
built = built1 | built2
print(f"built: t1={len(built1)} t2={len(built2)} total={len(built)}")

# global rank order = t1 candidates then t2 candidates (t2 strictly lower rank)
cand1 = json.load(open(CAND1))
cand2 = json.load(open(CAND2))
rank_order = [c["slug"] for c in cand1] + [c["slug"] for c in cand2]
addr = {c["slug"]: c["address"] for c in cand1 + cand2}

# copy t2 PDFs into the main dir
for slug in built2:
    src = os.path.join(T2, f"{slug}.teaser.pdf")
    dst = os.path.join(MAIN, f"{slug}.teaser.pdf")
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copyfile(src, dst)

combined = [s for s in rank_order if s in built]
# guard against any built slug missing from the candidate lists (shouldn't happen)
for s in built:
    if s not in combined:
        combined.append(s)
json.dump(combined, open(os.path.join(MAIN, "_built_slugs.json"), "w"))
json.dump([{"slug": s, "address": addr.get(s, "")} for s in combined],
          open(COMBINED_LIST, "w"), indent=1)
print(f"combined _built_slugs: {len(combined)} (top will be taken for the layup)")
print(f"combined candidate list -> {COMBINED_LIST}")
