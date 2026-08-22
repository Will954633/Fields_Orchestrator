#!/usr/bin/env python3
"""council_catalog.py — enumerate the Gold Coast City + QLD state ArcGIS catalogs into a
single manifest ("the master file"). Auth-free. Run to (re)build catalog.json.

  python3 council_catalog.py            # crawl + write catalog.json
  python3 council_catalog.py --grep flood   # print matching layers from the saved catalog
"""
import os, sys, json, requests, time
HERE = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(HERE, "catalog.json")
H = {"User-Agent": "Mozilla/5.0 FieldsEstate/council-catalog"}
GC = "https://services.arcgis.com/3vStCH7NDoBOZ5zn/arcgis/rest/services"
QLD = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services"

def j(url, **p):
    p["f"] = "json"
    for _ in range(3):
        try:
            r = requests.get(url, params=p, headers=H, timeout=45); return r.json()
        except Exception: time.sleep(2)
    return {}

def crawl_gc():
    # single root call returns every hosted service (name/type/url) — the master index.
    # per-service layer/field detail is fetched on demand by the assembler.
    return [{"name": s["name"].split("/")[-1], "type": s.get("type"), "url": s["url"]}
            for s in j(GC).get("services", [])]

def crawl_qld(folders=("FloodCheck", "Historic_Flood_Lines", "Elevation", "Environment")):
    out = []
    for f in folders:
        for s in j(f"{QLD}/{f}").get("services", []):
            url = f"{QLD}/{s['name'].split('/')[-1]}/{s['type']}"
            out.append({"folder": f, "name": s["name"].split("/")[-1], "type": s["type"], "url": url})
        time.sleep(0.05)
    return out

def build():
    print("crawling Gold Coast City org (256 services, layer detail)…")
    gc = crawl_gc()
    print(f"  {len(gc)} GC services")
    print("crawling QLD state (flood/elevation/environment folders)…")
    ql = crawl_qld()
    print(f"  {len(ql)} QLD services")
    cat = {"gold_coast": gc, "qld_state": ql, "counts": {"gc": len(gc), "qld": len(ql)}}
    json.dump(cat, open(CAT, "w"), indent=1)
    print("wrote", CAT)

def grep(term):
    cat = json.load(open(CAT)); t = term.lower()
    for s in cat["gold_coast"]:
        if t in s["name"].lower():
            print(f"GC  {s['name']:45} {s['url']}")
    for s in cat["qld_state"]:
        if t in s["name"].lower() or t in s["folder"].lower():
            print(f"QLD {s['folder']}/{s['name']:35} {s['url']}")

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--grep": grep(sys.argv[2])
    else: build()
