# Decision Feed: Product Concept Document

**Version:** 1.0
**Date:** 28 March 2026
**Author:** Fields Estate
**Status:** Concept / Pre-Build

---

## 1. Executive Summary

The Decision Feed is a replacement for the current `/for-sale` property listings page on fieldsestate.com.au. Instead of presenting a filterable grid of property cards -- the default pattern used by every property portal in Australia -- the Decision Feed presents a curated, vertical stream of ranked market judgements. Every screen asks the user to react, not read.

The core idea: Fields Estate has already analysed every listing using comparable sales data, GPT-4 photo/floor plan analysis, and a multi-agent editorial pipeline. The current page throws that intelligence away by presenting it in the same format as Domain and realestate.com.au. The Decision Feed makes the intelligence the product.

This is not a listings page. It is a decision engine that happens to contain listings.

---

## 2. The Problem

### The Ad Performance Data

Facebook Ads are driving traffic to `/for-sale` at $0.12 CPC. Over 1,237 clicks have been delivered. The cost efficiency is strong. The conversion is not.

The problem is not reach. The problem is what happens after the click.

### The Bounce Problem

Users arrive from a Facebook ad -- scrolling passively, mid-feed, probably on a phone. They land on a directory-style listing grid: filters, pagination, 20 property cards with addresses and bedroom counts. This is the experience of every property portal. It requires intent. The user has to know what they want, apply filters, scan cards, click through, and evaluate.

Facebook discovery traffic does not have that intent. These users are curious, not searching. They saw something interesting in their feed and tapped. The listings grid asks them to shift from passive browsing to active research in one step. Most leave.

### The Intent Mismatch

The current ForSalePage (`/home/fields/Feilds_Website/01_Website/src/pages/ForSalePage/ForSalePage.tsx`) is a standard tabbed listing page with:
- Two tabs (Currently For Sale / Recently Sold)
- Filter bar (suburb, price, beds, property type)
- Paginated grid of property cards (20 per page)
- A/B test variants adding intelligence chips (Test A), category quick-picks (Test C), and feature filters (Test B)

Even the A/B test variants are refinements of the directory pattern. They add intelligence to the grid, but the grid is still the experience. The fundamental assumption -- that users arrive with search intent and will browse systematically -- is wrong for discovery traffic.

The backend API (`properties-for-sale.mjs`) already returns intelligence fields: `valuation_positioning`, `value_gap_pct`, `reconciled_valuation`, `rarity_label`, `condition_score`, `price_changed`. The data is there. The presentation wastes it.

---

## 3. The Insight

### Cross-Industry Analysis

The pattern we need does not come from property. It comes from products that solved the same problem: converting passive, browsing users into engaged, returning users.

**TikTok** replaced "here is a library of videos, search for what you want" with "here is the next thing you should watch, react to it." The feed is the product. Every screen is a decision: watch or swipe.

**Duolingo** replaced "here is a language course, study it" with "here is a 30-second challenge, answer it now." Micro-commitments accumulate into habits. Progress bars create completion motivation.

**Robinhood** replaced "here is a brokerage platform, research stocks" with "here is what moved today, tap to see why." It leads with deltas -- what changed, not what is. The movement is the hook.

**Hinge** replaced "here are profiles, browse them" with "here is one person, react to something specific about them." One idea per screen. Forced reaction. Prompts, not profiles.

**Spotify Discover Weekly** replaced "here is a music library, search it" with "here is what you did not know you wanted, trust us." Algorithmic curation builds trust through demonstrated taste.

**The Economist Espresso** replaced "here is a newspaper, read it" with "here are 5 things that matter today, we chose them for you." Curation as value. Fewer items, more confidence.

### The Pattern

Every one of these products made the same move: replace "here is information, figure it out" with "here is what matters, react to it."

The critical shift is from **browsing** (user does the work) to **reacting** (product does the work, user makes micro-decisions). This is not about dumbing down. It is about doing the analysis for the user and presenting the conclusion first, with the evidence available on demand.

### The Theory

George Loewenstein's information gap theory (1994) explains why this works. Curiosity fires when there is a gap between what you know and what you want to know. The gap has to be specific -- you need to know enough to realise you do not know something.

