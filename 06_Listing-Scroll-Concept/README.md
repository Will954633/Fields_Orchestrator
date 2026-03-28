# Decision Feed -- /for-sale Redesign Concept

**Date:** 28 March 2026
**Status:** Concept locked, ready for build after AI analysis coverage reaches 100%

---

## What This Is

A complete redesign of `https://fieldsestate.com.au/for-sale` from a directory-style listing grid into a "Decision Feed" -- a vertical stream of ranked market judgements that converts passive Facebook discovery traffic into engaged property page visitors.

The concept was validated with a live HTML mockup and is ready for production build in React once all 127 active listings have published AI editorial analysis.

---

## Documents

| File | Purpose |
|------|---------|
| [01-PRODUCT-CONCEPT.md](01-PRODUCT-CONCEPT.md) | Product vision, UX principles, page architecture, card types, copy rules, feed ordering, success metrics, data requirements |
| [02-DEVELOPMENT-SPEC.md](02-DEVELOPMENT-SPEC.md) | React component tree, TypeScript interfaces, API spec, classification logic, feed assembly algorithm, CSS architecture, event tracking, migration plan, file manifest |
| [for-sale-v2-mockup.html](for-sale-v2-mockup.html) | The live HTML/CSS/JS mockup with real property data and images |

---

## Live Mockup

**URL:** https://fieldsestate.com.au/for-sale-v2.html
**Local:** `/home/fields/Fields_Orchestrator/06_Listing-Scroll-Concept/for-sale-v2-mockup.html`
**GitHub:** `Will954633/Website_Version_Feb_2026` at `public/for-sale-v2.html`

---

## Pre-Build Checklist

- [ ] Run AI editorial pipeline on all active listings: `python3 scripts/backend_enrichment/generate_property_ai_analysis.py --new-listings`
- [ ] Verify all 127 properties have `ai_analysis.status: "published"`
- [ ] Verify valuation coverage: properties with `valuation_data.confidence.reconciled_valuation` present
- [ ] Review classification thresholds with real data distribution
- [ ] Build new API endpoint: `GET /api/v1/properties/decision-feed`
- [ ] Build React components per dev spec
- [ ] Set up PostHog feature flag: `decision_feed_v1`
- [ ] Deploy behind feature flag, test on mobile
- [ ] Create matching Facebook ad variant pointing to new experience

---

## Key Metrics (Before vs After)

Track these from day one:
- Bounce rate on `/for-sale` (current baseline vs Decision Feed)
- Average cards viewed per session
- Click-through rate to individual property pages
- Time on page
- Interaction rate (quiz answers, reveals, compare opens)
- Return visits within 7 days

---

## Origin

This concept emerged from analysing a high-performing Facebook ad ($0.12 CPC, 1,237 clicks) that drove traffic to `/for-sale` with strong volume but high bounce rates. The insight: Facebook discovery users want curated judgements, not a search interface. Cross-industry patterns from TikTok, Duolingo, Robinhood, Hinge, and Spotify Discover informed the interaction design.
