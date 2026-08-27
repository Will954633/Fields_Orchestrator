#!/usr/bin/env python3
"""
assemble_valuation_reel.py — Fields "What the comps say" valuation reel.
15s vertical (1080x1920, 30fps), no presenter/camera: Ken-Burns motion on the real
159 Easthill Drive aerial + animated data plates + burned-in captions + soft chimes.

Scenes (outcome-first):
  0.0-3.3   HOOK    hero photo, slow push-in — "This Robina home SOLD $76,000 above its guide"
  3.3-7.2   COMPS   dark plate — subject + 3 real same-street Easthill sold comps stagger in
  7.2-10.7  PROOF   dark plate — "230 Robina house sales analysed" + two adjustment chips
 10.7-13.5  OFFER   hero photo — "What do the comps say about YOUR home?" + address field
 13.5-15.0  ENDCARD green plate — "See your comps" · fieldsestate.com.au · Smarter with data

Verified facts: 159 Easthill Drive sold $1,425,000 vs guide $1,349,000 (=+$76,000, 2026-04-07);
comps 142/286/62 Easthill Dr; 230 Robina house sales trailing 12 months. Adjustment figures
(-$45k/-$70k) are illustrative of the method. Landing page /analyse-your-home is address-only
and shows the methodology+confidence disclaimer.

Re-run: python3 assemble_valuation_reel.py
"""
import subprocess, tempfile, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE / "renders"
HERO = R / "hero.jpg"
OUT = R / "easthill_valuation_reel.mp4"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
W, H, FPS = 1080, 1920, 30

FOREST = "0x102A1C"     # dark green ground
GREEN  = "0x2E7D3A"     # brand green
AMBER  = "0xB9812F"     # the $ figure
MINT   = "0x9BE0A4"     # light green accent
RED    = "0xB23A2E"     # SOLD stamp

tmp = Path(tempfile.mkdtemp())
def tf(text):
    p = tmp / (str(abs(hash(text))) + ".txt"); p.write_text(text); return str(p)

def draw(ov, prev="base"):
    """ov: list of (text,size,color,box,x,y,t0,t1,font)"""
    out = []
    for i, (text, size, fc, box, x, y, t0, t1, font) in enumerate(ov):
        lbl = f"d{i}" if i < len(ov) - 1 else "vout"
        out.append(f"[{prev}]drawtext=fontfile={font}:textfile={tf(text)}:fontsize={size}:"
                   f"fontcolor={fc}:box=1:boxcolor={box}:boxborderw=22:x={x}:y={y}:"
                   f"line_spacing=12:enable='between(t,{t0},{t1})'[{lbl}]")
        prev = lbl
    return out

CTR = "(w-tw)/2"

def render_hero(dur, ov, out, z0=1.0, z1=1.14):
    # Ken-Burns push-in on the still
    per = (z1 - z0) / (dur * FPS)
    base = (f"[0:v]scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
            f"zoompan=z='min({z0}+{per:.6f}*on,{z1})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p[base]")
    fc = ";".join([base] + draw(ov))
    cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS),
           "-t", str(dur), "-i", str(HERO), "-filter_complex", fc,
           "-map", "[vout]", "-t", str(dur), "-r", str(FPS),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20", str(out)]
    subprocess.run(cmd, check=True)

def render_plate(dur, ov, out, color=FOREST):
    base = f"[0:v]format=yuv420p[base]"
    fc = ";".join([base] + draw(ov))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
           "-i", f"color=c={color}:s={W}x{H}:r={FPS}:d={dur}",
           "-filter_complex", fc, "-map", "[vout]", "-t", str(dur), "-r", str(FPS),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20", str(out)]
    subprocess.run(cmd, check=True)

