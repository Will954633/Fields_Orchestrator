#!/usr/bin/env python3
"""
Stage 01 — transcribe every raw clip → work/transcripts/<clip>.json
                                     → work/raw_transcript.md  (human/agent reads THIS)

Each clip is transcribed verbatim (including false starts and repeated takes) so the
EDL author can SEE the repetition and cut it. Also detects Will's face centre per clip
(for the crop) and stashes it alongside.

Usage:  python3 scripts/01_transcribe.py [--config config.yaml] [--only DJI_...MP4]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vlib  # noqa: E402

HERE = Path(__file__).resolve().parent.parent


def main():
    vlib.load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--only", help="transcribe just this clip basename")
    ap.add_argument("--no-face", action="store_true", help="skip face-centre detection")
    args = ap.parse_args()

    import yaml
    cfg = yaml.safe_load((HERE / args.config).read_text())
    work = (HERE / cfg["paths"]["work_dir"]).resolve()
    tdir = work / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((work / "manifest.json").read_text())

    def mmss(s): s = int(round(s)); return f"{s//60}:{s%60:02d}"

    combined = [f"# {cfg['project']['title']} — RAW transcript (all takes, unedited)", "",
                "Every clip, verbatim, **including repeated takes and false starts** — this is",
                "what you cut down into the EDL. `face_cx` is the auto-detected crop centre.", "", "---", ""]

    for clip in manifest["clips"]:
        if args.only and clip["name"] != args.only:
            continue
        src = Path(manifest["raw_dir"]) / clip["name"]
        stem = Path(clip["name"]).stem
        print(f"→ {clip['name']}  ({clip['duration']:.0f}s)")

        mp3 = work / f"_asr_{stem}.mp3"
        vlib.extract_audio_for_asr(str(src), str(mp3))
        segments = vlib.transcribe_audio(str(mp3))
        mp3.unlink(missing_ok=True)

        face_cx = None if args.no_face else vlib.detect_face_cx(str(src), at=min(1.0, clip["duration"] / 3))
        rec = {"clip": clip["name"], "duration": clip["duration"],
               "face_cx": face_cx, "segments": segments}
        (tdir / f"{stem}.json").write_text(json.dumps(rec, indent=2))
        print(f"   {len(segments)} segments, face_cx={face_cx}")

        combined.append(f"## {clip['name']}  ·  {clip['duration']:.0f}s  ·  face_cx={face_cx}")
        combined.append("")
        for s in segments:
            combined.append(f"**[{mmss(s['start'])}–{mmss(s['end'])}]** {s['text'].strip()}")
        combined.append("")

    if not args.only:
        (work / "raw_transcript.md").write_text("\n".join(combined))
        print(f"\n✓ wrote {work/'raw_transcript.md'}  (read this to author the EDL)")


if __name__ == "__main__":
    main()
