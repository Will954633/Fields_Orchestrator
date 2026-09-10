<!--
DRAFT v2 for Will's review — NOT published. 2026-09-09.
v2: rewritten for general-public register per Will — stats explained in plain words
at point of use, jargon removed, detail moved to "How we did this" box at the end.
Title: We Compared 578 Renovated and Unrenovated House Sales. The Suburb Changes Everything.
Excerpt: Fully renovated houses sell for more in Robina, Varsity Lakes and Burleigh
Waters — but how much more depends on the suburb. And half-finished renovations,
the data shows, add nothing at all.
Suggested tags: Market Research, Robina, Varsity Lakes, Burleigh Waters, Seller Data
Publish via: python3 scripts/push-ghost-draft.py --title "..." --md-file <this file>
   (strip this comment block first)
Sources: 16_Valuation/Renovation_Premium/results_24m.json, results_12m.json;
         16_Valuation/Market_Regime_Mix/results_regime_mix.json
Editorial checks: no advice ✓ no predictions ✓ no single-property valuation ✓
  exact figures ✓ limitations stated ✓ scrape sources unnamed ✓ forbidden words absent ✓
-->

# We Compared 578 Renovated and Unrenovated House Sales. The Suburb Changes Everything.

Every seller with a dated kitchen eventually asks the same question: if we renovated
before selling, would we get the money back?

It's usually answered with opinion. We answered it with sale records — 578 house sales
across Robina, Varsity Lakes and Burleigh Waters over the two years to September 2026.
The answer turns out to depend, more than anything else, on which suburb the house is in.

## First, a trap

The obvious way to test this is to work out what each home sold for per square metre of
floor space, then compare renovated homes with original ones.

We did that first, and it says something odd: in Robina and Varsity Lakes, renovated
homes appear to sell for *less* per square metre than untouched ones.

Odd — and wrong. Here's the catch. Big homes always sell for less per square metre than
small ones (a house twice the size doesn't cost twice as much). And big homes are more
likely to have been renovated. Stack those two facts together and renovated homes look
like poor value per square metre even when buyers are paying good money for them. The
comparison isn't measuring renovation at all. It's measuring house size.

So we compared like with like instead. Every renovated home was measured against
unrenovated homes of similar size, on similar land, with the same number of bedrooms,
selling around the same time, in the same suburb. Closest thing the real world offers
to a fair test.

## What a full renovation actually sold for

| Suburb | Fully renovated homes sold for | On a typical house, that's roughly |
|---|---|---|
| Burleigh Waters | 16% to 23% more | $300,000 to $420,000 |
| Robina | about 12% more | $175,000 |
| Varsity Lakes | maybe 7% more — too few sales to be sure | $93,000 |

*"Typical house" here means the middle sale in our data — half sold for more, half for
less: $1,845,000 in Burleigh Waters, $1,491,944 in Robina, $1,351,000 in Varsity Lakes.*

A note on those figures, because honesty matters more to us than tidy numbers. No study
of real sales can nail a premium to the decimal point — there's always a margin around
it. Robina's margin is fairly tight: the true premium is very likely somewhere between
6% and 18%, with 12% the best estimate. Burleigh Waters sits confidently in positive
territory too. Varsity Lakes had only 26 fully renovated sales in the window — not
enough to be certain of anything, which is why we say "maybe."

One thing the data *is* emphatic about: the gap between suburbs is real. Burleigh
Waters rewards a full renovation by around 10 percentage points more than Robina, and
that held every way we tested it.

Is the premium bigger than the cost of the renovation? That's the question, and sale
records can't answer it — they never show what an owner spent. What they show is the
size of the prize on offer. In Burleigh Waters, it's roughly twice Robina's.

## Half-finished is worth the same as untouched

This one surprised us more.

Our records grade each home's condition from its sale photos — original, cosmetically
updated, partially renovated, fully renovated. In all three suburbs, the homes in the
middle grades sold for about the same as original homes. All of the premium, in every
suburb, sits in one grade: fully renovated.

The market pays for finished. New floors under an old kitchen, one bathroom done and
one dated — homes like that priced as if nobody had touched them.

## No single room carries it

We also checked the rooms one at a time. Does a renovated kitchen, by itself, lift the
price? A renovated bathroom? New floors?

No, no and no — not on their own. What moved the price was the overall finish of the
whole home. Buyers in these suburbs responded to the complete picture, not to any one
room in it.

## Why Burleigh Waters is different

To understand the suburb gap, we went deeper into history: 8,647 house sales across the
three suburbs from 2015 to 2026 — a stretch that includes the cheap-money boom of
2020–21 and the fastest interest-rate rises in a generation through 2022–23.

In each year, we counted how many homes sold for more than one-and-a-half times that
suburb's typical price — call it the premium end of the market.

In Robina, the premium end barely moved in a decade: around 6 to 8 sales in every
hundred, in every rate environment. In Burleigh Waters it grew through *all* of them —
from about 9 in a hundred before 2020, to 10 during the rate rises, to 14 in a hundred
since 2024. When the cost of borrowing roughly quadrupled, Burleigh Waters' top end
didn't pause. It grew.

A premium market that shrugs off interest rates is a market where many buyers aren't
borrowing. And that fits the renovation numbers: buyers with the means to pay for a
finished home and no appetite for managing tradies themselves. Robina tells the
opposite story — a family market clustered around its middle price in good times and
bad, where the data suggests a renovated interior competes with everything else the
same budget could buy: the bigger yard, the pool, the extra bedroom.

## What this data doesn't say

Worth being upfront about four things. These figures are about sale prices, not
profits — nothing here shows what any renovation cost. Homes that get fully renovated
may be better homes to begin with, so some of the premium likely belongs to the house,
not the work. Condition was graded from sale photographs, which isn't perfect — though
grading mistakes would shrink these premiums, not inflate them. And waterfront homes, a
market of their own, were left out entirely.

---

**How we did this.** Fields analysis of 578 house sales in Robina, Varsity Lakes and
Burleigh Waters (24 months to September 2026), each home's renovation state classified
from its listing photography, compared with size, land, bedrooms, bathrooms, water
proximity and time of sale held constant — using three independent methods that all
agreed. Suburb history: 8,647 house sale records, 2015–2026. Waterfront properties
excluded throughout.
