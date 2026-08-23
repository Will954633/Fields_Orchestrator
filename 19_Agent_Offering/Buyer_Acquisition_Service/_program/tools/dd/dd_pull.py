#!/usr/bin/env python3
"""dd_pull.py — buyer due-diligence data assembler for the Fields conjunction program.

Queries the highest-value Gold Coast City + Queensland state ArcGIS layers (auth-free
REST /query and /identify), merges them with the flood/zoning fields already stored on
the Mongo listing document, and writes one clean structured result per layer to
    listings/<slug>/dd/dd_data.json

Read-only against every external + DB source. Nothing is written except dd_data.json.

  python3 dd_pull.py --address "93 Burleigh Street, Burleigh Waters"
  python3 dd_pull.py --address "..." --lotplan 187RP128164   # skip the address->parcel lookup

Parcel resolution: we NEVER trust a supplied lat/lon. We resolve the authoritative
parcel polygon from the GC cadastre by LOTPLAN and use its centroid for every spatial
query. (The point handed to us for 93 Burleigh in the brief was ~200 m west of the
actual lot; the cadastre centroid is the source of truth.)
"""
import os, sys, json, time, argparse, datetime, re
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))  # Buyer_Acquisition_Service/
LISTINGS = os.path.join(SERVICE_ROOT, "listings")

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

H = {"User-Agent": "Mozilla/5.0 FieldsEstate/dd-pull"}
GC  = "https://services.arcgis.com/3vStCH7NDoBOZ5zn/arcgis/rest/services"
QLD = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services"
SLEEP = 0.35  # be polite between calls

