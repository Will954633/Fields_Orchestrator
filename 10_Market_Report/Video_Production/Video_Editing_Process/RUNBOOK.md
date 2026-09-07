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
