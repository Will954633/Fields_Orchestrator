#!/usr/bin/env python3
"""
Mini-site health check — completeness + freshness audit of every house mini-site.

Reads the field spec (mirrors MINISITE_DATA_DICTIONARY.md), evaluates every dynamic
field on every property_reports doc, and emits per-field status:
  OK | STALE | MISSING | PENDING-EXPECTED | ERROR | UNKNOWN-FRESHNESS | KNOWN-GAP

Writes a per-run snapshot to system_monitor.minisite_health_snapshots so it can
populate "date last changed" and detect silently frozen Tier-2 data.

Usage:
  python3 scripts/minisite_health_check.py                 # check all reports, print summary
  python3 scripts/minisite_health_check.py --slug <slug>   # one report, verbose
  python3 scripts/minisite_health_check.py --json out.json  # write full results JSON
  python3 scripts/minisite_health_check.py --no-snapshot    # don't persist snapshot

Source of truth for fields/thresholds: MINISITE_DATA_DICTIONARY.md
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

AEST = ZoneInfo("Australia/Brisbane") if ZoneInfo else timezone(timedelta(hours=10))
NIGHTLY_RUN_HOUR = 20  # pipeline trigger 20:30 AEST
NIGHTLY_RUN_MIN = 30

# ---- status constants ---------------------------------------------------------
OK, STALE, MISSING, PENDING, ERROR, UNKNOWN, GAP = (
    "OK", "STALE", "MISSING", "PENDING-EXPECTED", "ERROR", "UNKNOWN-FRESHNESS", "KNOWN-GAP")
SEVERITY = {ERROR: 4, MISSING: 3, STALE: 2, UNKNOWN: 1, GAP: 0, PENDING: 0, OK: 0}

# Per-upstream staleness: None = nightly (judge vs expected last nightly run);
# a number = monthly/slow source judged on clock age in days.
UPSTREAM_STALE_DAYS = {"prices": None, "charts": None, "active": None,
                       "valuation": 3, "seasonality": 35, "library": None}


# ---- field spec (mirrors the data dictionary) ---------------------------------
# kind: always | tier1 | tier2          (tier1=nightly-refreshed, tier2=build-time)
# fresh: how to judge staleness:
#   {"nightly": "<path-to-ts-on-doc>"}     -> stale if ts predates last expected nightly run
#   {"self": "<path-to-ts-on-doc>"}        -> build-time stamp; informational unless stale_days set
#   {"upstream": "<key>"}                  -> judge against shared upstream source (see UPSTREAMS)
#   None                                   -> no freshness dimension
# rule: completeness check name + optional arg (see RULES)
def F(tab, field, path, kind, slot=None, fresh=None, rule=("present", None),
      stale_days=None, note=None):
    return dict(tab=tab, field=field, path=path, kind=kind, slot=slot,
                fresh=fresh, rule=rule, stale_days=stale_days, note=note)


SPEC = [
    # --- Header / always ---
    F("Header", "Address", "address", "always", rule=("nonempty_str", None)),
    F("Header", "Suburb", "suburb", "always", rule=("nonempty_str", None)),
    F("Header", "Lat", "lat", "always", rule=("number", None)),
    F("Header", "Lng", "lng", "always", rule=("number", None)),
    F("Header", "Report state", "state", "always", rule=("in_set", ["stub", "under_review", "final", "living"])),
    F("Header", "Last data pull", "slots.data_pull_date", "tier1", fresh={"nightly": "slots.data_pull_date"}, stale_days=1.5),
    F("Header", "Report updated", "updated_at", "tier1", fresh={"nightly": "updated_at"}, stale_days=1.5),
    F("Header", "Build state", "build_state", "always", rule=("eq", "complete")),

    # --- Your Home ---
    F("Home", "Beds", "property.bed", "always", rule=("int_ge", 0)),
    F("Home", "Baths", "property.bath", "always", rule=("int_ge", 0)),
    F("Home", "Car spaces", "property.car", "always", rule=("int_ge", 0)),
    F("Home", "Land area", "property.land_area_sqm", "always", rule=("number_gt", 0)),
    F("Home", "Internal area", "property.internal_area_sqm", "always", rule=("number_gt", 0), note="warn if null"),
    F("Home", "Property type", "property.property_type", "always", rule=("nonempty_str", None)),
    F("Home", "Gallery photos", "property.photos", "always", rule=("list_min", 1)),
    F("Home", "Photo analysis", "property.photo_analysis.categories", "always", rule=("present", None)),
    F("Home", "Floor plan image", "property.floor_plan.url", "always", fresh={"self": "property.floor_plan.generated_at"}, rule=("nonempty_str", None)),
    F("Home", "Floor plan rooms", "property.floor_plan.layout.rooms", "always", rule=("list_min", 1)),
    F("Home", "Satellite image", "property.satellite.satellite_image_url", "always", fresh={"self": "property.satellite.processed_at"}, rule=("nonempty_str", None)),
    F("Home", "Satellite narrative", "property.satellite.narrative.overall_setting", "always", rule=("nonempty_str", None)),
    F("Home", "Street view image", "property.street_view.street_view_image_url", "always", fresh={"self": "property.street_view.processed_at"}, rule=("nonempty_str", None)),
    F("Home", "Street view narrative", "property.street_view.narrative.kerb_summary", "always", rule=("nonempty_str", None)),
    F("Home", "POI walking distances", "pois", "tier2", slot="walking_distance", rule=("list_min", 1)),

    # --- Valuation ---
    F("Valuation", "Working range low", "valuation.model_range.low", "tier2", slot="comps", fresh={"drift": "valuation"}, rule=("number_gt", 0)),
    F("Valuation", "Working range high", "valuation.model_range.high", "tier2", slot="comps", rule=("gt_field", "valuation.model_range.low")),
    F("Valuation", "Range method", "valuation.model_range.method", "tier2", slot="comps", rule=("nonempty_str", None)),
    F("Valuation", "Range comp count", "valuation.model_range.comp_count", "tier2", slot="comps", rule=("int_ge", 3)),
    F("Valuation", "Comparable rows", "valuation.comps", "tier2", slot="comps", fresh={"drift": "valuation"}, rule=("list_items_have", ["soldPrice", "soldDate", "address"]), note="min 3"),
    F("Valuation", "Reconciled valuation", "valuation.reconciled", "tier2", slot="comps", rule=("nullable", None), note="null until analyst sign-off"),

    # --- The Market ---
    F("Market", "Median DOM", "market.median_dom", "tier1", fresh={"upstream": "charts"}, rule=("int_ge", 0)),
    F("Market", "Median DOM historical", "market.median_dom_historical", "tier1", fresh={"upstream": "charts"}, rule=("number", None)),
    F("Market", "DOM YoY change", "market.dom_yoy_change", "tier1", fresh={"upstream": "charts"}, rule=("number", None)),
    F("Market", "Latest median price", "market.latest_median_price", "tier1", fresh={"upstream": "prices"}, rule=("number_gt", 0)),
    F("Market", "Rolling 12m median", "market.rolling_12m_median", "tier1", fresh={"upstream": "prices"}, rule=("number_gt", 0)),
    F("Market", "Rolling 12m YoY %", "market.rolling_12m_yoy_pct", "tier1", fresh={"upstream": "prices"}, rule=("number", None)),
    F("Market", "Growth since baseline %", "market.growth_since_baseline_pct", "tier1", fresh={"upstream": "prices"}, rule=("number", None)),
    F("Market", "Baseline period", "market.baseline_period", "tier1", rule=("nonempty_str", None)),
    F("Market", "Sold transaction count", "market.sold_transaction_count", "tier1", rule=("int_ge", 1)),
    F("Market", "Active listings count", "market.active_listings_count", "tier1", fresh={"upstream": "active"}, rule=("int_ge", 0)),
    F("Market", "Competitor count", "slots.competitor_map.competitors", "tier1", slot="competitor_matches", fresh={"nightly": "slots.competitor_map.resolved_at"}, rule=("list_min", 1)),
    F("Market", "Competitor funnel", "slots.competitor_map.ranked_comparison.funnel.active_total", "tier1", slot="competitor_matches", rule=("number", None)),
    F("Market", "Ranked homes", "slots.competitor_map.ranked_comparison.homes", "tier1", slot="competitor_matches", rule=("list_min", 1)),
    F("Market", "Scarcity headline", "scarcity.headline", "tier2", slot="scarcity", fresh={"self": "scarcity.generated_at"}, rule=("nonempty_str", None)),
    F("Market", "Combinatorial match", "scarcity.combinatorialMatch", "tier2", slot="scarcity", rule=("nonempty_str", None)),
    F("Market", "Sold-cohort premiums", "scarcity.soldCohortPremiums", "tier2", slot="scarcity", rule=("list_min", 1)),
    F("Market", "Active listings (scarcity)", "scarcity_features.active_listings_total", "tier1", slot="scarcity", fresh={"upstream": "active"}, rule=("int_ge", 1)),
    F("Market", "Cohort premium stats", "scarcity_features.cohort_premiums", "tier2", slot="scarcity", rule=("list_min", 1)),
    F("Market", "Market narrative", "market_narrative.text", "tier2", slot="market_narrative", fresh={"drift": "market"}, rule=("str_len_between", [40, 600])),
    F("Market", "Dynamic case study", "case_studies.dynamic.address", "tier2", slot="case_studies", fresh={"self": "case_studies.dynamic.resolved_at"}, stale_days=30, rule=("nonempty_str", None)),

    # --- The Buyers ---
    F("Buyers", "Thesis headline", "buyers.thesis.headline", "tier2", slot="buyers", fresh={"self": "buyers.generated_at"}, rule=("nonempty_str", None)),
    F("Buyers", "Thesis body", "buyers.thesis.body", "tier2", slot="buyers", rule=("list_min", 1)),
    F("Buyers", "Thesis stat blocks", "buyers.thesis.statBlocks", "tier2", slot="buyers", rule=("list_items_have", ["value", "label"])),
    F("Buyers", "Catchment locations", "buyers.catchment.locations", "tier2", slot="buyers", rule=("list_min", 1)),
    F("Buyers", "Campaign math", "buyers.campaignMath.headline", "tier2", slot="buyers", rule=("nonempty_str", None)),

    # --- Positioning ---
    F("Positioning", "Strategic frame", "positioning.frame.angle", "tier2", slot="positioning", fresh={"self": "positioning.generated_at"}, rule=("nonempty_str", None)),
    F("Positioning", "Vocabulary use", "positioning.vocabulary.use", "tier2", slot="positioning", rule=("list_min", 1)),
    F("Positioning", "Vocabulary avoid", "positioning.vocabulary.avoid", "tier2", slot="positioning", rule=("list_min", 1)),
    F("Positioning", "Trade-offs", "positioning.tradeOffs", "tier2", slot="positioning", rule=("list_items_have", ["apparent", "reframe", "evidence"])),
    F("Positioning", "Photography brief", "positioning.photography", "tier2", slot="positioning", rule=("list_min", 3)),
    F("Positioning", "Sample paragraph", "positioning.sampleParagraph", "tier2", slot="positioning", rule=("nonempty_str", None)),
    F("Positioning", "Generic paragraph", "positioning.genericParagraph", "tier2", slot="positioning", rule=("nonempty_str", None)),
    F("Positioning", "Buyer personas", "positioning.personas", "tier2", slot="positioning", rule=("list_min", 3)),

    # --- The Process ---
    F("Process", "Seasonality calendar", "seasonality.months", "tier1", slot="seasonality", fresh={"upstream": "seasonality"}, rule=("list_min", 12)),
    F("Process", "Seasonality peak/trough", "seasonality.peakMonthIndex", "tier1", slot="seasonality", rule=("int_ge", 0)),

    # --- Messages / living ---
    F("Messages", "Activity feed", "activity", "tier1", fresh={"nightly": "activity_refreshed_at"}, stale_days=1.5, rule=("list_min", 1)),
    F("Messages", "Comparable feed", "comparables.closest_active", "tier1", fresh={"nightly": "comparables_refreshed_at"}, stale_days=1.5, rule=("list_min", 1)),
    F("Messages", "Messages", "messages", "tier1", fresh={"self": "messages_refreshed_at"}, rule=("list_min", 0)),
]


# ---- helpers ------------------------------------------------------------------
def get_path(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def as_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        s = v.replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(s)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(v[:19], fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def expected_last_run(now_utc):
    """Most recent 20:30 AEST instant at or before now (as UTC)."""
    now_aest = now_utc.astimezone(AEST)
    run_today = now_aest.replace(hour=NIGHTLY_RUN_HOUR, minute=NIGHTLY_RUN_MIN, second=0, microsecond=0)
    if now_aest < run_today:
        run_today -= timedelta(days=1)
    return run_today.astimezone(timezone.utc)


def value_hash(v):
    try:
        s = json.dumps(v, sort_keys=True, default=str)
    except TypeError:
        s = str(v)
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def value_summary(v):
    if isinstance(v, list):
        return f"[{len(v)} items]"
    if isinstance(v, dict):
        return f"{{{len(v)} keys}}"
    if isinstance(v, datetime):
        return v.isoformat()
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "..."


# ---- completeness rules -------------------------------------------------------
def check_rule(name, arg, value, doc):
    """Return (passed: bool, detail: str). Absence is handled by caller."""
    if name == "present":
        return value not in (None, "", [], {}), ""
    if name == "nullable":
        return True, ""
    if name == "known_gap":
        return None, "not implemented"  # signals GAP
    if name == "nonempty_str":
        return isinstance(value, str) and value.strip() != "", ""
    if name == "eq":
        return value == arg, f"expected {arg}, got {value}"
    if name == "in_set":
        return value in arg, f"got {value}"
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool), ""
    if name == "number_gt":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > arg, f"={value}"
    if name == "int_ge":
        return isinstance(value, int) and not isinstance(value, bool) and value >= arg, f"={value}"
    if name == "list_min":
        return isinstance(value, list) and len(value) >= arg, f"len={len(value) if isinstance(value, list) else 'n/a'}"
    if name == "list_items_have":
        if not isinstance(value, list) or not value:
            return False, "empty"
        for it in value:
            if not isinstance(it, dict) or any(k not in it or it.get(k) in (None, "") for k in arg):
                return False, f"item missing {arg}"
        return True, ""
    if name == "str_len_between":
        lo, hi = arg
        return isinstance(value, str) and lo <= len(value) <= hi, f"len={len(value) if isinstance(value, str) else 'n/a'}"
    if name == "gt_field":
        other = get_path(doc, arg)
        if not isinstance(value, (int, float)) or not isinstance(other, (int, float)):
            return False, "non-numeric"
        return value > other, f"{value} vs {other}"
    return True, f"unknown rule {name}"


# ---- upstream freshness -------------------------------------------------------
def load_upstreams(client, suburb_keys):
    """Per-suburb freshness for shared Tier-2/Tier-1 sources. Keyed by suburb_key.

    suburb_keys: set of suburb_keys present in the reports, used to disambiguate
    precomputed_market_charts _ids of the form "{suburb}_{metric}" where both
    suburb and metric may contain underscores (e.g. "burleigh_waters_days_on_market").
    """
    gc = client["Gold_Coast"]
    up = {"prices": {}, "charts": {}, "active": {}, "library": {}, "sold": {}, "seasonality": {}}
    for d in gc["precomputed_indexed_prices"].find({}, {"last_updated": 1}):
        up["prices"][str(d["_id"])] = as_dt(d.get("last_updated"))
    for d in gc["precomputed_active_listings"].find({}, {"last_updated": 1}):
        up["active"][str(d["_id"])] = as_dt(d.get("last_updated"))
    for d in gc["precomputed_seasonality"].find({}, {"last_updated": 1}):
        up["seasonality"][str(d["_id"])] = as_dt(d.get("last_updated"))

    # --- live current values for DRIFT detection (build-time slots vs moved market) ---
    up["market_live"] = {}   # suburb -> {latest_price, rolling_12m_yoy_pct, median_dom}
    up["sold_newest"] = {}   # suburb -> newest sold_date (datetime)
    for d in gc["precomputed_indexed_prices"].find(
            {}, {"latest_price": 1, "rolling_12m_yoy_pct": 1}):
        up["market_live"][str(d["_id"])] = {
            "latest_price": d.get("latest_price"),
            "rolling_12m_yoy_pct": d.get("rolling_12m_yoy_pct"),
        }
    keys_by_len = sorted(suburb_keys, key=len, reverse=True)
    for d in gc["precomputed_market_charts"].find(
            {"chart_type": "days_on_market"}, {"latest_quarter_median": 1}):
        _id = str(d["_id"])
        sub = next((k for k in keys_by_len if _id == k or _id.startswith(k + "_")), None)
        if sub and sub in up["market_live"]:
            up["market_live"][sub]["median_dom"] = d.get("latest_quarter_median")
    for sub in suburb_keys:
        if sub not in gc.list_collection_names():
            continue
        row = list(gc[sub].find({"listing_status": "sold", "sold_date": {"$exists": True}},
                                {"sold_date": 1}).sort("sold_date", -1).limit(1))
        if row:
            up["sold_newest"][sub] = as_dt(row[0].get("sold_date"))
    # market_charts: bucket each doc to the longest matching suburb_key prefix.
    keys_by_len = sorted(suburb_keys, key=len, reverse=True)
    for d in gc["precomputed_market_charts"].find({}, {"last_updated": 1}):
        _id = str(d["_id"])
        sub = next((k for k in keys_by_len if _id == k or _id.startswith(k + "_")), None)
        if not sub:
            continue
        ts = as_dt(d.get("last_updated"))
        if ts and (sub not in up["charts"] or ts > up["charts"][sub]):
            up["charts"][sub] = ts
    # case study library: newest built_at per suburb (published only)
    for d in client["system_monitor"]["case_study_library"].find({"published": True}, {"suburb": 1, "built_at": 1}):
        sub = (d.get("suburb") or "").strip().lower().replace(" ", "_")
        ts = as_dt(d.get("built_at"))
        if ts and (sub not in up["library"] or ts > up["library"][sub]):
            up["library"][sub] = ts
    return up


def check_drift(kind, doc, up, suburb_key):
    """Detect whether a build-time slot has DRIFTED — i.e. the market data it was
    generated from has since moved materially. Returns (is_drifted, detail, ref_ts).
    ref_ts is the slot's own generated/resolved timestamp (for display)."""
    if kind == "market":
        snap = get_path(doc, "market_narrative.inputs_snapshot.market") or {}
        live = up.get("market_live", {}).get(suburb_key)
        gen = as_dt(get_path(doc, "market_narrative.generated_at"))
        if not snap or not live:
            return False, "", gen
        issues = []
        sp, lp = snap.get("latest_median_price"), live.get("latest_price")
        if sp and lp and abs(lp - sp) / sp > 0.03:
            issues.append(f"price {sp:,.0f}→{lp:,.0f}")
        sd, ld = snap.get("median_dom"), live.get("median_dom")
        if sd and ld and abs(ld - sd) > 7:
            issues.append(f"DOM {sd}→{ld}")
        sy, ly = snap.get("rolling_12m_yoy_pct"), live.get("rolling_12m_yoy_pct")
        if sy is not None and ly is not None and abs(ly - sy) > 2.0:
            issues.append(f"YoY {sy}→{ly}pp")
        return (bool(issues), "market moved since narrative: " + ", ".join(issues) if issues else "", gen)

    if kind == "valuation":
        cra = as_dt(get_path(doc, "valuation.comps_resolved_at"))
        newest = up.get("sold_newest", {}).get(suburb_key)
        if not cra or not newest:
            return False, "", cra
        gap = (newest - cra).days
        if gap > 30:
            return True, f"comps resolved {cra.date()} but sales run to {newest.date()} (+{gap}d)", cra
        return False, "", cra

    return False, "", None


