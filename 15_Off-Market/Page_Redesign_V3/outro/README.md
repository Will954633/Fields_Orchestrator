# The outro — cracked glass, code behind, the ship's computer

What happens when someone presses **"Build my complete selling strategy"** on card
10 of the off-market discovery deck. The screen cracks where their finger landed,
the fracture races across the pane, the glass falls away, and the matrix code that
has been running behind it all along is revealed — with a computer voice reading
the build sequence over the top.

**Try it:** https://vm.fieldsestate.com.au/concepts/off-market-v3/outro/crack-demo.html
Sound is on by default — the toggle is top right. There is a build stamp bottom
left; if it does not change after a rebuild, you are looking at a cached script.

| | |
|---|---|
| The sequence | [`crack-demo.html`](crack-demo.html) |
| Voice, on its own | [`voice-test.html`](voice-test.html) |
| Voice candidates | [`voice-audition.html`](voice-audition.html) — audio deleted; `build_voice.py --audition` to rebuild |
| Signal candidates | [`../audio/alien-test.html`](../audio/alien-test.html) — 8 synthesis attempts + 3 NASA recordings |

End to end it runs about **20 seconds**: ~6s of glass, then ~14s of code, voice
and countdown.

---

## The one idea

**Two layers. Glass in front, code behind, and the code is only ever visible where
there is no glass.**

Everything here follows from that. The cracks are not decoration painted over the
page — they are holes, and a hole shows what is on the other side. Which is why:

- the impact hole is **flood-filled**, not tinted, so it reads as a gap into a dark
  space rather than a stain on the page;
- the glass carries a **faint smoky tint**, laid *under* the holes with
  `destination-over`, because black glass on a black background is invisible and
  there would otherwise be nothing to tell you where a hole begins;
- the code **does not start until the glass is completely gone**. Through the whole
  break you are looking into darkness. That was a deliberate call — glimpsing the
  code early makes it an effect; withholding it makes it a reveal.

## The beats

| | | |
|---|---|---|
| **impact** | 1.0s | Flash, recoil, the chip appears exactly under the pointer, one small hole punched through |
| **network** | 0.9s | The fracture races across the whole pane, clipped to a growing disc so it propagates rather than fades in |
| **settle** | 0.5s | It holds. Stress redistributing |
| **fall** | 3.8s | 67 pieces let go in waves from the impact outward — bigger first, each tumbling with its own spin and drift |
| **after** | — | The code starts on an empty screen, switches off right to left, and the lines type with the voice |
| **signal** | +1.0s | Cassini's Saturn radio emissions swell up under the code over 1.5s, ducking under each spoken line |
| **countdown** | 3.0s | *"Approaching completion in T-3 seconds"* — then the digit counts 3·2·1 on exact one-second beats, the line pulsing on each, the quake escalating underneath |
| **complete** | 1.6s | The signal stops the instant she begins *"Construction completed."* The last line lands in silence — the transmission **was** the build running, and the build has finished |

A `?seq=full` variant restores an earlier beat where a single crack ran to the top
and a gash opened along it. It was dropped: the gash is a slow, single-crack idea
and the pane break is a fast, everything-at-once idea, and running both read as two
effects stapled together.

---

## Files

### The effect
| File | |
|---|---|
| `crack.js` | The whole sequence. `FieldsCrack.strike(x, y, opts)` |
| `crack-demo.html` | A stand-in for card 10, plus the rain field and the typed lines |
| `cut_glass.py` | Cuts the crack artwork into tiling polygons |

### Artwork (Will)
| File | |
|---|---|
| `cracked-glass.png` | The impact chip. Dense, irregular, full of light |
| `cracked-glass-v4.png` | The whole-pane network |

### Generated
| File | |
|---|---|
| `glass_pieces.json` | 75 polygons cut from v4 — desktop |
| `glass_pieces_lo.json` | The same cut simplified to 886 vertices — phones |
| `glass_pieces_preview.png` | Every piece in a different colour, to confirm the cut tiles |

### Sound
| File | |
|---|---|
| `glass-audio.js` | Breaking glass, synthesised in Web Audio. No sample, no licence, 6.6KB |
| `build_voice.py` | Generates the spoken lines at build time |
| `voice/*.mp3` | `en-GB-Studio-C`. 7 clips (4 lines + `c3`/`c2`/`c1`), 88.2KB |
| `signal-bed.js` | The signal under the final scene. Fade, duck, stop |
| `../audio/nasa/saturn-radio.mp3` | Cassini, Saturn radio emissions. 208KB, **public domain** |
| `../audio/alien-test.html` | Where that clip was chosen, plus 8 synthesis attempts |