"127 properties for sale in Robina" creates no gap. There is nothing to be curious about.

"Renovated 4-bed with pool, $500K under the next comparable. The back fence explains it." creates a precise gap. You know the conclusion (underpriced). You do not know why (the back fence). You have to tap.

Every card in the Decision Feed is engineered to create an information gap: lead with the verdict, withhold the explanation, require a tap to close the gap.

---

## 4. The Solution

### Decision Feed

A mobile-first, vertical feed of ranked market judgements. Each screen presents one property, one insight, or one interaction. The user scrolls through a curated sequence that alternates between:

- **Property verdict cards** with tap-to-reveal explanations
- **Interactive quiz cards** that test the user's instinct against data
- **Head-to-head comparison cards** that force a choice
- **Surprise/insight cards** that reframe how the user thinks about price
- **Caution blocks** that build trust by flagging overpriced listings
- **Lead capture** positioned after trust has been earned

The feed is not a list of all properties. It is a curated selection of the most interesting ones -- typically 5-9 "best deals" out of 100+ total listings -- with the full directory available below via an "Explore All" transition.

The feed answers one question: "What should I pay attention to right now?"

---

## 5. Core UX Principles

### 5.1 Tap-to-Reveal on Every Card (Commitment Before Content)

Every property card shows a one-line verdict (the "hook") but hides the full explanation behind a "See why" button. The user must tap to see the trade-off analysis, the comparable data, and the "best for" tags.

This is not a gimmick. It is the information gap in action. The hook creates curiosity. The tap is a micro-commitment. Once tapped, the user has invested attention and is more likely to click through to the full analysis page.

The reveal section contains:
- The catch / trade-off explanation (what you give up)
- "Best for" buyer-type chips (Families near Marymount, Downsizers, WFH buyers)
- A CTA to the full property analysis page

### 5.2 Overpriced Card at Position 2 (Trust Builder)

The second card in the feed is always a "Paying a Premium" listing. This is deliberate. Showing an overpriced property second -- immediately after a best-value card -- signals that Fields Estate is not trying to sell everything. It is telling you what not to buy.

This is the single most important trust-building mechanic in the feed. Every property portal promotes listings. Fields tells you which ones are not worth it.

### 5.3 Feed Rhythm: Insight, Interaction, Compare, Surprise

The feed never shows the same card type twice in a row. The sequence follows a rhythm:

1. Property verdict card (Best Value)
2. Property verdict card (Paying a Premium -- trust builder)
3. Interactive quiz (Spot the Catch)
4. Property verdict card (Best Value -- different suburb)
5. Surprise card (Overpay Simulator)
6. Property verdict card (One of a Kind)
7. Compare card (This or That)
8. Interactive quiz (Would You Buy)
9. Property verdict card (Best Value)

This rhythm prevents feed fatigue. Each card type uses a different cognitive mode: evaluating (verdict cards), guessing (quizzes), comparing (head-to-head), and reframing (surprise cards).

### 5.4 Progress Bar Creating Completion Motivation (Zeigarnik Effect)

A sticky progress bar appears after scrolling past the hero. It tracks "X of 9 best deals viewed" and fills as the user taps "See why" on each card.

The Zeigarnik effect (1927): people remember incomplete tasks better than completed ones, and feel compelled to finish what they started. A progress bar at 4/9 creates a pull to see the remaining 5.

The progress bar only counts "best deal" cards, not quizzes or comparisons. This focuses the completion motivation on the highest-value content.

### 5.5 Lead with Deltas, Not Ranges

Every hook line leads with a delta -- how far this property sits from a reference point:

- "$500K under the next comparable"
- "~23% above adjusted comparable value"
- "~$200K below Robina's median"
- "66 sqm more than the nearest competitor"

Deltas are immediately meaningful. "$1,699,000" is a number. "$500K under the next comparable" is a story. Ranges require context and calculation. Deltas embed the context.

### 5.6 One Idea Per Screen, One Action Per Card

Each card communicates one thing:
- One verdict (Best Value / Paying a Premium / One of a Kind)
- One hook line (the single most interesting fact)
- One action (See why / Full analysis)

Cards never try to be comprehensive. They are designed to provoke a reaction, not provide complete information. The full property analysis page exists for depth. The feed exists for traction.

