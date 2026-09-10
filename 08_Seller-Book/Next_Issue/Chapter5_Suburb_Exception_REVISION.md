# Chapter 5 revision — "The Suburb Exception" (pp. 58–59)

**Status:** Draft replacement copy for next issue. 2026-09-09.

## Editor's note — what changed and why

The current edition states that fully renovated properties in Robina and Varsity Lakes
showed **lower** price per square metre than original-condition homes, with Burleigh
Waters (+14%) as the exception — and flags a possible floor-area confounder with
"further analysis is underway."

That analysis is now done (`16_Valuation/Renovation_Premium/renovation_premium_study.py`,
578 sold houses, 24-month window, three independent methods). **The confounder was the
whole story.** Controlled for floor area, land, beds/baths, water class and quarter of
sale, fully renovated homes sell at a **premium in all three suburbs** — Robina +11.7%,
Burleigh Waters +16.1% (matched-twins method: +22.9%), Varsity Lakes +6.9% (small sample,
not statistically significant). The negative Robina figure must not survive into the next
issue. What DOES survive — strengthened — is the suburb *difference* (BW rewards
renovation ~10 points more than Robina, p=0.002), the buyer-demographic mechanism, and
the practical advice, which now rests on cost arithmetic instead of a false negative.

Two new findings strengthen the chapter:
1. **Only full renovation is priced.** Cosmetic and partial renovation sell like original.
2. **No single item carries the premium** — buyers price the overall finished state, not
   the presence of a renovated kitchen or bathroom in isolation.

A separate mix study (8,647 sales 2015–2026, `16_Valuation/Market_Regime_Mix/`) adds
independent support for the mechanism: Burleigh Waters' premium tier (sales above 1.5×
the suburb median) has grown through every credit regime — including the 2022–23 rate
shock — from 9.5% to 14.3% of sales, while Robina's mix is static across a decade.
Cash-driven premium demand in BW is visible in the transaction record itself.

---

## Replacement text (book voice)

**The suburb exception.** In the first edition of this book I reported a finding that
renovated homes in Robina and Varsity Lakes appeared to sell for *less* per square metre
than original homes — and I flagged, honestly, that a confounder might be hiding in the
numbers: bigger homes have a lower price per square metre, and bigger homes are more
often renovated. I promised further analysis.

Here it is, and the confounder was real. When you compare like with like — same floor
area, same land, same bedrooms, same proximity to water, same quarter of sale — fully
renovated homes sell at a premium in every one of our three suburbs. What differs, and
differs sharply, is how much:

- **Burleigh Waters: roughly +16 to +23 per cent.** Across three separate methods, the
  strongest and most consistent renovation premium on the southern Gold Coast.
- **Robina: roughly +12 per cent.**
- **Varsity Lakes: roughly +7 per cent**, though with fewer renovated sales to measure,
  this number carries the widest uncertainty.

So does renovating before sale make money? Now the arithmetic matters. A 12 per cent
premium on a $1,400,000 Robina home is about $164,000 — and a genuine full renovation
of a family home can cost $100,000 to $150,000 or more before you count the months it
takes and the risk that the market moves underneath you. In Robina, a pre-sale
renovation is a break-even proposition at best. In Burleigh Waters, a 16 to 23 per cent
premium on a $1,700,000 home is $270,000 to $390,000 — the one market in our patch
where renovating before you sell can plausibly turn a profit.

The data adds two warnings for anyone tempted by the middle path. First, **only full
renovation is priced.** Homes our analysis classed as cosmetically updated or partially
renovated sold no differently from original homes. The market pays for *finished*, not
for *started* — a $50,000 half-measure recovers approximately nothing. Second, **no
single room carries the premium.** A renovated kitchen inside an otherwise tired house
was not detectably rewarded in any suburb. Buyers respond to the overall state of
completion, which is precisely why the cheap, whole-of-home actions in this chapter —
paint, presentation, light — punch so far above their cost.

Why does Burleigh Waters behave differently? The buyer pool. Burleigh Waters attracts
established professionals and downsizers — often cash buyers — paying for the beach
lifestyle and expecting turnkey quality; they will pay a premium not to project-manage
a renovation. Our transaction records bear this out independently: the share of
Burleigh Waters sales above 1.5 times the suburb median has grown through every
interest-rate environment since 2015, including the fastest rate-hiking cycle in a
generation. Money that doesn't need borrowing doesn't blink. Robina and Varsity Lakes
are family markets: buyers are stretched by the cost of getting in, plan to renovate to
their own taste in time, and will choose a bigger yard or a pool over someone else's
new benchtops. At these price points, over-capitalising on a pre-sale renovation
remains a genuine risk — not because renovation reduces value, as the raw figures once
suggested, but because the premium it earns is roughly the price of achieving it.

---

## Source figures (do not print; for fact-check)

| Claim in text | Source |
|---|---|
| Robina +11.7% [5.7, 18.0] p=.0001; BW +16.1% [4.2, 29.5] p=.007; VL +6.9% [−0.4, 14.8] p=.065 | `16_Valuation/Renovation_Premium/results_24m.json` leg2_hedonic |
| BW matched-twins +22.9% [11.4, 37.7] | same, leg3_matched |
| BW–Robina gap ~10pp, p=0.002 | same, suburb_interaction |
| Cosmetic/partial ≈ original (≈0%, ns, all suburbs) | same, leg2 tier ladder |
| No single item priced; modern_features_score +4.4–5.5%/pt | same, secondary_items |
| BW premium-tier share 9.5%→14.3% across regimes; Robina static | `16_Valuation/Market_Regime_Mix/results_regime_mix.json` |
| n=578 sold houses, 24-mo window; 8,647 sales 2015–2026 | both results files |
| $ arithmetic | medians: Robina ~$1.4M, BW ~$1.7M (book p.58 figures, still current) |

Caveats already embedded in the text: premium ≠ ROI (cost unobserved — handled via the
break-even framing); Varsity uncertainty named; selection bias covered by "can plausibly"
hedging. Editorial rules: this is the seller book (advice permitted), NOT website/FB copy —
do not lift sentences from here into public channels without the no-advice rewrite.