---

## Rebuilding

```bash
cd 15_Off-Market/Page_Redesign_V3/outro

# after new crack artwork
python3 cut_glass.py --preview                                    # 75 pieces, desktop
python3 cut_glass.py --min-area 0.0011 --eps 0.0055 \
                     --out glass_pieces_lo.json                   # simplified, phones

# after a copy change, or to try another voice
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
python3 build_voice.py                    # all 7 clips, current voice
python3 build_voice.py --audition         # 11 candidates -> voice-audition.html
```

`build_voice.py` uses Google Cloud TTS on the `fields-estate` project via
`gcloud auth print-access-token`. The API is already enabled. The whole set is a
few hundredths of a cent.

After any voice rebuild, **bump `VOICE_V` in `crack-demo.html`**. The filenames do
not change, so a cached clip would leave her saying the old line under the new
caption.

---

## Decisions, and why

**The crack is artwork, not code.** Two rounds of generating it procedurally got
close and never got there — the first read as a spider web (concentric rings at
shared radii), the second as a starburst (the lattice started too far from the
impact, so the centre was empty). Real glass throws long tapered splinters with
volume and a blown-out void, and hand-tuning that was never going to beat a render.

**The pieces are geometry, not artwork.** Asking an image generator for 200 shards
returns 200 handsome pieces that do not fit together, and every seam shows the
moment they move. One master image, cut programmatically, gives pieces bounded by
cracks the reader actually watched appear. This is the division of labour that
matters: **draw what has to look real, compute what has to fit.**

**The glass sound is synthesised.** A stock sample means a licence to check on a
commercial site, another 200–400KB on top of 2.5MB of artwork, and one fixed shape
that will not land on beats we have retuned six times. Synthesis is 6.6KB and
re-times for free. Acoustically: the impact is a broadband transient plus a brief
180→70Hz thump; a crack running is a sparse train of clicks that accelerates; the
tinkle is ~150 small resonators at 1.5–8kHz, front-loaded with stragglers, each
dropping slightly in pitch as it decays.

**The signal is a real recording, not synthesis.** Three rounds of synthesising a
*Contact*-style signal were rejected, because I had characterised the sound from
memory and never checked it. The film's signal is a variation of the **TARDIS**
effect — a key dragged along a gutted piano's bass strings, tape-slowed. It is a
sustained inharmonic metal resonance, and I had built pulses. `../audio/alien.js`
models the real mechanism and is a far better guess, but what actually got picked
was **Cassini's recording of Saturn's radio emissions** — public domain, no licence,
and alien because it is. Nothing synthesised was going to beat a measurement.

**The bed ducks under the voice.** It ramps to full as asked, then drops to 50%
for each spoken line and comes back. Without it the voice is fighting a
broadband noise bed in exactly its own frequency range. Both numbers are one
argument each in `crack-demo.html` if the duck should be deeper or gone.

**The voice is generated at build time, not by the browser.** The lines never
change and are identical for every reader. `speechSynthesis` is free but its voices
differ wildly across macOS, Windows and Android, which is no way to run a brand
moment. Seven files, one voice everywhere, no key in the browser, no per-view cost.

**The countdown is three separate clips, not one.** A single "three, two, one"
recording would mean reading the beats off its waveform and hard-coding them, and
they would drift the moment the voice, the rate or the wording changed. One clip
per number means the on-screen pulse and the digit are driven by the same loop
that triggers the audio, so they cannot fall out of step.

**The count waits for the sentence to actually finish.** Typing is paced to 82% of
each clip, so the last character lands while the voice is still going. Every other
line has a 500ms gap after it that hides this; the countdown chains straight on, so
it needs an explicit hold on the remaining audio. Without it, *"Three"* started
0.55s on top of *"…seconds"* — which is only visible if you measure clip end
against next clip start, not by watching the captions.

**The typing is paced to the speech**, not to a fixed characters-per-second. A fixed
rate either finishes early and leaves the voice talking to a static line or lags
behind it, and that mismatch is what makes captioned voice look cheap.

---

## Performance

Measured, not assumed — `window.__crackPerf` carries per-phase frame times.