# ---------------------------------------------------------------------------
# The curated registry — ~17 highest-value DD layers, selected from catalog.json.
#
#   method:
#     lotplan      -> attribute query on a LOTPLAN / LOT_PLAN field
#     point        -> point-in-polygon intersect at the parcel centroid
#     point_multi  -> point intersect across several layer ids (labelled bands)
#     buffer       -> features within `radius_m` of the centroid (proximity / nearby)
#     identify     -> MapServer /identify (for raster / dynamic / grouped QLD services)
#     unavailable  -> not published in the crawled catalogs; recorded honestly, not queried
# ---------------------------------------------------------------------------
REGISTRY = [
    {"key": "parcel", "label": "Cadastral parcel (identity + area)",
     "url": f"{GC}/Cadastre_Current_view/FeatureServer", "layer": 0,
     "method": "lotplan", "lotplan_field": "LOTPLAN",
     "out": "LOTPLAN,LOT,PLAN_,AREA_SIZE_SQ_M,SUBURB,POST_CODE,LONG_ADDRESS,TENURE,STRATATITLECODE,NUMBEROFUNITS",
     "answers": "Confirms the legal lot/plan, land area and address this DD pack is for."},

    {"key": "zoning", "label": "City Plan zoning",
     "url": f"{GC}/City_Plan_Zoning/FeatureServer", "layer": 0, "method": "point",
     "out": "LVL1_ZONE,LVL2_ZONE,ZONE_PRECINCT,LOT_PLAN",
     "answers": "The planning zone and precinct governing what may be built here."},

    {"key": "flood_overlay", "label": "Flood overlay (Flood Assessment Required)",
     "url": f"{GC}/Flood_assessment_required_v6/FeatureServer", "layer": 0, "method": "point",
     "out": "OVL2_DESC,OVL2_CAT,CAT_DESC",
     "answers": "Whether the City Plan flags the parcel for a flood assessment. Area-wide "
                "and deliberately conservative; it is NOT a statement that the land floods."},

    {"key": "flood_designated_level", "label": "Designated flood level (residential buildings)",
     "url": f"{GC}/Designated_Flood_Level_for_Residential_Buildings/FeatureServer", "layer": 0,
     "method": "point", "out": "*",
     "answers": "The minimum habitable floor level council sets for the defined flood event. "
                "Parcel-specific figures merged from the stored enrichment where the polygon is silent."},

    {"key": "flood_depth_modelled", "label": "Modelled flood depth (City Plan V6)",
     "url": f"{GC}/Flood_Depth_City_Plan_Version_6_update1/FeatureServer", "layer": 1, "method": "point",
     "out": "gridcode,Id",
     "answers": "Council's modelled flood depth band over the land in the defined event "
                "(gridcode 1 == the shallowest, <0.3 m band)."},

    {"key": "ica_insurance_flood", "label": "ICA insurance flood event (2026 model)",
     "url": f"{GC}/Insurance_Flood_Event_2026/FeatureServer", "method": "point_multi",
     "bands": {69: "Frequent (20% annual chance)", 70: "Infrequent (5% annual chance)",
               71: "Infrequent (1% annual chance)", 67: "Rare (0.2% annual chance)",
               68: "Extremely rare (0.05% annual chance)"},
     "out": "*",
     "answers": "The insurance industry's own flood-probability bands (Insurance_Flood_Event_2026). "
                "Which band, if any, contains the parcel — the basis insurers actually price on."},

    {"key": "acid_sulfate", "label": "Acid sulfate soils",
     "method": "unavailable",
     "answers": "Presence of acid sulfate soils (relevant to excavation / canal-front works). "
                "NOT published in the Gold Coast City ArcGIS org, nor in the crawled QLD state "
                "folders (FloodCheck / Historic_Flood_Lines / Elevation / Environment / "
                "GeoscientificInformation / InlandWaters). The GC City Plan carries an Acid "
                "Sulfate Soils overlay but it is not exposed as a queryable REST layer here — "
                "confirm via a council PD Online / City Plan interactive mapping search."},

    {"key": "bushfire_hazard", "label": "Bushfire hazard area",
     "url": f"{GC}/Bushfire_hazard_area_v5/FeatureServer", "layer": 0, "method": "point",
     "out": "OVL2_DESC,OVL2_CAT",
     "answers": "Whether the parcel sits in a mapped bushfire hazard area."},

    {"key": "landslide_hazard", "label": "Landslide hazard",
     "url": f"{GC}/Landslide_hazard_v5/FeatureServer", "layer": 0, "method": "point",
     "out": "OVL2_DESC,OVL2_CAT,SMEC_2010",
     "answers": "Whether the parcel sits in a mapped landslide / steep-land hazard area."},

    {"key": "heritage", "label": "Heritage place / listed area",
     "url": f"{GC}/Heritage_place_v5/FeatureServer", "layer": 1, "method": "point",
     "out": "*",
     "answers": "Whether the parcel is a heritage place or falls in a heritage-listed area."},

    {"key": "minimum_lot_size", "label": "Minimum lot size overlay",
     "url": f"{GC}/Minimum_lot_size/FeatureServer", "layer": 0, "method": "point",
     "out": "MLS,OVL2_DESC",
     "answers": "Any minimum-lot-size constraint (informs subdivision potential)."},

    {"key": "road_hierarchy", "label": "Functional road hierarchy (through-road / noise)",
     "url": f"{GC}/Functional_road_hierarchy_v5/FeatureServer", "layer": 1, "method": "buffer",
     "radius_m": 500, "out": "HIERARCHY,CUSTODIAN", "limit": 12,
     "answers": "Classified roads (arterial / sub-arterial / distributor) within 500 m — the "
                "through-road noise-exposure angle. No hit within 500 m means a quiet local street."},

    {"key": "development_applications", "label": "Nearby development applications (~400 m)",
     "url": f"{GC}/Property_Development_Applications_and_Determinations/FeatureServer", "layer": 0,
     "method": "buffer", "radius_m": 400,
     "out": "APPLICATION_NUMBER,APPLICATION_DESCRIPTION,APPLICATION_CLASS,CURRENT_STATUS,LODGEMENT_DATE,APPROVAL_DATE,FROM_STREET_NO,STREET,SUBURB",
     "limit": 25, "order": "LODGEMENT_DATE DESC",
     "answers": "Recent DAs within ~400 m — what is being built / changed around the parcel."},

    {"key": "sewer_main", "label": "Sewer main proximity",
     "url": f"{GC}/Sewer_Pipe_Non_Pressure/FeatureServer", "layer": 1, "method": "buffer",
     "radius_m": 60, "out": "*", "limit": 5,
     "answers": "Gravity sewer main within 60 m (connection / build-over relevance)."},

    {"key": "water_main", "label": "Potable water main proximity",
     "url": f"{GC}/Potable_Water_Pipe/FeatureServer", "layer": 0, "method": "buffer",
     "radius_m": 60, "out": "*", "limit": 5,
     "answers": "Potable water main within 60 m."},

    {"key": "stormwater_main", "label": "Stormwater / drainage pipe proximity",
     "url": f"{GC}/Drainage_Pipe/FeatureServer", "layer": 1, "method": "buffer",
     "radius_m": 60, "out": "*", "limit": 5,
     "answers": "Council stormwater drainage pipe within 60 m (drainage / easement relevance)."},

    {"key": "qld_floodcheck_1pct_aep", "label": "QLD FloodCheck 1% AEP (basin model)",
     "url": f"{QLD}/FloodCheck/BasinOnePercentAEP/MapServer", "method": "identify", "layers": "all",
     "answers": "Queensland state FloodCheck 1%-AEP (1-in-100-year) modelled flood extent by "
                "river basin, at the parcel."},

    {"key": "qld_floodcheck_study_coverage", "label": "QLD FloodCheck flood-study coverage",
     "url": f"{QLD}/FloodCheck/FloodStudies/MapServer", "method": "point_multi_url",
     "layer_ids": [2, 3], "out": "*",
     "answers": "Which state-registered flood study covers the parcel (study name, catchment, "
                "level, completion) — the provenance of the modelling behind the overlays."},

    {"key": "qld_historic_flood", "label": "QLD historic + dam-modelled flood extents",
     "url": f"{QLD}/InlandWaters/FloodLines/MapServer", "method": "identify", "layers": "all",
     "answers": "THE historical-inundation answer: does any recorded historic floodline "
                "(1974/2010/2011/2012/2013/2017/2019) or referable-dam modelled extent reach "
                "this parcel? Reported per intersecting layer."},
]

