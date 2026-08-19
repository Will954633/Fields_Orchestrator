"""
build_public_demo.py — build the PUBLIC, redacted demo report from a real one.

The demo at `/your-home/<demo-slug>` is the one report we deliberately publish
and buy traffic to. Everything else on that route is a private appraisal.

⚠ REDACTION HAPPENS HERE, IN THE DATA, NOT IN THE FRONTEND.

That is the whole point of this module. `property-report.mjs` serves whatever is
stored, so a React-layer blur would leave the real street address sitting in the
JSON payload for anyone who opens the network tab. The document written by this
script must be safe to publish as-is, with no help from the client.

What is redacted, and why each one matters:

  address / slug     the slug IS the address, and `your-home.$slug.tsx` reconstructs
                     the street address from it for the browser-tab title
  lat / lng          three sites (top level, competitor_map.subject,
                     valuation.evidence.subject). The subject pin on both Mapbox
                     maps is an exact pinpoint — this is the strongest single
                     identifier in the document
  comparable numbers street numbers are stripped from comp/competitor/activity
                     addresses. Street NAMES stay: they keep the report credible,
                     and they only narrow to a pocket, not a parcel
  POI distances      banded to ~250 m. "387 m to All Saints" triangulates; "about
                     400 m" does not
  photos             rehosted off Domain's CDN (see mirror_report_photos.py) and
                     the hero is replaced by a blurred derivative
  owner-process      messages / selling_plan / print_appraisal dropped entirely —
                     they are the real submitter's private state

Then `verify_no_residue()` re-reads the OUTPUT and fails closed if any trace of
the source identity survived. Rule 7b applied to a transform: a redactor that
silently redacts nothing is indistinguishable from one that worked, so the
assertion is the deliverable, not the transform.

Usage:
    python3 -m scripts.property_reports.build_public_demo \
        --source-slug 21-royal-links-drive-robina \
        --demo-slug sample-robina-house \
        --label "A 4-bedroom house"          # dry run, prints a diff
    ... --write                              # actually upsert the demo doc
"""
import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone

from shared.db import get_client
from shared.env import load_env

# Distance banding for POIs — metre precision is what pinpoints a parcel.
_POI_BAND_M = 250
# Any stored coordinate within this many degrees of the source is residue
# (~110 m per 0.001 degree at this latitude).
_COORD_EPSILON = 0.02

# Top-level fields carried into the demo. Whitelist, not blacklist: the
# fixture-leak incidents of 2026-08 all came from "copy everything, blank what
# we remember to blank". Anything new added upstream stays out until named here.
_CARRY = [
    "suburb", "suburb_key", "state", "property", "valuation", "slots",
    "activity", "activity_refreshed_at", "scarcity", "market", "buyers",
    "positioning", "process_sections_order", "scarcity_features", "seasonality",
    "case_studies", "slot_status", "pois", "market_narrative",
    "positioning_object", "your_street", "build_state", "schema_version",
]

# Dropped on purpose even though the API would project them: these are the real
# submitter's private process state, not report content.
_DROP = ["messages", "messages_refreshed_at", "selling_plan", "print_appraisal",
         "owner", "occupancy", "analyst_approved_at", "analyst_approved_by"]

_COORD_KEYS = {"lat", "lng", "latitude", "longitude"}
_BANNED_IMAGE_HOSTS = ("domainstatic.com.au", "rimh2.", "b.domainstatic")


def _street_tokens(address):
    """('21 Royal Links Drive, Robina QLD 4226') -> ('21', 'royal links drive')."""
    head = address.split(",")[0].strip()
    m = re.match(r"^(\d+[a-zA-Z]?)\s+(.*)$", head)
    if not m:
        return None, head.lower()
    return m.group(1), m.group(2).lower()


def _strip_street_number(value):
    """'16 Pine Valley Drive' -> 'Pine Valley Drive'. Leaves non-addresses alone."""
    if not isinstance(value, str):
        return value
    return re.sub(r"\b\d+[a-zA-Z]?(?:[-/]\d+[a-zA-Z]?)?\s+(?=[A-Z][a-z])", "", value, count=1)


