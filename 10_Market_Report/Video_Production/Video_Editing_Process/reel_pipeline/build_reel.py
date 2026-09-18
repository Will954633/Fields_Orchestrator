#!/usr/bin/env python3
"""build_reel.py — turn a reel spec (JSON) into a finished 9:16 reel.

Two scene types, matching the approved Sep-2026 formats:
  • "text"  — full-frame presenter (portrait window from the landscape clip),
              headline revealing on the wall to his left.
  • "chart" — full-bleed dark chart fills the frame, headline top, presenter in a
              rounded PIP bottom-right.

Each scene pulls its own audio span (ss..ss+dur) from the source clip, so the
presenter's voice stays in sync; scenes are then concatenated in order.

Usage:
  python3 build_reel.py <reel.json> [--only N] [--keep]
    --only N   build just scene index N (0-based) for a fast preview
    --keep     keep per-scene intermediates in work/<slug>/

See reel.example.json for the spec shape and REEL_PRODUCTION_GUIDE.md for the
full authoring workflow.
"""
import json, os, sys, subprocess, shutil
from PIL import Image, ImageDraw

HERE   = os.path.dirname(os.path.abspath(__file__))
PANELS = os.path.join(HERE, 'panels')
RENDER = os.path.join(HERE, 'reel_render.js')
NODE   = '/home/projects/.nvm/versions/node/v20.20.2/bin/node'
CHROME_FALLBACK_NODE = 'node'

# ---- text-beat presenter window: 608x1080 portrait out of 1920x1080, scaled to 1080x1920
TEXT_CROP_W, TEXT_CROP_H = 608, 1080
TEXT_CROP_X_DEFAULT = 820
# ---- chart-beat presenter PIP (bottom-right); override per-scene via scene["pip"]
PIP_DEFAULT = dict(x=572, y=1372, w=440, h=516, r=28, cropw=850, croph=996, cropx=815, cropy=44)


def run(cmd, **kw):
    print('$', ' '.join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)

def probe_dur(path):
    out = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0', path],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0

def node_bin():
    return NODE if os.path.exists(NODE) else CHROME_FALLBACK_NODE


def render_frames(panel, scene, frames_dir, dur, fps, transparent):
    scene_json = frames_dir + '.json'
    with open(scene_json, 'w') as f:
        json.dump(scene, f)
    run([node_bin(), RENDER, panel, scene_json, frames_dir, str(dur), str(fps), '1' if transparent else '0'])
    n = len([x for x in os.listdir(frames_dir) if x.endswith('.png')])
    if n == 0:
        raise RuntimeError(f'no frames rendered for scene -> {frames_dir}')
    return n


def build_text_scene(src, scene, frames_dir, out_mp4, fps):
    dur = float(scene['dur']); ss = float(scene['ss'])
    cropx = int(scene.get('cropx', TEXT_CROP_X_DEFAULT))
    render_frames(os.path.join(PANELS,'text_reel.html'), scene, frames_dir, dur, fps, True)
    vf = (f"[0:v]crop={TEXT_CROP_W}:{TEXT_CROP_H}:{cropx}:0,scale=1080:1920,setsar=1[bg];"
          f"[bg][1:v]overlay=0:0[outv]")
    run(['ffmpeg','-y','-ss',f'{ss}','-t',f'{dur}','-i',src,
         '-framerate',str(fps),'-i',os.path.join(frames_dir,'f%04d.png'),
         '-filter_complex',vf,'-map','[outv]','-map','0:a','-dn','-map_metadata','-1',
         '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p',
         '-c:a','aac','-b:a','192k','-r',str(fps),'-t',f'{dur}','-movflags','+faststart', out_mp4])


# chart + stat beats share this compositor (full-bleed bg panel + presenter PIP);
# only the panel HTML differs.
PIP_PANEL = {'chart': 'chart_reel.html', 'stat': 'stat_reel.html'}

