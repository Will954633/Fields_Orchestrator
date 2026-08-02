# Q2 2026 — Evidence Pack

**Data closed:** 1 August 2026 · **Source:** `Gold_Coast.precomputed_indexed_prices` + `precomputed_market_charts` (the live source of truth behind `/market-intelligence/:suburb`)
**Basis:** Domain ∪ onthehouse transaction union, houses only, deduped for contract-vs-settlement double counting.

Everything here is what the website now serves. Nothing in this file is computed separately for the report — that separation is what produced the errors in the published Q2 issue.

---

## The publishable numbers

| Suburb | 12-month median | 90% CI | n | YoY |
|---|---|---|---|---|
| **Burleigh Waters** | **$1,925,000** | $1,855,550–$2,000,000 (±3.9%) | 167 | **+6.9%** |
| **Robina** | **$1,490,000** | $1,449,000–$1,550,000 (±4.0%) | 265 | **+5.3%** |
| **Varsity Lakes** | **$1,400,000** | $1,380,000–$1,450,000 (±3.6%) | 111 | **+10.2%** |

External check: realestate.com.au publishes Burleigh Waters at **$1,910,000 on 195 sales** over the same window and methodology. We are within **0.8%** on the median; our 167 priced sales plus ~32 price-withheld ≈ 199 against their 195.

## Volume — union basis, complete quarters only

| Suburb | Q4 2025 | Q1 2026 | Q2 2026 | read |
|---|---|---|---|---|
| Robina | 71 | 71 | **51** | −28% off Q1 |
| Burleigh Waters | 41 | 44 | **42** | **flat** |
| Varsity Lakes | 45 | 31 | **17** | **−62%** |

Q3 2026 (8 / 12 / 7) is in progress and must not be charted as complete. **Q2 2026 is still filling in** as settlements register, so all three are floors.

The series starts at Q4 2025 — the first quarter onthehouse covers end to end. Earlier volume is Domain-recorded only, undercounts by roughly 25–55%, and crosses two composition shifts (the sold-listing feed arriving ~Q4 2024; property timelines going stale ~Q4 2025). **Do not publish a long-run volume chart.**

## What we may NOT say

- **No quarter-on-quarter median claims.** Q2 2026 quarterly medians carry ±9.9% (Robina), ±7.9% (Burleigh Waters), ±6.4% (Varsity Lakes, but on n=17). Only moves beyond roughly ±10% are distinguishable from noise, and none of this quarter's are.
- **No "double-digit growth" across the region.** Only Varsity Lakes reaches double digits. Two of three are single-digit. The published Q2 issue and the 28 July editorial outline both assert region-wide double-digit growth — that came from PropRadar's `growth_1y_pct` and is no longer supported.
- **No "sales halved" / "volume collapsed".** Published figures claimed Robina −67% and Burleigh Waters −30%. On the union basis Burleigh Waters is flat. That claim was an artefact of a source whose capture rate decays for recent quarters.
- **No year-on-year volume comparison at all.** onthehouse reaches back only to August 2025, so a YoY volume figure would compare a union quarter against a Domain-only one.
- **No absorption-rate-led "seller's market" claim without a caveat.** Absorption comes from PropRadar's `house_inventory_months`, built on the same inflated counts we demoted for the median (240 Burleigh Waters houses vs REA's 195). Inflated sales in the denominator make stock look like it clears faster, so absorption is probably **understated**. Robina reads 2.18 months. Soft — flag before leaning on it.
- **Days on market** is a median (robust) but drawn from the Domain-only sample, which skews expensive. Bias direction untested.

## The finding the numbers actually support

**The three suburbs have decoupled.** They are no longer one market moving together:

- Burleigh Waters — the most expensive — is the *steadiest*: volume flat, price up 6.9%.
- Varsity Lakes has the *strongest* price growth (+10.2%) and the *weakest* activity (−62%).
- Robina sits between, softening on both.

That is defensible from our own data, contradicts the "one Gold Coast market" framing every competitor uses, and speaks directly to the research doc's core finding: sellers can no longer read their own suburb from a neighbour's sale, because the comparable set thinned — and thinned *unevenly*.

It also reframes the reader's dominant fear ("have I missed the peak?") honestly: prices did not fall anywhere. What changed is how many buyers are transacting, and that differs by suburb rather than across the region.

## Case studies needed

Selected to prove a specific claim, not because we have photos:

1. **Burleigh Waters** — a sale supporting "steady, not stalled". Needs a Q2 2026 settled sale near the $1.9M median with normal days-on-market.
2. **Varsity Lakes** — a sale illustrating strong price against thin activity.
3. **Robina** — a mid-market sale showing the softening.

*(Not yet sourced. Must come from the union set, and each must be checked against the currently-listed guard before publication.)*

## Open questions carried into the issue

1. Does Burleigh Waters' flat volume hold once Q2 2026 finishes filling in?
2. Is Varsity Lakes' −62% real, or is it thin-quarter noise? n=17 is very small.
3. Absorption — is the PropRadar denominator inflating the seller's-market read?

---

*Every number in this pack is served live at `/market-intelligence/:suburb`. If the report and the site ever disagree, the site is right and the report is wrong — that is now an architectural property, not a discipline.*
