#!/usr/bin/env python3
"""
Download greyscale suburb maps from Mapbox Static Images API.

Each map shows the suburb boundary in Fields Grass against a muted light
basemap. The result is saved as JPEG into pipeline/output/maps/.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Public Mapbox token (pk.*) — same token the website's MapboxChoropleth uses.
# Loaded from MAPBOX_TOKEN env var so it never lives in source.
MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN")
if not MAPBOX_TOKEN:
    sys.exit("ERROR: MAPBOX_TOKEN not set. Add it to .env (load with `set -a && source .env && set +a`).")

GEOJSON_PATH = Path("/home/fields/Feilds_Website/08_Market_Narrative_Engine/backend/goldCoastSuburbs.geojson")

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output" / "maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Output dimensions (Mapbox @2x means physical pixels are 2x; final ~1280×880)
WIDTH = 640
HEIGHT = 440

# Fields brand
FIELDS_GRASS = "#22382C"
FIELDS_COPPER = "#B76749"

SUBURBS = [
    {"key": "robina",          "geojson_name": "Robina",         "outline_color": FIELDS_GRASS},
    {"key": "burleigh_waters", "geojson_name": "Burleigh Waters","outline_color": FIELDS_GRASS},
    {"key": "varsity_lakes",   "geojson_name": "Varsity Lakes",  "outline_color": FIELDS_GRASS},
]

# ---------------------------------------------------------------------------

def find_suburb_polygon(gj_collection, name):
    name_lower = name.lower()
    for f in gj_collection["features"]:
        if f["properties"].get("name", "").lower() == name_lower:
            return f
    return None


def styled_geojson(feature, outline_color):
    """Return a Feature with simplestyle-spec properties for Mapbox to render."""
    return {
        "type": "Feature",
        "properties": {
            # simplestyle-spec
            "stroke": outline_color,
            "stroke-width": 2.5,
            "stroke-opacity": 1.0,
            "fill": outline_color,
            "fill-opacity": 0.06,  # very subtle tint of the suburb area
        },
        "geometry": feature["geometry"],
    }


def fetch_static_map(geojson_feature, out_path):
    """Hit Mapbox Static Images API with a GeoJSON overlay."""
    gj_str = json.dumps(geojson_feature, separators=(",", ":"))
    encoded = urllib.parse.quote(gj_str, safe="")
    url = (
        "https://api.mapbox.com/styles/v1/mapbox/light-v11/static/"
        f"geojson({encoded})/auto/{WIDTH}x{HEIGHT}@2x"
        f"?access_token={MAPBOX_TOKEN}&padding=40"
    )
    if len(url) > 8000:
        # URL too long; will need polyline encoding instead. Should be rare for
        # our suburb polygons (47-81 points each).
        raise ValueError(f"Mapbox URL too long ({len(url)} chars). Use polyline encoding.")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    out_path.write_bytes(data)
    return len(data)


def main():
    print(f"Loading suburb boundary GeoJSON from {GEOJSON_PATH}...")
    with open(GEOJSON_PATH) as f:
        gj = json.load(f)

    for s in SUBURBS:
        feat = find_suburb_polygon(gj, s["geojson_name"])
        if not feat:
            print(f"  ✗ {s['geojson_name']}: not found in GeoJSON")
            continue
        styled = styled_geojson(feat, s["outline_color"])
        out = OUT_DIR / f"{s['key']}.jpg"
        try:
            size = fetch_static_map(styled, out)
            print(f"  ✓ {s['geojson_name']:20} → {out.name} ({size // 1024} KB)")
        except Exception as e:
            print(f"  ✗ {s['geojson_name']}: {e}")

    print(f"\nMaps saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
