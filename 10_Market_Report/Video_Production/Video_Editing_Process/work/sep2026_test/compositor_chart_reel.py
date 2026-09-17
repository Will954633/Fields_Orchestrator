#!/usr/bin/env python3
"""Chart beat in REEL dimensions (9:16, 1080x1920).

Full-bleed dark DOM chart fills the frame (headline top, line mid-band); the
presenter is a rounded-corner PIP floating in the clean bottom-right space.

Usage: compositor_chart_reel.py [SRC.MP4] [OUT.mp4]
  env: SS (default 24.3)  DUR (default 13.2)
"""
import subprocess, os, sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    HERE, '..', '..', 'assets', 'Market_Updates', 'Sep_2026', 'DJI_20260917140152_0052_D.MP4')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out_chart_reel_demo.mp4')
FRAMES = os.path.join(HERE, 'scenes', 'chart_reel_frames', 'f%04d.png')
MASK = os.path.join(HERE, 'pip_reel_mask.png')
FPS = 25
SS  = float(os.environ.get('SS', '24.3'))
DUR = float(os.environ.get('DUR', '13.2'))

# PIP box in the clean bottom-right; must stay clear of chart data + legend
PIP_X, PIP_Y, PIP_W, PIP_H, PIP_R = 572, 1372, 440, 516, 28
# presenter crop from the 1920x1080 source, aspect-matched, centred on Will
CROP_W, CROP_H, CROP_X, CROP_Y = 850, 996, 815, 44

m = Image.new('L', (PIP_W, PIP_H), 0)
ImageDraw.Draw(m).rounded_rectangle([0, 0, PIP_W-1, PIP_H-1], radius=PIP_R, fill=255)
m.save(MASK)

vf = (
    f"[1:v]crop={CROP_W}:{CROP_H}:{CROP_X}:{CROP_Y},scale={PIP_W}:{PIP_H},setsar=1[will];"
    f"[2:v]format=gray,scale={PIP_W}:{PIP_H}[mask];"
    f"[will][mask]alphamerge[willa];"
    f"color=c=black@0.55:s={PIP_W+40}x{PIP_H+40}:d={DUR},format=rgba,boxblur=18[sh];"
    f"[0:v][sh]overlay={PIP_X-20}:{PIP_Y-14}[bg1];"
    f"[bg1][willa]overlay={PIP_X}:{PIP_Y}[outv]"
)

cmd = [
    'ffmpeg', '-y',
    '-framerate', str(FPS), '-i', FRAMES,
    '-ss', f'{SS}', '-t', f'{DUR}', '-i', SRC,
    '-loop', '1', '-t', f'{DUR}', '-i', MASK,
    '-filter_complex', vf,
    '-map', '[outv]', '-map', '1:a',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '192k',
    '-r', str(FPS), '-t', f'{DUR}', '-movflags', '+faststart',
    OUT,
]
print(' '.join(cmd))
subprocess.run(cmd, check=True)
print('wrote', OUT)
