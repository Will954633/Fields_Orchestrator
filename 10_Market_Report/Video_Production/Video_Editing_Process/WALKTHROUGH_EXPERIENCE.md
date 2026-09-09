# Walkthrough Experience — the on‑page choreography system

How we turn the finished talking‑head clip into an **engaging, educational walkthrough**
that plays *over the live website*, and how to reproduce that quality first‑go for the
next suburb/month.

> **This document covers the second half of the process.** The first half — raw footage →
> clean embeddable `.mp4` (cull, crop, grade, denoise, caption) — is the ffmpeg pipeline
> documented in [README.md](README.md) / [RUNBOOK.md](RUNBOOK.md) / [OUTPUT_SPEC.md](OUTPUT_SPEC.md).
> This doc picks up where that leaves off: the clip is hosted, now make it *teach*.
>
> Reference build: **Robina — August 2026**, live at
> `https://fieldsestate.com.au/news/robina?walkthrough=1` (gated behind `?walkthrough=1`).

---

## 1. The north star

**We are not playing a video next to a chart. Will is sitting beside the viewer, and the
website is a sheet of paper he draws on as he talks.**

Everything else is derived from that one image. Two things move together the whole time:

1. **Will** — a circular talking head that glides around the page and changes size.
2. **The pen** — hand‑drawn marks and handwriting that appear *as he says them*, as if
   written in real time.

The goal is **engagement + learning**, in that order of difficulty:
- *Engagement* comes from movement synced to a real human voice (head glides, the page
  scrolls to each chart, the pen draws live). A static chart + voiceover is boring; this
  isn't.
- *Learning* is the harder, more valuable half. We borrow **Khan Academy's** core move:
  **write the concept on the screen as you explain it.** Don't just circle a number —
  write *"a symptom, not a predictor"* next to it while you say it. The handwriting is the
  teaching, not decoration.

If a future change ever fights the paper metaphor (chart scrolls off the edge, ink lands
over the logo, content zooms so the "paper" moves) — it's wrong, even if it looks flashy.
The paper stays still; we draw on it.

---

## 2. How it works (architecture)

```
/news/:suburb  ──(default)──▶  NewsSplitPage
                                 └─ "Market overview" pill ▶ MarketFlowProto   (React wrapper)
                                       └─ createMarketEngine()  (vanilla imperative engine)
                                             ├─ renders the 5 charts as innerHTML into fixed id hosts
                                             └─ WALKTHROUGH RUNTIME  ← what this doc is about
```

- **Route:** `src/routes/news.$suburb.tsx` → `NewsSplitPage` (NOT `MarketIntelligencePage`;
  that's only `?variant=control`). The market column mounts **`MarketFlowProto`**
  (`src/components/MarketFlowProto/MarketFlowProto.engine.ts` + `.css`), whose overview
  panel draws the charts imperatively into hard‑coded global‑`id` hosts.
- **The walkthrough runtime** lives inside that engine (search `Walkthrough with Will —
  live-page runtime`). It is a **viewport‑fixed overlay** appended to `document.body`:
  `#walkLayer` = `.wk-dim` (STAGE dimmer) + `#wkInk` (SVG for pen strokes) + `#wkAvatar`
  (the `<video>`) + `#wkCap` (spoken caption chip) + `#wkTransport` (play/scrub/close).
- **The clip is the clock.** On play, the `<video>` plays; a `requestAnimationFrame` loop
  reads `video.currentTime` and fires **beats** as time crosses each beat's `t`. This is
  why the pen keeps pace with the voice — there is no separate timer to drift.
- **Gating:** the whole thing only renders when `?walkthrough=1` is in the URL
  (`walkFlagOn()`), and the hero is only injected on the *overview* panel. Normal
  visitors see the page unchanged — the feature is dormant. This is what makes it safe to
  deploy to production before it's finished.
- **Hosting:** the clip is a static asset in the Website repo at
  `public/walkthrough/<slug>.mp4`, referenced by `WALK_SRC` in the engine. (Azure blob is
  retired; a GCS/CDN move is a future optimisation if repo size becomes a concern.)

### Why a bespoke runtime and not the old tour code
The engine already contained an older "guided tour" (`startTour`/`positionScene`) built
for the **standalone prototype's** DOM (it needs `#marketScroll`, a scroll container that
does not exist in the live `mountFlow`). Rather than retrofit it, the walkthrough runtime
is new and **viewport‑fixed** (avatar/ink/caption are `position:fixed`; the *window*
scrolls to each chart). That model is simpler and correct for a full‑page walkthrough.

---

## 3. The experience design rules (hard‑won — keep these)

These are the rules that make it feel right. Most were discovered by getting them wrong
first (see §6).

1. **The website is the paper. Nothing leaves the sheet.** No content zoom that pushes the
   chart off‑screen; the chart stays fully in view and static while docked. Movement comes
   from the head gliding, the page scrolling between charts, and the pen drawing — not from
   moving the chart.
2. **Two pens, two jobs.** *Red* (`#dc3545`) marks attention — circles and arrows. *Blue
   BIC biro* (`#1c39b0`, the ink colour chosen in the artifact) does the *writing* —
   numbers and concepts. One consistent scheme across every chart.
3. **Handwriting in the brand hand.** All written text uses **"Fields Hand"** (embedded
   `@font-face`, data‑URI in the CSS). Avoid glyphs a handwriting font may not have —
   **no arrows `↑ ↓ →`**, use words ("up", "down", "leads"). `≈ $ % ~ + : .` are safe.
4. **Write in real time.** Every handwritten note animates on with a **left‑to‑right clip
   reveal** (`@keyframes wkWrite`, ~1.35 s; concept notes 1.7 s). It should look written,
   not popped. Respect `prefers-reduced-motion`.
5. **Time everything to the word.** A number appears the instant it's spoken ("50 days" at
   0:51, not at the start of the chart). A concept is written as it's explained. This is
   the single biggest lever for the "teaching" feel — split each number/concept into its
   own beat at its spoken timecode.
6. **Teach with the pen (Khan move).** At each interpretive moment, *write the idea*:
   "days on market", "more days = weaker demand", "a symptom, not a predictor", "prices
   move gradually", "leads prices by ~12 months", "directional, not certain", and the
   closing 3‑signal recap list. The concept text is what the viewer takes away.
