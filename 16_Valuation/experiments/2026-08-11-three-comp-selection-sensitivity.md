# 2026-08-11 — Three-comparable selection sensitivity (the film run)

**Asked by:** Will, to support a social film built around the Queensland statutory CMA and the
"$469,000" three-comparable spread.
**Script:** `16_Valuation/experiments/three_comp_selection.py` → `three_comp_selection.jsonl`
**Sample:** 656 sold detached houses, $1M–$2M, Robina / Varsity Lakes / Burleigh Waters.
**Extends:** `15_Off-Market/Page_Redesign_V4/Prototypes/RESULT_dispersion_512.md` (2026-08-06, n=512).
Fields' own error is **joined by `_id`** from that run, not recomputed — see the ⚠ at the foot.

Fairness rules inherited and unchanged: subject excluded by `_id`, every sale on or after the
subject's own sale date dropped. No hindsight in any pool or any rule.

---

## ⚠ 1. The $469,000 was measured on a pool that is NOT the statutory CMA

The film says on screen: *three properties, sold within six months, within 5 km* — the Sch 2
definition in the Property Occupations Act 2014 (Qld). The 2026-08-06 run used a **12-month,
single-suburb** pool. Those are different populations, and the number moves a lot between them.

| pool definition | homes able to form it | median spread | median $ | >20% | >$300k |
|---|---|---|---|---|---|
| **as run 2026-08-06** — 12mo, same suburb | 526/656 | 32.9% | **$469,000** | 77% | 74% |
| **statutory** — 6mo, 5 km (crosses suburbs) | 546/656 | 47.6% | **$652,000** | 87% | 85% |
| statutory + floor area ±20% | 449/656 | 32.2% | $450,000 | 70% | 69% |
| **strict** — 6mo, 2 km, land ±20%, floor ±20% | 313/656 | 15.9% | **$227,500** | 42% | 37% |

All four also require same property type, same bedrooms, same bathrooms, land ±20%.

Paired on the 307 homes that can form **all four** pools, so this is not a composition effect:
as-run 37.2% / $511,250 · statutory 53.5% / $800,000 · +floor 38.8% / $560,000 · strict 15.8% /
$226,500.

**The statutory pool is wider, not narrower.** A 5 km radius reaches into neighbouring suburbs, and
that added heterogeneity outweighs halving the time window. So the number the film is entitled to
say alongside the statutory definition is **larger** than $469,000 — but it is also the loosest
pool, and the easiest for a hostile reviewer to attack as unrealistic.

**Recommendation: lead with the strict figure, $227,500.** It survives every screen a critic could
demand and it is still a quarter of a million dollars. Quote $469,000 only with "same suburb,
twelve months" attached, and do not put $652,000 on screen at all.

**Reproduction:** the control pool reproduces 2026-08-06 exactly at the median (32.9%, $469,000);
428/512 homes match to <0.01pp. The 84 that differ are comps with a missing sale date, which the
original kept and this run drops — a strictly tighter pool.

## 2. Spread thresholds

| | as run | statutory | strict |
|---|---|---|---|
| spread > $100,000 | 89.0% | 96.0% | 69.6% |
| > $200,000 | 83.5% | 91.6% | 56.9% |
| > $300,000 | 74.0% | 85.2% | 36.7% |
| > $500,000 | 45.6% | 69.8% | 16.3% |
| > $1,000,000 | 12.5% | 30.0% | 2.9% |
| spread > 10% of value | 87.6% | 95.4% | 66.1% |
| > 20% | 77.2% | 87.4% | 41.9% |
| > 30% | 58.0% | 78.2% | 18.8% |

Percentiles, as-run pool: p25 22.4% · **median 32.9%** · p75 47.3% · p90 79.7%.
Statutory: p25 33.1% · median 47.6% · p75 73.3%. Strict: p25 4.3% · median 15.9% · p75 26.1%.

## 3. Two agents, same rules, independent picks — how far apart?

Sampling 2,000 random pairs of triples per home. This is the honest version of the claim, because
it does not assume either agent picked the extreme.

| pool | median gap | >10% apart | >15% | >20% |
|---|---|---|---|---|
| as run | 7.0% | 31% | 17% | 8% |
| statutory | 9.3% | 42% | 26% | 16% |
| strict | 5.5% | 23% | 11% | 5% |

**Say this, not the max-minus-min figure, if the script implies two specific agents.** "Best case
versus worst case" is a range; "two agents disagreeing by more than 10% four times in ten" is what
actually happens to an owner.

## 4. ⭐ The finding: no ex-ante rule finds the right three

Statutory pool, n=546, scored by triple midpoint. Every rule uses only pre-sale information.

