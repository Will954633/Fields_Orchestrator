# 2026-08-08 — The comparable selector: what it does, and what fixing it does not buy

**Follows** `2026-08-08-where-the-headroom-is.md`. n = 581 detached houses $1M–$2M, off-market
(blind) subjects, all figures per-suburb de-biased.

---

## The pool is fine. The selector is not.

| | |
|---|---|
| candidate pool | median **47 available**, **8 chosen** |
| sells above the dearest **available** candidate | **2%** |
| sells above the dearest **chosen** comparable | **24%** (raw) / **42%** (adjusted) |
| the chosen comps are cheaper than the rejected ones by | **4.2pp** |

**The pool reaches higher than it needs to.** Coverage is not the constraint here — the selector
discards the top of a perfectly adequate pool.

## ⚠ The mechanism — selection on the dependent variable

`calculate_weight()`, factor 2, worth 20% of the weight:

```python
# Factor 2: Adjusted price accuracy (how close to cohort median)
acc_pct = comp.get('verification', {}).get('accuracy_pct')
adj_accuracy = max(0, 1 - abs(acc_pct) / 0.20)
```

**A comparable is scored on how close its adjusted price is to the cohort median — the very quantity
the comparables exist to estimate.** Comps that disagree with the median are penalised and dropped,
so the surviving set agrees with itself *by construction*.

That single line explains the noise-floor result directly. Our comparables agree within ±8.3% not
because the method is precise, but because **we select for agreement**. Their tight agreement is
manufactured, and it is why they can agree closely and still be collectively wrong.

Factor 1 (25–30%) compounds it: *"smaller total adjustment = more similar property"*. A genuinely
comparable but larger or better home needs a bigger adjustment, and is penalised for it.

## What using the whole pool actually buys

| selection rule | n | MAE | within 10% | 80% band | on $1.6M | sells above all |
|---|---|---|---|---|---|---|
| **SHIPPED — the 8 selected** | 581 | 8.76% | 66% | 13.7% | $437,755 | **42%** |
| **ALL candidates, no selection** | 581 | **8.58%** | **67%** | 13.7% | $437,221 | **5%** |
| nearest 12 to the pool median | 581 | 8.65% | 67% | 13.3% | $424,616 | 54% |
| nearest 16 by distance only | 580 | 9.73% | 62% | 15.4% | $491,678 | 12% |
| nearest 8 by distance only | 580 | 10.27% | 59% | 16.1% | $515,430 | 23% |

**Using every candidate is better than selecting eight** — marginally on MAE (8.58% against 8.76%)
and decisively on the ceiling (**42% → 5%**). The selector is not earning its keep; it is costing
0.18pp and manufacturing a pathology.

Distance-only selection produces an honest ceiling (12%, exactly fair) but is materially worse on
accuracy — proximity alone is not enough.

## ⚠ But it does NOT narrow the band, and that matters

**The 80% band is 13.7% either way.** Fixing selection repairs the *distributional* defect and leaves
the *width* untouched.

That is the third intervention in a row to move the centre or the shape without moving the width:

| intervention | ceiling | band width |
|---|---|---|
| shrinking the total adjustment (λ=0.9) | unchanged 42% | 13.7% → 13.3% |
| using the whole candidate pool | **42% → 5%** | 13.7% → 13.7% |
| showing the subject its photo attributes | unchanged 43% | unchanged |

**So the ~12pp of headroom identified by the noise floor is NOT recovered by any of them.** The width
is set by something none of these touch.

## ⚠ Correction to the previous record

`2026-08-08-where-the-headroom-is.md` concluded that the missing-subject-attribute hypothesis was
"rejected". **That was over-stated and is corrected here.** What was tested was the restoration of
**three specific photo-derived attributes** (`renovation_quality_score`, `kitchen_score`,
`number_of_stories`) — all three of which had *already* measured as noise. That is not a test of
"attributes we do not capture at all"; it is a re-test of three we know to be worthless.

The honest position: **aspect, outlook, slope, frontage width and noise exposure remain untested**,
because we hold no data on any of them for any property. They are the only remaining candidate for a
per-property displacement that survives every intervention above.

## Recommendation — and why it is not shipped

Use the **whole candidate pool for the calculation**, and keep the best eight **for display**. It is
free, marginally more accurate, and removes a real pathology.

⚠ **Not shipped, because it changes the product surface.** The page shows "the 8 strongest
comparisons", and the appraisal shows line-itemised receipts. Separating *what computes the number*
from *what the reader is shown* is a defensible design — arguably a better one — but it is a
decision about what we claim, not just about arithmetic, and it needs Will's call.

**The honest framing if we do it:** "your estimate is built from every comparable sale we hold — here
are the eight closest to your home."
