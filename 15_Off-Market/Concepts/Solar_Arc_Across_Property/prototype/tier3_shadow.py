#!/usr/bin/env python3
"""Tier-3: full-scene shadows (house + neighbours + trees) by ray-marching the LiDAR DSM.
Compute a shadow map for a sun position, warp it onto the property aerial, overlay."""
import laspy, numpy as np, rasterio, glob, bson, math, io, urllib.request, sys
sys.path.insert(0, '/home/fields/Fields_Orchestrator')
from shared.db import get_gold_coast_db
from pyproj import Transformer
from PIL import Image
LID = '/tmp/claude-1001/-home-fields-Fields-Orchestrator/d0cf8f8f-7d2e-434d-ad92-6e50edf06643/scratchpad/lidar'
SP = '/tmp/claude-1001/-home-fields-Fields-Orchestrator/d0cf8f8f-7d2e-434d-ad92-6e50edf06643/scratchpad'
TILE = 256
PID = '690bd7da8b8f5465926029b1'; SUB='robina'

def _project(lat, lon):
    s=min(max(math.sin(math.radians(lat)),-0.9999),0.9999)
    return (TILE*(0.5+lon/360.0), TILE*(0.5-math.log((1+s)/(1-s))/(4*math.pi)))
def fit_zoom(rings,w,h,scale,m=0.30):
    lons=[p[0] for r in rings for p in r]; lats=[p[1] for r in rings for p in r]
    (x0,y0),(x1,y1)=_project(max(lats),min(lons)),_project(min(lats),max(lons))
    dx,dy=abs(x1-x0) or 1e-9, abs(y1-y0) or 1e-9
    for z in range(21,0,-1):
        if dx*(2**z)<=w*(1-m) and dy*(2**z)<=h*(1-m): return z,(min(lats)+max(lats))/2,(min(lons)+max(lons))/2
    return 18,(min(lats)+max(lats))/2,(min(lons)+max(lons))/2
def sun(lat,doy,h):
    r=math.pi/180;L=lat*r; d=(-23.44*r)*math.cos((360/365*(doy+10))*r); Hh=15*(h-12)*r
    el=math.asin(max(-1,min(1,math.sin(L)*math.sin(d)+math.cos(L)*math.cos(d)*math.cos(Hh))))
    c=(math.sin(d)-math.sin(el)*math.sin(L))/(math.cos(el)*math.cos(L)+1e-9)
    az=math.acos(max(-1,min(1,c)));
    if Hh>0: az=2*math.pi-az
    return az/r, el/r

def shadow_map(dsm, cell, az_deg, el_deg, K=170):
    H,W=dsm.shape; azr=math.radians(az_deg); tanel=math.tan(math.radians(el_deg))
    dcol=math.sin(azr); drow=-math.cos(azr)          # toward the sun in grid (row+ = south)
    sh=np.zeros((H,W),bool)
    for k in range(1,K+1):
        sc=int(round(k*dcol)); sr=int(round(k*drow))
        if sc==0 and sr==0: continue
        blk=np.full((H,W),-1e4)
        r0,r1=max(0,-sr),min(H,H-sr); c0,c1=max(0,-sc),min(W,W-sc)
        if r1<=r0 or c1<=c0: continue
        blk[r0:r1,c0:c1]=dsm[r0+sr:r1+sr,c0+sc:c1+sc]
        sh |= (blk - k*cell*tanel) > (dsm + 0.4)
    return sh

db=get_gold_coast_db()
doc=db[SUB].find_one({'_id':bson.ObjectId(PID)},{'cadastral_polygon':1,'aerial_boundary_url':1})
rings=doc['cadastral_polygon']['rings']
# tile + DEM + point cloud
tf=Transformer.from_crs('EPSG:4326','EPSG:28356',always_xy=True)
e,n=tf.transform(rings[0][0][0],rings[0][0][1]); te,tn=int(e//1000*1000),int(n//1000*1000)
dem_p=glob.glob(f'{LID}/**/GoldCoast_2014_LGA_SW_{te}_{tn}_1K_DEM_1m.tif',recursive=True)[0]
las=laspy.read(glob.glob(f'{LID}/**/GoldCoast_2014_LGA_SW_{te}_{tn}_1K_Las.laz',recursive=True)[0])
with rasterio.open(dem_p) as d: dem=d.read(1).astype(float); tr=d.transform; H,W=dem.shape; nod=d.nodata
x,y,z=np.asarray(las.x),np.asarray(las.y),np.asarray(las.z)
col=((x-tr.c)/tr.a).astype(int); row=((y-tr.f)/tr.e).astype(int)
m=(col>=0)&(col<W)&(row>=0)&(row<H)
dsm=np.full((H,W),np.nan); np.fmax.at(dsm,(row[m],col[m]),z[m])
demf=np.where(dem==nod,np.nan,dem); dsm=np.where(np.isnan(dsm),demf,dsm)   # fill gaps with ground
from scipy.ndimage import gaussian_filter, grey_closing
dsm=grey_closing(dsm,size=(3,3))                 # fill 1-cell pits (roof gaps, panel holes)
dsm=gaussian_filter(dsm,1.1)                      # tame canopy speckle -> cleaner shadow edges
print('DSM built', dsm.shape, 'nDSM p99=%.1f'%np.nanpercentile(dsm-demf,99))

# sun: winter (21 Jun) 3:30pm
az,el=sun(-28.0747,172,15.5); print('sun az=%.0f el=%.0f'%(az,el))
sh=shadow_map(np.nan_to_num(dsm,nan=-1e4),1.0,az,el).astype(float); print('shadowed %.0f%%'%(100*(sh>0.5).mean()))

# --- warp shadow onto the aerial (inverse Web-Mercator -> MGA -> cell) ---
Wp,Hp=1280,880; zoom,clat,clon=fit_zoom(rings,640,440,2); cx,cy=_project(clat,clon); f=(2**zoom)*2
px=np.arange(Wp); py=np.arange(Hp); PX,PY=np.meshgrid(px,py)
worldX=cx+(PX-Wp/2)/f; worldY=cy+(PY-Hp/2)/f
lon=(worldX/TILE-0.5)*360.0
A=(0.5-worldY/TILE)*4*math.pi; s=np.tanh(A/2); lat=np.degrees(np.arcsin(s))
E,N=tf.transform(lon.ravel(),lat.ravel())
ci=((np.array(E)-tr.c)/tr.a).astype(int).reshape(Hp,Wp)
ri=((np.array(N)-tr.f)/tr.e).astype(int).reshape(Hp,Wp)
ok=(ci>=0)&(ci<W)&(ri>=0)&(ri<H)
shad_aerial=np.zeros((Hp,Wp),bool)
shad_aerial[ok]=sh[ri[ok],ci[ok]]

raw=urllib.request.urlopen(doc['aerial_boundary_url'],timeout=25).read()
im=Image.open(io.BytesIO(raw)).convert('RGB');
if im.size!=(Wp,Hp): im=im.resize((Wp,Hp))
arr=np.asarray(im).astype(float)
# soft, single-read shadow: blur the mask -> clean penumbra; cool+darken shadowed pixels
alpha=gaussian_filter(shad_aerial.astype(float),3.5)
alpha=np.clip(alpha*1.15,0,1)*0.5
for c,tintv in zip(range(3),(0.42,0.47,0.60)):
    arr[:,:,c]=arr[:,:,c]*(1-alpha)+ (arr[:,:,c]*tintv)*alpha
Image.fromarray(arr.clip(0,255).astype('uint8')).save(f'{SP}/tier3_winter_1530.png')
print('saved tier3 overlay')
