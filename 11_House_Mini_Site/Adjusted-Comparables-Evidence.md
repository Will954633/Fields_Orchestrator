# Adjusted Comparables — The Evidence

**Created 2026-08-05.** Worked evidence that adjusting comparable sales for measurable
property differences produces a materially tighter, more decision-useful range than
matching on bedroom and bathroom counts.

Intended use: marketing and editorial material for the valuation methodology, and the
worked example behind the individual-home article format.

> **Read §3 before using any of this publicly.** What this demonstrates is narrower
> than "our valuations are the most accurate", and one of the obvious framings is
> contradicted by our own backtest.

---

## 1. The finding

Subject: **26 Moorabbin Place, Robina** — 5 bed / 2 bath, 798 sqm land, 213.51 sqm
internal floor area. Sold **6 July 2026 for $1,620,000**.

Eight comparable sales were selected from 32 candidates. Every one sold **before**
the subject, and the subject's own sale is excluded.

| | Low | High | Spread |
|---|---|---|---|
| Raw sale prices | $1,300,000 | $1,910,000 | **$610,000** |
| Adjusted for property differences | $1,398,872 | $1,673,126 | **$274,254** |

**The adjusted spread is 45% of the raw spread — a 55% narrowing.**

The subject's actual sale price of $1,620,000 falls **inside** the adjusted range.

### The single most compelling illustration

The cheapest and the dearest raw comparables converge almost exactly once their
differences are priced:

| Comparable | Sold for | Adjusted to |
|---|---|---|
| 12 Kilburn Street (cheapest raw) | $1,300,000 | **$1,521,873** |
| 31 Huntingdale Crescent (dearest raw) | $1,910,000 | **$1,565,812** |

**$610,000 apart on raw price. $43,939 apart once adjusted.**

Two sales that look like they describe completely different markets are, once you
account for what is actually different about the houses, describing the same one.

### Why each moved

- **12 Kilburn Street** adjusted *up* $221,873 (+17.1%): the subject has one more
  bedroom (+$113,110) and 53 sqm more internal floor area (+$95,034), partly offset
  by the comparable's higher renovation level (−$48,016).
- **31 Huntingdale Crescent** adjusted *down* $344,188 (−18.0%): the comparable is
  better renovated (−$96,032), in better condition (−$95,500), has an extra bathroom
  (−$89,036) and a second storey (−$50,000).

---

## 2. Why this is the argument, in one sentence

> "Three bedrooms, two bathrooms, sold nearby" is a match on labels. It gave a
> $610,000 range. Pricing what is actually different between the houses — land,
> floor area, condition, kitchen, pool, position — narrowed it to $274,000.

That is a statement about **method**, and it is fully supported by the data above.

---

## 3. What this does and does not prove — READ BEFORE PUBLISHING

### It does prove

- Adjusting comparables for measurable differences converts a scattered set of raw
  prices into a much tighter range.
- Every adjustment is itemised and auditable: factor, subject value, comparable
  value, dollar impact.
- The comparison is honest about time: comparables are selected only from sales that
  occurred *before* the subject sold, so nothing uses hindsight.

### It does NOT prove

**1. It is not evidence that we are more accurate than any competitor.**
This compares *adjusted comparables* against *unadjusted comparables* — our method
against naive label-matching. It is not a comparison against Domain, any portal, or
any agency.

**Our own backtest currently goes the other way in our two most important suburbs.**
Fresh leave-one-out run, 5 August 2026:

| Suburb | Fields MAE | Domain MAE |
|---|---|---|
| Robina | 11.6% | 6.9% |
| Burleigh Waters (Jun run) | 13.7% | 8.1% |

Any public claim of superiority is falsifiable from our own published numbers.
See the standing rule in `valuation_backtest_claim_constraints` memory: **never write
or say "more accurate than Domain"** in any content, video or ad.

**2. A tighter spread is not the same as a more accurate centre.**
Precision and accuracy are different things. A narrow range can be narrowly wrong.
This evidence is about the *usefulness of the range*, not about hitting the number.

**3. This is one property.** n=1. See §5 — do not build a campaign on it until the
distribution is measured.

