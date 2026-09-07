#!/usr/bin/env python3
"""
Stage 03 — THE RENDER ENGINE.  EDL + config → every deliverable.

Deterministic: same EDL + same config + same raw = byte-comparable output. All the
creative judgement lives in the EDL; this script only executes it.

Per segment:  trim → centre-crop square on face → scale → colour/lighting grade →
              audio highpass + denoise + level  → normalised intermediate
Assemble:     concat (hard cut, stream-copy) or dissolve (xfade/acrossfade)
Master:       1080² square, the source of truth for every derivative
Derivatives:  • 512² web H.264 mp4  (no captions — the embed)   → out/<slug>.mp4
              • 1080 baked circle-on-black HEVC mov, no captions → out/<slug>_circle.mov
              • …+ burned captions                               → out/<slug>_circle_captions.mov
Captions:     re-transcribe the ASSEMBLED master audio (final timeline) → SRT + transcript.md

Usage:  python3 scripts/03_build.py --edl work/edl.json [--config config.yaml]
                                     [--stage all|segments|master|derivatives|captions]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vlib  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
RAW_W, RAW_H = 3840, 2160  # DJI 4K


# ----------------------------------------------------------------------------- config
def D(cfg, *path, default=None):
    cur = cfg
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def crop_geom(face_cx, zoom):
    """Centred square crop of the 4K frame around the face."""
    face_cx = 0.5 if face_cx is None else float(face_cx)
    zoom = max(1.0, float(zoom or 1.0))
    side = min(RAW_H, round(RAW_H / zoom))
    x = round(face_cx * RAW_W - side / 2)
    x = max(0, min(RAW_W - side, x))
    y = max(0, min(RAW_H - side, round((RAW_H - side) / 2)))
    return side, x, y


def grade_vf(cfg, seg, master):
    look = {**D(cfg, "look", default={}), **(seg.get("look") or {})}
    side, x, y = crop_geom(seg.get("face_cx"), seg.get("zoom", D(cfg, "framing", "zoom", default=1.0)))
    parts = [
        f"crop={side}:{side}:{x}:{y}",
        f"scale={master}:{master}:flags=lanczos",
        (f"eq=brightness={look.get('brightness',0.03)}:contrast={look.get('contrast',1.06)}"
         f":saturation={look.get('saturation',1.08)}:gamma={look.get('gamma',1.02)}"),
    ]
    warmth = look.get("warmth", 6)
    if warmth:
        parts.append(f"colorbalance=rm={warmth/100:.3f}:bm={-warmth/100:.3f}")
    sharp = look.get("sharpen", 0.6)
    if sharp:
        parts.append(f"unsharp=5:5:{sharp}:5:5:0.0")
    parts += [f"fps={D(cfg,'assembly','fps',default=30)}", "format=yuv420p", "setsar=1"]
    return ",".join(parts)


def grade_af(cfg):
    a = D(cfg, "audio", default={})
    chain = [f"highpass=f={a.get('highpass_hz',80)}"]
    dn = a.get("denoise", "afftdn")
    if dn == "afftdn":
        chain.append(f"afftdn=nf={a.get('denoise_nf',-25)}")
    elif dn == "anlmdn":
        chain.append("anlmdn")
    chain.append("dynaudnorm=f=200:g=5")  # gentle per-segment leveling; final loudnorm later
    return ",".join(chain)


# ----------------------------------------------------------------------------- stages
def snap_segment(cfg, work, seg, src):
    """Move this segment's in/out onto silence so no word is clipped and joins land on a
    breath (config assembly.snap_to_silence, default on). Returns (in, out, report)."""
    if not D(cfg, "assembly", "snap_to_silence", default=True):
        return float(seg["in"]), float(seg["out"]), None
    stem = Path(seg["src"]).stem
    sil = vlib.detect_silences(
        str(src), cache_json=str(work / f"_sil_{stem}.json"),
        noise_db=D(cfg, "assembly", "snap_noise_db", default=-38.0),
        min_silence=D(cfg, "assembly", "snap_min_silence", default=0.12),
    )
    in0, out0 = float(seg["in"]), float(seg["out"])
    new_in, rin = vlib.snap_in(sil, in0,
                               preroll=D(cfg, "assembly", "snap_preroll", default=0.18),
                               max_extend=D(cfg, "assembly", "snap_max_extend", default=3.0))
    new_out, rout = vlib.snap_out(sil, out0,
                                  tail_pad=D(cfg, "assembly", "snap_tail_pad", default=0.22),
                                  max_extend=D(cfg, "assembly", "snap_max_extend", default=3.0))
    # clamp to the clip's real duration (some EDL out-points overshoot the clip) and
    # never invert
    clip_dur = vlib.probe_summary(str(src))["duration"]
    new_out = min(new_out, clip_dur - 0.02)
    new_in = max(0.0, min(new_in, new_out - 0.3))
    report = {"src": seg["src"], "in": [round(in0, 2), round(new_in, 2), rin],
              "out": [round(out0, 2), round(new_out, 2), rout]}
    return new_in, new_out, report


def render_segments(cfg, edl, work):
    master = D(cfg, "framing", "master_square", default=1080)
    fps = D(cfg, "assembly", "fps", default=30)
    raw_dir = (HERE / cfg["paths"]["raw_dir"]).resolve()
    segs = [s for s in edl["segments"] if not s.get("drop")]
    paths, boundaries = [], []
    for i, seg in enumerate(segs):
        src = raw_dir / seg["src"]
        in_t, out_t, rep = snap_segment(cfg, work, seg, src)
        if rep:
            boundaries.append({"seg": i, **rep})
            if "WARN" in rep["out"][2] or "WARN" in rep["in"][2]:
                print(f"    ⚠ seg {i:03d} {rep}")
        seg = {**seg, "in": in_t, "out": out_t}
        dur = round(float(seg["out"]) - float(seg["in"]), 3)
        outp = work / f"seg_{i:03d}.mp4"
        vf, af = grade_vf(cfg, seg, master), grade_af(cfg)
        print(f"  seg {i:03d}  {seg['src']}  {seg['in']:.2f}→{seg['out']:.2f} ({dur:.1f}s) "
              f"cx={seg.get('face_cx')}  {seg.get('chapter','')}")
        threads = os.environ.get("WALK_FFMPEG_THREADS", "")
        tflag = ["-threads", threads] if threads else []
        vlib.run([
            "ffmpeg", "-v", "error", "-y", *tflag,
            "-ss", str(seg["in"]), "-i", str(src), "-t", str(dur),
            "-vf", vf, "-af", af,
            "-r", str(fps), "-ar", "48000", "-ac", "2", *tflag,
            # These are INTERMEDIATES (re-encoded into the finals), and 4K decode on a
            # shared VM is the bottleneck — veryfast/crf16 keeps them visually lossless
            # while roughly halving wall-clock vs preset medium.
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
            "-pix_fmt", "yuv420p", "-g", str(fps * 2), "-keyint_min", str(fps),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(outp),
        ])
        paths.append(outp)
    (work / "seg_list.json").write_text(json.dumps([str(p) for p in paths], indent=2))
    (work / "boundaries.json").write_text(json.dumps(boundaries, indent=2))
    if boundaries:
        adj = sum(1 for b in boundaries if b["in"][0] != b["in"][1] or b["out"][0] != b["out"][1])
        print(f"  ✓ {len(paths)} segments rendered · snapped {adj}/{len(boundaries)} boundaries to silence")
    else:
        print(f"  ✓ {len(paths)} segments rendered")
    return paths


def assemble_master(cfg, work):
    paths = [Path(p) for p in json.loads((work / "seg_list.json").read_text())]
    # Guard: a segment pass that was OOM-killed mid-write leaves a 0-byte/unreadable
    # intermediate; concat would silently inherit the corruption. Fail loud instead
    # (CLAUDE.md 7b — assert the outcome, don't just avoid throwing).
    for p in paths:
        if not p.exists() or p.stat().st_size < 1024:
            raise RuntimeError(f"segment missing/too small: {p} — re-render (delete it first)")
        try:
            d = vlib.probe_summary(str(p))["duration"]
        except Exception as e:
            raise RuntimeError(f"segment unreadable/corrupt: {p} ({e}) — delete and re-render")
        if not d or d < 0.1:
            raise RuntimeError(f"segment has no duration: {p} — delete and re-render")
    master_mp4 = work / "master_square.mp4"
    trans = D(cfg, "assembly", "transition", default="cut")
    if trans == "cut" or len(paths) == 1:
        listf = work / "concat_list.txt"
        listf.write_text("".join(f"file '{p}'\n" for p in paths))
        vlib.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                  "-i", str(listf), "-c", "copy", "-movflags", "+faststart", str(master_mp4)])
    else:  # dissolve: xfade/acrossfade chain
        d = float(D(cfg, "assembly", "dissolve_sec", default=0.2))
        durs = [vlib.probe_summary(str(p))["duration"] for p in paths]
        inputs = []
        for p in paths:
            inputs += ["-i", str(p)]
        vf, af, off = "", "", 0.0
        vlab, alab = "[0:v]", "[0:a]"
        for i in range(1, len(paths)):
            off += durs[i - 1] - d
            nv, na = f"[v{i}]", f"[a{i}]"
            vf += f"{vlab}[{i}:v]xfade=transition=fade:duration={d}:offset={off:.3f}{nv};"
            af += f"{alab}[{i}:a]acrossfade=d={d}{na};"
            vlab, alab = nv, na
        fc = vf + af
        vlib.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fc.rstrip(";"),
                  "-map", vlab, "-map", alab, "-c:v", "libx264", "-preset", "medium",
                  "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                  "-movflags", "+faststart", str(master_mp4)])
    dur = vlib.probe_summary(str(master_mp4))["duration"]
    print(f"  ✓ master_square.mp4  ({dur:.1f}s, {trans})")
    return master_mp4


def caption_pass(cfg, work, out):
    """Transcribe the assembled master → SRT + timecoded transcript.md."""
    master = work / "master_square.mp4"
    mp3 = work / "_asr_master.mp3"
    vlib.extract_audio_for_asr(str(master), str(mp3))
    segs = vlib.transcribe_audio(str(mp3))
    mp3.unlink(missing_ok=True)
    slug = cfg["project"]["slug"]
    srt = out / f"{slug}.srt"
    vlib.segments_to_srt(segs, str(srt))
    # ASS (with explicit PlayRes) is what we BURN; the SRT is kept for reuse/YouTube.
    cap = D(cfg, "captions", default={})
    ass = out / f"{slug}.ass"
    vlib.segments_to_ass(
        segs, str(ass),
        font=cap.get("font", "DejaVu Sans"), fontsize=cap.get("fontsize", 54),
        primary=cap.get("primary_colour", "&H00FFFFFF"),
        outline_col=cap.get("outline_colour", "&H00000000"),
        outline=cap.get("outline", 3), margin_v=cap.get("margin_v", 90),
    )
    md = out / f"{slug}_transcript.md"
    vlib.segments_to_transcript_md(segs, str(md), cfg["project"]["title"])
    print(f"  ✓ {srt.name} + {ass.name} + {md.name}  ({len(segs)} caption cues)")
    return srt


def loudnorm_af(cfg):
    a = D(cfg, "audio", default={})
    return f"loudnorm=I={a.get('target_lufs',-16.0)}:TP={a.get('target_tp',-1.5)}:LRA=11"


def render_derivatives(cfg, work, out, srt):
    master = work / "master_square.mp4"
    slug = cfg["project"]["slug"]
    msz = D(cfg, "framing", "master_square", default=1080)
    ln = loudnorm_af(cfg)
    outputs = {}

    # (a) 512² web mp4 — the embed (no captions)
    if D(cfg, "outputs", "web_mp4", default=True):
        web = D(cfg, "framing", "web_square", default=512)
        p = out / f"{slug}.mp4"
        vlib.run(["ffmpeg", "-v", "error", "-y", "-i", str(master),
                  "-vf", f"scale={web}:{web}:flags=lanczos", "-af", ln,
                  "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(p)])
        outputs["web_mp4"] = str(p)
        print(f"  ✓ {p.name}  ({web}×{web} H.264 — the embed)")

    # circle-on-black masters need a mask + geometry
    diam = D(cfg, "framing", "circle_diameter", default=round(msz * 0.76))
    cy = D(cfg, "framing", "circle_cy_frac", default=0.46)
    ox = round((1920 - diam) / 2)
    oy = round(cy * 1080 - diam / 2)
    mask = work / "circle_mask.png"
    vlib.make_circle_mask(str(mask), size=diam, feather=3)

    def circle_filtergraph(with_caps):
        # scale person→diam, mask to circle, overlay on 1920×1080 black; optional captions on top.
        # color= is an INFINITE source, so overlay MUST use shortest=1 or the render never ends.
        g = (f"[0:v]scale={diam}:{diam}:flags=lanczos,format=yuva420p[p];"
             f"[p][1:v]alphamerge[a];"
             f"color=black:s=1920x1080:r={D(cfg,'assembly','fps',default=30)}[bg];"
             f"[bg][a]overlay={ox}:{oy}:shortest=1")
        if with_caps:
            # Burn the ASS (explicit PlayResX/Y → real-pixel font, no libass 288 upscsale).
            ass = str(out / f"{cfg['project']['slug']}.ass")
            g += f"[v];[v]subtitles={ass}"
        return g

    # (b) circle mov, no captions
    if D(cfg, "outputs", "circle_mov_nocaps", default=True):
        p = out / f"{slug}_circle.mov"
        vlib.run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-i", str(mask),
                  "-filter_complex", circle_filtergraph(False),
                  "-map", "0:a", "-af", ln,
                  "-c:v", "libx265", "-preset", "faster", "-crf", "20", "-tag:v", "hvc1",
                  "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(p)])
        outputs["circle_mov_nocaps"] = str(p)
        print(f"  ✓ {p.name}  (1080 baked circle, no captions)")

    # (c) circle mov + captions
    if D(cfg, "outputs", "circle_mov_caps", default=True) and srt:
        p = out / f"{slug}_circle_captions.mov"
        vlib.run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-i", str(mask),
                  "-filter_complex", circle_filtergraph(True),
                  "-map", "0:a", "-af", ln,
                  "-c:v", "libx265", "-preset", "faster", "-crf", "20", "-tag:v", "hvc1",
                  "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(p)])
        outputs["circle_mov_caps"] = str(p)
        print(f"  ✓ {p.name}  (1080 baked circle + captions)")

    return outputs


# ----------------------------------------------------------------------------- main
def main():
    vlib.load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--edl", default="work/edl.json")
    ap.add_argument("--stage", default="all",
                    choices=["all", "segments", "master", "captions", "derivatives"])
    args = ap.parse_args()

    import yaml
    cfg = yaml.safe_load((HERE / args.config).read_text())
    work = (HERE / cfg["paths"]["work_dir"]).resolve(); work.mkdir(parents=True, exist_ok=True)
    out = (HERE / cfg["paths"]["out_dir"]).resolve(); out.mkdir(parents=True, exist_ok=True)
    edl = json.loads((HERE / args.edl).read_text() if not Path(args.edl).is_absolute()
                     else Path(args.edl).read_text())

    if edl.get("slug") and edl["slug"] != cfg["project"]["slug"]:
        print(f"  ⚠ EDL slug '{edl['slug']}' != config slug '{cfg['project']['slug']}'")

    srt = out / f"{cfg['project']['slug']}.srt"
    if args.stage in ("all", "segments"):
        print("▶ segments"); render_segments(cfg, edl, work)
    if args.stage in ("all", "master"):
        print("▶ assemble master"); assemble_master(cfg, work)
    if args.stage in ("all", "captions"):
        print("▶ captions"); srt = caption_pass(cfg, work, out)
    if args.stage in ("all", "derivatives"):
        print("▶ derivatives")
        outputs = render_derivatives(cfg, work, out, srt if srt.exists() else None)
        (out / "outputs.json").write_text(json.dumps(outputs, indent=2))
    print("\n✓ build complete →", out)


if __name__ == "__main__":
    main()
