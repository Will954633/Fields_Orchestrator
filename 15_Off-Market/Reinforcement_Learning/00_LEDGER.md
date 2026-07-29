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
- **Cycle 1b — 2026-07-29 (same session) — comp finding RESOLVED.** Built `offmarket_comp_backfill.py`: PropRadar
  recent-sold houses (~2 calls/suburb) → matched to cadastral docs for coords (87% match) → stamped as `listing_status:"sold"`
  + `sale_price`/`sold_date` comps. Nerang: 23 comps stamped; 6 within ~1km of 54 Crusader Way. **Screenshot-verified the full
  sell path**: page went 1/1 → **7 cards**, reveal card shows real **$940,000–$1,240,000 from 6 recent nearby sales** (editorially
  clean: range + methodology note, our method, no third-party AVM). Corrected the cycle-1 misread: the visible "1/1" is the
  intent-menu gate (by design); the comp backfill was still required so the sell path shows the real range vs the "one step away" fallback.
- **First full wave — NERANG — 2026-07-29.** Transform-only mint (zero fetch): **3,472 houses minted → 3,479 off-market house pages total**.
  Comp backfill: 23 PropRadar recent sales stamped → **100% of a 300-page sample has a comp within 2.5km** (Nerang is compact) → every
  page renders the real reveal card. Screenshot-verified across streets (Crusader Way $940k–$1.24M; Dugandan St $1.0M–$1.51M; both 7-card
  sell decks). **NOT sitemapped** (watched step pending Will). 1,838 no-timeline houses remain → bounded Bright-Data fetch batch (max 300)
  running in background (`logs/offmarket_nerang_fetch_batch.log`); the daily cycle finishes the tail. Skipped: 216 not-house, ~2.5K strata units, 1 waterfront.
- **Sitemap rollout STARTED — NERANG — 2026-07-29.** Release-gated expansion in `generate-sitemap.mjs` (per-suburb counter in
  `Gold_Coast.offmarket_sitemap_release`; core suburbs unlimited/unchanged). First **500 of 3,479** Nerang pages LIVE in the sitemap
  (verified: live sitemap off-market 17,245 -> 17,745). `offmarket_sitemap_release.py` +500/day cron @ 06:00 AEST (before the 06:15 VM
  regen that pushes it live); GSC-governed — hold/reduce if discovered-not-indexed backlog builds. Full Nerang in ~7 days. Deploy: website d070e95.
