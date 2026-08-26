#!/usr/bin/env python3
"""
assemble_reel3_news.py — the "breaking news" treatment of the basic Reel Three.
Same static Robina house + Australian VO + figure tings, dressed with broadcast
furniture: a red PROPERTY ALERT top bar, a two-tier lower-third chyron (red kicker
+ headline), a scrolling ticker crawl, a location bug, condensed news type, and a
soft opening alert tone.

COMPLIANCE: branded as a FIELDS Property Alert — NOT a real news outlet (no
broadcaster look-alike), no "LIVE" claim, every stat truthful ("gap", not "error").
Output 1080x1920 H.264. Re-run: python3 assemble_reel3_news.py
"""
import subprocess, tempfile
from pathlib import Path

BASE = Path("/home/fields/Fields_Orchestrator/03_Facebook/Reels/renders")
PHOTO = BASE / "robina_house.png"
VOICE = BASE / "news_vo_src.mp4"   # AU VO; narrator says "Can your estimate be trusted?"
OUT = BASE / "reel3_news_draft.mp4"
NEWS = "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
RED, NAVY, CREAM, FOREST, TERRA = "0xC8102E", "0x0A1B2E", "0xF2EFE6", "0x1E3A2F", "0xC05A38"
DUR = 11.0

# beat windows (matched to news_vo_src timings)
B1, B2, B3, B4 = (0.0, 2.55), (2.7, 7.35), (7.45, 9.2), (9.25, 11.0)

tmp = Path(tempfile.mkdtemp())
def tf(name, text):
    p = tmp / name; p.write_text(text); return str(p)

fc = ["[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p[s0]"]
n = [0]
def add(f):
    prev, cur = f"s{n[0]}", f"s{n[0]+1}"
    fc.append(f"[{prev}]{f}[{cur}]"); n[0] += 1

