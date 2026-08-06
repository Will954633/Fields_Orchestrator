#!/usr/bin/env python3
"""
render_property_aerial.py — satellite aerial with the true cadastral boundary drawn on it.

WHY (2026-08-06). The V4 private report opens on an aerial, and a reader looking at
a block of roofs cannot tell which one is theirs. We hold LOT/PLAN on every
Gold_Coast document, and Queensland publishes the parcel geometry for free, so the
outline can be exact rather than approximated.

    LOT 2 / PLAN RP222932  ->  lotplan "2RP222932"  ->  polygon rings (WGS84)

Geometry comes from the Queensland Government's public cadastral service
(PlanningCadastre/LandParcelPropertyFramework). It is cached onto the property
document as `cadastral_polygon` the first time it is fetched, so a re-render costs
one Mongo read and the API is hit once per property, ever.

    python3 scripts/render_property_aerial.py --address "28 Wedgebill Parade, ..." --colour all
    python3 scripts/render_property_aerial.py --suburb burleigh_waters --limit 5 --colour sun
    python3 scripts/render_property_aerial.py --slug 28-wedgebill-parade-burleigh-waters

Boundary colour is **Fields sun #fec66f** — decided 2026-08-07 on legibility:
gold (#D28C5E) and copper (#b76749) sit in the same hue family as the terracotta
roofs common in these suburbs and the line disappears into the roofline. Both
remain selectable via --colour for comparison, but sun is the default and the
one the report uses.
"""
import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

from dotenv import load_dotenv                          # noqa: E402
from PIL import Image, ImageDraw, ImageFilter           # noqa: E402

from src.mongo_client_factory import get_mongo_client   # noqa: E402

QLD_CADASTRE = ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
                "PlanningCadastre/LandParcelPropertyFramework/MapServer/4/query")

BRAND = {
    "sun":    (0xFE, 0xC6, 0x6F),      # --fields-sun    — the bright yellow
    "gold":   (0xD2, 0x8C, 0x5E),      # --gold          — the deck's warm gold
    "copper": (0xB7, 0x67, 0x49),      # --fields-copper — the deepest of the three
}
# The real Fields mark. Birch (light) on the photo: Grass is a dark green and
# disappears against a dark aerial, which is the same legibility problem that
# ruled out copper for the boundary. The page header uses Grass, on the birch
# background where it belongs.
LOGO = Path(ORCH) / "00_Run_Commands" / "Logo_Files" / "logo_pack" / "2-Birch" / "\u2022 PNG" / "2-Fields-FullName-Birch.png"
TILE = 256


# ── geometry ───────────────────────────────────────────────────────────────

def lotplan_for(doc):
    """`LOT` + `PLAN` concatenated is Queensland's parcel key. `zoning_data.lot_plan`
    carries the same thing when the cadastral enrichment ran, and is preferred
    because it has already been normalised."""
    lp = ((doc.get("zoning_data") or {}).get("lot_plan") or "").strip()
    if lp:
        return lp.replace("/", "").replace(" ", "").upper()
    lot, plan = doc.get("LOT"), doc.get("PLAN")
    if lot and plan:
        return f"{str(lot).strip()}{str(plan).strip()}".upper()
    return None


def fetch_polygon(lotplan):
    """Rings as [[(lon, lat), ...], ...]. Returns None rather than raising — a
    property with no parcel on file simply renders without an outline."""
    q = urllib.parse.urlencode({
        "where": f"lotplan='{lotplan}'",
        "outFields": "lotplan,lot_area",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    })
    try:
        with urllib.request.urlopen(f"{QLD_CADASTRE}?{q}", timeout=30) as r:
            data = json.loads(r.read())
    except Exception:
        return None
    feats = data.get("features") or []
    if not feats:
        return None
    rings, area = [], None
    for f in feats:                       # a property can span several parcels
        area = area or (f.get("attributes") or {}).get("lot_area")
        for ring in ((f.get("geometry") or {}).get("rings") or []):
            rings.append([(p[0], p[1]) for p in ring])
    return {"rings": rings, "lot_area_sqm": area, "lotplan": lotplan} if rings else None


