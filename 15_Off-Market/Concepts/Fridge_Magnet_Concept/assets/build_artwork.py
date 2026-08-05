#!/usr/bin/env python3
"""
build_artwork.py — generates assets/artwork.svg, a child's crayon drawing.

Why generated rather than a photo: it's ~15KB, scales to any door size, and can
be recoloured (the mono variant) from the same source. Drop a real photo in as
assets/artwork.jpg and index.html will use that instead — this is the stand-in.

The whole trick to making it read as a CHILD's drawing rather than a clean
vector illustration is that no line is straight and no stroke is a single pass.
Every stroke here is 2-3 jittered passes with round caps at slightly different
opacities, which is what a crayon or felt-tip actually leaves behind.
"""
import math, random, os

random.seed(11)
W, H = 1040, 740
out = []

def jit(pts, amp=3.0, seg=14):
    """Resample a polyline and push each point off the line a little."""
    dense = []
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        d = math.hypot(x2 - x1, y2 - y1)
        n = max(2, int(d / seg))
        for k in range(n):
            t = k / n
            dense.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    dense.append(pts[-1])
    return [(x + random.uniform(-amp, amp), y + random.uniform(-amp, amp)) for x, y in dense]

def d_of(pts):
    return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

def stroke(pts, color, w=6, passes=3, amp=3.0, op=0.92):
    """A crayon stroke: several jittered passes, not one clean line."""
    for p in range(passes):
        o = op * (1 - p * 0.22)
        out.append(
            f'<path d="{d_of(jit(pts, amp))}" fill="none" stroke="{color}" '
            f'stroke-width="{w - p * 0.6:.1f}" stroke-linecap="round" '
            f'stroke-linejoin="round" opacity="{o:.2f}"/>'
        )

def arc_pts(cx, cy, rx, ry, a0, a1, n=40):
    return [(cx + rx * math.cos(a), cy - ry * math.sin(a))
            for a in (a0 + (a1 - a0) * i / n for i in range(n + 1))]

# ── rainbow ────────────────────────────────────────────────────────────────
# Hatched bands, the way a kid fills an arc: many strokes along the curve, not
# one thick line.
BANDS = [("#e23b २1".replace(" २", "2"), 0), ("#f28c1c", 1), ("#f5d21e", 2),
         ("#1f8f5f", 3), ("#4fa8dd", 4), ("#8e2547", 5), ("#3b2f9e", 6)]
for color, i in BANDS:
    base = 250 - i * 22
    for k in range(16):
        r = base + random.uniform(-7, 7)
        a0 = math.radians(random.uniform(6, 30))
        a1 = math.radians(random.uniform(150, 176))
        pts = arc_pts(560, 330, 400 * (r / 250), r, a0, a1, 26)
        stroke(pts, color, w=7, passes=1, amp=3.5, op=random.uniform(0.55, 0.9))

# ── sun, top right ─────────────────────────────────────────────────────────
for k in range(16):
    a = math.radians(k * 22.5 + random.uniform(-6, 6))
    r0, r1 = 46, random.uniform(96, 132)
    stroke([(900 + r0 * math.cos(a), 108 - r0 * math.sin(a)),
            (900 + r1 * math.cos(a), 108 - r1 * math.sin(a))],
           random.choice(["#e8471f", "#f4a01b"]), w=7, passes=2, amp=2.4)
for k in range(11):
    stroke(arc_pts(900, 108, 40 - k * 2.4, 40 - k * 2.4, 0, 6.28, 22),
           random.choice(["#f4a01b", "#e8471f", "#f5d21e"]), w=6, passes=1, amp=2.6)

# ── rain / sky dashes ──────────────────────────────────────────────────────
for k in range(9):
    x = 320 + k * 62 + random.uniform(-9, 9)
    stroke([(x, 26), (x + random.uniform(-7, 7), 74)], "#5aa9dd", w=9, passes=2, amp=2.4)

# ── scribbles, top left ────────────────────────────────────────────────────
for cx, cy, rr in [(120, 60, 26), (190, 45, 30), (250, 52, 26), (95, 108, 20)]:
    for k in range(7):
        stroke(arc_pts(cx, cy, rr - k * 2.6, (rr - k * 2.6) * 0.7, 0, 6.28, 18),
               "#6c6c74", w=4, passes=1, amp=2.2, op=0.8)

# ── butterfly, left ────────────────────────────────────────────────────────
BW = "#171717"
for sx in (-1, 1):
    wing = [(250, 500), (250 + sx * 58, 452), (250 + sx * 86, 496),
            (250 + sx * 60, 546), (250, 512)]
    stroke(wing + [wing[0]], BW, w=5, passes=2, amp=2.2)
    for k in range(9):
        stroke([(250 + sx * 14, 470 + k * 9), (250 + sx * 74, 466 + k * 9)],
               "#f0a8c8", w=6, passes=1, amp=2.4, op=0.75)
