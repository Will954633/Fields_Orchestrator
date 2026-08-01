# Matrix Digital Rain — recreation

**View:** https://vm.fieldsestate.com.au/concepts/off-market/Matrix_Recreation/index.html

Single self-contained HTML file. No build, no dependencies, no network calls —
drop it anywhere and it runs.

## What makes it read as *the* effect

The details that separate this from a generic "falling green text" demo:

| Detail | How it's done |
|---|---|
| **Mirrored glyphs** | The film's typeface (Simon Whiteley, 1999) is half-width katakana traced from Japanese cookbooks and flipped. Every glyph is drawn with `scale(-1, 1)`. |
| **Glyph mix** | Katakana weighted 2:1 against Latin numerals plus a little punctuation — the ratio the source frames read at. |
| **White leading cell** | The head of every stream is blown out to near-white, not green. This is the single strongest cue. |
| **In-place churn** | Glyphs rewrite themselves *while lit* rather than only at spawn. Static trails look dead. |
| **Sparks** | ~3.5% of rewrites flare white for a few frames, giving the shimmer that travels through the field. |
| **Overlapping streams** | Streams are not one-per-column — several share a column and composite by max brightness, producing the film's stacked, uneven runs. |
| **Speed spread** | `pow(random, 1.7)` — many slow drifters, few fast runners. Uniform speeds look mechanical. |
| **Phosphor bloom + scanlines** | These are CRT monitors in the film, not flat panels. |

The field is **seeded mid-flight** on load, so it opens already raining rather
than filling in from an empty screen over ~15 seconds.

## Controls

`C` panel · `F` fullscreen · `R` reset · `Space` pause

Panel exposes glyph size, fall speed, density, trail length, mutation rate and bloom.

## Implementation notes

- **Glyph atlas.** Every glyph is pre-rendered at 24 brightness tiers into one
  offscreen canvas. The animation loop is pure `drawImage` — no `fillText`, no
  per-glyph transforms at runtime.
- **Brightness buffer.** Streams composite into a `Float32Array` per cell
  (`max`), then a single pass draws it. Overlapping streams blend instead of
  fighting over the same cell.
- **Bloom is blurred inside the low-res canvas**, not via CSS. A CSS
  `filter: blur()` on a full-screen layer rasterizes at viewport size; doing it
  at 1/5 resolution is ~25× cheaper for the same look. Measured on this VM
  (software rasterization, no GPU) at 1080p: **8 fps → 32 fps**. Safari < 16.4
  has no canvas `filter` and falls back to the CSS path automatically.
- Scanlines use plain alpha rather than `mix-blend-mode: multiply` — identical
  over a black scene, one less full-screen blend pass.
- Honours `prefers-reduced-motion` by slowing the fall and damping the churn.
