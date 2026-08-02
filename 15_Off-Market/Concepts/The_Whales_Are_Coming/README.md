# The Whales Are Coming — procedural swim study

A humpback swimming left to right, driven by measured biomechanics rather than
by keyframes. Three layers — far flipper, body, near flipper — sliced into
vertical strips and re-laid along a travelling body wave, with a blinking eye.

Open `index.html` — it plays on load, is fully self-contained (no server, no
network, no build step), and every parameter is a live slider.

**Preview:** https://vm.fieldsestate.com.au/concepts/off-market/The_Whales_Are_Coming/
(`whale_swim.mp4` on the same path is a rendered 24-second crossing.)

## Two versions

| Page | Look |
|---|---|
| `index.html` | The tonal drawing, in blue water. |
| `index_ink.html` | **Ink treatment** — cream strokes on black, as in the V3 reveal deck. |

Same rig, same physics, same blink. Only the sprites and the ground differ.

The ink version reduces the drawing to an **ink coverage mask** and paints that
coverage in warm cream (`#E6DDD2`) onto black. Paper becomes ground and only
strokes carry light, so it reads as scratchboard or silverpoint rather than as
an inverted photo. The levels — black point, clean floor, gamma, unsharp — are
lifted verbatim from `Page_Redesign_V3/reveals/build_reveal.py` so the whale
matches the rest of that deck exactly rather than approximately.

The ground is flat black on purpose. A gradient or a light shaft puts luminance
back into the paper and the effect collapses.

**A note on the source.** The tonal `Whale_V2.png` gives a soft, mezzotint-like
version of the treatment. The original pen drawing, `whale.png`, gives a far more
striking one — every individual hatch stroke comes up as a separate cream line,
which is exactly how the tree and pandanus read. It is not used here because the
two files are not interchangeable: aspect 1.703 vs 1.831, so the spine, flipper
hinges and eye box would all have to be re-measured. Worth doing if the ink
version becomes the primary one.

## What to look at

- The **whole animal** moves — head, body and flippers, not just the tail. That
  is the point of the build, and it is what the measurements demand.
- **One tail beat every ~4.3 seconds.** Slower than instinct says. Almost every
  hand-animated whale runs about 10× too fast.
- **Burst and coast** — a few strokes, then a long rigid glide.
- The eye **blinks**, as a canthus-anchored purse rather than a shutter. At the
  default size it is subtle; raise **Whale size** to see it.

## Files

| File | What it is |
|---|---|
| `swim.template.html` | **Source of both pages.** `{{BODY_DATA_URI}}`, `{{NEAR_DATA_URI}}`, `{{FAR_DATA_URI}}`, `{{THEME_DEFAULT}}` and `{{RIG_JSON}}` are filled in by the build, once per version. |
| `build_whale_sprite.py` | **Source of the sprite + rig.** `Whale_V2.png` → layers, measured rig → `index.html`. |
| `shoot.js` | Headless-Chrome frame renderer → MP4 / contact sheet. |
| `index.html` / `index_ink.html` | The two animations. *Generated* — edit `swim.template.html` instead. |
| `whale_body.png` / `whale_body_ink.png` | Body with the flippers cut away. *Generated.* |
| `whale_flipper_{near,far}[_ink].png` | The two pectoral blades. *Generated.* |
| `whale_rig.json` | Measured spine, thickness profile, flipper hinges, eye. *Generated.* |
| `whale_swim.mp4` / `whale_swim_ink.mp4` | Rendered crossings. *Generated.* |

The input image lives outside this folder, at
`../Near_beach_palm_reveal/Other images/Whale_V2.png`.

## Rebuild

```bash
source /home/fields/venv/bin/activate       # numpy, pillow, scipy
python3 build_whale_sprite.py               # layers + rig + index.html
node shoot.js --mp4 --dur 24 --fps 30       # the video
node shoot.js --page index_ink.html --name whale_swim_ink --mp4 --dur 24
node shoot.js --stills 6 --from 9 --to 13.3 # contact sheet of one tail cycle
```

