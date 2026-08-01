# Rapid Mini-Site Build — card 10 pixel-reveal

**Status:** concept + working prototype. Nothing shipped, nothing pushed.
**Preview:** https://vm.fieldsestate.com.au/preview/rapid-build.html
**Prototype source:** [prototype.html](prototype.html) (standalone, self-contained, has a live tuning panel)

---

## The finding that makes this worth building

Card 10's CTA is a dead link.

```
src/pages/OffMarketPage/discovery/DiscoveryDeck.tsx:278
<a className={styles.cta} href="#build-strategy" onClick={onCta}>{card.cta_label} →</a>
```

`grep -rn "build-strategy" src netlify` returns exactly that one line. **There is no
element with `id="build-strategy"` anywhere in the codebase.** Every visitor who
scrolls the full deck and clicks "Build my complete selling strategy" today gets
a no-op — the URL hash changes and the page does not move. The click still fires
`forward_cta_clicked` and the Telegram intent alert, so it *looks* healthy in
analytics while delivering nothing to the visitor.

So this concept isn't decoration bolted onto a working flow. It's the missing
destination. That reframes the whole thing: the box is not "an animation on card
10", it is **what happens when the deck's one conversion action is honoured.**

---

## The concept

The deck spends nine cards proving we already know this house. Card 10 says
"here's what we'd do." The natural next beat is not a form — it's **showing the
work being done, unprompted, in front of them.**

1.5 seconds after the visitor settles on card 10, a panel begins assembling
itself underneath in scattered pixel blocks, resolves into a bordered sheet of
paper, and then fills with the *live* build feed of their actual house website —
sixteen named steps, each resolving with a real value from their own property.

The emotional beat we're buying: **"they started building it without me asking."**

This is the single strongest asset the off-market flow has and it's currently
unused — [[contact_capture_reality_and_address_mail_strategy]] established the
public won't hand over a phone or email, and [[organic_offmarket_pivot_2026-07-23]]
established 94% of visitors view exactly one address (owner lookup) and the
bottleneck is *engagement*, not traffic. A build that happens without a form is
the only kind of "conversion" this audience will accept.

### Why a white box on a black deck

The deck is black ground / birch ink / copper accent. A pale panel is the single
biggest tonal inversion available — it grabs the eye without a colour that isn't
ours. The prototype uses `--paper: #F6F1EA`, deliberately **not** `#fff`: pure
white reads as a browser dialog or a cookie banner. Birch paper reads as *a
document is being made*, which is the story.

---

## The reveal mechanic

Five phases. All numbers below are the tuned defaults in the prototype — the
panel in the bottom-left lets you dial each one and replay.

| # | Phase | Timing | What happens |
|---|-------|--------|--------------|
| 0 | Dwell | `0 → 1500ms` | Card 10 crosses 0.5 intersection ratio. Timer starts. Nothing visible. |
| 1 | Fill | `1500 → ~2570ms` | Pixel cells pop in on a downward-biased, jittered schedule. Slot height animates 0 → measured height in step, so the page *grows with* the box. |
| 2 | Stroke | from `fill × 0.55` | Copper border draws as four separate strokes: top → right → bottom → left, 170ms apart. Starts before the fill finishes — the shape is legible by then, so the frame reads as containment rather than decoration. |
| 3 | Consolidate | `~2570 → 2830ms` | A single opaque paper layer crossfades over the cell grid; grid fades out. |
| 4 | Content | `+140ms`, overlapping | Header and step list fade in. Steps then stream and resolve. |

### The pixel schedule — why it looks Matrix and not like a progress bar

Each cell's animation delay is:

```js
const t     = row / (rows - 1);
const eased = t < .5 ? 2*t*t : 1 - Math.pow(-2*t + 2, 2)/2;   // easeInOutQuad
const d     = (eased * FILL * bias) + (random() * FILL * (1 - bias)) + random() * JITTER;
```

