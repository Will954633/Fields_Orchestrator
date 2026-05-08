# Designer Handoff — Property Position Report V3

This package contains everything needed to lay out the V3 Fields appraisal report for print or interactive PDF. It is intended for a print/editorial designer working in InDesign, Affinity Publisher, or equivalent.

The HTML→PDF preview in this folder (`preview.pdf`) is a **content-locked proof**, not a final art file. It establishes:
- Page count, sequence, and content per page
- Brand system (colours, fonts, header/footer chrome)
- Typography hierarchy
- Hero visual placement and treatment
- Single-idea-per-spread anatomy

The designer's job is to take the locked content + visual system and produce the final art. Every typographic, spacing, and image decision can be refined — but **the content, structure, and emotional architecture are decisions, not suggestions**.

---

## What's in this package

```
Version_Three/
├── README.md                ← V3 strategic overview, V2→V3 migration table, page index
├── 00_spread_template.md    ← Single-idea anatomy, typography targets, what's removed
├── HANDOFF.md               ← (this file)
├── preview.html             ← Coded preview, all 16 pages, self-contained
├── preview.pdf              ← Rendered proof PDF for visual reference
├── front/
│   ├── P01_cover.md         ← Cover spec
│   └── P02_thesis.md        ← Thesis page spec
├── spreads/
│   ├── S01_rarity.md        ← The killer spread — 1 of 4
│   ├── S02_buyer.md         ← The buyer who pays the premium
│   ├── S03_position.md      ← Where your home sits (3 competitors + band)
│   ├── S04_trust.md         ← The 72-hour pre-launch
│   ├── S05_campaign.md      ← The funnel — ~52K to 1
│   └── P13_pause.md         ← Full-bleed emotional pause
├── back/
│   ├── P14_verdict.md       ← The verdict + recommendations
│   ├── P15_next_steps.md    ← 4-step ladder + soft CTA
│   └── P16_closing_note.md  ← Will's signed note + audit clause
└── assets/
    ├── hero_0.png           ← Twilight pool exterior (cover + pause)
    ├── exterior.jpg         ← Subject home exterior shot
    ├── living.jpg           ← Subject home interior
    ├── kitchen.jpg          ← Subject home kitchen
    ├── satellite_13_terrace_court.png   ← Aerial for Spread 01
    ├── comp_5-straite-drive-robina.jpg  ← Competitor 1
    ├── comp_20-federal-place-robina.jpg ← Competitor 2
    └── fields-logo-white.png            ← Logomark
```

Each `*.md` page-spec file contains:
- A layout sketch (text-based)
- The final copy (headline, body, supporting facts, captions)
- Designer notes — colour callouts, image annotations, typography targets
- Production data sources (so claims can be re-verified at issue time)

---

## Brand system at a glance

| Token | Hex | Usage |
|---|---|---|
| Grass | `#22382C` | Primary text, dark panels |
| Birch (cream) | `#E6DDD2` | Page ground (never pure white) |
| Copper | `#B76749` | Accent, spread numbers, key statistics |
| Copper soft | `#F0D9CC` | Highlight regions on dark panels |

**Fonts:**
- **Playfair Display** — all serif headlines, spread numbers, body type on display pages (thesis, verdict)
- **Poppins** — sans-serif for header strips, footer, labels, secondary metadata
- **Optional alternate:** Cormorant Garamond for editorial body if a softer serif is preferred

**Page format:** A4 portrait, 210 × 297 mm, 16 pages, no spreads (each page is its own sheet).

---

## What V3 changed vs V2

| | V2 | V3 |
|---|---|---|
| Pages | 36 | 16 |
| Spreads | 10 (× 3 pages each, including "continued") | 5 (× 2 pages each) |
| Ideas per spread | 5–12 | 1 |
| Charts per spread | 3–4 | 1 maximum, often zero |
| Methodology | Front-loaded (page 4) | Back-loaded footer (page 16) |
| Inside-front note | Apologetic ("forty hours of work…") | Removed — replaced by thesis page |
| Closing note | Brief | Will's signed personal commitment |
| Personas (Spread 02) | Three with full demographic catchment math | One named primary, one secondary ribbon |
| Pricing argument | Spread 07 with adjustment tables, 90% CI | Spread 03 with single positioning band |
| Per-spread word count | 600–900 (incl. continued page) | 120–200 |

The strategic shift: from "look how much analysis we can do" to "these people understand my home better than anyone."

---

## Critical design notes

1. **Single-idea spreads.** Every spread is two pages. Left page argues a capability; right page applies it to the property. There are NO continued pages. If a spread feels short, it's correct — the goal is breathing room, not density.

