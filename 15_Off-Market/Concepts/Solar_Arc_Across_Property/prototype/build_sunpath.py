#!/usr/bin/env python3
import math, json, base64, urllib.request, sys, os
sys.path.insert(0,'/home/fields/Fields_Orchestrator')
from shared.db import get_gold_coast_db
import bson

LAT, LON = -28.07471564, 153.39215814
OUT = "/tmp/claude-1001/-home-fields-Fields-Orchestrator/d0cf8f8f-7d2e-434d-ad92-6e50edf06643/scratchpad/sunpath_artifact.html"

db = get_gold_coast_db()
d = db['robina'].find_one({'_id': bson.ObjectId('690bd7da8b8f5465926029b1')},
      {'address':1,'cadastral_polygon':1,'aerial_boundary_url':1})
ADDR = d['address']
rings = d['cadastral_polygon']['rings'][0]        # [[lon,lat],...]
AERIAL = d['aerial_boundary_url']

# ---- fetch aerial as data URI (self-contained) ----
try:
    raw = urllib.request.urlopen(AERIAL, timeout=20).read()
    AERIAL_DATA = "data:image/png;base64," + base64.b64encode(raw).decode()
except Exception as e:
    print("aerial fetch failed:", e); AERIAL_DATA = ""

# ---- solar ----
def solar_positions(lat, doy):
    latr=math.radians(lat); decl=math.radians(-23.44)*math.cos(math.radians(360/365*(doy+10)))
    out=[]
    for m in range(0,24*60+1,10):
        h=m/60.0; H=math.radians(15*(h-12))
        sel=math.sin(latr)*math.sin(decl)+math.cos(latr)*math.cos(decl)*math.cos(H)
        el=math.asin(max(-1,min(1,sel)))
        if el<=0: continue
        caz=(math.sin(decl)-math.sin(el)*math.sin(latr))/(math.cos(el)*math.cos(latr)+1e-9)
        az=math.degrees(math.acos(max(-1,min(1,caz))))
        if H>0: az=360-az
        out.append((h,az,math.degrees(el)))
    return out
winter=solar_positions(LAT,172); summer=solar_positions(LAT,355)
def hi(arc,hr): return min(arc,key=lambda p:abs(p[0]-hr))
def hrlabel(hr):
    if hr==12: return "noon"
    h=int(hr); return f"{h if h<=12 else h-12}{'am' if h<12 else 'pm'}"
w_noon=max(winter,key=lambda p:p[2]); s_noon=max(summer,key=lambda p:p[2])

# ---- polygon aspect ----
def bearing(a,b):  # a,b = [lon,lat]
    lon1,lat1,lon2,lat2=map(math.radians,[a[0],a[1],b[0],b[1]])
    dl=lon2-lon1
    x=math.sin(dl)*math.cos(lat2)
    y=math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(dl)
    return (math.degrees(math.atan2(x,y))+360)%360
def dist(a,b):
    R=6371000; lon1,lat1,lon2,lat2=map(math.radians,[a[0],a[1],b[0],b[1]])
    dlat=lat2-lat1; dlon=lon2-lon1
    h=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(h))
edges=[]
for i in range(len(rings)-1):
    a,b=rings[i],rings[i+1]
    edges.append({'brg':bearing(a,b),'len':dist(a,b)})
edges.sort(key=lambda e:-e['len'])
# longest edge ~ side boundary; its bearing gives the block's long axis
long_axis=edges[0]['brg']%180
# the outward normal that faces north-ish = long_axis +/-90 nearest to 0/360
cands=[(long_axis+90)%360,(long_axis-90)%360]
def northness(az): return math.cos(math.radians(az))  # 1 at N
rear_face=max(cands,key=northness)   # the face that most points north (gets winter sun)
COMPASS=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
def compass(az): return COMPASS[round(az/22.5)%16]

facts=dict(winter_noon=round(w_noon[2]),summer_noon=round(s_noon[2]),
  w_rise=round(winter[0][1]),w_set=round(winter[-1][1]),
  s_rise=round(summer[0][1]),s_set=round(summer[-1][1]),
  long_axis=round(long_axis),north_face=round(rear_face),north_face_c=compass(rear_face),
  lot_area=int(d['cadastral_polygon']['lot_area_sqm']))
