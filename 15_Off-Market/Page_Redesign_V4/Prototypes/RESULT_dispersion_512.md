# The real advantage is determinacy, not accuracy — 512 sold homes

**Run:** 2026-08-06 · `batch_dispersion.py` · seed 20260806 · results in `dispersion_results.jsonl`
**Sample:** 512 sold houses, $1M–$2M, Robina / Varsity Lakes / Burleigh Waters, with resolvable
floor area and land size. 654 scanned, 512 produced both a valid agent pool (≥3 comps) and a
Fields valuation.

**Method.** For each home, every possible agent valuation was enumerated — all combinations of
3 comps from the qualifying pool (same type, same beds, same baths, land ±20%, sold in the 12
months before the subject), each scored as the midpoint of that triple's price range. Compared
against the Fields adjusted-comparables figure and the actual sale price. Both methods exclude
the subject by `_id` and drop every sale on or after its sale date. Median qualifying pool: 21
sales.

---

## 1. The accuracy claim does not survive

**A randomly-selected agent triple beats Fields exactly 50.0% of the time.** It is a coin flip.

| | Fields | Agent median draw |
|---|---|---|
| Median absolute error | **10.0%** | **9.6%** |
| Mean absolute error | 11.5% | 12.1% |
| Within 10% of sale price | 50% | 53% |

Fields wins on the *mean* (fewer catastrophic misses) and loses on the *median*. The two methods
are indistinguishable on accuracy.

> ⚠ **This retracts the 29/71 (n=1) and 23/77 (n=9) figures.** Both were small-sample artefacts;
> the 9-property smoke test used collection order, not a random sample. **The "77% chance Fields
> is more accurate" claim is false and must not be used.**

## 2. What does hold — and it is much larger than expected

The agent method's answer depends almost entirely on *which three comps get picked*.

**Median spread between the best and worst possible agent valuation of the same home: 32.9% of
its value — a median of $469,000.**

| Agent spread exceeds… | Share of properties |
|---|---|
| 10% of the home's value | **87.3%** |
| 20% | **77.0%** |
| 30% | 57.6% |
| 50% | 21.7% |

| Per property | Share |
|---|---|
| Worst possible draw is >20% wrong | **73.4%** |
| Worst possible draw is >30% wrong | 35.4% |
| A near-perfect draw (<2% error) **exists in the pool** | **73.6%** |

**Those last two lines together are the finding.** The right answer is sitting in the comparable
set roughly three times in four — and the three-comp method has no way to identify it. The
problem is not that agents lack data. **The method is indeterminate.** Two honest agents,
same rules, same sales, same suburb, can hand the same owner numbers half a million dollars apart
and both be following standard practice.

---

## 3. So the competitive advantage is determinacy and auditability

Not *"our number is closer"* — it isn't, and saying so is falsifiable from this run.

**It is that our number does not depend on who picked the comps.** The selection is rule-based,
the set is disclosed, and every adjustment is itemised in dollars. Run it twice and you get the
same answer; run the agent method twice and you get a draw from a distribution spanning a third
of the home's value.

This lines up exactly with what the consumer evidence says the pain actually is — the owner with
six estimates spanning $382,000–$704,000 did not say "these are inaccurate", they said
***"I have no idea."*** Dispersion is the grievance. Determinacy is the answer to it, and it is
the one thing we can claim without an accuracy contest we would lose.

---

## 4. ⚠ Our own calibration is bad, and the confidence labels are worse than useless

Measured on the same 512 homes:

**The Fields range contains the actual sale price only 56.8% of the time.**

| Stated confidence | n | Range contains sale price | Median error |
|---|---|---|---|
| high | 273 | **56.0%** | 10.1% |
| medium | 226 | **57.5%** | 9.7% |
| low | 8 | 50.0% | 11.5% |
| very_low | 5 | 80.0% | 3.5% |

**"High" confidence performs no better than "medium" — 56.0% vs 57.5%, with near-identical
median error.** The labels carry no information. This is the inverted-labels problem from the
backtest, now quantified: it is not merely miscalibration, the label is **non-discriminating**.

This is exactly the failure we criticise Domain for — a band marked "high accuracy" that did not
contain the sale price. **We are currently doing the same thing.** Claims register C12 already
bars publishing any confidence label; this is the evidence for why, and fixing it is a
prerequisite to publishing a range at all.

---

## 5. What can and cannot be said

**Supported by this run:**
- "Three comparable sales can justify valuations a third of a home's value apart. We show you
  which eight we used and what each was adjusted for."
- "Our method returns the same answer every time, from a disclosed set of sales."
- "The right answer is usually sitting in the comparable set. The hard part is knowing which
  one it is."

**Not supported — do not say:**
- Any claim that Fields is more accurate than an agent appraisal. Dead heat.
- Any claim about accuracy versus a portal. Separately invalid — see fix-history
  `[DOMAIN-BENCHMARK-CONTAMINATED]`.
- Any confidence label, until §4 is fixed.
- "More reliable" in the sense of *stable over time* — that is a different property and it is
  still unmeasured. This run shows stability across *comp selection*, not across *months*.

**Caveats.** Method A's parameters (±20% land, exact bed/bath, 12-month window) were fixed before
the run but never externally pre-registered. Enumerating every triple treats all selections as
equally likely, which no real agent does — a skilled agent presumably draws better than random,
and this run cannot say how much better. The pool itself is our sold data, which under-captures
(see `data_source_undercapture_reset`).

---

## Replicating

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
python3 batch_dispersion.py            # ~2 min after a ~3 min cache build; resumable
```
