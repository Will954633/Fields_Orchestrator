# Pandanus — pixel reveal

A pixel-reveal animation that builds a black-and-white version of
`Hatch_Sketch_Pandanas_Palm.png`. The drawing arrives as coarse pixel blocks
that resolve into the fine hatch as they settle, so the ink appears to grow
rather than simply fade in.

Open `index.html` — it plays on load and is fully self-contained (no server, no
network, no build step).

## Files

| File | What it is |
|---|---|
| `index.html` | The animation. Generated — open it directly, edit `reveal.template.html` instead. |
| `reveal.template.html` | Source of the animation. `{{INK_DATA_URI}}` / `{{IMAGE_W}}` / `{{IMAGE_H}}` are filled in by the build. |
| `build_master.py` | Source image → black-and-white masters → `index.html`. |
| `render_video.js` | Headless-Chrome frame renderer → MP4 / GIF / stills. |
| `palm_bw.png` | Flat black-and-white version (white paper, black ink). Generated. |
| `palm_ink_alpha.png` | The same ink as an RGBA mask (RGB black, alpha = coverage). Generated. |
| `palm_reveal_growth.mp4` / `.gif` | Rendered animation, light. Generated. |
| `palm_reveal_growth_dark.mp4` | Rendered animation, dark. Generated. |

## Rebuild

```bash
python3 build_master.py          # re-derives the B&W masters and index.html
node render_video.js --gif       # re-renders the video
```

`build_master.py` must be re-run after any edit to `reveal.template.html` —
`index.html` is the generated artefact.

## Reveal modes

| Mode | Order |
|---|---|
| `growth` *(default)* | Outward from the base of the trunk — the tree grows. |
| `develop` | Darkest ink first: structure lands, then the light hatch fills in. |
| `dissolve` | Random pixels across the whole drawing. |
| `rise` | Bottom to top. |
| `sweep` | Diagonal wipe. |

Every mode also takes a `scatter` amount, which blends noise into the ordering
so the leading edge breaks up instead of advancing as a clean front.

## Controls

The panel under the canvas is live: mode, light/dark paper, pixel size,
duration, scatter, mosaic strength (how blocky a pixel is before it resolves),
and softening (how long a pixel takes to settle). The scrubber inspects any
moment; `space` replays; **Save frame** exports the current canvas as a PNG.

Every control is also a URL parameter, which is how the renderer drives it:

```
index.html?mode=develop&theme=dark&block=8&dur=7000&chaos=0.4
```

## Rendering

```bash
node render_video.js                                  # 1024px, 30fps, ~5s + hold
node render_video.js --mode develop --dur 7000 --gif
node render_video.js --stills 6 --width 700           # contact sheet of moments
node render_video.js --width 720 --fps 60 --hold 1.5
```

The renderer loads `index.html?capture=1`, which replaces the playback loop with
`window.__reveal.frame(t)` and steps frames by hand. Ordering comes from a
seeded RNG, so the rendered video is frame-identical to the preview and to any
re-render — nothing depends on how fast the machine draws.

## How the reveal works

`build_master.py` desaturates the source, sets the paper (a flat 254, not the
brightest pixel — a percentile white point would leave a 1/255 haze over the
whole background) to pure white and the deepest stroke to pure black, flattens
the residual haze so blank paper is exactly blank, and crops to the ink. It
writes the ink as an **alpha mask** rather than a black-on-white image, so the
animation composites strokes onto any paper colour without painting white
squares over the background.

The animation grids that mask into blocks, discards blocks with no ink, and
gives each remaining block a sort key from the chosen mode blended with noise.
After sorting, a block's reveal threshold is just its rank ÷ count — so pacing
stays even however the key happens to be distributed, and the mode only decides
the *order* things appear in.

Each frame paints in three bands: blocks that finished settling are committed
once to a persistent canvas, blocks mid-settle are redrawn as a flat pixel
cross-faded into the real hatch, and everything ahead is untouched. Only the
narrow in-flight band is redrawn per frame, which is what keeps it smooth at
1024px with ~40k live blocks.