Three things each do specific work:

- **`eased`, not linear** — the wavefront starts slow, rushes the middle, settles
  at the bottom. This is the "non-uniform rate" in the brief. A linear ramp looks
  mechanical; the ease looks like something *loading*.
- **`bias` blends wave against pure randomness** (default 78%). At 100% it's a
  strict top-to-bottom curtain — too orderly. At 0% it's static noise — no
  direction. Around 75–80% you read a direction *and* a scatter.
- **7% "leader" cells** land at 35% of their scheduled delay with their own
  overshoot keyframe. These are the isolated blocks that appear far ahead of the
  front. **This is the single detail that makes it read as Matrix.** Set leaders
  to 0 in the tuning panel and the effect immediately becomes ordinary.

### Tuned defaults (`REVEAL_SPEC`)

```js
REVEAL_SPEC = {
  dwellMs:     1500,   // brief's 1.5s — the whole trigger
  cellPx:        13,   // nominal; auto-coarsened under the budget (below)
  fillMs:       900,
  jitterMs:     380,
  leaderPct:      7,
  downwardBias:  78,   // %
  cellBudget:   900,   // hard node ceiling
}
```

### Two defects found and fixed while prototyping

Both are load-bearing — a naive implementation hits them and they look like bugs
in the *idea* rather than the code.

**1. Node count.** At 13px cells a 900×540 box wants ~2,800 divs each running its
own transform + opacity animation. Fine on this desktop; jank on a mid-range
Android, which is most of this traffic. Fix: a `CELL_BUDGET` of 900 that grows
the cell size until the count fits. Coarser pixels actually read *more* Matrix,
so the degradation is free rather than a compromise.

**2. Vertical seams.** `grid-template-columns: repeat(N, 1fr)` puts cell edges on
fractional pixels (measured: 23.13px per cell, lefts at `183.31, 206.43, 229.56,
252.70, 275.82…`). Where the accumulated fraction crosses a rounding threshold
the antialiased gap between neighbours becomes a visible hairline — producing
**bright vertical lines every ~185px straight down the panel**, exactly at the
predicted boundaries. Fix: `box-shadow: 0 0 0 1px var(--paper)` on every cell, so
each one bleeds a guaranteed full pixel on all sides regardless of where its edge
lands, with `overflow:hidden` on the grid to clip the outer bleed. `transform:
scale(1.06)` alone is *not* enough — it only buys ~0.7px at this cell size and
the seams survive it. Verified fixed mid-fill, not just after consolidation.

**3. Dead air.** Unclamped jitter leaves a handful of straggler cells landing
~400ms after the wave, and consolidating had to wait for them — which showed as
roughly a second of empty white paper before any content. Fix: clamp every cell's
delay to a known horizon (`fill + jitter × 0.45`) and consolidate exactly at that
horizon, with content fading in 140ms later so the paper settling and the first
words are one motion.

### Reuse the canvas engine, not this DOM grid

`15_Off-Market/Concepts/Hero_image_reveal/PixelReveal.tsx` (built the same day)
already solves the neighbouring problem — a hero *photo* resolving out of coarse
blocks — with a **canvas** engine, a per-cell delay field (diagonal projection
blended with radial distance, plus jitter), and a settled-layer optimisation that
only redraws cells currently in flight.

It is not directly droppable here: it requires an image `src` and works by
sharpening mip levels of that image, whereas this box materialises from nothing.
But for the React port, **its engine is the better foundation than the 851-div
grid in this prototype** — canvas sidesteps the node budget and the fractional-
pixel seams entirely (both defects above are DOM-grid-specific and simply do not
exist on canvas). Its `shape`/`scatter` params are the same idea as this
prototype's `downwardBias`/`jitter`, and its **deterministic seeded RNG** is
better than the `Math.random()` used here — repeat views look identical, which
matters for a returning owner.

