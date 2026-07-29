# General RL — Build Log

Running log of what's actually built. Scoping: [`00_SCOPING.md`](00_SCOPING.md). Human deps: [`WILL_TO_ACTION.md`](WILL_TO_ACTION.md).

---

## Phase 0 — Shared reward ledger + milestone map  (started 2026-07-29)

### ✅ `reward_ledger.py` — the milestone map + reward-weight table (LIVE)
The foundation everything else grades against. Read-only analytics layer over existing data
(`organic_journeys`, `lead_worklist`, `ad_daily_metrics`, `cost_tracking`) — **touches no website
code**, writes one new collection `system_monitor.rl_reward_ledger` (`_id:"latest"` for fast read +
timestamped history docs).

**Computes each run:**
- **Milestone map** — for each user, which seller-journey milestones they reached, and each
  milestone's **predictiveness** = P(true_reward | reached), Bayesian-shrunk to base rate (tiny-N safe).
  Self-reweighting → the built-in Goodhart defence (a milestone earns only what it currently predicts).
- **Channel / referrer / ai_source attribution** of conversion (the GEO signal lives in ai_source).
- **Cost attribution** — FB/Google spend + organic marginal (ai_compute+infra) → cost-per-conversion.

**True reward (v1 proxy):** `organic_journeys.converted` (address submit / contact-capture) = identified-
seller candidate. Strengthened once the identity-join fix (Gap A) lands.

**First seeded run (2026-07-29, window 2026-05-30→07-28, 240 users / 265 sessions / 7 conversions):**

| Milestone | reached | conv | predictiveness | lift |
|---|---|---|---|---|
| searched_address | 10 | 7 | 0.476 | **16.3×** ← highest-leverage pre-reward milestone |
| viewed_multiple_properties | 10 | 2 | 0.143 | 4.9× |
| return_visit | 20 | 3 | 0.126 | 4.3× |
| search_in_coverage | 120 | 7 | 0.057 | 2.0× |
| viewed_property | 126 | 3 | 0.024 | **0.82× (below base — passive browsing doesn't convert)** |
| submitted_address ★ | 7 | 7 | 0.596 | 20.4× (the reward) |

**First actionable insight:** getting a visitor to the **address-search** step is the single biggest
lever (16× lift; 7 of 10 searchers converted) — validates the FB funnel "what's MY number" law from the
onsite side. Passive property-browsing is *below* base rate → not a milestone worth chasing.

**Cadence / self-monitoring:** cron `30 0 * * *` (after the nightly `organic_journey_build` at 23:40).
`job_run("rl_reward_ledger", cadence_hours=24)` → self-registers on Systems Health Process Registry (Rule 7).
Validated: heartbeat status=success.

**Run:** `python3 reward_ledger.py [--dry-run] [--window-days N]`

### ✅ Identity join widened — lead-signup + subscribe forms (LIVE, deployed d22f3da)
Gap A: `posthog_distinct_id` was forwarded only by AYH/off-market/ladder forms. Now the for-sale-gate
(`SignupGate`→`lead-signup.mjs`) and newsletter (`SubscribeModal`/`SubscribeForm`→`subscribe.mjs`) forms
forward the **anonymous** PostHog id too (Will: no `identify()`, no new PII), and both backends persist it
on `lead_signups` / `subscribers`. → those conversions become joinable to the visitor's journey going forward.
Verified: react-router build clean; pushed as ONE Trees-API commit (Netlify discipline); deploy logged.

### ✅ Off-market deck trajectory added to the shared ledger (2026-07-29)
The Off-Market RL initiative (`15_Off-Market/Reinforcement_Learning/`) is an **application on this shared
framework**, not a fork. `organic_journey_build.py` now reconstructs `/off-market` sessions (previously dropped
as "not notable") and captures the deck events by presence — `offmarket_report_view`, `card_viewed`, `deck_exit`,
`offmarket_menu_*`, `forward_cta_clicked`, `offmarket_qualify` → new journey fields `is_offmarket`,
`offmarket_events`, `offmarket_card_views`. `reward_ledger._user_milestones()` grades four new milestones:
`offmarket_page_view`, `offmarket_deck_engaged`, `offmarket_intent_sell`, `offmarket_qualified` — same
predictiveness weighting as every channel. **First read:** offmarket_page_view reached 153 / lift **0.70 (below
base)** — the off-market engagement bottleneck, now quantified in the shared reward truth. The off-market cycle
READS this ledger for the macro/delayed reward and reads its own dense deck signals (dwell/swipe/reached-%) from
PostHog directly. One reward truth, many loops.

### ⏭ Next in Phase 0
- **Strengthen the true reward:** upgrade `reward_ledger.py` from the `converted` proxy to a real
  join across `lead_worklist` / `lead_signups` / `subscribers` / `offmarket_qualification` on
  `posthog_distinct_id` → contactable-seller (name+email+phone+intent). Now unblocked as the widened
  distinct_id data accumulates.
- **Retroactive stitch (optional):** best-effort backfill of distinct_id onto historic leads where a
  matching journey exists (email/session heuristics). Lower priority than forward-capture.
- **Then Phase 1:** the GEO/AI-channel flagship loop (pending WTA-008 approval).
