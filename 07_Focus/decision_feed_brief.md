# Decision Feed — Active Test Brief

**Page:** https://fieldsestate.com.au/for-sale-v2
**Status:** Live, Facebook ad test running (started 31 March 2026)
**Priority:** HIGH — this is the primary buyer discovery surface being tested

## What It Is

A vertical scroll feed of curated property cards with opinionated market judgements. Replaces the browse-all grid at `/for-sale` with a one-property-at-a-time experience.

Each card has:
- **Hero photo** with hook headline overlay (opinion-led, e.g. "Bought for $551K. Renovated to 9/10. Still priced under $2M")
- **Stats row** (bed/bath/car/sqm/days listed)
- **Price row** with estimated range from comparable sales
- **Context pill** — "New this week", "Price dropped", or scarcity signal ("1 of 3 under $2m")
- **Sub-headline** — evidence line bridging the hook to the tap (e.g. "Comparable sales cluster around $1.8M–$1.95M, but the collector road and compact bedrooms are doing the heavy lifting on that discount")
- **"See why" button** — tap to reveal trade-off detail + "Best for" buyer persona chips
- **"Full analysis" button** — links to property page with full editorial + valuation

Interactive elements interspersed every 3 cards: quiz cards ("Spot the Catch"), compare cards (side-by-side), surprise cards (overpay simulator).

**Sticky suburb filter** at top: All suburbs | Burleigh Waters | Robina | Varsity Lakes

## The Test

**Hypothesis:** Discovery traffic from Facebook converts better when it lands on a curated, opinionated feed than a directory-style grid.

**Facebook ads:** Low-volume test driving traffic to `/for-sale-v2` with UTM params:
- `utm_source=facebook`
- `utm_medium=paid`
- `utm_campaign=decision_feed_test`

**Control comparison:** Existing `/for-sale` grid page (same traffic source, historical data)

## What To Measure (PostHog)

All events carry UTM attribution. Filter by `utm_campaign = decision_feed_test` for ad traffic only.

| Metric | Event(s) | Target |
|--------|----------|--------|
| Reveal rate | `feed_card_reveal` / `feed_card_impression` | >30% |
| Click-through rate | `feed_card_click` / `feed_card_impression` | >15% |
| Feed depth | max `feed_position` on `feed_card_impression` | >5 cards |
| Feed completion | `scroll_depth` at 75%+ | >40% |
| Quiz engagement | `quiz_answer` count | >25% of visitors |
| Time on page | `time_on_page` at 60s+ | >50% of visitors |
| Bounce rate | sessions with only `decision_feed_view` | <50% |

## Data Available

- `metrics/decision_feed_7d.json` — full PostHog engagement funnel, attribution, depth, scroll, time
- `screenshots/decision_feed.png` — current visual state of the page
- `screenshots/decision_feed_page_text.txt` — full rendered text content

## Agent Responsibilities

- **Growth Lead:** Analyse Facebook ad performance vs cost. Compare decision feed engagement to /for-sale historical. Recommend budget scaling or creative changes.
- **Product Lead:** Review UX metrics (reveal rate, feed depth, drop-off points). Identify which card types drive engagement. Propose iteration priorities.
- **Engineering Lead:** Monitor page performance (load times, errors). Flag any data quality issues (missing photos, stale prices, broken cards).

## Design Rationale

Based on Economist Espresso model (opinion-led cards, tap for depth), Hinge "Most Compatible" (single recommendation with explanation = 2x engagement), and Loewenstein information gap theory (curiosity fires when gap is sized correctly). See `06_Listing-Scroll-Concept/01-PRODUCT-CONCEPT.md` for full product theory.
