<!--
DRAFT v5 for Will's review — NOT published. 2026-09-10.
v5: full revision per Will's editorial review — principal finding moved into the lede,
new title, "no measurable premium" precision, BW explanation reframed as hypothesis,
regime section condensed to 3 paragraphs, consumer-protection note under the table,
3-panel photo strips (kitchen/bathroom/living per home), sample-size language corrected,
methods named, new closing line.
Title: Renovated Homes Sell for More — but the Suburb Changes How Much
Excerpt: Fully renovated houses sold for more in Robina, Varsity Lakes and Burleigh
Waters — but the premium varied sharply between suburbs. Across 578 sales, we also
found no measurable premium for homes renovated only part-way. The market rewarded
the completed result, not individual improvements.
Suggested tags: Market Research, Robina, Varsity Lakes, Burleigh Waters, Seller Data
Publish via: python3 scripts/push-ghost-draft.py --title "..." --md-file <this file>
   (strip this comment block first)
Sources: 16_Valuation/Renovation_Premium/results_24m.json, results_12m.json;
         16_Valuation/Market_Regime_Mix/results_regime_mix.json
Editorial checks: no advice ✓ no predictions ✓ no single-property valuation ✓
  exact figures ✓ limitations stated ✓ scrape sources unnamed ✓ forbidden words absent ✓
Gallery: 3-panel strips (kitchen/bathroom/living) per graded home, labels burned in,
  NO addresses; blob property-images/articles/renovation-grades/home-*-strip.jpg;
  source docs 690bd7f08b8f546592609486, 690bd7df8b8f5465926031dd, 690bd7de8b8f546592602c60.
  All panels visually verified against grades 2026-09-10.
Chart: article-charts/renovation-premium.html (iframe, ?v=20260910) + .png noscript.
-->

# Renovated Homes Sell for More — but the Suburb Changes How Much

Every seller with a dated kitchen eventually asks the same question: if we renovated
before selling, would we get the money back?

We analysed 578 house sales across Robina, Varsity Lakes and Burleigh Waters. Two
findings stood out. Fully renovated homes sold for substantially more — but the premium
varied sharply by suburb. Homes renovated only part-way, meanwhile, sold for about the
same as homes left in original condition.

Here is what the records show, and how we checked it.

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
selling around the same time, in the same suburb. It is the closest the real world
offers to a fair comparison.

## What a full renovation actually sold for

| Suburb | Fully renovated homes sold for | On a typical house, that's roughly |
|---|---|---|
| Burleigh Waters | 16% to 23% more | $300,000 to $420,000 |
| Robina | about 12% more | $175,000 |
| Varsity Lakes | maybe 7% more — too imprecise to be sure | $93,000 |

*"Typical house" here means the middle sale in our data — half sold for more, half for
less: $1,845,000 in Burleigh Waters, $1,491,944 in Robina, $1,351,000 in Varsity Lakes.*

**These figures are estimated differences in sale price — not renovation profits.** A
$300,000 sale-price premium does not mean an owner made $300,000 by renovating, because
the data does not show the cost of the work or what the same house would otherwise have
sold for.

<iframe src="https://blobs.fieldsestate.com.au/article-charts/renovation-premium.html?v=20260910"
        scrolling="no" style="width:100%;aspect-ratio:820/470;border:0;"
        title="What a full renovation adds to the sale price — interval chart by suburb"></iframe>
<noscript><img src="https://blobs.fieldsestate.com.au/article-charts/renovation-premium.png?v=20260910"
     alt="Chart of the estimated renovation premium by suburb with uncertainty ranges"
     style="width:100%;height:auto;"></noscript>

A note on those figures. No study of real sales can nail a premium to the decimal
point — there's always a margin around it, and the bars in the chart show exactly that:
the dot is the best estimate, the bar is where the true premium very likely sits.
Robina's bar is fairly tight — very likely between 6% and 18%, with 12% the best
estimate. Burleigh Waters sits confidently in positive territory too. Varsity Lakes had
only 26 fully renovated sales, leaving the estimate too imprecise for a confident
conclusion — which is why its bar is drawn faded and we say "maybe."

The suburb difference itself was consistent: across all three comparison methods we
used, Burleigh Waters' estimated premium remained about 10 percentage points higher
than Robina's.

Is the premium bigger than the cost of the renovation? That's the question, and sale
records can't answer it — they never show what an owner spent. What they show is the
additional sale price associated with a fully renovated home. In Burleigh Waters, that
figure is roughly twice Robina's.

## Partial renovations earned no measurable premium

This finding surprised us more than the suburb gap.