`build_whale_sprite.py` must be re-run after **any** edit to
`swim.template.html` — `index.html` is a generated artefact and editing it
directly will be overwritten.

## Saving and restoring

Only three files are irreplaceable: `swim.template.html`,
`build_whale_sprite.py` and `shoot.js`, plus the input `Whale_V2.png`. All four
are on GitHub (`Will954633/Fields_Orchestrator`). `whale_rig.json` is pushed too,
as a readable record of the measurements.

**Everything else regenerates byte-for-byte.** That was verified by deleting the
generated files and rebuilding: `index.html`, `whale_body.png`, both flipper
layers and `whale_rig.json` all came back with identical MD5s. So the ~8 MB of
generated output is deliberately not committed — it would bloat the repo to
preserve something the build reproduces exactly.

The renders are deterministic for the same reason: `shoot.js` drives the page
with `?capture=1`, which replaces the animation loop with `window.__swim.frame(t)`
and re-integrates from t=0 at a fixed dt for every frame. Blink jitter runs off a
seeded PRNG. Nothing depends on wall-clock time or machine speed, so a re-render
is frame-identical.

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

## The kinematics are measured, not invented

The first version of this had amplitude clamped to zero across the front 38% of
the body, so the head was nailed in place. That is a caricature of thunniform
swimming and it is wrong twice over — wrong for cetaceans generally, and
especially wrong for humpbacks.

**Fish, F. E., Peacock, J. E. & Rohr, J. J. (2003), "Stabilization mechanism in
swimming odontocete cetaceans by phased movements", *Marine Mammal Science*
19(3): 515–528** digitised four points — rostrum, flipper tip, peduncle, fluke
tip — across seven species at 1.4–7.3 m/s. It is the load-bearing source here,
and it overturns the obvious model:

| Point | Amplitude | Phase vs fluke |
|---|---|---|
| Rostrum | 0.02–0.06 L (ratio to fluke 1:4.34–6.76) | **−9.4° to +33.0°** |
| Flipper tip | **smallest of the four** | trails by 60.9–123.4° |
| Peduncle | between | **leads** by 18.9–48.7° |
| Fluke tip | 0.17–0.25 L | — |

Two things in that table are counter-intuitive and both are now built in.

**The head moves nearly IN phase with the flukes, not against them.** A rigid
beam pivoting about its centre of mass would put rostrum and fluke 180° apart.
Real animals do not: in two species the phase difference is statistically
indistinguishable from zero. The paper's explanation, verbatim — "By
synchronously moving the rostrum in the same direction as flukes by muscular
control, there is a reduction in the natural tendency of the rostrum to swing
through a wide arc opposite the motion of the flukes."

**The amplitude minimum is at the flippers.** The flipper tip has the smallest
excursion of the four points, because it sits nearest the centre of mass — so
the envelope is not monotonic from nose to tail, it dips. That measured node
lands between this sprite's two flipper hinges (u = 0.25 and u = 0.37), which is
a pleasing independent check on the segmentation.

So the body is modelled in **two zones meeting at the node**: a travelling wave
behind it, and an anterior section whose phase is prescribed against the fluke
rather than inherited from the wave. That split is not a modelling convenience —
a single travelling wave cannot produce a near-synchronous rostrum *and* a
peduncle leading by only ~38° at the same time. The animal is not a passive
wave; it is actively stabilised, and the two-zone split is what that control
does.

Verified output against the measurements:

| | model | measured |
|---|---|---|
| Rostrum amplitude | 19% of fluke, 3.8% L | 15–23%, 2–6% L |
| Rostrum phase | +20° | −9.4° to +33.0° |
| Peduncle phase | leads 38° | leads 18.9–48.7° |
| Flipper excursion | 1–2% of fluke, the smallest | smallest of four |

### Independent cross-check: 44 species of fish agree

