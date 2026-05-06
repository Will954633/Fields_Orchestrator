# Visual System — How It Looks

This document defines the typography, colour, grid, photography, and chart-making rules that produce the Fields appraisal report's visual signature. It is an applied document — every rule maps to a CSS token, an InDesign style, or a render-pipeline parameter.

The single design ambition: **a homeowner who has received three other agent appraisals should look at ours and not recognise the category.**

---

## 1. Visual identity inheritance

We inherit the Fields brand system already in production:
- Colour tokens from `current_template_reference.html` `:root`
- Type ramp from existing seller-book and property-page work
- The "F" mark + "Smarter with data" lockup
- The Marty FA cover treatment (April 29 2026, see `4274 - Marty_Fields - Property Report_FA.pdf`) is the **canonical cover direction**.

This document refines, doesn't redefine. Any change here must be reflected in: (a) the HTML/CSS template, (b) the InDesign master if used for print, (c) the microsite components.

---

## 2. Colour system

### 2.1 Tokens (locked)
| Token | Hex | Use |
|---|---|---|
| `--grass` | `#22382C` | Verdict box background; primary deep tone; section divider TRUTH |
| `--copper` | `#B76749` | Cover callout block; section labels; trade-off accent; foil treatment in print |
| `--birch` | `#E6DDD2` | Background for honest assessment panels; warm neutral page tint |
| `--sky` | `#A0D1C9` | Soft accent; condition score pill background |
| `--sun` | `#FEC66F` | Single-statistic hero accent (e.g. scarcity number) |
| `--ink` | `#1A1F1B` | Body text |
| `--whisper` | `#FAFAF7` | Page background where birch is too warm |

### 2.2 Application rules

- **Grass + copper is the dominant pairing.** No other pairings should compete for the eye.
- **Sun is reserved for a single hero number per page** (peak attention). Never used on more than one element per spread.
- **Sky is functional, not expressive** — used for non-decision UI (score pills, neutral callouts).
- **No gradients.** No drop shadows. No glassmorphism. No blur-effects.
- **Print-specific:** copper callout block on the cover is foil-blocked on premium print runs (silver-foil-look copper, not metallic gold).

### 2.3 Forbidden colours
- Pure black (`#000`) — too harsh against birch backgrounds. Use `--ink`.
- Real-estate gold / yellow-orange combinations — instant franchise feel.
- High-saturation primary blue / red — not in our palette.

---

## 3. Typography

### 3.1 The pairing
Currently in production: **Poppins** (sans-serif, geometric, clean). The May 6 design-style PDF uses it well. We keep it for the digital system.

**For print master:** consider an upgrade to a paired serif/sans system, e.g.:
- Display + headlines: **GT Sectra** (Grilli Type) — editorial, used by The Modern House and *The Atlantic*. Or **Larken** (Apostrophe) — affordable, similar register.
- Body + UI: keep **Poppins**, or step to **Söhne** (Klim) for editorial weight.

The choice will turn on Will's preference. Until then, Poppins is the locked default.

### 3.2 Type ramp
| Style | Size (print) | Size (digital) | Weight | Use |
|---|---|---|---|---|
| Cover address | 60–72pt | n/a | 700 | Cover only |
| Section divider | 36pt | 32px | 400 | TRUTH / EVIDENCE / ACTION |
| H1 | 28pt | 28px | 600 | Page openers |
| H2 | 20pt | 22px | 600 | Sub-sections |
| H3 / Card title | 14pt | 16px | 600 | Card headings |
| Body | 10pt | 14px | 400 | Default |
| Callout body | 10pt | 14px | 400 | Verdict, trade-off panels |
| Caption / footnote | 8pt | 11px | 400 italic | Source lines |
| Numerical hero | 80–120pt | 80–120px | 700 | Single hero stat (e.g. scarcity number) |

### 3.3 Type rules