| | chip | network | fall | worst frame |
|---|---|---|---|---|
| desktop | 59 | 60 | 56 | 50ms |
| iPhone 14 | 61 | 60 | 60 | 17ms |
| mid-range (4× CPU throttle) | 28 | 26 | — | 100ms |
| low-end (6×) | 19 | 19 | — | 83ms |

**The lesson worth keeping:** I assumed the 67 tumbling polygons were the cost and
spent a pass optimising them. Profiling showed the fall was the *fastest* phase at
38fps while the static crack ran at 11. The real cost was both PNGs being scaled
from 1254×1254 to full screen **every frame, twice, under `lighter` blending**.
Pre-rendering them once to screen-sized layers took the pre-fall phases from 11–13
fps to 60 and killed the stutter. "The complicated-looking part must be the slow
part" is exactly the instinct that wasted that pass.

Phones also get a capped device-pixel-ratio of 1.5, the simplified cut, one paint
per piece instead of fill-plus-stroke, and a third of the particles.

**Adaptive degrade.** The opening second is measured on the actual device; if it
cannot hold ~29fps the fall is replaced with a 700ms dissolve, keeping the fracture
— which is the memorable part — and skipping the expensive part. Decided from real
frames, not a user-agent guess.

## Accessibility

**`prefers-reduced-motion`** skips the sequence entirely rather than shortening it —
a screen appearing to shatter is close to the top of what that setting exists to
prevent. The reader gets a 0.5s cut to what is behind, every callback still fires in
order, and no sound plays.

**Sound is on by default** (Will's call, 2026-08-03). There is no autoplay problem:
nothing makes a sound until the CTA is pressed, and that press is the user gesture
browsers require — the context is armed inside the click handler either way, which
is what makes the audio legal to play at all.

The toggle stays, and it is deliberately **visible before the CTA** rather than
tucked away, because that ordering is the whole consent story: someone reading
about their house on a train can kill the sound before they trigger anything.
Worth re-checking if the button ever moves below the fold in the React port.

---

## Not done

- ~~Not wired to the real deck.~~ **WIRED, 2026-08-04.** Card 11's neon CTA runs
  it on every deck. `outro-deck.js` packages the demo's machinery (rain, voice,
  countdown, quake, signal bed) minus the demo's own chrome, and builds its DOM
  only when the button is actually pressed. `crack.js` and `signal-bed.js` now
  resolve assets against `window.FIELDS_OUTRO_BASE`, because the deck sits two
  directories below this folder.
- **What comes AFTER the sequence has still not been designed.** It ends on
  `fields:strategy-built` with the code shut down, the last line green, and
  scroll still locked. That is the open question now — presumably where the
  3-minute build actually begins. **This is the blocker**; everything
  else on this list is polish.
- **Not pushed to GitHub.** All of V3 exists only on this VM, by Will's own plan
  ("build it locally, iterate, then push once"). Worth doing before it gets much
  bigger — this is exactly what CLAUDE.md Rule 2 exists to prevent.
- **The pane reads as a spider web.** `cracked-glass-v4.png` has evenly spaced
  radials and rings at matching radii. It is the most obviously synthetic thing left
  and it is an art fix: same brief, uneven radial spacing, rings at varying radii,
  some radials terminating early. It would also vary the piece shapes for free.
- **2.5MB of assets** for one transition. Both PNGs are only ever used as masks, so
  they do not need that resolution — probably a 4–5× saving, worth proving rather
  than assuming. Best done after the v4 redraw.
- **Mid-range phones run the crack at 26–28fps.** Watchable, not smooth. Further
  gains would cost the smoky pane or the DPR, which is the wrong trade.

## History

`logs/fix-history/2026-08-03.md` — `[V3-OUTRO-CRACK]`, `[V3-OUTRO-GASH]`,
`[V3-ALIEN-SIGNAL]`, `[V3-OUTRO-SIGNAL-BED]`, `[V3-OUTRO-COUNTDOWN]`.

Every correction in this effect came from Will watching it and saying what was
wrong; the fix history records what each one actually turned out to be. Two
patterns are worth carrying into the next piece of work:

**Check the target before building it.** Three rounds of signal synthesis were
wasted because I described the sound from memory. One search found the real recipe
in a minute. When the thing being matched is externally defined, look it up first.

**Verify the layer that matters, not the visible one.** The captions looked perfect
while the voice was talking over itself, and the fall looked expensive while the
static crack was the slow phase. Both were only found by measuring the right thing.