Worth deciding deliberately: if both effects ship in the same page family they
should share one visual language and ideally one engine.

### Accessibility & motion

`prefers-reduced-motion: reduce` skips phases 1–3 entirely — the box is simply
present, fully populated, no growth transition. This is not a nicety: a
900-element scatter animation is exactly the class of motion that triggers
vestibular symptoms.

---

## What goes in the box

This is the part worth arguing about, and the reason the folder is called
*Rapid Mini-Site Build*.

**The box is a live window onto the house-website build that is already
happening.** We do not need to invent content — the feed exists:

`netlify/functions/property-report-progress.mjs` already returns a 16-step
ordered checklist, polled every 1.5s by the existing live build page:

```
address_resolved · cadastral · floor_plan · satellite · street_view · gallery
comps · valuation · walking_distances · market_position · scarcity
scarcity_story · positioning · personas · buyers · analyst_handoff
```

The prototype renders those sixteen verbatim with plausible resolved values
(`612 m²`, `6 within 700m`, `$1.42M–$1.61M`, `650m to school`, `41 watching`).

Each line does double duty: it's a progress indicator *and* a proof point. By the
time the list finishes, the visitor has watched us demonstrate sixteen distinct
things we know about their house — which is a far stronger argument than any
paragraph on card 10 could make.

### Editorial compliance

The step values must respect the house rules ([[feedback_no_advice_data_only]],
[[feedback_no_valuation_in_headlines]]):

- `valuation` shows a **range** (`$1.42M–$1.61M`), never a single figure. This is
  consistent with [[valuation_method_comparables]] — `reconciled_valuation` as a
  single number is deprecated.
- No step label may contain an instruction. "Positioning angle chosen" is a
  statement of what we did; "Best time to sell" would be advice. Watch this when
  writing the real labels.
- `analyst_handoff` → "Reviewed by Will" is a commitment we have to actually
  honour, or it's a false claim. Either wire it to something real or soften it.

---

## Integration path into DiscoveryDeck

Deliberately small. The deck is live traffic — see
[[offmarket_two_decks_live_vs_ladder]] for the wrong-file trap
(`OffMarketPage/OffMarketDeck.tsx` is the *other*, ladder deck — do not edit it
for this).

1. **New component** `discovery/BuildReveal.tsx` + `buildReveal.module.css`.
   Self-contained; owns its own timers and grid. No changes to `CardBody`'s other
   nine branches.
2. **Mount it inside the `strategy` case**, after the CTA and save-links — not as
   a sibling of `<main>`. In the prototype the box sits outside the card and the
   ~250px gap is visible; it needs to be *attached* to card 10 to read as
   "forming underneath". Note card 10 is `min-height: 100svh` with
   `justify-content: center`, so appending content re-centres the whole card —
   the slot must animate its own height (as the prototype does) rather than
   letting flex re-layout, or the copy above visibly jumps.
3. **Trigger** off the deck's existing IntersectionObserver — it already computes
   `active`, so `active === total - 1` plus a 1500ms timer is the whole trigger.
   No second observer.
4. **The CTA becomes a shortcut, not a requirement.** Clicking skips the dwell
   and scrolls the box into view. Change `href="#build-strategy"` to a real
   handler so the dead link dies with this change.
5. **Data.** Two options — see open questions.

### Analytics

Reuse the existing schema so the offline journey builder and the RL reward ledger
(`OFFMARKET_EVENTS`) pick it up without changes — same pattern as
[[offmarket_discovery_deck_analytics]]:

| Event | When | Why it matters |
|---|---|---|
| `build_reveal_started` | phase 1 begins | denominator for everything below |
| `build_reveal_completed` | content phase | did they stay ~3s to watch it form |
| `build_steps_watched` | on exit, `{steps_resolved, dwell_ms}` | **the real engagement metric** — how far down the sixteen they stayed |
| `build_cta_clicked` | box CTA | the conversion this whole thing exists for |