def box(x, y, w, h, color, enable=None):
    e = f":enable='between(t,{enable[0]},{enable[1]})'" if enable else ""
    add(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={color}:t=fill{e}")

def txt(text, size, color, x, y, font=NEWS, boxcolor=None, bw=18, enable=None, key=None):
    path = tf((key or text[:10]) + f"_{n[0]}.txt", text)
    b = f":box=1:boxcolor={boxcolor}:boxborderw={bw}" if boxcolor else ""
    e = f":enable='between(t,{enable[0]},{enable[1]})'" if enable else ""
    add(f"drawtext=fontfile={font}:textfile={path}:fontsize={size}:fontcolor={color}:x={x}:y={y}{b}{e}")

# ---- persistent furniture ----
# top alert bar
box(0, 0, 1080, 120, RED + "@0.96")
box(40, 47, 30, 30, "white")   # signal dot
txt("PROPERTY ALERT", 54, "white", "92", "34", font=NEWS)
txt("GOLD COAST", 42, "white", "w-tw-34", "40")
# lower-third chyron bands
box(0, 1446, 1080, 74, RED + "@0.96")
box(0, 1520, 1080, 122, CREAM + "@0.97")
# ticker band + red tab
box(0, 1646, 1080, 86, NAVY + "@0.97")
# ticker crawl (scrolls right->left), drawn before the tab so the tab masks its start
TICKER = ("PROPERTY ALERT      SAME HOME VALUED $1.31M, $1.54M AND $1.76M BY THREE SITES      "
          "FIELDS TESTED 512 GOLD COAST HOMES      TYPICAL GAP OVER $215,000      "
          "SEE THE EVIDENCE BEHIND YOUR HOME'S VALUE AT FIELDSESTATE.COM.AU      ")
tpath = tf("ticker.txt", TICKER)
add(f"drawtext=fontfile={NEWS}:textfile={tpath}:fontsize={46}:fontcolor=white:"
    f"y=1666:x=w-mod(t*180\\,w+tw)")
box(0, 1646, 214, 86, RED)
txt("FIELDS", 48, "white", "36", "1666", key="tab")

# ---- beat 1: three valuations ----
txt("SAME HOME", 92, "white", "(w-tw)/2", 430, font=SERIF, boxcolor="black@0.45", enable=B1)
txt("$1.31M", 74, "white", "120", 690, boxcolor=TERRA + "@0.92", enable=(0.5, 2.4), key="p1")
txt("$1.54M", 74, "white", "(w-tw)/2", 690, boxcolor=TERRA + "@0.92", enable=(1.0, 2.4), key="p2")
txt("$1.76M", 74, "white", "w-tw-120", 690, boxcolor=TERRA + "@0.92", enable=(1.5, 2.4), key="p3")

# ---- beat 2: the gap ----
txt("OVER  $215,000", 106, "white", "(w-tw)/2", 720, boxcolor=RED + "@0.94", enable=B2, key="n1")
txt("TYPICAL GAP  ·  512 GOLD COAST HOMES TESTED", 40, "white", "(w-tw)/2", 900, boxcolor=NAVY + "@0.85", enable=B2, key="n2")

# ---- beat 3: the question ----
txt("CAN YOUR ESTIMATE", 76, "white", "(w-tw)/2", 700, font=SERIF, boxcolor="black@0.5", enable=B3, key="c1")
txt("BE TRUSTED?", 76, "0xE8A075", "(w-tw)/2", 800, font=SERIF, boxcolor="black@0.5", enable=B3, key="c2")

# ---- beat 4: CTA ----
txt("TEST MY HOME'S", 74, "white", "(w-tw)/2", 660, font=SERIF, boxcolor="black@0.5", enable=B4, key="d1")
txt("VALUATION", 74, "white", "(w-tw)/2", 768, font=SERIF, boxcolor="black@0.5", enable=B4, key="d1b")
txt("Get Started", 58, "white", "(w-tw)/2", 900, boxcolor=FOREST + "@0.96", enable=B4, key="d2")

# ---- chyron kicker + headline per beat ----
for (kick, head, win, k) in [
    ("SAME HOME · THREE VALUATIONS", "Three websites. Three different values.", B1, "cy1"),
    ("THE HIDDEN GAP", "In our test, the typical gap was over $215,000.", B2, "cy2"),
    ("THE QUESTION", "We built a quick way to find out.", B3, "cy3"),
    ("FIND OUT NOW", "Test your home's valuation — fieldsestate.com.au", B4, "cy4"),
]:
    txt(kick, 46, "white", "36", "1458", enable=win, key=k + "k")
    txt(head, 54, NAVY, "36", "1542", enable=win, key=k + "h")

# rename last video label to vout
fc[-1] = fc[-1].rsplit("[", 1)[0] + "[vout]"

# ---- audio: VO + soft opening alert tone + three gentle tings ----
def ting(freq):
    e = f"0.15*exp(-13*t)*sin(2*PI*{freq}*t)"; return f"{e}|{e}"
def bong(freq):
    e = f"0.16*exp(-6*t)*sin(2*PI*{freq}*t)+0.06*exp(-8*t)*sin(2*PI*{2*freq}*t)"; return f"{e}|{e}"
achains = [
    f"aevalsrc=exprs='{bong(196)}':s=44100:d=1.1[al0]",        # low alert swell @0
    f"aevalsrc=exprs='{ting(2093)}':s=44100:d=0.8[al1]",
    f"aevalsrc=exprs='{ting(2093)}':s=44100:d=0.8[al2]",
    f"aevalsrc=exprs='{ting(2093)}':s=44100:d=0.8[al3]",
    "[al1]adelay=500:all=1[t1]",
    "[al2]adelay=1000:all=1[t2]",
    "[al3]adelay=1500:all=1[t3]",
    "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[voa]",
    "[voa][al0][t1][t2][t3]amix=inputs=5:normalize=0:duration=first[aout]",
]
filter_complex = ";".join(fc + achains)

cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(PHOTO), "-i", str(VOICE),
       "-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]", "-t", str(DUR),
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-preset", "medium", "-crf", "20",
       "-c:a", "aac", "-b:a", "160k", str(OUT)]
print("rendering", OUT, "...")
subprocess.run(cmd, check=True)
print("done:", OUT)
