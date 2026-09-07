#!/usr/bin/env python3
"""
Stage 02 — turn the raw transcripts into an EDL (the cut list).

Two modes:

  (default)  Scaffold. One segment per clip, full span, face_cx filled in, transcript
             inline. Writes work/edl.draft.json. This is the starting point a HUMAN
             (or a Claude agent) edits down — trimming in/out, dropping repeated takes
             and dead air, re-ordering. THIS is where "seamless, not repetitive" is won.

  --auto     Headless cutter. Sends the full raw transcript to Gemini/Vertex and asks
             it to produce the trimmed, de-duplicated EDL against an explicit rubric,
             then validates every (src,in,out) against the manifest. Writes
             work/edl.auto.json. Use this only when no Claude agent is doing the cut;
             a Claude Max agent authoring the EDL by hand is the higher-quality path
             (see AUTONOMOUS.md).

Usage:  python3 scripts/02_propose_edl.py [--config config.yaml] [--auto]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vlib  # noqa: E402

HERE = Path(__file__).resolve().parent.parent

RUBRIC = """You are editing a real-estate market-update talking-head video into a single
seamless cut. You are given the VERBATIM transcript of every raw take (clips shot in
order). Produce the Edit Decision List: the spans to KEEP, in playback order.

Rules:
1. SEAMLESS & NOT REPETITIVE: the presenter re-records lines and restarts sentences.
   Keep only the BEST single take of each idea. Drop false starts, "let me start again",
   stumbles, long pauses, and any point re-explained better later.
2. NARRATIVE ORDER: intro → each chart/topic in the order they were shot → close.
   Do not invent content; only cut and order what exists.
3. Cut ON pauses/sentence boundaries so joins are clean. Leave ~0.15s of breath at each
   in/out; never clip the first or last word.
4. Keep the editorial content intact — the argument must still make sense end to end.

Return STRICT JSON only:
{"segments":[{"src":"<clip filename>","in":<sec>,"out":<sec>,"chapter":"<label>","transcript":"<what is said>"}],
 "notes":"<one paragraph: what you cut and why>"}
"""


def default_zoom(cfg):
    return cfg.get("framing", {}).get("zoom", 1.0)


def build_scaffold(cfg, work):
    tdir = work / "transcripts"
    manifest = json.loads((work / "manifest.json").read_text())
    segs = []
    for clip in manifest["clips"]:
        stem = Path(clip["name"]).stem
        tf = tdir / f"{stem}.json"
        rec = json.loads(tf.read_text()) if tf.exists() else {"segments": [], "face_cx": 0.5}
        text = " ".join(s["text"].strip() for s in rec.get("segments", []))
        segs.append({
            "src": clip["name"], "in": 0.0, "out": clip["duration"],
            "chapter": "", "face_cx": rec.get("face_cx"),
            "transcript": text,
        })
    return {"slug": cfg["project"]["slug"], "title": cfg["project"]["title"],
            "notes": "SCAFFOLD — one full clip per row. Trim in/out, drop repeated takes, "
                     "set chapter labels, reorder. Then run 03_build.py.",
            "segments": segs}


def auto_cut(cfg, work):
    raw = (work / "raw_transcript.md").read_text()
    reply = vlib._vertex_post(
        [{"text": RUBRIC + "\n\nTRANSCRIPT:\n" + raw}],
        max_tokens=16384,
        model=cfg.get("audio", {}).get("cutter_model", "gemini-2.5-pro"),
    )
    edl = vlib._extract_json(reply)
    # validate + backfill face_cx from transcripts
    manifest = json.loads((work / "manifest.json").read_text())
    dur = {c["name"]: c["duration"] for c in manifest["clips"]}
    faces = {}
    for tf in (work / "transcripts").glob("*.json"):
        r = json.loads(tf.read_text()); faces[r["clip"]] = r.get("face_cx")
    clean = []
    for s in edl.get("segments", []):
        if s["src"] not in dur:
            print(f"  ⚠ dropping segment with unknown clip {s['src']}")
            continue
        s["in"] = max(0.0, float(s["in"]))
        s["out"] = min(dur[s["src"]], float(s["out"]))
        if s["out"] - s["in"] < 0.5:
            print(f"  ⚠ dropping too-short segment {s['src']} {s['in']}–{s['out']}")
            continue
        s.setdefault("face_cx", faces.get(s["src"]))
        clean.append(s)
    edl["segments"] = clean
    edl["slug"] = cfg["project"]["slug"]
    edl["title"] = cfg["project"]["title"]
    return edl


def main():
    vlib.load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--auto", action="store_true", help="LLM-driven cut (headless)")
    args = ap.parse_args()
    import yaml
    cfg = yaml.safe_load((HERE / args.config).read_text())
    work = (HERE / cfg["paths"]["work_dir"]).resolve()

    if args.auto:
        edl = auto_cut(cfg, work)
        out = work / "edl.auto.json"
        kept = sum(s["out"] - s["in"] for s in edl["segments"])
        print(f"AUTO cut: {len(edl['segments'])} segments, {kept:.0f}s kept")
    else:
        edl = build_scaffold(cfg, work)
        out = work / "edl.draft.json"
        print(f"SCAFFOLD: {len(edl['segments'])} segments (full clips). Edit this down.")
    out.write_text(json.dumps(edl, indent=2))
    print(f"✓ wrote {out}")


if __name__ == "__main__":
    main()
