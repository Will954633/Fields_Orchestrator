# Walkthrough Video Production — raw footage → embeddable edited clip

A repeatable pipeline that turns a folder of raw DJI talking-head clips into the
finished walkthrough asset embedded on the site (e.g.
`https://fieldsestate.com.au/news/robina?walkthrough=1`).

It reproduces, as code, exactly what was done by hand for **Robina — August 2026**:

```
10 raw 4K clips (13.9 min)                         issues/Video/August_2026/
   → cull best takes, trim, reorder  ── the EDL     Robina_August_No_Captions.mov
   → recentre + square-crop on face                 Robina_August_01_Captions_Mask.mov
   → colour / lighting grade                        Robina_August_Transcript.md
   → denoise + loudness-normalise audio             public/walkthrough/robina_2026-08_dom.mp4
   → circle mask                                    (the live embed)
   → transcribe + burn captions
   → export web mp4 + social movs (10.8 min)
```

## The one hard part, and how we handle it

Everything except **which takes to keep and in what order** is deterministic ffmpeg
and can be fully automated. Take-selection needs judgement — Will re-records lines,
restarts sentences, explains the same idea twice. That decision is captured in a single
artefact, the **EDL** (Edit Decision List, `edl.json`): the list of `(clip, in, out)`
spans in playback order. The render engine only executes the EDL, so the same EDL always
produces the same video.

That gives us the two operating modes the brief asked about — they differ **only** in who
authors the EDL:

| Mode | Who cuts | When | Doc |
|---|---|---|---|
| **Assisted** (default, recommended) | Claude proposes the cut from the transcript in a session **with Will**; Will approves | Monthly hero videos, anything customer-facing | [RUNBOOK.md](RUNBOOK.md) |
| **Autonomous** | A Claude Max agent authors + renders + self-reports, no human in the loop until final review | Batch/scale, second-suburb variants, drafts | [AUTONOMOUS.md](AUTONOMOUS.md) |

**Recommendation:** run **assisted** for the primary monthly video (it's the face of the
brand, pre-revenue, editorial-sensitive), and keep **autonomous** for volume — extra
suburbs, re-cuts, and first drafts Will then trims. Both share every script below; the
only difference is stage 02.

## Pipeline stages

| Stage | Script | Does | Output |
|---|---|---|---|
| 00 | `scripts/00_probe.py` | Probe raw clips, order by shot time | `work/manifest.json` |
| 01 | `scripts/01_transcribe.py` | Transcribe every take verbatim + detect face centre | `work/transcripts/*.json`, `work/raw_transcript.md` |
| 02 | `scripts/02_propose_edl.py` | Build the cut list (scaffold, or `--auto`) | `work/edl.draft.json` / `edl.auto.json` |
| 03 | `scripts/03_build.py` | **The render engine** — cut→crop→grade→denoise→mask→caption→export | `out/<slug>*.{mp4,mov,srt,md}` |
| 04 | `scripts/04_verify.py` | QC gate (spec, duration, loudness, not-black, captions) | `out/qc_report.json` |

## Quick start

```bash
cd /home/fields/Fields_Orchestrator/10_Market_Report/Video_Production/Video_Editing_Process
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a

cp config.example.yaml config.yaml          # edit slug/title/raw_dir
python3 scripts/00_probe.py                  # → work/manifest.json
python3 scripts/01_transcribe.py             # → work/raw_transcript.md   (read this)
python3 scripts/02_propose_edl.py            # → work/edl.draft.json       (scaffold)
#  ── cut it down: edit into work/edl.json  (assisted: Claude+Will;  auto: 02 --auto) ──
python3 scripts/03_build.py --edl work/edl.json
python3 scripts/04_verify.py                 # QC → exits non-zero on FAIL
```

Then ship the embed (see [OUTPUT_SPEC.md](OUTPUT_SPEC.md) §Deploy):

```bash
cp out/<slug>.mp4  /home/fields/Feilds_Website/01_Website/public/walkthrough/<slug>.mp4
#  push public/walkthrough/<slug>.mp4 to the Website repo via gh api (CLAUDE.md §2)
```

## What you need to know before touching this

- **Deliverables & exact specs:** [OUTPUT_SPEC.md](OUTPUT_SPEC.md)
- **The EDL format:** [edl.schema.json](edl.schema.json) + [examples/](examples/)
- **All tunables** (framing, grade, denoise, captions, circle): [config.example.yaml](config.example.yaml)
- **Requirements:** ffmpeg + ffprobe (system), `/home/fields/venv` (pyyaml, google-auth,
  requests), Vertex key at `/home/fields/.gcp-vertex-key.json` (transcription + face
  detection go through Gemini/Vertex — already wired via `shared/claude_vision.py`).