def polygon_for(gc, suburb, doc, refetch=False):
    """Cached on the document. The QLD service is public and free but slow (~1-3s),
    and parcel boundaries do not move."""
    cached = doc.get("cadastral_polygon")
    if cached and cached.get("rings") and not refetch:
        return cached
    lp = lotplan_for(doc)
    if not lp:
        return None
    poly = fetch_polygon(lp)
    if poly:
        gc[suburb].update_one({"_id": doc["_id"]}, {"$set": {"cadastral_polygon": poly}})
    return poly


def _project(lat, lon):
    """Web Mercator world coordinates, the projection Google Static Maps uses."""
    siny = min(max(math.sin(math.radians(lat)), -0.9999), 0.9999)
    return (TILE * (0.5 + lon / 360.0),
            TILE * (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)))


def fit_zoom(rings, width, height, scale, margin=0.30):
    """Largest zoom at which the whole parcel still fits, with breathing room.
    Google caps static maps at 21."""
    lons = [p[0] for r in rings for p in r]
    lats = [p[1] for r in rings for p in r]
    (x0, y0), (x1, y1) = _project(max(lats), min(lons)), _project(min(lats), max(lons))
    dx, dy = abs(x1 - x0) or 1e-9, abs(y1 - y0) or 1e-9
    for z in range(21, 0, -1):
        if dx * (2 ** z) <= width * (1 - margin) and dy * (2 ** z) <= height * (1 - margin):
            return z, (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
    return 18, (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2


# ── rendering ──────────────────────────────────────────────────────────────

def static_map(lat, lon, zoom, width, height, scale, key):
    url = ("https://maps.googleapis.com/maps/api/staticmap?"
           f"center={lat},{lon}&zoom={zoom}&size={width}x{height}&scale={scale}"
           f"&maptype=satellite&key={key}")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = r.read()
    if len(data) < 5000:
        raise RuntimeError("static map returned an error tile")
    import io
    return Image.open(io.BytesIO(data)).convert("RGBA")


def draw_boundary(img, rings, centre_lat, centre_lon, zoom, scale, rgb):
    """Outline, drawn twice: a dark blurred pass underneath so the line survives
    over pale roofs and bright concrete, then the brand colour on top. A single
    flat stroke disappears on light roofs, which is most of Burleigh Waters."""
    W, H = img.size
    cx, cy = _project(centre_lat, centre_lon)
    f = (2 ** zoom) * scale

    def to_px(lon, lat):
        x, y = _project(lat, lon)
        return ((x - cx) * f + W / 2, (y - cy) * f + H / 2)

    pts_per_ring = [[to_px(lon, lat) for lon, lat in ring] for ring in rings]

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for pts in pts_per_ring:
        if len(pts) > 2:
            sd.line(pts + [pts[0]], fill=(0, 0, 0, 170), width=int(9 * scale), joint="curve")
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3 * scale)))

    # A faint fill reads as "this parcel" rather than "a line near here".
    fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fill)
    for pts in pts_per_ring:
        if len(pts) > 2:
            fd.polygon(pts, fill=rgb + (38,))
    img.alpha_composite(fill)

    d = ImageDraw.Draw(img)
    for pts in pts_per_ring:
        if len(pts) > 2:
            d.line(pts + [pts[0]], fill=rgb + (255,), width=int(3 * scale), joint="curve")
    return img