2. **Hero visual is the page.** Each right-hand page has one hero visual. If the image is weak, the page is weak — refine the image, not the typography.

3. **One forest-green panel in the entire document.** Spread 02's pull quote ("Saturday morning here looks like this…") is the only place the grass-green panel appears. Its rarity is its impact. Do not introduce additional green panels elsewhere.

4. **No bullet-list "What Fields uniquely does" panels.** V2 had these on every left page; V3 removes them entirely. The body paragraph carries the capability; the right page proves it.

5. **Three pages do not have page numbers or footers:** the cover, the emotional pause (P13), and any future full-bleed page.

6. **The phrase "difficult to replace" is the unifying philosophy.** It appears on the thesis page (P02). Do not over-use it elsewhere — its weight comes from being heard once and re-recognised in the verdict.

7. **Editorial rules (per Fields content guidelines):**
   - No advice ("you should sell" / "now is a good time"). Data only.
   - No predictions. Indicators only.
   - No forbidden words: stunning, nestled, boasting, rare opportunity, robust market.
   - Number format: `$1,250,000` not "$1.25m". Suburbs always capitalised.
   - Buyer interest range, never single-figure valuation in headlines.

---

## Production specifics

### Cover image
- Use V2's `hero_0.png` (twilight pool exterior with bushland edge and glass balustrade) OR commission a true twilight shoot of the subject property. The current image is daytime; a true dusk frame would lift the cover meaningfully.

### Spread 01 (Rarity) hero
- Aerial / satellite of 13 Terrace Court (`satellite_13_terrace_court.png`)
- Annotations: bushland boundary highlighted in copper, cul-de-sac head circled, "1 OF 4" badge top-right
- Annotations should be subtle — 1pt copper at 60% opacity, not heavy data overlays

### Spread 02 (Buyer) hero
- Lifestyle composition — twilight pool deck with bushland edge
- No people in the image (reader projects themselves in)

### Spread 03 (Position) cards
- Three property cards in a row, equal width
- Subject card uses copper outline; competitors use hairline grey
- Single horizontal positioning band beneath: copper-filled subject range, grey dots for competitors

### Spread 04 (Trust) hero
- Three real proofs stacked: (1) Fields website article screenshot with "FEATURED SLOT" copper tag, (2) Fields homepage / market intelligence thumbnail, (3) engagement metric card
- Use *real* software screenshots, not stylised mockups

### Spread 05 (Campaign) funnel
- Six rows: 52K → 3.8K → 480 → 95 → 45 → 1
- Bar widths use sqrt or log scaling (not linear) so the bottom rows remain visible
- The final row is a single copper dot, not a bar — this is the emotional landing

### Page 13 (Pause)
- Full-bleed twilight image, no header, no footer, no page number
- Text overlay sits in the lower portion with a dark gradient behind it (the preview shows this technique; refine in production with a hand-painted gradient if needed)

### Page 14 (Verdict)
- The opening assessment uses the LARGEST body type in the document (16pt cap-serif)
- The three-line climax — *"That category is scarce. / Scarcity changes buyer behaviour. / Behaviour determines price."* — should be set in italic copper with tight leading. This is the rhetorical apex.

### Page 16 (Closing note)
- "Will Simpson" signature is the visual anchor — large, copper, italic. If a digitised handwritten signature exists, replace the typeset version.

---

## What the designer can refine

- All typography sizes (we're targeting 13pt body, 1.7 leading — adjust within the visual system)
- Colour temperature of the cream background (current `#E6DDD2` may push slightly warmer or cooler depending on stock)
- Heading kerning (especially the cap-serif numbers and verdict typography)
- Image colour grading (maintain a coherent palette across all property photography)
- Hairline rule weights and copper accent intensity
- The "F" logomark currently rendered as inline SVG — a designer's vector logo is preferred

## What the designer should NOT change without consultation

- Page count (16) and sequence
- Spread structure (5 capability/applied pairs)
- The thesis statement on page 02
- The "1 of 4" headline on page 04
- The "Saturday morning" pull quote on page 06
- The price range and verdict statements on pages 08 and 14
- The closing note copy on page 16
- The audit promise / methodology footer on page 16

These are content decisions, not styling decisions, and they were made deliberately during the V2→V3 redesign.

---

## Contact for clarifications

Will Simpson · `will@fieldsestate.com.au`

Source data, telemetry queries, and any verification requests can be answered against the live Cosmos DB / PostHog systems. Most numbers in this report can be re-pulled at issue time using the data sources cited in each page-spec file.
