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

---

# Version 2 — Homeowner sequence

**View:** https://vm.fieldsestate.com.au/concepts/off-market/Matrix_Recreation/homeowner-sequence.html

Same rain engine, new alphabet and a scripted payoff.

## Why not katakana, and why not 0/1

- **Katakana** carries the reference but says nothing to a Burleigh Waters
  homeowner — it's set dressing from someone else's story.
- **Binary** has only two glyph shapes, so it has no visual texture, and 0/1
  rain reads as generic stock-footage "hacking".
- **What's here instead:** the raw material of a property record — digits
  (prices, land size, days on market) weighted 3:1 over capitals, plus
  `$ % m² ▲ ▼`. Unmirrored, because this is meant to read as data.

The strongest touch is the **token streams**: ~16% of streams carry a real
string that stamps one character per row as the head falls, so it reads
*vertically* out of the noise and then sits still while the trail decays —
`BURLEIGH WATERS`, `4220`, `SOLD`, `607M2`, `DOM 34`, `OFF MARKET`.
The owner sees their own suburb surface before a single word is typed.

## Sequence

| t | Beat |
|---|---|
| 0–3.0s | Full-field rain |
| 3.0–4.6s | Field contracts to a band on the left (34% width) and dims 42%; scrim fades in |
| 4.6s+ | Terminal types, left-aligned, over the narrowed field |

Typed lines, each below the last, with a blinking block cursor:

```
searching...          ← dots land one at a time, 380ms apart
searching...          ← again, 1s later
Found it
3 Avocet Avenue       ← white, bold
Burleigh Waters, QLD 4220
There's a problem...  ← amber
ERROR                 ← red, each triggers an alarm wash
ERROR
ERROR
ABORT                 ← red, tracked out, screen shake + rain surge + flicker
```

Holds 4.2s on ABORT, then loops. `R` replay · `L` toggle loop · `F` fullscreen.

## Per-owner address

The address is overridable by query string, so one file serves every owner —
useful if this is ever wired into the off-market funnel, where pages are
already per-address:

```
homeowner-sequence.html?street=12%20Curlew%20Court&locality=Robina,%20QLD%204226
```

Falls back to 3 Avocet Avenue. Input is control-character stripped and length
capped, and inserted via `textContent` (never HTML).

## Two things to decide before this goes anywhere public

1. **A real address next to "There's a problem / ERROR / ABORT."** Fine as a
   concept or for an owner's own page. If it runs as a broad ad against real
   addresses, it asserts something negative about an identifiable home. Worth a
   deliberate call rather than inheriting it from the demo.
2. **The `$1,285,000` / `$970,000` tokens in the rain** are unattached to any
   address, so they don't breach the no-single-valuation-in-headlines rule —
   but they are dollar figures on screen. Easy to drop from `TOKENS` if you'd
   rather not carry them.
