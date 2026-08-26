#!/usr/bin/env python3
"""
assemble_reel3.py — composite the Reel Three draft: full-frame Australian
presenter (reel3_presenter_v2.mp4) + timed on-screen text, the $200,000 gap,
and muted-first captions, matched to her actual spoken timings (from Gemini
transcription). Outputs 1080x1920 H.264 with her original audio.

Full-frame composition (pragmatic: omni gives a single ~10s take, so we overlay
rather than cut to a separate data plate). Bookend can come later with a matched
data-plate + VO. Re-run after regenerating the take: python3 assemble_reel3.py
"""
import subprocess, tempfile, os
from pathlib import Path

BASE = Path("/home/fields/Fields_Orchestrator/03_Facebook/Reels/renders")
SRC = BASE / "reel3_presenter_v2.mp4"
OUT = BASE / "reel3_draft.mp4"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTSERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

FOREST = "0x1E3A2F"
TERRA = "0xC05A38"

tmp = Path(tempfile.mkdtemp())
def tf(name, text):
    p = tmp / name
    p.write_text(text)
    return str(p)

# (textfile, fontsize, color, box color+alpha, x-expr, y, t_start, t_end, font)
OV = [
    # HOOK 0.15-3.3
    ("h1", "SAME HOME", 96, "white", "black@0.55", "(w-tw)/2", 170, 0.15, 3.35, FONTSERIF),
    ("h2", "$1.31M     $1.54M     $1.76M", 58, "white", "black@0.45", "(w-tw)/2", 330, 0.9, 3.35, FONT),
    # NUMBER 3.5-7.5
    ("n1", "OVER  $200,000", 100, "white", TERRA + "@0.9", "(w-tw)/2", 790, 3.5, 7.5, FONT),
    ("n2", "Typical gap  ·  Fields analysis of 512 homes", 36, "white", "black@0.55", "(w-tw)/2", 950, 3.6, 7.5, FONT),
    # CHALLENGE 7.6-9.2
    ("c1", "CAN YOUR ESTIMATE", 84, "white", "black@0.55", "(w-tw)/2", 720, 7.6, 9.25, FONTSERIF),
    ("c2", "BE TRUSTED?", 84, TERRA, "black@0.55", "(w-tw)/2", 840, 7.6, 9.25, FONTSERIF),
    # CTA 9.2-10.0
    ("d1", "TEST MY HOME'S", 78, "white", "black@0.55", "(w-tw)/2", 690, 9.25, 10.1, FONTSERIF),
    ("d1b", "ESTIMATE", 78, "white", "black@0.55", "(w-tw)/2", 800, 9.25, 10.1, FONTSERIF),
    ("d2", "Get Started", 58, "white", FOREST + "@0.95", "(w-tw)/2", 940, 9.25, 10.1, FONT),
    # CAPTIONS (muted-first), bottom safe zone
    ("cap1", "Three sites. Three very different values.", 42, "white", "black@0.5", "(w-tw)/2", 1500, 0.15, 3.35, FONT),
    ("cap2", "In our test, the typical gap was over $200,000.", 40, "white", "black@0.5", "(w-tw)/2", 1500, 3.5, 7.5, FONT),
    ("cap3", "Can your estimate be trusted?", 42, "white", "black@0.5", "(w-tw)/2", 1500, 7.6, 9.25, FONT),
]

filters = ["scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"]
for i, (name, text, size, fc, box, x, y, t0, t1, font) in enumerate(OV):
    path = tf(name + ".txt", text)
    filters.append(
        f"drawtext=fontfile={font}:textfile={path}:fontsize={size}:fontcolor={fc}:"
        f"box=1:boxcolor={box}:boxborderw=24:x={x}:y={y}:"
        f"enable='between(t,{t0},{t1})'"
    )
vf = ",".join(filters)

cmd = [
    "ffmpeg", "-v", "error", "-y", "-i", str(SRC),
    "-t", "10",
    "-vf", vf,
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
    "-c:a", "aac", "-b:a", "160k",
    str(OUT),
]
print("rendering", OUT, "...")
subprocess.run(cmd, check=True)
print("done:", OUT)
