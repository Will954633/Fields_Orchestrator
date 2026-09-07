# AUTONOMOUS mode — a Claude Max agent, no human until final review

Same pipeline as the [RUNBOOK](RUNBOOK.md); the only difference is **who authors the
EDL**. Here a Claude Max agent does the cut, renders, self-QCs, and reports — Will
reviews the finished video, not the cut list. Use it for volume (extra suburbs, re-cuts,
first drafts) — not for the primary monthly hero video, which stays assisted.

## Two ways to run it

### A. Claude agent as the cutter (recommended autonomous path)

A Claude session (this one, a background Agent, or a `spawn_task.py` out-of-session job)
runs stages 00–01, **reads `work/raw_transcript.md`, and writes `work/edl.json` by hand**
applying the rubric below — then runs 03–04. Claude's judgement on take-selection is far
better than a single LLM JSON call, and it can watch its own output frames and re-cut.

```bash
# stages the agent runs itself:
python3 scripts/00_probe.py
python3 scripts/01_transcribe.py
#   → agent READS work/raw_transcript.md, WRITES work/edl.json (the cut)
python3 scripts/03_build.py --edl work/edl.json
python3 scripts/04_verify.py
#   → agent extracts a few frames, reads them, spot-checks joins, re-cuts if needed
```

### B. Fully headless (`--auto`), no agent judgement

For batch runs with no Claude in the loop at all, stage 02 asks Gemini to produce the
cut against the same rubric:

```bash
python3 scripts/00_probe.py
python3 scripts/01_transcribe.py
python3 scripts/02_propose_edl.py --auto      # → work/edl.auto.json  (Gemini cuts)
cp work/edl.auto.json work/edl.json
python3 scripts/03_build.py --edl work/edl.json
python3 scripts/04_verify.py
```

`--auto` is the weakest link (an LLM guessing timecodes from a transcript). Always gate it
behind QC + a human final-watch. Prefer path A.

## Cut rubric

The standard both the Claude agent and `--auto` apply:

1. **Seamless & not repetitive.** Will re-records lines and restarts sentences. Keep only
   the **best single take** of each idea. Drop false starts, "let me start again",
   stumbles, filler, long pauses, and any point re-explained better later.
2. **Narrative order.** Intro → each chart/topic in the order shot → close. Don't invent
   content; only cut and order what exists. Cross-reference the
   [storyboard](../../issues/Video/August_2026/Robina_August_Walkthrough_Storyboard.md)
   chapter order (Intro → Days on Market → bridge → Median Price → Asking vs Sale →
   Withdrawn → New House Lending → Close).
3. **Clean joins.** Cut on pauses / sentence boundaries. Leave ~0.15 s of breath at each
   in/out; never clip the first or last word.
4. **Argument intact.** The editorial through-line must still make sense end to end, and
   must keep the **directional, non-predictive** framing (CLAUDE.md §5) — the close and
   the leading-indicator section especially.
5. **Break jump-cuts.** Give adjacent same-topic takes slightly different `zoom`
   (1.00 / 1.06) so a hard cut reads as a deliberate punch-in, not a glitch.

## Self-monitoring (mandatory for any scheduled/batch use — CLAUDE.md Rule 7)

If this ever runs on a schedule or as a spawned batch, wrap the build in the shared
heartbeat so it can't fail silently, and **assert the zero-output path** (Rule 7b):

```python
from job_status import job_run   # scripts/job_status.py
with job_run("walkthrough_build", cadence_hours=None, title="Walkthrough video build") as beat:
    n_seg = build(...)               # returns kept-segment count
    qc_fails = verify(...)
    beat.metrics = {"segments": n_seg, "qc_fails": qc_fails}
    if n_seg == 0:
        raise RuntimeError("EDL produced 0 segments — cut failed, not an empty edit")
    if qc_fails:
        raise RuntimeError(f"QC failed ({qc_fails}) — do not publish")
    beat.detail = f"{n_seg} segments, QC clean"
```

The point: a build that renders a black 0-second clip must **raise**, not report success.
QC (`04_verify.py`) already exits non-zero on the spec/loudness/black-frame failures — a
batch wrapper must treat that exit code as fatal and never ship on failure.

## Spawning it out-of-session

To hand the whole thing to a fresh headless session (survives this conversation), use
`scripts/spawn_task.py` (CLAUDE.md Rule 9). The brief must name: the raw footage folder,
the target slug/title, this runbook, and the deliverable (a QC-passing `out/<slug>.mp4`
plus a diff adding it to the Website repo — **not** an unattended deploy; there is no
deploy scope). Run the first two stages yourself first so the brief can cite a real
`raw_transcript.md`.
