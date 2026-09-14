#!/usr/bin/env python3
"""build_rental_yields.py — gross rental-yield series (rent×52 / asking price) for the
GC overview page and the three core suburb pages, each vs Brisbane / Sydney / Melbourne.

All from SQM (rent and price on the SAME source & geography, so the ratio is honest):
  - Capitals + GC region:  Gold_Coast.sqm_city_series  (rents_series + asking_series)
  - Suburb rent:           Gold_Coast.sqm_weekly_rents  (by postcode)
  - Suburb asking:         Gold_Coast.sqm_asking_prices (by suburb key)

Resampled to quarter-end (last weekly obs per quarter), yield computed per quarter
where both rent and price exist. Houses use *_all house fields, units *_all unit
fields. Gross yield (no costs) — labelled as such; editorial: data + source only.

Outputs to public/data/:
  gc_rental_yields.json            (GC overview page)
  rental_yields_<suburb>.json      (robina / burleigh_waters / varsity_lakes)

⚠ SQM ToS: republication is a Will decision (he requested these charts).

Usage: python3 scripts/build_rental_yields.py [--dry-run]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402

OUT_DIR = Path("/home/fields/Feilds_Website/01_Website/public/data")
CAPITALS = ["brisbane", "sydney", "melbourne"]
SUBURBS = {  # suburb key -> (rent postcode, display label)
    "robina": ("4226", "Robina"),
    "burleigh_waters": ("4220", "Burleigh Waters"),
    "varsity_lakes": ("4227", "Varsity Lakes"),
}


def to_quarter(date_str):
    y, m = int(date_str[:4]), int(date_str[5:7])
    return f"{y}-Q{(m - 1) // 3 + 1}"


def quarterly_last(series, field):
    """Last non-null value of `field` per quarter, as {quarter: value}."""
    out = {}
    for row in sorted(series, key=lambda r: r["date"]):
        v = row.get(field)
        if v:
            out[to_quarter(row["date"])] = v
    return out


def yield_series(rents, asking, rent_field, ask_field):
    """Quarterly gross yield % where both rent and price exist."""
    rq = quarterly_last(rents, rent_field)
    aq = quarterly_last(asking, ask_field)
    quarters = sorted(set(rq) & set(aq), key=lambda q: (int(q[:4]), int(q[-1])))
    return [{"q": q, "y": round(rq[q] * 52 / aq[q] * 100, 2)} for q in quarters if aq[q]]


def build(dry_run=False):
    db = get_client()["Gold_Coast"]
    city = {d["_id"]: d for d in db["sqm_city_series"].find({})}
    missing = [g for g in ["gold_coast"] + CAPITALS if g not in city]
    if missing:
        raise RuntimeError(f"sqm_city_series missing {missing} — run scrape_sqm_city_comparison.py")

    # Capital yield series (reused by every page), houses + units
    cap = {}
    for g in CAPITALS:
        cap[g] = {
            "houses": yield_series(city[g]["rents_series"], city[g]["asking_series"], "houses_all", "houses_all"),
            "units": yield_series(city[g]["rents_series"], city[g]["asking_series"], "units_all", "units_all"),
        }

    def merge(local_series, local_key):
        """Merge a local yield series with the 3 capitals onto shared quarters."""
        out = {"houses": [], "units": []}
        for dw in ("houses", "units"):
            local = {p["q"]: p["y"] for p in local_series[dw]}
            capq = {g: {p["q"]: p["y"] for p in cap[g][dw]} for g in CAPITALS}
            quarters = sorted(local, key=lambda q: (int(q[:4]), int(q[-1])))
            for q in quarters:
                row = {"q": q, local_key: local[q]}
                for g in CAPITALS:
                    if q in capq[g]:
                        row[g] = capq[g][q]
                out[dw].append(row)
        return out

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    written = []

    # GC overview page
    gc_local = {
        "houses": yield_series(city["gold_coast"]["rents_series"], city["gold_coast"]["asking_series"], "houses_all", "houses_all"),
        "units": yield_series(city["gold_coast"]["rents_series"], city["gold_coast"]["asking_series"], "units_all", "units_all"),
    }
    gc_out = {"generated": stamp, "local_key": "gold_coast", "local_label": "Gold Coast",
              "metric": "gross_rental_yield_pct",
              "source": "SQM Research — weekly asking rents ÷ asking prices (gross yield)",
              **merge(gc_local, "gold_coast")}
    print(f"gold_coast: houses {len(gc_out['houses'])}q (latest {gc_out['houses'][-1] if gc_out['houses'] else '-'}), "
          f"units {len(gc_out['units'])}q")
    if not dry_run:
        (OUT_DIR / "gc_rental_yields.json").write_text(json.dumps(gc_out, separators=(",", ":")) + "\n")
        written.append("gc_rental_yields.json")

    # Suburb pages
    for skey, (pc, label) in SUBURBS.items():
        rent_doc = db["sqm_weekly_rents"].find_one({"_id": pc})
        ask_doc = db["sqm_asking_prices"].find_one({"_id": skey})
        if not rent_doc or not ask_doc:
            print(f"{skey}: MISSING rent({bool(rent_doc)}) / asking({bool(ask_doc)}) — skipped")
            continue
        local = {
            "houses": yield_series(rent_doc["series"], ask_doc["series"], "houses_all", "houses_all"),
            "units": yield_series(rent_doc["series"], ask_doc["series"], "units_all", "units_all"),
        }
        out = {"generated": stamp, "local_key": skey, "local_label": label, "postcode": pc,
               "metric": "gross_rental_yield_pct",
               "source": "SQM Research — weekly asking rents ÷ asking prices (gross yield)",
               **merge(local, skey)}
        print(f"{skey}: houses {len(out['houses'])}q (latest {out['houses'][-1] if out['houses'] else '-'})")
        if not dry_run:
            (OUT_DIR / f"rental_yields_{skey}.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
            written.append(f"rental_yields_{skey}.json")

    if dry_run:
        print("(dry run — nothing written)")
    else:
        print("wrote:", ", ".join(written))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    load_env()
    build(dry_run=ap.parse_args().dry_run)
