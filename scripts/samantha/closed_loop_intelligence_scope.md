# Closed-Loop Intelligence (B1 → B2 → B3) — Development Scope
Will-approved 2026-07-17 ("absolutely, this would mimic reinforcement learning — create a scoping document").

## Concept
Turn the three brains into one learning loop that gets smarter every cycle:
- **Brain 1** (coaching-corpus graph) = hypothesis generator — external concepts proven elsewhere.
- **Brain 2** (FB Ads, PostHog, funnel collections) = ground truth — what WE measured.
- **Brain 3** (KB, 1,644 docs + fix-logs) = institutional memory — what we learned and why.
Today these are queried separately by hand. The loop makes concept → test → measurement → learning
a *pipeline*, which is functionally reinforcement learning: actions (tests) → reward (Brain-2 metric
delta) → policy update (source scores + KB learnings bias the next hypothesis).

## Pipeline stages (build order)
P1 — **Hypothesis queue** (`system_monitor.hypothesis_queue`).
   Schema: {concept, source(s), evidence_cite, surface, expected_effect, est_power (can our
   traffic read it?), priority_score, status: queued|live|concluded}. Feeder scripts:
   `brain1_query.py` + `search-kb.py` output → queue entries. This formalises the experiment
   backlog the charter already requires. (~1 day)
P2 — **Ledger link** — every launched test references its hypothesis_id; change_ledger `--sources`
   (SHIPPED tonight, commit 01bb956) tags which brain drove it. (~done + glue)
P3 — **Auto-measurement** — nightly job re-measures due ledger items from PostHog/FB automatically
   where `metric_how` is machine-readable (HogQL string), writes the verdict, flags "worse" for
   revert. Removes the manual re-measure step. (~2 days)
P4 — **Learning write-back** — every concluded test auto-writes a KB doc (hypothesis, result,
   verdict, context) via `save-to-kb.py` → Brain 3 grows from OUR results, not just external
   corpus. Source usefulness scores (`change_ledger.py sources`) feed P1's priority_score —
   sources that historically produce validated wins rank higher. **This is the RL policy update.**
   (~1 day)
P5 — **New data sources** (score them, don't assume): GSC API (organic queries — we fly blind
   here), JustCall call/SMS logs (engagement outcomes), FB comment/engagement text, mailout QR
   scans (flyer wave). Each enters as a tagged source and earns its priority via hit-rate.

## Honest constraints
- Our traffic (~600/wk) means most website tests conclude directionally, not significantly —
  the loop must record confidence level with every verdict (already in ledger verdicts).
- This is scaffolding around discipline we already run manually; value = nothing gets forgotten,
  every result compounds. No ML training required to start; a CatBoost propensity layer (Will's
  mailout idea) can join later as another hypothesis source.

## Suggested first build: P1 + P2 glue (one run), then P3.
