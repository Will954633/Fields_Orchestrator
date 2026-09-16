#!/usr/bin/env python3
"""build_auction_clearance_json.py — bake public/data/auction_clearance.json, the
data behind the capital-city auction clearance chart on /news/gold-coast.

SOURCE: SQM Research auction-results page embeds a per-city weekly clearance
history in a JS `auction_history` variable — {enddate, rCity, ttl (scheduled),
sold, clearance}. The `?state=XX` query switches which capital's history is
embedded (NSW->Sydney, VIC->Melbourne, QLD->Brisbane, SA->Adelaide, ACT->Canberra).
Data starts 2020-02. curl_cffi direct (SQM allows it — no proxy).

WHY combined type / no Gold Coast (documented so nobody "fixes" it later):
SQM tracks auction CAPITALS only and publishes a single combined clearance per
city — there is no house/unit split and no Gold Coast series in the history
(the GC is a private-treaty market; it only appears as individual current-week
QLD auction cards, never as a trend). Confirmed 2026-09-16 by mapping the page.

SMOOTHING: raw weekly clearance is noisy (holiday weeks schedule 2-3 auctions and
swing wildly). We emit a trailing-4-week VOLUME-WEIGHTED clearance sampled weekly
(sum sold / sum scheduled over the window) — the standard smoothed presentation,
holiday-proof, granular enough for the 1-year view. Each point carries n.

Usage: python3 scripts/build_auction_clearance_json.py [--dry-run] [--out PATH]
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared.env import load_env  # noqa: E402
from job_status import job_run  # noqa: E402

from curl_cffi import requests  # noqa: E402

DEFAULT_OUT = Path("/home/fields/Feilds_Website/01_Website/public/data/auction_clearance.json")
BASE = "https://sqmresearch.com.au/property/auction-results"

# The five capitals with a real auction market + full (~333+ week) history.
# state -> (key, label, color). Colours: validated categorical set, distinct in light.
CITIES = [
    ("NSW", "sydney", "Sydney", "#b76749"),
    ("VIC", "melbourne", "Melbourne", "#8b5cf6"),
    ("QLD", "brisbane", "Brisbane", "#0284c7"),
    ("SA", "adelaide", "Adelaide", "#16a34a"),
    ("ACT", "canberra", "Canberra", "#c6922b"),
]
ROLL_WEEKS = 4          # trailing volume-weighted window
MIN_WINDOW_N = 20       # drop points whose 4-week window scheduled < this (holiday gaps)

_REC = re.compile(r'\{"enddate":"([^"]+)","rCity":"([^"]+)","ttl":(\d+),"sold":(\d+),"clearance":"([\d.]+)"\}')


def fetch_city(state):
    r = requests.get(f"{BASE}?state={state}", impersonate="chrome120", timeout=30)
    recs = [{"enddate": d, "city": c, "ttl": int(t), "sold": int(s)}
            for d, c, t, s, _cl in _REC.findall(r.text)]
    recs.sort(key=lambda x: x["enddate"])
    return recs


def rolling_series(recs):
    """Trailing-ROLL_WEEKS volume-weighted clearance, sampled weekly."""
    out = []
    for i in range(len(recs)):
        window = recs[max(0, i - ROLL_WEEKS + 1): i + 1]
        if i < ROLL_WEEKS - 1:
            continue  # incomplete leading window
        n = sum(w["ttl"] for w in window)
        sold = sum(w["sold"] for w in window)
        if n < MIN_WINDOW_N:
            continue
        out.append({"week": recs[i]["enddate"], "clearance": round(sold / n, 4), "n": n})
    return out


def build(dry_run=False, out_path=DEFAULT_OUT):
    load_env()
    cities = {}
    for state, key, label, color in CITIES:
        recs = fetch_city(state)
        series = rolling_series(recs)
        cities[key] = {"label": label, "color": color, "series": series,
                       "latest": series[-1]["clearance"] if series else None}
        print(f"  {label:<10} {len(recs)} raw weeks -> {len(series)} smoothed pts | "
              f"latest {round((series[-1]['clearance'] if series else 0)*100)}% "
              f"({series[-1]['week'] if series else '-'})")

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "basis_note": (
            "Auction clearance rate = properties sold (prior to, at, or after auction) as a "
            "share of all auctions scheduled, from SQM Research; shown as a trailing 4-week "
            "volume-weighted rate to smooth week-to-week noise. Combined property types (auction "
            "clearance is not split house vs unit). Capital cities only — the Gold Coast is a "
            "private-treaty market, not an auction market, so it has no clearance series. "
            "Data begins February 2020. Not comparable with other providers, whose definitions differ."),
        "cities": cities,
    }

    # Rule 7b — every city must carry a usable line or the source broke.
    for _s, key, label, _c in CITIES:
        if len(cities[key]["series"]) < 50:
            raise RuntimeError(
                f"{label} has only {len(cities[key]['series'])} smoothed points — "
                f"SQM scrape under-delivered, not writing auction_clearance.json.")

    if dry_run:
        print("\n(dry-run — not written)")
        return out
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"\nWrote {out_path} ({out_path.stat().st_size} bytes)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    with job_run("build_auction_clearance", cadence_hours=24 * 8,
                 title="Capital-city auction clearance JSON (SQM)") as beat:
        out = build(dry_run=args.dry_run, out_path=args.out)
        beat.detail = ", ".join(f"{c[2]} {round((out['cities'][c[1]]['latest'] or 0)*100)}%" for c in CITIES)
        beat.metrics = {c[1]: len(out["cities"][c[1]]["series"]) for c in CITIES}


if __name__ == "__main__":
    main()
