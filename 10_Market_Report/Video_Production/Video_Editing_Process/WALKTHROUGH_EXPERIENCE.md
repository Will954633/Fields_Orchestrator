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
     intro, the interpretive bridges, and the close (talking *to* the viewer).
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
   2. **put a small blue‑pen asterisk (`*`) beside each of the chart's settings/controls**
      (e.g. Overlay / Window / Range for Days‑on‑Market; Price‑series / View / Range /
      Indicators for the explorer) — it flags that the chart is interactive and adjustable;
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
5. **A label and its value are one unit.** When a written label pairs with a value
   ("days on market" + "50 days"), **place the value relative to the label's rendered
   rect** (`label.getBoundingClientRect().right + gap`), never by independent coordinates —
   otherwise they drift or collide. Anchor the *pair* far enough from the right edge that
   the whole thing fits (see issue #26).
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
| `wkFreeNote(text,fx,fy,instant,big)` | Blue note at a viewport fraction — for STAGE concept lines (bridge, close recap) |
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
35   ▶ "days on market"                     (0:35 "known as its days on market")
42.5 red circle + arrow on the spike        (0:42 "shot up")
48   "≈25"                                   (0:48 "about 25 days in June")
51   "50 days"                               (0:51 "up to 50 days in August")
84   ▶ "more days = weaker demand"           (1:24 demand relationship)
110  ▶ "a symptom, not a predictor"          (1:54 the key reframe)
120  STAGE (bridge)
127  ▶ "prices move gradually"               (2:00)
134  ▶ "valued on the last 6 months"         (2:08)
156  DOCK Median
164  ▶ "gradual decline"                     (2:43)
170  circle peak + "$1.5M"                   (2:52 "1.5 million")
175  circle latest + "$1.49M"                (2:55 "1.492")
186  DOCK Asking (median overlay on, 10yr)
198  ▶ "asking price" / "median sale"        (3:20 line labels)
236  circle flip + "Dec 2023"                (3:56)
250  circle converge + "Sept 2026"           (4:11)
264  ▶ "sellers adjusting"                   (4:32)
285  DOCK Withdrawn
300  ▶ "homes that didn't sell"              (4:56)
326  circle 2025 + "23"                      (5:26)
334  circle 2026 + "53"                      (5:40)
350  ▶ "trend has changed"                   (5:48)
368  STAGE (need a leading signal)
380  ▶ "a signal that moves BEFORE prices"   (6:19)
402  DOCK Lending (#ac)
419  ▶ "leads prices by ~12 months"          (6:55)  [big]
412  ▶ "used by CBA + RBA"                   (6:48)
513  circle Q4-25 + "20%"                    (8:40)
520  circle Q2-26 + "10%"                    (8:43)
548  ▶ "directional, not certain"            (9:07)
583  STAGE (close)
591  ▶ "1. days on market: up"               (9:49 recap builds)
599  ▶ "2. homes withdrawn: up"
607  ▶ "3. new-house lending: down"
622  ▶ "so: flat to declining"               (10:12)
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
