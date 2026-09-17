#!/usr/bin/env python3
"""Text-only scene demo (16:9, 1920x1080).

Full-frame presenter (as shot, uncropped) with a headline revealing on the LEFT,
over the wall beside him. No chart. Background = the source clip; foreground =
transparent text frames from render_text.js.

Usage: compositor_text.py [SRC.MP4] [OUT.mp4]
  env: SS (src start sec, default 0)  DUR (seconds, default 6.0)
"""
import subprocess, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    HERE, '..', '..', 'assets', 'Market_Updates', 'Sep_2026', 'DJI_20260917140152_0052_D.MP4')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out_text_demo.mp4')
FRAMES = os.path.join(HERE, 'scenes', 'text_frames', 'f%04d.png')
FPS = 25
SS  = float(os.environ.get('SS', '0'))
DUR = float(os.environ.get('DUR', '6.0'))

vf = (
    f"[0:v]scale=1920:1080,setsar=1[bg];"
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
