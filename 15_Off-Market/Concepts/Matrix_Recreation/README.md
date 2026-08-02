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
| 0–5.6s | A curtain of code drops **from the top, every column at once** |
| 5.6–7.8s | Field switches **OFF, right → left**, easing out |
| 7.8s+ | Field is fully dark; the message prints into the grid on a clear screen |

The opening is set by `OPENING`: `'top'` (default) starts every column just
above the top edge with near-zero stagger, so the field arrives as one curtain
and spreads out on its own because the fall speeds differ. `'sweep'` restores
the older left-to-right switch-on. `T_OPEN` is timed so the curtain reaches the
bottom of the screen just as the collapse begins.

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

---

# Version 4 — Local recognition sequence

**View:** https://vm.fieldsestate.com.au/concepts/off-market/Matrix_Recreation/code-sequence-local.html

v3's engine, with the rain running **twice as long** (11.2s) and carrying words
the Burleigh Waters owner actually recognises. The intent is that the code feels
like it knows them before it says anything.

## The ramp

Recognition is staged, and each tier is **weighted higher than the last**, so the
mix keeps shifting toward the viewer rather than merely accumulating. Measured
tier mix: 100% tier 1 at 2.5s, tier 3 dominant at 7s, tier 4 dominant at 10.5s.

| From | Tier | Content | Share of field |
|---|---|---|---|
| 0s | 1 | Readable immediately — the suburb and the language of listings: `BURLEIGH WATERS`, `4220`, `SOLD`, `WITHDRAWN` | 62% |
| 2.4s | 2 | Wider area: `CHRISTINE AVE`, `TALLEBUDGERA CREEK`, `MARYMOUNT COLLEGE`, `STOCKLAND BURLEIGH` | →78% |
| 4.8s | 3 | The actual street grid around the home — `JABIRU AVE`, `FANTAIL CRT`, `CORELLA AVE`, `612M2` | →88% |
| 7.2s | 4 | Their own block and their own thoughts — `3 AVOCET AVE`, `WHERE WOULD I GO`, `IS THE NUMBER REAL` | →98% |

**Almost the whole field carries real records.** The "code" texture comes from
`dataChunk()`'s lot numbers, QLD plan numbers, areas and DOM fragments rather
than from random glyphs, so a high density does not flatten the look — it just
removes the gibberish. Measured on screen: 68% of streams carrying text at 1s,
96% at 11s. `window.__rainStats()` in the browser console reports the live
figure against target if this needs retuning.

The curtain lands already carrying words; what changes over the 11.2s is how
*local* they get. Note a physical floor on this: a phrase needs roughly its own
length in rows before it can render, so nothing is readable until the curtain is
~15 rows deep (~1.5s), no matter how high the density is set.

Then the field collapses right→left and the message prints, exactly as v3.

## Where the words come from

- **Street names are real.** Pulled from `Gold_Coast.burleigh_waters` cadastral
  records (6,885 geocoded parcels, 193 distinct streets) and ordered by true
  haversine distance from the Avocet Avenue centroid. Tier 3 is literally the
  nearest streets to the subject property, closest first: Jabiru 55m, Fantail
  58m, Burleigh St 86m, Corella 147m, Bluejay 173m.
- **House numbers are invented.** Real streets, mock numbers — so no real
  neighbour's address appears beside words like `WITHDRAWN`.
- **Owner-voice phrases** are drawn from the mindset brief's §3 and §5 — the
  owner's own questions, not market claims.
- **POIs are from general knowledge, not the database** — worth a sanity check.

## What was deliberately left out

The mindset brief is marked INTERNAL, and several of its figures are flagged in
its own §9/§10 as not publishable: the Burleigh Waters median, the +6.9%
year-on-year, and the 292→161 volume drop (which §10 says needs a lag
reconciliation first). None appear here. `DOM 29` is included because the brief
identifies volume and days-on-market as the reliable layer.

## Implementation note

Assigning tokens only at spawn ramps too slowly — the opening curtain fills the
screen in one go and those streams take ~9s to clear, so the field would stay
noise long past its cue. `maintainTokens()` therefore tops up each frame to a
target count, converting streams still in the top quarter of their fall. Token
streams also get `sLen` extended to at least `phrase.length + 4` so the whole
phrase is lit simultaneously — otherwise the start fades before the end is
written and nothing is readable.

## Every column reads differently

A stream does **not** repeat one phrase. Each time it finishes a chunk it pulls a
different one, so a column reads as a run of varied records:

```
t=0.2s   4 CAR  DAYS ON MARKET  COMPARABLE  BURLEI
t=6.0s   ACANTHUS AVE  67 WAGTAIL CRT  612M2  LOT
t=10.5s  56 SANDPIPER DR  JUST CURIOUS  WILL I MIS
```

Roughly 45% of chunks are **generated fresh** rather than drawn from a list —
lot numbers, QLD plan numbers (`RP182425`), floor and land areas, days on
market, bed/bath counts, mock street numbers — which is what keeps two columns
from ever running the same string. Measured: 154 distinct chunks in 400 draws.

## Keyword highlighting

The phrases most relevant to the owner of the subject property — the streets
around them (tier 3) and their own block and questions (tier 4) — are flagged
`hot` as they are stamped. A **crest of light then travels down the phrase**:
the highlight wave is offset by each character's index within its phrase, which
is what makes it sweep rather than blink.

Deliberately *not* a colour change. Hot phrases lift toward white within the
existing rain palette, so they catch the eye while still reading as part of the
code rather than as a caption laid over it. Highlights begin around 5–7s, once
the local tiers are in play — the early, generic part of the ramp stays flat.

`window.__rainStats()` reports `hotStreams` / `hotCells` alongside text density.
Measured: 0 highlights before 5s, 10 streams at 6.8s, 44 streams / 263 cells by
10.8s.

### Why the original sparks had quietly stopped firing

Worth recording, because it was invisible. The random white sparks are set
inside the churn block — and churn is **skipped for locked cells**, which is
every cell carrying text. So sparks only ever fired on random filler. Raising
text density to 98% therefore came close to extinguishing them, trading sparkle
for legibility without that being an intended choice. The keyword highlight puts
that energy back, and puts it somewhere it does work.

A clamp was also added to the tier lookup (`Math.min(tMax, …)`) — a brightened
cell could otherwise index past the end of the glyph atlas and render nothing,
turning a highlight into a dropout.
