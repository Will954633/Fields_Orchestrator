#!/usr/bin/env python3
"""
canonical_resolver.py — resolve each property's fragmented attribute fields
into a single canonical golden record WITH provenance.

The same fact lives in several fields across a property doc (floor area in 4+
places, pool in 2+, etc.), none authoritative. This resolver reads the ordered
source_priority for each attribute from config/canonical_attributes.yaml, takes
the first present value, and records which source field / method / model
produced it — so any client-facing statement is reproducible and defensible.

Golden records are written to Gold_Coast.property_attributes (one per property),
keyed by the source _id. The scarcity / positioning engines then query this one
clean collection instead of probing fragmented fields.

Usage:
  python3 scripts/property_reports/canonical_resolver.py --address "39 Manakin Avenue, Burleigh Waters QLD 4220"
  python3 scripts/property_reports/canonical_resolver.py --suburb robina --dry-run
  python3 scripts/property_reports/canonical_resolver.py --all-sample           # all members of latest manifest
  python3 scripts/property_reports/canonical_resolver.py --all-sample --sample-id sample_403617662ea8
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared.db import get_client, get_gold_coast_db  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPEC_PATH = REPO_ROOT / "config" / "canonical_attributes.yaml"
ATTR_COLLECTION = "property_attributes"


# ----------------------------------------------------------------------------- spec
def load_spec() -> Dict[str, Any]:
    with open(SPEC_PATH) as f:
        return yaml.safe_load(f)


# ----------------------------------------------------------------------------- helpers
def _dig(doc: Dict[str, Any], dotted: str) -> Any:
    """Walk a dotted path; return None if any segment is missing/non-dict."""
    cur: Any = doc
    for seg in dotted.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return None
        cur = cur[seg]
    return cur


def _coerce(value: Any, typ: str) -> Optional[Any]:
    """Coerce a raw source value into the declared canonical type.
    Handles the dict-or-scalar shapes seen in the data (e.g. a score field
    that is sometimes {'overall_score': 8} and sometimes 8)."""
    if value is None:
        return None
    # Some score fields arrive as a dict — pull the obvious scalar.
    if isinstance(value, dict):
        for k in ("overall_score", "value", "score"):
            if k in value:
                value = value[k]
                break
        else:
            return None
    if typ == "bool":
        return bool(value)
    if typ in ("int", "float"):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return int(value) if typ == "int" else float(value)
        if isinstance(value, str):
            try:
                f = float(value.replace(",", "").strip())
                return int(f) if typ == "int" else f
            except (TypeError, ValueError):
                return None
        return None
    return value  # str / other passthrough


def resolve_attribute(doc: Dict[str, Any], name: str, spec: Dict[str, Any],
                      method_conf: Dict[str, float]) -> Dict[str, Any]:
    """Resolve one attribute → {value, _prov{...}} walking source_priority."""
    typ = spec.get("type", "str")
    for src in spec.get("source_priority", []):
        raw = _dig(doc, src["path"])
        val = _coerce(raw, typ)
        if val is not None:
            method = src["method"]
            return {
                "value": val,
                "_prov": {
                    "source_field": src["path"],
                    "method": method,
                    "model": _model_for(doc, method),
                    "confidence": method_conf.get(method, 0.5),
                    "raw": raw if not isinstance(raw, (dict, list)) else None,
                },
            }
    return {"value": None,
            "_prov": {"source_field": None, "method": "unavailable",
                      "model": None, "confidence": 0.0, "raw": None}}


def _model_for(doc: Dict[str, Any], method: str) -> Optional[str]:
    """Best-effort model attribution for a method, read from the doc itself."""
    ps = doc.get("processing_status") or {}
    if method.startswith("gpt_floorplan") or method == "gpt_photo":
        return ps.get("model_used")
    if method == "gpt_satellite":
        return ((doc.get("satellite_analysis") or {}).get("model")
                or "claude-opus-4-8")
    return None


def _apply_sanity(canon: Dict[str, Dict[str, Any]]) -> None:
    """floor_area_land_flip: a 'floor area' > 500 with no land is the known
    Domain anomaly where land was captured into floor_area. Flip it, and mark
    provenance so the correction is auditable."""
    fa = canon.get("floor_area_sqm", {})
    ls = canon.get("land_size_sqm", {})
    if (fa.get("value") and fa["value"] > 500 and not ls.get("value")):
        canon["land_size_sqm"] = {
            "value": fa["value"],
            "_prov": {**fa["_prov"], "method": "derived",
                      "note": "floor_area_land_flip (anomaly correction)"},
        }
        canon["floor_area_sqm"] = {
            "value": None,
            "_prov": {"source_field": None, "method": "unavailable",
                      "model": None, "confidence": 0.0,
                      "note": "floor_area_land_flip (anomaly correction)"},
        }


# ----------------------------------------------------------------------------- thresholds
def compute_threshold_hits(canon: Dict[str, Dict[str, Any]],
                           spec: Dict[str, Any]) -> List[Dict[str, str]]:
    """Which scarcity threshold keys this property satisfies (de-duped for
    supersedes). Mirrors scarcity_features.FEATURE_RULES semantics."""
    hits: List[Dict[str, str]] = []
    superseded: set = set()

    for name, adef in spec["attributes"].items():
        val = canon.get(name, {}).get("value")
        for th in adef.get("scarcity_thresholds", []):
            if _threshold_met(val, th):
                hits.append({"key": th["key"], "label": th["label"], "attribute": name})
                if th.get("supersedes"):
                    superseded.add(th["supersedes"])

    for comp in spec.get("composite_thresholds", []):
        if all(_threshold_met(canon.get(a, {}).get("value"), req)
               for a, req in comp["requires"].items()):
            hits.append({"key": comp["key"], "label": comp["label"], "attribute": "composite"})

    return [h for h in hits if h["key"] not in superseded]


def _threshold_met(val: Any, th: Dict[str, Any]) -> bool:
    if val is None:
        return False
    if th.get("truthy"):
        return bool(val)
    if "gte" in th and not (val >= th["gte"]):
        return False
    if "gt" in th and not (val > th["gt"]):
        return False
    if "lte" in th and not (val <= th["lte"]):
        return False
    return any(k in th for k in ("gte", "gt", "lte"))


# ----------------------------------------------------------------------------- record
def build_record(doc: Dict[str, Any], suburb: str, spec: Dict[str, Any],
                 in_sample: bool) -> Dict[str, Any]:
    method_conf = spec.get("method_confidence", {})
    canon: Dict[str, Dict[str, Any]] = {
        name: resolve_attribute(doc, name, adef, method_conf)
        for name, adef in spec["attributes"].items()
    }
    _apply_sanity(canon)

    values = {k: v["value"] for k, v in canon.items()}
    prov = {k: v["_prov"] for k, v in canon.items()}
    hits = compute_threshold_hits(canon, spec)
    content_hash = hashlib.sha256(
        json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()

    return {
        "source_id": str(doc["_id"]),
        "suburb": suburb,
        "address": doc.get("address") or doc.get("complete_address"),
        "url_slug": doc.get("url_slug"),
        "listing_status": doc.get("listing_status"),
        "sold_date": doc.get("sold_date"),
        "property_type": doc.get("property_type"),
        "in_sample": in_sample,
        "schema_version": spec["schema_version"],
        "resolved_at": dt.datetime.utcnow().isoformat() + "Z",
        "attributes": values,
        "provenance": prov,
        "scarcity_hits": hits,
        "content_hash": content_hash,
    }


# ----------------------------------------------------------------------------- targets
def _manifest(client, sample_id: Optional[str]) -> Dict[str, Any]:
    coll = client["system_monitor"]["sample_manifest"]
    if sample_id:
        m = coll.find_one({"sample_id": sample_id})
    else:
        m = coll.find_one(sort=[("created_at", -1)])
    if not m:
        raise SystemExit("No sample_manifest found — run build_positioning_sample.py first.")
    return m


def gather_targets(db, client, args) -> List[Tuple[str, Dict[str, Any], bool]]:
    """Return list of (suburb, doc, in_sample)."""
    out: List[Tuple[str, Dict[str, Any], bool]] = []
    if args.all_sample:
        m = _manifest(client, args.sample_id)
        print(f"Using manifest {m['sample_id']} ({m['member_count']} members)")
        for suburb, ids in m["members"].items():
            for oid in ids:
                d = db[suburb].find_one({"_id": ObjectId(oid)})
                if d:
                    out.append((suburb, d, True))
        return out

    sample_ids = _sample_id_set(client, args.sample_id)
    if args.address or args.slug:
        key = "address" if args.address else "url_slug"
        val = args.address or args.slug
        for suburb in (["robina", "burleigh_waters", "varsity_lakes"]
                       if not args.suburb else [args.suburb]):
            d = db[suburb].find_one({key: val})
            if d:
                out.append((suburb, d, str(d["_id"]) in sample_ids))
                break
    elif args.suburb:
        for d in db[args.suburb].find({"listing_status": "sold"}):
            out.append((args.suburb, d, str(d["_id"]) in sample_ids))
    return out


def _sample_id_set(client, sample_id: Optional[str]) -> set:
    try:
        m = _manifest(client, sample_id)
        return {oid for ids in m["members"].values() for oid in ids}
    except SystemExit:
        return set()


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address")
    ap.add_argument("--slug")
    ap.add_argument("--suburb")
    ap.add_argument("--all-sample", action="store_true",
                    help="Resolve every member of the (latest) sample manifest")
    ap.add_argument("--sample-id", help="Specific manifest sample_id")
    ap.add_argument("--dry-run", action="store_true", help="Print, do not write")
    args = ap.parse_args()

    spec = load_spec()
    db = get_gold_coast_db()
    client = get_client()
    targets = gather_targets(db, client, args)
    if not targets:
        print("No targets matched.")
        return 1

    coll = client["Gold_Coast"][ATTR_COLLECTION]
    written = 0
    for suburb, doc, in_sample in targets:
        rec = build_record(doc, suburb, spec, in_sample)
        if args.dry_run or len(targets) == 1:
            filled = sum(1 for v in rec["attributes"].values() if v is not None)
            print(f"\n{rec['address']}  [{suburb}]  in_sample={in_sample}")
            print(f"  filled {filled}/{len(rec['attributes'])} attributes  | hits: "
                  f"{[h['key'] for h in rec['scarcity_hits']]}")
            for a, v in rec["attributes"].items():
                p = rec["provenance"][a]
                print(f"    {a:20} = {str(v):>10}    via {p['method']:24} "
                      f"({p['source_field']})")
        if not args.dry_run:
            coll.replace_one({"source_id": rec["source_id"]}, rec, upsert=True)
            written += 1

    if not args.dry_run:
        print(f"\n✓ Wrote {written} golden records to Gold_Coast.{ATTR_COLLECTION}")
    else:
        print(f"\n(dry-run — {len(targets)} records resolved, none written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
