# Basic vs adjusted comparables — one property

**Run:** 2026-08-06 · `compare_comp_methods.py --suburb robina --match Moorabbin`
**Subject:** 26 Moorabbin Place, Robina — 5 bed / 2 bath / 798 sqm land / 213.51 sqm floor
**Sold:** 2026-07-06 for **$1,620,000**

Both methods exclude the subject by `_id` and drop every sale dated on or after
2026-07-06. Neither can see the future.

---

## Method A — basic label match

Same property type, **same bedroom count, same bathroom count, land within ±20%**,
sold in the 12 months before the subject. Raw sale prices, no adjustments.
10 comparables from a 615-record Robina pool.

| Sale price | Date | Land | Address |
|---|---|---|---|
| $1,340,000 | 2025-07-24 | 920 sqm | 3 Claremont Drive |
| $1,510,000 | 2026-02-02 | 880 sqm | 72 Cottesloe Drive |
| $1,520,000 | 2025-10-20 | 853 sqm | 20 Indooroopilly Court |
| $1,589,000 | 2025-11-10 | 756 sqm | 3 Golf View Terrace |
| $1,590,000 | 2025-09-18 | 834 sqm | 89 Glen Eagles Drive |
| $1,670,000 | 2025-09-30 | 730 sqm | 19 Carlingford Place |
| $1,868,000 | 2025-10-14 | 950 sqm | 20 Bentleigh Court |
| $1,904,000 | 2025-07-26 | 863 sqm | 11 Beecroft Place |
| $1,905,000 | 2025-09-25 | 825 sqm | 16 Manly Drive |
| $2,226,000 | 2025-11-09 | 847 sqm | 44 Manly Drive |

**Range $1,340,000 → $2,226,000 (width $886,000) · midpoint $1,783,000**

## Method B — Fields adjusted comparables

8 comparables included of 32 assessed. Confidence: medium.

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

**Range $1,353,442 → $1,722,562 (width $369,120) · midpoint $1,538,002**

---

## Scoreboard — actual sale price $1,620,000

| Method | Range width | Midpoint | Midpoint error |
|---|---|---|---|
| A — basic label match | $886,000 | $1,783,000 | **+10.1%** |
| B — Fields adjusted | $369,120 | $1,538,002 | **−5.1%** |

- **Range narrowed 58%.**
- **Midpoint error halved** — 10.1% → 5.1%.
- The actual price falls inside both ranges, but range A is wide enough
  ($886,000) that this is nearly unavoidable.

---

## Three things to know before this is quoted anywhere

**1. It is n=1.** One property says nothing about the distribution. Per
`Adjusted-Comparables-Evidence.md` §5, run all 262 eligible sold homes and quote
the **median** narrowing and the **median** error improvement, not this example.

**2. ⚠ The result flips if you use the median instead of the midpoint.** Method A's
**median is $1,630,000 — only +0.6% from the actual sale price**, better than our
−5.1%. The midpoint of a range is a fragile statistic: one $2,226,000 outlier drags
it up $150,000. Our advantage here is partly that we are being compared against the
weakest reasonable summary of the basic set. A critic will run the median. **Measure
both across the full sample before any public claim, and decide the statistic in
advance.**

**3. Method B's midpoint IS its reconciled valuation** — both $1,538,002. That is by
construction: the range is the reconciled figure ± `1.645 × weighted_std_dev`, so it
is symmetric. The two columns are not independent evidence.

**Also pre-register the Method A parameters.** ±20% land, exact bed and bath match,
12-month window are all choices, and different tolerances produce different sets.
Fix them before running the full sample or it is cherry-picking.

---

## Replicating

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
python3 compare_comp_methods.py --suburb robina --match Moorabbin \
    [--land-tolerance 0.20] [--window-months 12]
```

Takes ~3 minutes; almost all of it is the suburb-median and street-premium caches,
which build once and would amortise across a batch run.

**Do not** substitute `precompute_valuations.precompute_property_valuation()` — on an
already-sold home its comp filter lets the subject's own sale back in as its own
top-weighted comparable, and the valuation just reproduces the sale price.