**Di Santo, V., Goerig, E., Wainwright, D. K., Akanyeti, O., Liao, J. C.,
Castro-Santos, T. & Lauder, G. V. (2021), "Convergence of undulatory swimming
kinematics across a diversity of fishes", *PNAS* 118(49):e2113206118** fitted 44
species and got a global envelope (peak-to-peak, proportion of body length):

> y = 0.05 − 0.13x + 0.28x²

Head 0.05 L, tail 0.20 L → **head:tail = 25%**, minimum at **x = 0.232 L**. Their
across-species medians give head 0.03 / tail 0.18 → **17%**. This model sits at
**19%** with the node at 0.28 — between their fit and their medians, from an
entirely separate literature (cetacean tag and video data). Two independent
lines converging is the strongest evidence here.

The older Videler & Hess (1984) saithe fit, `A(x) = 0.02 − 0.0825x + 0.1625x²`
(half-amplitudes), gives nose:tail = **20.0%** with the node at **0.254 L** —
the same answer a third time.

**And the textbook ordering is empirically wrong.** Di Santo et al., verbatim:
"there was **no decrease in head:tail amplitude from the anguilliform to
thunniform mode** of locomotion as we expected from the traditional
classification," and the ratio "was only statistically higher in the tuna." The
supposedly stiffest swimmer has the *most* head yaw of the four canonical
species. A locked head is not conservative realism — it is a myth.

### Passive recoil is a demo slider, and zero is the correct default

Lighthill's elongated-body recoil — zeroing net lateral and angular momentum,
weighted by mass per unit length from the measured thickness profile — is
implemented. It throws the head into **anti-phase** and roughly doubles its throw
(20% → 39% of fluke).

It defaults to **zero**, for two reasons. The measured phases say a live cetacean
muscularly suppresses that anti-phase swing. And more decisively: **measured
envelopes already contain whatever recoil was not cancelled**, so adding a recoil
term on top double-counts it. Maertens, Gao & Triantafyllou (2017, *JFM*
813:301) make this explicit by setting their recoil term `B(x,t) = 0` for the
canonical carangiform gait, precisely because the envelope came from Videler's
measurements. Solve the momentum balance only when prescribing a pure *bending*
wave and deriving the rigid motions yourself — never on top of a measured
envelope. The slider is there to show the see-saw, not to be used.

For the record, Lighthill's 1960 *optimum* does call for amplitude "increasing
from zero over the front portion." So the locked-head version was reproducing a
theoretical optimum. The measurements simply say real animals do not swim that
way.

### Numbers, all from tag data

| Parameter | Value | Source |
|---|---|---|
| Body length | 13.5 m (n=128) | Woodward, Winn & Fish 2006, *J. Morphol.* 267:1284 |
| Cruising speed | 1.77–2.09 m/s | Gough et al. 2019/2021, *JEB* |
| Fluke-beat frequency | **0.229 ± 0.039 Hz** (n=97) | Gough et al. 2019 |
| Fluke amplitude | 0.20–0.24 L p-p | Gough et al. 2019 (direct fluke-tag measure) |
| Fluke pitch angle | 30° | Gough et al. 2021 |

> **One tail beat every ~4.3 seconds.** Almost every hand-animated whale runs
> about 10× too fast.

**Caveat on Strouhal.** Frequency here is still derived via `St = fA/U`, because
it is a good animation control — change speed and the tail retimes itself. But
the animal does not obey it. Gough et al. 2019 found frequency scales as
**L^−0.53** where an optimal-Strouhal oscillator predicts L^−1.0, and concluded
whales are not operating as Strouhal machines. Their one directly measured
humpback Strouhal was **0.24** (at 2.61 m/s), while the default here is 0.31 —
chosen so the lock reproduces the measured *frequency*. Those two facts cannot
both be honoured at one speed; the frequency is the better-evidenced number
(n=97 deployments vs n=1 animal). Rohr & Fish 2004 (n=248, 6 species) also found
only 55% of cetaceans fall in the theoretical 0.25–0.35 band, with 74% in
0.20–0.30.