# ---------------- SCENE 1 · HOOK (3.3s) ----------------
s1 = [
    ("SOLD", 56, "white", RED + "@0.95", "70", 250, 0.25, 3.3, FONT),
    ("THIS ROBINA HOME SOLD", 60, "white", "black@0.5", CTR, 430, 0.15, 3.3, SERIF),
    ("$76,000", 155, "white", AMBER + "@0.95", CTR, 560, 0.55, 3.3, FONT),
    ("ABOVE ITS GUIDE", 68, "white", "black@0.5", CTR, 790, 0.8, 3.3, SERIF),
    ("159 Easthill Drive, Robina", 40, "white", "black@0.55", CTR, 1620, 0.15, 3.3, FONT),
]
# ---------------- SCENE 2 · COMPS (3.9s) ----------------
s2 = [
    ("THE COMPARABLE SALES", 58, "white", GREEN + "@0.95", CTR, 250, 0.0, 3.9, FONT),
    ("159 Easthill Dr    $1,425,000   SOLD", 44, "white", GREEN + "@0.9", CTR, 540, 0.3, 3.9, FONT),
    ("142 Easthill Dr    $1,500,000", 42, "white", "black@0.5", CTR, 720, 0.8, 3.9, FONT),
    ("286 Easthill Dr    $1,250,000", 42, "white", "black@0.5", CTR, 900, 1.3, 3.9, FONT),
    ("62 Easthill Dr    $1,055,000", 42, "white", "black@0.5", CTR, 1080, 1.8, 3.9, FONT),
    ("The comparable sales suggested stronger value.", 40, "white", "black@0.55", CTR, 1600, 0.3, 3.9, FONT),
]
# ---------------- SCENE 3 · PROOF (3.5s) ----------------
s3 = [
    ("230", 168, "white", GREEN + "@0.95", CTR, 360, 0.0, 3.5, FONT),
    ("ROBINA HOUSE SALES ANALYSED", 44, "white", "black@0.5", CTR, 620, 0.25, 3.5, FONT),
    ("last 12 months", 40, MINT, "black@0.4", CTR, 720, 0.25, 3.5, FONT),
    ("Larger home       - $45,000", 46, "0xF2C572", "black@0.5", CTR, 920, 0.7, 3.5, FONT),
    ("Renovated         - $70,000", 46, "0xF2C572", "black@0.5", CTR, 1040, 1.1, 3.5, FONT),
    ("Adjusted for size, condition and land.", 40, "white", "black@0.55", CTR, 1600, 0.25, 3.5, FONT),
]
# ---------------- SCENE 4 · OFFER (2.8s) ----------------
s4 = [
    ("What do the comps say", 58, "white", "black@0.55", CTR, 440, 0.0, 2.8, SERIF),
    ("about YOUR home?", 58, "white", "black@0.55", CTR, 560, 0.0, 2.8, SERIF),
    ("12 Your Street, Robina", 46, "white", "black@0.6", CTR, 780, 0.35, 2.8, FONT),
    ("PRIVATE  -  No email  -  No sales call", 40, MINT, "black@0.5", CTR, 920, 0.6, 2.8, FONT),
    ("Enter your address - we build your comps live.", 38, "white", "black@0.55", CTR, 1600, 0.0, 2.8, FONT),
]
# ---------------- SCENE 5 · END CARD (1.5s) ----------------
s5 = [
    ("SEE YOUR COMPS", 72, "white", GREEN + "@0.97", CTR, 740, 0.1, 1.5, FONT),
    ("fieldsestate.com.au", 56, "white", "black@0.0", CTR, 960, 0.25, 1.5, FONT),
    ("Smarter with data.", 44, MINT, "black@0.0", CTR, 1060, 0.35, 1.5, FONT),
]

clips = []
print("· scene 1 hook");   render_hero(3.3, s1, R/"c1.mp4", 1.0, 1.14); clips.append(R/"c1.mp4")
print("· scene 2 comps");  render_plate(3.9, s2, R/"c2.mp4");           clips.append(R/"c2.mp4")
print("· scene 3 proof");  render_plate(3.5, s3, R/"c3.mp4");           clips.append(R/"c3.mp4")
print("· scene 4 offer");  render_hero(2.8, s4, R/"c4.mp4", 1.08, 1.16);clips.append(R/"c4.mp4")
print("· scene 5 endcard");render_plate(1.5, s5, R/"c5.mp4", GREEN if False else FOREST); clips.append(R/"c5.mp4")

# concat (identical params -> stream copy)
lst = R / "concat.txt"
lst.write_text("".join(f"file '{c}'\n" for c in clips))
silent = R / "silent.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                "-i", str(lst), "-c", "copy", str(silent)], check=True)

# ---------------- AUDIO: soft air bed + chimes ----------------
def chime(freq):
    e = f"0.15*exp(-11*t)*sin(2*PI*{freq}*t)"
    return f"{e}|{e}"
TING = 2093  # C7
# global times: $76k reveal 0.55; comp rows 3.6/4.1/4.6/5.1; 230 reveal 7.2
CHIME_T = [0.55, 3.6, 4.1, 4.6, 5.1, 7.2]
achains = []
mix = []
for i, t0 in enumerate(CHIME_T):
    achains.append(f"aevalsrc=exprs='{chime(TING)}':s=44100:d=0.7[c{i}]")
    achains.append(f"[c{i}]adelay={int(t0*1000)}:all=1[cd{i}]")
    mix.append(f"[cd{i}]")
# very soft filtered brown-noise "air"
achains.append("anoisesrc=color=brown:amplitude=0.10:d=15[nz]")
achains.append("[nz]lowpass=f=380,volume=0.18[air]")
mix.append("[air]")
achains.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first[aout]")
afc = ";".join(achains)

subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent),
                "-filter_complex", afc, "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", "15", str(OUT)], check=True)

# thumbnail + contact sheet for review
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(OUT), "-ss", "1.4",
                "-frames:v", "1", str(R/"thumb.png")], check=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(OUT),
                "-vf", "select='eq(n\\,20)+eq(n\\,150)+eq(n\\,270)+eq(n\\,360)+eq(n\\,435)',"
                       "scale=360:640,tile=5x1", "-frames:v", "1", str(R/"contact_sheet.png")],
               check=True)
print("\nDONE:", OUT)
print("thumb:", R/"thumb.png", " sheet:", R/"contact_sheet.png")
