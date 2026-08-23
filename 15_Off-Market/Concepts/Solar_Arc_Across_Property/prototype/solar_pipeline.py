#!/usr/bin/env python3
"""Solar Arc — end-to-end, no-AI, no-cost pipeline for ONE property.

Fetch (cadastral polygon, aerial, lat/lon, storeys) -> georeference the aerial with our own
Web-Mercator code (replicating render_property_aerial.py) -> extract the roof by classic CV
(colour + contour, clipped to the cadastral polygon) -> compute the correct metres-per-pixel
from the render zoom -> emit the self-contained interactive experience HTML.

Usage:  python3 solar_pipeline.py --coll robina --id 690bd7da8b8f5465926029b1 --out /tmp
No AI. No paid API. Free QLD LiDAR DSM is the colour-agnostic fallback for dark/metal roofs.
"""
import os, sys, math, json, base64, argparse, urllib.request, re
sys.path.insert(0, '/home/fields/Fields_Orchestrator')
from shared.db import get_gold_coast_db
import bson, numpy as np
from PIL import Image, ImageDraw, ImageFilter
import cv2

TILE = 256
R_EARTH = 6378137.0

def project(lat, lon):
    s = min(max(math.sin(math.radians(lat)), -0.9999), 0.9999)
    return (TILE*(0.5 + lon/360.0), TILE*(0.5 - math.log((1+s)/(1-s))/(4*math.pi)))

def fit_zoom(rings, w, h, scale, margin=0.30):
    lons = [p[0] for r in rings for p in r]; lats = [p[1] for r in rings for p in r]
    (x0, y0), (x1, y1) = project(max(lats), min(lons)), project(min(lats), max(lons))
    dx, dy = abs(x1-x0) or 1e-9, abs(y1-y0) or 1e-9
    for z in range(21, 0, -1):
        if dx*(2**z) <= w*(1-margin) and dy*(2**z) <= h*(1-margin):
            return z, (min(lats)+max(lats))/2, (min(lons)+max(lons))/2
    return 18, (min(lats)+max(lats))/2, (min(lons)+max(lons))/2

def slugify(a): return re.sub(r'[^a-z0-9]+', '-', a.lower()).strip('-')

def extract_roof(im, rings, to_px):
    """Return list of {'pts','area'} roof polygons (px), clipped to the cadastral lot."""
    W, H = im.size
    arr = np.asarray(im.convert('RGB')).astype(int)
    mask = Image.new('L', (W, H), 0); md = ImageDraw.Draw(mask)
    for r in rings: md.polygon([to_px(lon, lat) for lon, lat in r], fill=255)
    mask = mask.filter(ImageFilter.MinFilter(15))          # erode ~7px: drop the drawn boundary stroke
    cad = np.asarray(mask) > 0
    Rc, Gc, Bc = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    roof = (Rc > 110) & (Rc-Gc > 28) & (Gc-Bc > 8) & (Rc-Bc > 55) & cad   # terracotta tile
    m = (roof*255).astype('uint8')
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), 'uint8'))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), 'uint8'))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:4]:
        a = cv2.contourArea(c)
        if a < 4000: continue
        ap = cv2.approxPolyDP(c, 0.012*cv2.arcLength(c, True), True)
        out.append({'area': int(a), 'pts': [[int(p[0][0]), int(p[0][1])] for p in ap]})
    return out

def build(coll, pid, out_dir):
    db = get_gold_coast_db()
    d = db[coll].find_one({'_id': bson.ObjectId(pid)},
        {'address':1,'LATITUDE':1,'LONGITUDE':1,'cadastral_polygon':1,'aerial_boundary_url':1,
         'property_valuation_data.property_overview':1})
    if not d or not d.get('cadastral_polygon') or not d.get('aerial_boundary_url'):
        print('SKIP', pid, '- missing cadastral polygon or aerial'); return None
    rings = d['cadastral_polygon']['rings']; lat, lon = d['LATITUDE'], d['LONGITUDE']
    addr = d['address']; lot = int(d['cadastral_polygon'].get('lot_area_sqm') or 0)
    po = (d.get('property_valuation_data') or {}).get('property_overview') or {}
    stories = po.get('number_of_stories') or 1
    W, H = 1280, 880
    zoom, clat, clon = fit_zoom(rings, 640, 440, 2)
    cx, cy = project(clat, clon); f = (2**zoom)*2
    def to_px(lon_, lat_):
        x, y = project(lat_, lon_); return ((x-cx)*f + W/2, (y-cy)*f + H/2)
    mpp = (2*math.pi*R_EARTH*math.cos(math.radians(lat)))/(TILE*(2**zoom)*2)   # metres per pixel, this zoom
    # aerial
    raw = urllib.request.urlopen(d['aerial_boundary_url'], timeout=25).read()
    im = Image.open(__import__('io').BytesIO(raw)).convert('RGB')
    if im.size != (W, H): im = im.resize((W, H))
    aerial = 'data:image/png;base64,' + base64.b64encode(raw).decode()
    parts = extract_roof(im, rings, to_px)
    ridge = round(3.0*stories + 2.5, 1)   # single-storey ridge ~5.5m
    buildings = [{'pts': p['pts'], 'h': ridge if i == 0 else 3.0} for i, p in enumerate(parts)]
    roof_note = ('roof outline extracted from the aerial by our own image processing (no AI)'
                 if buildings else 'roof not auto-detected (dark/metal roof -> use LiDAR); shadow omitted')
    print(f'{addr[:40]:40} zoom={zoom} mpp={mpp:.4f} roof_parts={len(buildings)} stories={stories}')
    tpl = open(os.path.join(os.path.dirname(__file__), '_template.html'), encoding='utf-8').read()
    html = (tpl.replace('__ADDR__', addr)
               .replace('__SUB__', f'{addr} &middot; lot {lot}&nbsp;m&sup2; &middot; faces the winter sun')
               .replace('__LAT__', f'{lat:.4f}')
               .replace('__MPP__', f'{mpp:.5f}')
               .replace('__BUILDINGS__', json.dumps(buildings))
               .replace('__ROOFNOTE__', roof_note)
               .replace('__AERIAL__', aerial))
    outp = os.path.join(out_dir, f'solar_{slugify(addr.split(",")[0])}.html')
    open(outp, 'w', encoding='utf-8').write(html)
    print('  ->', outp)
    return outp

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--coll', required=True); ap.add_argument('--id', required=True)
    ap.add_argument('--out', default='/tmp')
    a = ap.parse_args()
    build(a.coll, a.id, a.out)
