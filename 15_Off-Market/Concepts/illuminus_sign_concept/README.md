# Illuminus — the off-market CTA as a night neon sign

Two versions:

| | View |
|---|---|
| **Wall sign** — the tight pill, closest to the current CTA | [index.html](https://vm.fieldsestate.com.au/concepts/off-market/illuminus_sign_concept/index.html) |
| **Roadside pylon** — marquee cabinet on posts, with chase bulbs | [roadside.html](https://vm.fieldsestate.com.au/concepts/off-market/illuminus_sign_concept/roadside.html) |
| **Low monument** — long slab ~1 m up, seen from the left at 40° | [low-profile.html](https://vm.fieldsestate.com.au/concepts/off-market/illuminus_sign_concept/low-profile.html) |

Both run the same discharge engine and the same three-swells-then-flicker
sequence. The roadside version adds a second, physically different emitter —
see [Roadside](#roadside) below.

---

## Status — paused 2026-08-03

**Concept stage. Nothing is live.** Both versions are built, measured and
viewable; neither is wired into the site.

| | |
|---|---|
| Built + verified | Wall sign, roadside pylon, React port of the wall sign |
| **Not** wired in | `DiscoveryDeck.tsx:278` still renders the original flat pill |
| **Not** tested | Any real phone. Headless Chrome only, desktop viewport |
| **Not** built | React port of the roadside version (it's a scene, not a button — see below) |
| Blocked on | Will's four decisions in [Open decisions](#open-decisions) |

### Files

```
index.html          wall sign — standalone, no build
roadside.html       roadside pylon — standalone, no build
port/NeonCta.tsx    drop-in React component for the wall sign
port/NeonCta.module.css
verify/verify.js    reproduces every measured number in this README
verify/shots/       screenshots it writes (regenerated, not source)
```

Served with no build step at
`vm.fieldsestate.com.au/concepts/off-market/illuminus_sign_concept/` — edit the
file, refresh the browser.

### Picking it back up

The numbers quoted throughout this README are measured, not asserted. If you
touch any physics constant, re-run them:

```bash
cd /home/fields/Feilds_Website/01_Website        # where puppeteer lives
node ../../Fields_Orchestrator/15_Off-Market/Concepts/illuminus_sign_concept/verify/verify.js
```

It checks the three claims that actually matter — that the mains ripple does
not alias into a strobe, that flash-safe mode holds the WCAG cap across 400
seeds, and that the filaments smear rather than switch — and writes screenshots
of the states worth looking at.

**Screenshot rather than reason about the geometry.** Four bugs in the roadside
arrow survived careful reading of the code and died instantly on being looked
at, including a chevron built with its arms diverging the wrong way, which
pointed the arrow backwards.

---

Replaces the flat copper pill at the end of the `/off-market` discovery deck
([`DiscoveryDeck.tsx:278`](../../../../Feilds_Website/01_Website/src/pages/OffMarketPage/discovery/DiscoveryDeck.tsx))
— *Build my complete selling strategy* — with a bordered neon sign that swells
three times, flickers, and catches.

The deck already ends on pure black, so the sign is read as being on a wall at
night: the tube lights the wall behind it, and when it drops out the glass is
still there.

---

## The sequence

| Phase | Duration | What happens |
|---|---|---|
| Dark | 0.42 s | Dead tube. Grey glass only. |
| Pulse ×3 | 1.15 s each | Instant strike to 30%, then a smooth swell to full and back. |
| Flicker | ~2–3.5 s | 7–10 dropout / restrike events. |
| Steady | 3.4 s | Locked on, with thermal drift. |
| Rest | 0.9 s | Back to dark, loop. |

---

## Why it looks real

Most CSS "neon" is a box-shadow on an opacity keyframe. That reads as a lamp on
a dimmer, which is the one thing a neon sign is not. A neon sign is a gas
discharge tube on a transformer, and every decision here follows from that.

**1. Striking is binary and instant.** Ionisation completes in microseconds and
pure neon has essentially no afterglow. So the tube edge is a hard step — there
is no easing on it anywhere. What you read as softness is the halo, not the
tube.

**2. The halo lags; the tube doesn't.** The apparent fade is bounce light on the
wall plus your own retinal integration. Modelled as an asymmetric one-pole
filter — 12 ms attack, 55 ms release — run at 1 kHz, not per frame.

**3. Mains.** Australia is 50 Hz. A discharge tube extinguishes and restrikes at
every zero crossing, so it ripples at **100 Hz**. This is the trap: you cannot
see 100 Hz and neither can a 60 fps screen. Animating it naively aliases it into
a **20 Hz strobe** — wrong, and genuinely unpleasant.

The fix is to stop sampling and start integrating. Every frame is rendered as
the *time-average of emission over that frame's exposure window*, supersampled
at 1 kHz. That is exactly what an eye and a camera shutter do. Measured over a
full take, steady burn lands at **≈97.5% mean with a ~4% residual shimmer** —
the ripple correctly almost vanishes when the sign is healthy, and correctly
bites during sub-frame flicker events.

**4. Flicker has a grammar.** A failing tube is not random opacity. It drops
out (14–110 ms, occasionally 180–440 ms), hesitates at partial ionisation
(5–21 ms, dim and pink, because a cold discharge runs pinker), strikes with
~62 Hz streamer instability decaying over the first 22 ms, holds, drops again.

**5. An unlit tube is still there.** Off, it is pale grey-green glass. Anything
that vanishes to nothing is a div, not a sign. The frame also carries a real
gap at bottom centre where the tube exits to a transformer housing, and the
electrode ends run hotter and pinker than the middle of the run.

Also: the border is a generated SVG path measured from the live button box, so
corner radii never distort at any width; and the wall bounce carries a faint
grain overlay, because dark radial gradients band badly on 8-bit panels.

---

## Flash safety — read before shipping

**WCAG 2.3.1 forbids anything that flashes more than three times in one second.**
A genuinely failing tube stutters faster than that. Measured across 400 seeds:

| Mode | Worst strikes in any 1 s window | Mean rate |
|---|---|---|
| `SAFE = false` (raw physics) | **8** | 4.80 / s |
| `SAFE = true` (**default**) | **3** | 2.48 / s |

SAFE mode keeps every dropout exactly as hard and as sudden as the physics
demands, and pads only the *lit* holds to a 340 ms minimum between strike
onsets. Safety never softens an edge — it just makes the sign fail less
frantically. It is compliant by construction, not by argument.

`prefers-reduced-motion: reduce` bypasses the whole sequence and renders the
sign simply lit. No pulse, no flicker.

**Toggle both in the panel to compare before deciding.** My recommendation is
to ship SAFE — the difference is barely perceptible and the unrestricted
version is a genuine seizure risk on a page we point paid traffic at.

---

## Panel

| Control | Does |
|---|---|
| Replay | Restart the current take (clicking the sign does this too) |
| New flicker | Reseed — every take is a different failure |
| Flash-safe | Toggle the WCAG cap (on by default) |
| Sound | Transformer hum at 100 Hz with odd harmonics, plus a strike tick |
| Reduced motion | Preview the accessible fallback |

The oscilloscope traces actual emission, so the physics is inspectable rather
than something you have to take on trust.

---

## Roadside

`roadside.html` — a highway pylon: marquee cabinet on steel posts, a `FIELDS`
plate above the CTA, a chasing bulb arrow below, standing on a dark road under
a night sky, swaying very slightly in the wind.

The reason this is a real build and not a reskin is that **a roadside sign has
two emitters, and they obey opposite physics.**

| | Neon tube | Incandescent bulb |
|---|---|---|
| Switching | instant — microseconds | **cannot switch** — thermal mass |
| Rise / fall | no afterglow at all | ~45 ms heat, ~115 ms cool |
| Colour | fixed by the gas | **shifts with filament temperature** |

That second column is the entire reason a real chase reads as real. The
trailing bulbs are still hot after the drive has moved on, so the chase
**smears** — and because radiated colour follows filament temperature, the
smear is *red*: a cooling bulb slides down the blackbody curve from warm white
through orange to dull red before it goes out.

So bulbs are modelled as filaments, not as opacity:

- temperature `T` integrates toward the drive with asymmetric time constants
  (heating is faster than cooling, which is why the trail is longer than the
  attack)
- luminance is `T³·⁵` — radiated power in the visible band is steeply
  superlinear in temperature, so a filament at half temperature is nowhere near
  half as bright
- colour is a real blackbody curve (Tanner Helland's approximation) mapped over
  1500–2800 K
- light is composited **additively** on canvas (`lighter`), because overlapping
  light adds — it does not alpha-blend
- a couple of bulbs are permanently dead and a couple make poor contact and
  stutter, because every real sign has some

Unlike the discharge, the filaments are **not** supersampled — deliberately.
Their time constants are many times longer than a frame, so per-frame
integration is already exact. Sub-frame detail matters for a tube that switches
in microseconds; it does not for a lump of hot metal.

**Verified:** sampled during steady burn with the chase running, **all 36 live
bulbs are mid-transition** at any given instant — none sits at a binary
extreme (temperature histogram across quintiles: `14 · 0 · 10 · 0 · 12`). The
filaments genuinely smear rather than switching, which is the whole claim.

Two things worth knowing about it: the cabinet is **squarer than a real pylon**
(roadside signs are tall because they're read at 80 km/h from 200 m; ours has
to stay legible in a scroll deck, so the CTA is set over three lines), and the
`FIELDS` plate settles a beat *before* the main tube, which is how a genuine
multi-circuit sign wakes up.

---

## Low monument

`low-profile.html` — an elongated rounded slab about a metre off the ground on
two short legs, lighting the ground beneath it. Built to Will's brief: camera
left of centre, slightly above, ~40° off the face, close enough to a level view
that the narrow **top surface** reads as a surface rather than an edge. CTA text
only — no `FIELDS` plate.

This is the only version that is a genuine 3D object rather than a flat panel:
a slab with a front face, a top, a left end cap and a back, assembled from CSS
transforms and lit as one. Same discharge engine as the other two.

**Camera is adjustable in the panel** — yaw and pitch sliders, reading out in
degrees. Defaults are 40° / 13°. Dial it to what you actually pictured and tell
me the numbers rather than describing it.

Three things that only matter once the sign is a solid:

- **The top surface is the brightest non-emitting part of the sign.** It sits
  millimetres from the tube and faces up into its spill, so its front lip is
  near-white while its back edge falls to bare metal. Getting that gradient
  right is what makes the slab read as having thickness.
- **The SVG tube path is built from `offsetWidth/offsetHeight`, not
  `getBoundingClientRect`.** On a 3D-rotated element the rect returns the
  screen-space bounding box, which is not the face's geometry — using it warps
  the tube as the camera moves.
- **A shallow pitch makes a large ground plane useless.** Viewed ~13° from
  edge-on, a big horizontal plane projects into a skewed smear that wanders off
  frame. The dark ground and the light pool are therefore separate planes, and
  the pool is small and pinned to the sign so it cannot drift.

Open: the sign's proportions (currently 4.4:1) and exactly how much top surface
shows are both guesses at Will's mental picture. A reference image would settle
both faster than another round of description.

---

## Porting it

`port/` holds a drop-in React version matching the deck's CSS-module setup.

```tsx
import { NeonCta } from "./NeonCta";

// DiscoveryDeck.tsx:278 — replace
// <a className={styles.cta} href="#build-strategy" onClick={onCta}>{card.cta_label} →</a>
<NeonCta label={card.cta_label ?? ""} href="#build-strategy" onClick={onCta} />
```

Two deliberate differences from this concept page:

- **It does not loop.** The take plays once when the card scrolls into view,
  then holds steady lit. A sign flickering forever under a CTA is obnoxious and
  burns battery on the phones that are most of this deck's traffic.
- **The rAF loop stops** once steady is reached and whenever the card is
  off-screen.

It stays a real `<a>` throughout — focusable, keyboard-operable, and it still
carries the existing `onCta` analytics handler, so the deck's card/dwell
tracking is unaffected.

---

## Open decisions

Nothing goes further until these are settled. Ordered by how much they change.

**1. Which version?** The wall sign is an element — it drops into the existing
strategy card and the React port is already written. The roadside pylon is a
*scene*: sky, road, structure. It would have to become the whole final card of
the deck, and it needs a port built from scratch. That is the real fork; the
rest are details.

**2. Flash-safe or raw?** → *Recommend safe.* Raw physics peaks at 8 strikes in
a one-second window against WCAG's limit of 3. The difference is barely
perceptible and the unrestricted version is a genuine seizure risk on a page we
point paid traffic at. Toggle both in the panel before deciding.

**3. Play once, or re-trigger?** The port plays once on scroll-into-view then
parks lit — a sign flickering forever under a CTA is obnoxious and burns
battery on the phones that are most of this deck's traffic. A slow re-trigger
(say every 20 s of dwell) is easy if you want it to keep drawing the eye.

**4. Gas colour.** The CTA tube is `#F0793E`, sitting between brand copper
`#C0704A` and true neon orange so it reads as lit gas while staying on-brand;
locking it to exact copper is a one-line `--gas` change but costs some of that
quality. Separately, the roadside `FIELDS` plate is argon blue-white
(`#BFE6FF`) — mixed gas colours are what make a sign read as *roadside* rather
than as a modern backlit panel, but it is off-brand by definition. Both are
easy to pull back.