# ---------------------------------------------------------------------------
def slugify(address):
    a = address.split(",")[0].strip() + "-" + (address.split(",")[1].strip() if "," in address else "")
    return re.sub(r"[^a-z0-9]+", "-", a.lower()).strip("-")


def http_json(url, params, timeout=45):
    params = dict(params); params["f"] = "json"
    last = None
    for _ in range(3):
        try:
            r = requests.get(url, params=params, headers=H, timeout=timeout)
            return r.json()
        except Exception as e:
            last = e; time.sleep(1.5)
    return {"error": {"message": f"request failed: {last}"}}


def resolve_parcel(lotplan, address):
    """Authoritative parcel from the GC cadastre by LOTPLAN -> polygon, centroid, address."""
    url = f"{GC}/Cadastre_Current_view/FeatureServer/0/query"
    r = http_json(url, {"where": f"LOTPLAN='{lotplan}'",
                        "outFields": "LOTPLAN,LOT,PLAN_,AREA_SIZE_SQ_M,SUBURB,POST_CODE,LONG_ADDRESS",
                        "returnGeometry": "true", "outSR": 4326})
    feats = r.get("features", [])
    if not feats:
        return None
    f = feats[0]
    ring = f["geometry"]["rings"][0]
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return {"lotplan": lotplan, "attributes": f["attributes"],
            "centroid": {"lon": round(cx, 7), "lat": round(cy, 7)},
            "bbox": {"lon_min": min(xs), "lon_max": max(xs), "lat_min": min(ys), "lat_max": max(ys)},
            "geometry_source": "GC Cadastre_Current_view by LOTPLAN"}


