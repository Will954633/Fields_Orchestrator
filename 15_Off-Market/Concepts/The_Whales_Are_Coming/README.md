# The Whales Are Coming — procedural swim study

A humpback swimming left to right, driven by the physics rather than by
keyframes. One flat sprite, sliced into vertical strips and re-laid along a
travelling wave whose frequency is locked to swimming speed by the Strouhal
number.

Open `index.html` — it plays on load, is fully self-contained (no server, no
network, no build step), and every parameter is a live slider.

Preview: `https://vm.fieldsestate.com.au/concepts/off-market/The_Whales_Are_Coming/`

## Files

| File | What it is |
|---|---|
| `index.html` | The animation. Generated — edit `swim.template.html` instead. |
| `swim.template.html` | Source of the animation. `{{SPRITE_DATA_URI}}` / `{{RIG_JSON}}` are filled in by the build. |
| `build_whale_sprite.py` | `Whale_V2.png` → trimmed sprite + measured rig → `index.html`. |
| `shoot.js` | Headless-Chrome frame renderer → MP4 / contact sheet. |
| `whale_sprite.png` | Trimmed, feathered, colour-bled sprite. Generated. |
| `whale_rig.json` | Measured spine, thickness profile, zone boundaries. Generated. |
| `whale_swim.mp4` | Rendered crossing. Generated. |

## Rebuild

```bash
python3 build_whale_sprite.py            # re-derives the sprite and index.html
node shoot.js --mp4 --dur 24 --fps 30    # re-renders the video
node shoot.js --stills 6 --from 9 --to 13.7   # contact sheet of one tail cycle
```

`build_whale_sprite.py` must be re-run after any edit to `swim.template.html` —
`index.html` is the generated artefact.

## Why the source image works

`Whale_V2.png` (1536×1024 RGBA) ships with a real alpha matte, so there is no
keying to do. The alpha is cleanly bimodal — 1.21M fully transparent px, 358k
fully opaque, only 0.38% of the frame in between — and the RGB *under* the
transparent ring averages 180/173/168, essentially the same as the whale itself.
That edge-extend is what stops the silhouette picking up a dark rim when the
sprite is scaled and warped, and it is the usual reason cut-out sprites look
cheap.

The build still has to trim (the matte fills 1432×782 of the frame, leaving too
little margin for the fluke to swing), feather the near-binary edge so the
per-strip rotation does not alias it, and bleed colour a few more pixels past
the new crop.

## The rig, measured not assumed

`build_whale_sprite.py` reads the spine out of the matte rather than assuming a
horizontal axis — the whale sags through the belly and the peduncle lifts toward
the flukes, and the wave has to ride the body the artist actually drew.

It also locates where the tail stock meets the trunk: **u = 0.79**. That is
measured, and it is measured by a threshold rather than by looking for a waist,
because in this three-quarter pose the flukes read as two thin lobes and the
column count climbs monotonically from the fluke tip into the body — there is no
local minimum to find. The trunk reference is a 90th percentile rather than a
max because the pectoral fins hang below the belly and spike the column count by
about 2× where they cross. The fattest columns in the image are fin, not body.

## The physics

**Strouhal is the whole realism story.** `St = fA/U`, efficient band 0.25–0.35.
Solving for frequency at humpback figures — L = 14 m, U = 2 m/s, A = 0.2 L =
2.8 m, St = 0.30:

> **f ≈ 0.21 Hz — one full tail beat every 4.7 seconds.**

Almost every hand-animated whale runs about 10× too fast. Frequency here is
derived, never set: change the speed slider and the tail retimes itself. It
tracks *instantaneous* speed, so as the whale accelerates out of a glide the
beat naturally quickens.

**Burst and coast.** Large whales rarely beat continuously. The default is 3.5
beats, then five seconds of rigid glide while quadratic drag bleeds the speed
off. Thrust is scaled so continuous beating settles at exactly the cruise speed
asked for (steady state is `thrust == drag·U²`), so the slider stays meaningful.

**The travelling wave.** Amplitude is ~0 across the rigid front, then ramps to
full at the flukes; the phase term makes the wave travel backwards down the
body at 0.9 body lengths, which is what makes the fluke lag the peduncle and
scoop water rather than just wag.

**Secondary motion.** The body heaves against the stroke and pitches counter to
it, both lagging a quarter cycle. Without these the animation reads as a rigid
sprite on a path with a wiggling tail bolted on.

**A real crossing is slow.** At the default staging the frame holds 33 m of
water, so a full left-to-right pass takes about 24 seconds. If a card only has
six, shrink the whale — do not speed the tail up. That is exactly the failure
mode that reads as sliding rather than swimming.

## What is deliberately not modelled

**Arc-length shortening.** A bent body projects slightly shorter than a straight
one. At the amplitudes real whales use this is a 1–2% effect, well under the
point where the hatch texture shearing gives the trick away first.

**Depth rotation.** The source is a three-quarter view and a flat sprite cannot
rotate in depth, so the fluke's angle of attack is faked by the phase lag rather
than being a real pitch. It holds up at the default amplitude. Push
`ampFrac` past ~0.28 and the flukes start to read as rubber.

**Separated pectoral fins.** The fins cross over the body, so the column warp
drags them along with it. Cutting them as their own layers means inpainting the
tone behind them — worth it only if the whale is going to be shown large.

## Controls

Every slider is also a URL parameter, which is how `shoot.js` drives the page:

```
index.html?St=0.28&U=2.4&ampFrac=0.22&glide=7&size=0.3&theme=light
```

`capture=1` swaps the rAF loop for `window.__swim.frame(t, fps)` and steps
frames by hand. Each frame re-integrates from t=0 at a fixed dt, so a frame is
reproducible on its own and the render never depends on how fast the machine
draws.