**Burst and coast.** 3.5 beats, then five seconds of rigid glide while quadratic
drag bleeds the speed off. Thrust is scaled so continuous beating settles at
exactly the cruise speed asked for (steady state is `thrust == drag·U²`).

**A real crossing is slow.** The frame holds 33 m of water, so a left-to-right
pass takes ~24 s. If a card only has six, shrink the whale — do not speed the
tail up. That is the failure mode that reads as sliding rather than swimming.

## The blink

The lids are made of **the artist's own hatching**, sampled from the tissue
immediately above and below the eye and stretched toward each other. Painting a
lid, or inpainting the socket and drawing a crease, would have to invent pen
texture that matches at 5× magnification — and it would not. Both bands are
bounded to a soft-edged almond via a destination-out radial mask, so they can
only ever cover the eye opening and the edge dissolves into the surrounding lid
tissue instead of cutting across it.

### It is a purse, not a shutter

The first version dropped an upper lid like a window blind. That is wrong for a
cetacean. The orbicularis oculi closes the palpebral fissure "using the medial
and lateral canthi as fulcrums" (**Nishimaniwa, Yamada, Sekiya, Amano & Tajima,
*J. Vet. Med. Sci.* 88(1):1–12**) — a sphincter contraction anchored at the
corners, with the retractor bulbi pulling the globe inward at the same time. So
both margins converge on a mid-line, the travel tapers to zero at the corners,
and the closing line **bows** rather than staying straight. Drawn in 2 px
vertical strips so each column carries its own travel.

**And the humpback is the awkward case.** In dolphins and porpoises the upper
palpebral region has degenerated into an aponeurotic sheet with almost no
facial-nerve supply, so the lower lid does most of the moving. Mysticetes did
not: in the humpback and bowhead the muscle is "entirely composed of muscular
fibers", the ancestral mammalian arrangement (**Rodrigues et al. 2015, *Acta
Zool.* 96:328; Zhu, Hillmann & Henk 2000, *Anat. Rec.* 259:189**). A humpback
blink should therefore be **more** symmetric than a dolphin's, not less — which
is why both lids move here by equal measure.

**No nictitating membrane.** Cetaceans lack one (**Meshida, Lin, Domning,
Reidenberg, Wang & Gilland 2020, *Anat. Rec.***, listing it among features
"absent in cetaceans but present in other closely related terrestrial mammals").
Most popular sources claim they have a third eyelid. They are wrong; none is
animated.

Closure is faster than reopening. That asymmetry *is* sourced — Aiello et al.
(2023, *PNAS* 120(18):e2220404120) measured significantly higher peak velocity
and acceleration on closing than reopening (P < 10⁻¹⁹), and note the same holds
"in all tetrapods for which data is available."

### The two timing numbers are NOT sourced

**There is no published measurement of blink rate or blink duration for any
cetacean species.** That was checked directly against Europe PMC across species
and term variants; every cetacean hit is either anatomy with no kinematics, or
sleep work that scores eye state as a sustained condition in 5-second epochs
rather than counting blinks.

So mean interval 11 s and stroke 0.55 s are **artistic choices**, and are the
only numbers in this build that are not backed by a paper. What the literature
does license is "infrequent, and slow" — the sleep-scoring methodology only works
if frequent brief blinks are not happening, and cetaceans have well-developed
Harderian glands, so "blinking seems unnecessary for maintaining the moisture of
the corneal surface" (Nishimaniwa et al.). The mechanism is also heavy: thick
lashless lids, a canthus-anchored sphincter, and simultaneous globe retraction.
That is a reasoned argument for a slow blink, not a measurement.

Widely-repeated web claims that whales "blink once every couple of hours" have no
citation and no traceable origin. Do not use them.

Timing is jittered from a **seeded** PRNG. The capture renderer re-integrates
every frame from t=0, so unseeded jitter would make the eye flicker at random
between frames of the same render.

At the default staging the eye is only ~40 px wide on screen and the blink is
correspondingly subtle. Raise **Whale size** to see it properly.

## Where the evidence runs out

