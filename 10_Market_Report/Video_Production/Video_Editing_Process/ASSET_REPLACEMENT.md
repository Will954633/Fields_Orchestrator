# Replacing a walkthrough's video + captions (and re-timing the ink)

How to drop a **new cut of the talking-head video** into the live on-page walkthrough. Written
from the **Robina August V2** swap (2026-09-08); the same steps apply to **Varsity Lakes** and
**Burleigh Waters** because every suburb uses the **same narration script** — only the numbers,
the peak month, and the day counts change.

> **The trap that makes this more than a file copy:** a new cut is almost never the same length,
> and re-recorded narration adds/removes seconds *mid-clip*. The Robina V2 cut was 6s shorter
> overall **but ran +23s behind the old one by the median chart** (extra narration was added
> around 2:35–3:00). The on-page **ink beats are timed in video-seconds**, so if you swap the
> video without re-timing the beats, every circle/note after the first chart fires at the wrong
> moment. **You must re-time the beats to the new audio.** The tooling below does it from the new
> captions in one step.

---

## What the editor hands you

New assets live in `assets/<Suburb>_<Month>_V2/` (e.g. `assets/Robina_August_V2/`). The three
files that matter for the website:

| File | What it is | Used for |
|---|---|---|
| `<slug>.mp4` | the web mp4 (512², h264+aac) | the embed video — **re-encode first, see step 1** |
| `<slug>_walk_segments.txt` | `var WALK_SEGMENTS=[[t,"text"],…]` | the captions, already synced to the new video |
| `master_words.json` | word-level timestamps | only if you need to hand-check a specific beat |

The rest (`edl.json`, `manifest.json`, `qc_report.json`, `_preview_*.mp4`, the `_circle*.mov`
socials) are the editing pipeline's own artefacts — ignore them for the website swap.

Check `qc_report.json` shows `"fails": 0` before starting.

---

## The swap — step by step

Paths: website = `/home/fields/Feilds_Website/01_Website`; engine =
`src/components/MarketFlowProto/MarketFlowProto.engine.ts`; tools = this folder's `qa/`.

### 1. Re-encode the video for the web (~16 MB, faststart)
The pipeline's web mp4 can be large (Robina V2 was **62 MB @ 775 kbps** — too heavy for a mobile
autoplay embed, and near the GitHub Contents-API limit). Re-encode to the ~16 MB / ~200 kbps the
old embed used — plenty for a 512² talking head — with `+faststart` so it streams from the first
byte:
```bash
ffmpeg -y -i assets/<S>_V2/<slug>.mp4 -c:v libx264 -crf 29 -preset veryfast -pix_fmt yuv420p \
  -vf scale=512:512 -c:a aac -b:a 96k -movflags +faststart /tmp/<slug>_web.mp4
ls -la /tmp/<slug>_web.mp4     # aim ~15–25 MB
```

### 2. Replace the captions (`WALK_SEGMENTS`)
The new `*_walk_segments.txt` is already synced to the new video — use it verbatim. Replace the
`var WALK_SEGMENTS=[[…]];` line in the engine with its contents (compact JSON is fine).

### 3. Re-time the ink beats — `qa/retime_beats.py`
Every ink beat is anchored to a **structural trigger phrase** in the narration (not a
suburb-specific number), so the same map re-times any suburb. It reads the new captions and prints
a `remap={old_t:new_t,…}` dict:
```bash
cd qa && python3 retime_beats.py ../assets/<S>_V2/<slug>_walk_segments.txt
# -> remap={...}   and, on stderr, "all triggers matched" (or a list of any it couldn't find)
```
If it reports **unmatched triggers**, the wording for that line changed — open the new captions,
find the equivalent phrase, and update that beat's trigger in `retime_beats.py` (keep it
structural, not a number/month, so it survives the next suburb).

### 4. Apply captions + remap to the engine (one script)
```python
# from the website dir; edit the two paths at the top
import re, json
NEWCAP = "…/assets/<S>_V2/<slug>_walk_segments.txt"
REMAP  = { …paste from step 3… }
eng = "src/components/MarketFlowProto/MarketFlowProto.engine.ts"
s = open(eng).read()
cap = json.loads(re.search(r'\[\s*\[.*\]\s*\]', open(NEWCAP).read(), re.S).group(0))
s = re.sub(r'var WALK_SEGMENTS=\[\[.*?\]\];',
           "var WALK_SEGMENTS="+json.dumps([[round(float(t),2),x] for t,x in cap], separators=(',',':'))+";",
           s, count=1, flags=re.S)
def repl(m):
    v=float(m.group(1)); k=int(v) if v==int(v) else v
    return "{ t:%s,"%REMAP[k] if k in REMAP else m.group(0)
s = re.sub(r'\{ t:(\d+(?:\.\d+)?),', repl, s)   # count of replacements MUST equal your beat count
open(eng,"w").write(s)
```
⚠ **Beats that share one caption segment collapse to the same time** (e.g. "25 days in June" and
"50 days in August" are one sentence; the peak and latest medians are one sentence). `retime_beats`
gives both the segment start — nudge the *second* of each such pair a few seconds later by hand so
the two circles don't draw simultaneously (Robina: June 48 / Aug 51; peak 193 / latest 198).

