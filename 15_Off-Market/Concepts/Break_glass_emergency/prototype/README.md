# Break Glass — break + pull interaction

Working prototype of the full sequence: **tap the glass → it shatters and falls
away → the bail is revealed → drag it down → the latch throws → the panel behind
opens.**

**Preview:** `https://vm.fieldsestate.com.au/concepts/off-market/Break_glass_emergency/prototype/`

Built from the four stills in the parent folder. No 3D, no video — the swing is a
single CSS `rotateX` on a cut-out sprite, so it is drag-responsive and weighs
~840KB total.

---

## What the source images actually gave us

The four renders were generated independently, so they do **not** share a camera
or a consistent handle. Two measurements decided the whole build:

| | pivot bolts | bar | arm length |
|---|---|---|---|
| `handle_up.png` | y ≈ 772 | y ≈ 447 | **325** |
| `handle_down.png` | y ≈ 643 | y ≈ 861 | **221** |

`handle_down` is the only **internally consistent** frame — its pivot sits exactly
midway between where the bar would be raised and lowered. `handle_up` drew the
arms ~120px too long, and also placed the PULL DOWN sign ~110px lower.

So `handle_down` is the motion source. `handle_up` is used only as a start frame
and as a donor for clean plate.

The bail is a **rigid U hinged on the horizontal axis through the two pivot
bolts** — not a parallelogram linkage. That means the entire swing is one
rotation about y=643, which CSS does natively:

```css
transform-origin: 50% 13.4%;      /* the hinge, in sprite-local coords */
transform: rotateX(var(--angle)); /* 180deg = up, 0deg = down */
```

Because the parent has `perspective`, the bail sweeps *toward the camera* through
the mid-swing, which is what the real object does.

## The one cheat

A flat sprite collapses to a zero-height line at exactly 90°. It is covered by a
specular streak (`#glint`) that peaks there plus a motion blur that ramps with
proximity to 90°. At full speed that window is ~30ms. Scrub the dev slider to
90 to see it as a still.

## Pipeline

`build_assets.py` regenerates everything from the four source PNGs:

1. **Register** `v1` / `broken` / `handle_up` onto `handle_down` — affine ECC,
   estimated at ¼ res, keyed on the *metal box frame only* (outside the glass,
   so cracks and the handle cannot drag the fit). `v1` needed a 0.89 scale.
2. **Cut the bail** — brightness thresholding fails here (it grabs the plate and
   the sign), so the mask is the *frame difference*: the bail is whatever got
   brighter when it swung down. Dark end-caps are added as explicit circles.
3. **Repair the plate** — the bail has to swing over something. Low-frequency
   lighting comes from a ⅛-scale inpaint; grain is borrowed from a real
   text-free patch of the same plate; below y≈800 real pixels are donored from
   `handle_up` (genuinely clean there). The sign is restored verbatim at the end
   so the repair cannot eat its screws.

The script prints the CSS geometry that `index.html` needs, so the two cannot
silently drift apart.

```bash
python3 build_assets.py     # -> assets/*.webp
```

Assets are **not** committed (same as the other concepts here) — regenerate them
from the source PNGs, which live one level up on the VM.

## Interaction notes

- **Drag** the bail down; past ~65% travel it commits, otherwise it springs back.
- **Tap** it and it pulls itself.
- Keyboard: both hit targets are real `<button>`s, Enter/Space works.
- Sound is synthesised in WebAudio (no audio files) — smash, sweep, latch.
- `prefers-reduced-motion` shortens the swing and drops the shake.
- Dev bar: **Reset**, a **scrub slider** for the swing, and a sound toggle.
  Strip the `.dev` block for production.

## Known rough edges

- Faint residual smudge on the repaired plate below-left of the sign. Only
  exposed mid-swing, behind a blurred moving bail.
- The 90° collapse (above).
- `#reveal` is a placeholder — drop the real off-market panel in there.

Both of the first two go away completely if the box is ever rebuilt as a real 3D
render (or if intermediate swing frames are generated); nothing else about the
build would change.