| rule | MAE | median err | within 10% | beats a random draw |
|---|---|---|---|---|
| nearest the pool's own median price | **11.1%** | 9.1% | 56% | 64% |
| nearest the pool's median $/sqm | 12.1% | 9.4% | 52% | 55% |
| composite (floor + land + distance + recency) | 12.5% | 9.8% | 51% | 57% |
| **three geographically closest** | 12.6% | 9.6% | 52% | 56% |
| three most similar on floor area | 14.2% | 10.0% | 50% | 53% |
| **three most recent** | **15.3%** | 11.7% | 44% | **46%** |
| three most similar on land size | 15.7% | 11.1% | 45% | **45%** |
| *— random draw* | *13.9%* | *10.3%* | *48%* | — |
| *— ORACLE, the best triple in the pool* | ***2.4%*** | ***0.1%*** | ***92%*** | — |
| *— the worst triple in the pool* | *42.8%* | *33.9%* | — | — |

Direct answers to the questions asked:

- **Closest three:** improves slightly. Beats a random draw 56% of the time. Not reliable.
- **Most recent three:** **makes it worse.** 15.3% vs 13.9% for random, and it beats a random draw
  only 46% of the time. The most natural-sounding rule an agent could state is worse than chance.
- **Most physically similar:** floor area is indistinguishable from random (53%); land size is
  worse than random (45%).
- **Any simple rule that reliably identifies the right three: no.** Scored as *recovery* — 0% = as
  bad as the worst triple, 100% = found the best — all seven rules land between **65.0% and 72.3%**,
  against **68.4% for picking at random.** The entire spread of every sensible selection rule is
  about seven points on a hundred-point scale, straddling chance.

**And the answer is sitting right there.** A triple within 2% of the eventual sale price exists in
the statutory pool for **81.7%** of homes (within 5%: 88%). The oracle scores 2.4% MAE and 92%
within 10%. The best rule anyone could state in advance gets 11.1% and 56%.

**The one rule that does help is not a similarity rule at all.** "Nearest the pool's own median
price" wins — it does not look at the subject property. It just discards the extremes. Note this is
the same median-closeness screen our own selector applies, and the same one
`2026-08-08-comparable-selection.md` shows manufactures agreement and pins the ceiling. It buys
accuracy and costs distribution.

## 5. Per suburb (statutory pool)

| suburb | n | median spread | median $ | >20% | oracle exists <2% |
|---|---|---|---|---|---|
| Robina | 241 | 55.3% | $798,750 | 91% | 83% |
| Burleigh Waters | 139 | 49.9% | $800,000 | 89% | 80% |
| Varsity Lakes | 166 | 39.2% | $518,875 | 81% | 81% |

On the as-run pool the ordering is different and much wider apart — Burleigh Waters 58.4% /
$911,050, Robina 33.9% / $503,750, Varsity Lakes 24.3% / $330,750. **The suburb ranking is an
artefact of the pool definition, not a property of the suburb.** Do not make a per-suburb claim in
the film; it does not survive a change of pool.

---

## ⚠ Caveats — read before quoting anything above

1. **The Fields column in the raw output is stale and must not be used.** `fields_err` is joined
   from the 2026-08-06 run, which used the backtest configuration *before* the full candidate pool
   and λ=0.80 shrinkage — it reports MAE 11.5% / 49% within 10%, where
   `accuracy/2026-08-08-figures.md` publishes **8.05% / 69%** for current production. On these
   numbers the best simple rule appears to beat Fields. That comparison is invalid.
   **A head-to-head against current production has not been run, and the film must not imply one.**
2. **The prohibition in `RESULT_dispersion_512.md` §5 still stands.** No claim that Fields is more
   accurate than an agent appraisal. Nothing here changes it — this run measures *selection
   sensitivity*, not a contest.
3. **Under-capture cuts both ways.** Our sold data misses an estimated 40–50% of transactions
   (`data_source_undercapture_reset`). A fuller pool would contain more extremes, so the spread
   figures are **conservative**. But the "share of homes that can form a compliant pool" figures
   (83.2% statutory, 47.7% strict) are **anti-conservative and must not be published** — the real
   share is higher because the missing sales would fill pools.
4. **Enumerating every triple treats all selections as equally likely.** A skilled agent presumably
   draws better than random. §4 is the closest thing to a test of that — seven plausible expert
   rules, none materially better than chance — but it is not the same as observing real agents.
5. **Midpoint scoring ignores the middle comp** ((min+max)/2 of the three). Re-scored as the mean of
   the three, the statutory median spread is 45.9% / $613,750 versus 47.6% / $652,000. The finding
   is not an artefact of the scoring choice.
6. **Beds/baths/land ±20% is our operationalisation of "similar standard or condition"**, which is
   the Act's actual test. Ours is stricter and more mechanical than the statute. Reasonable, but it
   is a modelling choice, not the law.

## Replicating

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
cd /home/fields/Fields_Orchestrator/16_Valuation/experiments
python3 three_comp_selection.py          # ~1.2 min, seed 20260811
```