def upstream_ts(up, key, suburb_key, client, doc):
    if key == "valuation":
        # best-effort: subject property doc in Gold_Coast.<suburb>
        pid = doc.get("property_id")
        if pid and suburb_key:
            try:
                from bson import ObjectId
                pd = client["Gold_Coast"][suburb_key].find_one(
                    {"_id": ObjectId(pid)}, {"valuation_data.metadata.computed_at": 1})
                if pd:
                    return as_dt(get_path(pd, "valuation_data.metadata.computed_at")), True
            except Exception:
                pass
        return None, False
    table = up.get(key, {})
    return table.get(suburb_key), (suburb_key in table)


# ---- evaluate one report ------------------------------------------------------
def evaluate(doc, up, client, now_utc, prev_fields):
    suburb_key = (doc.get("suburb_key") or doc.get("suburb") or "").strip().lower().replace(" ", "_")
    slot_status = doc.get("slot_status") or {}
    under_review = doc.get("state") in (None, "stub", "under_review")
    last_run = expected_last_run(now_utc)
    results = []

    for f in SPEC:
        path, slot, kind = f["path"], f["slot"], f["kind"]
        value = get_path(doc, path)
        slot_state = slot_status.get(slot) if slot else None
        rule_name, rule_arg = f["rule"]

        status, detail, fresh_ts, fresh_src = OK, "", None, None

        # 1) known-gap short circuit
        if rule_name == "known_gap":
            status = GAP
            detail = f.get("note") or "not implemented"
            results.append(_field_result(f, value, status, detail, None, None, now_utc, prev_fields))
            continue

        # 2) slot error
        if slot and slot_state == "error":
            status, detail = ERROR, f"slot '{slot}' = error"
            results.append(_field_result(f, value, status, detail, None, None, now_utc, prev_fields))
            continue

        # 3) completeness
        passed, rdetail = check_rule(rule_name, rule_arg, value, doc)
        absent = value in (None, "", [], {})
        if passed is False or (absent and rule_name not in ("nullable",)):
            if slot and slot_state != "approved" and under_review:
                status, detail = PENDING, f"slot '{slot}'={slot_state or 'unset'}"
            else:
                status, detail = MISSING, rdetail or "absent/failed rule"
            results.append(_field_result(f, value, status, detail, None, None, now_utc, prev_fields))
            continue

        # 4) freshness (only if present & complete)
        fr = f["fresh"]
        if fr:
            if "nightly" in fr:
                fresh_src = fr["nightly"]
                fresh_ts = as_dt(get_path(doc, fresh_src))
                if fresh_ts is None:
                    status, detail = UNKNOWN, f"no ts at {fresh_src}"
                elif fresh_ts < last_run:
                    status, detail = STALE, f"missed nightly run ({fresh_ts.date()})"
            elif "upstream" in fr:
                key = fr["upstream"]
                fresh_ts, known = upstream_ts(up, key, suburb_key, client, doc)
                fresh_src = f"upstream:{key}"
                sd = UPSTREAM_STALE_DAYS.get(key)
                if not known or fresh_ts is None:
                    status, detail = UNKNOWN, f"no upstream {key} for {suburb_key}"
                elif sd is None and fresh_ts < last_run:
                    status, detail = STALE, f"upstream {key} missed nightly run ({fresh_ts.date()})"
                elif sd is not None and (now_utc - fresh_ts) > timedelta(days=sd):
                    status, detail = STALE, f"upstream {key} >{sd}d old ({fresh_ts.date()})"
            elif "drift" in fr:
                is_drift, ddetail, ref_ts = check_drift(fr["drift"], doc, up, suburb_key)
                fresh_src = f"drift:{fr['drift']}"
                fresh_ts = ref_ts
                if is_drift:
                    status, detail = STALE, ddetail
            elif "self" in fr:
                fresh_src = fr["self"]
                fresh_ts = as_dt(get_path(doc, fresh_src))
                sd = f.get("stale_days")
                if sd is not None:
                    if fresh_ts is None:
                        status, detail = UNKNOWN, f"no ts at {fresh_src}"
                    elif (now_utc - fresh_ts) > timedelta(days=sd):
                        status, detail = STALE, f">{sd}d old ({fresh_ts.date()})"
                # else build-time stamp, informational only

        results.append(_field_result(f, value, status, detail, fresh_ts, fresh_src, now_utc, prev_fields))

    return results