`build_steps_watched` is the one to instrument carefully. It answers the question
that decides whether this concept survives contact with real traffic: *does
watching a machine enumerate sixteen facts about your house hold attention, or do
people leave at step three?* Everything else is vanity.

---

## Open questions for Will

1. **Real build or theatre?** Two honest options:
   - **(a) Real** — reveal triggers an actual on-demand mini-site build for the
     slug, and the box polls `property-report-progress` for genuine step events.
     Strongest possible version; every value is true. Cost: a resolver run per
     deck-completion, and the ~14.6k indexed set means we cannot pre-build all of
     them. Would need a guard so bots/crawlers don't trigger builds.
   - **(b) Replay** — the discovery doc already contains everything the steps
     would show, so the box replays known facts on a synthetic cadence. Zero
     backend cost, instant, no build queue. But the timing is a performance, and
     if we ever say "building" while nothing is building, that's a claim we can't
     stand behind.

   My recommendation: **(b) for the copy, (a) for the CTA.** The box replays what
   we already know (all true, just pre-computed — the honest framing is
   "Assembling from the data behind the pages above", which is what the prototype
   says, *not* "building now"). Clicking the box CTA then kicks the real build and
   hands off to the existing live build page. That gets the theatre without the
   dishonesty and without a build queue sized to anonymous traffic.

2. **What is the box's CTA?** The prototype says "Open my house website →". The
   alternative is to keep the deck's existing lower-commitment SMS/WhatsApp/
   Messenger save row inside the box instead, where it now has far more context.
   Possibly both.

3. **Does the box replace or supplement the existing CTA?** Right now the deck's
   copper CTA sits above the box and the box has its own. Two CTAs 300px apart may
   split attention.

4. **Currently-listed guard.** [[listed_vs_offmarket_guard]] and
   [[ayh_currently_listed_guard]] — a home that's on-market must not get a build
   offer. If the reveal triggers a real build (option a) it needs the same guard.

5. **Trigger on card 10 only, or earlier?** Card 10 is the last card, so only
   visitors who scroll the entire deck ever see this. If completion rate is low,
   the best animation in the world reaches nobody. Worth pulling
   `deck_exit.max_index_reached` first to size the audience before building.

---

## Files

| File | What |
|---|---|
| `prototype.html` | Standalone working prototype. Mock card 09 + real card 10 copy + the box. Tuning panel bottom-left (desktop only). Also copied to `/home/fields/offmarket-preview/rapid-build.html` for viewing. |
| `README.md` | This document. |

**Verification done:** rendered headless at 900×900 and at 390×844 (mobile,
DPR 2), screenshotted across the full sequence — mid-fill, stroke, consolidate,
content, final. Cell count confirmed at 851 (under budget). Seam geometry
measured directly from the DOM to confirm the diagnosis before fixing, then
re-verified mid-fill after. No JS errors.

**Two problems the mobile pass surfaced** — neither is cosmetic:

1. **The gap above the box is much worse at 390px.** Because the box currently
   sits outside card 10, there's ~175 CSS px of dead black between the CTA and
   the panel. It does not read as "forming underneath" — it reads as a separate
   section. Reinforces integration step 2: the box must mount *inside* the
   strategy card.
2. **The box is far taller than a phone viewport.** Sixteen steps plus a header
   at 390px wide overflows well past 844px, so the visitor watches the top ~40%
   of the panel form and the rest assembles off-screen — the eye-catching part of
   the effect is largely wasted on the majority of this traffic. Needs a decision
   before any port: cap the panel to roughly viewport height and let the step
   list scroll/rotate within it, or show a condensed set of steps on small
   screens. **This is the most likely reason the concept underperforms if shipped
   as-is.**

**Not done:** real-device performance (headless on a loaded 2-core VM is not a
proxy for a mid-range Android), no React port, no integration with the live deck,
nothing pushed to GitHub.
