# The second comparable set — recent sales nearby

**Date:** 2026-08-13 · Built after Will asked whether comps older than six months are
compatible with the Property Occupations Act, and where a published range gets its top
number when no comparable reaches it.

## The question

Our unit range is built from sales in the **same building**, most of them older than six
months. A Comparative Market Analysis under the **Property Occupations Act 2014 (Qld)
Sch 2** means at least three sales, **within six months**, of similar standard, **within
5km**. 82.6% of our comparables fail the recency test.

The page's position — that this is general information and not an appraisal, so s215 is
not triggered — is correct but incomplete. It answers the legal question and ignores the
better one: *is the older same-building sale actually the better evidence?* That is a
measurable claim, and it was being asserted rather than measured.

## What was built

A **second** comparable set on the same page, to the statutory standard: same bedroom
count, within 5km, settled in the last six months, each sale adjusted to the subject.
Shown alongside the same-complex set, not instead of it.

### Distance needed geometry we did not have

Per-unit coordinates exist on **0.7% of indexed attached dwellings** (16 of 2,281 in
Robina). Geocoding 4,967 unit addresses would have been slow, paid, and *wrong in a
specific way*: a geocoder resolves `12/45 Smith St` to the street, so every home in a
tower gets a slightly different point implying precision we do not have.

The **scheme centroid** is not a workaround for that — it is the correct geometry. Every
home in one building genuinely shares one location. `ingest_scheme_centroids.py` computes
an area-weighted centroid per strata plan from the QLD cadastre:
**1,964 of 1,964 schemes located (100%), covering 100% of indexed units.**

Sanity-checked against real geography: Robina→Varsity Lakes 2.39km, Robina→Burleigh
Waters 4.04km, Varsity Lakes→Burleigh Waters 1.76km. All three suburbs fall inside one
5km radius, so the pool deliberately spans all three collections — scoping to the
subject's own suburb would apply a filter the Act does not ask for and would drop the
nearest sales for anyone near a boundary.

⚠ `returnCentroid=true` is a documented ArcGIS parameter that **this service silently
ignores** — HTTP 200, well-formed features, `"centroid": null` on every one. We request
full geometry and compute the centroid ourselves.

## The results

**Coverage:** a statutory set exists for **86.3% of indexed units** (4,297 of 4,980).
Of the rest, 675 have no bedroom count and 8 genuinely lack three recent nearby sales.

**It is measurably worse evidence.** Scored leakage-free on the same 1,542 sales, both
methods predicting the same homes with only prior sales visible:

| | median error | MAE | within 10% |
|---|---|---|---|
| Sales in this building | **5.7%** | **9.3%** | **67.4%** |
| Recent sales within 5km | 9.1% | 14.6% | 54.1% |

Same-complex is closer on 54.5% of individual sales — but the gap in MAE (9.3% vs 14.6%)
is much larger than that, which means the statutory set is not merely a coin-flip worse:
it is far worse **in the tail**. Its typical answer is tolerable; its bad answers are much
worse.

**And far more dispersed.** The adjusted sales span a median of **43%** of their own
median, because "a 2-bedroom attached dwelling within 5km" covers a beachside apartment in
Burleigh Waters and a townhouse in western Robina alike. The 2-bed pool alone runs
$802,000–$1,230,000.

### So it is published as evidence, never as an estimate

Nothing in this set feeds the range. It exists so a reader can see the trade the primary
method makes rather than being asked to trust it — and so a compliant CMA already exists
the moment a seller asks. **If it ever starts feeding the range, the page gets less
accurate while looking more compliant, which is the worst of both.**

## Two decisions worth recording

**Same bedroom count is required, not preferred.** The obvious way to lift coverage is to
accept a 3-bedroom comparable for a 2-bedroom subject and adjust by the observed bedroom
step (Robina medians: 1bd $712,500 · 2bd $870,000 · 3bd $1,090,000 · 4bd $1,315,000 — a
stable ~1.22–1.25× per bedroom). We do not. Those medians conflate bedroom count with
everything correlated with it — floor area, car spaces, aspect, building age — so
adjusting a 3-bed down by 22% prices the bedroom *and* silently prices all of that. The
"adjustment" would be mostly confound.

**The ranking never contains price.** "Within 5km in the last six months" is a catchment,
not a comparable set: it returns a median of 25 sales spanning 72% of the median price. We
rank on distance, floor area, bathrooms and recency and keep the closest 12, which brings
the spread to 43%. Ranking on closeness to an expected value — or to the pool median —
would select the evidence to agree with the answer and then report the agreement as
accuracy. Our house selector already scores comps on closeness to the median, which is
why its backtest flatters it.

## What this surfaced elsewhere

Building the backtest reported floor area known on **0 of 3,005** attached Robina homes
when the true figure is 20.1%. The zero was ours: `_num` was aliased to `sale_price`, whose
$20,000 price floor deleted every floor area in the system. `impute_floor_area` — live on
the page data path — had therefore returned `None` for **every unit ever asked**, while
advertising an accuracy figure it could not have produced. See
`logs/fix-history/2026-08-13.md` `[UNIT-NUM-ALIAS-EATS-FLOOR-AREA]`.

## Files

| | |
|---|---|
| `scripts/ingest_scheme_centroids.py` | cadastre → scheme centroids (monthly) |
| `scripts/statutory_comparables.py` | the set itself |
| `scripts/precompute_statutory_comparables.py` | → `Gold_Coast.unit_statutory_comps` (daily) |
| `scripts/backtest_statutory_comparables.py` | the head-to-head, leakage-free |
| `v4/StatutoryCompsSection.tsx` | the page section |
