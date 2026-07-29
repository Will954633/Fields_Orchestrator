# Off-Market RL — Ledger

**Owner:** Off-Market RL cycle (autonomous, daily) · **Started:** 2026-07-29
**Goal:** discover which on-page INFORMATION + FORMAT best engage/convert homeowners who Google
their own address (`/off-market/:slug`), growing inbound seller enquiry. Design: `00_SCOPING.md`.
**Reward:** multi-milestone, time-delayed ladder (§5). **Action space:** content move × format (§2).
**Cadence:** daily now → twice-daily once traffic rises. **Coverage:** houses-only Bright-Data scrape,
GSC-governed ≤500/day, watched waves highest-value-suburb-first.

## Build log
- **2026-07-29** — Phase 0/1 stand-up. Built `offmarket_coverage_scraper.py` (validated: 24 Nerang houses minted,
  transform-only zero-fetch), `cycle_state.py`, `run_cycle.sh` + `cycle_prompt.md`. Fixed frontend `findPropertyById`
  (dynamic suburb-from-slug, was a hardcoded 9-suburb allowlist) + shipped Phase-0 deck instrumentation
  (`card_dwell`/`deck_exit`) in one batched commit `f1f35d5`. Screenshot-verified the live Nerang page.

## Cycles
- **Cycle 1 — 2026-07-29 12:20** — baseline + stand-up (observed). Corpus 16,904 eligible; 24 Nerang minted (not sitemapped).
  **Key finding:** new-suburb pages render thin (hero-only) because `getNearbySoldComps` filters `listing_status:"sold"`
  and minted docs are `listing_status:None` → no comps → wealth-reveal/market cards gate off. Comp-query extension is the
  unlock for rich new-suburb pages (staged for cycle 2). See `cycles/cycle_20260729_1220.md`.