print(json.dumps(facts,indent=2))

# ---- SVG: polar sun-path chart ----
def polar(az,el,R,cx,cy):
    r=R*(90-el)/90.0; a=math.radians(az-90)  # N up
    return cx+r*math.cos(a), cy+r*math.sin(a)
def arc_path(arc,R,cx,cy):
    pts=[polar(az,el,R,cx,cy) for _,az,el in arc]
    return "M"+" L".join(f"{x:.1f},{y:.1f}" for x,y in pts)
R=150; CX=CY=175
rings_svg=""
for el in (0,30,60):
    rr=R*(90-el)/90
    rings_svg+=f'<circle cx="{CX}" cy="{CY}" r="{rr:.0f}" fill="none" stroke="#cfc9ba" stroke-width="1"/>'
    rings_svg+=f'<text x="{CX+3}" y="{CY-rr+12:.0f}" font-size="9" fill="#9a9382">{el}°</text>'
for lbl,az in [('N',0),('E',90),('S',180),('W',270)]:
    x,y=polar(az,-4,R+14,CX,CY)
    rings_svg+=f'<text x="{x:.0f}" y="{y:.0f}" font-size="12" font-weight="700" fill="#4a4a44" text-anchor="middle" dominant-baseline="middle">{lbl}</text>'
def marker(arc,hr,color):
    p=hi(arc,hr); x,y=polar(p[1],p[2],R,CX,CY)
    return f'<circle cx="{x:.0f}" cy="{y:.0f}" r="4" fill="{color}"/><text x="{x:.0f}" y="{y-8:.0f}" font-size="9" fill="{color}" font-weight="600" text-anchor="middle">{hrlabel(hr)}</text>'
sunpath_svg=f'''<svg viewBox="0 0 350 360" width="100%">
 <rect width="350" height="360" fill="#f4efe4"/>
 {rings_svg}
 <path d="{arc_path(summer,R,CX,CY)}" fill="none" stroke="#e0a884" stroke-width="3"/>
 <path d="{arc_path(winter,R,CX,CY)}" fill="none" stroke="#24392c" stroke-width="3"/>
 {"".join(marker(winter,h,"#24392c") for h in (9,12,15))}
 {"".join(marker(summer,h,"#c1632f") for h in (9,12,15))}
 <text x="12" y="340" font-size="11" fill="#24392c" font-weight="700">— Winter (21 Jun)</text>
 <text x="150" y="340" font-size="11" fill="#c1632f" font-weight="700">— Summer (21 Dec)</text>
</svg>'''

# ---- SVG overlay on aerial: winter sun rays (from sun azimuth) + compass ----
def dirvec(az):  # screen unit vector pointing TOWARD azimuth (N up)
    a=math.radians(az); return math.sin(a), -math.cos(a)
AC=250  # aerial svg is 500x500, center
rays=""
for hr,color in [(9,'#f2c94c'),(12,'#f2a900'),(15,'#f2c94c')]:
    p=hi(winter,hr); az=p[1]
    dx,dy=dirvec(az)               # direction toward the sun
    # ray comes FROM the sun: start far in sun direction, arrow toward centre
    sx,sy=AC+dx*230,AC+dy*230
    ex,ey=AC+dx*70,AC+dy*70
    rays+=f'<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{ex:.0f}" y2="{ey:.0f}" stroke="{color}" stroke-width="4" marker-end="url(#ah)" opacity="0.95"/>'
    lx,ly=AC+dx*248,AC+dy*248
    rays+=f'<text x="{lx:.0f}" y="{ly:.0f}" font-size="14" fill="{color}" font-weight="700" text-anchor="middle" dominant-baseline="middle" style="paint-order:stroke;stroke:#1c1c1a;stroke-width:3px">{hrlabel(hr)}</text>'
# compass — fixed north-pointing arrow
compass_svg=('<g transform="translate(58,58)">'
  '<circle r="30" fill="rgba(28,28,26,0.6)"/>'
  '<path d="M0,-20 L7,10 L0,4 L-7,10 Z" fill="#e0a884"/>'
  '<text y="26" font-size="13" fill="#fff" font-weight="700" text-anchor="middle">N</text></g>')
