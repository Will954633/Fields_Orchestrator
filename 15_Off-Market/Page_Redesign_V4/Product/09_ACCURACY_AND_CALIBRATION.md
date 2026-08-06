# 09 — Accuracy and calibration

**Status:** blocking. `copy_v4.yaml:card_05_method.error_rate` is `null` pending this.
**Measured:** 2026-08-06, n=333 sold homes across Robina, Varsity Lakes, Burleigh Waters.
**Script:** `scripts/valuation_backtest.py --price-filter none`

---

## The headline

| | figure |
|---|---|
| Mean absolute error | **12.3%** ($180,680) |
| **Median absolute error** | **9.3%** ($127,600) |
| Bias | −2.0% (we come in slightly low) |
| Within 5% | 27% |
| Within 10% | 52% |
| Within 20% | 80% |
| Worst over / under | +68.6% / −47.2% |

⚠ **SUPERSEDED by the addendum below** — the sample was Robina-only, and the published figure is
now per-suburb and scoped to the design envelope. Kept for the record.

**Originally recommended:** *"Tested against 333 homes in these three
suburbs that have since sold: half the time the estimate landed within 9.3% of the eventual sale
price. The average miss was 12.3%."*

Both numbers, because quoting the median alone is the flattering half. The mean is dragged by a
thin tail (worst case +68.6%) and the median describes the home the reader actually owns.

---

## Finding 1 — the figure in circulation was measured with the answer in the filter

`in_cohort` pruned each subject's comparable pool to sales within ±40% of **that home's actual
sale price** — the value being predicted. Production anchors on the *listing* price, and on an
off-market home there is no listing price at all: `price` is absent on **12,275 of 12,278**
off-market houses (0.0%), so the filter never fires there.

| anchor | MAE | median AE | within 10% |
|---|---|---|---|
| `sale` — leaked | 11.7% | 8.8% | 55% |
| `listing` — production, for-sale | 12.3% | 9.3% | 53% |
| `none` — **production, off-market** | **12.3%** | **9.3%** | 52% |

The leak is worth 0.6pp. **11.7% was the number in circulation as "11.6%".** The comment at
`precompute_valuations.py:3038` cites the backtest to justify the filter — *"reduces MAE from
12.7% → 11.7%"* — but that gain was measured under leakage and bought a filter inert on the
entire off-market book. Logged `[BACKTEST-TARGET-LEAKAGE]`.

`listing` and `none` are identical to the decimal, which tells us most sold docs lack a `price`
too — so the filter rarely fires anywhere. It is close to dead code with a misleading comment.

---

## Finding 2 — the "90% confidence range" contains the truth 61% of the time

> **203 of 333 (61%) of actual sale prices fell inside the predicted range.**

⚠ **CORRECTED, same day.** This section first claimed the range is `1.645 × weighted_std_dev`.
**It is not, and has not been for some time.** That description survives in CLAUDE.md (now fixed)
and in memory, but the code uses a deliberate flat **±12%** and its own comment says so: *"This
reflects the empirical accuracy of the comparable-sales model — not a statistical CI."* The
t-distribution approach was abandoned because it produced negative lower bounds on 2 comparables.
That was a sound decision, documented honestly, and I misread it.

Verified directly: **all 9,232 published ranges are exactly ±12.0%. One distinct value.** The
range carries no property-specific information at all — same width whether we found 3 comparables
or 30, whether they agreed or scattered.

So the corrected picture: ±12% is empirically a **~60% interval** (measured 61%, and 67% inside
the design envelope). A genuine 90% band needs **±26.4%** — the measured P90 error, i.e. 2.2×, not
the 3.1× I derived from normal theory the code does not use.

**This is a live claim risk, not a modelling nicety.** §1's entire argument is *"the width is the
honest part"* — and the width currently understates our own uncertainty.

Two ways out, and they are genuinely different products:

1. **Widen the range** to what 90% containment actually requires. Honest, and makes the ranges
   visibly less useful — a $470k-wide range on a $1.9M home says little the owner didn't know.
2. **Keep the width, relabel it.** Never call it a 90% range. State the measured containment:
   *"about six in ten sales land inside a range built this way."*

**Recommendation: (2), and say the number.** It preserves a usable range, it is true, and
admitting the containment rate is exactly the move the rest of the page makes its name on. (1)
is more conservative but throws away the thing that makes the page worth reading. Either way the
phrase "90% confidence" must not appear anywhere in the V4 arm.

⚠ **Needs Will's sign-off** — this changes what a range on the page means.

---

## Finding 3 — the confidence label is not calibrated

| level | MAE | within 10% | n |
|---|---|---|---|
| high | 11.7% | 55% | 146 |
| medium | 12.8% | 46% | 143 |
| low | 12.2% | 56% | 16 |
| **very_low** | 13.1% | **61%** | 28 |

