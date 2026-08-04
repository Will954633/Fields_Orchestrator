# Off-Market Discovery Deck — V3

Working directory for the V3 rebuild. Everything is built and iterated **locally
here**; there is one push to the website repo at the end, not a push per change.

Brief (Will, 2026-08-02):

1. On load the reader sees the **matrix curtain** from
   `Concepts/Matrix_Recreation/code-sequence-local.html`.
2. The rain **stops the moment the address has printed** — not 14s later after
   the ERROR/ABORT tail.
3. The page then **auto-scrolls to card 01**.
4. Remove the "we found your home" beat that the matrix currently carries.
5. Cards **03 and 04** carry a **hatch-drawing reveal** in the manner of
   `Concepts/Near_beach_palm_reveal` — the pandanus for beachside, and one of
   the other eight drawings for the other lead angles.

---

## What V3 is changing, against what exists

The live deck (`DiscoveryDeck.tsx`, 518 lines) has **no intro animation at all**
and **no image anywhere** — card 01 is rendered visible on first paint and the
reader lands directly on it. So V3 adds two genuinely new primitives:

| New | Where it lands |
|---|---|
| A full-viewport intro that owns the first ~6s and then hands off | before card 01, outside `sectionRefs` |
| An angle-selected drawing that reveals beside the copy on cards 03/04 | the `reveal` and `explanation` cards |

`lead_angle` is already emitted at the top level of every
`system_monitor.offmarket_discovery` doc (`emit_json.py:307`) and is **currently
unread by React**. That is the hook for media selection — no builder change is
needed to know which drawing a home gets.

**Index caveat, carried from the survey:** the chapter label prints `card.n`
(absolute) over `doc.cards.length` (rendered), and the IntersectionObserver
indexes `sectionRefs` positionally. Any intro section added to `<main>` must
stay out of `sectionRefs` or it shifts every observer index and corrupts the
rail plus the `rendered_index` on all card analytics.

---

## The reveal technique does not generalise — measured, not assumed

The pandanus works because of a specific property: it is a **graphic object on
blank paper**. The build inverts it to cream-on-black, so it dissolves into the
deck's ground with no frame and no visible edge.

Running the same pipeline over the other eight drawings and rendering stills at
deck theme (`--paper #000000 --ink #E6DDD2`) shows that property is rare:

| Drawing | Ink coverage | Inverted onto black |
|---|---|---|
| `whale.png` | 23.1% | ✅ Works. Floats exactly like the pandanus. |
| `Walk to school.png` | 37.1% | ❌ Floats, but inverts the **faces** — negative eyes and teeth, reads as ghostly. |
| `Golf_course.png` | 67.4% | ❌ Photographic negative in a hard rectangle. |
| `Parkland.png` | 76.8% | ❌ Same — sky goes black, trunks go white. |
| `water_adjacent .png` | 85.1% | ❌ Same. |
| `Robina_Pavillion.png` | 89.1% | ❌ Same. |
| `bushland.png` | 90.1% | ❌ Same. |

A full-bleed tonal scene cannot be inverted onto black — the sky is the largest
area of paper, so inversion turns it into the largest area of ink. Rendered
**positive** (black ink on its own cream paper) every one of them looks right;
it just becomes a bright plate sitting on a black deck rather than a drawing
floating in it.

So the drawings split into two media languages, and the split is a property of
the artwork, not a preference:

- **Emblem** — pandanus, pandanus fruit, whale. Cream on black, no frame.
- **Plate** — the five scenes (+ the school walk). Positive, on its own paper.

What a drawing must be in order to work is written up, with the measured
thresholds and a one-command gate, in **[SOURCE_ART_SPEC.md](SOURCE_ART_SPEC.md)**
— including the six replacement drawings that would cover 76% of decks.

### Ordering

`build_master.py` ordered the reveal by geodesic distance from the base of the
trunk, travelling through the ink — which is why the palm *grows*. A parkland or
a lake has no trunk; seeding "densest ink low in the frame" picks an arbitrary
shrub. Scenes use `develop` (darkest ink first — structure lands, hatch fills in
behind it), which keys off density alone and never touches the growth channel.
`build_reveal.py --order none` therefore skips the Dijkstra entirely: a scene
builds in ~11s instead of minutes, and nothing is lost.

---

## Angle → drawing

Distribution across all 18,070 built decks, with what each angle currently has:

