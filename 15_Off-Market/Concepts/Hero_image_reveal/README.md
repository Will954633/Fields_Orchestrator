# Hero Image Reveal — "Pixel Reveal"

A hero photo that resolves out of coarse pixel blocks, the front sweeping from the
bottom-left corner toward the top-right. Built 2026-08-02 as a concept for property
hero images.

## ▶ Open the demo

**Interactive artifact (private to your Claude account, opens anywhere):**

https://claude.ai/code/artifact/b831909e-9faa-4e52-bb62-99e70b99ed3d

Three real listing photos, live controls for origin, block size, duration, front shape,
scatter, trail and coarseness.

**Or open the offline copy** — `pixel-reveal-demo.html` in this folder is fully
self-contained (photos embedded as data URIs, no network needed). Download it and
double-click, or serve it locally:

```bash
cd /home/fields/Fields_Orchestrator/15_Off-Market/Concepts/Hero_image_reveal
python3 -m http.server 8899   # then open http://<vm-ip>:8899/pixel-reveal-demo.html
```

`mid-reveal-still.png` is a frame grabbed mid-sweep if you just want to see the look.

## How it works

Three ideas, and that's the whole effect:

1. **A delay field.** The image is cut into a grid of cells. Each cell's start time comes
   from its distance to the origin corner — blended between a *diagonal projection*
   (a straight wall sweeping across) and *true radial distance* (a circular bloom out of
   the corner), then jittered so the edge breaks up instead of marching in lockstep.

2. **Resolving, not fading.** The image is pre-rendered at a stack of pixelation levels
   (full res, 2px, 4px … 64px blocks). As a cell's own clock runs it walks *down* that
   stack, so it sharpens from chunky blocks to full detail. Nearest-neighbour upscaling
   (`imageSmoothingEnabled = false`) keeps the blocks hard-edged and globally aligned.

3. **A settled layer.** Once a cell finishes it is blitted into an offscreen canvas and
   never touched again. Each frame draws that one canvas plus only the cells currently
   in flight — so halving the block size barely changes frame cost.

## Files

| File | What |
|------|------|
| `PixelReveal.tsx` | Drop-in React component, no dependencies. Typechecks clean against the website's `tsconfig.app.json`. |
| `pixel-reveal-demo.html` | Self-contained interactive demo — same page as the artifact, photos embedded. |
| `pixel-reveal-demo.template.html` | The demo's source, with `__IMG_A__` / `__IMG_B__` / `__IMG_C__` placeholders instead of the base64 blobs. Edit this, then re-inject (see below). |
| `photos/` | The three resized listing photos the demo embeds. |
| `mid-reveal-still.png` | A frame captured mid-sweep. |

To rebuild the demo after editing the template:

```bash
cd /home/fields/Fields_Orchestrator/15_Off-Market/Concepts/Hero_image_reveal
python3 -c "
import base64
t = open('pixel-reveal-demo.template.html').read()
for tok, f in (('__IMG_A__','photos/pr_a.jpg'),('__IMG_B__','photos/pr_b.jpg'),('__IMG_C__','photos/pr_c.jpg')):
    t = t.replace(tok, 'data:image/jpeg;base64,' + base64.b64encode(open(f,'rb').read()).decode())
open('pixel-reveal-demo.html','w').write(t)"
```

Source photos: `A1_huntingdale` and `C1_windemere` from
`03_Facebook/CTA_Book_Before-you-list/photos/`, `house.jpg` from
`09_Appraisals/Alex_Working_Files/`.

## Usage

```tsx
import PixelReveal from "./PixelReveal";

<PixelReveal src={property.heroPhoto} alt={property.address} />
```

Everything is optional beyond `src`:

| Prop | Default | Notes |
|------|---------|-------|
| `origin` | `"bl"` | `bl` / `br` / `tl` / `tr` / `c` |
| `tile` | `28` | Cell size in device px |
| `duration` | `2600` | Total sweep, ms |
| `shape` | `0.55` | `0` = straight diagonal wall, `1` = circular bloom |
| `scatter` | `0.22` | Randomises each cell's turn |
| `trail` | `0.26` | How long one cell takes to sharpen, as a fraction of `duration` |
| `levels` | `5` | Cell starts at `2^(levels+1)` px blocks — 64px |
| `ground` | `#0d1611` | Colour the photo emerges from (Fields grass-dark) |
| `frontTint` | `#c97a57` | Warm glint at the leading edge (Fields copper). `null` to disable |
| `revealOnScroll` | `true` | Waits for the canvas to scroll into view |
| `replayKey` | — | Change this value to replay |

## Notes before shipping it

- **CORS.** The canvas reads pixel data, so the image must be same-origin or served with
  CORS headers. Azure blob photos need `Access-Control-Allow-Origin` set.
- **Reduced motion.** Respected — the final image is drawn immediately, no animation.
- **LCP.** A canvas is not an `<img>`, so this will not be picked up as the Largest
  Contentful Paint element and it delays the hero appearing. On a page where hero
  load speed matters for SEO, render a real `<img>` and overlay the canvas, or keep
  this for below-the-fold moments.
- **Accessibility.** The canvas carries `role="img"` and `aria-label={alt}` — always
  pass a real `alt`.
