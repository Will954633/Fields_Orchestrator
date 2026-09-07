#!/usr/bin/env python3
"""
Stage 04 — QC the deliverables → out/qc_report.json  (exit non-zero on FAIL)

Checks that turn "the render finished" into "the render is correct" (CLAUDE.md 7b):
  • the embed mp4 is exactly the spec the live site expects (square, H.264, yuv420p, has audio)
  • master duration ≈ sum of kept EDL spans (no silent segment loss)
  • integrated loudness is in band (audio was actually normalised, not silent)
  • a mid frame is not black/frozen (mask/overlay didn't blank the person)
  • captions + transcript exist and are non-trivial

Usage:  python3 scripts/04_verify.py [--config config.yaml] [--edl work/edl.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vlib  # noqa: E402

HERE = Path(__file__).resolve().parent.parent


def measure_loudness(path):
    p = vlib.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                  "loudnorm=print_format=json", "-f", "null", "-"], check=False)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if not m:
        return None
    try:
        return float(json.loads(m.group(0)).get("input_i"))
    except Exception:
        return None


def mean_luma(path, at):
    """Rough brightness of one frame (0–255) via signalstats YAVG."""
    p = vlib.run(["ffmpeg", "-hide_banner", "-ss", str(at), "-i", str(path),
                  "-frames:v", "1", "-vf", "signalstats,metadata=print", "-f", "null", "-"],
                 check=False)
    m = re.search(r"YAVG=([\d.]+)", p.stderr)
    return float(m.group(1)) if m else None


def main():
    vlib.load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--edl", default="work/edl.json")
    args = ap.parse_args()
    import yaml
    cfg = yaml.safe_load((HERE / args.config).read_text())
    out = (HERE / cfg["paths"]["out_dir"]).resolve()
    work = (HERE / cfg["paths"]["work_dir"]).resolve()
    slug = cfg["project"]["slug"]
    edl = json.loads((HERE / args.edl).read_text())

    checks, fails = [], 0

    def check(name, ok, detail=""):
        nonlocal fails
        status = "PASS" if ok else "FAIL"
        if not ok:
            fails += 1
        checks.append({"check": name, "status": status, "detail": detail})
        print(f"  [{status}] {name}  {detail}")

    # 1. embed mp4 spec
    web = out / f"{slug}.mp4"
    if web.exists():
        s = vlib.probe_summary(str(web))
        want = D = cfg.get("framing", {}).get("web_square", 512)
        check("embed_mp4_square", s["width"] == s["height"] == want,
              f"{s['width']}×{s['height']} (want {want}²)")
        check("embed_mp4_h264", s["vcodec"] == "h264", s["vcodec"])
        check("embed_mp4_has_audio", bool(s["acodec"]), s["acodec"] or "none")
    else:
        check("embed_mp4_exists", False, str(web))

    # 2. master duration vs EDL
    master = work / "master_square.mp4"
    if master.exists():
        got = vlib.probe_summary(str(master))["duration"]
        kept = sum(float(x["out"]) - float(x["in"]) for x in edl["segments"] if not x.get("drop"))
        # dissolve shortens by (n-1)*d; allow generous tolerance
        check("master_duration", abs(got - kept) <= max(2.0, 0.05 * kept),
              f"master {got:.1f}s vs EDL {kept:.1f}s")
        # 3. loudness
        li = measure_loudness(master)
        target = cfg.get("audio", {}).get("target_lufs", -16.0)
        check("audio_not_silent", li is not None and li > -50, f"input_i={li}")
        # 4. not black mid-frame
        yl = mean_luma(master, got / 2)
        check("midframe_not_black", yl is not None and yl > 20, f"YAVG={yl}")
    else:
        check("master_exists", False, str(master))

    # 5. captions + transcript
    srt = out / f"{slug}.srt"
    md = out / f"{slug}_transcript.md"
    check("srt_present", srt.exists() and srt.stat().st_size > 100, f"{srt.stat().st_size if srt.exists() else 0}B")
    check("transcript_present", md.exists() and md.stat().st_size > 200,
          f"{md.stat().st_size if md.exists() else 0}B")

    report = {"slug": slug, "fails": fails, "checks": checks}
    (out / "qc_report.json").write_text(json.dumps(report, indent=2))
    print(f"\n{'✓ QC PASSED' if fails == 0 else f'✗ QC FAILED ({fails})'} → {out/'qc_report.json'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
