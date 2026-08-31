#!/usr/bin/env python3
"""
Backfill the cadastral parcel + boundary aerial for listings that are missing it.

WHY THIS EXISTS
───────────────────────────────────────────────────────────────────────────────
A boundary border only draws on the /property aerial when the document carries a
`cadastral_polygon` (the QLD title boundary). That polygon is resolved by LOT/PLAN
against the QLD cadastre. A freshly-scraped Domain listing has NEITHER a LOT/PLAN
nor a `cadastral_polygon` — Domain does not publish lot/plan — so newly-published
pages render with no boundary, a null `living_map.parcel`, and no `aerial_boundary_url`.

The obvious fix — point-in-polygon from the doc's geocoded coordinates — DOES NOT
WORK on our data: the coordinates are nominatim road-level geocodes that land on
the *road parcel* (measured 2026-09-01: 7 Beauty Point Dr and 22/1 Warbler Pde both
resolved to a "Road Type Parcel", ~150-185 m off the real lot). So this instead
resolves LOT/PLAN by ADDRESS against the QLD Addresses layer (layer 0 of
LandParcelPropertyFramework), which returns an authoritative lotplan + rooftop
coordinate per address string. From there the existing pipeline does the rest.

WHAT IT DOES, per target document
───────────────────────────────────────────────────────────────────────────────
1. Resolve lotplan: prefer an existing LOT/PLAN/zoning_data.lot_plan on the doc;
   otherwise query the QLD Addresses layer by the parsed address and take the
   exact match. Writes LOT, PLAN, zoning_data.lot_plan, and a rooftop
   `address_geocode` back to the doc.
2. `render_property_aerial.polygon_for()` — resolves + caches `cadastral_polygon`
   (own lot for houses/townhouses; scheme footprint for apartments, scope recorded).
3. Rebuild `living_map` so `living_map.parcel` populates (border source for the map).
4. Render the boundary aerial, publish `aerial_boundary_url` + WebP derivatives.

This is the same chain the batch aerial renderer runs, plus the address→lotplan
resolution step that new listings need. Idempotent; skips a target that already
has a `cadastral_polygon` unless --force.

    python3 scripts/backfill_parcel_boundary.py --address "7 Beauty Point Drive, Robina" --suburb robina
    python3 scripts/backfill_parcel_boundary.py --id 6a9558d56fdb6cafc3519d7e --suburb robina
    python3 scripts/backfill_parcel_boundary.py --suburb robina --missing --dry-run
    python3 scripts/backfill_parcel_boundary.py --missing --limit 20        # all target suburbs
"""

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import json
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root
sys.path.insert(0, _HERE)                     # scripts/
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from shared.env import load_env
from shared.db import get_gold_coast_db
from shared import image_derivatives as deriv
from job_status import job_run
from bson import ObjectId

load_env()

import render_property_aerial as ra  # noqa: E402 (needs load_env first)

SUBURBS = ("robina", "varsity_lakes", "burleigh_waters")
BLOB_ROOT = Path("/data/blobs/property-images/aerial")
PUBLIC_ROOT = "https://blobs.fieldsestate.com.au/property-images/aerial"
DERIV_CONTAINER = "property-images"
ADDRESSES_LAYER = ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
                   "PlanningCadastre/LandParcelPropertyFramework/MapServer/0/query")


# ── address → lotplan via the QLD Addresses layer ───────────────────────────
def _norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def parse_address(address):
    """Pull (unit, street_number, street_words, locality) out of a listing address
    like '22/1 Warbler Parade, Varsity Lakes, QLD 4227' or
    '7 Beauty Point Drive, Robina, QLD 4226'. Returns a dict or None."""
    if not address:
        return None
    parts = [p.strip() for p in address.split(",")]
    street = parts[0]
    locality = parts[1] if len(parts) > 1 else ""
    m = re.match(r"^\s*(?:(?:unit|u)\s*)?(\d+[a-zA-Z]?)\s*/\s*(\d+[a-zA-Z]?)\s+(.*)$", street)
    if m:
        unit, number, rest = m.group(1), m.group(2), m.group(3)
    else:
        m = re.match(r"^\s*(\d+[a-zA-Z\-]?)\s+(.*)$", street)
        if not m:
            return None
        unit, number, rest = None, m.group(1), m.group(2)
    return {"unit": unit, "number": number, "street": rest.strip(), "locality": locality}