Not monotonic in either column. `very_low` has a **better** within-10% hit rate than `high`, and
so does `low`. Only high-vs-medium discriminates at all (55% vs 46% on within-10%, n=146/143),
and even there MAE separates by just 1.1pp. The `low`/`very_low` cells are small (n=16, n=28) and
noisy — but that is the point: we cannot demonstrate the label means anything.

**`emit_v4.py:128` surfaces this label to the reader** as `tier_caveat`, from
`confidence_reason` or `confidence`. A reader shown "high confidence" reasonably infers the range
is more trustworthy. The data does not support that inference.

**Recommendation:** stop emitting the bare level. `confidence_reason` — which states *why*
(e.g. how many comparables, how close) — is a fact and can stay. The one-word tier is a claim we
cannot back, and it is the kind of unearned confidence signal this whole page exists to argue
against. Shipping it would be self-refuting.

---

## What this does to the page

- **§3 / `card_05_method`** — unblocked. Use the median + mean sentence above.
- **§1 / `card_01_range`** — the copy never says "90%", so no existing line is false. But it must
  never acquire one, and `tier_caveat` should drop the bare tier.
- **§4 / `card_06_dispersion`** — unaffected and *strengthened*. The $469,000 dispersion finding
  is about the three-comp method's instability, measured separately. Our own 12.3% sits well
  inside that spread, which is the comparison the card is making.

## What is still not established

- Every figure here is **leave-one-out on sold homes**. Off-market homes are not a random sample
  of sold homes — they are, by definition, homes that did not sell. Applying a sold-home error
  rate to them is an assumption, and the page should not pretend otherwise.
- n=333 across three suburbs, one snapshot. No confidence interval on the error rate itself.
- The Domain comparison in the same run (MAE 7.7%, within-10% 77%) is **not usable**: per
  `valuation_backtest_claim_constraints`, and because Domain revises valuations after listing, so
  its figure is contaminated by look-ahead. It is recorded here only so nobody re-derives it and
  believes it. **It does not belong on the page in either direction.**


---

# Addendum — the design envelope, and why the figure is per-suburb (2026-08-06, later)

**Will:** *"our comparables valuation was only designed for detached houses in that range. its
not cherry picking."* That constraint was recorded nowhere. It is now — see
[[valuation_design_envelope]] and CLAUDE.md.

## Scoped to the envelope: detached houses, $1M–$2M

| suburb | n | MAE | median AE | within 10% | containment | bias |
|---|---|---|---|---|---|---|
| Robina | 278 | **10.5%** | 8.2% | 59% | 67% | — |
| Burleigh Waters | 155 | 11.2% | 9.8% | 52% | 60% | −3.7% |
| **Varsity Lakes** | 207 | **13.8%** | 13.4% | **36%** | **41%** | **−10.6%** |
| blended | 640 | ~11.7% | ~10.3% | ~50% | ~57% | |

**Scoping works** — 12.3% → 11.7% blended, containment 61% → 57%… but read the next line before
celebrating.

## Why the claim is per-suburb and not blended

**The spread between suburbs (10.5% → 13.8%) is larger than the entire gain from scoping
(12.3% → 11.7%).** A single blended figure would overstate our accuracy to a Varsity Lakes owner
by 2.1pp and understate it to a Robina owner. The page knows the address, so it can say the true
thing. `copy_v4.yaml:error_rate_by_suburb`, with **no blended fallback** — an unmeasured suburb
renders nothing rather than borrowing another's record.

## The finding that should worry us most

**Varsity Lakes carries a −10.6% systematic bias.** Not noise — a consistent undervaluation, on
a page whose job is to earn a homeowner's trust. Telling Varsity Lakes owners their home is worth
10.6% less than it is, is the worst available direction to be wrong in. Containment there is 41%
against Robina's 67%.

This is a **model defect, not a disclosure problem**, and no amount of honest labelling fixes it.
Recommend it blocks the V4 arm in Varsity Lakes specifically.

## Two more things the envelope work turned up

**The fallback chain saved us, then nearly tripped us.** When the engine declines,
`fact_bundle` falls through to `exterior_evidence` → `thin`. For 30 Whitehead Drive that produced
a point of **$2,507,000 — above the comps ceiling entirely** — and a range $852K wide against the
±12% band's $500K, carrying its own "Lower — exterior evidence only" explanation. That is the
right answer for an out-of-envelope home.

But `card_05` would have attached the **engine's** measured error rate to a range built by a
different, never-measured method. Fixed: the error rate renders only when
`valuation.method == "engine"`; otherwise a caveat says so plainly.

**A hard threshold has a soft edge.** A home valued at $1.99M passes and gets a ±12% band running
to $2.23M — whose upper half sits outside the envelope the method is built for. Inherent to any
cut-off, worth knowing, not worth over-engineering today.
