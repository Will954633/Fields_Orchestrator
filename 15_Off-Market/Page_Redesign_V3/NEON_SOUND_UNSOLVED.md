# The neon sign has no sound on Android — UNSOLVED

**Status: open.** Parked 2026-08-04 after five rounds of attempted fixes.
Everything below is what has already been tried so the next attempt does not
repeat it.

---

## The symptom, precisely

On Will's Android phone, on a built deck
(`preview/examples/23-bellbird-avenue-burleigh-waters.html`):

- The card-11 neon sign **lights and pulsates correctly on arrival.** The visual
  take is right, and it is right at the right moment. Timing is not the problem.
- It produces **no sound at any point** — not on arrival, not while flickering,
  not after it settles, not before.
- **Pressing the sign works perfectly**, with sound: glass shatter, code rain,
  the voice-over, the countdown, all audible on the same device in the same
  session, seconds later.
- Media volume is up. He has confirmed this repeatedly.

On a laptop the sign has sound.

---

## What has been ruled OUT (do not re-test these)

Will tapped all seven buttons on `audio/neon-sound-test.html` on the affected
handset and **heard every one of them.** That single reply eliminated most of the
search space:

| Ruled out | Because |
|---|---|
| The speaker can't do the frequencies | 100 Hz alone *and* 700 Hz alone were both audible |
| The hum recipe is wrong | The shipped recipe at ×1 was audible in isolation |
| The level is too low | ×1 audible, ×8 loud — the shipped level sits between them |
| Web Audio is blocked on the device | The 440 Hz control tone played |
| The page's audio path is broken | Glass audio works on the same page, same session |
| The phone is on silent / wrong volume channel | Confirmed by Will, repeatedly |

So the sound the sign makes is a sound this phone can make. The failure is in
**when and how the neon's audio context is created**, not in what it plays.

---

## What has been tried, in order, and what happened

1. **Added odd harmonics (300/500/700 Hz).** Theory: a handset speaker rolls off
   below ~500 Hz and cannot reproduce a 100 Hz ballast. → No change. The test
   page later disproved the premise — 100 Hz alone is audible on his phone.
2. **Raised the level to ×3** after Will confirmed ×1/×8 on the test page.
   → No change.
3. **Made the ballast continuous** (`0.55 + 0.45·lvl`) instead of gating the hum
   off emission, so it no longer vanished through every dropout of a take that is
   mostly dark. More faithful to a real transformer, and it should have helped.
   → No change.
4. **Removed 1.9 MB of eagerly-loaded crack assets.** Genuine improvement to page
   weight; irrelevant to this bug. → No change.
5. **Held the take until audio was provably live.** Rejected by Will on sight —
   *"it's not illuminating as soon as I arrive"* — a sign that sits dark is worse
   than a sign that strikes quietly. Reverted. The rule stands: **the visual
   never waits for the audio.**
6. **Trigger geometry.** Over-corrected `rootMargin` to `-25% 0px -25% 0px`,
   which made the sign unreachable and stopped the take firing at all. Reverted
   to `-18%` on the bottom edge only.
7. **Layout — a real bug, found and fixed.** Card 11 was the last card with the
   neon at its bottom, so the document ran out below it and the sign could never
   rise above **92% of screen height**. The take fired as it clipped the bottom
   edge and played its whole seven seconds in a sliver while the reader was still
   scrolling toward it. Fixed with `#card-11 { padding-bottom: 26svh / 38svh }`;
   the sign now rests at **59–62%**. This was worth fixing and it changed nothing
   about the sound.
8. **Rebuilt the context inside a gesture.** A context born outside a user gesture
   reports `state: "running"` on a handset and emits nothing, so `arm()` learned
   to tear down a load-born context and rebuild it on the first gesture.
   → No change.
9. **Fixed which events count as a gesture.** `touchstart`/`pointerdown` grant no
   user activation on Android — a finger going down may be the start of a scroll,
   so Chrome withholds activation until the gesture resolves as a tap. Activation
   lands on `touchend`/`pointerup`/`click`, none of which were being listened for,
   and `bornInGesture` had latched `true` on a `touchstart`, permanently killing
   the rebuild path. Now asks `navigator.userActivation.isActive` instead of
   inferring from the event type. **This was a genuine bug.** → Still no sound.