### 5. Put the video in place + build
```bash
cp /tmp/<slug>_web.mp4 public/walkthrough/<slug>.mp4
npm run build          # must pass (prod-strictness gate)
```
(If this is a *new suburb* rather than a re-cut, also point `WALK_SRC` at the new file — see
"Adding a new suburb" below.)

### 6. Verify the beats land on the new audio — screenshot at the trigger moments
Use the local dev server + the headless shooter (`qa/`/`scratchpad` `_shotwalk.cjs`): seek to a few
remapped beat times and read the frame — **the caption phrase must match the ink being drawn.**
Check at least: DOM 50-days, median peak (biggest mid-clip drift), the asking Dec-2023 flip, the
withdrawn 2025→2026 pair, and the lending 20%/10%. Robina V2 verified: at the median-peak beat the
caption read "…1.5 million back in" exactly as the peak was circled.

### 7. Deploy (git push hangs → `gh api`, CLAUDE.md §2)
Push the engine (text) and the mp4 (binary, JSON `--input`):
```bash
SHA=$(gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' --jq '.sha')
python3 -c "import json,base64;print(json.dumps({'message':'…','content':base64.b64encode(open('LOCAL','rb').read()).decode(),'sha':'$SHA'}))" > /tmp/p.json
gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' --method PUT --input /tmp/p.json
```
Then wait for Netlify, log the deploy (`website-deploy-tracker.py`), and re-shoot the same beats on
the **live** URL. ⚠ Same filename ⇒ Netlify CDN may serve the old video briefly; hard-refresh /
re-shoot after the build completes.

---

## Adding a NEW suburb (Varsity Lakes / Burleigh Waters)

**DONE for Varsity Lakes on 2026-09-09** — the engine is now **suburb-aware** via a registry, so adding
Burleigh Waters is a small, mechanical follow. Mechanism (see fix-history `[WALK-VARSITY-LAKES]`):

- **`walkSuburb()`** reads `state.suburb` (set by `mountFlow` from the `/news/:suburb` route).
- **`walkConf()`** is a registry keyed by **(suburb, version)** → `{src, segs, beats, end, chapters}`.
  `WALK_SRC()`, `walkCues()`, `wkSkip()` (chapters), `walkFlagOn()` (gates the hero — returns false, so
  NO hero, when the suburb has no asset), and `startWalk`'s beat dispatch are ALL driven by it.
- The **ink beats read live chart geometry** (`domPts`/`wkMedianPts`/`wkAskLines`/the blue `#007bff`
  lending line, etc.), so circle POSITIONS and the circled NUMBERS auto-adapt to each suburb's data
  (Varsity's DOM auto-labelled ≈23→35; Robina's was ≈25→50 — same beat, no code change).
- The **withdrawn + lending charts are 3-suburb POOLED** (23→53, 20→10) — identical across suburbs, so
  those beats are copied verbatim.

**To add Burleigh Waters:**
1. Re-encode its `*_dom.mp4` (step 1) → `public/walkthrough/burleigh-waters_2026-08_dom.mp4`.
2. Add `WALK_SEGMENTS_BURLEIGH` from its `*_walk_segments.txt` (compact JSON, one line).
3. Add a `"Burleigh Waters": { 1:{ src, segs:WALK_SEGMENTS_BURLEIGH, beats:walkBeatsVarsity /*or a variant*/, end:<videoLen>, chapters:[…] } }` entry to `walkConf()`.
4. **Beats:** if Burleigh's narration matches the V3 structure (flat/rising median? layer-in-Robina asking?),
   reuse `walkBeatsVarsity` and just retime; if its median/asking STORY differs, clone it to
   `walkBeatsBurleigh()` and adjust those two sections (everything else — DOM, withdrawn, lending, stages —
   is shared). **Read the captions and check the median + asking narration specifically**, that's where
   suburbs diverge.
5. Verify BOTH the new suburb AND Robina (a registry bug can break routing) via headless screenshots at
   the DOM/median/asking/withdrawn/lending beats, then deploy engine + video.