def build_pip_scene(src, scene, frames_dir, out_mp4, fps):
    dur = float(scene['dur']); ss = float(scene['ss'])
    p = dict(PIP_DEFAULT); p.update(scene.get('pip', {}))
    mask = frames_dir + '_mask.png'
    m = Image.new('L', (p['w'], p['h']), 0)
    ImageDraw.Draw(m).rounded_rectangle([0,0,p['w']-1,p['h']-1], radius=p['r'], fill=255)
    m.save(mask)
    render_frames(os.path.join(PANELS, PIP_PANEL[scene['type']]), scene, frames_dir, dur, fps, False)
    vf = (f"[1:v]crop={p['cropw']}:{p['croph']}:{p['cropx']}:{p['cropy']},scale={p['w']}:{p['h']},setsar=1[will];"
          f"[2:v]format=gray,scale={p['w']}:{p['h']}[mask];"
          f"[will][mask]alphamerge[willa];"
          f"color=c=black@0.55:s={p['w']+40}x{p['h']+40}:d={dur},format=rgba,boxblur=18[sh];"
          f"[0:v][sh]overlay={p['x']-20}:{p['y']-14}[bg1];"
          f"[bg1][willa]overlay={p['x']}:{p['y']}[outv]")
    run(['ffmpeg','-y','-framerate',str(fps),'-i',os.path.join(frames_dir,'f%04d.png'),
         '-ss',f'{ss}','-t',f'{dur}','-i',src,'-loop','1','-t',f'{dur}','-i',mask,
         '-filter_complex',vf,'-map','[outv]','-map','1:a','-dn','-map_metadata','-1',
         '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p',
         '-c:a','aac','-b:a','192k','-r',str(fps),'-t',f'{dur}','-movflags','+faststart', out_mp4])


def build_graphic_scene(src, scene, frames_dir, out_mp4, fps):
    """Full-bleed graphic beat with NO presenter (e.g. a quote/evidence card).
    Renders the panel frames and lays the source audio span under them."""
    dur = float(scene['dur']); ss = float(scene['ss'])
    render_frames(os.path.join(PANELS, 'quote_reel.html'), scene, frames_dir, dur, fps, False)
    run(['ffmpeg','-y','-framerate',str(fps),'-i',os.path.join(frames_dir,'f%04d.png'),
         '-ss',f'{ss}','-t',f'{dur}','-i',src,
         '-map','0:v','-map','1:a','-dn','-map_metadata','-1',
         '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p',
         '-c:a','aac','-b:a','192k','-r',str(fps),'-t',f'{dur}','-movflags','+faststart', out_mp4])


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    spec_path = sys.argv[1]
    only = None; keep = False
    if '--only' in sys.argv: only = int(sys.argv[sys.argv.index('--only')+1])
    if '--keep' in sys.argv: keep = True
    spec = json.load(open(spec_path))

    slug = spec['slug']; fps = int(spec.get('fps', 25))
    src = spec['source']
    if not os.path.isabs(src): src = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(spec_path)), src))
    if not os.path.exists(src): raise FileNotFoundError(f'source clip not found: {src}')

    work = os.path.join(HERE, 'work', slug); os.makedirs(work, exist_ok=True)
    os.makedirs(os.path.join(HERE,'out'), exist_ok=True)

    scene_clips = []
    for i, scene in enumerate(spec['scenes']):
        if only is not None and i != only: continue
        frames_dir = os.path.join(work, f'scene_{i:02d}_frames')
        out_mp4    = os.path.join(work, f'scene_{i:02d}.mp4')
        print(f'\n=== scene {i} [{scene["type"]}]  ss={scene["ss"]} dur={scene["dur"]} ===')
        if scene['type'] == 'text':               build_text_scene(src, scene, frames_dir, out_mp4, fps)
        elif scene['type'] in ('chart','stat'):   build_pip_scene(src, scene, frames_dir, out_mp4, fps)
        elif scene['type'] == 'quote':            build_graphic_scene(src, scene, frames_dir, out_mp4, fps)
        else: raise ValueError(f'unknown scene type: {scene["type"]}')
        d = probe_dur(out_mp4)
        if d <= 0: raise RuntimeError(f'scene {i} produced an empty clip')
        print(f'    -> {out_mp4}  ({d:.2f}s)')
        scene_clips.append(out_mp4)

    if only is not None:
        print(f'\nBuilt scene {only} only: {scene_clips[0]}'); return

    # concat (identical encoder settings -> stream copy is safe)
    listfile = os.path.join(work, 'concat.txt')
    with open(listfile, 'w') as f:
        for c in scene_clips: f.write(f"file '{c}'\n")
    out_reel = os.path.join(HERE, 'out', f'{slug}_reel.mp4')
    run(['ffmpeg','-y','-f','concat','-safe','0','-i',listfile,'-c','copy','-movflags','+faststart', out_reel])
    total = probe_dur(out_reel); want = sum(float(s['dur']) for s in spec['scenes'])
    print(f'\n✓ reel: {out_reel}  ({total:.2f}s, expected ~{want:.2f}s)')
    if abs(total - want) > 1.0:
        print(f'  ⚠ duration off by {abs(total-want):.2f}s — check scene encodes')
    if not keep:
        for d in os.listdir(work):
            if d.endswith('_frames'): shutil.rmtree(os.path.join(work,d), ignore_errors=True)

if __name__ == '__main__':
    main()