Also fixed along the way: the `?audiodebug=1` readout was deleting its own test
button eight times a second (`box.textContent` wipes all children).

---

## Why none of this was caught locally

**Headless Chrome cannot reproduce any of it.** It reports
`navigator.userActivation` as active from a cold load, honours audio with no
input, and has no speaker. Every local measurement came back healthy while the
phone was silent. `--autoplay-policy=document-user-activation-required` helps a
little but does not model Android's touch-activation rules.

**We have never once seen a reading from the affected device.** Five rounds of
fixes were aimed at a system whose actual state was never observed. That is the
single biggest thing to correct next time.

---

## The leading hypothesis, untested

> **The reader never taps anything before reaching the sign, so there is no user
> activation at all — and the one tap that does arrive is the press on the sign
> itself, by which time the take is over.**

This fits every observation exactly:

- Pure scrolling grants no activation on Android. Chrome's activation comes from
  a tap gesture, not from `GestureScrollBegin`/`Update`.
- So the take runs, correctly and on time, with the audio context suspended.
  `frame()` no-ops. The sign lights and is silent — *exactly* what Will sees.
- Then he presses the sign. That press is a real `click`, so the glass context is
  born activated and the whole shatter sequence is audible — *also* exactly what
  he sees.
- **And the sign can never recover**, because the take is one-shot: by the time
  activation exists, `done` is true, `frame()` is never called again, and
  `settle()` has already faded the master gain to zero. There is no path from
  "audio became available" back to "make the hum audible". **This gap is real and
  currently unhandled**, regardless of whether it is the whole story.

It also explains the one time it worked: on that load he must have tapped
something — a chapter cue, the intro's skip — before scrolling down.

---

## What to do next (Will's plan, and the right one)

**Build the smallest possible test page and get scroll-triggered sound working
there before touching the sign again.** No deck, no discharge physics, no take,
no IntersectionObserver geometry, no CSS variables. Just:

> three screens of filler → a target at the bottom → when it scrolls into view,
> play a 440 Hz tone for two seconds.

Then walk variants on the phone, in this order, reporting only "noise / no noise":

1. **Pure scroll, no tap anywhere.** Establishes whether scroll-triggered audio
   is possible on Android at all. If this is silent, that is the answer and the
   sign's design has to change rather than its code.
2. **Tap once on blank page area first, then scroll.** Isolates whether a prior,
   unrelated tap is sufficient.
3. **One shared AudioContext** created on that first tap, reused for everything,
   instead of the three the deck currently builds (neon, glass, signal bed).
   Some Android builds are unhappy about multiple contexts; cheap to eliminate.
4. **`<audio>` element instead of Web Audio.** Different permission path, and if
   it works it is a legitimate fallback for the hum specifically.

Each variant should print `navigator.userActivation.isActive` /
`.hasBeenActive`, `ctx.state`, and a frame counter **on the page in large text**,
so a single screenshot from the phone answers everything.

Then bring the finding back to the sign. If it turns out scroll cannot produce
sound without a tap, the honest design options are:

- Ride the sign's sound on the **first tap anywhere in the deck** — the chapter
  cues are already real clickable anchors, so most readers will have tapped one.
- Add the missing **late-arrival path**: keep the graph alive when a take
  finishes silently, and energise the hum briefly if activation arrives later —
  suppressed if that activation is the button press itself, or it will hum
  underneath the shatter.
- Accept the sign is silent until pressed, and design for that.

---

## Files involved

- `preview/neon_cta.js` — the sign, its take, and all of its audio
- `audio/neon-sound-test.html` — the seven-tone diagnostic Will has already run
- `preview/deck.css` — `#card-11 { padding-bottom }`, fix #7 above
- `outro/glass-audio.js` — the context that **does** work, for comparison
- Fix history: `[V3-NEON-TOUCHSTART-NOT-ACTIVATION]` and
  `[V3-NEON-PINNED-TO-BOTTOM]`, both 2026-08-04
