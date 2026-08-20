#!/usr/bin/env python3
"""scripts/property_dossier.py — single-property dossier + contradiction report.

READ-ONLY. Never writes to any property document.

Given one property (by --address / --id / --slug) this prints a compact,
complete dossier AND a ranked "contradiction report": the automatic pass that
would have caught 93 Burleigh Street's data problems on day one instead of by
eye — three different floor areas (203/220/331), alfresco_present=false while
the floor plan lists a "Covered Alfresco", car spaces stored as both 2 and 4,
a non-numeric price masking a numeric history, and "Under Negotiation" copy on a
still-for_sale listing.

Design notes / rules honoured
-----------------------------
* Rule 8 (no guessed field names): every field path below was verified against a
  live document with scripts/db_fields.py before being read. Where a source is
  absent the check reports "not present", never "data missing".
* Rule 7b (assert an outcome): the contradiction report ALWAYS states how many
  checks ran. Zero contradictions prints "no contradictions detected across N
  checks", never an empty section — so "clean" is distinguishable from "the
  checker did nothing".
* Rule 5 (no advice / factual): the dossier reports figures and their provenance;
  it never tells a reader what to do.

Reuses shared helpers rather than reinventing:
  shared.floor_area.resolve_internal_floor_area / resolve_building_area
  shared.block_geometry.compute_block_geometry
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_client
from shared.floor_area import resolve_internal_floor_area, resolve_building_area
from shared.block_geometry import compute_block_geometry

try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None

DB_NAME = "Gold_Coast"
SCRATCH = os.environ.get(
    "CLAUDE_SCRATCH",
    "/tmp/claude-1001/-home-fields-Fields-Orchestrator/"
    "545fb342-e0c9-4a83-8bdf-e8c189e850c8/scratchpad",
)

# Collections in Gold_Coast that are NOT suburb property collections.
_NON_PROPERTY_COLLS = {
    "address_search_index",
    "system.views",
}

_UNDER_CONTRACT_PATTERNS = re.compile(
    r"under\s*(?:contract|offer|negotiation)|going\s*under\s*contract",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# small utilities
# --------------------------------------------------------------------------- #
def dig(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def as_float(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def first_numeric_in(text):
    """First plausible dollar figure inside a free-text string, else None."""
    if not isinstance(text, str):
        return None
    m = re.search(r"\$?\s*([0-9][0-9,]{4,})", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def pct_gap(a, b):
    if not a or not b:
        return None
    return abs(a - b) / max(a, b)


# --------------------------------------------------------------------------- #
# lookup
# --------------------------------------------------------------------------- #
def property_collections(db):
    return [
        c
        for c in db.list_collection_names()
        if c not in _NON_PROPERTY_COLLS and not c.startswith("system.")
    ]


def find_property(db, address=None, _id=None, slug=None):
    """Return (collection_name, doc) or (None, None)."""
    colls = property_collections(db)

    if _id:
        query = None
        if ObjectId is not None:
            try:
                query = {"_id": ObjectId(_id)}
            except Exception:
                query = {"_id": _id}
        else:
            query = {"_id": _id}
        for c in colls:
            d = db[c].find_one(query)
            if d:
                return c, d
        return None, None

    if slug:
        for field in ("url_slug", "slug"):
            for c in colls:
                d = db[c].find_one({field: slug})
                if d:
                    return c, d
        return None, None

    if address:
        # Prefer live listings; fall back to any match.
        rx = {"$regex": re.escape(address.strip()), "$options": "i"}
        best = None
        for c in colls:
            for d in db[c].find({"address": rx}).limit(5):
                if d.get("listing_status") == "for_sale":
                    return c, d
                if best is None:
                    best = (c, d)
        if best:
            return best
        return None, None

    return None, None


# --------------------------------------------------------------------------- #
# contradiction checks
# --------------------------------------------------------------------------- #
def _room_names(doc):
    out = []
    pr = doc.get("parsed_rooms") or {}
    if isinstance(pr, dict):
        for v in pr.values():
            if isinstance(v, dict) and v.get("room_name"):
                out.append(str(v["room_name"]))
    return out


def check_floor_area(doc):
    """Floor-area disagreement across internal sources + total-as-internal leaks."""
    findings = []

    internal_val, internal_src, internal_conflict = resolve_internal_floor_area(doc)
    building_val, building_src = resolve_building_area(doc)

    # Gather every internal-labelled source that is present.
    internal_sources = {
        "scraped_data_v2.internal_area_sqm": as_float(dig(doc, "scraped_data_v2.internal_area_sqm")),
        "onthehouse_data.floor_area_sqm": as_float(dig(doc, "onthehouse_data.floor_area_sqm")),
        "processing_status.internal_floor_area_sqm": as_float(dig(doc, "processing_status.internal_floor_area_sqm")),
        "floor_plan_analysis.internal_floor_area.value": as_float(dig(doc, "floor_plan_analysis.internal_floor_area.value")),
    }
    internal_sources = {k: v for k, v in internal_sources.items() if v}

    # 1) internal-vs-internal disagreement > 15%
    vals = list(internal_sources.items())
    worst = None
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            g = pct_gap(vals[i][1], vals[j][1])
            if g and g > 0.15 and (worst is None or g > worst[0]):
                worst = (g, vals[i], vals[j])
    if worst:
        g, (n1, v1), (n2, v2) = worst
        findings.append(
            {
                "severity": "high",
                "kind": "floor_area_internal_disagreement",
                "detail": (
                    f"internal-area sources disagree by {g*100:.0f}%: "
                    f"{n1}={v1:g} vs {n2}={v2:g}"
                ),
                "values": {n: v for n, v in internal_sources.items()},
            }
        )
    if internal_conflict and not worst:
        findings.append(
            {
                "severity": "medium",
                "kind": "floor_area_resolver_conflict",
                "detail": (
                    f"resolve_internal_floor_area flags a conflict; best="
                    f"{internal_val:g} ({internal_src})"
                ),
            }
        )

    # 1b) modest internal spread (5-15%) — below the hard-conflict bar but worth
    #     surfacing. On 93 Burleigh this is the residual 203 (Domain/onthehouse)
    #     vs 220 (photo-analysis internal) after today's enriched_data correction.
    if len(vals) > 1 and not worst:
        lo = min(v for _, v in vals)
        hi = max(v for _, v in vals)
        spread = pct_gap(lo, hi)
        if spread and 0.05 < spread <= 0.15:
            detail = (
                f"internal-area sources span {lo:g}-{hi:g} sqm ({spread*100:.0f}%): "
                + ", ".join(f"{n}={v:g}" for n, v in vals)
            )
            if building_val:
                detail += (
                    f"; a separate building total of {building_val:g} sqm "
                    f"({building_src}) also exists on file"
                )
            findings.append(
                {
                    "severity": "low",
                    "kind": "floor_area_internal_spread",
                    "detail": detail,
                    "values": {n: v for n, v in internal_sources.items()},
                }
            )

    # 2) a consumer / display field carrying a building TOTAL where internal is expected.
    #    A total (incl. carport + alfresco) leaking into an "internal" field.
    consumer_fields = {
        "enriched_data.floor_area_sqm": as_float(dig(doc, "enriched_data.floor_area_sqm")),
        "floor_area_sqm": as_float(dig(doc, "floor_area_sqm")),
        "total_floor_area": as_float(dig(doc, "total_floor_area")),
    }
    if building_val and internal_val:
        for fname, fval in consumer_fields.items():
            if not fval:
                continue
            # field holds (approximately) the building total, not the internal figure
            if (
                pct_gap(fval, building_val) is not None
                and pct_gap(fval, building_val) < 0.05
                and pct_gap(fval, internal_val) is not None
                and pct_gap(fval, internal_val) > 0.15
                and fname != "total_floor_area"  # total_floor_area is meant to be a total
            ):
                findings.append(
                    {
                        "severity": "high",
                        "kind": "total_as_internal",
                        "detail": (
                            f"{fname}={fval:g} matches the building TOTAL "
                            f"({building_src}={building_val:g}) not the internal living "
                            f"area ({internal_src}={internal_val:g}) — a total is being "
                            f"consumed where internal is expected"
                        ),
                    }
                )
    return findings


def check_alfresco(doc):
    findings = []
    alfresco_present = dig(doc, "property_valuation_data.outdoor.alfresco_present")
    rooms = _room_names(doc)
    alfresco_rooms = [
        r for r in rooms if re.search(r"alfresco|deck|patio|pergola", r, re.I)
    ]
    fp_count = len(doc.get("floor_plans") or [])
    if alfresco_present is False and alfresco_rooms:
        findings.append(
            {
                "severity": "high",
                "kind": "alfresco_boolean_vs_plan",
                "detail": (
                    "property_valuation_data.outdoor.alfresco_present=false but the "
                    f"floor plan lists {alfresco_rooms} "
                    f"({fp_count} floor plan(s) on file)"
                ),
            }
        )
    return findings


def check_fence(doc):
    findings = []
    fence_type = dig(doc, "property_valuation_data.exterior.fence_type")
    if not (isinstance(fence_type, str) and fence_type.lower() == "none"):
        return findings
    # Positive fence / enclosed-yard signal from plan text, room names, satellite
    # narrative or the agent description.
    signals = []
    for rn in _room_names(doc):
        if re.search(r"\bfenc|enclosed yard|fenced yard", rn, re.I):
            signals.append(f"parsed_rooms room_name '{rn}'")
    for path in (
        "satellite_analysis.narrative.lot_assessment",
        "satellite_analysis.narrative.buyer_highlights",
        "agents_description",
    ):
        v = dig(doc, path)
        if isinstance(v, list):
            v = " ".join(str(x) for x in v)
        if isinstance(v, str) and re.search(r"\bfenced\b|fully fenced|fenced yard", v, re.I):
            signals.append(f"{path} mentions a fence")
    if signals:
        findings.append(
            {
                "severity": "medium",
                "kind": "fence_boolean_vs_plan",
                "detail": (
                    "property_valuation_data.exterior.fence_type='none' but a fence "
                    f"is described elsewhere: {signals}"
                ),
            }
        )
    return findings


def check_car_spaces(doc):
    findings = []
    sources = {
        "car_spaces": as_float(dig(doc, "car_spaces")),
        "carspaces": as_float(dig(doc, "carspaces")),
        "scraped_data.features.car_spaces": as_float(dig(doc, "scraped_data.features.car_spaces")),
        "property_insights.parking.value": as_float(dig(doc, "property_insights.parking.value")),
    }
    present = {k: int(v) for k, v in sources.items() if v is not None}
    distinct = set(present.values())
    if len(distinct) > 1:
        findings.append(
            {
                "severity": "medium",
                "kind": "car_spaces_disagreement",
                "detail": (
                    "car-space count disagrees across sources: "
                    + ", ".join(f"{k}={v}" for k, v in present.items())
                ),
                "values": present,
            }
        )
    return findings


def check_stale_copy(doc):
    findings = []
    status = doc.get("listing_status")
    if status != "for_sale":
        return findings
    tags = doc.get("tags") or []
    has_uc_tag = any("under_contract" in str(t).lower() for t in tags) if isinstance(tags, list) else False
    for field in ("agents_description", "description"):
        text = doc.get(field)
        if isinstance(text, str) and _UNDER_CONTRACT_PATTERNS.search(text):
            m = _UNDER_CONTRACT_PATTERNS.search(text)
            findings.append(
                {
                    "severity": "high" if not has_uc_tag else "low",
                    "kind": "stale_under_contract_copy",
                    "detail": (
                        f"listing_status='for_sale' but {field} says "
                        f"\"...{text[max(0,m.start()-10):m.start()+40].strip()}...\""
                        + ("" if has_uc_tag else " and no under_contract tag is set")
                    ),
                }
            )
            break
    return findings


def check_price(doc):
    findings = []
    price = doc.get("price")
    price_is_numeric = as_float(price) is not None or first_numeric_in(str(price)) is not None
    if isinstance(price, str) and as_float(price) is None and first_numeric_in(price) is None:
        # non-numeric headline price — is there a numeric anywhere in history?
        numeric_hist = None
        for ev in doc.get("price_history") or []:
            pn = ev.get("price_numeric") if isinstance(ev, dict) else None
            if pn:
                numeric_hist = (pn, ev.get("recorded_at"))
        if numeric_hist:
            findings.append(
                {
                    "severity": "low",
                    "kind": "non_numeric_price_vs_history",
                    "detail": (
                        f"price='{price}' carries no figure, but price_history holds a "
                        f"numeric ${int(numeric_hist[0]):,} (recorded {numeric_hist[1]})"
                    ),
                }
            )
    return findings


def check_geometry(doc):
    findings = []
    geom = compute_block_geometry(doc.get("cadastral_polygon"))
    if not geom:
        return findings
    shape = geom.get("shape_label")
    if shape and shape != "rectangular":
        claim_text = " ".join(
            str(dig(doc, p) or "")
            for p in ("agents_description", "description")
        )
        # satellite lot assessment can also claim regularity
        claim_text += " " + str(dig(doc, "satellite_analysis.narrative.lot_assessment") or "")
        if re.search(r"\brectangular\b", claim_text, re.I):
            findings.append(
                {
                    "severity": "medium",
                    "kind": "geometry_vs_claim",
                    "detail": (
                        f"cadastre measures shape='{shape}' "
                        f"(rectangularity={geom.get('rectangularity')}, "
                        f"edges={geom.get('edges_m')}) but copy calls the block "
                        f"'rectangular'"
                    ),
                }
            )
    return findings


CHECKS = [
    ("floor_area", check_floor_area),
    ("alfresco_boolean_vs_plan", check_alfresco),
    ("fence_boolean_vs_plan", check_fence),
    ("car_spaces", check_car_spaces),
    ("stale_listing_copy", check_stale_copy),
    ("price_vs_history", check_price),
    ("geometry_vs_claim", check_geometry),
]

_SEV_RANK = {"high": 0, "medium": 1, "low": 2}


def run_contradiction_checks(doc):
    all_findings = []
    for name, fn in CHECKS:
        try:
            all_findings.extend(fn(doc))
        except Exception as e:  # a broken check must not hide the others
            all_findings.append(
                {
                    "severity": "medium",
                    "kind": f"{name}_check_error",
                    "detail": f"check '{name}' raised {type(e).__name__}: {e}",
                }
            )
    all_findings.sort(key=lambda f: _SEV_RANK.get(f.get("severity"), 3))
    return all_findings, len(CHECKS)


# --------------------------------------------------------------------------- #
# dossier assembly
# --------------------------------------------------------------------------- #
def build_dossier(coll, doc):
    internal_val, internal_src, internal_conflict = resolve_internal_floor_area(doc)
    building_val, building_src = resolve_building_area(doc)
    geom = compute_block_geometry(doc.get("cadastral_polygon"))
    pvd = doc.get("property_valuation_data") or {}
    zoning = doc.get("zoning_data") or {}

    pois = doc.get("nearby_pois") or {}
    poi_highlights = {}
    by_cat = pois.get("by_category") if isinstance(pois, dict) else None
    if isinstance(by_cat, dict):
        for cat, items in by_cat.items():
            if items:
                nearest = min(items, key=lambda x: x.get("distance_km", 9e9))
                poi_highlights[cat] = f"{nearest.get('name')} ({nearest.get('distance_km')}km)"

    txns = doc.get("transactions") or []
    price_hist = doc.get("price_history") or []

    return {
        "_id": str(doc.get("_id")),
        "collection": coll,
        "identity": {
            "address": doc.get("address"),
            "suburb": doc.get("suburb"),
            "postcode": doc.get("postcode") or doc.get("display_postcode"),
            "url_slug": doc.get("url_slug"),
            "listing_status": doc.get("listing_status"),
            "property_type": doc.get("classified_property_type") or doc.get("property_type"),
            "bedrooms": doc.get("bedrooms"),
            "bathrooms": doc.get("bathrooms"),
            "lot_plan": zoning.get("lot_plan") or dig(doc, "cadastral_polygon.lotplan"),
            "lot_size_sqm": doc.get("lot_size_sqm") or dig(doc, "cadastral_polygon.lot_area_sqm"),
            "year_built": doc.get("year_built"),
            "last_updated": str(doc.get("last_updated")),
        },
        "floor_area": {
            "internal_resolved_sqm": internal_val,
            "internal_source": internal_src,
            "internal_conflict": internal_conflict,
            "building_total_sqm": building_val,
            "building_source": building_src,
        },
        "block_geometry": geom,
        "condition_summary": {
            "condition_summary_text": pvd.get("condition_summary"),
            "exterior": pvd.get("exterior"),
            "outdoor": pvd.get("outdoor"),
            "renovation": pvd.get("renovation"),
        },
        "nearby_pois": poi_highlights,
        "transactions": txns,
        "price": {
            "current_price_field": doc.get("price"),
            "price_history": price_hist,
        },
        "zoning": {
            "zone": zoning.get("zone"),
            "zone_detail": zoning.get("zone_detail"),
            "flood_overlay": zoning.get("flood_overlay"),
            "flood_description": zoning.get("flood_description"),
            "flood_designated_level_m": zoning.get("flood_designated_level_m"),
        },
        "media": {
            "property_images": len(doc.get("property_images") or []),
            "floor_plans": len(doc.get("floor_plans") or []),
            "aerial_boundary_url": bool(doc.get("aerial_boundary_url")),
            "satellite_analysis": bool(doc.get("satellite_analysis")),
        },
        "ai_analysis": {
            "status": dig(doc, "ai_analysis.status"),
            "headline": dig(doc, "ai_analysis.headline"),
            "generated_at": dig(doc, "ai_analysis.generated_at"),
        },
    }


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _hr(title):
    return f"\n{'='*72}\n{title}\n{'='*72}"


def render(dossier, findings, n_checks):
    L = []
    idn = dossier["identity"]
    L.append(_hr("PROPERTY DOSSIER"))
    L.append(f"{idn['address']}")
    L.append(
        f"  {idn['property_type']} | {idn['bedrooms']} bed / {idn['bathrooms']} bath | "
        f"status={idn['listing_status']} | {dossier['collection']}/{dossier['_id']}"
    )
    L.append(
        f"  lot_plan={idn['lot_plan']} | lot_size={idn['lot_size_sqm']} sqm | "
        f"year_built={idn['year_built']} | last_updated={idn['last_updated']}"
    )
    L.append(f"  slug={idn['url_slug']}")

    fa = dossier["floor_area"]
    L.append(_hr("FLOOR AREA"))
    L.append(
        f"  internal (resolved): {fa['internal_resolved_sqm']} sqm  "
        f"[source={fa['internal_source']}, conflict={fa['internal_conflict']}]"
    )
    L.append(
        f"  building total:      {fa['building_total_sqm']} sqm  "
        f"[source={fa['building_source']}]"
    )

    g = dossier["block_geometry"]
    L.append(_hr("BLOCK GEOMETRY"))
    if g:
        L.append(
            f"  area={g['area_sqm']} sqm | frontage~{g['frontage_m_est']}m | "
            f"depth~{g['depth_m_est']}m"
        )
        L.append(
            f"  shape={g['shape_label']} (rectangularity={g['rectangularity']}) | "
            f"edges_m={g['edges_m']}"
        )
    else:
        L.append("  no cadastral_polygon on file")

    cs = dossier["condition_summary"]
    L.append(_hr("CONDITION"))
    if cs.get("condition_summary_text"):
        L.append(f"  {str(cs['condition_summary_text'])[:300]}")
    ext = cs.get("exterior") or {}
    out = cs.get("outdoor") or {}
    L.append(
        f"  exterior: cladding={ext.get('cladding_material')}/{ext.get('cladding_condition')} "
        f"| garage={ext.get('garage_type')} | fence={ext.get('fence_type')}"
    )
    L.append(
        f"  outdoor: pool={out.get('pool_present')} | alfresco={out.get('alfresco_present')} "
        f"| water_views={out.get('water_views')}"
    )

    L.append(_hr("NEARBY"))
    if dossier["nearby_pois"]:
        for cat, v in list(dossier["nearby_pois"].items())[:8]:
            L.append(f"  {cat}: {v}")
    else:
        L.append("  no nearby_pois on file")

    L.append(_hr("TRANSACTIONS"))
    for t in dossier["transactions"]:
        L.append(f"  {t.get('date')}  ${t.get('price'):,}  ({t.get('source')})" if t.get("price") else f"  {t}")
    if not dossier["transactions"]:
        L.append("  none on file")

    L.append(_hr("PRICE"))
    L.append(f"  current price field: {dossier['price']['current_price_field']!r}")
    for ev in dossier["price"]["price_history"]:
        L.append(
            f"    {ev.get('recorded_at')}  {ev.get('price_text')!r}  "
            f"num={ev.get('price_numeric')}"
        )

    z = dossier["zoning"]
    L.append(_hr("ZONING / FLOOD"))
    L.append(f"  zone={z['zone']} ({z['zone_detail']})")
    L.append(
        f"  flood_overlay={z['flood_overlay']} | {z['flood_description']} | "
        f"designated_level={z['flood_designated_level_m']}m"
    )

    m = dossier["media"]
    ai = dossier["ai_analysis"]
    L.append(_hr("MEDIA / AI"))
    L.append(
        f"  images={m['property_images']} | floor_plans={m['floor_plans']} | "
        f"aerial={m['aerial_boundary_url']} | satellite={m['satellite_analysis']}"
    )
    L.append(f"  ai_analysis: status={ai['status']} | generated_at={ai['generated_at']}")
    if ai.get("headline"):
        L.append(f"    headline: {ai['headline']}")

    # ---- contradiction report ------------------------------------------- #
    L.append(_hr("CONTRADICTION REPORT"))
    if findings:
        L.append(f"  {len(findings)} contradiction(s) found across {n_checks} checks:")
        for i, f in enumerate(findings, 1):
            L.append(f"\n  [{i}] ({f['severity'].upper()}) {f['kind']}")
            L.append(f"      {f['detail']}")
    else:
        L.append(f"  no contradictions detected across {n_checks} checks.")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Single-property dossier + contradiction report (read-only).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--address")
    g.add_argument("--id")
    g.add_argument("--slug")
    ap.add_argument("--json", action="store_true", help="also write a structured dossier JSON to the scratchpad")
    args = ap.parse_args()

    client = get_client()
    db = client[DB_NAME]

    coll, doc = find_property(db, address=args.address, _id=args.id, slug=args.slug)
    if not doc:
        target = args.address or args.id or args.slug
        print(f"ERROR: no property found for {target!r} in {DB_NAME}", file=sys.stderr)
        sys.exit(2)

    dossier = build_dossier(coll, doc)
    findings, n_checks = run_contradiction_checks(doc)

    print(render(dossier, findings, n_checks))

    if args.json:
        os.makedirs(SCRATCH, exist_ok=True)
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dossier": dossier,
            "contradiction_report": {
                "checks_run": n_checks,
                "contradictions_found": len(findings),
                "findings": findings,
            },
        }
        slug = (dossier["identity"].get("url_slug") or dossier["_id"])
        path = os.path.join(SCRATCH, f"dossier_{slug}.json")
        with open(path, "w") as fh:
            json.dump(out, fh, indent=2, default=str)
        print(f"\n[json written] {path}")


if __name__ == "__main__":
    main()