### 5.7 Progressive Disclosure: Verdict, Explanation, Full Analysis

Three layers of depth:
1. **Verdict + hook** (visible on scroll) -- 2-second scan
2. **Trade-off explanation + best-for tags** (tap to reveal) -- 10-second read
3. **Full property analysis page** (click through) -- 2-minute deep dive

Each layer earns the right to the next. If the verdict is not interesting, the user scrolls past -- no harm done. If the trade-off is not compelling, they do not click through. Every transition is earned.

### 5.8 Social Proof Counters

Property cards show "327 views this week" or similar counters in the top-right corner of the image. These serve two functions:

1. **Scarcity signal:** High view counts on best-value properties imply competition
2. **Validation:** Other people are looking at this too, which validates the "best value" classification

### 5.9 Copy That Provokes Reaction, Not Passive Reading

Every hook line is written to create a reaction -- surprise, disagreement, curiosity -- not to inform neutrally.

- "The back fence explains it." (What is behind the fence?)
- "Our data says you're paying ~23% above adjusted comparable value." (Is that true?)
- "Nothing else like it in Robina." (Really? Prove it.)
- "The market is telling you something." (What is it telling me?)

Neutral copy ("4 bedroom home in Burleigh Waters, recently renovated") creates no reaction. It is information without tension. Every hook line needs tension or contradiction.

---

## 6. Page Architecture

Full screen-by-screen breakdown of the mockup as built in `/home/fields/Fields_Orchestrator/drafts/for-sale-v2.html`.

### 6.1 Sticky Header

Fixed to the top of the viewport. Contains:
- Fields Estate logo (green "F" mark + wordmark)
- Search icon (right)
- Menu icon (right)

Minimal. Does not compete with feed content. `position: sticky; top: 0; z-index: 50`.

### 6.2 Dark Hero with Scarcity Framing

Full-width dark background (`#1a1a1a`) with copper accent gradient. Contains:

- **Tag:** "MARKET INTELLIGENCE" -- uppercase, copper, positions this as analysis, not listings
- **Headline:** "127 properties. Only **9** look worth your time." -- scarcity framing. The copper-highlighted "9" is the hook. Out of 127 listings, the system has identified 9 as worth attention.
- **Subtitle:** "Every listing analysed on price, condition, floor plan, and comparable sales." -- methodology signal
- **Verdict pills:** Three tappable pills showing the breakdown:
  - Green: 9 Best Value
  - Amber: 71 Full Price
  - Red: 22 Premium
- **CTA button:** "Start with the best deals" -- copper background, scrolls to first card
- **Updated line:** Date + suburb names in muted text

The hero sets the frame for everything that follows. The user is not browsing listings. They are reviewing a curated analysis. The numbers (127 total, 9 worth it) establish that Fields has done the work.

### 6.3 Progress Bar

Appears on scroll (after 400px). Sticky below the header. Contains:
- A thin green progress track that fills as deals are revealed
- Text: "X of 9 best deals viewed"

Starts hidden (`opacity: 0; transform: translateY(-100%)`) and transitions in with CSS when `visible` class is added.

### 6.4 Section Divider: "Best Deals Right Now"

Simple divider with title and count ("9 found"). Separates the hero from the feed cards. Creates a named section that the user is entering.

### 6.5 Feed Cards with Tap-to-Reveal

Each feed card contains:

**Image section** (`fc-img`):
- Full-width property photo (220px height)
- Top-left badge (Best Value / Paying a Premium / One of a Kind / Full Price)
- Top-right social proof counter ("327 views this week")
- Bottom gradient overlay for text legibility

**Body section** (`fc-body`):
- Suburb name (uppercase, muted)
- Street address (bold, 17px)
- Stats row (beds, baths, floor area, lot size)
- Hook line (`fc-hook`) -- the single most provocative claim, styled with cream background and copper left border

**Reveal section** (`fc-reveal`):
- Hidden by default (`max-height: 0; opacity: 0`)
- Animates open on tap (`max-height: 600px; opacity: 1`)
- Contains trade-off explanation and "best for" buyer-type chips