- **Tracking is open** on display sizes (+20 to +60 units). Never tight-set unless intentional brand mark.
- **Line-height is generous** — 1.5 for body, 1.3 for H2/H3.
- **Numbers are monospaced** in tabular contexts (comparison adjustments, financial tables). Use OpenType `tnum` feature.
- **Hyphenation off**, except in body prose where natural breaks read better than ragged-right rivers.
- **Maximum line length** 65 characters in body. Forces multi-column layout where prose volume demands it.

### 3.4 The numerical signature
Every dollar figure rendered with comma separators and no abbreviation: `$1,725,000` not `$1.725M`. (Janiszewski & Uy 2008.) Per the editorial review checklist (`04_content_modules.md`).

---

## 4. Grid system

### 4.1 Page geometry
- **Format:** A4 portrait. Print bleed 3mm, trim 210×297mm. Live area 18mm margins all sides; 22mm bottom for footer rule.
- **Grid:** 12 columns, 4mm gutter. Content can break at 1, 2, 3, 4, 6, or 12 column groupings.
- **Baseline grid:** 4mm baseline. All text rests on the grid for visual rhythm.

### 4.2 Layout patterns
- **Hero pages** (cover, section dividers, full-bleed photo) — 12-column edge-bleed.
- **Verdict + specs pages** — 8-column main + 4-column sidebar.
- **Comparable cards** — 12-column equal split into 3 (digital) or 4–5 (print expanded).
- **Honest assessment panels** — 12-column stack (single-column) for readability of dense prose.
- **Two-column body prose** — used for longer narrative sections (M11, M21).
- **Three-column reference matter** — methodology + sources page.

### 4.3 Whitespace discipline
- Top and bottom whitespace ≥ 30mm on text-heavy pages (Cereal-influenced).
- Information-dense pages (comp adjustments, market context) compress to 18mm — Monocle density signal.
- Section dividers: 70%+ whitespace. Earned restraint.

---

## 5. Photography rules

### 5.1 What ships
| Photo | Angle | Time of day | Print stock |
|---|---|---|---|
| Cover hero | Full exterior including roofline + landscape context | Twilight (or golden hour minimum) | Coated 200gsm |
| Property Through Our Eyes | Interior key rooms (kitchen, living, master) | Afternoon, blinds open, lights on | Coated 200gsm |
| Location & Lifestyle | Aerial / drone (when available), shot toward water/parks | Mid-morning | Coated 200gsm |
| Lifestyle narrative pages | Ambient: kettle on, deck table set, pool with one towel | Morning, soft light | Uncoated 100gsm — feels editorial, not real-estate |

### 5.2 Photographic discipline
- **No stock photography. Ever.** A single stock photo invalidates the document.
- **No cars in driveways.** Move them or shoot another angle.
- **No people in frame** unless explicitly arranged (M11 narrative pages may include a deliberate presence).
- **No HDR over-processing.** The Modern House / Inigo register: real light, real shadow, real materials.
- **Photo metadata preserved** — caption every photo with at least the time of day. Adds editorial credibility.
- **Twilight is the brand signature.** A Fields cover is twilight or it isn't a Fields cover.

### 5.3 When we don't have the right photo
- Use a *withheld photo* indicator: a soft-tinted photo placeholder that names the shot we'd take. Better than placing a weak photo. ("Twilight pool deck shot to be added once weather permits.")
- Or, escalate to *in-suburb same-archetype paired example* — labelled as such, not implied to be the subject's home.
- Never crop a poor photo to hide the issue. Either fix it, replace it, or admit it's missing.

---

## 6. Charts and information design

### 6.1 The Tufte / FT discipline
- **Conclusion in the title.** Every chart's title is the headline finding. ("89% of online estimates overvalue Gold Coast homes" not "Estimate accuracy by suburb".)
- **Source line on every chart.** Always — including dataset name and date.
- **Strip non-essential ink.** No 3D effects, no gridlines unless they aid reading, no axis labels where the title carries them.
- **Small multiples** preferred over a single complex chart where comparison is the goal.

### 6.2 Chart palette (locked)
- **Primary series:** `--grass`
- **Comparison series:** `--copper` (when 2 series), `--sun` (when 3 series), `--sky` (when 4 series). Order is visually ordered by importance.
- **Chart background:** `--whisper` (never white-on-white when on a birch page).
- **Annotations:** `--ink`, 8pt, italic.
- **Hero stat bands:** `--grass` background with `--sun` for the number.

