#!/usr/bin/env python3
"""Text-only scene demo in REEL dimensions (9:16, 1080x1920).

A portrait window is cropped from the landscape clip so the presenter sits
right-of-centre with wall space on his left; the headline reveals over that
wall on the LEFT. Full-bleed presenter, no box.

Usage: compositor_text_reel.py [SRC.MP4] [OUT.mp4]
  env: SS (default 0)  DUR (default 6.0)  CROPX (source x of the 608-wide window, default 820)
"""
import subprocess, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    HERE, '..', '..', 'assets', 'Market_Updates', 'Sep_2026', 'DJI_20260917140152_0052_D.MP4')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out_text_reel_demo.mp4')
FRAMES = os.path.join(HERE, 'scenes', 'text_reel_frames', 'f%04d.png')
FPS = 25
SS  = float(os.environ.get('SS', '0'))
DUR = float(os.environ.get('DUR', '6.0'))
# 9:16 portrait window out of the 1920x1080 source: 608x1080 -> scaled to 1080x1920
CROP_W, CROP_H, CROP_X, CROP_Y = 608, 1080, int(os.environ.get('CROPX', '820')), 0

vf = (
    f"[0:v]crop={CROP_W}:{CROP_H}:{CROP_X}:{CROP_Y},scale=1080:1920,setsar=1[bg];"
    f"[bg][1:v]overlay=0:0[outv]"
)

cmd = [
    'ffmpeg', '-y',
    '-ss', f'{SS}', '-t', f'{DUR}', '-i', SRC,
    '-framerate', str(FPS), '-i', FRAMES,
    '-filter_complex', vf,
    '-map', '[outv]', '-map', '0:a',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '192k',
    '-r', str(FPS), '-t', f'{DUR}', '-movflags', '+faststart',
    OUT,
]
print(' '.join(cmd))
subprocess.run(cmd, check=True)
print('wrote', OUT)
