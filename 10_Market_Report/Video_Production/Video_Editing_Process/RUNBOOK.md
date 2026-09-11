# RUNBOOK — Assisted mode (Claude + Will)

The default, recommended path for the monthly hero video. Claude runs every mechanical
stage; the **one** decision Will owns is the cut. End to end ≈ 30–45 min, most of it the
final render.

> Prereqs (once per session):
> ```bash
> cd /home/fields/Fields_Orchestrator/10_Market_Report/Video_Production/Video_Editing_Process
> source /home/fields/venv/bin/activate
> set -a && source /home/fields/Fields_Orchestrator/.env && set +a
> ```

## Step 1 — Drop the footage & configure

Put the raw clips in a folder (default `../Example_Raw_Video`, or point `raw_dir` at the
month's folder). Then:

```bash
cp config.example.yaml config.yaml
# edit config.yaml: project.slug, project.title, project.suburb, paths.raw_dir
```

Naming convention for `slug`: `<suburb>_<YYYY-MM>_<topic>` → `robina_2026-08_dom`.

## Step 2 — Probe & transcribe (Claude runs)

```bash
python3 scripts/00_probe.py        # → work/manifest.json   (clips, durations, order)
python3 scripts/01_transcribe.py   # → work/raw_transcript.md   ← the artefact for step 3
```

`raw_transcript.md` is every take, verbatim, **including the repeated takes and false
starts** — that repetition is exactly what the cut removes.

## Step 3 — Author the cut (the decision) ⭐

This is where "seamless, not repetitive" is won or lost. Claude reads `raw_transcript.md`
and proposes an EDL; Will approves or adjusts.

1. Claude generates the scaffold and reads the transcript:
   ```bash
   python3 scripts/02_propose_edl.py     # → work/edl.draft.json  (one full clip per row)
   ```
> **Cut points are approximate — the audio decides the exact frame.** Stage 03 runs
> **snap-to-silence** (`assembly.snap_to_silence`, on by default): it maps each clip's
> real sound/silence (ffmpeg `silencedetect`) and moves every `in`/`out` onto a silence
> gap — so a sentence is never clipped mid-word and every join lands on a breath. It pads
> `snap_tail_pad` after the last word and `snap_preroll` before the first, and if there's
> no pause forward within `snap_max_extend` it falls back to the nearest pause *behind*
> (ends the previous complete sentence). The adjustments are logged to
> `work/boundaries.json` and `04_verify.py` fails if any cut couldn't be snapped to
> silence. So author the EDL at *sentence* granularity — you don't need frame accuracy,
> and you should **not** set a cut mid-sentence expecting it to hold.

2. **Claude proposes the cut** by editing the scaffold into `work/edl.json`, applying the
   rubric in [AUTONOMOUS.md §Cut rubric](AUTONOMOUS.md#cut-rubric):
   - keep only the **best single take** of each idea; drop restarts, stumbles, dead air;
   - order intro → each chart in shot order → close;
   - cut on pauses, leave ~0.15 s of breath, never clip first/last word;
   - vary `zoom` slightly (e.g. 1.00 then 1.06) on adjacent same-topic takes so a hard
     cut doesn't read as a jump;
   - fill `chapter` labels (they flow into the storyboard).
   See [examples/robina_2026-08.edl.json](examples/robina_2026-08.edl.json) for shape.
3. **Will reviews the EDL** — a readable list of `(clip, in→out, chapter, what's said)`.
   Cheapest possible review: it's text, not video. Approve, or say "keep take 2 of the
   intro, it's cleaner" and Claude edits the rows.
4. *(optional)* render a fast proof of just the cut before the full grade:
   ```bash
   python3 scripts/03_build.py --edl work/edl.json --stage segments
   python3 scripts/03_build.py --edl work/edl.json --stage master
   ffplay work/master_square.mp4     # or extract a few frames to eyeball
   ```

## Step 4 — Build (Claude runs)

```bash
python3 scripts/03_build.py --edl work/edl.json      # full: segments→master→captions→derivatives
```

Timings (e2-standard-4): segment render dominates — roughly **real-time per minute of
kept footage** for the 4K→1080 crop/grade pass; the derivatives add a few minutes.
For a 10-min video expect ~15–25 min. Run it in the background and check the tail.

Stages are independently re-runnable with `--stage {segments,master,captions,derivatives}`
— if you only re-cut, re-run from `segments`; if you only re-graded audio, `derivatives`
alone rebuilds the movs from the existing master.

### Rendering on this VM — memory & contention (read before a full run)

The 4K→1080 segment pass is CPU- and memory-heavy, and `fields-orchestrator-vm` also runs
mongod, code-server, the orchestrator and often a `claude -p` session. Observed 2026-09-07:
a full 9-segment (~10 min) build was **OOM-killed** part-way through the longest segments
under that load, leaving a **corrupt** `work/seg_NNN.mp4` (0 bytes, "moov atom not found").

Practical rules:
- **Render the segment pass when the VM is quiet** (nothing else heavy running), or split it:
  `--stage segments` first, confirm all `work/seg_*.mp4` are non-zero and probe cleanly, then
  `--stage master captions derivatives`. Every stage is independently re-runnable, so a killed
  segment pass just resumes — but **delete any zero-byte/corrupt `seg_*.mp4` first** or the
  concat inherits the corruption.
- The intermediates use `-preset veryfast -crf 16` for this reason (visually lossless as an
  intermediate, roughly half the wall-clock of `medium`). The finals keep full quality.
- Peak memory is one 4K decode at a time (the pipeline is sequential), so short spans are
  safe; the risk is the long (>60 s) 4K segments. If OOM recurs, render those segments
  individually.
- **Don't kill/restart a running build to "unstick" it** — under contention it's slow, not
  stuck. Killing mid-segment is what produces the corrupt intermediate above.

## Step 5 — QC (Claude runs, must pass)

```bash
python3 scripts/04_verify.py     # exits non-zero on any FAIL
```

Then **watch it** — QC catches spec/loudness/black-frame failures, not taste. Extract a
few frames and read them (multimodal), and spot-check the audio for a clean join at each
cut. Verify the transcript numbers against the audio (CLAUDE.md §5 — exact figures).

## Step 6 — Ship

Follow [OUTPUT_SPEC.md §Deploy](OUTPUT_SPEC.md#deploy-the-embed): copy `out/<slug>.mp4`
into the Website repo's `public/walkthrough/`, push via `gh api` (git push hangs on this
VM — CLAUDE.md §2), and if it's a new suburb/month update `WALK_SRC` in
`MarketFlowProto.engine.ts`. Then the website verification gates (CLAUDE.md §4):
screenshot `/news/<suburb>?walkthrough=1`, read the PNG, confirm the avatar plays.

Log it: fix-history entry if you fixed anything, and an ops note that the month's video
shipped.

## Step 7 — Archive (mandatory once shipped)

**The root disk is 97G and shared with the production database — finished video does
not live on it.** (5.4G of shipped video was part-cause of the 2026-09-11 disk incident
that corrupted three nights of MongoDB backups.) The moment Step 6 is verified live:

```bash
# the month's raw-footage/project folder (repeat per folder if several):
python3 scripts/05_archive.py --project <Project_Folder> --purge --drive

# then the shared scratch (work/ + qa/ + out/) for the shipped slug:
python3 scripts/05_archive.py --work --purge --drive
```

What it does: copies to `/data/blobs/video_archive/<name>/` (738G disk, synced
off-site nightly to `gs://fields-blob-backup` at 03:00), **verifies the copy
byte-for-byte, and only then deletes the local copy**. `--drive` additionally pushes
the same bundle to the shared [Video_Archive Drive folder](https://drive.google.com/drive/folders/1cIrw53ggePRR0eVZ0Jf8nq43NsHdAJ8D)
for browser access.

Notes:
- `out/` is included in `--work` deliberately — the social circle `.mov`s ship
  nowhere else (the website repo only receives the web mp4).
- The Drive OAuth token dies every 7 days (Testing-mode app — see memory
  `gdrive_oauth_7day_expiry`). A dead token fails only the Drive leg with a
  re-auth pointer; the blob+GCS copy is the durable one. Catch Drive up later with
  `--drive-only`.
- Retrieval for a re-cut: `rsync -a /data/blobs/video_archive/<Project>/ assets/<Project>/`.

## If something looks wrong

| Symptom | Knob |
|---|---|
| Will off-centre in the circle | per-segment `face_cx` in the EDL (0=left, 1=right) |
| Jarring jump at a cut | give the two segments different `zoom`, or switch `assembly.transition: dissolve` |
| Too dark / flat | `look.brightness`, `look.contrast`, `look.gamma` |
| Colour too cool/warm | `look.warmth` |
| Hiss / AC noise remains | `audio.denoise: anlmdn`, or lower `audio.denoise_nf` (e.g. −20) |
| Captions overlap the circle | `captions.margin_v` up, or `framing.circle_diameter`/`circle_cy_frac` down/up |
| Wrong figure in captions | fix the `.srt`, re-run `--stage derivatives` |
