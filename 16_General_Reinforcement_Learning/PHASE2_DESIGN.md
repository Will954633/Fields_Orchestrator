# Phase 2 — Onsite Personalization (design for approval)

**Scope (Will, approved):** thin, staged, two-surface server-side decision layer.
**Hard constraint (Will, non-negotiable):** the site must NOT get any slower. It's already too slow.

## The constraint is the architecture

Measured baseline (2026-07-29, real users + curl):

| Surface | p75 LCP | TTFB (warm) | payload |
|---|---|---|---|
| market-metrics / property / off-market | **11–22 s** | — | heavy |
| `/for-sale-v3` | (heavy) | ~1.4 s (3.3 s cold) | 138 KB |
| `/analyse-your-home` | (light) | ~0.4 s | 24 KB |

LCP in the **tens of seconds** means **any** added work on the critical render path is unacceptable. So the design
rule is absolute: **personalization must not touch TTFB or LCP.** That rules out added SSR compute, render-blocking
JS, and any synchronous fetch before paint.

## The mechanism: server DECIDES, client APPLIES late (deferred slot)

Reconciles "server-side layer" with "zero added latency":

```
1. DECIDE (server, precomputed, offline)   — reward_ledger already knows milestone → best next content.
   A nightly job writes a tiny lookup: milestone_state → {slot content variant}. No per-request compute.
2. IDENTIFY (cheap)                         — the visitor's milestone_state comes from their distinct_id
   (cookie or one lightweight post-load call). No heavy work.
3. APPLY (client, AFTER paint)              — each surface has ONE personalization slot, rendered as its DEFAULT
   in SSR (so baseline perf is byte-for-byte unchanged). After the page is interactive (requestIdleCallback,
   post-LCP), a tiny script swaps in the variant for this visitor's state. Reserved height → no layout shift (CLS safe).
```

Because step 3 runs **after** LCP and the SSR default is unchanged, this **cannot** regress TTFB or LCP — provably.
The "personalization" is an enhancement layered on a fast default, not a rebuild of the render path.

## What gets personalized (v1 — narrow)

Driven by the reward ledger's milestone weights (address-search is the 26× lever; passive-browse is dead):

- **`/analyse-your-home`** (light, fast, the conversion surface): the slot nudges toward the **address-search**
  milestone based on state — e.g. returning visitor who searched before → "Pick up where you left off"; came from a
  market-metrics page → "You were reading Gold Coast data — see YOUR home". One slot, ~3 variants + default.
- **`/for-sale-v3`** (the browse surface): the slot surfaces the **next milestone** — e.g. viewed ≥2 properties →
  a soft bridge to address-search/AYH (the proven converting path), not more listings (which the ledger says don't convert).

All copy obeys editorial rules (data-framed, soft CTA, no advice). Variants are the RL "arms"; the ledger grades them.

## Guardrails (how we keep the promise)

1. **Perf gate:** measure p75 LCP + TTFB on both surfaces before and 48 h after ship (PostHog `$web_vitals` + curl).
   Ship stays only if LCP is unchanged within noise. This is a release blocker, not a nicety.
2. **Kill switch:** a single flag disables the slot instantly (reverts to SSR default) — no redeploy.
3. **CLS safe:** the slot reserves its space in SSR; the swap never shifts layout.
4. **No new blocking requests:** the decision is a cookie read or one idle-time call; if it fails, the default stays.
5. **Reward-gated rollout:** one surface first (`/analyse-your-home`), prove LCP-flat + a lift in the address-search
   milestone over a week, then the second surface.

## Build order

- **P2.0 — decision layer (backend, zero perf risk):** `personalization_policy.py` — reads `rl_reward_ledger` +
  a visitor's milestone-state → emits the milestone_state→variant table into `system_monitor.rl_personalization_policy`.
  Nightly. *(Safe to build now — no render-path change.)*
- **P2.1 — the slot component + deferred apply (needs Will's nod — it's the one render-path touch):** the SSR-default
  slot + post-LCP swap on `/analyse-your-home`. Behind the kill-switch flag. Perf-gated.
- **P2.2 — grade + iterate:** the slot's variants become RL arms; the ledger attributes which lifts the address-search
  milestone; weekly verdicts; then extend to `/for-sale-v3`.

## Open question for Will (the one render-path touch)

The decision layer (P2.0) is safe and I'll build it now. **P2.1 is the only piece that touches a live page** — even
though it's post-LCP and kill-switched. Approve the **deferred-slot mechanism** (server-decides / client-applies-late,
perf-gated, one surface first), or do you want to see the exact slot diff + a before/after LCP measurement on a preview
before it goes near production?
