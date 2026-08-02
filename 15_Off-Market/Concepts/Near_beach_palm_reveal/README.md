# Near-beach palm reveal

Concept work for the off-market Discovery Deck: a Pandanus drawing that reveals
itself, drops a fruit, and rolls that fruit across the screen to carry the
reader into the next card.

Two things live here.

**1. The card simulation** — what this is all for.
<https://vm.fieldsestate.com.au/concepts/off-market/Near_beach_palm_reveal/offmarket_beach_card.html>

**2. The reveal tool** — a standalone lab for the palm animation, with live
controls and a video renderer.
<https://vm.fieldsestate.com.au/concepts/off-market/Near_beach_palm_reveal/index.html>

Both are static files with no build server. Anything dropped in this folder is
live on next request — see the `/concepts/` nginx block. **A local file path is
not openable in a browser**; use the URLs above.

---

## The card simulation

Simulates `/off-market/:slug` when the **beachside** lead angle fires. Three
cards: `02 hook` → `03 reveal` → `04 explanation`.

Copy is the real approved copy, not invented — `copy.yaml:75`
(`card_02_hook.hooks.beachside`) and `copy.yaml:153-158` (`card_03.beachside`).
Design tokens, card anatomy and the 900ms reveal timing are taken from
`src/pages/OffMarketPage/discovery/{DiscoveryDeck.tsx,discovery.module.css}`.

The sequence, once card 03 is on screen:

1. Copy staggers in line by line.
2. `MEDIA_DELAY_MS` (1250ms) later the palm arrives and draws itself (~6.4s).
3. The fruit detaches from the crown and falls — `FALL_MS` 1150ms.
4. The page **scrolls itself** to card 04 over `ROLL_MS + 400`, and the fruit
   rolls toward the viewer and away to the left as it goes.
5. It settles bottom-left; card 04's copy sits to its right.

### Things that will bite you

- **The live deck is single-column** (`max-width: 40rem`) and contains no video,
  canvas or image in any card. The side-by-side text/media split here is a **new
  layout primitive**, not an existing pattern. Decide on it before shipping.
- **The auto-scroll takes over the reader's scroll.** It fires once, only from
  card 03, never under `prefers-reduced-motion`, and any wheel / touch / key /
  pointer input hands control straight back. Those guards are the feature — do
  not drop them. It also forces `scroll-behavior: auto` for the duration;
  per-frame `scrollTo` against CSS smooth scrolling makes the two fight.
- **Assets are deferred deliberately.** The clip has no `src` in markup and
  `preload="none"`; it attaches on the reader's first input. The sprite sheet
  loads via `window.__loadSprites()` when card 03 appears. With them eager, first
  paint was 3.61 MB before the reader scrolled at all; it is now 0.04 MB. Note
  that attaching on *card 02 visible* defers nothing — card 02 **is** the view at
  load — and a backstop observer with a positive bottom `rootMargin` fires
  immediately too, because card 03 begins exactly at the fold.
- **Play is triggered by the media being on screen, not the card.** The card is
  100svh+, so on a phone "card visible" happens while the palm is still ~1000px
  below the fold; it would draw itself and finish unwatched.
- **The roll is a rate-limited follow of the scroll**, not a scrub and not a
  timer. Pure scrubbing makes the roll's speed the reader's scroll speed and one
  wheel flick skips the whole thing. Pure time-driving desyncs it from where the
  reader actually is.

---

## Files

| File | |
|---|---|
| `offmarket_beach_card.html` | The card simulation. Hand-edited. |
| `index.html` | The reveal lab. **Generated** — edit `reveal.template.html`. |
| `reveal.template.html` | Source of the lab. `{{INK_DATA_URI}}` / `{{IMAGE_W}}` / `{{IMAGE_H}}` filled at build. |
| `build_master.py` | Sketch → B&W masters + growth order → `index.html`. |
| `render_video.js` | Headless-Chrome frame renderer → MP4 / GIF / stills. |
| `build_fruit_sprites.py` | Fruit sketch → rolling sprite sheet. |
| `pandanus_fruit.js` | Draws the fruit: sprite sheet, with a procedural fallback. |
| `Hatch_Sketch_Pandanas_Palm.png` | Source drawing of the tree. |
| `Other images/Pandanas_Palm_Fruit.png` | Source drawing of the fruit. |
| `palm_reveal_deck.mp4` | The clip the card uses. Generated. |
| `fruit_sprites.png` + `.json` | 24-frame barrel roll. Generated. |
| `fruit_patch.png` | Covers the fruit's spot on the tree once it detaches. Generated. |
| `palm_bw.png`, `palm_ink_alpha.png` | B&W master and ink mask. Generated. |
| `palm_reveal_growth*.mp4/.gif` | Earlier standalone cuts on `#111216` paper. |
| `fruit_fall_feasibility/` | Working images from scoping the fruit. Not used at runtime. |

## Rebuild

```bash
python3 build_master.py        # after ANY edit to reveal.template.html
python3 build_fruit_sprites.py # after changing the fruit's look or size
node render_video.js --mode growth --theme dark --paper 000000 \
  --grain 0 --vignette 0 --block 1 --hold 1.4 --crf 21 --out palm_reveal_deck
```

