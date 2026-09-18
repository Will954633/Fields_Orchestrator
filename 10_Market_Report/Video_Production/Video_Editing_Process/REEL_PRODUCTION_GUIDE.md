# Reel Production Guide — Fields Market-Update Reels (9:16)

**This is the canonical spec for how we make market-update reels going forward.**
Adopted 2026-09-18 after Will approved the two scene formats below. Any market-update
reel (crash-risk, monthly update, single-metric explainer) is built by chaining these
two scene types.

> **Three copies of this file exist and must be kept in sync:**
> - `03_Facebook/Reels/REEL_PRODUCTION_GUIDE.md` (where reels get published from)
> - `10_Market_Report/REEL_PRODUCTION_GUIDE.md` (market-content home)
> - `10_Market_Report/Video_Production/Video_Editing_Process/REEL_PRODUCTION_GUIDE.md` (next to the code — **edit this one, then copy out**)
>
> **The code lives in one place:**
> `10_Market_Report/Video_Production/Video_Editing_Process/reel_pipeline/`

---

## 1. The two approved formats

All beats are **1080×1920 (9:16)**, dark-theme graphics, copper accent (`#DB7A4A`), Fields voice.
A reel is a sequence of **three** beat types: **text**, **chart**, and **stat** (§3).

**Worked examples (copy these specs):**
- `reel_pipeline/reel.example.json` — Sep-2026 "crash risk" (text + chart). Indoor, plain wall.
- `reel_pipeline/reel.auctions.json` — Sep-2026 "auctions not working" (text ×4 + `clearance`
  chart + `stat`). **Outdoor/lakeside shoot → text beats use `theme: "dark"`.** Output:
  `Auctions_Not_Working_REEL_9x16_Sep2026.mp4`.

### Text beat — full-frame presenter, headline to his left
Approved reference: **`GC_Crash_Risk_DEMO_text-only_REEL_9x16_Sep2026.mp4`**
→ https://drive.google.com/file/d/1cITbXVfhw1hJMWlZuc-MLKRJQRS_iBw2/view

- Presenter shown **full frame**, right-of-centre (a portrait window cropped from the
  landscape clip), wall on his left.
- Headline reveals **word-by-word** over the wall, on the left. Accent word in copper.
- Small copper kicker above ("Gold Coast · Market Watch").
- Dark text on the light wall + a soft light scrim for legibility.
- **Use for:** the hook, transitions, statements, "two angles" setups — anything spoken
  without a chart.

### Chart beat — full-bleed chart, presenter in a PIP
Approved reference: **`GC_Crash_Risk_DEMO_chart-beat_REEL_9x16_Sep2026.mp4`**
→ https://drive.google.com/file/d/1FvDCok5hOQYrWCN1vM6Gitb4NiTzNpt4/view

- The **chart is the full-bleed dark backdrop** (fills the frame). Headline + chips +
  a copper stat pill sit **top-left**. Line animates on; annotation points circle in as
  they're named; the pill reveals last.
- The presenter is a **rounded-corner PIP** floating in the **clean bottom-right** space
  under the rising line (never covers the data). Legend + source bottom-left.
- **Use for:** any data point — days on market, median price, lending, clearance, etc.

> **Why a wide chart in a tall frame works this way:** a time-series line can't literally
> fill a 9:16 frame. The honest translation is: chart = full-bleed background, line lives
> in a mid-band, text and presenter float on top. Don't try to stretch the plot to the
> full height.