def _band_metres(m):
    if not isinstance(m, (int, float)) or m <= 0:
        return m
    return int(round(m / _POI_BAND_M) * _POI_BAND_M)


def _walk_mutate(node, fn, path=""):
    """Depth-first mutate every scalar in place via fn(path, key, value)."""
    if isinstance(node, dict):
        for k in list(node.keys()):
            v = node[k]
            if isinstance(v, (dict, list)):
                _walk_mutate(v, fn, f"{path}.{k}" if path else k)
            else:
                node[k] = fn(f"{path}.{k}" if path else k, k, v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, (dict, list)):
                _walk_mutate(v, fn, f"{path}[{i}]")
            else:
                node[i] = fn(f"{path}[{i}]", path.rsplit(".", 1)[-1], v)


def redact(src, demo_slug, label, mirrored_photos=None):
    """Build the public demo document from a real report document."""
    number, street = _street_tokens(src["address"])
    suburb = src.get("suburb") or ""
    postcode = ""
    pm = re.search(r"\b(\d{4})\b", src["address"])
    if pm:
        postcode = pm.group(1)

    out = {k: copy.deepcopy(src[k]) for k in _CARRY if k in src}
    out["slug"] = demo_slug
    # line1 is derived by stripping the suburb/state/postcode tail, so the label
    # must lead and the tail must be present for the frontend split to work.
    out["address"] = f"{label}, {suburb} QLD {postcode}".strip()
    out["is_public_demo"] = True
    out["demo_source_ref"] = None  # deliberately NOT the source slug — see verify
    out["created_at"] = src.get("created_at")
    out["updated_at"] = datetime.now(timezone.utc)
    out["build_state"] = "complete"
    out["state"] = "demo"

    for k in _DROP:
        out.pop(k, None)

    street_re = re.compile(re.escape(street).replace(r"\ ", r"\s+"), re.I)
    full_re = re.compile(
        rf"\b{re.escape(number or '')}\s*{re.escape(street)}\b".replace(r"\ ", r"\s+"), re.I
    ) if number else street_re

    def scrub(path, key, value):
        # Coordinates: remove outright rather than fuzz. A fuzzed pin still draws
        # a circle around the home; an absent pin draws nothing.
        if key in _COORD_KEYS and isinstance(value, (int, float)):
            return None
        if not isinstance(value, str):
            return value
        # Any surviving mention of the subject street becomes the neutral label.
        value = full_re.sub(label.lower().lstrip("a ").strip() or "this home", value)
        value = street_re.sub("this home", value)
        # The source slug can appear inside share URLs / listing links.
        if src["slug"] in value:
            value = value.replace(src["slug"], demo_slug)
        return value

    _walk_mutate(out, scrub)

    # Comparable + competitor + activity addresses: strip the street NUMBER.
    for coll, field in (
        (out.get("comparables", {}).get("closest_active"), "address"),
        (out.get("comparables", {}).get("closest_sold"), "address"),
        (out.get("activity"), "headline"),
        (out.get("activity"), "detail"),
        (out.get("slots", {}).get("recent_comps"), "address"),
        (out.get("valuation", {}).get("comps"), "address"),
        (out.get("valuation", {}).get("evidence", {}).get("comparables"), "address"),
        (out.get("valuation", {}).get("statutory_cma", {}).get("comparables"), "address"),
        (out.get("valuation", {}).get("statutory_cma", {}).get("current_listings"), "address"),
        (out.get("slots", {}).get("competitor_map", {}).get("competitors"), "address"),
    ):
        if isinstance(coll, list):
            for item in coll:
                if isinstance(item, dict) and isinstance(item.get(field), str):
                    item[field] = _strip_street_number(item[field])

    # best_comp is a single object, not a list.
    bc = out.get("slots", {}).get("best_comp")
    if isinstance(bc, dict) and isinstance(bc.get("address"), str):
        bc["address"] = _strip_street_number(bc["address"])

    # Subject pin: drop the whole subject node so the map renders competitors only.
    cm = out.get("slots", {}).get("competitor_map")
    if isinstance(cm, dict):
        cm.pop("subject", None)
    ev = out.get("valuation", {}).get("evidence")
    if isinstance(ev, dict):
        ev.pop("subject", None)

    # POI distances -> bands.
    for poi in out.get("pois") or []:
        if isinstance(poi, dict):
            for k in ("walkMetres", "driveMetres", "metres"):
                if k in poi:
                    poi[k] = _band_metres(poi[k])

    # Photos: swap in the mirrored (self-hosted) set, hero first and blurred.
    if mirrored_photos:
        out.setdefault("property", {})["photos"] = mirrored_photos

    return out


