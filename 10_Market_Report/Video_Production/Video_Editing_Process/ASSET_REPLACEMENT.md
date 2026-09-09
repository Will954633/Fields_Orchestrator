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

The walkthrough currently runs **Robina only** (`WALK_SRC` + `WALK_SEGMENTS` are single values, and
`?walkthrough=1` is wired to the Robina overview). Because the narration script is identical, the
**captions timeline and the beat remap are produced the same way** (steps 2–4, and `retime_beats.py`
works unchanged). What's extra for a *new* suburb is making the engine pick the right assets:

- Make `WALK_SRC` and `WALK_SEGMENTS` **per-suburb** (keyed by the `/news/:suburb` slug) instead of
  single constants, and gate the hero on the suburb having an asset.
- The **ink beats are shared** — same `walkBeats()`, just re-timed per suburb's captions. Circle
  *positions* already read from live chart geometry (`wkMedianPts`, the blue `#007bff` lending line,
  etc.), so they auto-adapt to each suburb's data; only the **times** come from `retime_beats`.
- The lending chart is the **3-suburb pooled** indicator — identical across all three walkthroughs,
  so its beats/times/circles don't change between suburbs.

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