stroke([(250, 452), (250, 548)], BW, w=6, passes=2, amp=1.6)
for sx in (-1, 1):
    stroke([(250, 456), (250 + sx * 26, 386), (250 + sx * 30, 344)], BW, w=4, passes=2, amp=2)
    out.append(f'<circle cx="{250 + sx * 31}" cy="340" r="11" fill="{BW}"/>')

# ── the figure ─────────────────────────────────────────────────────────────
HX, HY = 700, 640          # head centre
stroke(arc_pts(HX, HY, 78, 84, 0, 6.28, 30), "#f28c1c", w=6, passes=2, amp=3)
for k in range(14):        # hair scribble
    a = math.radians(random.uniform(20, 160))
    stroke([(HX + 72 * math.cos(a), HY - 74 * math.sin(a)),
            (HX + 96 * math.cos(a), HY - 104 * math.sin(a))], "#8a3a12", w=6, passes=1, amp=3)
for k in range(9):         # face fill
    stroke([(HX - 58, HY - 46 + k * 13), (HX + 56, HY - 52 + k * 13)],
           "#f9c27a", w=7, passes=1, amp=2.6, op=0.55)
out.append(f'<circle cx="{HX-28}" cy="{HY-14}" r="12" fill="#141414"/>')
out.append(f'<circle cx="{HX+26}" cy="{HY-18}" r="12" fill="#141414"/>')
stroke(arc_pts(HX, HY + 14, 34, 24, math.radians(200), math.radians(340), 16), "#e2453a", w=5, passes=2, amp=2)

BODY = "#5ab4e0"
stroke([(HX + 44, HY + 64), (HX + 300, HY + 34)], BODY, w=6, passes=2, amp=3)      # back
stroke([(HX + 40, HY + 132), (HX + 292, HY + 118)], BODY, w=6, passes=2, amp=3)    # front
stroke([(HX + 300, HY + 34), (HX + 292, HY + 118)], BODY, w=6, passes=2, amp=3)
stroke([(HX + 118, HY + 40), (HX + 252, HY - 32), (HX + 316, HY - 40)], BODY, w=6, passes=2, amp=3)
stroke([(HX + 316, HY - 40), (HX + 330, HY + 26)], BODY, w=6, passes=2, amp=3)
# raised arm + hand
stroke([(HX + 150, HY - 22), (HX + 262, HY - 116)], "#3aa0d4", w=6, passes=2, amp=3)
for a in range(4):
    stroke([(HX + 262, HY - 116), (HX + 268 + a * 15, HY - 176 - a * 6)], "#f2a03c", w=6, passes=2, amp=2.6)
# trailing leg + foot
stroke([(HX + 62, HY + 130), (HX + 8, HY + 214)], "#f2a03c", w=6, passes=2, amp=3)
stroke([(HX + 8, HY + 214), (HX - 44, HY + 232), (HX + 6, HY + 250)], "#f2a03c", w=6, passes=2, amp=3)

# ── ball ───────────────────────────────────────────────────────────────────
for k in range(8):
    stroke(arc_pts(632, 900, 44 - k * 4.4, 40 - k * 4.2, 0, 6.28, 18), "#5aa9dd", w=5, passes=1, amp=2.4, op=0.8)

# ── grass ──────────────────────────────────────────────────────────────────
def grass(x0, x1, y, n, col):
    pts = [(x0, y)]
    step = (x1 - x0) / n
    for k in range(n):
        pts.append((x0 + step * (k + 0.5), y - random.uniform(60, 110)))
        pts.append((x0 + step * (k + 1), y))
    stroke(pts, col, w=6, passes=2, amp=3)
grass(60, 560, 1010, 7, "#2f8fa8")
grass(1400, 1560, 1010, 2, "#2f8fa8")

# ── ground ─────────────────────────────────────────────────────────────────
for k in range(11):
    stroke([(620 + random.uniform(-14, 14), 1020 + k * 8),
            (1420 + random.uniform(-14, 14), 1012 + k * 8)], "#8d8d92", w=8, passes=1, amp=3, op=0.7)

# A4 LANDSCAPE, exactly: 297 x 210mm = 1.41429. At width 1560 that is height
# 1103, not 1100 — a 0.3% error nobody would see, but the sheet is supposed to
# BE a sheet of A4, so it may as well be one.
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1560 1103" width="1560" height="1103">
<rect width="1560" height="1103" fill="#fdfbf6"/>
<g>{''.join(out)}</g>
</svg>'''

here = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(here, 'artwork.svg')
open(p, 'w').write(svg)
print('artwork.svg', os.path.getsize(p), 'bytes')