**Action buttons** (`fc-actions`):
- "See why" button (toggles reveal, changes to "Hide" when open)
- "Full analysis" button (links to property page)

### 6.6 Quiz Cards

Two types implemented in the mockup:

**Spot the Catch:**
- Dark gradient header with title and subtitle
- Question text describing a property with an apparent anomaly
- Four answer options (tap to select)
- Correct answer highlights green; wrong answer highlights red and reveals correct
- Result panel slides open with explanation and CTA to property page

**Would You Buy:**
- Same structure but with opinion-based answers (Yes / Depends / No)
- No right or wrong -- all answers reveal the Fields verdict
- Result panel shows data-driven assessment regardless of user choice

### 6.7 Compare Card

Head-to-head comparison of two properties:

- Dark header: "This or That?" with context line ("Two Burleigh Waters homes. $800K apart.")
- Side-by-side property thumbnails with addresses and prices
- Comparison grid rows: Floor Area, Condition, Catch, Price Gap
- Values highlighted green (advantage) or red (disadvantage)
- Two CTA buttons: one for each property

### 6.8 Surprise Card: Overpay Simulator

Dark background card with centered layout:
- Large number: "+$1,220/mo"
- Context: "What overpaying $200K actually costs" on a 30-year mortgage at 6.2%
- Subtext: "$439,200 extra over the life of the loan"

Reframes price differences from abstract percentages into monthly mortgage impact. Makes overpaying visceral.

### 6.9 Caution Block

Section divider: "Where to Be Careful"

Red-tinted block containing a list of properties where buyers may be overpaying:
- Red background header
- Each item shows address, days listed, and a tap-to-expand detail section
- Detail section explains the pricing gap and market signal (e.g., "67 days listed" as evidence)

This section exists purely for trust. Showing users what not to buy is more persuasive than showing them what to buy.

### 6.10 Lead Capture

Positioned after the feed content, after trust has been established:
- Headline: "Selling before you buy?"
- Body: "We'll run the same comparable-sales analysis on your property."
- Primary CTA: "Analyse my property" (copper)
- Secondary CTA: "Talk through my situation" (outline)

The lead capture only appears after the user has seen multiple analyses and trust signals. It is not at the top of the page.

### 6.11 Explore All Transition with Filter Pills

The gate between the curated feed and the full directory:
- Headline: "Explore all 127 properties"
- Subtitle: "Filter by our verdict, suburb, price, or property type."
- Filter pills: All (127), Best Value (9), Full Price (71), Premium (22), Houses, Units, Robina, Burleigh Waters, Varsity Lakes

This section acknowledges that some users want the full list. It provides a transition from the curated feed into a more traditional browsable format, but the pills still use Fields' verdict categories rather than standard filters.

### 6.12 Mini-List Grid

Below the Explore All section, a compact list of all properties:
- Horizontal layout: thumbnail (72x72), content, arrow
- Each item shows: verdict badge (colour-coded), address, suburb + beds + price, one-line hook
- Tappable to full property page

This is the "directory" view for users who want to see everything, but even here, every item leads with the Fields verdict and a hook line, not just listing data.

---

## 7. Card Types

### 7.1 Best Value Card

**Badge:** Green "BEST VALUE"
**Purpose:** Properties where the asking price sits meaningfully below the adjusted comparable range.
**Hook pattern:** Lead with the delta ("$500K under the next comparable"), then hint at the catch ("The back fence explains it").
**Reveal content:** The catch/trade-off, why the gap exists, and who this property is best for.
**Example from mockup:** 27 Seville Circuit -- renovated 4-bed with pool, $500K under comps, industrial warehouses behind the back fence.

### 7.2 Paying a Premium Card

**Badge:** Red "PAYING A PREMIUM"
**Purpose:** Properties where the asking price exceeds the adjusted comparable range by a significant margin.
**Hook pattern:** Acknowledge the quality ("9/10 condition. Beautiful home."), then state the data ("our data says you're paying ~23% above adjusted comparable value").
**Reveal content:** The pricing evidence, days on market as a market signal, and what the premium is buying.
**Example from mockup:** 7 Auriga Court -- 5 bed, 9/10 condition, but ~23% above adjusted comps and 73 days listed.

### 7.3 One of a Kind Card

