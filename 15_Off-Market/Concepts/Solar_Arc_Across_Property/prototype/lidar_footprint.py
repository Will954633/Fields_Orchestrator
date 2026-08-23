#!/usr/bin/env python3
"""Building footprint + TRUE height from the free QLD LiDAR point cloud — no AI, no cost.

Given a property's cadastral polygon + the ELVIS "GoldCoast_2014_LGA" tiles (LAZ point clouds +
1 m DEM), this:
  1. finds the 1 km MGA-zone-56 tile covering the property,
  2. reads the classified LiDAR (LAS class 6 = building) -> building footprint (colour-agnostic,
     separates houses from trees which are class 5),
  3. height = building-point Z minus the DEM ground -> TRUE ridge/eave height,
  4. vectorises the footprint and reprojects MGA -> lat/lon -> aerial pixels (via the same
     Web-Mercator georeference as render_property_aerial.py) so it drops onto the experience aerial.

PROVEN on 17 Springvale St, Robina 2026-08-22: footprint matches the whole roof (incl. the
solar-panel area the colour method notched out); height 3.8 m (single storey) vs the 5.5 m assumption.

Deps: laspy, lazrs, pyproj, rasterio, opencv-python, numpy, Pillow.
The DSM (surface) is built from the point cloud as max-Z per cell; the point cloud also carries
neighbours + trees (class 5) for the Tier-3 context-shadow build.
"""
import laspy, numpy as np, rasterio, glob, math, json, os
from pyproj import Transformer
from rasterio.features import geometry_mask, shapes
import cv2

TILE = 256
def _project(lat, lon):
    s = min(max(math.sin(math.radians(lat)), -0.9999), 0.9999)
    return (TILE*(0.5+lon/360.0), TILE*(0.5-math.log((1+s)/(1-s))/(4*math.pi)))
def fit_zoom(rings, w, h, scale, m=0.30):
    lons=[p[0] for r in rings for p in r]; lats=[p[1] for r in rings for p in r]
    (x0,y0),(x1,y1)=_project(max(lats),min(lons)),_project(min(lats),max(lons))
    dx,dy=abs(x1-x0) or 1e-9, abs(y1-y0) or 1e-9
    for z in range(21,0,-1):
        if dx*(2**z)<=w*(1-m) and dy*(2**z)<=h*(1-m): return z,(min(lats)+max(lats))/2,(min(lons)+max(lons))/2
    return 18,(min(lats)+max(lats))/2,(min(lons)+max(lons))/2

def footprints_for(rings, lidar_root, dem_glob='**/GoldCoast_2014_LGA_SW_%d_%d_1K_DEM_1m.tif',
                   laz_glob='**/GoldCoast_2014_LGA_SW_%d_%d_1K_Las.laz'):
    """rings: cadastral rings [[[lon,lat],...]]. Returns [{'pts':[[px,py],...],'h':metres,'area':m2}]."""
    tf = Transformer.from_crs('EPSG:4326','EPSG:28356', always_xy=True)
    inv = Transformer.from_crs('EPSG:28356','EPSG:4326', always_xy=True)
    e, n = tf.transform(rings[0][0][0], rings[0][0][1])
    te, tn = int(e//1000*1000), int(n//1000*1000)
    dem_p = glob.glob(os.path.join(lidar_root, dem_glob % (te, tn)), recursive=True)
    laz_p = glob.glob(os.path.join(lidar_root, laz_glob % (te, tn)), recursive=True)
    if not dem_p or not laz_p:
        return None                                        # tile not in the downloaded set
    with rasterio.open(dem_p[0]) as d:
        dem=d.read(1).astype(float); tr=d.transform; H,W=dem.shape; nod=d.nodata
    las = laspy.read(laz_p[0])
    cls=np.asarray(las.classification); x,y,z=np.asarray(las.x),np.asarray(las.y),np.asarray(las.z)
    mring=[tf.transform(lon,lat) for lon,lat in rings[0]]
    lot=geometry_mask([{'type':'Polygon','coordinates':[mring]}],(H,W),tr,invert=True)
    b=cls==6
    col=((x[b]-tr.c)/tr.a).astype(int); row=((y[b]-tr.f)/tr.e).astype(int)
    m=(col>=0)&(col<W)&(row>=0)&(row<H); col,row,zb=col[m],row[m],z[b][m]
    bras=np.zeros((H,W),np.uint8); bras[row,col]=1
    hgt=np.full((H,W),np.nan); np.fmax.at(hgt,(row,col),zb); hgt=hgt-np.where(dem==nod,np.nan,dem)
    bras=cv2.morphologyEx((bras & lot).astype(np.uint8),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    # aerial georeference (same as render_property_aerial.py)
    Wp,Hp=1280,880; zoom,clat,clon=fit_zoom(rings,640,440,2); cx,cy=_project(clat,clon); f=(2**zoom)*2
    to_px=lambda lon,lat:[(_project(lat,lon)[0]-cx)*f+Wp/2,(_project(lat,lon)[1]-cy)*f+Hp/2]
    out=[]
    for geom,val in shapes(bras,mask=bras.astype(bool),transform=tr):
        if val!=1: continue
        ring=geom['coordinates'][0]
        area=abs(sum(ring[i][0]*ring[i+1][1]-ring[i+1][0]*ring[i][1] for i in range(len(ring)-1))/2)
        if area<15: continue
        cnt=np.array([to_px(*inv.transform(px,py)) for px,py in ring],np.float32).reshape(-1,1,2)
        poly=[[int(a),int(c)] for a,c in cv2.approxPolyDP(cnt,3.0,True).reshape(-1,2)]
        hh=hgt[geometry_mask([geom],(H,W),tr,invert=True) & (bras>0)]
        ridge=round(float(np.nanpercentile(hh,90)),1) if np.isfinite(hh).any() else 4.0
        out.append({'pts':poly,'h':ridge,'area':int(area)})
    return sorted(out,key=lambda o:-o['area'])
