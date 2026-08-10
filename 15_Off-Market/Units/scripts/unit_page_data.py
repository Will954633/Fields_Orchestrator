#!/usr/bin/env python3
"""unit_page_data.py — THE single data assembly for an attached dwelling's page.

WHY THIS MODULE EXISTS AT ALL
-----------------------------
There are now two renderers — markdown (`render_unit_report.py`, the review surface)
and HTML (`render_unit_page.py`, the visual prototype) — and a third consumer is coming
(React). If each assembled its own facts they would drift, and one would be maintained.
That is the single most common defect in this codebase: `_toFullRes` duplicated, the
SERP hook read at two shapes, the unit-address test written three times in three
languages, the effective-address chain written three ways. Every one shipped a bug.

So: facts are assembled HERE, once. Renderers format; they never compute.

Sources, all of which are themselves single-definition:
    fact_bundle.build() / emit_v4()   deck engine — POI, rarity, existing copy
    Gold_Coast.complexes              ingest_complexes.py + ingest_storeys.py
    Gold_Coast.unit_market_series     build_unit_market_series.py
    unit_valuation.UnitValuer         unit_valuation.py
    shared.dwelling_type              the classifier
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNITS = HERE.parent
ROOT = UNITS.parent.parent
ENGINE = ROOT / "15_Off-Market" / "Page_Redesign_V2"
for p in (str(ROOT), str(ENGINE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.dwelling_type import classify_dwelling      # noqa: E402
from shared.db import get_client                        # noqa: E402
from unit_valuation import UnitValuer                   # noqa: E402

CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

PROJ = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
        "property_type": 1, "classified_property_type": 1, "PLAN": 1, "LOT": 1,
        "scraped_data.features.property_type": 1, "scraped_data_v2.property_type": 1,
        "PROPERTY_NAME": 1, "UNIT_NUMBER": 1, "bedrooms": 1, "bathrooms": 1,
        "car_spaces": 1, "floor_area_sqm": 1, "internal_living_area_sqm": 1,
        "enriched_data.floor_area_sqm": 1, "enriched_data.transactions": 1,
        "complex_plan": 1, "complex_cms": 1, "complex_name_cadastre": 1,
        "complex_lot_count": 1, "complex_subtype": 1, "listing_status": 1}

# Gaps a renderer may surface. Codes match UNITS_DEVELOPMENT_PLAN.md workstreams.
GAPS = {
    "C2": "no floor area recorded and none imputable from this scheme",
    "C3": "no complex amenity beyond lift — pool, gym, secure parking not stored",
    "E5": "no body-corporate levy — lawful only as an owner's agent (Phase 4)",
    "G1": "copy is the house voice; copy_units_v4.yaml does not exist yet",
}


def effective_address(d):
    """`address || complete_address || street_address`.
    ⚠ Never ADDRESS_STANDARD — it holds the datum code "UK" on 2,952 robina units."""
    return d.get("address") or d.get("complete_address") or d.get("street_address") or ""


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def resolve(address=None, slug=None):
    gc = get_client()["Gold_Coast"]
    if slug:
        for s in CORE_SUBURBS:
            d = gc[s].find_one({"url_slug": slug}, PROJ)
            if d:
                return d, s
        return None, None
    want = _norm(address)
    head = address.split(",")[0].strip()
    for s in CORE_SUBURBS:
        for field in ("address", "complete_address", "street_address"):
            for d in gc[s].find({field: {"$regex": re.escape(head), "$options": "i"}},
                                PROJ).limit(60):
                if want in _norm(effective_address(d)):
                    return d, s
    return None, None


def floor_of(d):
    for k in ("floor_area_sqm", "internal_living_area_sqm"):
        if d.get(k):
            return d[k]
    return (d.get("enriched_data") or {}).get("floor_area_sqm")


def card_of(cards, t):
    for c in cards:
        if c.get("type") == t:
            return c
    return None


def scheme_size(cx):
    """⚠ OUR dwelling count, not the cadastre's parcel count.

    The cadastre holds base parcels, not one polygon per apartment, so it understated
    1,240 of 1,964 schemes — "Greenwich On Riverwalk" read as 2 lots against 53 real
    dwellings. The cadastre figure is kept beside it for provenance."""
    if not cx:
        return None
    return (cx.get("dwellings_in_scheme_data") or cx.get("scheme_lot_count")
            or cx.get("lot_count"))


def assemble(address=None, slug=None):
    """Everything a renderer needs, in one dict. Raises LookupError if unresolvable."""
    doc, suburb = resolve(address, slug)
    if not doc:
        raise LookupError(f"no document for {address or slug}")
    slug = doc.get("url_slug")
    if not slug:
        raise LookupError("document has no url_slug")

    gc = get_client()["Gold_Coast"]
    notes = []

    bundle, cards = None, []
    try:
        import fact_bundle
        import emit_v4 as E4
        bundle = fact_bundle.build(slug, suburb)
        (fact_bundle.BUNDLE_DIR / f"{slug}.json").write_text(
            json.dumps(bundle, indent=2, default=str))
        cards = (E4.emit_v4(slug) or {}).get("cards") or []
    except SystemExit as e:
        notes.append(f"deck engine refused: {e}")
    except Exception as e:
        notes.append(f"deck engine raised {type(e).__name__}: {e}")

    cx = (gc["complexes"].find_one({"_id": f"{suburb}:{doc.get('complex_plan')}"})
          if doc.get("complex_plan") else None)
    mkt = gc["unit_market_series"].find_one({"_id": suburb}) or {}
    V = UnitValuer(gc, suburb)

    floor = floor_of(doc)
    imputed = V.impute_floor_area(doc) if not floor else None

    gaps = []
    if not floor and not imputed:
        gaps.append("C2")
    if not (cx and cx.get("lift_inferred")):
        gaps.append("C3")
    else:
        gaps.append("C3")          # amenity beyond lift is still absent everywhere
    gaps.append("E5")
    gaps.append("G1")

    return {
        "slug": slug,
        "suburb_key": suburb,
        "suburb": (suburb or "").replace("_", " ").title(),
        "address": effective_address(doc),
        "dwelling_class": classify_dwelling(
            {**doc, "street_address": effective_address(doc)}),
        "bedrooms": doc.get("bedrooms"),
        "bathrooms": doc.get("bathrooms"),
        "car_spaces": doc.get("car_spaces"),
        "floor_area": floor,
        "floor_area_imputed": imputed,
        "lot": doc.get("LOT"),
        "complex": cx,
        "scheme_size": scheme_size(cx),
        "market": mkt,
        "valuation": V.value(doc),
        "bundle": bundle or {},
        "cards": cards,
        "proximity": (bundle or {}).get("proximity") or {},
        "scarcity": (bundle or {}).get("scarcity") or {},
        "dispersion_card": card_of(cards, "dispersion"),
        "control_card": card_of(cards, "control"),
        "gaps": sorted(set(gaps)),
        "notes": notes,
    }