**Badge:** Copper "ONE OF A KIND"
**Purpose:** Properties with unique characteristics that make direct comparable analysis difficult or where the property is genuinely rare in the market.
**Hook pattern:** Lead with the story ("Bought for $960,000. Fully rebuilt. 22m of lake frontage."), then the rarity claim ("Nothing else like it in Robina").
**Reveal content:** Why the property might be accessible despite its uniqueness, spatial or structural compromises.
**Example from mockup:** 138 Camberwell Circuit -- lakefront rebuild, 920 sqm, tight setbacks keeping price below $2,300,000.

### 7.4 Quiz: Spot the Catch

**Purpose:** Engage the user's analytical instinct. Present a property that looks like a great deal and ask them to guess what the catch is.
**Mechanics:** Four answer options, one correct. Correct answer reveals green result panel. Wrong answer reveals amber panel with the correct answer.
**Data needed:** A property with a clear, specific catch that can be framed as a multiple-choice question.
**Example from mockup:** 14 Eagle Avenue -- 5 bed, full reno, pool, $575K below competition. Catch: missing ensuite and third bathroom.

### 7.5 Quiz: Would You Buy

**Purpose:** Force the user to form an opinion before seeing the data. Creates investment in the answer.
**Mechanics:** Three opinion-based options (Yes / Depends / No). No right or wrong answer. All options reveal the same Fields verdict.
**Data needed:** A property with a clear tension between a compelling feature and a significant concern.
**Example from mockup:** 12 Beaconsfield Drive -- pool, tennis court, 1,562 sqm, price already dropped $200K. Verdict: proceed with caution (289 sqm house on 1,562 sqm lot, partial reno, 199 days listed).

### 7.6 Compare Card

**Purpose:** Make trade-offs concrete by placing two properties side by side with a direct comparison grid.
**Mechanics:** Two property thumbnails, a comparison grid (floor area, condition, catch, price gap), and two CTAs (one for each property).
**Data needed:** Two properties in the same suburb or price bracket with complementary strengths and weaknesses.
**Example from mockup:** 27 Seville Circuit ($1,699,000, industrial behind fence) vs 25 Dotterel Drive ($2,345,000+, weatherboard, no garage). Same suburb, $800K apart.

### 7.7 Surprise / Insight Card

**Purpose:** Reframe how the user thinks about price by translating abstract numbers into concrete, personal impact.
**Mechanics:** Centred dark card with a single large number and supporting context.
**Data needed:** A calculation derived from current market data (mortgage impact, opportunity cost, renovation budget equivalent).
**Example from mockup:** Overpay Simulator -- "$200K overpayment = +$1,220/month = $439,200 over the life of a 30-year loan at 6.2%."

### 7.8 Caution Item

**Purpose:** Build trust by flagging properties where the data suggests buyers may be overpaying.
**Mechanics:** Compact list item with address, days-listed badge, and tap-to-expand detail text.
**Data needed:** Properties with value_gap_pct > threshold AND high days_on_market (market confirming the data).
**Example from mockup:** 11 Kingston Heath Place -- 4 bed, 299 sqm, asking ~23% above adjusted range, 67 days listed.

### 7.9 Mini-List Item

**Purpose:** Provide a compact, scannable view of all properties for users who want the full directory.
**Mechanics:** Horizontal card with thumbnail, verdict badge, address, metadata, and one-line hook.
**Data needed:** Same as feed cards but distilled to a single hook line.

---

## 8. Feed Ordering Rules

### First 5 Items

The first 5 items in the feed must include all of the following:
1. One Best Value card
2. One Paying a Premium card (at position 2 -- the trust builder)
3. One quiz card (Spot the Catch)
4. One property card from a different suburb than position 1
5. One surprise/insight card

### Diversity Constraints

- Never the same suburb twice in a row
- Never the same card type twice in a row
- Never two Best Value cards in a row (alternate with interactions)
- Quizzes must be separated by at least 2 other cards
- The compare card must appear after at least 2 property verdict cards have been seen (so the user has context)
- The caution block appears after the main feed, before the lead capture

### Feed Sequence Template