def verify_no_residue(out, src, demo_slug):
    """Fail closed. Returns a list of findings; empty means clean."""
    findings = []
    number, street = _street_tokens(src["address"])
    blob = json.dumps(out, default=str)

    # 1. The street name, in any spacing/casing.
    if re.search(re.escape(street).replace(r"\ ", r"\s+"), blob, re.I):
        findings.append(f"street name {street!r} still present")

    # 2. The source slug.
    if src["slug"] in blob:
        findings.append(f"source slug {src['slug']!r} still present")

    # 3. The full source address string.
    if src["address"].lower() in blob.lower():
        findings.append("full source address still present")

    # 4. Any coordinate near the source, and any surviving coordinate key.
    src_lat, src_lng = src.get("lat"), src.get("lng")
    coords = []

    def collect(path, key, value):
        if key in _COORD_KEYS and isinstance(value, (int, float)):
            coords.append((path, value))
        return value

    _walk_mutate(copy.deepcopy(out), collect)
    for path, value in coords:
        findings.append(f"coordinate survives at {path} = {value}")
    if isinstance(src_lat, (int, float)):
        for m in re.finditer(r"-?\d+\.\d{3,}", blob):
            try:
                v = float(m.group())
            except ValueError:
                continue
            if abs(v - src_lat) < _COORD_EPSILON or abs(v - src_lng) < _COORD_EPSILON:
                findings.append(f"value {v} is within {_COORD_EPSILON} of the source coordinate")
                break

    # 5. Images still served from Domain's CDN.
    for host in _BANNED_IMAGE_HOSTS:
        if host in blob:
            findings.append(f"image host {host!r} still referenced")
            break

    # 6. The demo must actually BE the demo.
    if out.get("slug") != demo_slug:
        findings.append("output slug is not the demo slug")
    if not out.get("is_public_demo"):
        findings.append("is_public_demo flag not set")

    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-slug", required=True)
    ap.add_argument("--demo-slug", required=True)
    ap.add_argument("--label", default="A 4-bedroom house")
    ap.add_argument("--photos-json", help="JSON file of mirrored photo objects")
    ap.add_argument("--write", action="store_true", help="upsert the demo doc")
    args = ap.parse_args()

    load_env()
    db = get_client()["system_monitor"]
    src = db.property_reports.find_one({"slug": args.source_slug})
    if not src:
        sys.exit(f"source report not found: {args.source_slug}")

    photos = None
    if args.photos_json:
        with open(args.photos_json) as fh:
            photos = json.load(fh)

    out = redact(src, args.demo_slug, args.label, photos)
    findings = verify_no_residue(out, src, args.demo_slug)

    print(f"source : {src['slug']}  ({src['address']})")
    print(f"demo   : {out['slug']}  ({out['address']})")
    print(f"fields : {len(out)} top-level, {len(json.dumps(out, default=str))} bytes")
    print()

    if findings:
        print("REDACTION FAILED — residue found:")
        for f in findings:
            print(f"  ✗ {f}")
        sys.exit(1)

    print("✓ residue scan clean")

    if not args.write:
        print("\n(dry run — pass --write to upsert)")
        return

    db.property_reports.update_one(
        {"slug": args.demo_slug}, {"$set": out}, upsert=True
    )
    print(f"\n✓ upserted {args.demo_slug}")


if __name__ == "__main__":
    main()
