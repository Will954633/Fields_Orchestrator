<!--
DRAFT for Will's review — NOT published. 2026-09-09.
Title: We Compared 578 Renovated and Unrenovated House Sales. The Suburb Changes Everything.
Excerpt: Fully renovated houses sell at a premium in Robina, Varsity Lakes and Burleigh
Waters — but the size of that premium varies so much by suburb that it changes what a
renovation is worth. Half-finished renovations, the data shows, are worth nothing at all.
Suggested tags: Market Research, Robina, Varsity Lakes, Burleigh Waters, Seller Data
Publish via: python3 scripts/push-ghost-draft.py --title "..." --md-file <this file>
   (strip this comment block first)
Sources: 16_Valuation/Renovation_Premium/results_24m.json, results_12m.json;
         16_Valuation/Market_Regime_Mix/results_regime_mix.json
Editorial checks: no advice ✓ no predictions ✓ no single-property valuation ✓
  exact figures ✓ limitations stated ✓ scrape sources unnamed ✓ forbidden words absent ✓
-->

# We Compared 578 Renovated and Unrenovated House Sales. The Suburb Changes Everything.

Every seller with a dated kitchen eventually asks the same question: would renovating
before selling pay for itself? It is usually answered with opinion. We answered it with
sale records — 578 house sales across Robina, Varsity Lakes and Burleigh Waters over the
24 months to September 2026 — and the result depends, more than anything else, on which
suburb the house is in.

## The trap in the obvious comparison

The obvious way to test this is to divide sale prices by floor area and compare renovated
homes with original ones. We did that first, and it produces a strange result: in Robina
and Varsity Lakes, renovated homes appear to sell for *less* per square metre than
original-condition homes.

That number is real, and it is misleading. Larger homes sell for less per square metre —
a 350-square-metre house does not cost twice as much as a 175-square-metre one — and
larger homes are also more likely to have been renovated. Put those two facts together
and renovated homes look cheap per square metre even when they are commanding a premium.
The raw comparison measures house size, not renovation.

So we controlled for it. Each home's renovation state was classified from its sale
listing photographs by an AI vision model into six tiers, from original through
cosmetically updated and partially renovated to fully renovated. We then compared like
with like — same floor area, same land size, same bedrooms and bathrooms, same proximity
to water, same quarter of sale — three separate ways: a stratified comparison within
size brackets, a regression across all 578 sales, and a matched-pairs test that put each
fully renovated sale next to its closest unrenovated twins and measured the gap.
Waterfront properties were excluded throughout. All three methods pointed the same way.

## What a full renovation sold for

| Suburb | Price premium, fully renovated vs comparable unrenovated | On this study's median house |
|---|---|---|
| Burleigh Waters | +16.1% (regression) to +22.9% (matched twins) | $297,000 to $423,000 on $1,845,000 |
| Robina | +11.7% | $175,000 on $1,491,944 |
| Varsity Lakes | +6.9% — statistically inconclusive | $93,000 on $1,351,000 |

*Medians are of the 578 sales studied (non-waterfront houses with a renovation
classification), 24 months to September 2026.*

The statistical ranges matter. The Burleigh Waters regression estimate of +16.1% carries
an uncertainty band of +4.2% to +29.5%; Robina's +11.7% sits in a tighter band of +5.7%
to +18.0%. Varsity Lakes had only 26 fully renovated sales in the window — too few to
pin down, which is why we report its +6.9% as inconclusive rather than as a finding.

The gap between suburbs, however, is not noise: Burleigh Waters' renovation premium
exceeds Robina's by roughly 10 percentage points, and that difference held across every
method and every time window we tested.

Whether a premium of that size exceeds the cost of achieving it depends on the
renovation — a question sale data cannot answer, because the records never show what an
owner spent. What the data does show is the size of the prize each market offers, and
that Burleigh Waters offers roughly twice Robina's.

## Half-finished is worth the same as untouched

The second finding surprised us more than the first. Across all three suburbs, homes
classified as cosmetically updated or partially renovated sold no differently from
original-condition homes. Every measured premium sits in one tier: fully renovated.

The market, in other words, pays for finished. A home part-way through its
transformation — new floors under an old kitchen, one bathroom done and one dated —
priced like a home nobody had touched.

## No single room carries it

We also tested the rooms individually. Controlling for a home's overall level of finish,
the presence of a renovated kitchen on its own carried no detectable premium. Nor did
renovated bathrooms, nor new flooring. What predicted price was the overall modernity of
the home — worth between 4.4% and 5.5% per point on our ten-point scale, in every
suburb. Buyers in these markets responded to the whole finished state of a house, not to
any single feature within it.

## Why Burleigh Waters is different

The transaction record offers an explanation. We examined 8,647 house sales across the
three suburbs from 2015 to 2026, through four distinct interest-rate environments, and
tracked the share of each suburb's sales that closed above 1.5 times its median that
year.

In Robina, that share barely moved in a decade — around 6% to 8% in every rate
environment. In Burleigh Waters it climbed through every one of them: 9.5% of sales
before 2020, 10.4% during the 2022–2023 rate rises — the fastest tightening cycle in a
generation — and 14.3% since 2024. Burleigh Waters' top end kept transacting, and kept
growing, straight through the period when borrowed money roughly quadrupled in cost.

A premium segment that does not flinch at interest rates is a segment where a
significant share of buyers are not borrowing. That is consistent with what the
renovation numbers show: a buyer pool with the means to pay for a finished product, and
a preference for not managing a renovation themselves. Robina's flat mix tells the
opposite story — a family market concentrated near its median in every rate environment,
where the data suggests buyers weigh a renovated interior against everything else the
same budget could hold.

## What this data does not say

Four limits worth stating plainly. First, a price premium is not a profit — these
figures say nothing about what any renovation cost, only what renovated homes sold for.
Second, homes that get fully renovated may differ from those that don't in ways we
cannot fully measure; some part of the premium likely belongs to the houses themselves,
not the work done to them. Third, renovation state was classified from listing
photographs, which is imperfect — classification errors would, if anything, shrink the
measured premiums rather than inflate them. Fourth, Varsity Lakes' sample is small, and
waterfront homes — a distinct market — are excluded throughout.

---

*Source: Fields analysis of 578 house sales in Robina, Varsity Lakes and Burleigh Waters
(24 months to September 2026; renovation state classified from listing photography;
premiums estimated with floor area, land size, bedrooms, bathrooms, water proximity and
quarter of sale held constant) and 8,647 house sale records 2015–2026. Statistical
ranges are 95% intervals. Waterfront properties excluded.*
