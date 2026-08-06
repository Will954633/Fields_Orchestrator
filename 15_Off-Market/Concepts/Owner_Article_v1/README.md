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

## The batch

| Address | Comps | Radius |
|---|---|---|
| 20 Heidelberg Circuit, Robina | 6 | 2.5 km (widened) |
| 16 Cheltenham Drive, Robina | 8 | 2.0 km |
| 3 Springvale Street, Robina | 8 | 2.0 km |
| 13 Chantilly Place, Robina | 7 | 2.0 km |
| 14 Ranier Crescent, Varsity Lakes | 7 | 2.0 km |
| 11 Placid Court, Varsity Lakes | 8 | 2.0 km |
| 28 Wedgebill Parade, Burleigh Waters | 8 | 2.0 km |
| 37 Manakin Avenue, Burleigh Waters | 6 | 2.0 km |
| 8 Whitehead Drive, Burleigh Waters | 7 | 2.5 km (widened) |

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
