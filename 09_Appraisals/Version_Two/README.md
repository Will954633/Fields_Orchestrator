# Property Position Report — Version Two

A complete redesign of the internal pages of the Fields Appraisal Report, built around a single structural idea: **every internal spread is a two-page argument** — the left page presents one of Fields' ten core seller advantages; the right page applies that advantage to the subject property.

The front cover, inside-front handwritten note, contents, and methodology are carried forward from V1 unchanged in spirit (see [front/](./front/)).

This is a **content mock-up** — focused on editorial excellence first, production engineering second. Numbers are plausible-but-illustrative until the production pipeline is wired in.

---

## Working subject

**13 Terrace Court, Merrimac, QLD 4226 — prepared for Dee.**

Specs (from V1 report):
- 6 bedrooms + study, 3 bathrooms, dual living
- 658 m² land, 221 m² internal floor area
- Pool, north-facing rear, cul-de-sac head
- 9/10 condition (kitchen 9/10, exterior n/a)
- Bushland-adjacent (Kingary Wetland Reserve, 623 m)
- Schools: All Saints Anglican (387 m walk), Star of the Sea (1,085 m)

---

## The ten spreads

Sourced from the curated capability list ([Google Doc · Seller Core Competitive Advantages](https://docs.google.com/document/d/1RXzceEhxnXQofduxUg49iB3ARF3FtOO0HDK-R-sf3RE/edit)).

| # | Spread title (working) | Capability |
|---|---|---|
| 1 | We see your home in more dimensions than any other agency | Multi-modal property analysis depth |
| 2 | What makes your home rare — and why that moves the price | Scarcity-attribute identification |
| 3 | The buyer who pays the most is a specific person | Scarcity-to-persona mapping |
| 4 | We know where your buyers are and how to reach them | Buyer-pool sizing & targeting |
| 5 | Buyers arrive at your home already trusting Fields | Pre-built buyer trust |
| 6 | Buyers decide with their hearts. We engineer for that | Hearts-first presentation |
| 7 | Your home's price, derived not declared | Reconciled valuation engine |
| 8 | Nobody knows your suburb better — including what's coming next | Forward-looking market intelligence |
| 9 | The right method for your home, not for our brand | Method choice without bias |
| 10 | The best month to list your home is a number we can give you | Optimal timing intelligence |

---

## Spread anatomy

Every spread follows the same skeleton — see [00_spread_template.md](./00_spread_template.md).

**Left page — *The capability*:**
- Spread number + headline
- The principle (one or two sentences)
- What Fields uniquely does (3-6 specific items)
- The evidence (citations, data counts, named studies)
- Pull quote
- Why this matters for the seller (one paragraph)

**Right page — *Applied to your home*:**
- Subject address strip + spread title echo
- The headline finding for this property
- Data inventory specific to the home
- Visual element (chart, map, table, image grid)
- What this means for your sale

---

## Folder layout

```
Version_Two/
├── README.md                    ← this file
├── 00_spread_template.md        ← reusable left/right anatomy spec
├── front/
│   ├── P01_cover.md             ← keep (reference V1 spec)
│   ├── P02_inside_front_note.md ← rewrite (handwritten Will note)
│   ├── P03_contents.md          ← rewrite (10-spread index)
│   └── P04_methodology.md       ← rewrite (compact one-pager)
├── spreads/
│   ├── S01_data_depth.md
│   ├── S02_scarcity.md
│   ├── S03_buyer_personas.md
│   ├── S04_buyer_targeting.md
│   ├── S05_buyer_trust.md
│   ├── S06_hearts_first.md
│   ├── S07_valuation_engine.md
│   ├── S08_local_market_intel.md
│   ├── S09_method_choice.md
│   └── S10_optimal_timing.md
└── back/
    ├── verdict.md               ← consolidated valuation + recommended listing range
    ├── next_steps.md            ← three-step ladder
    └── inside_back_note.md      ← Will's closing handwritten note
```

---

## Status

- 2026-05-07 — V2 scaffold + Spread 1 (data depth) drafted as template lock. Spreads 2-10, front matter, and back matter pending review of S01.
