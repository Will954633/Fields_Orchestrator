📐 Valuation: 78.3% of the addressable for-sale book valued (n=69) · 40.6% of all listings (n=212) · MAE 8.05% (n=581, unchanged, not re-measured this cycle)

**Cycle 1 — the domain's first run. Brief tier: `current` (0d), full standing authorisations,
which in week one means read-only. Nothing was written to any property document, no method
constant was touched, no recompute was run.**

---

## The headline, plainly

The standing brief opens on a premise that is false, and this cycle's main output is
retiring it.

> *"76 of the 126 — 60% of all failures — record no reason whatsoever … we currently
> cannot tell a deliberate refusal from a crash."*

We can. **All 76 record a machine-readable reason, and not one of them is a crash.** They
record it under a key the sensor does not read. This is Rule 8 — *a query returning zero is
a fact about the field name you typed* — applied to our own instrument, and it is the thing
that put "the 76 silent failures" at the top of the brief and generated Will's open question
about widening write access in week two.

---

## What changed in my area since last cycle

`fix_digest.py --days 8 --domain valuation` returns **49 entries**, 18 of them today. This
is the most actively-changed area in the business right now. Directly relevant:

- `[ORPHANED-VALUATIONS]` and `[DECLINE-LEAVES-THE-OLD-FIGURE]` (08-13) — a withdrawn
  valuation kept its old range; a job cannot correct what it stopped evaluating. Both are
  the same class as what I looked at: state left behind when the method stops speaking.
- `[UNITS-VALUATION-LIVE]` (08-10) — attached dwellings now get a measured range. This is
  why the "excluded by decision" line in the brief is no longer the whole story (see below).
- `[BACKTEST-BLIND-NOT-BLINDING]` (08-12) — `--blind-subject` was penalising rather than
  blinding. Anything measured with it before 08-12 is suspect.
- `[VALUATION-UNKNOWN-ASYMMETRY]` (08-12) — unknown attributes marked subjects down.

Nothing in the digest had already fixed what I raise here.

---

## The numbers, with their denominators

All figures: `Gold_Coast.{robina,varsity_lakes,burleigh_waters}`, `{"listing_status":
"for_sale"}`, **n = 212**, 2026-08-13. Repro:
`python3 16_Valuation/experiments/coverage_decomposition.py`. Full working:
`16_Valuation/experiments/2026-08-13-coverage-decomposition.md` (append-only record).

### 1. The 76 "silent" failures decompose cleanly, and every one is a correct refusal

| population | n | where the reason actually lives |
|---|---|---|
| `confidence.confidence == "directional"` | 42 | `confidence.directional_reason` |
| `confidence.confidence == "insufficient_data"` | 34 | the tier itself; `n_total ∈ {0,1}` |

The 42: `above_design_ceiling` 25 (House), `below_design_floor` 12 (10 Unit, 2 Townhouse),
`price_above_threshold` 5 (House). List price median **$2,000,000**, max **$4,198,000** —
these are exactly the homes the envelope exists to refuse.

The 34: 33 attached dwellings + 1 house, all with 0 or 1 comparable in the pool.

`computed_at` is populated on all 76. **Zero never-computed. Zero crashes.**

### 2. Coverage on the population the method claims to serve is 78.3%, not 40.6%

| | n |
|---|---|
| live for-sale | 212 |
| classified House | 99 |
| less envelope-suppressed (25 + 5) | −30 |
| **addressable by the house method** | **69** |
| **valued** | **54 — 78.3%** |

| suburb | valued / addressable | % |
|---|---|---|
| Robina | 38 / 49 | 77.6% |
| Varsity Lakes | 9 / 11 | 81.8% |
| Burleigh Waters | 7 / 9 | 77.8% |

**Burleigh Waters' alarming 16.7% is a composition effect, not a Burleigh Waters problem.**
45 of its 54 listings are attached dwellings or above the design ceiling. On the homes the
method is built for it performs identically to Robina — 77.8% vs 77.6%. That answers open
question 3 in the brief: it is structurally outside the envelope and correctly silent, and a
targeted data-sourcing effort there is not warranted.

The entire remaining addressable gap is **15 properties**: missing floor area 7,
misclassified dwelling 3, missing land size 2, insufficient comparables 2, insufficient data
1. **Nine of those are a sourceable missing input.** That is the whole honest coverage lever
on the house method — and it is small, which is itself the finding. There is no large
coverage win hiding here.

