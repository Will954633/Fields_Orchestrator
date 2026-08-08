# Owner-subject article — generated batch v1

Preview: `https://vm.fieldsestate.com.au/concepts/off-market/Owner_Article_v1/<slug>.html`

Nine articles, generated 2026-08-07 by
`scripts/owner_article/build_owner_article.py`. **Not published, not posted.**

These are the first articles produced by a GENERATOR rather than written by hand.
The 2026-08-05 prototypes in `../Article_Prototypes/` were one-off drafts whose
generator never existed on disk — regenerating them was impossible, and their
figures had already drifted from the database by the time they were reviewed.

## What changed against the prototype

| Prototype (2026-08-05) | Now |
|---|---|
| Printed `confidence grade: high` | **Removed.** Measured across 512 sold homes the label is non-discriminating (high 56.0% range-hit vs medium 57.5%) |
| Comps to 2.57 km, copy said "near your street" | **Hard 2.0 km radius**, widened in 0.5 km steps only if fewer than 4 comps remain, and the widening is disclosed in the article |
| Claimed proximity | States the true nearest and furthest distance |
| Hardcoded "+5.8% matches +5.8%" agreement | **Derived per home** — close / same-direction / opposite, with the closing caveat matched to which case fired |
| Numbers hand-typed (one draft shipped "four of the eight" when it was six) | **Every figure minted through `factbook.py`**; any figure in the copy that was not minted fails the build |
| `<title>` leaked "26 Moorabbin Place" onto the Heidelberg article | Title derived from the subject |
| No image | **Aerial hero** with the true cadastral boundary drawn on it |

## Two data visuals (added 2026-08-08)

1. **How long homes are taking to sell** — median days on market by quarter, with
   the sample size under every point and quarters below 15 sales drawn hollow.
   Placed before the median section on purpose: the homeowner brief §8.3 says to
   lead with time-on-market over medians, because it is more reliable in our data
   and cannot accidentally become advice.
2. **Suburb median house price** — rolling 12-month median with its bootstrap 90%
   confidence interval drawn as a ribbon. This is §8.2 ("publish the confidence,
   not just the number") made literal, aimed at ranked fear #3, *"the number in my
   head might not be real."* The ribbon visibly narrows as the sample grows.

Both read from the SAME collections the Market Intelligence pages render, never
recomputed. Verified this batch: DOM reads 34 / 26 / 29 for Robina / Varsity Lakes
/ Burleigh Waters, matching `market_pulse.data_snapshot.dom_median` exactly. A
mismatch is a **build failure**, not a warning — an owner may hold this sheet while
looking at the website and cannot tell which is stale.

⚠ **Why DOM is publishable and sales VOLUME is not.** Our PropRadar cross-check
(memory `data_source_undercapture_reset`) found days-on-market and price growth
matched closely while scraped sold volume under-counts by ~2x. A median survives a
sample; a count is exactly what sampling destroys. So `transaction_count` appears
only as a sample size beneath each point, never as a market figure.

⚠ **The median series is SPARSE.** Robina is missing Q3 2024 even inside the recent
window. Points are placed by true quarter ordinal and the chart plots only the most
recent UNBROKEN run, so no line is ever drawn across a quarter we do not hold.

## The batch

| Address | Comps | Radius |
|---|---|---|
| 20 Heidelberg Circuit, Robina | 6 | 2.5 km (widened) |
| 16 Cheltenham Drive, Robina | 8 | 2.0 km |
| 3 Springvale Street, Robina | 8 | 2.0 km |
| 13 Chantilly Place, Robina | 7 | 2.0 km |
| 14 Ranier Crescent, Varsity Lakes | 7 | 2.0 km |
| 11 Placid Court, Varsity Lakes | 8 | 2.0 km |
| 37 Manakin Avenue, Burleigh Waters | 6 | 2.0 km |
| 8 Whitehead Drive, Burleigh Waters | 7 | 2.5 km (widened) |

**28 Wedgebill Parade was in the first batch and is now REJECTED** — the nightly
recompute moved its adjusted-comparable midpoint from $1,976,692 to $2,263,910 and
flagged it `directional_only`. The design-envelope guard caught it. Worth knowing
that eligibility is not stable between runs.

Chosen for spread: all three suburbs, adjusted-midpoints $1.15M–$1.98M, comp
counts 6–8, two needing a widened radius. All nine passed the live PropRadar
mailability guard (not listed, not under contract).

## Still open

1. **Time adjustment is computed but not composed** with the feature adjustments —
   inherited from the engine, unchanged here.
2. **Visual treatment is a first pass.** Hero, accent on the adjusted column,
   print stylesheet. Colours and layout await Will's direction.
3. **Aerials are ~1.6 MB each.** Fine on screen, wants compression before any
   print or bulk run.
4. **No sequence, no suppression, no mail history.** This generates one piece;
   nothing tracks who has received what. That is the campaign layer, not built.

See `scripts/owner_article/` for the generator, `factbook.py` for the numeric
gate and `guardrails.py` for the editorial one.
