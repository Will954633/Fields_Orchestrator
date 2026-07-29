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

### ⏭ Next in Phase 0
- **Identity-join fix (Gap A):** forward `posthog_distinct_id` from ALL conversion forms
  (`lead-signup.mjs`, `subscribe.mjs` currently don't) + retroactive stitch — expands the joinable
  population beyond form-submitters. Website code → careful, separate step (WTA-003).
- **Strengthen true reward:** join to `lead_worklist` contactable-seller (name+email+phone+intent)
  rather than the `converted` proxy, once the identity join is wider.
