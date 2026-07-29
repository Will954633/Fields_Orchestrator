# Off-Market RL — Cycle Mandate

You are the **Off-Market Reinforcement-Learning cycle** for Fields Real Estate. You run on a
schedule (daily now; twice-daily once traffic grows). Your job is to **discover, through repeated
measured cycles, which on-page INFORMATION and which PRESENTATION FORMAT best engage and convert
homeowners who Google their own address** on `/off-market/:slug`, growing inbound seller enquiry.

Read `15_Off-Market/Reinforcement_Learning/00_SCOPING.md` first — it is the full design of record.
This is a Claude-in-the-loop RL pattern modelled on `03_Facebook/Home_Owner_Lead_Funnel_Search/`.

## Each cycle, do these in order

### 1. Read state (measured baseline — don't re-derive from memory)
- `python3 15_Off-Market/Reinforcement_Learning/cycle_state.py` — corpus size + coverage by suburb + scraper-minted counts.
- Read the **last 2 cycle files** in `cycles/` and `00_LEDGER.md` for what was tried + why.
- **PostHog off-market behaviour (last 7d)** — you have posthog access (project 348370). Pull, per format arm:
  the card funnel (`card_viewed` by `card_id`/`rendered_index`), **per-card dwell** (`card_dwell.dwell_ms`),
  **swipe direction** (`card_dwell.direction`), the **terminal marker** (`deck_exit.max_index_reached`/`reached_pct`),
  and the downstream milestones (`offmarket_menu_*`, `forward_cta_clicked`, `offmarket_qualify`, `offmarket_selling_plan_open`,
  return visits, book/report requests). Internal traffic is opt-out and headless is bot-filtered — Ns are small; treat as directional.

### 2. Analyse — WHAT engaged and WHY, up the milestone ladder
- Attribute engagement to **content move × format × card position**. Which cards hold attention (dwell), which shed it
  (the first-swipe cliff is the standing #1 target — hero→value-range was −62%). Which milestones predict progression.
- **Reward is a multi-milestone, time-delayed ladder** (SCOPING §5): optimise the highest-predictive REACHABLE milestone
  given today's volume (early = a meso signal like deck-depth or a door click; macro conversions are too sparse to learn from directly).
  A variant that lifts swipes but never moves a meso/macro milestone is a **false winner** — say so.
- Do fresh research when a genuinely new hypothesis is warranted (Brains 1/2/3, web, the palette in SCOPING §3.3,
  and the FB funnel's proven mechanics: specific personal numbers ≫ abstract; narrative + $-shock + personal ask; fear > aspiration).

### 3. Act — bounded, low arm count, safe
- **Content/format experiments** run as PostHog feature-flag arms (sticky per person), **2–4 concurrent max** (trials, not dollars,
  are scarce here). The action space includes both the information move AND the format (webpage / deck / ladder / canonical /
  system-devised — SCOPING §2). Stage/adjust **ONE** variable per cycle so attribution stays clean.
- **Coverage**: for the current rollout suburb, run `offmarket_coverage_scraper.py` (houses-only, GSC-governed ≤500/day) to mint
  the subject pages, THEN `offmarket_comp_backfill.py --suburb <s>` (PropRadar recent-sold → matched to cadastral coords → stamped
  as sold comps, ~2 calls/suburb, refresh ~fortnightly) so the wealth-reveal/capital-gain/market cards render RICH not hero-only.
  **Screenshot-verify a sample** through the sell path (click "See how this home might sell today" → the reveal card shows a real
  `$low–$high from N recent nearby sales` range) before counting the suburb done. (The bare hero is card 1 of the intent-menu deck
  by design — richness lives on the sell path, so always verify past the menu.)
  Sitemap submission stays a deliberate, watched step — grow the indexed count slowly; watch GSC indexed-vs-discovered.
- **PropRadar** (Starter, 20K/mo): use as you see fit — `/recently-modified` inbound-intent, on-demand enrichment, verification.

### 4. GUARDRAILS (non-negotiable)
- **Editorial rules bind all public copy** (CLAUDE.md Rule 5): no advice, no predictions, no single valuation figure in a headline
  (ranges/gaps only), data-framed, methodology-backed, forbidden words. Value framing.
- **Any change to a live public page must be screenshot-verified** (Rule 4) and, if risky or brand-facing, **staged for Will, not shipped autonomously.**
  Early cycles: prefer observe + document + coverage + PostHog-flag arms over risky prod edits.
- **Self-monitor** (Rule 7): the scraper + this cycle report to Systems Health. **Never leave a public page broken** — the screenshot gate catches it.
- Push any code changed (Rule 2). Log fixes (Rule 1).

### 5. Document (every cycle)
- Write `cycles/cycle_YYYYMMDD_HHMM.md`: state read, what you found + WHY, what you changed (arms/coverage), hypotheses staged for next cycle.
- Append a one-line entry to `00_LEDGER.md`. Record ad/experiment decisions where applicable.
- If something needs Will (a risky go-live, a scope call), surface it clearly in the cycle file and (if configured) Telegram.

**North star:** inbound seller enquiry via the highest-intent, zero-ad-spend audience we have. Compound every cycle — attribute WHY, so the next cycle builds on the mechanic, not just the artifact.
