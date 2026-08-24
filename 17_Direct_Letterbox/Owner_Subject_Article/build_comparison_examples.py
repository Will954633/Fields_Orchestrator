#!/usr/bin/env python3
"""
build_comparison_examples.py -- the two real homes for the "what the same money
buys" side-by-side (Gold Coast left, Sydney right).

Both are actual sold houses chosen to sit on the arbitrage medians the section
already states: near ~$1.5M, four beds, with the Robina block ~650 m2 (our sold
median) and the Sydney block ~420 m2 (The Ponds median). Photos are Google Street
View at each address -- one licensable source both sides (attribution "Street View,
Google"), showing the actual home and block, rather than copyright listing photos.

Writes comparison_examples.json with each home's facts + a base64 Street View data
URI, so the article is self-contained (no broken image on a printed/HTML piece).

    python3 build_comparison_examples.py
"""
from __future__ import annotations

import base64
import json
import os
import sys

from curl_cffi import requests as cffi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")

OUT_PATH = os.path.join(HERE, "comparison_examples.json")
SV = "https://maps.googleapis.com/maps/api/streetview"

# Curated representatives. Facts verified 2026-08-24: Robina from our sold records
# (28 Olympus Drive), Sydney from onthehouse sold (12 Adelong Pde, The Ponds).
EXAMPLES = {
    "gc": {
        "label": "Gold Coast",
        "suburb": "Robina",
        "address": "Olympus Drive, Robina",
        "price": 1_550_000,
        "beds": 4, "baths": 2, "land": 650,
        "context": "about 5 km to the beach",
        "lat": -28.08153, "lon": 153.39522,
        "source": "Fields sold records",
    },
    "syd": {
        "label": "Sydney",
        "suburb": "The Ponds",
        "address": "Adelong Parade, The Ponds",
        "price": 1_520_000,
        "beds": 4, "baths": 2, "land": 420,
        "context": "about 34 km to the CBD",
        "lat": -33.69649, "lon": 150.90502,
        "source": "public sold records",
    },
}


def _streetview_data_uri(lat, lon, key) -> str | None:
    meta = cffi.get(f"{SV}/metadata?location={lat},{lon}&key={key}", timeout=20).json()
    if meta.get("status") != "OK":
        print(f"  ! no Street View at {lat},{lon} ({meta.get('status')})", file=sys.stderr)
        return None
    img = cffi.get(f"{SV}?size=640x420&location={lat},{lon}&fov=78&pitch=6"
                   f"&source=outdoor&key={key}", timeout=30)
    if img.status_code != 200 or not img.content:
        print(f"  ! Street View fetch failed {img.status_code}", file=sys.stderr)
        return None
    b64 = base64.b64encode(img.content).decode()
    return f"data:image/jpeg;base64,{b64}", meta.get("date")


def main():
    try:
        from shared.env import load_env
        load_env()
    except Exception:
        pass
    key = os.environ.get("GOOGLE_STREETVIEW_API_KEY")
    if not key:
        print("GOOGLE_STREETVIEW_API_KEY not set", file=sys.stderr)
        return 1

    out = {"retrieved_at": None, "attribution": "Street View, Google"}
    from datetime import datetime, timezone
    out["retrieved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for side, home in EXAMPLES.items():
        res = _streetview_data_uri(home["lat"], home["lon"], key)
        if not res:
            print(f"FAILED to get Street View for {side}", file=sys.stderr)
            return 2
        uri, date = res
        entry = {k: home[k] for k in home if k not in ("lat", "lon")}
        entry["photo_data_uri"] = uri
        entry["photo_date"] = date
        out[side] = entry
        print(f"  {side}: {home['suburb']} ${home['price']:,} "
              f"{home['land']}m² — Street View {date}, {len(uri)//1000}KB", file=sys.stderr)

    with open(OUT_PATH, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"wrote {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
