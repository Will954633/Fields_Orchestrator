#!/usr/bin/env python3
"""screen_panel.py — screen candidate capital suburbs via PropRadar and select the
Gold-Coast-matched panels for the DOM comparison.

For each candidate suburb it reads PropRadar's per-suburb snapshot (house/unit median
price and 12-month sales volume) and keeps it in the HOUSE panel if its house median
sits in the GC-like band with enough volume, and separately in the UNIT panel on the
unit median + unit volume. Two panels per city (a suburb can be in one, both, or
neither) so each comparison line is genuinely price-matched to the GC.

GC baseline (propradar_suburb_stats, 2026-09): houses ~$1.35-1.47M, units ~$0.92-1.03M,
~200-370 house & ~65-230 unit sales/yr per suburb.

Output: scripts/capitals_dom/panel.json — the scraper (scrape_capitals.py) consumes it.

Usage: python3 scripts/capitals_dom/screen_panel.py [--out PATH]
"""
import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))            # scripts/
sys.path.insert(0, str(HERE.parent / "propradar"))  # scripts/propradar/
sys.path.insert(0, str(HERE.parent.parent))     # repo root
import propradar_client as pr  # noqa: E402
from candidates import all_candidates, CITY_LABEL  # noqa: E402

# GC-matched bands. Centred on the GC target-suburb medians with a ~±18% spread.
HOUSE_BAND = (1_200_000, 1_700_000)
UNIT_BAND = (780_000, 1_150_000)
# Per-suburb sales-volume floors (statistical power). Lenient because we POOL many
# suburbs — the pool carries the power; this just drops genuinely thin markets.
HOUSE_MIN_SALES = 90
UNIT_MIN_SALES = 45

DEFAULT_OUT = HERE / "panel.json"


def screen(out_path):
    house_panel = {"NSW": [], "VIC": [], "QLD": []}
    unit_panel = {"NSW": [], "VIC": [], "QLD": []}
    rows = []
    cands = list(all_candidates())
    print(f"Screening {len(cands)} candidates via PropRadar…\n")
    for i, c in enumerate(cands):
        try:
            data, hdr = pr.call("/suburbs/" + c["state"] + "/" + urllib.parse.quote(c["suburb"].title()))
        except Exception as e:
            print(f"  {c['slug']}: PropRadar error {e}")
            time.sleep(0.5)
            continue
        meds = data.get("medians") or {}
        md = data.get("market_dynamics") or {}
        hp, up = meds.get("house_price"), meds.get("unit_price")
        hs, us = md.get("house_sales_12mo"), md.get("unit_sales_12mo")
        hdom, udom = md.get("house_days_on_market"), md.get("unit_days_on_market")
        in_h = hp is not None and HOUSE_BAND[0] <= hp <= HOUSE_BAND[1] and (hs or 0) >= HOUSE_MIN_SALES
        in_u = up is not None and UNIT_BAND[0] <= up <= UNIT_BAND[1] and (us or 0) >= UNIT_MIN_SALES
        entry = {"suburb": c["suburb"], "slug": c["slug"], "state": c["state"],
                 "postcode": c["postcode"]}
        if in_h:
            house_panel[c["state"]].append({**entry, "house_price": hp, "house_sales_12mo": hs, "house_dom": hdom})
        if in_u:
            unit_panel[c["state"]].append({**entry, "unit_price": up, "unit_sales_12mo": us, "unit_dom": udom})
        rows.append({**entry, "house_price": hp, "unit_price": up, "house_sales_12mo": hs,
                     "unit_sales_12mo": us, "house_dom": hdom, "unit_dom": udom,
                     "in_house": in_h, "in_unit": in_u})
        flag = ("H" if in_h else " ") + ("U" if in_u else " ")
        print(f"  [{i+1}/{len(cands)}] {flag} {c['slug']:<26} "
              f"h=${hp} ({hs} sales, dom {hdom}) | u=${up} ({us} sales, dom {udom})")
        time.sleep(0.5)  # PropRadar 2 rps

    out = {
        "generated_bands": {"house": HOUSE_BAND, "unit": UNIT_BAND,
                            "house_min_sales": HOUSE_MIN_SALES, "unit_min_sales": UNIT_MIN_SALES},
        "house_panel": house_panel,
        "unit_panel": unit_panel,
        "all_screened": rows,
    }
    out_path.write_text(json.dumps(out, indent=2))

    print("\n=== PANEL SUMMARY ===")
    for st in ("NSW", "VIC", "QLD"):
        hp = house_panel[st]
        up = unit_panel[st]
        h_sales = sum(x["house_sales_12mo"] or 0 for x in hp)
        u_sales = sum(x["unit_sales_12mo"] or 0 for x in up)
        print(f"{CITY_LABEL[st]}:")
        print(f"  HOUSE panel: {len(hp)} suburbs, {h_sales} house sales/yr pooled — "
              f"{', '.join(x['suburb'] for x in hp)}")
        print(f"  UNIT  panel: {len(up)} suburbs, {u_sales} unit sales/yr pooled — "
              f"{', '.join(x['suburb'] for x in up)}")
    print(f"\nWrote {out_path}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    screen(args.out)


if __name__ == "__main__":
    main()
