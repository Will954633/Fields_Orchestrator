#!/usr/bin/env python3
"""
Phase 5: Predictive Modelling — Property Positioning Research
==============================================================
"What predicts sale outcomes?"

Studies:
  5.1 - Hedonic price model (what should a property sell for?)
  5.2 - DOM prediction (what controllable factors reduce time to sell?)
  5.3 - Sale premium prediction (what predicts selling above expected value?)
"""

import json, os, re, sys, time, warnings
from collections import defaultdict
from datetime import datetime
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import cross_val_score, LeaveOneOut
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_5"
os.makedirs(OUTPUT_DIR, exist_ok=True)
TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters", "mudgeeraba", "merrimac", "carrara", "worongary", "reedy_creek"]
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

client = get_client()
db_target = client["Target_Market_Sold_Last_12_Months"]
db_gc = client["Gold_Coast"]

def parse_price(s):
    if not s or not isinstance(s, str): return None
    m = re.search(r"(\d{6,})", s.replace(",", "").replace("$", ""))
    return int(m.group(1)) if m else None

def safe_get(doc, path, default=None):
    parts = path.split(".")
    cur = doc
    for p in parts:
        if isinstance(cur, dict): cur = cur.get(p)
        else: return default
        if cur is None: return default
    return cur

def normalise_address(addr):
    if not addr: return ""
    addr = addr.upper().strip()
    addr = re.sub(r"\s*,\s*", " ", addr)
    addr = re.sub(r"\s+", " ", addr)
    addr = re.sub(r"\bQLD\b", "", addr).strip()
    addr = re.sub(r"\b\d{4}\b$", "", addr).strip()
    return addr

def load_all_data():
    print("Loading data...")
    all_docs = []
    for suburb in TARGET_SUBURBS:
        time.sleep(1)
        docs = list(db_target[suburb].find({}))
        for d in docs:
            d["_suburb"] = suburb
            d["_numeric_price"] = parse_price(d.get("sale_price"))
            ifa = safe_get(d, "floor_plan_analysis.internal_floor_area.value")
            d["_floor_area"] = ifa if isinstance(ifa, (int, float)) and ifa and ifa > 30 else None
            d["_ppsqm"] = (d["_numeric_price"] / d["_floor_area"]) if d["_numeric_price"] and d["_floor_area"] else None
        all_docs.extend(docs)
    print(f"  {len(all_docs)} records")

    gc_lookup = {}
    for suburb in TARGET_SUBURBS:
        time.sleep(4)  # Extra throttle for Cosmos RU
        retries = 0
        while retries < 3:
            try:
                for gc in db_gc[suburb].find({}, {"complete_address": 1, "scraped_data.property_timeline": 1, "scraped_data.valuation": 1, "lot_size_sqm": 1}):
                    norm = normalise_address(gc.get("complete_address", ""))
                    if norm: gc_lookup[norm] = gc
                break
            except Exception as e:
                if "16500" in str(e):
                    retries += 1
                    wait = 5 * retries
                    print(f"    RU throttled on {suburb}, waiting {wait}s (retry {retries}/3)")
                    time.sleep(wait)
                else:
                    raise

    dom_count = 0
    for d in all_docs:
        if d.get("time_on_market_days") and isinstance(d["time_on_market_days"], (int, float)):
            d["_dom"] = int(d["time_on_market_days"]); dom_count += 1; continue
        norm = normalise_address(d.get("address", ""))
        gc = gc_lookup.get(norm) or gc_lookup.get(re.sub(r"^\d+/", "", norm))
        if gc:
            d["_domain_val"] = safe_get(gc, "scraped_data.valuation")
            d["_lot_size"] = gc.get("lot_size_sqm")
            for ev in (safe_get(gc, "scraped_data.property_timeline") or []):
                if ev.get("is_sold") and ev.get("days_on_market"):
                    d["_dom"] = int(ev["days_on_market"]); dom_count += 1; break
        else:
            d["_domain_val"] = None
            d["_lot_size"] = None
    print(f"  DOM: {dom_count}")
    return all_docs


