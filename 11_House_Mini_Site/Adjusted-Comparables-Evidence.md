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

## Related

- `scripts/valuation_backtest.py` — the accuracy harness and the safe comp-set builder
- `/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py` — the engine
- Memory: `valuation_backtest_claim_constraints`, `valuation_method_comparables`
- `11_House_Mini_Site/Gap_Analysis_11th_Jun/04_VIDEO_PLAN_AND_SCRIPTS.md` Part 1 — full guardrail list
