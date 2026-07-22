# AI-as-Distribution-Channel Doc — Reviewed (2026-07-23)

Reviewed the doc Will shared (`1Noe9k5XHorLKERwxlla5Q92QEPx6B7CtP3owycxBDt0`). It's unusually
thorough already — a real ChatGPT transcript, followed by actual `curl`/schema.org testing against
the live site, and a genuine self-correcting strategic analysis (two of three initial objections were
walked back on reflection: the "privacy" argument doesn't hold since Domain/realestate.com.au already
publish per-address valuation ranges, and the "giving away the product" argument doesn't hold at
pre-revenue/awareness-constrained stage). This is my endorsement + the concrete next action, not a
re-derivation — the doc already did the hard thinking.

## I agree with its final, corrected conclusion
- `/property/:id` pages (1,594 of them) are already fully SSR'd with rich schema.org markup
  (`RealEstateListing`, `Residence`, `Offer`, etc.) and indexable — genuinely AI-citeable today. The
  ceiling there is domain authority, not crawlability (matches the existing SEO-indexation baseline
  finding).
- The one real, still-open gap: **`/market-intelligence/:suburb` still shows "Loading market data…"
  in the server-rendered HTML** — verified this is still true right now (`curl` as Googlebot UA still
  returns the loading-shell text, not the actual median/chart data in the body). This is the single
  concrete, scoped fix that serves Google AND any AI browsing/citation equally.
- The line the doc lands on for what's safe to expose is right: **range + comparables + market
  context + methodology link is fine to expose per-address** (matches what bigger competitors already
  do, and complies with the existing range-not-single-figure rule) — but **the advice/strategy layer
  (recommended actions, positioning, sale-method) must never go into a machine-readable public feed**,
  since that's a direct hit on the hardest editorial rule (no advice, ever). That distinction is
  the correct one to hold going forward for any future AI-facing data work.

## Concrete next action (not yet built — this is a scoped follow-up, not this cycle's work)
SSR `/market-intelligence/:suburb`'s market data (medians, trends) into the response body, the same
way `/property/:id` already works. This is a genuine implementation task (needs the actual data-fetch
timing in that route understood — likely a `loader`/client-fetch split issue, not investigated in
depth this cycle) — scoping it properly deserves its own dedicated pass rather than a rushed partial
fix at the tail of an unrelated cycle.

## What I would NOT do (agreeing with the doc)
Do not build a standalone public JSON valuation API endpoint speculatively. The existing SSR'd
`/property/:id` pages already carry this data in citeable form; a dedicated API adds real engineering
+ governance surface (rate limiting, the directional-only-above-$2.5M filter, no-advice-field
scrubbing) for a benefit (AI citation volume) that isn't measured yet. Better sequence: ship the
market-intelligence SSR fix first, then check whether `ai_referral_signal` (already tracked in Brain
2) shows any lift before building anything bigger.
