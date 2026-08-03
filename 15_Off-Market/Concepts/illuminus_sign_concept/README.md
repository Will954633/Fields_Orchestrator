# Illuminus — the off-market CTA as a night neon sign

Two versions:

| | View |
|---|---|
| **Wall sign** — the tight pill, closest to the current CTA | [index.html](https://vm.fieldsestate.com.au/concepts/off-market/illuminus_sign_concept/index.html) |
| **Roadside pylon** — marquee cabinet on posts, with chase bulbs | [roadside.html](https://vm.fieldsestate.com.au/concepts/off-market/illuminus_sign_concept/roadside.html) |

Both run the same discharge engine and the same three-swells-then-flicker
sequence. The roadside version adds a second, physically different emitter —
see [Roadside](#roadside) below.

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
full take, steady burn lands at **97.4% mean with a 6% residual shimmer** —
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

**Verified:** sampled mid-chase during steady burn, 22 of 36 live bulbs are
mid-transition at any instant (temperature histogram across quintiles:
`10 · 12 · 0 · 0 · 14`). The filaments genuinely smear rather than switching
binary, which is the whole claim.

### Roadside-specific decisions for Will

- **The `FIELDS` plate is a different gas** — argon/mercury blue-white
  (`#BFE6FF`) against the neon orange. Mixed gas colours are what make a sign
  read as *roadside* rather than as a modern backlit panel, but it is off-brand
  by definition. Easy to pull back to a warm white if you'd rather. It also
  settles a beat *before* the main tube, which is how a genuine multi-circuit
  sign wakes up.
- **The cabinet is squarer than a real pylon.** Roadside signs are tall because
  they're read at 80 km/h from 200 m. Ours has to stay readable in a scroll
  deck, so the CTA is set over three lines rather than stacked vertically.
- **This is a bigger commitment than the wall sign.** It is a scene — sky,
  road, structure — not a button. It would want to be the whole final card of
  the deck, not an element inside one. The wall version drops into the existing
  card; this one replaces it.

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

## Open questions for Will

1. **Ship flash-safe or raw?** Recommend safe (see above).
2. **Play once or loop?** The port plays once on scroll-into-view. A slow
   re-trigger (say every 20 s of dwell) is possible if you want it to keep
   drawing the eye.
3. **Gas colour.** Currently `#F0793E` — sits between brand copper `#C0704A`
   and true neon orange, so it reads as real neon while staying on-brand.
   Locking it to exact brand copper is a one-line change (`--gas`) but costs
   some of the "lit gas" quality.
