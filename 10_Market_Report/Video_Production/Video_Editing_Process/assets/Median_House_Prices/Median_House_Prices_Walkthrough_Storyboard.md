# Median House Prices — "what the number hides" · Talking‑Head Walkthrough Storyboard

**Source video:** `median-house-prices_2026-09.mp4` (512² web cut, **15:23 / 922.8s**, QC fails: 0)
**Assets:** `10_Market_Report/Video_Production/Video_Editing_Process/assets/Median_House_Prices/`
**Overlays page:** [https://fieldsestate.com.au/articles/comparing-median-house-prices](https://fieldsestate.com.au/articles/comparing-median-house-prices) — article *"Why you should be careful comparing median house prices"* (route renders **`ArticlePage`**, self‑hosted article HTML from `system_monitor.content_articles`, slug `comparing-median-house-prices`).
**Transcript:** verbatim, timecoded — §5 (also `..._walk_segments.txt`, 128 segments).
**Status:** STORYBOARD / planning. Not yet built. This is the document to sign off before engine work.

---

## 0. ⚠ How this differs from the market‑overview walkthroughs (read first)

The three suburb walkthroughs (`/news/:suburb`, `MarketFlowProto`) overlay a **live imperatively‑drawn SVG** panel — the engine reads chart geometry (`wkMedianPts`, the blue lending line, etc.) so circles snap to data. **This article is a different animal, three ways:**

1. **Different page / mount.** It's `ArticlePage`, not `NewsSplitPage`/`MarketFlowProto`. The walkthrough runtime (viewport‑fixed overlay: `#walkLayer` = dim + `#wkInkWrap` + `#wkAvatar/#wkVid` + `#wkCap` + transport) has to be ported to mount over the article. The ink/beat/camera machinery is reusable as‑is; the *host* and the *anchors* are new.
2. **The charts are NOT live SVG.** They're **blob‑hosted assets** embedded in the article:
   - **Trap 1** — a **static PNG** (`median_robina_bedroom_index.png`, Robina attached, indexed to 100).
   - **Trap 3** — an **interactive `<iframe>`** (`median_robina_rolling_ci.html`) + PNG fallback.
   - **Trap 4** — an **interactive `<iframe>`** (`median_bw_asking_sqm.html`) + PNG fallback.
   We **cannot read SVG path geometry** for these. Ink must be anchored by **position over the element's bounding box** (fractions of the img/iframe rect), authored per‑beat and verified visually — closer to the *early* Robina beats (hard‑coded viewBox coords) than the geometry‑reading ones. Cross‑origin iframes also can't be introspected or driven, so any "switch the pills" action must either (a) be narrated‑only with ink drawn over the iframe, or (b) require us to add a `postMessage` hook to the blob charts. **Decision needed — see §6.**
3. **Two whole sections have NOTHING on the page to point at.** The **intro math** (how a median is calculated; median‑vs‑average with the $12M outlier) and **Trap 2** (different‑city mixes) are **text‑only** in the article. These become **STAGE sequences where Will hand‑draws the worked examples** on the dimmed overlay — number rows, circled middle value, the outlier, the ratio diagrams. This is the biggest new authoring surface and the most fun part; see §3.1 and beats **A/B** and **G/H**.

---

## 1. The feel (unchanged from the suburb walkthroughs)

Will appears as a **circular talking head on top of the real article page** and teaches it like he's sitting beside you with the article printed on the table, **drawing on it with a pen** — circling, arrowing, scribbling numbers in the margin — as he speaks. The page underneath is the real live article: when he says "scroll down to this chart", the page scrolls to it.

> **The one rule:** the viewer always sees the thing being spoken about **and** Will at the same time, and Will never covers it.

Because this is an **educational explainer**, not a market update, the balance tips **more toward STAGE** than the suburb walkthroughs — a lot of it is Will teaching a concept and drawing an example, not pointing at a live number. Roughly: **~55% STAGE (teach + hand‑draw), ~45% DOCK (three real charts).**

---

## 2. Head states (reuse `MarketFlowProto` `wkStage`/`wkDock`)

| State | When | Notes |
|---|---|---|
| **STAGE** — big, centred, page dimmed | intro, the math examples, Trap 2, every "trick number N" takeaway, the close | The default here. Ink is drawn on the dimmed stage (the "whiteboard"), not on a chart. |
| **DOCK** — small (~150px desktop / ~96px mobile), pinned to the chart corner furthest from the ink | Trap 1 PNG, Trap 3 iframe, Trap 4 iframe | Dock to the corner opposite the inked region; short arrow bridges head→point. |
| **HALF** — medium, chart still whole | the "what does this chart *mean*" beat between naming a number and interpreting it | e.g. Trap 3 "noise vs signal". |

Docking side is per‑beat (opposite the ink). Mobile: ink in upper ~55%, head pinned bottom, chart auto‑scrolled so the annotated region clears the head.

---

## 3. Ink vocabulary (reuse + one new family)

Reused from the suburb engine (all hand‑drawn, ballpoint filter, write‑on): `circle`, `arrow(Will→point)`, `trace(lineSegment)`, `bracket(xRange)`, `value("…")` big callout (blue biro `#1c39b0`), `note("…")` margin scribble, `wkDirArrow` (↑/↓/→ for a moving quantity), `wkStageBox`/`wkBoxNote` (STAGE note‑box), the chart **camera** `wkCamera` (viewBox‑animation zoom — works as of 2026‑09‑09).

### 3.1 NEW: the "worked‑example on the whiteboard" family (STAGE)

The intro math and Trap‑1 example need Will to **lay out a row of numbers and manipulate it** on the STAGE. Proposed primitives (to build):

- **`numRow([…], opts)`** — draw a horizontal row of sale prices left→dearest→right, hand‑written, appearing left‑to‑right as spoken. Supports a **highlight** on the middle element(s) and an **insert/remove** animation for the outlier.
- **`bracePair(iLeft, iRight, label)`** — an under‑brace joining the two middle numbers with a label ("÷2 = 1.49M").
- **`swapCount(label)`** — the little "9 × 2‑bed · 3 × 3‑bed · 1 × 4‑bed" tallies under a row, re‑drawn for the 2024 vs 2026 comparison.
- **`ratioGlyph(a:b, labels)`** — a simple two‑block bar (or split circle) for the mix ratios in Trap 2 (Melbourne units×2; Robina 1:1; Burleigh 2:1).

These render on the dim stage (a faint "paper" panel), same Fields‑Hand blue ink + write‑on. They are the visual spine of the two text‑only sections.

---

## 4. Beat‑by‑beat sequence

Times are **video seconds** (M:SS) from the transcript. `→` = page action. Anchors named against the article skeleton (§7). **STAGE unless a DOCK/HALF is stated.**

### INTRO + MATH — *STAGE, hand‑drawn on the whiteboard* (0:00 – 2:16) · article section H2 "First, what a median actually is" (text‑only)

- **A1 · 0:00** — STAGE, centred, page at top. Personal hook: *"I really wanted to do a video on median house prices… easily presented in a way that's misleading."* No ink.
- **A2 · 0:16** — STAGE. `wkBoxNote` title card forming: **"4 traps"** (foreshadow). *"…how it's calculated and four different traps."*
- **A3 · 0:25 → 0:36** — STAGE. **`numRow([…8 sales…])`** draws on; when he says *"the median is simply the middle number"*, **highlight the two middle values (1.48M & 1.55M)**. `bracePair` under them.
- **A4 · 0:43** — STAGE. Write **`= 1.49M`** (÷2). *"add those two up, divide by two."*
- **A5 · 0:50 → 1:16** — STAGE. **Insert a `$12M` outlier** into the row (animate it sliding to the far right); median stays ≈ **1.49M**; then **remove it** → **1.48M**. `value("median barely moves: 1.49 → 1.48 (−$10k)")`. This is the whole point of "median resists outliers" — let it land.
- **A6 · 1:30 → 2:11** — STAGE. Switch the SAME row to **average**: with $12M in → **2.75M**; pull it out → **1.43M**. `value("average lurches: 2.75 → 1.43")` beside it, next to the median's tiny move. Contrast is the payoff → *"that's why median is the good measure for property."*
- **A7 · 2:16** — STAGE. *"Math out of the way — the core issue: four ways we get tricked."* Re‑show the **"4 traps"** card, then → **scroll to Trap 1**.

### TRAP 1 — the mix changes (2:25 – 5:43) · H2 "Trap 1" + **PNG chart** `median_robina_bedroom_index.png`

- **B1 · 2:28** — STAGE→announce *"Trap 1: the mix of homes that sells changes, and the median moves with it."* → scroll so the Trap‑1 chart is in view.
- **B2 · 2:35** — **DOCK** to the PNG (dock bottom‑left; lines rise to the right). `note("Robina · attached dwellings · indexed to 100 (Jun 2024)")`. Establish it's units/duplexes, 2‑bed / 3‑bed / all‑attached.
- **B3 · 2:56 → 3:16** — **DOCK**, hold. `circle(all‑attached line where it sits ABOVE both others)` + `note("all‑attached > BOTH 2‑bed & 3‑bed — how?")`. The paradox is the hook.
- **B4 · 3:16 → 3:44** — **HALF**. Answer: *"the mix changed — in 2026 far more large, expensive properties sold."* `note("not prices rising — the MIX rising")`.
- **B5 · 3:44 → 5:11** — **STAGE** (leave the chart; the article has **no table** for this — Will draws it). Worked example on the whiteboard:
  - **2024 row:** `numRow(13 sales)` + `swapCount("9×2‑bed · 3×3‑bed · 1×4‑bed")`; highlight the **7th (middle) = 2‑bed \$860k** → `value("2024 median = $860k")`.
  - **2026 row:** re‑draw, `swapCount("5×2‑bed · 8× 3‑bed+")`; highlight middle **= 3‑bed \$1.118M** → `value("2026 median = $1.118M")`.
  - `value("+30%")` bridging them, with `note("…but 2‑bed only +18%, 3‑bed only +25% — the MIX did the rest")`.
- **B6 · 5:27** — STAGE takeaway card: **`Trick 1 — break the median down: attached vs detached, then by bedrooms.`**

### TRAP 2 — different cities have different mixes (5:43 – 7:31) · H2 "Trap 2" (text‑only → STAGE)

- **C1 · 5:43** — STAGE announce *"Trap 2: different cities have different mixes."* → scroll to the Trap‑2 heading (keeps the reader oriented even though it's prose).
- **C2 · 6:00 → 6:26** — STAGE. `ratioGlyph` **Melbourne ≈ 2× the units of other capitals**; `note("all‑dwellings median: Melbourne vs Sydney/Brisbane isn't like‑for‑like — Melbourne has ~2× the units, and units are cheaper")`.
- **C3 · 6:34 → 6:50** — STAGE. Bring it local: `ratioGlyph` **Robina ≈ 1:1 houses:units**, **Burleigh Waters ≈ 2:1 houses:units**. 
- **C4 · 6:50 → 7:06** — STAGE. `note("comparing all‑dwellings Robina vs Burleigh says as much about what's BUILT there as what homes are worth")`.
- **C5 · 7:06** — STAGE takeaway → same trick as 1 (split by type + bedrooms) **but** `note("careful: drill down too far → sample gets tiny → unreliable")` — deliberately bridges into Trap 3.

### TRAP 3 — the sample is often too small (7:31 – 12:03) · H2 "Trap 3" + **iframe** `median_robina_rolling_ci.html` (+PNG)

- **D1 · 7:31** — STAGE announce *"Trap 3: sample sizes too small can be unreliable."*
- **D2 · 7:36** — STAGE/HALF. `note("hear a median → ask: how many sales is it built on? it should be disclosed.")`
- **D3 · 7:47 → 8:05** — → scroll to the chart. **DOCK** (bottom‑right; action is across the whole line). `trace(green 12‑month rolling line)` + `note("smooth · 12‑month rolling · Q1‑25 → Q2‑26")`.
- **D4 · 8:05 → 8:33** — **DOCK**, hold. *"layer in the rolling 3‑month median"* → the copper single‑quarter dots. `trace/scatter(copper dots)` + `note("3‑month = erratic — short windows look dramatic")`. ⚠ If we can drive the iframe, actually toggle its pill here; otherwise ink over it (see §6).
- **D5 · 8:33 → 8:55** — **DOCK**, use the **camera** to zoom the recent quarters. `circle(March‑26 dot ≈ $1.56M)` → `arrow` → `circle(June‑26 dot ≈ $1.4M)`; `value("$1.56M → $1.4M in ONE quarter")` + `note("72 sales, then 55")`.
- **D6 · 8:55 → 9:26** — **DOCK**. `circle(12‑mo line same window: $1.5M → $1.492M)` + `value("274 samples vs 71")` + `note("big sample → gentle move; small sample → wild move")`. `wkCameraOff`.
- **D7 · 9:26 → 10:29** — **STAGE/HALF** (interpretive). *"Sept 2026: the 12‑mo still holds last year's boom + only a few decline months; the 3‑mo has caught the whole decline."* `note("noise… or signal?")`.
- **D8 · 10:47 → 11:17** — STAGE. **Callback to the market‑overview walkthrough:** `wkBoxNote` list — **days on market ↑ · homes withdrawn ↑ · new‑house lending ↓** — *"combine the 3‑mo median with unrelated datasets; if they all point the same way, the noise might be signal."* (Each line with `wkDirArrow`.)
- **D9 · 11:43** — STAGE takeaway: **`Trick 3 — always ask the sample size. Want 100–200+; longer windows are steadier. Single suburbs on a 3‑mo median swing a lot.`**

### TRAP 4 — asking vs sold prices (12:03 – 14:54) · H2 "Trap 4" + **iframe** `median_bw_asking_sqm.html` (+PNG)

- **E1 · 12:03** — STAGE announce *"Trap 4, the last one: asking prices are different to sale prices."*
- **E2 · 12:13 → 12:40** — STAGE. `note("asking‑price data: SQM Research — a monthly per‑suburb figure")`. ⚠ **Verify spelling "SQM Research"** (transcript renders "QSM"). Naming David Koch / Ross Greenwood as users is Will's colour — keep, but flag to Will (§6).
- **E3 · 12:40 → 13:08** — → scroll to final chart. **DOCK** (bottom‑left). Label the two lines: `note("copper = ASKING (what vendors list at)", at=copperLine)` + `note("green = SOLD median (what actually sells)", at=greenLine)`.
- **E4 · 13:08 → 13:22** — **DOCK/trace**. `trace(copperLine)` — *"asking is more volatile, shoots up and down; the two move on different trajectories."*
- **E5 · 13:22 → 14:00** — **DOCK**, camera on the two gap periods. `bracket(2022) + note("market correction — big persistent gap")`; `bracket(Dec 2025 peak) + circle(spike) + note("peak — asking way out of sync")`. `value("biggest gaps = corrections & peaks")`.
- **E6 · 14:08 → 14:39** — **STAGE** (the payoff). *"Ask what you actually want from a median. If it's your home's value — asking price is misleading."* `note("want your home's worth? use SOLD, not ASKING")`.
- **E7 · 14:39** — STAGE takeaway: **`Trick 4 — median SALE, not median LISTING. And still: mind the sample size.`**

### CLOSE — "How to read a median" (14:54 – 15:22) · final H2

- **F1 · 14:54** — → scroll to "How to read a median". **STAGE**, page calm. Recap the four traps as a checklist card:
  `1 break down by type + bedrooms · 2 same mix when you compare · 3 mind the sample size (12‑mo > 3‑mo) · 4 sold, not asking.`
  Land on *"…make sure your sample sizes are large enough to have real underlying meaning."* Fade to the article.

---

## 5. Verbatim transcript (timecoded)

Full verbatim is in **`median-house-prices_2026-09_walk_segments.txt`** (128 segments, `[t,"text"]`) and `..._transcript.md`. Section anchors (video seconds):

| Section | starts | key figures spoken |
|---|---|---|
| Intro + how it's calculated | 0:00 (0.30) | 8 sales; middle 1.48 & 1.55 → **1.49M** |
| Median vs average (outlier) | 0:50 (50.02) | median 1.49→1.48 (−$10k); average 2.75→1.43 |
| Trap 1 · mix changes | 2:28 (148.28) | all‑attached > 2‑bed & 3‑bed; 2024 $860k → 2026 $1.118M (**+30%**); 2‑bed +18%, 3‑bed +25% |
| Trap 2 · city/suburb mixes | 5:43 (343.04) | Melbourne ~2× units; Robina ~1:1; Burleigh ~2:1 houses |
| Trap 3 · sample size | 7:31 (451.64) | Mar‑26 $1.56M (72 sales) → Jun‑26 $1.4M (55); 12‑mo $1.5M→$1.492M (274 vs 71) |
| Trap 4 · asking vs sold | 12:03 (723.66) | SQM asking; BW houses; gaps at 2022 correction & Dec‑2025 peak |
| Close · how to read a median | 14:54 (894.38) | 12‑mo best; 3‑mo cautious; like‑for‑like; sample size |

---

## 6. Open questions / decisions for Will before we build

1. **The two big STAGE‑drawn examples (intro math + Trap‑1 13‑sale table).** The article has no table/graphic for these; the plan is for Will to hand‑draw them on the dim stage (§3.1). Happy with that, or do you want those small graphics **added to the article** (so they're there without the video too)? *(Recommendation: hand‑draw them — it's the strongest teaching moment and keeps the article clean.)*
2. **Driving the interactive iframes (Trap 3 & 4).** They're cross‑origin blob HTML, so the walkthrough can't click their pills or read their geometry. Options: (a) narrate the pill switch and just draw ink over the iframe at authored positions; (b) add a tiny `postMessage` API to the two blob charts so the walkthrough can flip 12‑mo↔3‑mo and highlight a point. *(Recommendation: (a) for v1 — simplest, robust; upgrade to (b) only if the pill‑switch really needs to be live.)*
3. **Anchoring ink over a PNG / iframe by position.** No geometry to read, so circles are placed by fraction‑of‑box and verified by eye per beat (like the early Robina beats). Fine? *(It means a bit more manual tuning + headless verification per beat.)*
4. **Naming SQM Research + David Koch / Ross Greenwood** (Trap 4). Factual data‑source citation — keep as spoken, or soften to "a widely‑used asking‑price data source"? Confirm spelling is **SQM Research**.
5. **Length.** 15:23 is long for an overlay. Ship as one, or offer chapter skips (the transport already supports `⏮/⏭` chapters — I'd set marks at the 4 traps + close)?

---

## 7. Article anchors (confirmed against stored HTML, slug `comparing-median-house-prices`)

Order on the page (for scroll targets):

| # | element | anchor / src |
|---|---|---|
| 0 | H2 **First, what a median actually is** | text only |
| 1 | H2 **Trap 1: the mix changes** | text |
| 2 | **IMG** Robina attached bedroom‑index | `…/median_robina_bedroom_index.png` |
| 3 | H2 **Trap 2: "dwellings" and "houses" are different questions** | text only |
| 4 | H2 **Trap 3: the sample is often too small** | text |
| 5 | **IFRAME** rolling CI (12‑mo vs 3‑mo) | `…/median_robina_rolling_ci.html` (+ PNG fallback) |
| 6 | H2 **Trap 4: asking vs sold** | text |
| 7 | **IFRAME** BW asking vs SQM | `…/median_bw_asking_sqm.html` (+ PNG fallback) |
| 8 | H2 **How to read a median** | text (close) |

**Engineering note (for later, not this doc):** porting the `#walkLayer` runtime to `ArticlePage` + a versioned/gated flag (`?walkthrough=1`) mirrors the `MarketFlowProto` setup; the reusable pieces are the overlay layer, `wkStage/wkDock`, ink primitives, the `wkCamera` viewBox zoom, captions/beat clock. The **new** work is: the STAGE worked‑example primitives (§3.1), position‑anchored ink over img/iframe, optional iframe `postMessage`, and scroll‑to‑anchor against article DOM instead of chart hosts.