Our records grade each home's condition from its sale photos — original, cosmetically
updated, partially renovated, fully renovated. Across all three suburbs, we found no
reliable price premium for homes in the middle grades compared with original homes. In
price terms, they behaved much more like original homes than fully renovated ones.
Every measurable premium, in every suburb, sat in one grade: fully renovated.

The market appears to pay for finished. The measurable premium emerged only when the
entire home was renovated — new floors under an old kitchen, or one bathroom done and
one dated, showed no detectable reward.

## See the grading for yourself

Fair question at this point: how good is an AI model at judging a home from photos?
You can check its work. Below are three real Robina homes from the sales we studied,
each shown across three rooms, with the grade our model gave the whole home.

One thing to know first: **"original" describes whether the home has been substantially
renovated — not whether it is clean, functional or well maintained.** That is why an
original home can still score reasonably on condition. The grades measure completeness
of renovation; the 0–10 scores measure state of repair.

![Three rooms of an original-condition Robina home: as-built kitchen, bathroom and living area](https://blobs.fieldsestate.com.au/property-images/articles/renovation-grades/home-original-strip.jpg)

*Original: everything works and the home is well kept — but the kitchen cabinetry,
bathroom and finishes are as built. Sold May 2026.*

![Three rooms of a partially renovated Robina home: updated kitchen, retiled family room, original carpeted lounge](https://blobs.fieldsestate.com.au/property-images/articles/renovation-grades/home-partially-renovated-strip.jpg)

*Partially renovated — and you can see the "partial" in one glance: the kitchen has new
stone benchtops and the family room new tiles, while the lounge keeps its original
carpet and wood heater. The work stopped part-way. Sold May 2026.*

![Three rooms of a fully renovated Robina home: stone-island kitchen, frameless-glass bathroom, modern open living](https://blobs.fieldsestate.com.au/property-images/articles/renovation-grades/home-fully-renovated-strip.jpg)

*Fully renovated: stone island bench and pendant lighting in the kitchen, frameless
glass and floor-to-ceiling tiles in the bathroom, nothing left from the original home.
Sold November 2025.*

Notice the middle home scored a solid 7 out of 10 for overall condition — genuinely
good work where it was done — yet it still sold in a grade for which we found no
measurable premium. Condition and completeness are different things, and the premium
followed completeness.

## No single room carried it

We also checked the rooms one at a time. Does a renovated kitchen, by itself, lift the
price? A renovated bathroom? New floors?

We found no reliable premium for any one of them on its own. What moved the price was
the overall finish of the whole home. Buyers in these suburbs responded to the complete
picture, not to any one room in it.

## Why might Burleigh Waters be different?

The sales records cannot tell us why buyers paid a larger renovation premium in
Burleigh Waters, but the suburb's upper price segment provides a clue.

Across 8,647 sales since 2015, homes selling above one-and-a-half times the suburb's
typical price became steadily more common in Burleigh Waters — from about 9 in every
hundred sales before 2020 to about 14 in every hundred since 2024 — and that share held
up even through the 2022–2023 interest-rate rises, the fastest tightening in a
generation. Robina's share stayed relatively stable, around 6 to 8 in a hundred, in
every rate environment.

That does not tell us whether these buyers were paying cash, borrowing less, earning
more or simply prioritising Burleigh Waters more highly. But it does show the suburb's
premium segment remained unusually resilient as borrowing costs rose. One possible
explanation is that more buyers at this end of the Burleigh Waters market have both the
means and the preference to pay for a completed home rather than manage a renovation
themselves. The sales records cannot prove that motivation — but it is consistent with
the larger renovation premium we observed.

## What this data doesn't say

Worth being upfront about four things. These figures are about sale prices, not
profits — nothing here shows what any renovation cost. Homes that get fully renovated
may be better homes to begin with, so some of the premium likely belongs to the house,
not the work. Condition was graded from sale photographs, which isn't perfect — random
grading mistakes would generally blur the difference between groups and pull the
estimated premiums toward zero, although systematic grading errors could still affect
the results. And waterfront homes, a market of their own, were left out entirely.

The conclusion is not that every owner should renovate. It is that buyers distinguished
sharply between a home that was completely finished and one where the work had merely
begun — and the amount they paid for that difference depended heavily on the suburb.

---

**How we did this.** Fields analysis of 578 house sales in Robina, Varsity Lakes and
Burleigh Waters (24 months to September 2026), each home's renovation state classified
from its listing photography. We estimated the premium three independent ways: a
like-for-like comparison within size brackets; a statistical model holding floor area,
land size, bedrooms, bathrooms, water proximity and quarter of sale constant; and a
matched-pairs test putting each fully renovated sale beside its closest unrenovated
twins. All three pointed the same way. Suburb history: 8,647 house sale records,
2015–2026. Waterfront properties excluded throughout.
