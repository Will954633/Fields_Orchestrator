# Off-Market Page Redesign V2 — Discovery Experience

A **deterministic** harness that turns the existing property resolvers into the
marketing expert's 10-card "emotional progression" as a markdown document — so we
can nail the insight/story layer over many real homes *before* touching the
front-end.

**No LLM.** Every card is either static framing copy or dynamic data from
resolvers that already exist (`scarcity_features`, `competitor_matcher`,
`positioning_object`, the valuation engine).

## The pipeline

```
fact_bundle.py   (slow, cached)   Gold_Coast doc + resolvers -> bundles/<slug>.json
        │                         scarcity, competition, comps, value drivers,
        │                         buyer, valuation range, positioning, POIs
        ▼
copy.yaml        (the file we iterate)   static framing for all 10 cards
        │
        ▼
assemble.py      (instant, no data)   bundle + copy -> output/<slug>.md
        │
        ▼
batch.py         run over a random sample -> output/*.md + output/INDEX.md
```

**Why the split:** data is expensive, copy iteration is constant. Bundles are
cached, so editing `copy.yaml` and re-running `assemble.py` is instant — no DB hit.

## Iterate on the story

1. Read `output/INDEX.md`, open the per-home files.
2. To change a **sentence** → edit `copy.yaml`, re-run `python3 assemble.py --slug X`.
3. To change **which story leads** → edit `detect_discovery()` in `assemble.py`.
4. To change **what data a card shows** → edit `fact_bundle.py` (then re-run it).

## Run

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
python3 batch.py --n 10 --seed 7          # random sample
python3 assemble.py --slug <slug> --print  # re-render one after a copy edit
```

## The three-jobs contract (per the directive)

Every card: **answer** the previous card's question → **reveal** the substance →
**open** the next curiosity loop. A card with no honest data is **omitted, never
faked** (see each file's `build notes`).

## Known iteration items (v1)

- **Discovery engine over-fires "scarcity"** — 7/10 in the first batch. Needs
  stronger differentiation so common homes don't all read as rare.
- **Card 07 "may negotiate"** currently borrows the positioning anti-frame noun,
  which is a "what we won't claim" item, not a true buyer-negotiation lever.
- **Card 01 credibility counts** are real but modest (~20 characteristics) vs the
  directive's illustrative "487" — decide framing.
- Units/apartments legitimately lose scarcity/comp/valuation cards (thin land data).