✅ **The on-page chart camera zoom (`wkCamera`) WORKS as of 2026-09-09** (fix-history
`[WALK-CAMERA-VIEWBOX-FIX]`). It zooms by animating the svg's **`viewBox` attribute** (SVG-native, always
paints) + a matching screen affine on the ink wrap — NOT a CSS transform on the svg (that silently painted
nothing, the `transform-box: view-box` quirk). Reuse `wkCamera(DS,1000,940,3.2,secs,352,420)` for a new
suburb's withdrawn "zoom in on 2025" beat (draw the 23/53 circles FIRST, then camera).

⚠ **When cloning a beat set, grep every helper call against `function <name>`** — a deleted helper (e.g.
`wkArrowVB`, removed 2026-09-09) is a runtime *throw* inside the rAF beat loop that silently kills
`walkTick` and everything downstream (transport freezes at 0:00). It may NOT surface on the paused-seek
verify path — only on monotonic playback. Burleigh hit exactly this (`[WALK-BURLEIGH-ARROWVB-THROW]`).

---

## Reusable tools in `qa/`
- **`retime_beats.py`** — the trigger-phrase → beat map; prints `remap={old:new}` from any suburb's
  `walk_segments.txt`. The map is the artefact to maintain if narration wording changes.
- **`sync_check.py` + `transcribe_words.py`** — independent caption-vs-audio drift checker (word
  timestamps). Editor-supplied `walk_segments` are usually already synced; use this only to audit.
- **`walkthrough_qa.cjs`** — layout lint (overlap / off-screen / over-caption / stale-ink) across
  desktop + mobile. Run it after a swap the same as for any change (see WALKTHROUGH_EXPERIENCE.md §7).

---

## Adding a SECOND version of a walkthrough (`?walkthrough=2`)

Done for Robina on 2026-09-09 (the V3 cut). Use this when you want a second cut of the SAME suburb
live alongside the first (A/B), rather than replacing it. Unlike a straight swap, a second cut is
usually a **different narration** — reworded, a different length, and sometimes different chart
stories — so it needs its **own beat choreography**, not a re-time of the first.

The engine is versioned by the `?walkthrough=` value:
- **`walkVersion()`** reads the query param → `1` or `2` (0 = off). `walkFlagOn()` = `walkVersion()>0`
  (gates the hero).
- **`WALK_SRC()`** returns the per-version video path (`robina_2026-08_dom.mp4` vs
  `robina_2026-08_v3_dom.mp4`). Used by `avatarVideo()` and `#wkVid`.
- **Captions** are per-version: `WALK_SEGMENTS` (v1) and `WALK_SEGMENTS_V2` (v2); `walkCues()` picks
  by version.
- **Beats** are per-version: `walkBeats()` (v1) and `walkBeatsV3()` (v2); `startWalk` dispatches on
  `walk.version`.

To add version 2:
1. Re-encode + place the video as a **new file** (`robina_2026-08_v3_dom.mp4`); wire it into
   `WALK_SRC()`.
2. Add `WALK_SEGMENTS_V2` from the new `walk_segments.txt`; confirm `walkCues()` and its `END`
   fallback are version-aware (⚠ when you copy caption logic, swap **every** `WALK_SEGMENTS[...]`
   ref — a missed `[i+1]` reference read past the shorter v1 array and threw
   `Cannot read '0' of undefined`, which silently killed the whole beat loop; the transport shows
   but the video sticks at 0:00).
3. **Author `walkBeatsV3()` to the new narration** — don't assume `retime_beats.py` will map it. Read
   the new captions; most beats reuse the same helpers (`wkEnter`/`wkDock`/`wkDomJune`/`wkMedianPts`/
   `wkAcRecent`/…), but any section whose *story* changed needs new beats (V3's asking chart tells a
   June-2026 "$1.6M asking vs $1.49M median, then dropped to match" story instead of the
   Dec-2023-flip story; V3 also adds a rental-yields STAGE section). Circle POSITIONS still read from
   live geometry, so they adapt.
4. ⚠ **Zoom + annotate order (double-transform trap):** the camera scales the chart **and**
   `#wkInkWrap` together. If you zoom FIRST and then draw ink, the ink is computed from the
   already-transformed chart and then transformed AGAIN by the wrap → it flies off-screen. **Draw the
   circles/notes first, THEN `wkCamera` to magnify** (the ink is already in the wrap and scales with
   it — the V1 asking-recent pattern). This is why the V3 asking beats are circle(300)/arrow(308)/
   zoom(312), not zoom-then-circle.
5. Build, verify **both** `?walkthrough=1` and `?walkthrough=2` (a versioning bug can break one and
   not the other), then deploy the engine + the new video.

⚠ **Headless verify for a longer/2nd video:** a bigger clip needs buffering before a seek to a late
timepoint sticks — use a shooter that waits for the `seeked` event (`_shotwalkR.cjs`), not a fixed
sleep, or late frames screenshot blank at 0:00.

See **WALKTHROUGH_EXPERIENCE.md** for the choreography/design rules the beats implement.