1. Best Value card (highest value_gap_pct)
2. Paying a Premium card (trust builder)
3. Quiz: Spot the Catch
4. Best Value card (different suburb from #1)
5. Surprise card (Overpay Simulator or similar)
6. One of a Kind / interesting property
7. Compare card
8. Quiz: Would You Buy
9. Best Value card (third suburb or strongest remaining)
10. Caution block
11. Lead capture
12. Explore All transition
13. Mini-list grid

---

## 9. Copy Rules

### Verdict Labels

| Internal term | Feed label | Rationale |
|---|---|---|
| Underpriced | **Best Value** | "Underpriced" implies the seller made a mistake. "Best Value" frames it as a smart buy. |
| Fair value | **Full Price** | "Fair value" is technical. "Full Price" is what people say at a shop. |
| Overpriced | **Paying a Premium** | "Overpriced" is aggressive. "Paying a Premium" acknowledges the buyer is getting something (quality, finish) but at a cost. |

### Hook Line Rules

1. **Lead with the delta.** "$500K under the next comparable" not "$1,699,000 for a 4-bed in Burleigh Waters."
2. **Use tension or contradiction.** "9/10 condition. Beautiful home. But our data says..." The "but" is the hook.
3. **Hint at the catch without revealing it.** "The back fence explains it." Not "Industrial warehouses behind the property."
4. **Never lead with ranges or technical language.** No "adjusted comparable range of $1,928,000-$2,454,000" in the hook. That goes in the reveal.
5. **Never lead with bedroom count or address.** These are metadata, not hooks.
6. **One sentence for the verdict, one sentence for the gap.** Two sentences maximum.
7. **Use "the market" as an authority.** "The market is telling you something" not "we think this is overpriced."

### Reveal Section Rules

1. **Always start with "The catch:" or "The trade-off:" or "Why the premium:" in bold.** Immediate framing.
2. **Specific numbers, not generalities.** "$80,000-$130,000 closing those gaps" not "significant renovation cost."
3. **End with a conditional.** "The size either works for you or it doesn't." Not "this is a great option for downsizers."
4. **Comply with editorial content rules.** No advice. No predictions. Data and trade-offs only.

---

## 10. Classification Logic

### Value Classification Thresholds

Properties are classified using the `value_gap_pct` field from the valuation pipeline (stored in `valuation_data.summary.value_gap_pct`):

| Classification | value_gap_pct range | Feed label |
|---|---|---|
| Best Value | <= -0.10 (10%+ below adjusted comps) | Best Value (green) |
| Full Price | -0.10 to +0.10 | Full Price (amber) |
| Paying a Premium | > +0.10 (10%+ above adjusted comps) | Premium (red) |
| One of a Kind | No clear comps OR unique rarity_label | One of a Kind (copper) |

### Fallback for No-Price Listings

Properties listed as "Contact Agent" or with no numeric price:
- If `reconciled_valuation` exists, classify based on listing text hints vs. valuation
- If no valuation data, classify as "Full Price" (neutral default)
- Never classify a no-price listing as "Best Value" (cannot verify the claim)

### One of a Kind Override

A property is classified as "One of a Kind" regardless of value_gap_pct if:
- It has fewer than 3 valid comparables in the valuation pipeline
- It has a `rarity_label` from property_insights (e.g., "Top 2% for land size in Robina")
- It has a unique combination of features not found in any other active listing (lakefront + pool + specific finish level)

---

## 11. Success Metrics

### Primary Metrics

| Metric | Definition | Target |
|---|---|---|
| Feed completion rate | % of users who scroll past the 5th card | > 40% |
| Reveal rate | % of cards where "See why" is tapped | > 30% |
| Quiz engagement rate | % of users who answer at least one quiz | > 25% |
| Click-through to property page | % of users who click "Full analysis" on any card | > 15% |
| Time on page | Median seconds spent on the Decision Feed | > 60s |
| Bounce rate (from Facebook traffic) | % of users who leave without any interaction | < 50% |

### Secondary Metrics

| Metric | Definition | Target |
|---|---|---|
| Progress bar completion | % of users who view all 9 deals | > 10% |
| Compare card engagement | % of users who click one of the two compare CTAs | > 20% |
| Lead capture conversion | % of users who reach the lead capture and submit | > 2% |
| Return visit rate | % of users who return within 7 days | > 8% |
| Caution block expansion | % of users who tap a caution item to expand | > 15% |

### What Success Looks Like

The Decision Feed is working if:
1. Facebook discovery traffic stays on the page 3x longer than the current grid
2. Users tap "See why" on at least 2 cards per session (proving the information gap works)
3. Click-through to full property pages increases vs. the current grid
4. The lead capture at the bottom gets meaningful impressions (users scroll that far)
5. Quiz engagement proves users are willing to interact, not just scroll

---

## 12. Data Requirements

### What the Feed Needs from Each Property

| Field | Source | Current Coverage |
|---|---|---|
| `valuation_data.summary.positioning` | Valuation pipeline (step 6) | All properties with price + comps |
| `valuation_data.summary.value_gap_pct` | Valuation pipeline (step 6) | All properties with price + comps |
| `valuation_data.confidence.reconciled_valuation` | Valuation pipeline (step 6) | All properties with price + comps |
| `ai_analysis` (headline, hook, trade-off) | AI editorial pipeline | ~60-70% of active listings |
| `property_valuation_data.condition_summary.overall_score` | GPT-4 photo analysis (step 105) | Most properties with photos |
| `property_insights` (rarity_label, percentiles) | Enrichment pipeline (steps 11-19) | Most enriched properties |
| `days_on_domain` / `days_on_market` | Scraper (step 101) | All active listings |
| Photo URLs | Blob storage (step 110) or scraped | All active listings |
| Floor area, lot size, beds, baths | Scraped + enriched | All active listings |

### What Needs to Happen Before Build

1. **AI editorial coverage must reach 90%+ of active listings.** The feed depends on hook lines and trade-off explanations. Properties without `ai_analysis` cannot populate feed cards meaningfully. Run `generate_property_ai_analysis.py --backfill` to close the gap.

2. **Feed-specific copy fields.** The current `ai_analysis` generates headline, sub-headline, and analysis paragraph for the property page. The Decision Feed needs:
   - `feed_hook` -- the one-line provocative claim (max 120 chars)
   - `feed_catch` -- the trade-off explanation (2-3 sentences)
   - `feed_best_for` -- array of buyer-type tags
   - `feed_quiz_eligible` -- boolean, whether this property has a clear enough catch for a quiz question
   - `feed_quiz_question` / `feed_quiz_options` / `feed_quiz_answer` -- if quiz-eligible

   These could be added as a new section in the AI editorial pipeline output, or generated as a separate lightweight pass.

3. **View count data.** The mockup shows "327 views this week" on property cards. This requires either:
   - PostHog event aggregation (property page views per property per week)
   - A simple counter increment on each property page load, stored on the document

4. **Compare pair selection.** An algorithm or manual curation step to identify good compare pairs: same suburb or price bracket, complementary strengths/weaknesses. Could be generated by the AI editorial pipeline as a "compare_candidates" field.

5. **Overpay Simulator calculation.** A simple mortgage calculator function: given an overpay amount, current interest rate, and loan term, compute the monthly and lifetime cost difference. This is a frontend calculation, not a data dependency.

---

## 13. Live Mockup Reference

- **Live URL:** https://fieldsestate.com.au/for-sale-v2.html
- **Local file:** `/home/fields/Fields_Orchestrator/drafts/for-sale-v2.html`
- **Type:** Static HTML mockup with inline CSS and vanilla JavaScript
- **Status:** Visual concept only. All data is hardcoded. No backend integration.
- **Properties featured:** 27 Seville Circuit (Burleigh Waters), 7 Auriga Court (Robina), 14 Eagle Avenue (Burleigh Waters), 1 Saint Andrews Glade (Robina), 138 Camberwell Circuit (Robina), 25 Dotterel Drive (Burleigh Waters), 1/62 Bayswater Avenue (Varsity Lakes), 12 Beaconsfield Drive (Robina)
- **Images:** Mix of Azure Blob Storage URLs (Fields-hosted) and Domain.com.au bucket URLs

The mockup is mobile-optimised (`max-scale=1.0, user-scalable=no`) and designed for a phone-width viewport. All interactions (tap-to-reveal, quiz answers, progress bar) are functional in the static HTML via vanilla JavaScript.