### 3. The attached-dwelling surface is the real thin one — 28.3% (n = 113)

Townhouse 12/33 (36.4%) · Unit/Apartment 16/69 (23.2%) · Villa 2/7 (28.6%). Dominant
blocker is empty comparable pools (33), not missing subject attributes. Also: a **house**
envelope reason, `below_design_floor`, is stamped on **12 attached dwellings** — worth a
look now that units have their own method, since the house floor has no obvious meaning for
a unit.

### 4. Two houses are classified `Vacant Land`

`288 Christine Avenue` (3 bed, 163 m²) and `7 Jurien Crescent` (5 bed, 232 m²), both Varsity
Lakes, carry `classified_property_type: "Vacant Land"` with `property_type: "House"`. Both
are correctly valued — the defect is the classifier (step 112), and it matters because
house-only filters gate on that field (cf. `[HOUSE-ONLY-FILTER-SWEEP]`). n = 2 of 212;
outside my write envelope and too small to spend a recommendation slot on, so it is recorded
here and in the experiment record for whoever owns step 112.

---

## The mechanism I think is at work

The sensor was written the same day as the brief, and the brief was written from the
sensor's output. Nothing sat between them. `valuation_signal.py` verified its field paths
carefully — its docstring lists paths that do *not* exist, which is exactly right — but it
verified that `exclusion_reason` **exists**, not that it is **the only place a reason is
recorded**. Three separate writers stamp refusals (`exclusion_reason`, `directional_reason`,
and the `confidence` tier itself), the sensor reads one, and the residual was labelled "(no
reason recorded)" — a phrase that asserts an outcome the query cannot support.

The same shape produced the second defect: the envelope counter runs under `if has_rv`, so
the one population it exists to measure — properties the envelope *suppressed*, which by
definition have no `reconciled_valuation` — is the exact population it cannot see. It
printed `above 0` for Robina against 25 real `above_design_ceiling` flags. The sensor's
priority-2 surface currently reports close to the opposite of the truth.

This is Rule 7b for reads, which the mandate states directly: an empty result must assert an
outcome, not merely fail to throw.

---

## What I did autonomously

Read-only week, and I stayed inside it.

- Ran `valuation_signal.py --dry-run`; read the sensor source.
- Ran four read-only decompositions against `Gold_Coast` (no writes).
- Verified `classified_property_type` / `property_type` fill with
  `db_fields.py Gold_Coast burleigh_waters --grep property_type --query '{"listing_status":
  "for_sale"}'` → both 54/54 (100%), per Rule 8, before using either.
- Wrote the append-only experiment record `2026-08-13-coverage-decomposition.md` and its
  repro script `coverage_decomposition.py` under `16_Valuation/experiments/`.
- Did **not** fix the sensor, though it is a real bug defeating the brief's intent:
  `valuation_signal.py` carries a Rule 7 heartbeat, which makes it monitoring code and
  permanently non-autonomous regardless of brief.
- Did not run a backtest. Published accuracy is 5 days old, `--blind-subject` was only
  fixed on 08-12, and coverage was the brief's stated priority; spending the budget on a
  re-measure this week would have bought less than the decomposition did.

## What I proposed

**One.** `REC-valuation-001` [fix, S, reversible] — the two sensor counting defects, with
the ask that **open question 1 in the brief should not proceed**: widening write access to
valuation documents so the domain can stamp `exclusion_reason` onto the 76 would be granting
a risky permission to fix a reporting bug in the reader. Ledger now 1/2.

I deliberately did not propose a second. The 15-property addressable gap is real but small
and does not need Will; the classifier defect is n=2 and belongs to another owner; the
attached-dwelling coverage question is genuinely open but I have not measured it well enough
this cycle to spend his attention on it. Next week's work, not this week's recommendation.

## What I graded

Nothing — first cycle, `due-for-grading` empty, `feedback` empty.

## The open question I would most like answered next week

**Is the attached-dwelling surface in scope for this domain at all?** The brief says units
are "excluded by decision" because they inflate published accuracy figures — but
`[UNITS-VALUATION-LIVE]` shipped a measured unit range to live pages on 2026-08-10, and 32
attached dwellings currently carry a valuation. So the brief and the product disagree. It
matters because 113 of 212 live listings are attached: if they are in scope, coverage there
(28.3%) is now the largest quality question in the business, and the `below_design_floor`
flag sitting on 12 of them is the first thing I would pull. If they are out of scope, then
this domain's denominator is 69 and I should stop counting them.
