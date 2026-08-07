# 02 — Visual system, taken from the live property page (PARKED 2026-08-07)

**Status: parked.** Raised by Will after reviewing the prototype against the live listing page; set
aside to keep working on prose and flow. Everything needed to execute it is here — do not re-do the
research.

**Reference:** `https://fieldsestate.com.au/property/126-acanthus-avenue-burleigh-waters`
Measured from computed styles + mobile screenshots, not eyeballed.

---

## The tokens

| role | value | notes |
|---|---|---|
| page background | `#e6ddd2` `--fields-birch` | a TRUE warm stone. The prototype uses `#F7F5F1`, near-white — this is the single biggest visual gap |
| card | `#ffffff` and `rgba(255,255,255,.65)` | translucent white over birch; `--card` is the .65 form |
| interpretation block | `#22382c` `--fields-grass` | 7 uses on that page — reserved for Fields' own reading |
| accent | `#b76749` `--fields-copper` | labels, left rules, CTAs (44 uses at .95) |
| label on dark | `#dd8f6d` `--copper-on-dark` | copper is illegible on grass; this is its dark-surface pair |
| shadow | `0 14px 40px rgba(34,56,44,.12)` | green-tinted, soft. Prototype uses flat 1px borders |
| grass ramp | `#0b110e` → `#22382c` (`--grass-900`…`--grass-500`) | for nesting darker tiles inside grass blocks |
| CTA radius | 4–8px | copper fill, white text |

## The structure — colour carries meaning

Every section on the live page follows the same four tiers:

1. **Label** — small uppercase, letter-spaced (`CONDITION & VALUE`, `PRICE ANALYSIS`)
2. **Claim** — bold lead sentence stating the finding
3. **Evidence** — either a blush pull-quote with a copper left rule, or a `KEY POINTS` bulleted list
   with bold lead-in terms
4. **Interpretation** — a dark grass block headed `WHAT THIS MEANS`, nested *inside* the white card

Plus: small labelled **stat tiles** in a grid (`DAYS LISTED`, `PER M²`, `FLOOR-TO-LAND`), a
full-bleed hero photo with gradient overlay and the headline reversed out of it, and a dark grass
header bar carrying the white logo.

## Why this is cheap for us

**Our content already has these tiers.** `copy_v4.yaml` carries a `means:` field on nearly every
card — the mandatory "so what" translation line. The prototype renders those as a faint grey
`.weight` box. On the live page that same semantic role gets a **dark grass block**, and it is the
main reason that page has rhythm.

So the work is not "add styling" — it is **render the tiers we already have in the vocabulary we
already own**: white = the record, grass = our reading of it.

## Order of impact

1. Warm the background to `#e6ddd2`. Makes white cards read as cards.
2. Grass block for every `means` line.
3. Blush pull-quote + copper rule for narrative passages (dispersion finding, buyer portrait,
   the envelope explanation).
4. Stat tiles for the facts row instead of an inline strip.
5. Dark grass header bar with the white logo.
6. Soft green-tinted shadows instead of flat borders.

## ⚠ Two cautions — read before executing

**The reference page is SELLING; this one is not.** It carries "Analyse My Property", "Get My
Property Analysis", "Track updates" — copper buttons throughout. `01_UI_BRIEF.md` rules that out
for this page: *"should not feel like a lead-generation funnel… the first human-contact CTA should
appear only after substantial value."* **Take the colour system and card hierarchy; leave the CTA
density.**

**There is a genuine tension between the brief and this direction.** The brief asks for *"quiet,
premium, evidence-led… no bright portal-style cards, very limited icon use."* The live page is more
energetic than that. Current reading: Will wants the *structure and colour-as-meaning*, not the
sales energy — but that was never explicitly settled, and it changes several decisions. **Confirm
before building.**

## How to execute when we return

Build it as a **variant** beside the current page rather than replacing it — same content, same
data, live vocabulary — so the two can be judged together. The aerial colour-comparison page is the
pattern that worked.

See [[01_UI_BRIEF]], `Prototypes/render_prototype_a.py`.