That render command is the one that produces the card's clip: `paper 000000` +
no grain/vignette so it sits on the deck's black with no visible panel edge.

---

## The reveal

`build_master.py` desaturates the sketch, sets the paper to pure white and the
deepest stroke to pure black, and crops to the ink. Two details worth keeping:

- The paper is a flat **254**, not 255, and 71.75% of pixels sit there. A
  percentile white point leaves a 1/255 haze over the whole background, which
  makes every "empty" block count as ink.
- The ink is written as an **alpha mask**, not black-on-white, so strokes
  composite onto any paper colour without painting white squares over it.

The animation grids that mask into blocks, drops blocks with no ink, and gives
each a sort key from the chosen mode blended with noise. After sorting, a
block's threshold is its rank ÷ count — so pacing stays even however the key is
distributed, and the mode decides only the *order*.

Painting writes bytes straight into an `ImageData` rather than issuing canvas
calls per block. That is what makes a **1px** reveal possible: block count grows
with the square as size shrinks, and the old per-block path measured 253ms/frame
(4fps) at 1px against 20ms (50fps) now. It also removed the tint pass — the ink
colour is written directly into RGB.

### Modes

| Mode | Order |
|---|---|
| `growth` *(default)* | Outward from the base of the trunk. |
| `crystal` | Geodesic **through the ink** — accretes root → trunk → branch → frond, so a frond can only appear after the branch that carries it. Defaults to `scatter 0.10`; heavy scatter breaks the growth front into snow. |
| `develop` | Darkest ink first. |
| `dissolve` | Random. |
| `rise` | Bottom to top. |
| `sweep` | Diagonal wipe. |

`crystal` needs the geodesic order, which `build_master.py` bakes into the mask
PNG's RGB channels (R high byte, G low, 16-bit) — they were zeroed before, so it
is free at runtime, but it does take `palm_ink_alpha.png` from 603 KB to 1457 KB
and `index.html` to ~1.9 MB. That only affects the lab page; the card uses the
rendered clip. Drop the growth-order bake if you want that weight back.

### Controls

The panel under the canvas is live, and every control is also a URL parameter —
which is how the renderer drives it:

```
index.html?mode=crystal&theme=dark&block=4&dur=7000&chaos=0.4
```

`paper`, `ink`, `grain` and `vignette` can be overridden too, to match the
animation to whatever page it will sit on.

### Rendering

```bash
node render_video.js                          # 1024px, 30fps, ~5s + hold
node render_video.js --stills 6 --width 700   # contact sheet of moments
node render_video.js --crf 23 --width 768     # smaller file
```

The renderer loads `index.html?capture=1`, which swaps the playback loop for
`window.__reveal.frame(t)` and steps frames by hand, so output is frame-exact
regardless of machine speed. Ordering comes from a seeded RNG, so a re-render is
identical to the preview.

**On file size:** the clip is 1024px but displayed at 469px (desktop) / 333px
(mobile). `--width 768` gives ~1.7 MB and `640` ~1.2 MB against 2.7 MB at 1024.
Fine-grained reveals compress far worse than chunky ones — the 1px cut was
3.7 MB at crf17, hence the crf21 default. **VP9 is worse here** (4.2 MB at
1024/crf34); the reveal noise defeats it. Do not assume the newer codec wins.

---

## The fruit

`build_fruit_sprites.py` wraps the real drupe texture from
`Other images/Pandanas_Palm_Fruit.png` around a sphere and renders 24 frames of
one full roll. The runtime picks a frame from the roll angle.

Procedural drawing came first and never matched the hand of the tree. A set of
separately-drawn frames would strobe, because a rolling object has to be
pixel-consistent frame to frame. Here every frame comes from one source image
through one 3D mapping, so consistency is structural.

- **It rolls about its LONG axis, like a barrel** — a pandanus head is a rounded
  prolate and is far too fat to tumble end over end. So the long axis lies
  horizontal *along* the roll axis. The silhouette barely changes while rolling
  and only the surface moves, which is what reads as rolling.
- **The texture comes from a strand-free patch**, not the whole fruit. Bracts
  hang across the drawing's face and would smear round the sphere.
- **The drawing's own lighting is divided out** before re-lighting per frame,
  or the highlight rotates *with* the surface instead of staying with the light.
- **The silhouette is displaced by drupe height** sampled at the rim, so the
  outline is chewed up by the drupes actually sitting on the edge. Displace by
  the raw texture instead of a drupe-scale height map and it comes out looking
  like a chestnut.

Tuning lives at the top of the script: `DRUPES_ACROSS` (8 across the diameter),
`BUMP` (0.042 — how far a drupe stands proud), `FRAMES`, `TILE`. `BASE_R` (0.88)
is how much of the tile the body occupies; the rest is headroom for the bumps,
and the runtime scales by `1/baseR` from `fruit_sprites.json` so apparent size is
unchanged.

The fruit's resting size is set in `offmarket_beach_card.html` (`restState`).
The honest number comes from the drawing: the tree is ~6m off and the fruit is
~22px there, so a fruit a metre away is ~150px — not the 306px it started at.
Its resting *position* is anchored to card 04's own left column, not to a
fraction of the viewport, or it drifts away from the copy as the window widens.