| Share | Decks | Lead angle | Drawing | Language |
|---|---|---|---|---|
| 32.4% | 5,862 | `parkland` → park | `Parkland.png` | plate |
| 12.8% | 2,310 | `school_walk` | `Walk to school.png` | plate (must not invert) |
| 12.6% | 2,271 | `water_adjacent` → lake | `water_adjacent .png` | plate |
| **12.4%** | **2,235** | **`land_prestige`** | **— none —** | |
| 9.3% | 1,689 | `beachside` | `Hatch_Sketch_Pandanas_Palm.png` | emblem ✅ built |
| **8.3%** | **1,493** | **`market_context`** | **— none —** | |
| 3.0% | 550 | `parkland` → golf course | `Golf_course.png` | plate |
| 4.1% | 740 | `scarcity` / `thin_competition` | — none — (abstract) | |
| 2.7% | 494 | `parkland` → bushland / reserve | `bushland.png` | plate |
| 1.3% | 239 | `parkland` → reserve / open space | `Parkland.png` (shared) | plate |
| 0.5% | 105 | `water_adjacent` → creek / river | `bushland.png` (has a creek) | plate |
| — | ~0 | `water_views` | `whale.png` | emblem |
| 0.2% | 82 | gardens, wetland, scale, prestige_value | — none — | |

**Superseded 2026-08-02** by the v2 emblem set (gum, satchel, reeds, retriever,
banksia) — five single subjects on blank paper, all of which clear the gate and
render as true pandanus-language emblems. The current mapping and what remains
outstanding live in **[SOURCE_ART_SPEC.md §5](SOURCE_ART_SPEC.md)**.

Coverage is now **84%** of the 18,070 decks. One drawing outstanding: a golf
flag and pin (3.0%). `market_context` (8.3%), `scarcity` and `thin_competition`
(4.1%) are deliberately text-only — abstract angles with no object to draw.
`Robina_Pavillion.png` has no angle.

---

## Layout

Per the beach-card simulation
(`Concepts/Near_beach_palm_reveal/offmarket_beach_card.html`), which is the
reference implementation:

- Cards 02/03/04 switch from the deck's single 40rem column to a **two-column**
  grid (`.innerWide`, 68rem, text left / media right). Card 02 keeps an empty
  right cell so the text column's left edge does not jump between cards.
- The drawing is held back `1250ms` after the copy starts revealing, so it
  arrives as the last line settles rather than competing with it.
- The clip is attached on **first scroll intent**, not on load — attaching it
  when card 02 intersects is no deferral at all, because card 02 *is* the view
  at load.
- Card 04 continues card 03: the pandanus **fruit detaches** from the finished
  drawing, travels across the page on a canvas layer and comes to rest as
  foreground beside the card-04 copy. The five plate drawings have no equivalent
  detachable element — see open questions.

---

## Layout of this directory

```
Page_Redesign_V3/
├── PLAN.md                  ← this file
├── intro/                   ← the modified matrix curtain
├── reveals/
│   ├── build_reveal.py      ← generalised build_master.py (any source, any ordering)
│   ├── render_reveal.js     ← generalised render_video.js (--html <page>)
│   ├── reveal.template.html ← copied from Concepts, so V3 is self-contained
│   ├── sources/             ← the 9 drawings
│   └── out/                 ← per-drawing ink mask + standalone page + renders
├── preview/                 ← the full local V3 deck
└── angle_media.yaml         ← lead angle → drawing + language (to be written)
```

Rebuild any drawing:

```bash
python3 build_reveal.py --all --only parkland whale
node render_reveal.js --html out/whale.html --mode develop \
     --paper "#000000" --ink "#E6DDD2" --grain 0 --vignette 0 --out out/whale_deck
```

---

## Open questions for Will

1. **What exactly comes out of the matrix.** Proposal: keep `searching...` ×2,
   drop `Found it`, print the address + locality, stop there — cutting
   `There's a problem…` / `ERROR` ×3 / `ABORT` entirely, since the reader is
   about to be handed a report rather than a warning.
2. **Card 01's headline.** The matrix will have just printed the address; card
   01 currently opens "We found your home." over the same address. One of the
   two has to go — which?
3. **Plate vs emblem** for the five scene drawings, or regenerate them as
   emblems (a single spotted gum, a lone reed clump, one golf flag) so the whole
   deck speaks one language.