7. **The head has two states.**
   - **STAGE** — large, front‑and‑centre (within the market column), page dimmed — for the
     intro, the interpretive bridges, and the close (talking *to* the viewer). Any writing
     in this state goes in a **note‑box** on the clean site background, not straight over the
     dimmed page (§3.1.10).
   - **DOCK** — small, pinned to the **bottom edge of the chart** (anchored to the chart,
     not the viewport, so it's never "too low"), page undimmed — for talking *about* data.
8. **Stay inside the market column.** The avatar, captions and handwriting are clamped to
   the right (market) column — `ROOT.getBoundingClientRect()`. Never drift over the left
   article rail, the nav, or the logo. Handwriting is additionally **width‑clamped** so a
   long line can't run off the right edge.
9. **Anchor ink to real data.** Circles/arrows/notes are placed from the chart's own
   **viewBox coordinates** → screen via `getBoundingClientRect`. The circle lands on the
   *actual* spike/point, not painted on top.
10. **Sparse and sequential.** Introduce one idea at a time; clear the slate between
    chapters (dock/stage both clear the ink). Resist crowding a chart with five notes at
    once. (Current known weak spot: Days‑on‑Market briefly holds relationship + "symptom"
    together — see §8.)
11. **Editorial guardrails still apply.** No forecasts/certainty — "directional, not
    certain" is deliberately written on the lending chart (CLAUDE.md §5). Verify every
    figure against the audio before shipping (CLAUDE.md §5/§6).

### 3.1 Reusable interaction patterns (apply to every chart)

These came out of the intro/Days‑on‑Market build‑out but are **universal** — bake them
into every chapter, not just Days‑on‑Market. Each maps to a helper that already exists.

1. **Chapter entrance is a ritual — title, settings, then settle.** When the walkthrough
   arrives at a chart, on the way to its docked position:
   1. **pause on the title and sweep a yellow highlighter across it** (`wkTitleHighlight`
      → `wkHighlight`) as the narrator names the chart;
   2. **put a small blue‑pen asterisk (`*`) sitting ON the top‑right corner of each
      *selected* settings pill** — mostly *on* the pill, slightly overhanging the corner
      (not floating above it). Measure the asterisk and place it by ~⅔ overlap
      (`left = pill.right − starW*0.62`, `top = pill.top − starH*0.16`). It flags that the
      chart is interactive and adjustable. (Selected pills = `.dom-pill.active` for
      dom/median/asking/withdrawn; `.seg button.on, .pill.on` for the explorer.) **As each
      asterisk is drawn, its pill blinks/flickers a couple of times quickly** (`wkBlinkPill`
      → `@keyframes wkPillBlink`, ~0.55 s) to draw the eye to the control being marked.
   3. **then drop the head down** to its beside‑the‑chart resting position.
   One entrance per chapter. ⚠ The highlighter uses `mix-blend-mode:multiply`, so it only
   works over the **light, undimmed** chart — do it in the DOCK entrance, never over a
   dimmed STAGE.
   **⏸ Watch the timing — pause the video if needed.** If, right after arriving, the
   narrator is about to say something **specific to the data** (the viewer needs to be
   looking at the chart), **pause the clip** while the title‑highlight + asterisks finish,
   then resume (`wkHold(seconds)` pauses the `<video>` and auto‑resumes). If he's just
   **introducing the chart or talking generally**, run the entrance **under his voice** — no
   pause. Decide per chart from the transcript: measure the gap between the "arrival"
   line and the first data‑specific line; a comfortable gap (≳ 10 s) → no pause; a tight
   gap (≲ 7 s) → a brief `wkHold`.
2. **Write in the narrator's order; erase before you replace.** A point that *supersedes*
   an earlier one ("it's a symptom, **not** a prediction" replacing "more days = weaker
   demand") should **fade the first out, then write the replacement in the same spot**
   (tag the first `"rel"`, `wkFadeTag("rel")` at +6 s, write the second at the same
   coordinates). This is the Khan erase‑and‑replace and it keeps the chart uncluttered.
3. **Transient concepts fade; headline facts persist.** A concept that's only relevant for
   one sentence should **fade after ~6 s** (tagged fade) rather than accumulate. Numbers,
   line‑labels and the circled data points stay until the chapter changes. This is the fix
   for "too many notes on screen at once."
4. **Horizontal for sentences, tilted for call‑outs.** Multi‑word *concepts* and *labels*
   read best **horizontal** (`.flat` — no rotation); keep the slight biro tilt only for
   short numbers/call‑outs. Long tilted sentences are hard to read.
5. **A label and its value are one unit — but the *label* is transient.** When a written
   label pairs with a value ("days on market" + "50 days"), the **value is the headline fact
   and persists**; the **written label fades** a few seconds after it's read (tag it and
   `wkFadeTag` on a later beat, per §3.1.3) so it doesn't clutter the chart while the number
   and the circled spike stay. When both are on screen together, place the value relative to
   the label's rendered rect (`label.getBoundingClientRect().right + gap`), never by
   independent coordinates; if the label fades independently, anchor the value on its own so
   it survives (Days‑on‑Market: "50 days" is spike‑anchored, "days on market" is tagged
   `domlabel` and fades at t≈44). Keep the pair clear of the right edge (issue #26).
6. **Directional arrows are drawn, never typed.** `↑ ↓ →` are not in "Fields Hand" — draw
   them as pen strokes (`wkArrowGlyph`, blue, tagged with the concept so they fade with
   it). Same for any glyph beyond `≈ $ % ~ + : . -`.
7. **Give the transport chapter skip.** ⏮/⏭ over a per‑walkthrough `WALK_CHAPTERS` array
   (the dock/stage start times). Maintain that array whenever you add/re‑time a chapter.
8. **Think in horizontal lanes.** A chart has a few clear bands: a **title/header lane**
   (top), one or two **concept lanes** (upper, above the data), and **data‑point call‑outs**
   (on the points). Assign each note a lane (a viewBox `y`) and never put two long lines in
   the same lane — that's the #1 source of overlap. Leave ≳ 40 viewBox‑y between long
   lines.
9. **Every moving variable gets a hand‑drawn arrow.** Whenever the copy states the
   *direction* of a variable ("days on market up", "demand down", "prices flat"), draw a
   **hand‑drawn arrow** showing that movement — up / down / sideways — right beside the
   word. It must be **blue** (same pen as the writing) and in the **same rough, hand‑drawn
   style as the red data arrows** (`wkDirArrow`, not a font glyph). Tag it with the
   concept so it fades with the text. This turns a stated relationship into a *shown* one:
   e.g. Days‑on‑Market's "↑ more days on market = weaker demand ↓". Apply it everywhere a
   direction is spoken (see the close recap: up / up / down / sideways‑down).
   **Inside a STAGE note‑box (§3.1.10) the arrow is an *inline* child of its line**
   (`wkBoxNote(text,…,dir)` renders a small `wk-boxarrow` SVG in the flex row), not free ink
   beside the box. Free ink drawn *next to* a growing box gets covered when a later, wider
   line widens the box over it (issue #28) — inline arrows can't, and they stay glued to
   their word.
10. **STAGE writing goes in a note‑box, not straight on the page.** When the head is in
    **STAGE** (full‑view, page dimmed/blurred), handwriting placed directly over the blurred
    chart is hard to read. Write STAGE concept lines into a **note‑box**: a rounded‑corner
    panel (`wk-notebox`, `border-radius:16px`) filled with the **site background colour**
    (`#f8f9fa`) so the blue biro sits on clean "paper", not over the dimmed page. Rules for
    the box:
    - **Horizontal only.** Box lines never tilt (`.wk-boxline` has no rotation) — the box is
      a legibility surface, so slanted text defeats it. (The tilt stays for on‑chart DOCK
      call‑outs.)
    - **One box per STAGE segment**, positioned to the **left** of the head so it doesn't
      overlap the avatar (`wkStageBox(fx,fy)`, default `fx≈0.27`); lines stack downward and
      the box grows to fit. Cleared with the ink on the next chapter (`clearWkInk` removes
      `.wk-notebox`).
    - **Same write‑on + biro treatment** as free notes (left‑to‑right clip reveal, ballpoint
      filter), and directional arrows go **inline** in the line (see §3.1.9). Helpers:
      `wkStageBox` / `wkBoxNote(text,instant,big,fx,fy,dir)`.
    - This is the STAGE counterpart to §3.1.5's on‑chart placement: on a **light DOCK** chart
      write on the chart; on a **dimmed STAGE** write in the box.
    - **Mobile:** the box goes `.mob` — **centred** horizontally (`left:50%`), directly **under the
      head + caption** (head moves to the top, `wkStage` mobile branch), width‑capped to `92vw`
      with lines allowed to **wrap** and centre‑align. A left‑anchored desktop box runs off the
      left edge on a 390px screen (issue #33).
11. **Two reference points = two circles, in narration order — NOTHING drawn between them.** When
    the copy compares two points ("from ~25 in June **up to** 50 in August", "peak of 1.5M … **down
    to** 1.49M"), do NOT circle a region or fire a Will‑hand arrow at one blob. Circle the
    **first‑mentioned** point, then — on the beat where the second point is spoken — circle the
    **second** point. The order follows the *narration*, not the calendar: whatever Will says first is
    circled first. **Never draw a connecting arrow or line between the two circles** — the pair of
    circles carries the comparison on its own. (Rule changed 2026‑09‑09 on Will's direction: the arced
    `wkArrowVB` connector and its helper were deleted from the engine; the old arc/direction rules
    lived here and in §3.1.14, both now retired.) Helper: `wkPointCircle(sel,VBW,VBH,pt,partner,note,
    instant,tag,delay)` (circle one point + a value note pushed clear). Applied to all five charts
    (DOM June→Aug, median peak→latest, asking Dec 2023→Sept 2026, withdrawn 23→53, lending 20%→10%).
12. **Anchor circles to the LIVE line, not hardcoded viewBox coords — and keep numbers off both.**
    Hardcoded `(vx,vy)` drift the moment the chart's range/data changes and the circle lands in
    empty space (median circles were sitting up in the "gradual decline" text, issue #30). Read the
    point from the rendered path at runtime (`wkMainPath` → `getPointAtLength`; `wkMedianPts` finds
    the peak = min‑y and the latest = endpoint; `wkAskLabels` reads each line for its leader
    target). Every value note is then **pushed to the outer side, away from its partner point**
    (`placeClear`) so a number never overlaps its own circle or its partner point. A runtime
    **anti‑overlap** pass (`avoidNoteOverlap`) additionally nudges any note off another note it
    collides with (the auto‑fix, §5c).
13. **Design mobile (≤640px) as a distinct layout, not a scaled desktop.** The 390px column
    compresses every viewBox‑x, so desktop coordinates collide and long lines bleed off‑edge. Rules:
    (a) STAGE head to the top, caption + centred note‑box below it (pattern 10); (b) DOCK head sits
    **lower** (`wkHeadAtChart` mobile overlap 0.28 vs 0.55) so it stops covering the chart it's
    talking about; (c) long DOCK notes **wrap** (`.wk-note{white-space:normal;max-width:82vw}`)
    instead of running off the right edge; (d) concept lines that sit low on desktop (e.g. "sellers
    adjusting") move **up into white space** and drop `big` on mobile so they never land on the
    caption bar; (e) give mobile‑specific viewBox positions via a `markMobile(desk,mob)` switch, and
    let `wkIsMobile()` gate every branch. **Verify mobile separately** — the QA harness (§5c) runs
    both viewports because mobile carries ~5× the layout findings.
14. **(RETIRED 2026‑09‑09 — connecting arrows removed.)** This rule governed the arc shape and
    first→second direction of the two‑point connector (`wkArrowVB`, issues #35/#36). The connector no
    longer exists: two compared points get two circles and nothing between them (§3.1.11). What still
    applies: read compared points from the *live chart geometry* (`wkMainPath`, or a colour‑targeted
    path like the blue `#007bff` lending line — §3.1.12), never from hardcoded coords that drift with
    the chart's range.
15. **Lock ink to the chart on scroll; boxes stay on screen.** Chart‑anchored ink (circles, arrows,
    on‑chart notes, highlights, the settings asterisks) lives in `#wkInkWrap`; a scroll listener
    translates the wrap by `(baseline − scrollY)` so it **rides with the chart** when the viewer scrolls
    or the page auto‑scrolls (item 8). STAGE note‑boxes, the avatar and the caption are NOT in the wrap —
    they stay fixed to the viewport. Anything you draw on a chart is chart‑anchored by default.
16. **⚠ KNOWN NO-OP as of 2026-09-09 — the chart camera does NOT visibly zoom. Do not rely on it; use
    circles/labels to carry any "zoom in / look closer" narration.** Confirmed on production
    (`robina?walkthrough=2`): Chrome computes an `<svg>` root's `transform-box` as `view-box`, so the CSS
    transform MEASURES as scaled (`getBoundingClientRect`) but PAINTS in viewBox user-space → nothing zooms.
    The ink wrap (a div) transforms fine, which is why the drawn ink can look like it moved while the chart
    underneath doesn't. The proper fix (future, deliberate task) is to transform a wrapper `<div>` with an
    explicit width/height around each chart svg, not the svg itself. See fix-history
    `[WALK-CAMERA-SVG-TRANSFORMBOX]`. The description below is the *intended* behaviour, retained for when it's fixed:

    **Zoom + pan (the camera) — use it where the narration walks along a specific stretch of data.**
    `wkCamera(svgSel, VBW, focusVx, scale, secs)` scales the chart svg **and** `#wkInkWrap` around the
    same screen point, so any annotations stay glued through the move; call it again with a new `focusVx`
    to **pan** (the CSS transition animates the translate); `wkCameraOff` returns to normal. Reach for it
    when Will narrates a *specific section or period* on a chart and a closer look helps — e.g. panning
    left→right across the "asking sat below sale" history, then zooming the recent convergence. Rules:
    (a) **never let the docked head cover the data being spoken to** — the focus is usually the upper/right
    of the chart, the head sits bottom‑left, so check the overlap per zoom; (b) fade/clear on‑chart text
    that would scale awkwardly *before* a big zoom; (c) a scene change (`clearWkInk`) resets the camera,
    so keep a zoom inside one dock scene; (d) use it a **few** times, not constantly — it punctuates, it
    isn't the default view. (e) **Draw the circles/notes first, THEN `wkCamera`** — zooming first and
    annotating after double‑transforms the ink off‑screen (the wrap transform applies twice); annotate‑
    then‑zoom keeps the ink glued and magnified with the chart. (f) For a target **low or high on the
    chart** (e.g. the withdrawn 2025/2026 bars near the bottom axis), pass the optional `foVy, VBH`
    (`wkCamera(sel,VBW,foVx,scale,secs,foVy,VBH)`) so it centres **vertically** too — a centre‑anchored
    scale would otherwise push a low target out of the clipped view and its number labels with it.

---

## 4. The choreography model (how it's built in code)

The walkthrough is a **beat list** (`walkBeats()` in the engine) — an array of
`{ t: <video seconds>, run: function(instant){…} }`. On playback, `run` fires when the
clock crosses `t`; on seek/rebuild it runs with `instant=true` (no animation).

The building blocks (all in the engine, prefixed `wk`):

| Helper | What it does |
|---|---|
| `wkStage(instant)` | Head large + centred in the market column, page dimmed, ink cleared |
| `wkDock(sel, instant)` | Scroll `sel`'s chart into view, head small at its bottom edge, ink cleared |
| `wkCircleVB(sel,VBW,VBH,vx,vy,rx,ry,arrow,instant)` | Red circle (+ optional arrow from Will) at a chart viewBox point |
| `wkNoteVB(sel,VBW,VBH,vx,vy,dx,dy,text,instant,big,flat,tag)` | Blue handwritten note at a viewBox point (+px nudge), width‑clamped. `flat`=horizontal (no tilt); `tag`=group id for fading. Returns the element. |
| `wkNote(text,sx,sy,instant,big,flat,tag)` | Same, at absolute screen px — use for a value placed relative to another note's rect (§3.1.5) |
| `wkFreeNote(text,fx,fy,instant,big)` | Blue note at a viewport fraction. ⚠ Superseded for STAGE by the note‑box below — free STAGE notes over a dimmed page are hard to read |
| `wkStageBox(fx,fy,instant)` | Create/return the STAGE **note‑box** — rounded panel on the site background (`#f8f9fa`), left of the head (§3.1.10) |
| `wkBoxNote(text,instant,big,fx,fy,dir)` | Write one horizontal line into the STAGE note‑box (creating it if needed). `dir` appends an **inline** hand‑drawn arrow: `"up"/"down"/"left"/"right"`, or `"right-down"` for two |
| `wkEnter(chartSel,holdSec,instant)` | The chapter entrance: `wkTitleHighlight` + `wkSettingsStars`, optionally holding the video (§3.1.1) |
| `wkTitleHighlight(chartSel,instant)` | Scroll the chart's `.section-title` into view + yellow‑highlighter sweep it |
| `wkSettingsStars(chartSel,instant)` | Blue‑pen `*` at the top‑right of each **selected** settings pill (`.dom-pill.active`; explorer `.seg button.on,.pill.on`) |
| `wkHold(sec)` | Pause the `<video>` (and narration) for `sec`, then auto‑resume — for entrances where he reaches the data too fast to run under his voice |
| `wkConceptDir(noteEl,dir,instant,tag)` | Draw a hand‑drawn blue direction arrow just right of a note (moving‑variable illustration) |
| `wkDirArrow(x,y,dir,len,instant,tag)` | Hand‑drawn **blue** directional arrow (`"up"`/`"down"`/`"left"`/`"right"`), same rough‑pen style as the red arrows — use for any moving variable in the copy (§3.1.9); tag to fade with its concept |
| `wkFadeTag(tag,instant)` | Fade + remove every note *and* pen stroke carrying `tag` (erase‑and‑replace, §3.1.2) |
| `wkHeadAtChart(sel,size,instant)` | Re‑pins the head to a chart's bottom edge |
| `WALK_CHAPTERS` / `wkSkip(dir)` | Chapter start times + the ⏮/⏭ transport skip (§3.1.7) |

Everything is driven by two coordinate facts per chart: its **container selector** and its
**viewBox size**. Given those + a data point's viewBox `(vx,vy)`, ink maps to the pixel.

### Reference: the five Robina charts

| Chart | Selector | viewBox | Anchor points used (viewBox) |
|---|---|---|---|
| Days on Market | `#domChartHost svg.chart-svg` | 780×340 | spike = last‑3 of the trailing‑3 line (computed live via `domGeometry`) |
| Median price | `#mpriceChartHost svg.chart-svg` | 780×340 | peak `611,66` ($1.5M) · latest `720,79` ($1.49M) — default 3yr view |
| Asking vs sale | `#askingChartHost svg.chart-svg` | 780×340 | **set `median:true`, range `10yr`** first; Dec‑2023 flip `546,124` · Sept‑2026 converge `720,74` |
| Homes withdrawn | `#dsChartHost svg.chart-svg` | 1000×420 | 2025 bar `917,359` (=23) · 2026 bar `962,334` (=53) |
| New‑house lending | `#ac` (inside `.liexp.ex-slot`) | 900×374 | Q4‑2025 `770,273` (20%) · Q2‑2026 `808,283` (10%). **No zoom** (tall multi‑panel). Async mount — gate on `#ac` existing |

> These coordinates are specific to Robina's data/ranges. For a new suburb, the *selectors
> and viewBox stay the same* but the anchor `(vx,vy)` must be recomputed for that suburb's
> data (the peak is a different quarter, etc.). Get them the way we did: an
> `Explore`/read pass over the chart engine's data arrays + geometry functions, or by
> screenshotting and reading the point positions.

### The Robina beat sheet (the finished choreography, as a worked example)

Times are video seconds. `▶` = concept/teaching write.

```
0    STAGE (intro)
23   DOCK Days-on-Market (force trailing-3 window)
35   ▶ "days on market" [tag domlabel]      (0:35 "known as its days on market")
44   fade "days on market" (wkFadeTag)      (label read; "50 days" persists)
48   circle June + "≈25"                    (0:48 "about 25 days in June")   ← 1st point
51   arrow June→Aug, circle Aug + "50 days" (0:51 "up to 50 days in August") ← 2nd point (§3.1.11)
84   ▶ "more days = weaker demand"           (1:24 demand relationship)
110  ▶ "a symptom, not a predictor"          (1:54 the key reframe)
120  STAGE (bridge) — note-box
127  ▶ box: "Unlike share markets, home prices move gradually" [big]  (2:00)
134  ▶ box: "Homes are valued on 6 months of data, stocks change value instantly…"  (2:08)
156  DOCK Median
164  ▶ "gradual decline" (open lower-left)   (2:43)
170  circle peak + "$1.5M"                   (2:52 "1.5 million")   ← peak/latest READ from line (§3.1.12)
175  arrow peak→latest, circle + "$1.49M"    (2:55 "1.492")
186  DOCK Asking (median overlay on, 10yr)
198  ▶ "asking price"/"median sale" + blue leaders; FADE at 214 (§3.1.5/4b)
216  CAMERA zoom+pan L→R across the historical period (asking<sale)  ← §3.1.16
230  CAMERA off
236  circle flip + "Dec 2023"                (3:56)                ← 1st point
250  arrow flip→converge, circle + "Sept 2026" (4:11)             ← 2nd point
255  CAMERA zoom the recent convergence (Sept 2026); off at 263
264  ▶ "sellers adjusting"                   (4:32)
285  DOCK Withdrawn
300  ▶ "homes that didn't sell"              (4:56)
326  circle 2025 + "23"                      (5:26)                ← 1st point
334  arrow 2025→2026, circle + "53"          (5:40)                ← 2nd point
350  ▶ "trend has changed"                   (5:48)
368  STAGE (need a leading signal) — note-box
380  ▶ box: "a signal that moves BEFORE prices" (6:19)
402  DOCK Lending (#ac) — entrance ritual on #subseg/#modeseg/#rangeseg pills (item 7)
414  ▶ "used by CBA + RBA"                   (6:48)
420  ▶ "leads prices by ~12 months"          (6:55)  [big]
435  SET explorer: 3-suburb / actual timing / all data (+re-star those pills)
479  SET range → 3 yr ("click on the three-year view")
510  RECENT: clear all text, lock to 3yr view
513  circle Q4-25 + "20%" (read from blue #007bff line)           ← 1st point
520  arrow Q4-25→Q2-26, circle + "10%"                            ← 2nd point
548  ▶ "directional, not certain"            (9:07)
583  STAGE (close) — note-box
591  ▶ box: "days on market" ↑ (inline arrow) (9:49 recap builds)
599  ▶ box: "homes withdrawn" ↑
607  ▶ box: "new-house lending" ↓
622  ▶ box: "so: flat to declining" → ↓ [big] (10:12)
```

---

## 5. Producing a new walkthrough — the systemised process

Do these in order. Steps 1–2 are the **editing pipeline** (other docs); 3‑onward is this
system. Budget the on‑page choreography (4–6) as the real work — the asset is quick.

**1. Asset.** Produce the clean clip via the editing pipeline ([RUNBOOK.md](RUNBOOK.md)):
cull → crop to a circle → grade → denoise → export web mp4. Host it at
`public/walkthrough/<slug>.mp4` and point `WALK_SRC` at it (or make `WALK_SRC` suburb‑aware).
*Key params we used:* circle crop `crop=710:710:604:172` (measure the mask per shoot),
grade `eq=brightness=0.07:gamma=1.22:saturation=1.08:contrast=1.03`, denoise
`highpass=f=90,arnndn=m=<sh.rnnn>,afftdn=nr=8:nf=-28,speechnorm`.

**2. Transcript.** Transcribe verbatim **with timecodes** (Gemini — see §6; OpenAI credits
are dead). Save as `<slug>_Transcript.md`. The timecodes are the spine of the beat sheet.

**3. Map transcript → chapters → charts.** Walk the transcript and mark: which chart each
section is about (in scroll order), the exact **spoken timecode** of every number and every
teachable concept. This is the storyboard; capture it like the beat sheet in §4.

**4. Get the anchor coordinates** for each chart in this suburb: selector (same as Robina),
viewBox (same), and the `(vx,vy)` of each point you'll circle/label (recompute per suburb).

**5. Author the beat list.** Translate the storyboard into `walkBeats()`, and for **each
chapter** apply the reusable patterns from **§3.1** in this order:
- **entrance:** highlight the chart title as it's named (`wkTitleHighlight`), then dock;
- **read‑out:** one beat per number at its spoken second, placed on/next to its point
  (label+value as a unit, §3.1.5);
- **teach:** one concept write per idea at its spoken second, on its own horizontal *lane*
  (§3.1.8), horizontal for sentences, with drawn arrows if needed;
- **erase:** fade a concept (tagged, ~6 s) before writing one that replaces it (§3.1.2/3);
- keep the `WALK_CHAPTERS` skip array in sync with your dock/stage times.
Then the STAGE recap at the close. Follow every rule in §3 and §3.1.

**6. Verify locally, then ship.** See §7. Never push blind — dev‑ESM run + prod build +
headless screenshots first, then `gh api`, then live verify.

---

## 6. Issues we hit → how we fixed them → how to avoid them next time

| # | Issue | Fix | Avoid next time |
|---|---|---|---|
| 1 | 784 MB `.mov` upload looked complete but ffmpeg said "moov atom not found" | It was still uploading; waited until byte size was stable & matched Drive | Before processing, confirm size is stable and equals the source |
| 2 | OpenAI Whisper 429 — **credits exhausted** | Transcribed via **Gemini** (`GOOGLE_GEMINI_API_KEY`, `google-genai`) | Use Gemini for transcription. Note `gemini-2.5-pro` is retired → `gemini-3.1-pro-preview` |
| 3 | Custom gdrive token `invalid_grant` (7‑day expiry) | Will uploaded the clip to the VM directly | Don't rely on the VM gdrive token for large media; upload to the VM |
| 4 | Two ffmpeg jobs writing the **same output** corrupted it (104k decode errors) — from a double‑backgrounded run | Killed the orphan, re‑encoded to a fresh file, **validated with `ffmpeg -v error -i out -f null -` (0 errors)** | Never `nohup … &` *inside* a backgrounded tool call. Run encodes foreground; always integrity‑check the output |
| 5 | Azure blob host dead (DNS) for hosting the clip | Hosted in the Website repo `public/walkthrough/` | For now use repo `public/`; large binaries pushed via `gh api` JSON `--input` (below) |
| 6 | The engine's old tour was wired to the prototype DOM (`#marketScroll`) and didn't run in the live mount | Built a **new viewport‑fixed runtime** | Don't retrofit the old tour; extend the `wk*` runtime |
| 7 | Dev tolerated code that the **strict, minified prod bundle** would throw on (the historic `tip is not defined`) | Dev server runs ESM (same strictness) → a clean dev run + a passing `npm run build` is the proof; feature is flag‑dormant anyway | Always `npm run build` before deploy; keep the feature behind the flag until verified |
| 8 | `window.scrollTo` did nothing (page scroll container isn't `window`) | Used `element.scrollIntoView(...)` | Scroll the target element, not the window |
| 9 | Tall lending explorer: scrolling the *section card* left the chart below the viewport; and CSS‑zoom distorted it, dropping ink onto the CTA cards | Scroll the **chart element** (`#ac`) itself; **no zoom** for the explorer | Scroll the chart, not its card; don't geometric‑zoom multi‑panel charts |
| 10 | Ink from one chart persisted onto the next | Clear ink on **dock**, not just on stage | Any beat that moves to a new chart must clear the slate |
| 11 | Head drifted over the left **article column** | Anchor avatar/caption to the market column (`ROOT` rect), not the viewport | Everything clamps to the market column |
| 12 | Head sat **too far below** the chart | Anchor the head to the **chart's bottom edge**, not the viewport bottom | `wkHeadAtChart` — dock relative to the chart |
| 13 | **Content zoom pushed charts off the page** and ink over the logo | **Removed the zoom** — the paper stays still; movement is head + scroll + pen | Never move the chart content off the sheet |
| 14 | Colour scheme wrong (all one colour, then swapped) | **Red** circles/arrows, **blue biro** handwriting | Two pens, two jobs (§3.2) |
| 15 | Long/big handwritten lines ran **off the right edge** | **Width‑aware clamp** in `wkNote` (measure width, shift left to fit) | All notes clamp to fit inside the column |
| 16 | Arrow glyphs `↑↓→` risked missing in the handwriting font | Used words | Never put arrows in Fields Hand text |
| 17 | Numbers all appeared at once, not when spoken | Split each into its own beat at its spoken timecode | Author one beat per spoken figure |
| 18 | Handwriting "popped" instead of being written | Left‑to‑right **clip‑reveal** animation, slowed to ~1.35 s | Keep the write‑on; tune duration, don't remove |
| 19 | Background **goat noise** ~1:00–1:20 | Aggressive denoise chain (highpass + RNN `arnndn` + FFT + loudness) | No ML source‑separation on the VM — a distinct overlapping sound can be *suppressed*, not perfectly removed. Record in a quiet space |
| 20 | `gh api` PUT failed (exit 144 / arg length) for larger files | Build a JSON payload and `gh api … --method PUT --input payload.json` | Always use the `--input` JSON method for content pushes |
| 21 | Live screenshot caught a **half‑deployed** state (stale JS/CSS) | Waited for Netlify (~2–5 min; 16 MB asset ≈ 4.5 min) and re‑verified | Poll for the deploy (asset byte size flips / re‑shoot) before trusting a live screenshot |
| 22 | The **SVG ballpoint filter bleeds past the text's layout box** (region was ‑12%/124%), so two notes with a real layout gap still *overlapped visually* | Tightened the filter region to ‑4%/108% and left extra gap between adjacent notes | Any element with `filter:url()` renders wider than its box — keep the filter region tight and never butt two filtered notes edge‑to‑edge; leave a visible gap |
| 23 | **Width‑clamp fought relative positioning at the right edge** — a value placed at `label.right+gap` overflowed, so the clamp yanked it back *onto* the label | Anchored the label+value **pair** far enough from the right that the whole unit fits before clamping | Place label+value as a unit sized to fit the remaining column width; if it can't, shrink the font — don't rely on right‑edge real estate |
| 24 | **Two long horizontal lines collided** (the "days on market 50 days" header and the "more days…" concept both in the top band) | Moved the concept into a distinct lane (viewBox y 96) below the header | Assign every long line its own horizontal lane; ≳ 40 viewBox‑y apart (§3.1.8) |
| 25 | **Cursive width was underestimated** from character count, so coordinate math put notes too close | Verified every placement by screenshot at the real (30 px desktop) font size and nudged | Don't trust coordinate math for handwriting — screenshot at the deployed font size; cursive is wider than it looks |
| 26 | A faded concept left **orphan arrows** behind (text is a `div`, arrows are SVG `path`s) | `wkFadeTag` fades **both** by tag (inline opacity on div *and* path); tag every element of a concept group with the same tag | Treat a concept as a *group* — tag its text and its glyphs together, fade by tag |
| 27 | Dock/stage beats **auto‑clear all notes + highlights** (`clearWkInk`) | Intentional (slate‑clear between chapters); sequence transient effects (title highlight) *before* the next dock | Remember: moving to a new chart wipes the slate. Put entrance effects on the entrance beat, not before it |
| 28 | STAGE recap **arrows drawn as free ink beside the note‑box got hidden** — a later, wider line grew the box over the earlier arrows (box.right moved right of where they were drawn) | Made directional arrows **inline children** of each box line (`wk-boxarrow` SVG in the flex row), so they ride with the text and stay on top of the box (§3.1.9/§3.1.10) | Never anchor free ink to the *edge* of a container that grows after you draw. Put per‑line adornments *inside* the line |
| 29 | STAGE handwriting **straight over the dimmed/blurred chart was hard to read** (blue biro on a busy, low‑contrast background) | Write STAGE lines into a **rounded note‑box filled with the site bg (`#f8f9fa`)** — clean "paper" under the pen (§3.1.10) | On a dimmed STAGE, give the writing its own opaque surface; only write directly on a chart when it's the light, undimmed DOCK |
| 30 | **Circles landed off the data line** — hardcoded `(vx,vy)` were tuned for a different range and drifted up into the "gradual decline" text | Read the point from the **rendered path** at runtime (`wkMainPath`/`wkMedianPts` via `getPointAtLength`) instead of hardcoding | Never hardcode a chart coordinate that depends on the selected range/data — anchor to the live geometry (§3.1.12) |
| 31 | **Handwriting clipped top & bottom** — the write‑on `clip-path:inset(0 …)` cut the cursive ascenders/descenders, and the ballpoint filter region was too short | Gave the clip vertical breathing room (`inset(-38% … -38% …)`), raised `line-height`, widened the filter `y`/`height`, shrank the font a touch | A `clip-path:inset()` reveal clips top/bottom at 0 by default — use negative top/bottom insets for any tall/looping font, and widen the `filter` region to match |
| 32 | **Stale ink floated over the page during the auto‑scroll** into the next scene ("gradual decline" + numbers stayed on‑screen scrolling into the asking chart) | `clearWkInk()` now fires at the **start of every scene entry** — `wkStage` / `wkTitleHighlight` (before its scroll) / `wkDock` | Ink is viewport‑fixed; clear it BEFORE you scroll, not after you arrive. Detected automatically by the QA harness `stale-ink` rule (§7) |
| 33 | **Mobile:** STAGE note‑box ran off the **left** edge; long DOCK notes bled off the **right**; "sellers adjusting" wrote over the caption | `.wk-notebox.mob` centred + width‑capped; `.wk-note` wraps on ≤640px; low concept lines raised via `markMobile` (§3.1.13) | Treat ≤640px as its own layout; a scaled desktop always collides. Screenshot mobile separately |
| 34 | Overlapping notes slipped through manual review | Runtime `avoidNoteOverlap` nudges a note off any note it hits; the **QA harness** (§7) screenshots every `note-overlap`/`over-caption`/`offscreen`/`note-on-circle`/`stale-ink` violation across desktop + mobile before deploy | Don't eyeball overlaps — lint them. Construct to avoid (a), auto‑nudge (b), and screenshot‑on‑violation (c) |
| 35 | The two‑point **arc looped back on itself** instead of connecting the circles | Reduced the bow to `min(46, dist*0.24)` — a gentle, capped arc | A bow larger than the chord (esp. a big `min()` floor) curls the arrow; keep the arc gentle and capped (§3.1.14) |
| 36 | **Withdrawn arrow pointed 2026→2025** (backwards vs the narration) | The circles were close but large‑radius, so the edge offsets crossed over; `wkArrowVB` now scales the offsets so start stays behind end | When circles are close relative to their radii, full edge offsets reverse the arrow — scale them (§3.1.14) |
| 37 | Lending **entrance ritual did nothing** — pills got no asterisk/blink | The explorer's pills live in `#subseg`/`#modeseg`/`#rangeseg`, NOT inside `#ac` (the chart) — scoped `wkSettingsStars` to those segs | The explorer's controls are outside its chart element; scope the ritual to the widget, not the svg (§3.1.1/item 7) |
| 38 | Lending **recent circles landed on the wrong line** ("20%" flew off left) | `wkMainPath` grabbed the longest (black price) path; targeted the **blue `#007bff`** new‑housing‑lending line instead | On a multi‑line chart, pick the path by **colour/role**, not by length (§3.1.12) |
| 39 | Captions ran **~1–5 s behind Will's voice** | Word‑timestamp transcription → `qa/sync_check.py` measured the drift and rewrote `WALK_SEGMENTS` to the actual spoken starts | Don't hand‑time captions — measure against the audio and correct systematically (§7 sync check) |

---

## 7. Verify & deploy (the gate — never skip)

**Local verification loop** (this is how every frame in this project was checked):

```bash
cd /home/fields/Feilds_Website/01_Website
PORT=5173 npm run dev &                     # react-router dev server
# headless screenshot at a chosen video time (puppeteer-core + system Chrome):
#   _shotwalk.cjs: goto ?walkthrough=1 → click .tour-hero-cta → seek #wkVid.currentTime → screenshot
node ./_shotwalk.cjs "http://localhost:5173/news/robina?walkthrough=1" out.png <seconds>
```
Read the PNGs (multimodal) at the key beats. Then **`npm run build`** must pass (the prod
strictness gate, §6.7).

**Automated layout QA — the error‑detection gate (`qa/walkthrough_qa.cjs`).** Eyeballing a few
frames misses overlaps, especially on mobile. The harness drives the walkthrough across **both
viewports** (desktop 1280 + mobile 390), seeks to ~55 audit timepoints that bracket every scene
transition and annotation, reads the geometry of every note / ink path / caption / chart, and
flags five violation classes — **`note-overlap`, `over-caption`, `offscreen`, `note-on-circle`,
`stale-ink`** — screenshotting each and writing `qa/out/qa_report.json` (exit 1 on any finding).
This is the three‑part contract Will asked for: **(a) construct so it can't happen** (clear‑before‑scroll,
`placeClear`, mobile layout), **(b) auto‑fix at runtime** (`avoidNoteOverlap`), **(c) surface with a
screenshot** when it still slips through. Run it against dev before deploying and again against the
live URL after:
```bash
cd 10_Market_Report/Video_Production/Video_Editing_Process/qa
NODE_PATH=/home/fields/Feilds_Website/01_Website/node_modules \
  node walkthrough_qa.cjs "http://localhost:5173/news/robina?walkthrough=1" --out ./out_dev
```
Read the screenshots it flags — some findings are legitimate (a note that *should* sit off the
charts), so the PNG is the arbiter, not the raw count. The count must not regress against the
prior run.

**Caption/voice sync check (`qa/sync_check.py` + `qa/transcribe_words.py`).** Captions come from the
hardcoded `WALK_SEGMENTS` timecodes; if those drift from Will's actual delivery the subtitles run
ahead of or behind his voice. The checker transcribes the clip with **word‑level timestamps**
(`transcribe_words.py` → faster‑whisper → `words.json`), then for each segment finds where its
opening words are *actually* spoken (search windowed to ±18 s of the declared time so it can't match a
later repeat of common words), reports the drift, and writes a **corrected `WALK_SEGMENTS`**
(`walk_segments_corrected.txt`, high‑confidence + monotonic only). Re‑run it whenever the clip or the
segments change. On the first pass it found a **systematic ~1 s lag (up to ~5 s on individual lines)**
and re‑synced 54 of 82 captions. The on‑chart ink beats are timed to the same video clock, so fixing
the captions to the voice also aligns them with the ink.

**Deploy** (website changes are gated — CLAUDE.md §2/§4; git push hangs → `gh api`):
```bash
# text file (engine/css): get sha, base64, PUT via JSON payload
SHA=$(gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' --jq '.sha')
python3 -c "import json,base64;json.dump({'message':'…','content':base64.b64encode(open('LOCAL','rb').read()).decode(),'sha':'$SHA'},open('/tmp/p.json','w'))"
gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' --method PUT --input /tmp/p.json
```
Then: wait for Netlify, **screenshot the LIVE page** at a couple of beats + the no‑flag
page (must be unchanged), confirm no console errors, and `website-deploy-tracker.py log`.

Files that change per walkthrough: `src/components/MarketFlowProto/MarketFlowProto.engine.ts`
(beats + `WALK_SRC`), `…/MarketFlowProto.css` (only if styling changes),
`public/walkthrough/<slug>.mp4` (the asset).

---

## 8. Known‑remaining / backlog

- **Roll §3.1 patterns out to charts 2–5** — Days‑on‑Market now has the full treatment
  (title highlight, timed numbers, horizontal concepts, drawn arrows, fade‑and‑replace).
  Median / Asking / Withdrawn / Lending still use the earlier, simpler treatment (both
  numbers at once, no title highlight, no fades). Bring them up to the same standard.
- **Mobile pass** — the whole thing is verified at desktop width; the dock/caption layout
  needs a real 390 px pass (head size, caption placement, chart legibility). Note the
  handwriting‑width and lane‑collision issues (#22–25) are worse at narrow widths.
- **Chapter density** — *addressed* on Days‑on‑Market via the tagged fade‑and‑replace
  (§3.1.2/3); apply the same wherever a chart would otherwise hold >2 concepts at once.
- **Explorer control interactions (Chapter G)** — the transcript narrates selecting
  "three‑suburb median / actual timings / all data / 3‑year view"; those UI controls are
  addressable (`#subseg`,`#modeseg`,`#rangeseg` buttons) but the walkthrough doesn't drive
  them yet.
- **Per‑suburb generalisation** — `WALK_SRC` and the anchor coords are Robina‑specific.
  To scale, make `WALK_SRC` derive from the suburb and store each suburb's anchor set.
- **Video hosting** — currently in the repo `public/`; move to GCS/CDN if repo size grows.

---

## 9. Appendix — quick reference

- **Colours:** red pen `#dc3545` (circles/arrows) · blue biro `#1c39b0` (handwriting).
- **Font:** "Fields Hand" (embedded woff2 data‑URI `@font-face` in `MarketFlowProto.css`).
- **Ballpoint look:** an SVG filter `#wkBallpoint` (fine `feTurbulence`+`feDisplacementMap` for an organic fibre edge, plus a faint dark‑blue `feColorMatrix`/`feComposite` mottle for ink‑density skip/pool) applied via `filter:url(#wkBallpoint)` on `.wk-note`; halo softened from a hard white outline to a subtle paper glow + faint ink‑depth shadow, ink `#1b3aa0`. This is what makes the handwriting read as BIC biro rather than a flat font.
- **Write‑on:** `@keyframes wkWrite` clip‑path reveal, `.wk-note.show` 1.35 s / `.big` 1.7 s;
  `.noanim` for instant (seek) paths; reduced‑motion disables it.
- **Overlay ids:** `#walkLayer`, `.wk-dim`, `#wkInk`, `#wkAvatar`/`#wkVid`, `#wkCap`/`#wkChip`,
  `#wkTransport`.
- **Flag:** `?walkthrough=1` (`walkFlagOn()`), hero injected on the overview panel only.
- **Verify tooling:** `react-router dev` (:5173) + `puppeteer-core` + `/usr/bin/google-chrome`.
- **Live example:** `https://fieldsestate.com.au/news/robina?walkthrough=1`.
- **Storyboard/source notes:** `10_Market_Report/issues/Video/August_2026/` (transcript,
  storyboard, POC artifacts).
- **Memory pointer:** the `news_split_prototype_spec` memory carries the running technical
  detail and per‑round change log.