**The humpback-specific kinematic dataset does not exist.** Every per-body-point
amplitude and phase above is **odontocete** — dolphins, orca, beluga. For
humpbacks there is exactly one direct fluke-amplitude measurement in the
literature (Gough et al. 2019: n=1 animal, 14 stroke sequences, from a tag that
happened to slip onto a fluke blade). Everything else humpback-specific is
frequency, speed and morphometrics.

That matters because **humpbacks are more flexible than dolphins.** Buchholtz
(2001, *J. Zool.* 253:175) found mysticetes retain the archaeocete pattern of
constant vertebral shape along the torso, which acts as an undulatory unit:
dorsoventral displacement begins **at the chest** in a swimming humpback, versus
being restricted to the caudal peduncle in porpoises and white-sided dolphins.
Woodward et al. 2006 puts the humpback at fineness ratio 4.21 against the blue
whale's 6.37 — a fast manoeuvrer, not a stiff cruiser. So the anterior share of
the motion here is plausibly *under*-stated, not over-stated. There is no
published number to correct it with, so it has been left at the odontocete
value rather than invented.

**The wavelength is inferred, not measured.** λ = 1.8 body lengths is set purely
to reproduce the measured peduncle phase lead over the fluke (38°, against 19–49°
observed). That is longer than any published fish value — Di Santo et al. give
0.58 L for eel, 0.96 for mackerel, 1.17 for tuna, with a thunniform median of
1.14 — which is consistent with cetaceans being stiffer-tailed still, but it is
an inference from phase data rather than a measurement of a wave.

**No one has published a flipper motion time series for steady straight-line
cruising** — for any cetacean. The descriptive work (Edel & Winn 1978, *Marine
Biology* 48:279; Segre et al. 2017, *Curr. Biol.* 27:R636) has flippers acting as
near-static trim and control surfaces in cruise, saving the large strokes for
banked turns and lunges; Segre's flapping flipper-stroke was seen twice in
hundreds of hours of video. So the flippers here are driven off the measured
*phase lag* with deliberately small amplitude, and that is a modelling choice
standing on an extrapolation from odontocete data, not a measurement.

## What is deliberately not modelled

**Arc-length shortening.** A bent body projects slightly shorter than a straight
one — a 1–2% effect at these amplitudes.

**Depth rotation.** The source is a three-quarter view and a flat sprite cannot
rotate in depth, so the fluke's angle of attack is faked by the phase lag rather
than being a real pitch. Push `ampFrac` past ~0.28 and the flukes read as rubber.

**Cross-section rotation.** Strips are sheared vertically, not rotated. Rotating
each strip about its own centre makes adjacent strips disagree along their shared
edge wherever the slope changes, and the gaps open into a visible comb down the
peduncle exactly where the wave is steepest. The shear agrees with both
neighbours by construction. The cost is a cos θ effect, invisible here.

The animal is also composed at **1:1 sprite scale** into an offscreen canvas and
scaled once, rather than drawn strip-by-strip onto the scaled canvas. Drawing
into the scaled canvas puts every strip boundary on a fractional device pixel, so
each strip antialiases its own edges and adjacent edges do not sum to full
coverage. With opaque sprites that is invisible. With the semi-transparent ink
layers it is not, and it cannot be patched either way: a 1 px overlap
double-composites and comes out too bright (27% swing between `strips=1` and
`strips=8`), no overlap leaves gaps and comes out too dark (6%). At 1:1 the
boundaries are integers, `drawImage` does no edge AA, and the strips tile
exactly — verified strip-count invariant to 0.0002%.

## Controls

Every slider is also a URL parameter, which is how `shoot.js` drives the page:

```
index.html?St=0.28&U=2.4&ampFrac=0.22&glide=7&size=0.3&theme=light
```

`capture=1` swaps the rAF loop for `window.__swim.frame(t, fps)` and steps
frames by hand. Each frame re-integrates from t=0 at a fixed dt, so a frame is
reproducible on its own and the render never depends on how fast the machine
draws.
