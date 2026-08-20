#!/usr/bin/env python3
"""ingest_cityplan_report.py — parse a Gold Coast City Plan property report and
compute the derived development signals (Conjunction Program Tier 3.1).

Two ways in, because the parcel City Plan web UI 403s automated access, so a human
generates the PDF from the "City Plan online" link:

  # From the Council property-report PDF a human downloaded:
  python3 scripts/ingest_cityplan_report.py --pdf "/path/property report-187RP128164.pdf" \
      --slug 93-burleigh-street-burleigh-waters [--land 822 --frontage 19.9] [--store]

  # Or feed the layers directly (e.g. from a manual read), no PDF needed:
  python3 scripts/ingest_cityplan_report.py --layers-json '{...}' --slug ... [--store]

It extracts the mapping layers, runs shared.planning_signals.assess_planning(), prints
the verdict, and (with --store) writes them to the property's `zoning_data.cityplan`.

⚠ The PDF text extraction is keyed off the documented City Plan report layer names and
needs a real sample PDF to finalise the regexes — until then, values it can't find are
left None (honest unknown, Rule 7b) and can be supplied via CLI flags or --layers-json.
Nothing is guessed. Development facts are heuristics to guide investigation, never advice.
"""
import argparse
import json
import re
import sys

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.planning_signals import assess_planning  # noqa: E402


# Layer-name -> (regex to find it in the report text, how to interpret).
# "present" layers: the report LISTS a layer when it applies; absence => False.
_PRESENCE_LAYERS = {
    "residential_density_overlay": r"residential density",
    "minimum_lot_size_overlay": r"minimum lot size",
    "dwelling_house_overlay": r"dwelling house overlay",
    "flood_assessment_required": r"flood[^\n]{0,30}(assessment required|overlay)",
    "acid_sulfate_soils": r"acid sulfate soil",
}


def _extract_pdf_text(pdf_path: str) -> str:
    try:
        import fitz  # pymupdf
    except ImportError:
        raise SystemExit("pymupdf (fitz) not available — install it or use --layers-json")
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def parse_layers_from_text(text: str) -> dict:
    """Best-effort extraction of City Plan layers from report text.

    Presence layers: True if the layer name appears in the report's applicable-content
    list, else False. Zone and area parsed by pattern. Anything genuinely ambiguous is
    left None so the caller/flags can supply it — never guessed.
    """
    low = text.lower()
    layers = {}

    m = re.search(r"(low density residential|medium density residential|"
                  r"high density residential|community facilities|centre)[^\n]*zone", low)
    layers["zone"] = m.group(0).strip() if m else None

    m = re.search(r"(\d{3,5}(?:\.\d+)?)\s*m(?:2|²|\^2)\b", text)
    layers["land_area_sqm"] = float(m.group(1)) if m else None

    for key, pat in _PRESENCE_LAYERS.items():
        layers[key] = bool(re.search(pat, low))

    # Development.i "Nil" applications — only trust it if the report says so explicitly.
    if re.search(r"applications associated with this property[^\n]{0,40}nil", low):
        layers["da_applications_nil"] = True

    # Residential Density CODE if a report happens to spell it (RD1/RD2/...).
    m = re.search(r"\brd([1-9])\b", low)
    if m:
        layers["residential_density_overlay"] = True
        layers["residential_density_code"] = "RD" + m.group(1)

    return layers


def main():
    ap = argparse.ArgumentParser(description="Ingest a City Plan property report -> planning signals")
    ap.add_argument("--pdf", help="path to the Council property-report PDF")
    ap.add_argument("--layers-json", help="JSON of layers, bypassing PDF parsing")
    ap.add_argument("--slug", help="property url_slug, for --store")
    ap.add_argument("--id", help="property _id, for --store")
    ap.add_argument("--suburb", help="suburb collection, for --store")
    ap.add_argument("--land", type=float, help="override land_area_sqm")
    ap.add_argument("--frontage", type=float, help="override frontage_m")
    ap.add_argument("--dual-frontage", dest="dual_frontage", action="store_true")
    ap.add_argument("--store", action="store_true", help="write zoning_data.cityplan to the property doc")
    args = ap.parse_args()

    if args.layers_json:
        layers = json.loads(args.layers_json)
    elif args.pdf:
        text = _extract_pdf_text(args.pdf)
        layers = parse_layers_from_text(text)
    else:
        raise SystemExit("Provide --pdf or --layers-json")

    if args.land is not None:
        layers["land_area_sqm"] = args.land
    if args.frontage is not None:
        layers["frontage_m"] = args.frontage
    if args.dual_frontage:
        layers["dual_frontage"] = True

    result = assess_planning(layers)

    print("=== PARSED LAYERS ===")
    for k, v in result["inputs"].items():
        print(f"  {k}: {v}")
    print("\n=== DERIVED SIGNALS ===")
    for k, v in result["signals"].items():
        print(f"  {k}: {v}")
    print("\n=== FLAGS ===")
    for f in result["flags"]:
        print("  -", f)
    print("\n=== VERDICT ===")
    print(" ", result["verdict"])
    print("\n" + result["caveat"])

    if args.store:
        if not (args.slug or args.id):
            raise SystemExit("--store needs --slug or --id")
        from shared.db import get_client
        try:
            from src.mongo_client_factory import cosmos_retry
        except Exception:
            def cosmos_retry(fn, *a, **k):
                return fn(*a, **k)
        db = get_client()["Gold_Coast"]
        q = {"url_slug": args.slug} if args.slug else {"_id": args.id}
        suburbs = [args.suburb] if args.suburb else [c for c in db.list_collection_names()]
        wrote = 0
        from datetime import datetime, timezone
        payload = {"zoning_data.cityplan": {
            "layers": result["inputs"], "signals": result["signals"],
            "flags": result["flags"], "verdict": result["verdict"],
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }}
        for s in suburbs:
            if db[s].find_one(q, {"_id": 1}):
                cosmos_retry(db[s].update_one, q, {"$set": payload})
                wrote += 1
                print(f"\n✓ stored to Gold_Coast.{s}")
                break
        if wrote == 0:
            raise SystemExit("no matching property found to --store")


if __name__ == "__main__":
    main()
