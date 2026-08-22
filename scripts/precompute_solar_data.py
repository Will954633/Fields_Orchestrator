#!/usr/bin/env python3
"""Batch-precompute per-property solar_data (LiDAR building footprints + true heights + aerial scale)
and store on each Gold_Coast listing, so the website can render the sun experience without touching
LiDAR at request time. No AI, no cost. Groups properties by 1 km LiDAR tile for efficiency.

Writes: property.solar_data = {buildings:[{pts,h,subject}], mpp, source, generated_at}
Run on the VM with the ELVIS 'GoldCoast_2014_LGA' tiles present under LID.
"""
import os, sys, math, glob, json, io, urllib.request, datetime, collections
sys.path.insert(0,'/home/fields/Fields_Orchestrator')
import laspy, numpy as np, rasterio, bson, cv2
from shared.db import get_gold_coast_db
from pyproj import Transformer
from rasterio.features import geometry_mask, shapes
try:
    from src.mongo_client_factory import cosmos_retry
except Exception:
    def cosmos_retry(fn,*a,**k): return fn(*a,**k)
LID=os.environ.get('SOLAR_LIDAR_DIR','/home/fields/Fields_Orchestrator/data/lidar')
SUBS=['robina','varsity_lakes','burleigh_waters']; TILE=256
tf=Transformer.from_crs('EPSG:4326','EPSG:28356',always_xy=True); inv=Transformer.from_crs('EPSG:28356','EPSG:4326',always_xy=True)
def _project(lat,lon):
    s=min(max(math.sin(math.radians(lat)),-0.9999),0.9999)
    return (TILE*(0.5+lon/360.0),TILE*(0.5-math.log((1+s)/(1-s))/(4*math.pi)))
def fit_zoom(rings,w,h,scale,m=0.30):
    lons=[p[0] for r in rings for p in r];lats=[p[1] for r in rings for p in r]
    (x0,y0),(x1,y1)=_project(max(lats),min(lons)),_project(min(lats),max(lons))
    dx,dy=abs(x1-x0) or 1e-9,abs(y1-y0) or 1e-9
    for z in range(21,0,-1):
        if dx*(2**z)<=w*(1-m) and dy*(2**z)<=h*(1-m): return z,(min(lats)+max(lats))/2,(min(lons)+max(lons))/2
    return 18,(min(lats)+max(lats))/2,(min(lons)+max(lons))/2
def chaikin(pts,it=2):
    pts=[[float(a),float(b)] for a,b in pts]
    for _ in range(it):
        n=[]
        for i in range(len(pts)):
            a=pts[i];b=pts[(i+1)%len(pts)]
            n.append([a[0]*.75+b[0]*.25,a[1]*.75+b[1]*.25]);n.append([a[0]*.25+b[0]*.75,a[1]*.25+b[1]*.75])
        pts=n
    return [[int(round(x)),int(round(y))] for x,y in pts]