4. **The school-walk drawing** has identifiable human faces — provenance and
   whether it can carry 12.8% of decks.
5. **`land_prestige` (12.4%) and `market_context` (8.3%)** have no drawing.
6. **Card 04** — what continues the drawing for the five plates, given only the
   pandanus has a detachable fruit.

---

## Decided (Will, 2026-08-03)

1. **Matrix ends at the address** — `searching...` x2 -> street -> locality -> rain
   stops -> scroll to card 01. `Found it` and the `There's a problem / ERROR /
   ABORT` tail are cut. **Built.**
2. **Card 01 headline** -> **"Then we went to work."** The address moves above it
   as a quiet anchor, so it reads as the matrix's address settling into the page.
   Body, credibility figures and the "What was interesting?" hook are unchanged.
   **Staged, not yet applied** — see the push checklist.
3. **Golf flag** delivered and built (`golfflag`, positive polarity, cast shadow
   masked). Coverage now **87%** of decks.

## Done

- **Matrix intro** stopping at the address, handing off to card 00 → card 01.
  11.0s at the default; `?speed=` scales the whole thing (9.1s at 0.3).
- **Per-home recognition tokens** (`intro/intro_tokens.py`). Was hard-coded to
  Burleigh Waters; now cadastral streets, derived arterials and the deck's own
  verified POIs, per home, in 0.8s.
- **Card 00 "We found your home."** standalone — Will's pick, 2026-08-03. The
  merged variant was built, compared and removed rather than left as dead code.
- **All eight emblems final**, 87% of decks. Five grow, three resolve.
- **The full deck, cards 00–10**, rendering from the real
  `offmarket_discovery` document rather than a mockup. `angle_media.yaml` picks
  the drawing off `lead_angle`, sub-routing on the OSM kind so a golf course
  gets the flag and bushland the banksia.
- **Ten worked examples**, desktop and mobile, at `preview/examples.html`.

## Still open

- **The detach-and-travel to card 04 — BUILT, for beachside only** (2026-08-04).
  `reveals/build_fruit_sprite.py` cuts the sprite out of
  `sources/Pandanas_Palm_Fruit.png`; `preview/fruit_roll.js` runs it. Live on
  `23-bellbird-avenue-burleigh-waters` and `5-comet-court-burleigh-waters`; every
  other deck gets no script at all rather than a disabled one.

  Still open for the other seven: only three of eight emblems have a plausible
  detachable element — this fruit, the golf ball and the dog's ball. The gum,
  reeds and banksia each need one drawn; the satchel and whale have none, so
  those two need a different transition. Will's call was to prove the motion on
  one angle first and decide the rest after seeing it.

  **Patched**, using `fruit_patch.png` ported from the original beach-card
  concept (`Concepts/Near_beach_palm_reveal/`) — foliage cloned from the video's
  own pixels, laid over the crown the instant the fruit detaches. Our clip is a
  different size (900x976 vs 1024x1110) but the same framing, so the concept's
  fractions carry over; verified by compositing it onto our own last frame first.
  The sprite is not drawn at all before that moment, so the reader never sees two
  fruit in one place.
- **Media weight.** Eight MP4s, 0.7–2.0 MB each. Attached on first scroll
  gesture so a bounce costs nothing, but the ink masks are *smaller* than the
  clips, so rendering the reveal live on canvas may be the better call at port
  time. Decide then, not now.

## Data issue for the builder (not V3)

`16-moorabbin-place-robina` shows both "Moorabbin Park" (102m) and "Moorabin
Park" (156m) on its doorstep list — near-duplicate OSM entries, one misspelled.
It is on the live deck today and will affect others. Wants a dedupe pass in
`assemble.py`.

## Push checklist (single push, at the end)

- [ ] `copy.yaml` -> `card_01_recognition.headline` = "Then we went to work."
      **Do not apply early** — until the intro ships, card 01 would open on that
      line with nothing before it, and it reads as a non-sequitur.
- [ ] `emit_json.py` -> emit `intro_tokens` (see above)
- [ ] Port `intro/matrix-intro.html` to a React component; keep it OUT of
      `sectionRefs` or every IntersectionObserver index shifts and the rail plus
      `rendered_index` on all card analytics go wrong.
- [ ] Card 03/04 media, driven off the existing top-level `lead_angle`
- [ ] `angle_media.yaml`