### The sayable claims

- "Comparable sales that look $610,000 apart can be $44,000 apart once you price the
  differences between the houses."
- "We adjust each comparable for land, floor area, condition, renovation, kitchen,
  pool, storeys, cladding, age, beach distance and street — and we show every
  adjustment in dollars."
- "We publish our error rate. We have not found another agency or portal that
  publishes theirs." *(this is the approved comparative line — it is about
  disclosure, not accuracy)*

---

## 4. How to replicate

Prototype lives in the session scratchpad; the durable dependency is
`scripts/valuation_backtest.py`.

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
python3 comps_for_sale.py robina Moorabbin      # suburb_key, address regex
# writes comps.json + prints the table. Takes ~4 min (street-premium cache
# is built across all suburbs before the single valuation runs).
```

### Why NOT the production engine

`precompute_valuations.precompute_property_valuation()` **cannot be used on a home
that has already sold.** Its sold-comp filter tests property type, price and a
rolling 12-month window only — the `$ne: _id` guard applies to *current listings*.
Run it against a sold home and that home's own transaction returns as one of its own
comparables, with near-zero adjustment, "verified" status and top weight. The
valuation would simply reproduce the sale price.

`valuation_backtest.backtest_single_property()` is the only code path that builds the
comp set correctly — it excludes the subject by `_id` *and* excludes every sale dated
on or after the subject's (`sold_before_subject()`, `valuation_backtest.py:139-160`).

**2026-08-05 change:** that function now also returns `included_points`, `all_points`
and `subject_features`, so the per-comparable adjustment detail is reachable. It
previously computed the detail and discarded it, returning only summary accuracy
metrics. Additive — existing callers unaffected.

### Two bugs found while producing this

1. **`total_adjustment_pct` is a fraction, not a percentage.** A +17.1% adjustment
   reads as `0.171`. Multiply by 100 before display or it prints as "+0.2%".
2. **Time adjustment does not fire on the backtest path.** Only
   `precompute_valuations.py:3222-3228` applies it, and it hardcodes the target as
   `datetime.utcnow()`. For a home that already sold, comparables should be restated
   to **the quarter the subject sold in**, not to today. The prototype adds
   `time_adjust_to()` which reuses the same median series with a different target.

---

## 5. Required before this becomes a campaign

**The narrowing is measured on one property.** Before any public claim:

1. Run across all eligible sold homes (262 currently qualify: detached, $1M–$2M,
   across the three target suburbs) and report the **distribution** of the
   raw-spread → adjusted-spread narrowing — median, quartiles, and how often it
   fails to narrow at all. The honest claim is the median, not this example.
2. **Compose the two adjustments.** Right now the $274,254 adjusted spread comes from
   property-feature adjustments applied to the **raw** price. Time adjustment is
   computed separately and not folded in. Production composes them (time-adjust
   first, then feature-adjust). For reference, on this property time adjustment
   *alone* narrows $610,000 → $402,335. Both narrow; the composed figure is not yet
   verified and must not be quoted.
3. Re-check the accuracy relativities in §3 against the latest weekly backtest —
   relativities move.

---

## 6. Proposed: prospective platform-valuation study (Will, 2026-08-05)

**The idea.** Run a Python process over a large sample of **off-market** homes, capture
the automated platform valuations for each (including screenshots as evidence of what
was shown and when), and store our own adjusted-comparables range alongside them.
Then set a trigger: when one of those homes later **lists or sells**, the captured
estimates become a settled, out-of-sample test. Publish the results as editorial and
marketing material.

**Why it is methodologically strong.** Every accuracy claim we currently make is
retrospective — we look back at what a platform said at listing. Capturing estimates
*before* any listing exists removes every objection about hindsight, selection, or
the platform having already seen the asking price. It is a **pre-registered study**,
and that is a genuinely rare thing in this industry.

### Most of the plumbing already exists

Sold documents already carry `domain_valuation_at_listing` (`low`, `mid`, `high`,
`accuracy` label, `date`, `captured_at`, `source`) and a post-sale
`domain_valuation_accuracy` (`error_dollars`, `error_pct`, `within_range`). Coverage
is 240/616 sold Robina docs. What is new in Will's proposal is (a) capturing for homes
that are **not on the market**, (b) the screenshot as evidence, (c) storing *our*
range at the same moment, and (d) the list/sell trigger.

The trigger has a natural home: the off-market discovery pipeline already tracks these
addresses nightly and already has a real-time listed-property guard.

### ⚠ What the data already says — read this before planning the article

We do not have to wait for the study to know roughly what it will find. Across **708**
sold properties where we captured the platform estimate at listing:

| Suburb | n | Platform MAE | Median AE | Within 10% | Sale inside its own stated range |
|---|---|---|---|---|---|
| Robina | 213 | 7.6% | 7.3% | 76% | 95% |
| Burleigh Waters | 249 | 9.3% | 5.6% | 82% | 91% |
| Varsity Lakes | 246 | 13.6% | 12.8% | 41% | **52%** |
| **Combined** | **708** | **10.3%** | **7.7%** | **66%** | — |

**The platform's combined MAE of 10.3% is better than ours (11.6% Robina, 12.1%
across the June n=1,534 run).** An article premised on "automated platform valuations
are inaccurate" would, run honestly on our own data, largely fail — and in our two
biggest suburbs it would show them ahead of us. Pre-registering a study we lose, then
publishing it, is worse than not running it.

There is also a hard editorial rule in the way: `prompts/editorial_rules.md` forbids
naming Domain or realestate.com.au in any public content — the permitted phrase is
"automated platform valuation". So the article cannot single out a named competitor
even if the numbers supported it.

### The angle that IS supported — and it is better

The real finding in that table is not accuracy. It is **calibration**:

> A stated valuation *range* that the eventual sale price falls outside of **48% of
> the time** (Varsity Lakes) is not a range in any useful sense.

That is a category-wide problem, **and we have it too** — our own ±12% band captured
only 45–57% of sale prices in the 5 August backtest, against a label that says 90%.

So the defensible, and far stronger, article is:

> *Automated valuation ranges — ours included — are systematically overconfident.
> Here is a sample of homes, here is what the automated estimates said before they
> sold, here is what they sold for, and here is how often each range actually
> contained the answer. Including ours.*

That is publishable, survives scrutiny, breaks no rule, requires no competitor to be
named, and is a much rarer thing to say than "we're more accurate." It also creates
the pressure to fix our own range calibration, which is already an open action item.

### Preconditions before building

1. **Fix our own range first.** Publishing a calibration study while our own "90%"
   band runs at ~50% is self-inflicted. Recalibrate, then publish.
2. **Pre-register the sample and publish every outcome.** Fix the address list and
   the capture date up front. If we publish only the homes where the estimates
   missed, the study is worthless and the first person to check will say so.
3. **Legal review on the screenshots.** Capturing a competitor's page and
   republishing it as evidence of their inaccuracy raises ToS, copyright and
   misleading-conduct exposure — distinct from quoting a number. Note also that the
   VM is Akamai-blocked from Domain and must fetch via `shared.domain_fetch`.
4. **Include our own estimate in the same capture**, at the same timestamp, or the
   study is not honest and cannot be defended.

---

## 7. Proposed: the cost of a listing price set without adjusted comparables (Will, 2026-08-05)

**The idea.** Find real campaigns where the asking price looks like it was set by
label-matching rather than by adjusted comparables, and show what it cost. Three
shapes:

- **Listed too high** — sold well below the asking price after a long campaign, where
  adjusted comparables computed *at listing date* already said the price was outside
  the evidence.
- **Listed too low** — sold quickly at or above asking, where the comparables
  supported more.
- **Withdrawn** — the campaign that never produced a sale at all. Will's instinct that
  this is the strongest case is right: it is the least ambiguous outcome.

This is the consequence story rather than the method story, and it is more persuasive
for exactly that reason.

### The signal is real

Sold properties in the three suburbs with at least two recorded priced events:

| | n | Median days on market |
|---|---|---|
| Reduced the asking price | 21 | **68** |
| Did not reduce | 11 | **37** |

Campaigns that cut their price ran **84% longer**. Strongest current examples:

| Property | First asked | Reduced to | Sold | Days |
|---|---|---|---|---|
| 16 Collingwood Avenue, Robina | $1,949,000 | $1,749,000 | $1,700,000 | **127** |
| 2 Sugarleaf Court, Burleigh Waters | $1,595,000 | $1,390,000 | $1,330,000 | 49 |
| 20 Tropicana Circuit, Burleigh Waters | $1,995,000 | $1,800,000 | $1,780,000 | 66 |

### ⚠ The wake-up call — we already published one of these as a success story

We published **"$1,700,000 in Robina: How 16 Collingwood Avenue Beat the Suburb Median
by 11.8%"**. That home was first asked at **$1,949,000**, cut to $1,749,000, and sold
for $1,700,000 after **127 days**. The published article:

- never mentions the 127-day campaign
- never mentions the original $1,949,000 asking price
- refers to $1,749,000 as "the guide" (9 mentions of "guide"), i.e. treats the
  *reduced* price as if it were the original

Every sentence is arguably true and the overall impression is wrong. The current
article format can turn a struggling campaign into a win, because it only ever sees
the final guide. **That is the best argument for building this concept**, and it is
also an immediate fix to make in the How It Sold pipeline: read `price_history`, not
just `listing_price`.

### Data available

- `price_history[]` on each doc: `{price_text, price_numeric, recorded_at, run_id,
  event: initial|change}`. Present on 270/1,549 sold docs; **32** currently have two
  or more *priced* events (many first events are "Auction" or "Expressions of
  Interest" with a null price).
- **64 withdrawn** properties across the three suburbs, **48** with at least one
  priced event. Note `days_on_market` is null on withdrawn docs — campaign length must
  be derived from `price_history` timestamps (first `recorded_at` to last seen).

### ⚠ Constraints — this one has the most ways to go wrong

**1. The sample is small and time-limited, but it grows.** Price tracking only began
around March 2026, so n=32 is five months of accrual, not a ceiling. This is a
"instrument now, publish in six months" concept. It also means the price-history
collector must not be allowed to silently stop.

**2. The comparables must be computed as at the LISTING date — not the sale date.**
Different cutoff from §4. Claiming "the comparables already said this was too high"
requires the comp set to contain only sales before the property was *listed*.
`sold_before_subject()` would need the listing date passed in instead.

**3. Our own error rate sets the bar for what counts as a miss.** At 11–12% MAE we
cannot call an 8% overprice a mistake — it is inside our noise. Only gaps well outside
our own error (say 20%+) are defensible, and the article must state our error rate in
the same breath.

**4. Pre-commit the selection rule or this is cherry-picking.** Hunting for cases where
our method looks prescient, and publishing only those, is the fastest way to destroy
the credibility the rest of this document is built on. Define the rule first (e.g.
"every sold or withdrawn property in the band with ≥2 priced events"), run it over
everything, and report how often our comparables *failed* to anticipate the outcome.

**5. This one has real legal and relationship exposure.** An article saying a named
address was overpriced is implicitly criticising an identifiable agent and agency, and
touches a vendor's financial affairs. There is currently **no vendor or agent privacy
rule anywhere in the editorial prompts** — this concept makes that gap acute. Before
building: decide whether properties are de-identified (suburb and type only), get a
view on naming agencies, and keep the mindset brief's framing — the angle is the
pricing evidence, never a judgement of the people. "Be fair to the vendor. Circumstances
change."

### Suggested sequence

1. Fix the How It Sold pipeline to read `price_history` so current articles stop
   presenting a reduced price as the original guide. Cheap, and it removes an active
   accuracy problem.
2. Add a listing-date comp cutoff.
3. Run the full pre-committed set, measure the hit rate honestly, and only then decide
   whether there is an article.

---

## Related

- `scripts/valuation_backtest.py` — the accuracy harness and the safe comp-set builder
- `/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py` — the engine
- Memory: `valuation_backtest_claim_constraints`, `valuation_method_comparables`
- `11_House_Mini_Site/Gap_Analysis_11th_Jun/04_VIDEO_PLAN_AND_SCRIPTS.md` Part 1 — full guardrail list