def _field_result(f, value, status, detail, fresh_ts, fresh_src, now_utc, prev_fields):
    vh = value_hash(value)
    prev = prev_fields.get(f["path"]) if prev_fields else None
    if prev and prev.get("value_hash") == vh:
        last_changed = prev.get("last_changed")
    else:
        last_changed = now_utc.isoformat()
    return {
        "tab": f["tab"], "field": f["field"], "path": f["path"],
        "kind": f["kind"], "slot": f["slot"],
        "value": value_summary(value), "value_hash": vh,
        "status": status, "detail": detail,
        "freshness_ts": fresh_ts.isoformat() if fresh_ts else None,
        "freshness_src": fresh_src,
        "last_changed": last_changed,
        "note": f.get("note"),
    }


# ---- reusable audit entry point ----------------------------------------------
def get_mongo_client():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("COSMOS_CONNECTION_STRING="):
                    conn = line.split("=", 1)[1].strip().strip('"')
                    break
    return MongoClient(conn)


def run_audit(client=None, slug=None, persist=True):
    """Audit every (or one) report. Returns (all_results, now_utc).

    all_results: list of per-report dicts sorted worst-first, each with `fields`.
    Shared by the CLI and the Google Sheet builder.
    """
    own = client is None
    if own:
        client = get_mongo_client()
    reports = client["system_monitor"]["property_reports"]
    snaps = client["system_monitor"]["minisite_health_snapshots"]
    now_utc = datetime.now(timezone.utc)

    query = {"slug": slug} if slug else {"state": {"$ne": None}}
    docs = [d for d in reports.find(query) if d.get("address")]  # skip template stub

    suburb_keys = {(d.get("suburb_key") or d.get("suburb") or "").strip().lower().replace(" ", "_")
                   for d in docs} - {""}
    up = load_upstreams(client, suburb_keys)

    all_results = []
    for doc in docs:
        rslug = doc.get("slug")
        prev = snaps.find_one({"slug": rslug}, sort=[("run_at", -1)])
        prev_fields = (prev or {}).get("fields", {})
        prev_map = {fr["path"]: fr for fr in prev_fields} if isinstance(prev_fields, list) else prev_fields
        fields = evaluate(doc, up, client, now_utc, prev_map)

        counts = {}
        for fr in fields:
            counts[fr["status"]] = counts.get(fr["status"], 0) + 1
        health = round(100 * counts.get(OK, 0) / max(1, len(fields)))
        worst = max((SEVERITY[fr["status"]] for fr in fields), default=0)

        all_results.append({
            "slug": rslug, "address": doc.get("address"), "suburb": doc.get("suburb"),
            "state": doc.get("state"), "health_pct": health, "worst_severity": worst,
            "counts": counts, "data_pull_date": value_summary(get_path(doc, "slots.data_pull_date")),
            "fields": fields,
        })

        if persist:
            snaps.insert_one({
                "slug": rslug, "run_at": now_utc, "health_pct": health,
                "counts": counts, "fields": {fr["path"]: {
                    "value_hash": fr["value_hash"], "status": fr["status"],
                    "last_changed": fr["last_changed"]} for fr in fields},
            })

    all_results.sort(key=lambda r: (-r["worst_severity"], r["health_pct"]))
    if own:
        client.close()
    return all_results, now_utc


