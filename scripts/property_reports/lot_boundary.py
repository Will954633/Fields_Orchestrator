"""
Fetch lot boundary polygon from the GCCC ArcGIS Cadastre service.

Uses a point-in-polygon query (lat/lng → lot polygon) against the public
Gold Coast City Council cadastral layer. Returns a list of (lng, lat) pairs
forming the lot boundary ring.

No API key required — the GCCC ArcGIS services are public.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 12  # seconds

# Primary: dedicated cadastral layer with LOTPLAN, LONG_ADDRESS, AREA_SIZE_SQ_M
_CADASTRE_URL = (
    "https://services.arcgis.com/3vStCH7NDoBOZ5zn/arcgis/rest/services"
    "/Cadastre_Current_view/FeatureServer/0/query"
)

# Fallback: city plan zoning layer — same lot boundaries, different attributes
_ZONING_URL = (
    "https://services.arcgis.com/3vStCH7NDoBOZ5zn/arcgis/rest/services"
    "/City_Plan_Zoning/FeatureServer/0/query"
)


def fetch_boundary(
    lat: float,
    lng: float,
) -> Optional[List[Tuple[float, float]]]:
    """Return the lot boundary ring as a list of (lng, lat) tuples, or None.

    Queries the GCCC ArcGIS cadastral service using point-in-polygon.
    The returned ring is closed (first == last vertex).
    """
    params = {
        "geometry": f'{{"x":{lng},"y":{lat},"spatialReference":{{"wkid":4326}}}}',
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "LOTPLAN,LONG_ADDRESS,AREA_SIZE_SQ_M",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "json",
    }

    for url in (_CADASTRE_URL, _ZONING_URL):
        try:
            resp = requests.post(url, data=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                continue
            rings = features[0].get("geometry", {}).get("rings", [])
            if not rings or not rings[0]:
                continue
            # rings[0] is a list of [lng, lat] pairs
            ring = [(float(c[0]), float(c[1])) for c in rings[0]]
            logger.debug(
                "lot_boundary: %d vertices from %s",
                len(ring),
                "cadastre" if "Cadastre" in url else "zoning",
            )
            return ring
        except Exception as exc:
            logger.warning("lot_boundary fetch failed (%s): %s", url, exc)
            continue

    return None