aerial_svg=f'''<svg viewBox="0 0 500 500" width="100%">
 <defs>
   <marker id="ah" markerWidth="9" markerHeight="9" refX="6" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#f2a900"/></marker>
   <marker id="ah2" markerWidth="8" markerHeight="8" refX="4" refY="7" orient="auto"><path d="M0,8 L4,0 L8,8 z" fill="#e0a884"/></marker>
 </defs>
 <image href="{AERIAL_DATA}" x="0" y="0" width="500" height="500"/>
 {rays}
 {compass_svg}
</svg>'''

aspect_line=(f"The block's long axis runs {compass(facts['long_axis'])}–{compass((facts['long_axis']+180)%360)}, "
 f"so its broad face looks {facts['north_face_c']} — toward the winter sun. In winter the sun stays low in the "
 f"northern sky (peaks at {facts['winter_noon']}° at midday), so {facts['north_face_c']}-facing outdoor space "
 f"holds midday sun while the opposite side sits in the home's winter shadow. In summer the sun is nearly overhead "
 f"({facts['summer_noon']}°) and clears the whole block by mid-morning.")

stat_items=[("Winter midday sun",f"{facts['winter_noon']}° high"),
  ("Summer midday sun",f"{facts['summer_noon']}° high"),
  ("Winter sunrise → set",f"{compass(facts['w_rise'])} → {compass(facts['w_set'])}"),
  ("Faces the winter sun",facts['north_face_c'])]
stat_cards="".join(
  '<div style="background:#24392c;color:#efe9dd;border-radius:10px;padding:12px 16px;flex:1;min-width:150px">'
  '<div style="font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;color:#c8b98f">'+t+'</div>'
  '<div style="font-size:1.35rem;font-weight:700;color:#fff">'+str(v)+'</div></div>'
  for t,v in stat_items)

html=f'''<div style="max-width:1100px;margin:0 auto;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1c1c1a">
 <div style="background:#dcd8cd;padding:28px 26px;border-radius:16px">
  <p style="font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:#8a7f63;font-weight:700;margin:0 0 4px">Aspect &amp; sun path</p>
  <h2 style="margin:0 0 4px;font-size:1.5rem">Which way it faces the sun</h2>
  <p style="color:#5a5a50;margin:0 0 22px">{ADDR} · lot {facts['lot_area']} m²</p>
  <div class="sp-grid">
    <figure class="sp-card">{aerial_svg}<figcaption>Yellow arrows show the direction of the winter sun at 9am, noon and 3pm. Aerial is north-up; the orange outline is the lot boundary.</figcaption></figure>
    <figure class="sp-card sp-chart">{sunpath_svg}<figcaption>The sun's path across the sky through the day — winter stays low in the north, summer arcs nearly overhead.</figcaption></figure>
  </div>
  <div class="sp-stats">{stat_cards}</div>
  <p style="line-height:1.65;margin:20px 0 0;color:#2c2c28">{aspect_line}</p>
  <p style="font-family:ui-monospace,monospace;font-size:.72rem;color:#7a7a70;margin:14px 0 0">Computed from the lot boundary (QLD cadastre, plan {d['cadastral_polygon']['lotplan']}) and solar geometry for this latitude. Block-level aspect — confirm room-by-room sun at inspection.</p>
 </div>
</div>'''

style='''<style>
  .sp-page{background:#efe9dd;min-height:100vh;padding:24px 16px;box-sizing:border-box}
  .sp-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
  .sp-card{margin:0;background:#fff;border-radius:12px;overflow:hidden}
  .sp-card.sp-chart{background:#f4efe4;padding:8px 8px 0}
  .sp-card figcaption{font-size:.78rem;line-height:1.45;color:#6f6a5c;padding:10px 14px 14px}
  .sp-stats{display:flex;gap:14px;flex-wrap:wrap;margin:22px 0 0}
  @media (max-width:720px){ .sp-grid{grid-template-columns:1fr} }
</style>'''
page=f'<div class="sp-page">{html}</div>'
open(OUT,'w').write(style+page)
print("WROTE", OUT, "aerial_bytes_ok=", bool(AERIAL_DATA), "len=", len(style+page))