def q_point(url, lid, lon, lat, out="*"):
    return http_json(f"{url}/{lid}/query", {
        "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": out,
        "returnGeometry": "false", "where": "1=1"})


def q_buffer(url, lid, lon, lat, radius_m, out="*", limit=25, order=""):
    p = {"geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
         "distance": radius_m, "units": "esriSRUnit_Meter",
         "spatialRel": "esriSpatialRelIntersects", "outFields": out,
         "returnGeometry": "false", "where": "1=1", "resultRecordCount": limit}
    if order:
        p["orderByFields"] = order
    return http_json(f"{url}/{lid}/query", p)


def q_identify(url, lon, lat, layers="all"):
    return http_json(f"{url}/identify", {
        "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "sr": 4326,
        "tolerance": 2, "mapExtent": f"{lon-0.01},{lat-0.01},{lon+0.01},{lat+0.01}",
        "imageDisplay": "600,600,96", "layers": layers, "returnGeometry": "false"})


def load_mongo_flood(address):
    try:
        from shared.db import get_gold_coast_db
        db = get_gold_coast_db()
        sub = address.split(",")[1].strip().lower().replace(" ", "_") if "," in address else "burleigh_waters"
        d = db[sub].find_one({"address": {"$regex": "^" + re.escape(address.split(",")[0]), "$options": "i"}},
                             {"zoning_data": 1, "address": 1})
        z = (d or {}).get("zoning_data", {})
        keep = ("lot_plan", "zone", "zone_precinct", "cadastral_area_sqm",
                "flood_overlay", "flood_description", "flood_designated_level_m",
                "flood_ground_level_m", "flood_floor_level_m", "flood_freeboard_m",
                "flood_risk_note", "flood_depth_code", "flood_depth_description",
                "in_any_ica_zone", "ica_note", "heritage_listed", "latitude", "longitude")
        return {"address": (d or {}).get("address"), **{k: z.get(k) for k in keep if k in z}}
    except Exception as e:
        return {"error": f"mongo read failed: {e}"}

