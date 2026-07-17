# SEO / SSR Property-Page Sprint — Scope (Will-approved "go ahead and scope it", 2026-07-17)

Owner: Samantha (scoping) → engineering execution in reversible increments.
Goal ladder: crawlable property pages → indexation of ~1,594 /property URLs (currently ~0%) →
organic + AI-referral demand → address entries → seller leads → appraisals.

## Problem (Brain 2 evidence)
1. `/property/:id` and `/your-home/:address` serve a JS shell — crawlers and AI browsers see
   "Loading your property report…" only. Confirmed independently by Will's ChatGPT transcript
   (2026-07-17) and by `seo_indexation_check.py` (75% discovered-not-indexed, ~0% indexed).
2. Search-result copy is weak/generic for properties never processed by the analysis system —
   they fall back to the template description ("Property report with valuation, comparable sales…").
   Will's SEO-notes examples (59 Bluejay St, 17 Pitta Pl) are exactly these fallback cases.
3. Sold pages = 86% of the SEO surface (sold_editorial_scoping) — the biggest win is there.

## Sprint slices (each reversible, shippable alone)
S1 — SSR body for /property pages (prerequisite for everything).
   Extend the market-metrics SSR pattern (already proven in prod) to property pages: prerender
   crawler-visible HTML body — address, beds/baths/car, floor area, listing status, sale
   price + date (exact figures), 3-5 comparable sales, methodology note. No client-JS required
   to read the core facts. Editorial rules apply (no advice/forecast; single-figure valuation only
   inside the page, never in meta).
S2 — Meta/description upgrade from analysed data.
   Where `ai_analysis` or the zero-LLM insight engine has output, generate unique
   title/description per page; keep fallback template only where no data exists. This directly
   answers Will's SEO-notes question: yes — un-analysed properties get generic copy today; fix =
   widen coverage via the zero-LLM sold insight engine (no per-page LLM cost).
S3 — Sold-page re-enable with slugs (~1,500 pages) — staged batches (100 → 500 → rest),
   watching GSC indexation after each batch. NEVER a 1k-5k bulk dump (seo_indexation_baseline).
S4 — AI-distribution readiness: verify OAI-SearchBot / PerplexityBot / ClaudeBot in robots.txt
   allow-list; confirm rendered body is readable via `curl -A` per bot; add a machine-readable
   JSON-LD block (RealEstateListing schema) per property.

## Measurement (change ledger, one entry per slice)
- Metric: GSC indexed count on /property URLs (baseline ~0%) + organic entries to /property
  (PostHog, baseline from seo_landing_performance.py).
- Review: 14/28 days per slice (indexation is slow — no early verdicts).

## Effort / risk
- S1 is the only non-trivial slice (Netlify prerender or edge-function render of existing
  property.mjs data). All slices are one-commit revertable; no schema changes; no spend.
- Order is strict: S1 → S2 → S3 → S4. S3 without S1 wastes the crawl budget.
