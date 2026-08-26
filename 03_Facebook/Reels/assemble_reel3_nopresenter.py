#!/usr/bin/env python3
"""
assemble_reel3_nopresenter.py — Reel Three, no presenter. Same script / timings /
on-screen text as the presenter cut, but b-roll instead of a face:
  0.00-3.35  aerial Gold Coast home  (hook)
  3.35-9.25  green data plate        (the $200,000 gap + the challenge)
  9.25-10.0  aerial home             (CTA)
The Australian voice from the presenter take is reused as an OFF-CAMERA VO, so the
overlay timings still line up. Output 1080x1920 H.264.
Re-run: python3 assemble_reel3_nopresenter.py
"""
import subprocess, tempfile
from pathlib import Path

BASE = Path("/home/fields/Fields_Orchestrator/03_Facebook/Reels/renders")
AERIAL = BASE / "reel3_aerial_hook_alt.mp4"
PLATE = BASE / "reel3_data_plate.mp4"
VOICE = BASE / "reel3_presenter_v2.mp4"      # audio source (her AU VO)
OUT = BASE / "reel3_nopresenter_draft.mp4"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTSERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
FOREST, TERRA = "0x1E3A2F", "0xC05A38"

tmp = Path(tempfile.mkdtemp())
def tf(name, text):
    p = tmp / name; p.write_text(text); return str(p)

# text overlays (name, text, size, color, box, x, y, t0, t1, font)
OV = [
    ("h1", "SAME HOME", 100, "white", "black@0.5", "(w-tw)/2", 210, 0.15, 3.35, FONTSERIF),
    ("h2", "$1.31M     $1.54M     $1.76M", 60, "white", "black@0.5", "(w-tw)/2", 380, 0.9, 3.35, FONT),
    ("n1", "OVER  $200,000", 100, "white", TERRA + "@0.9", "(w-tw)/2", 820, 3.5, 7.5, FONT),
    ("n2", "Typical gap  ·  Fields analysis of 512 homes", 36, "white", "black@0.55", "(w-tw)/2", 995, 3.6, 7.5, FONT),
    ("c1", "CAN YOUR ESTIMATE", 86, "white", "black@0.5", "(w-tw)/2", 780, 7.6, 9.25, FONTSERIF),
    ("c2", "BE TRUSTED?", 86, "0xE8A075", "black@0.5", "(w-tw)/2", 900, 7.6, 9.25, FONTSERIF),
    ("d1", "TEST MY HOME'S", 78, "white", "black@0.55", "(w-tw)/2", 720, 9.25, 10.1, FONTSERIF),
    ("d1b", "ESTIMATE", 78, "white", "black@0.55", "(w-tw)/2", 830, 9.25, 10.1, FONTSERIF),
    ("d2", "Get Started", 58, "white", FOREST + "@0.95", "(w-tw)/2", 970, 9.25, 10.1, FONT),
    ("cap1", "Three sites. Three very different values.", 42, "white", "black@0.5", "(w-tw)/2", 1520, 0.15, 3.35, FONT),
    ("cap2", "In our test, the typical gap was over $200,000.", 40, "white", "black@0.5", "(w-tw)/2", 1520, 3.5, 7.5, FONT),
    ("cap3", "Can your estimate be trusted?", 42, "white", "black@0.5", "(w-tw)/2", 1520, 7.6, 9.25, FONT),
]

def norm(label):
    return (f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,fps=30,setsar=1,format=yuv420p{label}")

parts = [
    f"[0:v]split=2[a0][a1]",
    f"[a0]{norm('')},trim=0:3.35,setpts=PTS-STARTPTS[segA]",
    f"[1:v]{norm('')},trim=0:5.90,setpts=PTS-STARTPTS[segB]",
    f"[a1]{norm('')},trim=3.35:4.10,setpts=PTS-STARTPTS[segC]",
    f"[segA][segB][segC]concat=n=3:v=1:a=0[base]",
]
draw = []
prev = "base"
for i, (name, text, size, fc, box, x, y, t0, t1, font) in enumerate(OV):
    path = tf(name + ".txt", text)
    outlbl = f"v{i}" if i < len(OV) - 1 else "vout"
    draw.append(f"[{prev}]drawtext=fontfile={font}:textfile={path}:fontsize={size}:"
                f"fontcolor={fc}:box=1:boxcolor={box}:boxborderw=24:x={x}:y={y}:"
                f"enable='between(t,{t0},{t1})'[{outlbl}]")
    prev = outlbl
filter_complex = ";".join(parts + draw)

cmd = ["ffmpeg", "-v", "error", "-y",
       "-i", str(AERIAL), "-i", str(PLATE), "-i", str(VOICE),
       "-filter_complex", filter_complex,
       "-map", "[vout]", "-map", "2:a",
       "-t", "10",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
       "-c:a", "aac", "-b:a", "160k", str(OUT)]
print("rendering", OUT, "...")
subprocess.run(cmd, check=True)
print("done:", OUT)
