#!/usr/bin/env python3
"""
assemble_reel3_basic.py — the BASIC Reel Three: a single STATIC photo of an
average Robina house (no camera movement — one frozen frame held the whole time),
two lines of text that match the Australian narrator word-for-word, plus captions
and a minimal CTA. Output 1080x1920 H.264.

Narration (basic_vo_src.mp4):  "Same house, three different values." (0-3s)
                               "In our test, the typical gap was over $200,000." (4-8.5s)
Re-run: python3 assemble_reel3_basic.py
"""
import subprocess, tempfile
from pathlib import Path

BASE = Path("/home/fields/Fields_Orchestrator/03_Facebook/Reels/renders")
PHOTO = BASE / "robina_house.png"          # static, no movement
VOICE = BASE / "basic_vo4_src.mp4"         # AU VO, 4 lines ("over $215,000")
OUT = BASE / "reel3_basic_draft.mp4"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTSERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
FOREST, TERRA = "0x1E3A2F", "0xC05A38"
DUR = 11.0

tmp = Path(tempfile.mkdtemp())
def tf(name, text):
    p = tmp / name; p.write_text(text); return str(p)

# (name, text, size, color, box, x, y, t0, t1, font)
OV = [
    # HOOK 0.0-2.4  "Same house, three different values."
    ("h1", "SAME HOUSE", 100, "white", "black@0.5", "(w-tw)/2", 150, 0.0, 2.4, FONTSERIF),
    # three figures appear one-by-one (each with a charm chime at 0.5 / 1.0 / 1.5s)
    ("p1", "$1.31M", 62, "white", TERRA + "@0.9", "90", 320, 0.5, 2.4, FONT),
    ("p2", "$1.54M", 62, "white", TERRA + "@0.9", "(w-tw)/2", 320, 1.0, 2.4, FONT),
    ("p3", "$1.76M", 62, "white", TERRA + "@0.9", "w-tw-90", 320, 1.5, 2.4, FONT),
    ("cap1", "Same house, three different values.", 44, "white", "black@0.55", "(w-tw)/2", 1520, 0.0, 2.4, FONT),
    # THE FACT 2.5-6.6  "In our test, the typical gap was over $215,000."
    ("n1", "OVER  $215,000", 100, "white", TERRA + "@0.92", "(w-tw)/2", 720, 2.5, 6.6, FONT),
    ("n2", "Typical gap  ·  Fields analysis of 512 homes", 36, "white", "black@0.6", "(w-tw)/2", 890, 2.6, 6.6, FONT),
    ("cap2", "In our test, the typical gap was over $215,000.", 40, "white", "black@0.55", "(w-tw)/2", 1520, 2.5, 6.6, FONT),
    # CHALLENGE 6.7-8.95  display "CAN YOUR ESTIMATE BE TRUSTED?" / speaker "We built a quick way to find out."
    ("c1", "CAN YOUR ESTIMATE", 84, "white", "black@0.55", "(w-tw)/2", 700, 6.7, 8.95, FONTSERIF),
    ("c2", "BE TRUSTED?", 84, "0xE8A075", "black@0.55", "(w-tw)/2", 815, 6.7, 8.95, FONTSERIF),
    ("cap3", "We built a quick way to find out.", 42, "white", "black@0.55", "(w-tw)/2", 1520, 6.7, 8.95, FONT),
    # CTA / end card 9.0-11.0  (button)
    ("d1", "TEST MY HOME'S", 76, "white", "black@0.55", "(w-tw)/2", 690, 9.0, 11.0, FONTSERIF),
    ("d1b", "VALUATION", 76, "white", "black@0.55", "(w-tw)/2", 800, 9.0, 11.0, FONTSERIF),
    ("d2", "Get Started", 60, "white", FOREST + "@0.97", "(w-tw)/2", 950, 9.15, 11.0, FONT),
]

filters = ["[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p[base]"]
prev = "base"
draw = []
for i, (name, text, size, fc, box, x, y, t0, t1, font) in enumerate(OV):
    path = tf(name + ".txt", text)
    out = f"v{i}" if i < len(OV) - 1 else "vout"
    draw.append(f"[{prev}]drawtext=fontfile={font}:textfile={path}:fontsize={size}:fontcolor={fc}:"
                f"box=1:boxcolor={box}:boxborderw=24:x={x}:y={y}:enable='between(t,{t0},{t1})'[{out}]")
    prev = out
# --- audio: VO + three soft ascending "charm" chimes at each figure's entrance ---
def chime(freq):
    # bell = fundamental + soft octave, fast attack, exponential decay (~0.8s)
    e = f"0.26*exp(-6*t)*sin(2*PI*{freq}*t)+0.09*exp(-10*t)*sin(2*PI*{2*freq}*t)"
    return f"{e}|{e}"   # stereo
CHIMES = [(1047, 500), (1319, 1000), (1568, 1500)]   # C6/E6/G6 ascending @ 0.5/1.0/1.5s
achains, mixins = [], ["[voa]"]
for i, (freq, delay_ms) in enumerate(CHIMES):
    achains.append(f"aevalsrc=exprs='{chime(freq)}':s=44100:d=0.8[cs{i}]")
    achains.append(f"[cs{i}]adelay={delay_ms}:all=1[cd{i}]")
    mixins.append(f"[cd{i}]")
achains.append("[1:a]aformat=sample_rates=44100:channel_layouts=stereo[voa]")
achains.append("".join(mixins) + "amix=inputs=4:normalize=0:duration=first[aout]")

filter_complex = ";".join(filters + draw + achains)

cmd = ["ffmpeg", "-v", "error", "-y",
       "-loop", "1", "-i", str(PHOTO),      # static photo, held
       "-i", str(VOICE),
       "-filter_complex", filter_complex,
       "-map", "[vout]", "-map", "[aout]",
       "-t", str(DUR),
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-preset", "medium", "-crf", "20",
       "-c:a", "aac", "-b:a", "160k", str(OUT)]
print("rendering", OUT, "...")
subprocess.run(cmd, check=True)
print("done:", OUT)