# ---- main ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--json")
    ap.add_argument("--no-snapshot", action="store_true")
    args = ap.parse_args()

    client = get_mongo_client()
    all_results, now_utc = run_audit(client, slug=args.slug, persist=not args.no_snapshot)
    print(f"\nMini-site health — {len(all_results)} reports — {now_utc.astimezone(AEST):%Y-%m-%d %H:%M AEST}")
    print(f"Expected last nightly run: {expected_last_run(now_utc).astimezone(AEST):%Y-%m-%d %H:%M AEST}\n")
    print(f"{'HEALTH':>6}  {'ERR':>3} {'MIS':>3} {'STA':>3} {'PND':>3} {'UNK':>3}  SLUG")
    for r in all_results:
        c = r["counts"]
        print(f"{r['health_pct']:>5}%  {c.get(ERROR,0):>3} {c.get(MISSING,0):>3} "
              f"{c.get(STALE,0):>3} {c.get(PENDING,0):>3} {c.get(UNKNOWN,0):>3}  {r['slug']}")

    if args.slug and all_results:
        print(f"\n--- field detail: {args.slug} ---")
        for fr in all_results[0]["fields"]:
            if fr["status"] != OK:
                print(f"  [{fr['status']:<17}] {fr['tab']:<11} {fr['field']:<26} {fr['detail']}")

    # highlight problems across the fleet
    problems = [(r["slug"], fr) for r in all_results for fr in r["fields"]
                if fr["status"] in (ERROR, MISSING, STALE)]
    if problems and not args.slug:
        print(f"\n--- {len(problems)} non-OK fields (ERROR/MISSING/STALE) ---")
        for slug, fr in problems[:60]:
            print(f"  [{fr['status']:<7}] {slug:<38} {fr['tab']}/{fr['field']}: {fr['detail']}")
        if len(problems) > 60:
            print(f"  ... and {len(problems)-60} more")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(all_results, fh, indent=2, default=str)
        print(f"\nFull results → {args.json}")

    client.close()


if __name__ == "__main__":
    main()