# ── Study 5.1: Hedonic Price Model ────────────────────────────────────────
def study_5_1(all_docs):
    print("\n═══ Study 5.1: Hedonic Price Model ═══")
    results = {}

    # Suburb encoding
    suburb_map = {s: i for i, s in enumerate(TARGET_SUBURBS)}

    # Build feature matrix
    rows = []
    for d in all_docs:
        if not d["_numeric_price"] or not d.get("bedrooms"):
            continue

        beds = d.get("bedrooms", 0)
        baths = d.get("bathrooms", 0)
        cars = d.get("carspaces", 0)
        floor_area = d.get("_floor_area") or 0
        lot_size = d.get("_lot_size") or safe_get(d, "floor_plan_analysis.total_land_area.value") or 0
        if isinstance(lot_size, dict): lot_size = lot_size.get("value", 0) or 0
        condition = safe_get(d, "property_valuation_data.condition_summary.overall_score") or 7
        presentation = safe_get(d, "property_valuation_data.property_metadata.property_presentation_score") or 8
        pool = 1 if safe_get(d, "property_valuation_data.outdoor.pool_present") is True else 0
        water = 1 if safe_get(d, "property_valuation_data.outdoor.water_views") is True else 0
        levels = safe_get(d, "floor_plan_analysis.levels.total_levels") or 1
        reno_map = {"new_build": 4, "fully_renovated": 3, "cosmetically_updated": 2, "partially_renovated": 1, "original": 0, "tired": 0}
        reno = reno_map.get(safe_get(d, "property_valuation_data.renovation.overall_renovation_level"), 2)
        modern = safe_get(d, "property_valuation_data.renovation.modern_features_score") or 7

        # Skip if too many missing
        if floor_area < 30:
            continue

        features = {
            "bedrooms": beds,
            "bathrooms": baths,
            "carspaces": cars,
            "log_floor_area": np.log(floor_area) if floor_area > 0 else 0,
            "log_lot_size": np.log(lot_size) if lot_size and lot_size > 0 else 0,
            "condition": condition,
            "presentation": presentation,
            "pool": pool,
            "water_views": water,
            "levels": levels,
            "renovation_level": reno,
            "modern_features": modern,
        }
        # Suburb dummies
        for s in TARGET_SUBURBS[1:]:  # skip first as reference
            features[f"suburb_{s}"] = 1 if d["_suburb"] == s else 0

        rows.append({
            "features": features,
            "price": d["_numeric_price"],
            "log_price": np.log(d["_numeric_price"]),
            "suburb": d["_suburb"],
            "address": d.get("address", ""),
        })

    print(f"  Records with complete features: {len(rows)}")

    if len(rows) < 50:
        print("  Insufficient data for modelling")
        return results

    feature_names = list(rows[0]["features"].keys())
    X = np.array([[r["features"][f] for f in feature_names] for r in rows])
    y_price = np.array([r["price"] for r in rows])
    y_log = np.array([r["log_price"] for r in rows])

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Model 1: Linear on log(price)
    model_log = Ridge(alpha=1.0)
    scores_log = cross_val_score(model_log, X_scaled, y_log, cv=10, scoring="r2")
    model_log.fit(X_scaled, y_log)
    y_pred_log = model_log.predict(X_scaled)
    y_pred_prices = np.exp(y_pred_log)

    mae = mean_absolute_error(y_price, y_pred_prices)
    mape = np.mean(np.abs((y_price - y_pred_prices) / y_price)) * 100
    r2 = r2_score(y_price, y_pred_prices)

    # Feature importance (coefficients on scaled features)
    coef_importance = sorted(zip(feature_names, model_log.coef_), key=lambda x: abs(x[1]), reverse=True)

    results = {
        "model_type": "Ridge regression on log(price)",
        "n_records": len(rows),
        "n_features": len(feature_names),
        "cv_r2_mean": round(float(np.mean(scores_log)), 3),
        "cv_r2_std": round(float(np.std(scores_log)), 3),
        "train_r2": round(float(r2), 3),
        "mae": int(mae),
        "mape": round(float(mape), 1),
        "feature_importance": [
            {"feature": f, "coefficient": round(float(c), 4), "direction": "increases price" if c > 0 else "decreases price"}
            for f, c in coef_importance
        ],
        "interpretation": {},
    }

    # Compute dollar impact for key features (approximate)
    median_price = np.median(y_price)
    for f, c in coef_importance[:10]:
        # c is coefficient on standardised feature for log(price)
        # Approx dollar impact = median_price * (exp(c * 1_std) - 1)
        pct_impact = round((np.exp(abs(c)) - 1) * 100, 1)
        results["interpretation"][f] = {
            "pct_per_std": pct_impact,
            "direction": "+" if c > 0 else "-",
        }

    print(f"\n  Model: R²={r2:.3f}, CV R²={np.mean(scores_log):.3f}±{np.std(scores_log):.3f}")
    print(f"  MAE=${mae:,.0f}, MAPE={mape:.1f}%")
    print(f"\n  Feature importance (top 10):")
    for f, c in coef_importance[:10]:
        direction = "↑" if c > 0 else "↓"
        print(f"    {f:25s} {direction} coef={c:+.4f}")

    with open(os.path.join(OUTPUT_DIR, "study_5_1_hedonic.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 5.2: DOM Prediction ─────────────────────────────────────────────
def study_5_2(all_docs):
    print("\n═══ Study 5.2: DOM Prediction Model ═══")
    results = {}

    rows = []
    for d in all_docs:
        if not d.get("_dom") or d["_dom"] <= 0 or not d["_numeric_price"]:
            continue

        beds = d.get("bedrooms") or 3
        floor_area = d.get("_floor_area") or 0
        condition = safe_get(d, "property_valuation_data.condition_summary.overall_score") or 7
        presentation = safe_get(d, "property_valuation_data.property_metadata.property_presentation_score") or 8
        pool = 1 if safe_get(d, "property_valuation_data.outdoor.pool_present") is True else 0
        water = 1 if safe_get(d, "property_valuation_data.outdoor.water_views") is True else 0
        reno_map = {"new_build": 4, "fully_renovated": 3, "cosmetically_updated": 2, "partially_renovated": 1, "original": 0}
        reno = reno_map.get(safe_get(d, "property_valuation_data.renovation.overall_renovation_level"), 2)
        modern = safe_get(d, "property_valuation_data.renovation.modern_features_score") or 7

        # Price position (vs suburb-bedroom cohort)
        cohort_key = (d["_suburb"], beds)
        price_position = d["_numeric_price"]  # will normalise below

        # Sale month
        sd = d.get("sale_date", "")
        month = int(sd[5:7]) if sd and len(sd) >= 7 else 6

        if floor_area < 30:
            continue

        features = {
            "bedrooms": beds,
            "log_floor_area": np.log(floor_area),
            "condition": condition,
            "presentation": presentation,
            "pool": pool,
            "water_views": water,
            "renovation_level": reno,
            "modern_features": modern,
            "log_price": np.log(d["_numeric_price"]),
            "sale_month": month,
        }
        for s in CORE_SUBURBS[1:]:
            features[f"suburb_{s}"] = 1 if d["_suburb"] == s else 0

        rows.append({"features": features, "dom": d["_dom"], "log_dom": np.log(d["_dom"]), "suburb": d["_suburb"]})

    print(f"  Records with DOM + features: {len(rows)}")

    if len(rows) < 50:
        print("  Insufficient data")
        return results

    feature_names = list(rows[0]["features"].keys())
    X = np.array([[r["features"][f] for f in feature_names] for r in rows])
    y_dom = np.array([r["dom"] for r in rows])
    y_log_dom = np.array([r["log_dom"] for r in rows])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = Ridge(alpha=1.0)
    scores = cross_val_score(model, X_scaled, y_log_dom, cv=10, scoring="r2")
    model.fit(X_scaled, y_log_dom)
    y_pred = np.exp(model.predict(X_scaled))

    r2 = r2_score(y_dom, y_pred)
    mae = mean_absolute_error(y_dom, y_pred)

    coef_importance = sorted(zip(feature_names, model.coef_), key=lambda x: abs(x[1]), reverse=True)

    # Classify features as controllable vs fixed
    controllable = {"presentation", "condition", "renovation_level", "modern_features", "pool", "log_price", "sale_month"}

    results = {
        "model_type": "Ridge regression on log(DOM)",
        "n_records": len(rows),
        "cv_r2_mean": round(float(np.mean(scores)), 3),
        "cv_r2_std": round(float(np.std(scores)), 3),
        "train_r2": round(float(r2), 3),
        "mae_days": round(float(mae), 1),
        "feature_importance": [
            {"feature": f, "coefficient": round(float(c), 4),
             "effect": "increases DOM" if c > 0 else "decreases DOM",
             "controllable": f in controllable}
            for f, c in coef_importance
        ],
    }

    print(f"\n  Model: R²={r2:.3f}, CV R²={np.mean(scores):.3f}±{np.std(scores):.3f}")
    print(f"  MAE={mae:.1f} days")
    print(f"\n  DOM drivers (sorted by |impact|):")
    for f, c in coef_importance:
        ctrl = " [CONTROLLABLE]" if f in controllable else ""
        direction = "slower" if c > 0 else "faster"
        print(f"    {f:25s} {direction:8s} coef={c:+.4f}{ctrl}")

    with open(os.path.join(OUTPUT_DIR, "study_5_2_dom_model.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 5.3: Sale Premium Prediction ────────────────────────────────────
def study_5_3(all_docs):
    print("\n═══ Study 5.3: Sale Premium Prediction ═══")
    results = {}

    # For properties with Domain valuation, predict sale_price vs domain_mid
    rows = []
    for d in all_docs:
        if not d["_numeric_price"] or not d.get("_domain_val"):
            continue
        dv_mid = safe_get(d, "_domain_val.mid")
        if not dv_mid or not isinstance(dv_mid, (int, float)) or dv_mid <= 0:
            continue

        premium_pct = (d["_numeric_price"] / dv_mid - 1) * 100
        beat_valuation = 1 if premium_pct > 0 else 0

        condition = safe_get(d, "property_valuation_data.condition_summary.overall_score") or 7
        presentation = safe_get(d, "property_valuation_data.property_metadata.property_presentation_score") or 8
        market_appeal = safe_get(d, "property_valuation_data.property_metadata.market_appeal_score") or 8
        pool = 1 if safe_get(d, "property_valuation_data.outdoor.pool_present") is True else 0
        water = 1 if safe_get(d, "property_valuation_data.outdoor.water_views") is True else 0
        reno_map = {"new_build": 4, "fully_renovated": 3, "cosmetically_updated": 2, "partially_renovated": 1, "original": 0}
        reno = reno_map.get(safe_get(d, "property_valuation_data.renovation.overall_renovation_level"), 2)
        modern = safe_get(d, "property_valuation_data.renovation.modern_features_score") or 7
        beds = d.get("bedrooms") or 3
        floor_area = d.get("_floor_area") or 0
        if floor_area < 30: continue

        features = {
            "condition": condition,
            "presentation": presentation,
            "market_appeal": market_appeal,
            "pool": pool,
            "water_views": water,
            "renovation_level": reno,
            "modern_features": modern,
            "bedrooms": beds,
            "log_floor_area": np.log(floor_area),
        }
        for s in TARGET_SUBURBS[1:]:
            features[f"suburb_{s}"] = 1 if d["_suburb"] == s else 0

        rows.append({
            "features": features,
            "premium_pct": premium_pct,
            "beat_valuation": beat_valuation,
            "suburb": d["_suburb"],
            "address": d.get("address", ""),
            "price": d["_numeric_price"],
            "domain_mid": dv_mid,
        })

    print(f"  Records with Domain valuation: {len(rows)}")

    if len(rows) < 50:
        print("  Insufficient data")
        return results

    feature_names = list(rows[0]["features"].keys())
    X = np.array([[r["features"][f] for f in feature_names] for r in rows])
    y = np.array([r["premium_pct"] for r in rows])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = Ridge(alpha=1.0)
    scores = cross_val_score(model, X_scaled, y, cv=10, scoring="r2")
    model.fit(X_scaled, y)
    y_pred = model.predict(X_scaled)

    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)

    coef_importance = sorted(zip(feature_names, model.coef_), key=lambda x: abs(x[1]), reverse=True)

    # Profile: outperformers vs underperformers
    outperformers = [r for r in rows if r["premium_pct"] > 0]
    underperformers = [r for r in rows if r["premium_pct"] < -10]

    def profile_group(group):
        if not group: return {}
        return {
            "count": len(group),
            "avg_premium": round(float(np.mean([r["premium_pct"] for r in group])), 1),
            "avg_condition": round(float(np.mean([r["features"]["condition"] for r in group])), 1),
            "avg_presentation": round(float(np.mean([r["features"]["presentation"] for r in group])), 1),
            "pool_pct": round(100 * sum(r["features"]["pool"] for r in group) / len(group), 1),
            "water_pct": round(100 * sum(r["features"]["water_views"] for r in group) / len(group), 1),
            "avg_reno": round(float(np.mean([r["features"]["renovation_level"] for r in group])), 1),
        }

    results = {
        "model_type": "Ridge regression on premium_pct (vs Domain valuation)",
        "n_records": len(rows),
        "cv_r2_mean": round(float(np.mean(scores)), 3),
        "mae_pct": round(float(mae), 1),
        "overall_stats": {
            "mean_premium": round(float(np.mean(y)), 1),
            "median_premium": round(float(np.median(y)), 1),
            "pct_beating_valuation": round(100 * sum(1 for r in rows if r["beat_valuation"]) / len(rows), 1),
        },
        "feature_importance": [
            {"feature": f, "coefficient": round(float(c), 4), "effect": "increases premium" if c > 0 else "decreases premium"}
            for f, c in coef_importance
        ],
        "outperformer_profile": profile_group(outperformers),
        "underperformer_profile": profile_group(underperformers),
    }

    print(f"\n  Model: CV R²={np.mean(scores):.3f}, MAE={mae:.1f}%")
    print(f"  Overall: mean premium={np.mean(y):.1f}%, beating valuation={results['overall_stats']['pct_beating_valuation']}%")
    print(f"\n  Premium drivers:")
    for f, c in coef_importance[:10]:
        direction = "↑ premium" if c > 0 else "↓ premium"
        print(f"    {f:25s} {direction}  coef={c:+.4f}")

    print(f"\n  Outperformers (beat Domain): n={results['outperformer_profile'].get('count', 0)}")
    print(f"  Underperformers (<-10%): n={results['underperformer_profile'].get('count', 0)}")

    with open(os.path.join(OUTPUT_DIR, "study_5_3_premium.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Summary ────────────────────────────────────────────────────────────────
def generate_summary(s51, s52, s53):
    md = []
    md.append("# Phase 5: Predictive Modelling — \"What Predicts Sale Outcomes?\"")
    md.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")

    # 5.1
    md.append("\n---\n## 5.1 Hedonic Price Model")
    md.append(f"\n**Model:** {s51.get('model_type', 'N/A')}")
    md.append(f"**Records:** {s51.get('n_records', 0)}")
    md.append(f"**Performance:** R²={s51.get('train_r2', 'N/A')}, CV R²={s51.get('cv_r2_mean', 'N/A')}±{s51.get('cv_r2_std', 'N/A')}")
    md.append(f"**MAE:** ${s51.get('mae', 0):,} ({s51.get('mape', 0)}% MAPE)")
    md.append("\n### Feature Importance (what drives property price)")
    md.append("| Rank | Feature | Coefficient | Direction |")
    md.append("|------|---------|------------|-----------|")
    for i, f in enumerate(s51.get("feature_importance", [])[:12], 1):
        md.append(f"| {i} | {f['feature']} | {f['coefficient']:+.4f} | {f['direction']} |")

    # 5.2
    md.append("\n---\n## 5.2 DOM Prediction Model")
    md.append(f"\n**Model:** {s52.get('model_type', 'N/A')}")
    md.append(f"**Records:** {s52.get('n_records', 0)}")
    md.append(f"**Performance:** CV R²={s52.get('cv_r2_mean', 'N/A')}±{s52.get('cv_r2_std', 'N/A')}")
    md.append(f"**MAE:** {s52.get('mae_days', 'N/A')} days")
    md.append("\n### DOM Drivers")
    md.append("| Feature | Coefficient | Effect | Controllable? |")
    md.append("|---------|-----------|--------|---------------|")
    for f in s52.get("feature_importance", []):
        md.append(f"| {f['feature']} | {f['coefficient']:+.4f} | {f['effect']} | {'YES' if f['controllable'] else 'no'} |")

    # 5.3
    md.append("\n---\n## 5.3 Sale Premium Prediction (vs Domain Valuation)")
    md.append(f"\n**Records:** {s53.get('n_records', 0)}")
    md.append(f"**CV R²:** {s53.get('cv_r2_mean', 'N/A')}")
    os_data = s53.get("overall_stats", {})
    md.append(f"**Mean premium vs Domain:** {os_data.get('mean_premium', 'N/A')}%")
    md.append(f"**Properties beating Domain valuation:** {os_data.get('pct_beating_valuation', 'N/A')}%")
    md.append("\n### Premium Drivers")
    md.append("| Feature | Coefficient | Effect |")
    md.append("|---------|-----------|--------|")
    for f in s53.get("feature_importance", [])[:10]:
        md.append(f"| {f['feature']} | {f['coefficient']:+.4f} | {f['effect']} |")

    op = s53.get("outperformer_profile", {})
    up = s53.get("underperformer_profile", {})
    if op and up:
        md.append("\n### Outperformers vs Underperformers")
        md.append("| Metric | Outperformers (beat Domain) | Underperformers (<-10%) |")
        md.append("|--------|---------------------------|------------------------|")
        md.append(f"| Count | {op.get('count',0)} | {up.get('count',0)} |")
        md.append(f"| Avg premium | {op.get('avg_premium','N/A')}% | {up.get('avg_premium','N/A')}% |")
        md.append(f"| Avg condition | {op.get('avg_condition','N/A')}/10 | {up.get('avg_condition','N/A')}/10 |")
        md.append(f"| Avg presentation | {op.get('avg_presentation','N/A')}/10 | {up.get('avg_presentation','N/A')}/10 |")
        md.append(f"| Pool % | {op.get('pool_pct','N/A')}% | {up.get('pool_pct','N/A')}% |")
        md.append(f"| Water views % | {op.get('water_pct','N/A')}% | {up.get('water_pct','N/A')}% |")

    md.append(f"\n---\n*Fields Estate — Phase 5 | {datetime.now().strftime('%Y-%m-%d')}*")
    path = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_5_summary.md"
    with open(path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary: {path}")

def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Phase 5: Predictive Modelling — Positioning Research         ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    all_docs = load_all_data()
    s51 = study_5_1(all_docs)
    s52 = study_5_2(all_docs)
    s53 = study_5_3(all_docs)
    generate_summary(s51, s52, s53)
    print("\n" + "=" * 60)
    print("Phase 5 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