### Safe area (all reels)
Instagram/TikTok/FB overlay their own UI over the **bottom ~20% and right edge**. Keep
faces, headlines, and all chart data out of that zone. Both formats already do (in the
chart beat the PIP's lower third and the source line sit in the sacrificial zone — fine).

---

## 2. The pipeline (one command builds a whole reel)

Location: **`Video_Editing_Process/reel_pipeline/`**

```
reel_pipeline/
├── build_reel.py            ← THE DRIVER. reel.json → finished reel.
├── reel_render.js           ← renders a panel to a 1080×1920 frame sequence (Chrome)
├── reel.example.json        ← the Sep-2026 crash-risk reel, as a spec (copy this)
├── panels/
│   ├── text_reel.html       ← text-beat panel (window.__build(scene) + __setT(t))
│   ├── chart_reel.html      ← chart-beat panel (supports chart kinds: dom, median)
│   └── chart_data.js        ← the numbers (window.CHART_DATA). Regenerate to refresh.
├── work/<slug>/             ← per-scene intermediates (auto-cleaned unless --keep)
└── out/<slug>_reel.mp4      ← the finished reel
```

**Architecture:** every scene is authored as JSON. `build_reel.py` renders each scene's
graphics to PNG frames (via headless Chrome driving `window.__setT(t)`, so animation is a
pure function of time and fully deterministic), composites the presenter from the source
clip — a **portrait crop** for text beats, a **rounded PIP** for chart beats — pulling
that scene's **audio span** so the voice stays in sync, then concatenates the scenes.

### Quick start

```bash
cd /home/fields/Fields_Orchestrator/10_Market_Report/Video_Production/Video_Editing_Process/reel_pipeline
source /home/fields/venv/bin/activate

# 1. copy the example spec and edit it for your reel (see §3)
cp reel.example.json reel.mine.json

# 2. build the whole reel
python3 build_reel.py reel.mine.json
#   → out/<slug>_reel.mp4

# fast iteration: build ONE scene while you tune it
python3 build_reel.py reel.mine.json --only 1 --keep
#   → work/<slug>/scene_01.mp4   (and keeps the PNG frames for inspection)
```

Then **watch it and read a few frames** (multimodal QC — CLAUDE.md §4/§5): check the join
at each cut, that captions/numbers match the audio, and that nothing important is under
the safe-area zone.

---

## 3. Authoring a reel (`reel.json`)

```jsonc
{
  "slug": "gc_crash_risk_2026-09",         // names the output + work dir
  "source": "../assets/Market_Updates/Sep_2026/DJI_...MP4",  // the talking-head clip (rel to the json)
  "fps": 25,
  "scenes": [ /* ordered beats */ ]
}
```

### A text beat
```jsonc
{
  "type": "text",
  "ss": 0.0,            // start second IN THE SOURCE CLIP for this beat's audio
  "dur": 6.0,           // beat length (seconds)
  "theme": "dark",      // OPTIONAL: "dark" = dark scrim + light text (bright/outdoor shoots);
                        //           omit for the default light scrim + dark text (plain wall)
  "cropx": 820,         // x of the 608px-wide portrait window (tune presenter framing, see §5)
  "kicker": "Gold Coast · Market Watch",
  "words": [["Is",0.24],["the",0.70], ... ],   // [word, appear_second] — see §4
  "breaks_after": [1,3,5,7],                    // insert a line break after these word indexes
  "accent_index": 8                             // this word renders in copper (omit for none)
}
```
> **On-screen text is DISTILLED, not verbatim.** For a long spoken sentence, author a short
> 3–7 word headline that captures the beat (e.g. VO "what's the best sale method given these
> softer conditions" → on-screen "Auction or private treaty?"). The VO carries the detail; the
> headline is a title. Reveal times for a distilled headline just need to feel good — space them
> across the beat; they need not match VO word times (only verbatim headlines do).
> **`theme: "dark"`** is essential for outdoor/bright shoots — dark text won't read over sky/water.

### A chart beat
```jsonc
{
  "type": "chart",
  "ss": 24.3, "dur": 13.2,
  "kicker": "Angle 1 · Days on market",
  "headline": "How long are homes taking to sell?",
  "chips": [["Houses","g"],["Rolling 3-mo",""],["3-year range",""]],  // ["label","g|b|"] (g=green,b=blue)
  "chart": "dom",                                // chart kind — see §6
  "annotations": [                               // circle these data points as they're named
    {"key": "2026-04", "label": "27d · Apr"},    // key matches the data's m (dom) or q (median)
    {"key": "2026-08", "label": "40d · Aug"}
  ],
  "pill": ["<b>27d</b> Apr", "→", "<b>40d</b> Aug"],  // copper stat pill; <b> = the big number
  "anim": {"drawon": 2.0, "pops": [6.6, 8.7], "pill": 9.2},  // seconds (beat-local) — see §4
  "source": "Source <b>Fields Estate</b> · fieldsestate.com.au",
  "pip": {"x":572,"y":1372,"w":440,"h":516,"cropw":850,"croph":996,"cropx":815,"cropy":44}  // optional, see §5
}
```
`pip` is optional — omit it to use the default bottom-right box.

### A stat beat  (big animated number — for a single/comparison figure)
Same full-bleed dark canvas + presenter PIP as the chart beat, but shows a headline stat
instead of a chart. Use it when the data point is one striking figure, not a series
(e.g. "over 1% less", "clearance halved").
```jsonc
{
  "type": "stat",
  "ss": 23.5, "dur": 13.8,
  "kicker": "New Research · University of NSW",
  "headline": "What happens after a failed auction?",
  "stat": {
    "pre":  "Homes that fail to sell at auction go on to sell for",  // small eyebrow line
    "big":  "over <b>1%</b> less",                                    // the hero — <b> = huge copper
    "post": "than if they had listed as private treaty first"        // sub-line
  },
  "anim": {"pre": 2.0, "big": 9.2, "post": 10.6},   // seconds (beat-local) each element appears
  "source": "Source <b>UNSW</b> research",
  "pip": { /* same shape as the chart beat; optional */ }
}
```
> Keep `source` short — it sits bottom-left and the PIP occupies the bottom-right, so anything
> past ~500px is hidden behind the box. Same applies to the chart beat's `source`.

---

## 4. Timing — cut the video to the graphics

Animation seconds are **beat-local** (0 = start of that beat). You author them to line up
with what the presenter says.

1. **Transcribe with word timestamps** (faster-whisper `base.en`, `word_timestamps=True`)
   — the existing `scripts/01_transcribe.py` in this folder does this, or run whisper
   directly on the clip. You get every word with a start time.
2. **Text beat:** `words` = `[word, start_second]` straight from the transcript for that
   sentence (subtract the beat's `ss` so it's beat-local). The word appears as he says it.
3. **Chart beat:** set `anim.pops[i]` to the second (beat-local) he *names* annotation `i`
   ("...in **April** it was 27 days" → the April ring pops then). `anim.drawon` is how long
   the line takes to draw (≈2s). `anim.pill` = when the summary pill flies in.
4. `ss`/`dur` define which slice of the clip (and its audio) the beat uses. Author cuts at
   sentence granularity; leave ~0.15s of breath at the ends.

---

## 5. Shooting the clip (so the crops land)

The presenter comes from **one continuous landscape talking-head clip** (DJI, 1920×1080,
25fps). Both beat types crop from it, so frame it once, correctly:

- **Orientation:** landscape 1080p (or 4K → it's downscaled). 25fps.
- **Position:** stand **centred, slightly right of centre**, with **clear wall to your left
  (screen-left)** — that wall is where the text goes in the text beat. A plain, evenly-lit
  wall keys best.
- **Headroom:** leave space above the head; the text-beat window is full-height portrait.
- **Eyeline:** to the lens (the Sep practice take reads off-phone, looking down — avoid).
- **Audio:** lav mic; the pipeline denoises/normalises at export if you route through the
  main `03_build.py`, but the reel driver currently takes the clip's audio as-is.

**Tuning to a new clip (numbers in `reel.json`):**
- Text beat: `cropx` slides the 608px portrait window left/right (lower = more wall/less of
  him). Default 820 for a presenter centred at ~x1240.
- Chart beat `pip`: `cropw/croph/cropx/cropy` frame the presenter inside the box; `x/y/w/h`
  place/size the box. Keep the box in the clean bottom-right, clear of the last data point.

---

## 6. Chart kinds & data

`chart_reel.html` builds charts as **custom SVG from `panels/chart_data.js`**
(`window.CHART_DATA`). Supported `chart` values today:

| kind | data key | series | notes |
|------|----------|--------|-------|
| `dom` | `CHART_DATA.dom` (monthly `{m,v}`) + `CHART_DATA.seasonal` | blue line + gold dotted historical | days-on-market |
| `median` | `CHART_DATA.median` (quarterly `{q,v}`) | green line + end dot | median house price |
| `clearance` | `CHART_DATA.clearance` (monthly `{m,v}`, value = %) | copper line | auction clearance %. Built from `public/data/auction_clearance.json` (SQM, capitals — GC has no auction series; use Brisbane as nearest capital and say so). |

**Add a new kind** by adding one config block to the `CFG` map in `chart_reel.html`
(lo/hi, gridlines, colour, x-label formatter, legend). No other file changes.

**Refresh the numbers:** `chart_data.js` was extracted from the live site
(`/data/gc_overview.json`, `/data/gc_dom_by_type.json` on `fieldsestate.com.au/news/gold-coast`).
Update the JSON in `chart_data.js` (or regenerate from those endpoints) before a new reel so
the figures are current. **Verify every figure against the audio** (CLAUDE.md §5 — exact
numbers, no rounding).

---

## 7. Deploy & archive

- **Publish:** finished reels are square/vertical social assets — post via the Facebook/
  Instagram tooling in `03_Facebook/` (organic) or as a Reel ad. Reels can only be made as
  dark posts via API then consolidated — see memory `fb_reel_publish_and_post_id_consolidation`.
- **Editorial rules still apply** (CLAUDE.md §5): no advice, no predictions, no single
  valuation figure in a headline, cite the source, exact numbers.
- **Archive off the root disk once shipped** (CLAUDE.md / RUNBOOK §7): the root disk is
  shared with the production DB. Move the source clip + `out/` reel to
  `/data/blobs/video_archive/` via `scripts/05_archive.py` and to the Video_Archive Drive
  folder. Don't leave multi-GB clips on `/home`.

---

## 8. Gotchas

- **`color=` base is infinite** — the compositor bounds every layer with `-t <dur>`; keep
  that if you hand-edit ffmpeg.
- **Render when the VM is quiet.** The 1080×1920 frame render is Chrome-heavy; a full reel
  is a few minutes. `build_reel.py` runs scenes sequentially. If Chrome/ffmpeg get OOM-killed
  under load, re-run — scenes already built are in `work/<slug>/` (use `--keep`, then rebuild
  only the missing scene with `--only N`).
- **Concat needs identical encode settings** — all scenes are encoded the same, so the
  driver stream-copies them together. If you hand-make a scene, match: 1080×1920, 25fps,
  h264 yuv420p, aac. A benign "Non-monotonous DTS" note at the join is auto-corrected.
- **Chart pill/annotation clamp:** annotation pills are clamped inside the plot so the last
  point's pill doesn't clip. Keep that if you move points.
- **The presenter's audio is taken as-is** by the reel driver (no denoise pass). For a hero
  reel, either shoot clean or pre-process the clip's audio before pointing the spec at it.

---

## 9. Manual fallback (if the driver breaks)

Every step the driver runs, you can run by hand:
```bash
# 1. render a scene's frames  (transparent=1 for text overlay, 0 for chart bg)
node reel_render.js panels/chart_reel.html scene.json /tmp/frames 13.2 25 0
# 2a. text beat composite:
ffmpeg -y -ss SS -t DUR -i SRC.MP4 -framerate 25 -i /tmp/frames/f%04d.png \
  -filter_complex "[0:v]crop=608:1080:CROPX:0,scale=1080:1920,setsar=1[bg];[bg][1:v]overlay=0:0[outv]" \
  -map "[outv]" -map 0:a -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -t DUR scene.mp4
# 2b. chart beat composite: see build_chart_scene() in build_reel.py for the PIP filtergraph
# 3. concat: ffmpeg -f concat -safe 0 -i list.txt -c copy out.mp4
```
The single-scene prototypes that these were generalised from live in
`work/sep2026_test/` (`panel_*_reel.html`, `compositor_*_reel.py`) for reference.
