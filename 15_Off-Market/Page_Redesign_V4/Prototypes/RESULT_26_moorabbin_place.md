# Agent 3-comp valuation vs Fields adjusted comparables — one property

**Run:** 2026-08-06 · `compare_comp_methods.py --suburb robina --match Moorabbin`
**Subject:** 26 Moorabbin Place, Robina — 5 bed / 2 bath / 798 sqm land / 213.51 sqm floor
**Sold:** 2026-07-06 for **$1,620,000**

Both methods exclude the subject by `_id` and drop every sale dated on or after
2026-07-06. Neither can see the future.

> **Supersedes the first run of this file**, which gave the agent method ten comps.
> Ten is not what an agent valuation does. With three — the real practice, and the
> statutory Statement of Information standard — **the range-narrowing claim
> disappears entirely.** See §"What died" below.

---

## Method A — agent valuation, 3 comps

Same property type, same bedroom count, same bathroom count, land within ±20%,
sold in the 12 months before the subject. Raw prices, no adjustments.

**Ten sales qualify — so there are 120 possible three-comp selections.** Rather than
pick one, all 120 were enumerated:

| | Range width | Midpoint | Midpoint error |
|---|---|---|---|
| Best case | $564,000 | $1,622,000 | **+0.1%** |
| **Median case** | $330,000 | $1,505,000 | **−7.1%** |
| Worst case | $322,000 | $2,065,000 | **+27.5%** |

Median range width across all 120: **$394,000**. Median absolute error: **7.1%**.

Two selections an agent could actually defend:

| Selection | Range | Midpoint | Error |
|---|---|---|---|
| 3 most recent | $1,510,000 → $2,226,000 | $1,868,000 | **+15.3%** |
| 3 closest on land | $1,589,000 → $1,905,000 | $1,747,000 | **+7.8%** |

## Method B — Fields adjusted comparables

8 comparables included of 32 assessed, medium confidence. Each raw sale price is
adjusted for measurable differences from the subject:

| Sold for | Adjusted to | Move | Address |
|---|---|---|---|
| $1,405,000 | $1,398,872 | −0.4% | 18 Fan Road |
| $1,565,086 | $1,457,766 | −6.9% | 22 Huntingdale Crescent |
| $1,410,000 | $1,512,544 | +7.3% | 81 Thorngate Drive |
| $1,300,000 | $1,521,873 | **+17.1%** | 12 Kilburn Street |
| $1,570,000 | $1,528,204 | −2.7% | 24 Springvale Street |
| $1,910,000 | $1,565,812 | **−18.0%** | 31 Huntingdale Crescent |
| $1,520,000 | $1,620,023 | +6.6% | 4 Springvale Street |
| $1,700,000 | $1,673,126 | −1.6% | 40 Tullamarine Drive |

**Range $1,353,442 → $1,722,562 (width $369,120) · midpoint / reconciled $1,538,002 · −5.1%**

---

## Scoreboard — actual sale price $1,620,000

| Method | Range width | Midpoint | Error |
|---|---|---|---|
| A — agent 3 comps, median case | $394,000 | $1,505,000 | −7.1% |
| A — agent, 3 most recent | $716,000 | $1,868,000 | +15.3% |
| A — agent, 3 closest on land | $316,000 | $1,747,000 | +7.8% |
| **B — Fields adjusted** | **$369,120** | **$1,538,002** | **−5.1%** |

---

## What died

**The range-narrowing claim.** Against a ten-comp basic set the Fields range was 58%
narrower. Against a **three**-comp agent set it is **12% wider** ($369,120 vs a
$394,000 median — effectively a tie). This is arithmetic, not merit: any three points
span less than any ten. **Do not repeat "our range is narrower than an agent's" — it
is false against the three-comp baseline, which is the one that matters.**

Worse, the *worst* agent selection has the **narrowest** range of all ($322,000) and
is **27.5% wrong**. Narrow is not right. A tight three-comp range is false confidence,
which is the same failure we criticise portals for.

## What survived — and it is a better argument

**Accuracy.** Fields is closer than the agent's median case (5.1% vs 7.1%), and closer
than **both** selections an agent could actually defend (+15.3% and +7.8%). Modest but
real, and in the right direction.

**Dispersion — this is the finding.** The same method, same data, same defensible
rules produces answers from **+0.1% to +27.5%** depending purely on *which three sales
get picked*. A 27-point swing attributable to nothing but selection. Fields produces
one answer, from a stated set of eight, with every adjustment itemised in dollars.

> The three-comp method is not inaccurate so much as it is a **lottery** — and the
> homeowner has no way of knowing which ticket they were handed.

That is an argument about **method and auditability**, not accuracy — which is exactly
where our evidence is strongest and where the claims register already says we must
stay. It also does not require any comparison against Domain or PropTrack.

⚠ The +0.1% best case is only identifiable in hindsight. An agent cannot pick it
deliberately. The honest expectation for the method is the **median** case, ~7.1%.

---

## Before this is quoted anywhere

1. **n=1.** Run all 262 eligible sold homes and quote the median of the *dispersion*,
   not this example. Per `Adjusted-Comparables-Evidence.md` §5.
2. **Pre-register Method A's parameters.** ±20% land, exact bed and bath match, and a
   12-month window are choices. Different tolerances give different pools, and with
   only three comps the pool size drives everything.
3. **Method B's midpoint IS its reconciled valuation** — both $1,538,002 — because the
   range is symmetric at ±1.645 × weighted std dev. Not independent evidence.
4. **Do not extend any of this to a portal comparison.** The 2026-08-05 backtest has
   Domain ahead of us in Robina (6.9% vs 11.6%). This compares us to *agent practice*,
   which is a different and defensible claim.

---

## Replicating

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
python3 compare_comp_methods.py --suburb robina --match Moorabbin \
    [--n-comps 3] [--land-tolerance 0.20] [--window-months 12]
```

~3 minutes, almost all of it the suburb-median and street-premium caches, which build
once and would amortise across a batch.

**Do not** substitute `precompute_valuations.precompute_property_valuation()` — on an
already-sold home its comp filter lets the subject's own sale back in as its own
top-weighted comparable, and the valuation simply reproduces the sale price.