def tile_for(lat,lon):
    e,n=tf.transform(lon,lat); return int(e//1000*1000),int(n//1000*1000)
def load_tile(te,tn):
    dem=glob.glob(f'{LID}/**/GoldCoast_2014_LGA_SW_{te}_{tn}_1K_DEM_1m.tif',recursive=True)
    laz=glob.glob(f'{LID}/**/GoldCoast_2014_LGA_SW_{te}_{tn}_1K_Las.laz',recursive=True)
    if not laz:  # point cloud still zipped -> extract on demand
        import zipfile
        zp=glob.glob(f'{LID}/**/GoldCoast_2014_LGA_SW_{te}_{tn}_1K_Las.zip',recursive=True)
        if not dem or not zp: return None
        exd=f'{LID}/las_extracted'; os.makedirs(exd,exist_ok=True)
        with zipfile.ZipFile(zp[0]) as z:
            for nm in z.namelist():
                if nm.lower().endswith('.laz'): z.extract(nm,exd); laz=[os.path.join(exd,nm)]; break
    if not dem or not laz: return None
    with rasterio.open(dem[0]) as d: DEM=d.read(1).astype(float); TR=d.transform; H,W=DEM.shape; ND=d.nodata
    las=laspy.read(laz[0]); cls=np.asarray(las.classification)
    x,y,z=np.asarray(las.x),np.asarray(las.y),np.asarray(las.z)
    return dict(DEM=DEM,TR=TR,H=H,W=W,ND=ND,cls=cls,x=x,y=y,z=z)

def buildings_for(doc, tile):
    rings=doc['cadastral_polygon']['rings']; DEM=tile['DEM']; TR=tile['TR']; H,W=tile['H'],tile['W']; ND=tile['ND']
    Wp,Hp=1280,880; zoom,clat,clon=fit_zoom(rings,640,440,2); cx,cy=_project(clat,clon); f=(2**zoom)*2
    lat=doc['LATITUDE']
    mpp=(2*math.pi*6378137*math.cos(math.radians(lat)))/(TILE*(2**zoom)*2)
    to_px=lambda lon,la:[(_project(la,lon)[0]-cx)*f+Wp/2,(_project(la,lon)[1]-cy)*f+Hp/2]
    def p2ll(px,py):
        wX=cx+(px-Wp/2)/f;wY=cy+(py-Hp/2)/f;lon=(wX/TILE-0.5)*360.0;A=(0.5-wY/TILE)*4*math.pi;return lon,math.degrees(math.asin(math.tanh(A/2)))
    ext=[tf.transform(*p2ll(px,py)) for px,py in [(0,0),(Wp,0),(Wp,Hp),(0,Hp)]]
    extm=geometry_mask([{'type':'Polygon','coordinates':[ext]}],(H,W),TR,invert=True)
    b=tile['cls']==6; col=((tile['x'][b]-TR.c)/TR.a).astype(int); row=((tile['y'][b]-TR.f)/TR.e).astype(int)
    m=(col>=0)&(col<W)&(row>=0)&(row<H); col,row,zb=col[m],row[m],tile['z'][b][m]
    bras=np.zeros((H,W),np.uint8); bras[row,col]=1
    hgt=np.full((H,W),np.nan); np.fmax.at(hgt,(row,col),zb); hgt=hgt-np.where(DEM==ND,np.nan,DEM)
    bras=cv2.morphologyEx(bras,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    bras=(bras.astype(bool)&extm).astype(np.uint8)
    lot=geometry_mask([{'type':'Polygon','coordinates':[[tf.transform(lo,la) for lo,la in rings[0]]]}],(H,W),TR,invert=True)
    out=[]
    for geom,val in shapes(bras,mask=bras.astype(bool),transform=TR):
        if val!=1: continue
        ring=geom['coordinates'][0]
        area=abs(sum(ring[i][0]*ring[i+1][1]-ring[i+1][0]*ring[i][1] for i in range(len(ring)-1))/2)
        if area<18: continue
        cnt=np.array([to_px(*inv.transform(px,py)) for px,py in ring],np.float32).reshape(-1,1,2)
        ap=cv2.approxPolyDP(cnt,2.5,True).reshape(-1,2)
        poly=chaikin([[a,bb] for a,bb in ap],2)
        gm=geometry_mask([geom],(H,W),TR,invert=True); hh=hgt[gm&bras.astype(bool)]
        ridge=round(float(np.nanpercentile(hh,85)),1) if np.isfinite(hh).any() else 4.0
        # keep in-frame only
        if all(0<=p[0]<=Wp and 0<=p[1]<=Hp for p in poly[::4]) or True:
            out.append({'pts':poly,'h':ridge,'subject':bool((gm&lot).sum()>10)})
    out.sort(key=lambda o:(-o['subject'],-len(o['pts'])))
    return out, round(mpp,5)

def _addr_head(a):
    if not a: return None
    import re
    return re.sub(r'\s+',' ',a.split(',')[0].strip().lower()) or None

def twin_join_geo(coll):
    """Self-heal: a freshly-scraped for_sale doc often lacks geometry that a cadastral
    'twin' for the SAME parcel already carries (see fix-history SOLAR-NEW-LISTING-UNENRICHED
    / [[offmarket_property_twin_dedup]]). Denormalise LATITUDE/LONGITUDE/cadastral_polygon/
    aerial_boundary_url from a UNIQUELY-matching twin so the listing becomes solar-eligible.
    Conservative: only joins when exactly one twin shares the address head; never overwrites
    a field the listing already has."""
    twins={}; ambiguous=set()
    for t in coll.find({'cadastral_polygon.rings':{'$exists':True},'aerial_boundary_url':{'$nin':[None,'']},
                        'LATITUDE':{'$nin':[None]}},
                       {'address':1,'LATITUDE':1,'LONGITUDE':1,'cadastral_polygon':1,'aerial_boundary_url':1}):
        h=_addr_head(t.get('address'))
        if not h: continue
        if h in twins: ambiguous.add(h)
        twins[h]=t
    joined=0
    for d in coll.find({'listing_status':'for_sale'},
                       {'address':1,'LATITUDE':1,'LONGITUDE':1,'cadastral_polygon':1,'aerial_boundary_url':1}):
        need=(not d.get('cadastral_polygon',{}).get('rings')) or d.get('LATITUDE') is None or not d.get('aerial_boundary_url')
        if not need: continue
        h=_addr_head(d.get('address'))
        if not h or h in ambiguous: continue
        tw=twins.get(h)
        if not tw or tw['_id']==d['_id']: continue
        upd={}
        if not d.get('cadastral_polygon',{}).get('rings'): upd['cadastral_polygon']=tw['cadastral_polygon']
        if d.get('LATITUDE') is None: upd['LATITUDE']=tw['LATITUDE']; upd['LONGITUDE']=tw.get('LONGITUDE')
        if not d.get('aerial_boundary_url'): upd['aerial_boundary_url']=tw['aerial_boundary_url']
        if upd:
            cosmos_retry(coll.update_one,{'_id':d['_id']},{'$set':upd}); joined+=1
    return joined

def main():
    sys.path.insert(0,'/home/fields/Fields_Orchestrator/scripts')
    try:
        from job_status import job_run
    except Exception:
        import contextlib
        @contextlib.contextmanager
        def job_run(*a,**k):
            class B:
                metrics=None; detail=None
            yield B()
    db=get_gold_coast_db()
    with job_run('solar_data_precompute', cadence_hours=168, title='Solar experience precompute') as beat:
        # self-heal geometry from twins first, so new listings become solar-eligible
        tjoin=0
        for sub in SUBS: tjoin+=twin_join_geo(db[sub])
        print(f'twin-joined geometry onto {tjoin} listing(s)')
        # gather candidates, group by tile
        cand=[]
        for sub in SUBS:
            for d in db[sub].find({'listing_status':'for_sale','cadastral_polygon.rings':{'$exists':True},
                                   'aerial_boundary_url':{'$exists':True},'LATITUDE':{'$exists':True}},
                                  {'_id':1,'LATITUDE':1,'LONGITUDE':1,'cadastral_polygon':1,'address':1}):
                cand.append((sub,d))
        by_tile=collections.defaultdict(list)
        for sub,d in cand: by_tile[tile_for(d['LATITUDE'],d['LONGITUDE'])].append((sub,d))
        done=0; notile=0; err=0
        for (te,tn),items in sorted(by_tile.items()):
            tile=load_tile(te,tn)
            if tile is None: notile+=len(items); continue
            for sub,d in items:
                try:
                    bld,mpp=buildings_for(d,tile)
                    sd={'buildings':bld,'mpp':mpp,'source':'qld_lidar_2014','generated_at':datetime.datetime.utcnow().isoformat()}
                    cosmos_retry(db[sub].update_one,{'_id':d['_id']},{'$set':{'solar_data':sd}})
                    done+=1
                except Exception as e:
                    err+=1; print('  ERR',d.get('address'),str(e)[:80])
            del tile
        beat.metrics={'stored':done,'no_tile':notile,'errors':err,'candidates':len(cand),'twin_joined':tjoin}
        beat.detail=f'{done} stored, {tjoin} twin-joined, {notile} no-tile, {err} err'
        print(f'DONE: {done} stored / {len(cand)} candidates / {tjoin} twin-joined / {notile} no-tile / {err} err')
        if done==0 and len(cand)>0: raise RuntimeError('0 stored though candidates existed')

if __name__=='__main__': main()