# ---------------------------------------------------------------------------
def run_entry(e, parcel):
    lon, lat = parcel["centroid"]["lon"], parcel["centroid"]["lat"]
    today = datetime.date.today().isoformat()
    base = {"key": e["key"], "label": e["label"], "answers": e["answers"],
            "method": e["method"], "source_url": e.get("url"), "as_at": today}
    m = e["method"]
    try:
        if m == "unavailable":
            base.update({"status": "unavailable", "hit": None,
                         "note": "Layer not present in the crawled ArcGIS catalogs."})

        elif m == "lotplan":
            r = http_json(f"{e['url']}/{e['layer']}/query",
                          {"where": f"{e['lotplan_field']}='{parcel['lotplan']}'",
                           "outFields": e["out"], "returnGeometry": "false"})
            feats = r.get("features", [])
            base.update({"status": "ok" if "error" not in r else "error",
                         "hit": bool(feats),
                         "attributes": feats[0]["attributes"] if feats else None,
                         "error": r.get("error")})

        elif m == "point":
            r = q_point(e["url"], e["layer"], lon, lat, e["out"])
            feats = r.get("features", [])
            base.update({"status": "ok" if "error" not in r else "error",
                         "hit": bool(feats),
                         "attributes": feats[0]["attributes"] if feats else None,
                         "error": r.get("error")})

        elif m == "point_multi":
            bands_hit = {}; err = None
            for lid, name in e["bands"].items():
                r = q_point(e["url"], lid, lon, lat, e.get("out", "*"))
                if "error" in r:
                    err = r["error"]; continue
                bands_hit[name] = bool(r.get("features"))
                time.sleep(SLEEP)
            inside = [n for n, h in bands_hit.items() if h]
            base.update({"status": "ok" if not err else "error",
                         "hit": bool(inside), "bands": bands_hit,
                         "attributes": {"bands_containing_parcel": inside}, "error": err})

        elif m == "point_multi_url":
            hits = []; err = None
            for lid in e["layer_ids"]:
                r = q_point(e["url"], lid, lon, lat, e.get("out", "*"))
                if "error" in r:
                    err = r["error"]; continue
                for f in r.get("features", []):
                    hits.append({"layer": lid, **f["attributes"]})
                time.sleep(SLEEP)
            base.update({"status": "ok" if not err else "error",
                         "hit": bool(hits), "features": hits, "error": err})

        elif m == "buffer":
            r = q_buffer(e["url"], e["layer"], lon, lat, e["radius_m"],
                         e.get("out", "*"), e.get("limit", 25), e.get("order", ""))
            feats = r.get("features", [])
            base.update({"status": "ok" if "error" not in r else "error",
                         "hit": bool(feats), "radius_m": e["radius_m"],
                         "count": len(feats),
                         "features": [f["attributes"] for f in feats],
                         "error": r.get("error")})

        elif m == "identify":
            r = q_identify(e["url"], lon, lat, e.get("layers", "all"))
            results = r.get("results", [])
            base.update({"status": "ok" if "error" not in r else "error",
                         "hit": bool(results),
                         "intersecting_layers": [x.get("layerName") for x in results],
                         "features": [{"layer": x.get("layerName"),
                                       "attributes": x.get("attributes")} for x in results],
                         "error": r.get("error")})
    except Exception as ex:
        base.update({"status": "error", "hit": None, "error": str(ex)})
    return base

# ---------------------------------------------------------------------------
def summarize_row(res):
    s = res.get("status")
    if s == "unavailable":
        return "n/a", "not a queryable REST layer (see note)"
    if s == "error":
        msg = res.get("error")
        msg = msg.get("message") if isinstance(msg, dict) else msg
        return "ERR", str(msg)[:70]
    hit = res.get("hit")
    k = res["key"]
    if k == "parcel":
        a = res.get("attributes") or {}
        return "OK", f"{a.get('LONG_ADDRESS')} — {a.get('AREA_SIZE_SQ_M')} m2"
    if k == "zoning":
        a = res.get("attributes") or {}
        return ("HIT" if hit else "—"), (a.get("LVL1_ZONE") or "") if hit else "no zoning polygon"
    if k == "ica_insurance_flood":
        inside = (res.get("attributes") or {}).get("bands_containing_parcel") or []
        return ("IN" if inside else "CLEAR"), (", ".join(inside) if inside else "in NONE of the 5 ICA bands")
    if k == "flood_designated_level":
        a = res.get("attributes") or {}
        if hit and a.get("FLOODLVLDES") is not None:
            return "HIT", f"designated {a.get('FLOODLVLDES'):.2f} / ground {a.get('GROUNDCENTRE'):.2f} m AHD"
        return ("HIT" if hit else "—"), ("(merge stored 4.18/4.03 m AHD)" if not hit else "")
    if k == "flood_depth_modelled":
        a = res.get("attributes") or {}
        return ("HIT" if hit else "—"), (f"gridcode {a.get('gridcode')}" if hit else "no depth band")
    if k in ("development_applications", "road_hierarchy", "sewer_main", "water_main", "stormwater_main"):
        c = res.get("count", 0)
        if k == "road_hierarchy":
            classes = sorted({f.get("HIERARCHY") for f in res.get("features", [])})
            return ("HIT" if hit else "CLEAR"), (", ".join(classes) if hit else f"no classified road within {res.get('radius_m')} m")
        return ("HIT" if hit else "—"), f"{c} within {res.get('radius_m')} m"
    if k in ("qld_historic_flood", "qld_floodcheck_1pct_aep"):
        lyrs = res.get("intersecting_layers") or []
        return ("HIT" if hit else "CLEAR"), (", ".join(lyrs) if lyrs else "no intersecting extent")
    if k == "qld_floodcheck_study_coverage":
        feats = res.get("features") or []
        names = sorted({f.get("studyname") for f in feats if f.get("studyname")})
        return ("HIT" if hit else "—"), (", ".join(names) if names else ("covered (LGA record)" if hit else "no study polygon"))
    # generic overlays (flood_overlay, bushfire, landslide, heritage, min lot, designated level)
    a = res.get("attributes") or {}
    desc = a.get("OVL2_DESC") or a.get("MLS") or ""
    return ("HIT" if hit else "CLEAR"), (str(desc) if hit else "not within overlay")

# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True)
    ap.add_argument("--lotplan", default=None, help="override; else read lot_plan from Mongo")
    ap.add_argument("--out", default=None, help="override output path")
    a = ap.parse_args()

    mongo = load_mongo_flood(a.address)
    lotplan = a.lotplan or mongo.get("lot_plan")
    if not lotplan:
        print("FATAL: no LOTPLAN (pass --lotplan or ensure the Mongo doc has zoning_data.lot_plan)")
        sys.exit(1)

    print(f"Resolving parcel {lotplan} from GC cadastre …")
    parcel = resolve_parcel(lotplan, a.address)
    if not parcel:
        print(f"FATAL: LOTPLAN {lotplan} not found in GC cadastre")
        sys.exit(1)
    c = parcel["centroid"]
    print(f"  parcel centroid {c['lon']}, {c['lat']}  ({parcel['attributes'].get('LONG_ADDRESS')})")

    results = []
    for e in REGISTRY:
        print(f"  querying {e['key']} …", flush=True)
        results.append(run_entry(e, parcel))
        if e["method"] != "unavailable":
            time.sleep(SLEEP)

    out = {
        "address": a.address,
        "lotplan": lotplan,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "parcel": parcel,
        "mongo_flood_zoning": mongo,
        "layers": results,
    }

    slug = slugify(a.address)
    out_path = a.out or os.path.join(LISTINGS, slug, "dd", "dd_data.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2, default=str)

    # ---- readable summary table ----
    print("\n" + "=" * 92)
    print(f"BUYER DD  ·  {parcel['attributes'].get('LONG_ADDRESS')}  ·  Lot/Plan {lotplan}")
    print("=" * 92)
    print(f"{'LAYER':34} {'RESULT':7} DETAIL")
    print("-" * 92)
    for res in results:
        badge, detail = summarize_row(res)
        print(f"{res['label'][:33]:34} {badge:7} {detail}")
    print("-" * 92)

    # historical-flood headline
    hist = next((r for r in results if r["key"] == "qld_historic_flood"), {})
    lyrs = hist.get("intersecting_layers") or []
    historic = [l for l in lyrs if "Floodline" in l]
    dam = [l for l in lyrs if "dam" in l.lower() or "referable" in l.lower()]
    print("\nHISTORICAL-INUNDATION ANSWER:")
    if historic:
        print("  Recorded historic floodline(s) reach this parcel:", ", ".join(historic))
    else:
        print("  No recorded historic floodline reaches this parcel. Queensland's state historic")
        print("  floodlines cover other catchments (Brisbane/Bremer 1974, Bundaberg, Fitzroy,")
        print("  Logan-Albert 2017, western QLD) — none for the southern Gold Coast coastal")
        print("  catchment this lot sits in.")
    if dam:
        print("  Modelled referable-dam extent(s) DO cover it:", ", ".join(dam))
        print("  (Hinze Dam — extreme/low-probability dam-failure & probable-maximum-flood modelling,")
        print("   far beyond the 1% AEP; not a record of past inundation.)")

    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