def resolve_lotplan_by_address(address):
    """Return {lotplan, lat, lon, matched_address, scope_hint} for the exact address,
    or None if the Addresses layer has no confident match. Raises on transport failure
    so the caller distinguishes 'no address on file' from 'service down' (Rule 7b)."""
    p = parse_address(address)
    if not p:
        return None
    # First street token is enough to scope; verify the exact row afterward.
    street_token = p["street"].split()[0]
    where = (f"UPPER(address) LIKE '%{p['number']} {street_token.upper()}%"
             f"{p['locality'].split()[0].upper()}%'")
    q = urllib.parse.urlencode({
        "where": where,
        "outFields": "lotplan,unit_number,street_number,street_name,street_type,"
                     "locality,latitude,longitude,address,lotplan_status",
        "returnGeometry": "false", "f": "json",
    })
    with urllib.request.urlopen(f"{ADDRESSES_LAYER}?{q}", timeout=45) as r:
        data = json.loads(r.read())
    if data.get("error"):
        raise RuntimeError(f"Addresses layer error: {data['error']}")
    want_num = _norm(p["number"])
    want_unit = _norm(p["unit"]) if p["unit"] else None
    want_street = _norm(p["street"])          # e.g. BEAUTYPOINTDRIVE
    want_loc = _norm(p["locality"])
    for f in data.get("features", []):
        a = f["attributes"]
        if _norm(a.get("street_number")) != want_num:
            continue
        if want_unit and _norm(a.get("unit_number")) != want_unit:
            continue
        # street_name+street_type on the layer, concatenated, should equal our street
        cand_street = _norm(f"{a.get('street_name','')}{a.get('street_type','')}")
        if cand_street != want_street:
            continue
        if want_loc and _norm(a.get("locality")) != want_loc:
            continue
        if not a.get("lotplan"):
            continue
        return {"lotplan": a["lotplan"], "lat": a.get("latitude"),
                "lon": a.get("longitude"), "matched_address": a.get("address"),
                "lotplan_status": a.get("lotplan_status")}
    return None


def split_lotplan(lotplan):
    """'44RP184003' -> ('44', 'RP184003'); '22GTP103921' -> ('22', 'GTP103921')."""
    m = re.match(r"^(\d+)([A-Z].*)$", lotplan.strip().upper())
    return (m.group(1), m.group(2)) if m else (None, None)


# ── aerial publish (mirrors batch_render_aerials publish block) ─────────────
def ensure_derivatives(suburb, doc_id):
    blob_name = f"aerial/{suburb}/{doc_id}/boundary.png"
    before = deriv.existing_derivatives(DERIV_CONTAINER, blob_name)
    try:
        got = deriv.make_derivatives_from_disk(DERIV_CONTAINER, blob_name)
    except deriv.DecodeError as exc:
        print(f"    ! aerial derivative decode failed: {exc}")
        return 0
    if got is None:
        print(f"    ! aerial png not on disk for derivatives: {blob_name}")
        return 0
    return len(set(got) - set(before))