### 6.3 Sparklines (Tufte)
Inline data in body prose. Width 60–100px. No axis. Leading-and-trailing dot anchors. Use cases:
- "The Robina median has tracked [↗ sparkline] +6% YoY across 5 years."
- "Days on market for 4-bed homes [↘ sparkline] has fallen from 31 to 18 days since June."

This is a deliberate signature — almost no Australian property report uses sparklines, and they read as expert.

### 6.4 The map module
Every report includes one suburb-context map and one street-context map.
- **Suburb map:** subject as copper pin, comparables as grass pins. Date and price labels. Walk-distance rings to top 3 POIs. (Print) silk-screen overlay of street names where the map is pale.
- **Street map:** zoomed to ~150m radius. Shows boundaries (wetland, school, road). Subtitled: "What the buyer's drone sees."

---

## 7. Iconography

The `Icons/` folder in `09_Appraisals/` already contains a complete light + dark icon set. Use rules:
- **Use icons sparingly.** Only on (a) feature highlights in M5, (b) pricing-strategy tags, (c) Next-Steps numbered list.
- **One icon per panel.** Multiple icons per panel reads as franchise marketing.
- **Always stroke, never fill.** The fill style reads cheaper.
- **Same colour as the surrounding text.** Don't introduce a new colour just for an icon.

---

## 8. Object-level decisions (print only)

### 8.1 Stock
- **Cover + interior photography pages:** 200gsm coated silk. Photography breathes; saturation honest.
- **Body / methodology pages:** 100–120gsm uncoated. Editorial feel; matches Inigo / Modern House register.
- **Inside-back-cover business card pocket:** 350gsm card stock, foil-blocked.

### 8.2 Binding
- **Perfect-bound** for print runs ≥ 16 pages. Spine wide enough for spine-text on the 36-page Print Master.
- **Saddle-stitched** for the 12-page Digital-equivalent print preview run.
- **Lay-flat** binding (Otabind or PUR adhesive) for the 36-page edition. Critical: the seller will spread it on the dining table.

### 8.3 Packaging
- **Custom matte-black slim box** (LJ Hooker pre-listing box, [reference](https://trustyboxes.com.au/portfolio-item/lj-hooker-real-estate-pre-listing-presentation-box/)) — but better.
- Single embossed Fields F mark on the lid, copper-foil.
- Inside: report, sealed envelope (containing the listing range on a single card), and a Fields business card.
- Weight is part of the experience. The package should feel deliberate when handed over.

### 8.4 Print runs
- One report per home. No bulk printing.
- We hold a digital print proof for sign-off before the run.
- **Local print partner:** start with a Gold Coast-based studio (boutique, not chain). Specs a designer can deliver to without Will's intervention.

---

## 9. Visual signature audit — what should be unmistakable on a 5-second flip

If the seller's friend picks the report up off the dining table, after five seconds of flipping, they should be able to identify:
1. **The cover treatment** — copper callout, twilight hero photo, restraint.
2. **The grass-on-copper colour pairing** — never seen in another agent's report.
3. **Tabular precision** — line-item adjustments, monospaced numbers, footnoted sources.
4. **The lifestyle narrative page** — full page of body prose, magazine register.
5. **The methodology page** — citations, dataset counts, source dates.

If two of these five aren't immediately legible, the visual system has failed.

---

## 10. What we do *not* do (visual)

- No agent-headshot circle on the cover.
- No "Sold!" stickers anywhere.
- No watermarked agent name or contact details on every page (Privacy strip on the cover footer is enough).
- No flag icons, address pins, "FOR SALE" graphics on the cover.
- No multi-colour rainbow charts. (We use 2–4 colours from the palette per chart, ordered by importance.)
- No emoji in any context (per project policy).
- No stock real-estate templates rebranded with our palette.

---

*Owner: Will Simpson · Updated 2026-05-06 · Reading order: read after `04_content_modules.md`, before `06_production_plan.md`.*
