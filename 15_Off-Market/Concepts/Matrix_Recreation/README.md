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

---

# Version 3 — In-code sequence

**View:** https://vm.fieldsestate.com.au/concepts/off-market/Matrix_Recreation/code-sequence.html

No HTML text layer at all. The message is written **into the rain's own
character grid** — same cells, same glyph atlas, same bloom — so the words are
part of the code rather than sitting on top of it. Rain keeps streaming to the
left and right of every printed line.

## Sequence

| t | Beat |
|---|---|
| 0–1.4s | Field switches **ON, left → right** |
| 1.4–4.0s | Full field |
| 4.0–6.2s | Field switches **OFF, right → left**, easing out |
| 6.2s+ | Field is fully dark; the message prints into the grid on a clear screen |

Each column extinguishes over 0.45s as the front passes, so it reads as
switching off rather than snapping off. Same script, timing and payoff as v2
(slow-landing dots, alarm wash per ERROR, shake + rain surge on ABORT), and the
same `?street=&locality=` overrides.

`SURVIVOR` controls how many columns keep raining after the collapse. It is
**0** — the field switches off completely, so the message never types over live
rain. Raise it for a residual ribbon of code; `layout()` then pushes the message
clear of the surviving columns automatically, so the two can't overlap at any
setting.

## How the message lives in the grid

- **Per-palette atlases.** Seven palettes (rain, dim, ok, addr, warn, err,
  abort), each a full glyph atlas at 24 brightness tiers. That's what lets a
  line turn amber or red while still being drawn by the same `drawImage` path
  as the rain.
- **Message layer.** `textB` (brightness) and `textP` (palette) per cell. A cell
  with `textB > 0` owns its glyph outright — the rain can neither recolour nor
  overwrite it.
- **Landing flash.** Each character stamps at full white-hot brightness and
  settles to 0.84 after 90ms, so type lands like a stream head.
- **Text-only glyphs.** Lowercase, apostrophe and space live in the atlas but
  sit above `RAND_G`, so random churn never selects them — the rain keeps its
  uppercase/numeric character while the message reads in sentence case.

### Bug worth remembering

First cut printed `seaLc in2.2.` / `3 ANo2et A e ue`. The random churn was
correctly guarded against message cells, but the **token stamper was not** — it
wrote `cell[]` unconditionally, so `BURLEIGH WATERS` and friends ate characters
out of the printed words as they fell through those rows. Any writer to `cell[]`
must check `textB[j] === 0` first; there are two of them, not one.

### Second bug: columns freezing part-way through their fade

With `SURVIVOR = 0` the sweep front only reaches its target at the very last
instant of the shutdown phase, and `colLife` was updated **only** while that
phase was active. The leftmost columns therefore froze mid-fade and sat on
screen as a lit stripe down the left edge, which the message then typed beside.
The fade now continues draining during the print phase. Verified by sampling lit
pixels left of the message column: 177 before the fix, 0 after.