def stamp_logo(img, scale, opacity=0.55):
    if not LOGO.exists():
        return img
    logo = Image.open(LOGO).convert("RGBA")
    target_w = int(img.size[0] * 0.20)
    logo = logo.resize((target_w, max(1, int(logo.size[1] * target_w / logo.size[0]))),
                       Image.LANCZOS)
    a = logo.split()[3].point(lambda v: int(v * opacity))
    logo.putalpha(a)
    # A soft dark wash behind it, so the white mark holds on pale rooftops.
    #
    # ⚠ The rectangle must be INSET inside a larger canvas. Drawn edge-to-edge on
    # a canvas its own size, GaussianBlur has nothing to bleed into and the result
    # is a visible grey box with slightly fuzzy corners — which is what the first
    # render produced. The margin is what turns it into a vignette.
    pad = int(16 * scale)
    m = int(26 * scale)
    wash = Image.new("RGBA", (logo.size[0] + (pad + m) * 2, logo.size[1] + (pad + m) * 2),
                     (0, 0, 0, 0))
    ImageDraw.Draw(wash).rounded_rectangle(
        [m, m, wash.size[0] - m, wash.size[1] - m],
        radius=int(10 * scale), fill=(0, 0, 0, 70))
    wash = wash.filter(ImageFilter.GaussianBlur(m / 2))
    origin = int(8 * scale)
    img.alpha_composite(wash, (origin - m, origin - m))
    img.alpha_composite(logo, (origin + pad - m + m, origin + pad - m + m))
    return img


def render(gc, suburb, doc, colour, out_dir, width=640, height=440, scale=2, refetch=False):
    key = os.getenv("GOOGLE_MAPS_STATIC_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_MAPS_STATIC_API_KEY not set")
    poly = polygon_for(gc, suburb, doc, refetch=refetch)
    if not poly:
        return None, "no parcel geometry"
    zoom, clat, clon = fit_zoom(poly["rings"], width, height, scale)
    img = static_map(clat, clon, zoom, width, height, scale, key)
    img = draw_boundary(img, poly["rings"], clat, clon, zoom, scale, BRAND[colour])
    img = stamp_logo(img, scale)
    slug = "-".join(str(doc.get("address", "")).lower().replace(",", "").split()[:-2]) or str(doc["_id"])
    out = Path(out_dir) / f"{slug}-aerial-{colour}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out, f"{poly.get('lot_area_sqm')} m² · lot {poly['lotplan']} · zoom {zoom}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address")
    ap.add_argument("--slug")
    ap.add_argument("--suburb", default="burleigh_waters")
    ap.add_argument("--limit", type=int, default=1)
    # DECIDED 2026-08-07 (Will): Fields sun. Gold and copper share a hue family
    # with the terracotta roofs that dominate these suburbs and dissolve into the
    # roofline; sun holds against roof, lawn, concrete and pool alike. `all` is
    # kept only for re-running the comparison, never for production output.
    ap.add_argument("--colour", choices=["sun", "gold", "copper", "all"], default="sun")
    ap.add_argument("--refetch", action="store_true", help="ignore the cached polygon")
    ap.add_argument("--out", default="/home/fields/Fields_Orchestrator/15_Off-Market/"
                                     "Concepts/V4_Private_Report/aerials")
    args = ap.parse_args()

    load_dotenv(os.path.join(ORCH, ".env"))
    gc = get_mongo_client()["Gold_Coast"]

    if args.address:
        docs = [(args.suburb, gc[args.suburb].find_one({"address": args.address}))]
    elif args.slug:
        found = None
        for s in ["robina", "varsity_lakes", "burleigh_waters"]:
            if args.slug.endswith(s.replace("_", "-")):
                street = args.slug[: -(len(s) + 1)].replace("-", " ")
                d = gc[s].find_one({"address": {"$regex": f"^{street}", "$options": "i"}})
                if d:
                    found = (s, d)
                    break
        docs = [found] if found else []
    else:
        docs = [(args.suburb, d) for d in gc[args.suburb].find(
            {"property_type": "House", "LOT": {"$exists": True}}).limit(args.limit)]

    colours = ["sun", "gold", "copper"] if args.colour == "all" else [args.colour]
    n = 0
    for suburb, doc in docs:
        if not doc:
            print("  not found")
            continue
        for c in colours:
            try:
                out, note = render(gc, suburb, doc, c, args.out, refetch=args.refetch)
                if out:
                    print(f"  ✓ {out.name:<52} {note}")
                    n += 1
                else:
                    print(f"  – {doc.get('address','?')[:44]}: {note}")
            except Exception as e:
                print(f"  ✗ {doc.get('address','?')[:44]} [{c}]: {type(e).__name__}: {e}")
    print(f"\n{n} image(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