def render_and_publish(db, suburb, doc):
    """Render boundary aerial for a doc that now has a resolvable polygon.
    Returns 'rendered' | 'no_parcel' | 'error:<msg>'."""
    out_dir = BLOB_ROOT / suburb / str(doc["_id"])
    try:
        path, note = ra.render(db, suburb, doc, "sun", str(out_dir))
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}: {exc}"
    if not path:
        db[suburb].update_one({"_id": doc["_id"]},
                              {"$set": {"aerial_boundary_failed": note}})
        return "no_parcel"
    final = out_dir / "boundary.png"
    Path(path).rename(final)
    url = f"{PUBLIC_ROOT}/{suburb}/{doc['_id']}/boundary.png"
    fresh = db[suburb].find_one({"_id": doc["_id"]}, {"cadastral_polygon": 1})
    scope = ((fresh or {}).get("cadastral_polygon") or {}).get("boundary_scope") or "lot"
    db[suburb].update_one({"_id": doc["_id"]},
                          {"$set": {"aerial_boundary_url": url,
                                    "aerial_boundary_scope": scope,
                                    "aerial_boundary_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                           "$unset": {"aerial_boundary_failed": ""}})
    ensure_derivatives(suburb, doc["_id"])
    return "rendered"


def rebuild_living_map(address):
    """Shell out to the supported living-map entrypoint so living_map.parcel repopulates."""
    r = subprocess.run(
        [sys.executable, os.path.join(_HERE, "precompute_living_map.py"),
         "--address", address, "--force"],
        cwd=os.path.dirname(_HERE), capture_output=True, text=True, timeout=300)
    return r.returncode == 0, (r.stderr or r.stdout)[-400:]


# ── per-document driver ─────────────────────────────────────────────────────
def process_doc(db, suburb, doc, force=False, dry_run=False):
    addr = doc.get("address")
    print(f"\n▸ {suburb}: {addr}  ({doc['_id']})")
    if doc.get("cadastral_polygon", {}).get("rings") and not force:
        print("  already has cadastral_polygon — skip (use --force to redo)")
        return "skip"

    lot, plan = doc.get("LOT"), doc.get("PLAN")
    lotplan = ((doc.get("zoning_data") or {}).get("lot_plan")
               or (f"{lot}{plan}" if lot and plan else None))
    set_fields = {}
    if not lotplan:
        try:
            hit = resolve_lotplan_by_address(addr)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! Addresses layer transport error: {exc}")
            return "error"
        if not hit:
            print("  ✗ no confident address match in QLD Addresses layer")
            db[suburb].update_one({"_id": doc["_id"]},
                                  {"$set": {"parcel_backfill_failed": "no_address_match"}})
            return "no_match"
        lotplan = hit["lotplan"]
        lot, plan = split_lotplan(lotplan)
        print(f"  ✓ address→lotplan {lotplan}  (matched '{hit['matched_address']}')")
        if hit.get("lat") and hit.get("lon"):
            set_fields["address_geocode"] = {"latitude": hit["lat"], "longitude": hit["lon"],
                                             "source": "qld_addresses", "geocoded_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if lot and plan:
        set_fields["LOT"] = str(lot)
        set_fields["PLAN"] = str(plan)
        set_fields.setdefault("zoning_data", {})
        # merge lot_plan without clobbering an existing zoning_data object
        set_fields["zoning_data.lot_plan"] = lotplan

    if dry_run:
        print(f"  [dry-run] would set {list(set_fields)} and render aerial for lotplan {lotplan}")
        return "dry"

    if set_fields:
        # dotted keys + nested — split so we never overwrite zoning_data wholesale
        flat = {k: v for k, v in set_fields.items() if k != "zoning_data"}
        db[suburb].update_one({"_id": doc["_id"]}, {"$set": flat,
                              "$unset": {"parcel_backfill_failed": ""}})

    doc = db[suburb].find_one({"_id": doc["_id"]})   # refresh with LOT/PLAN
    poly = ra.polygon_for(db, suburb, doc, refetch=force)
    if not poly:
        print(f"  ✗ QLD cadastre returned no parcel for lotplan {lotplan}")
        db[suburb].update_one({"_id": doc["_id"]},
                              {"$set": {"parcel_backfill_failed": f"no_parcel:{lotplan}"}})
        return "no_parcel"
    print(f"  ✓ cadastral_polygon {poly.get('lotplan')} "
          f"scope={poly.get('boundary_scope')} area={poly.get('lot_area_sqm')} sqm")

    ok, tail = rebuild_living_map(addr)
    print(f"  {'✓' if ok else '✗'} living_map rebuild ({'ok' if ok else tail})")

    status = render_and_publish(db, suburb, db[suburb].find_one({"_id": doc["_id"]}))
    print(f"  aerial: {status}")
    return "done" if status == "rendered" else status


def collect_targets(db, args):
    targets = []
    if args.address:
        subs = [args.suburb] if args.suburb else SUBURBS
        for s in subs:
            d = db[s].find_one({"address": {"$regex": re.escape(args.address.split(",")[0]), "$options": "i"},
                                "listing_status": "for_sale"})
            if d:
                targets.append((s, d))
    elif args.id:
        s = args.suburb
        d = db[s].find_one({"_id": ObjectId(args.id)})
        if d:
            targets.append((s, d))
    elif args.missing:
        subs = [args.suburb] if args.suburb else SUBURBS
        q = {"listing_status": "for_sale",
             "$or": [{"cadastral_polygon": {"$exists": False}},
                     {"cadastral_polygon.rings": {"$exists": False}}],
             "parcel_backfill_failed": {"$exists": False}}
        for s in subs:
            for d in db[s].find(q).limit(args.limit or 0):
                targets.append((s, d))
    return targets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address")
    ap.add_argument("--id")
    ap.add_argument("--suburb", choices=list(SUBURBS))
    ap.add_argument("--missing", action="store_true",
                    help="all for-sale listings in scope missing a cadastral_polygon")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.id and not args.suburb:
        ap.error("--id requires --suburb")

    db = get_gold_coast_db()
    # On-demand tool: record a heartbeat but do NOT self-register a cadence — nothing
    # schedules it yet, so a cadence would false-alarm STALE on the health board. When
    # this is wired into the /property build stage (or a cron), add cadence_hours here.
    with job_run("backfill_parcel_boundary",
                 title="Parcel Boundary Backfill (on-demand)") as beat:
        targets = collect_targets(db, args)
        print(f"{len(targets)} target(s)")
        counts = {}
        for suburb, doc in targets:
            r = process_doc(db, suburb, doc, force=args.force, dry_run=args.dry_run)
            counts[r] = counts.get(r, 0) + 1
        beat.metrics = counts
        beat.detail = ", ".join(f"{k}={v}" for k, v in counts.items())
        # Rule 7b: if we had work and NOTHING resolved, that is a failure, not success.
        if targets and not args.dry_run and not (counts.get("done") or counts.get("skip")):
            raise RuntimeError(f"processed {len(targets)} targets, 0 boundaries produced: {counts}")


if __name__ == "__main__":
    main()
