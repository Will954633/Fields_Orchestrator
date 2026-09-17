#!/usr/bin/env python3
"""Reel (1080x1920) compositor.
Base = dark top zone + presenter video cropped into the bottom band.
Then overlay each scene: animated scenes use a PNG frame-sequence (with a held
freeze frame after), static scenes use a single PNG. Fades on enter/exit.

Usage: compositor.py [SRC.MP4] [OUT.mp4]
"""
import subprocess, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    HERE, '..', '..', 'assets', 'Market_Updates', 'Sep_2026', 'DJI_20260917140152_0052_D.MP4')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out_sep2026_reel.mp4')
SCN = os.path.join(HERE, 'scenes')
FPS = 25
FADE = 0.3

# source duration (the color base is otherwise infinite -> runaway encode)
DUR = float(subprocess.run(
    ['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0', SRC],
    capture_output=True, text=True).stdout.strip())

# (scene, start, end, animated, active_dur)  active_dur only for animated
TIMELINE = [
    ('hook',            0.00,  3.35, True,  3.1),
    ('median_chart',    3.50, 10.60, True,  2.6),
    ('demand',         10.90, 15.30, False, None),
    ('dom_rule',       15.40, 24.30, False, None),
    ('dom_chart',      24.50, 48.80, True,  9.5),
    ('indicator_intro',49.10, 62.80, False, None),
    ('logos',          63.10, 69.40, False, None),
    ('signals_chart',  69.60, 85.30, False, None),
    ('cta',            85.70, 96.70, False, None),
]

# ---- base: dark canvas + presenter band (crop centred on Will) ----
# source 1920x1080, Will centred ~x=1240 -> crop 1104x1080 @x=688 -> scale 1080x1056 @y=864
base_filter = (
    "color=c=0x14171A:s=1080x1920:r={fps}:d={dur}[bg];"
    "[0:v]crop=1104:1080:688:0,scale=1080:1056,setsar=1[pres];"
    "[bg][pres]overlay=0:864,"
    "drawbox=x=0:y=860:w=1080:h=4:color=0xDB7A4A:t=fill[base0]"
).format(fps=FPS, dur=round(DUR,3))

inputs = ['-i', SRC]
parts = [base_filter]
last = '[base0]'
idx_in = 1  # input 0 is SRC

for si, (name, a, b, anim, act) in enumerate(TIMELINE):
    if anim:
        seq = os.path.join(SCN, f'{name}_frames', 'f%04d.png')
        frz = os.path.join(SCN, f'{name}_last.png')
        # frame sequence input (plays once at FPS)
        inputs += ['-framerate', str(FPS), '-i', seq]
        i_seq = idx_in; idx_in += 1
        # freeze image input (looped for the hold portion)
        hold = round(b - (a + act), 3)
        inputs += ['-loop', '1', '-t', f'{max(hold,0.04)}', '-i', frz]
        i_frz = idx_in; idx_in += 1
        a_end = round(a + act, 3)
        # sequence: fade in at start, no fade out (freeze continues it)
        parts.append(f"[{i_seq}:v]format=rgba,fade=t=in:st=0:d={FADE}:alpha=1,setpts=PTS+{a}/TB[ov{si}a]")
        out_a = f'[s{si}a]'
        parts.append(f"{last}[ov{si}a]overlay=eof_action=pass:enable='between(t,{a},{a_end})'{out_a}")
        # freeze: fade out at end
        fo = round(hold - FADE, 3)
        parts.append(f"[{i_frz}:v]format=rgba,fade=t=out:st={max(fo,0)}:d={FADE}:alpha=1,setpts=PTS+{a_end}/TB[ov{si}b]")
        out_b = f'[s{si}b]'
        parts.append(f"{out_a}[ov{si}b]overlay=eof_action=pass:enable='between(t,{a_end},{b})'{out_b}")
        last = out_b
    else:
        png = os.path.join(SCN, f'{name}.png')
        dur = round(b - a, 3)
        inputs += ['-loop', '1', '-t', f'{dur}', '-i', png]
        i = idx_in; idx_in += 1
        fo = round(dur - FADE, 3)
        parts.append(f"[{i}:v]format=rgba,fade=t=in:st=0:d={FADE}:alpha=1,fade=t=out:st={fo}:d={FADE}:alpha=1,setpts=PTS+{a}/TB[ov{si}]")
        out = f'[s{si}]'
        parts.append(f"{last}[ov{si}]overlay=eof_action=pass:enable='between(t,{a},{b})'{out}")
        last = out

filt = ';'.join(parts)
cmd = ['ffmpeg', '-y'] + inputs + [
    '-filter_complex', filt, '-map', last, '-map', '0:a?',
    '-t', f'{round(DUR,3)}',
    '-c:v', 'libx264', '-crf', '19', '-preset', 'medium', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', OUT,
]
print('scenes:', len(TIMELINE), '| inputs:', (len(inputs)//2))
r = subprocess.run(cmd)
print('exit', r.returncode, '->', OUT if r.returncode == 0 else 'FAILED')
