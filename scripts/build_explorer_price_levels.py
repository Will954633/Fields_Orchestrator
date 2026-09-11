#!/usr/bin/env python3
"""Analysis tool: build `priceLevel` (median house price, $) for the /news explorer data.

⚠ FEATURE CANCELLED 2026-09-11 — do not wire this into the explorer without re-asking Will.
The "Median house price" view pill was requested and then cancelled the same day, because
this script's guard surfaced that the COMBINED 3-suburb median level line shows NO
peak/decline in 2026 (Robina peaked 2026-Q1 $1,515,000 → $1,495,000, but Burleigh Waters
and Varsity Lakes kept rising, so pooled goes $1,565,000 → $1,573,000 — flat-to-up) —
which would visually contradict the walkthrough narration ("prices started declining end
of 2025 into early 2026"). Will's decision: keep the momentum view exactly as it is.
Kept for the loaders/method and the guard, and because the numbers above are a verified
data finding (union-median based, consistent with published suburb medians).

The explorer (`public/data/leading_indicators.json` in Website_Version_Feb_2026) ships
`price` = year-ended % momentum only (pooled = arithmetic mean of the three suburb
momentum series — verified against the baked JSON). A level view would need this series:
a 12-month rolling median of sold house prices, sampled at each quarter of `E.quarters`,
for pooled + each suburb.

Source: the SAME Domain ∪ onthehouse union used for every published median on the
site (`scripts/precompute_union_prices.py` loaders — houses only, address_key join,
contract/settlement dedupe). Do NOT substitute a timeline-only series: the Domain
timeline scrape is ~6 months stale, which biases the 2026 tail upward (it showed
pooled RISING through 2026-Q2 where the union series — and the published suburb
medians — peak in Q1).

One-shot manual tool (not scheduled — no heartbeat needed). Re-run after a data
refresh, then push the JSON to the website repo.

Usage:
    python3 scripts/build_explorer_price_levels.py           # dry-run: print, no write
    python3 scripts/build_explorer_price_levels.py --write   # patch the JSON in place
"""

import argparse
import json
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from collections import defaultdict            # noqa: E402

from shared.db import get_client               # noqa: E402
from precompute_union_prices import (          # noqa: E402
    load_domain_history, load_onthehouse, dedupe_sales,
    PRICE_FLOOR, PRICE_CEILING, SUBURBS,
)

JSON_PATH = Path("/home/fields/Feilds_Website/01_Website/public/data/leading_indicators.json")
MIN_N = 5  # below this a rolling median is null (matches union pipeline's floor idea)


def quarter_end(q: str) -> date:
    """'2026-Q2' -> 2026-06-30"""
    y, qq = int(q[:4]), int(q[-1])
    m = qq * 3
    nxt = date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
    return nxt - timedelta(days=1)


def rolling_levels(sales, quarters):
    """sales: {(key, 'YYYY-MM-DD'): price} -> 12m-rolling median at each quarter end."""
    dated = sorted((d, p) for (_, d), p in sales.items()
                   if PRICE_FLOOR <= p <= PRICE_CEILING)
    out = []
    for q in quarters:
        end = quarter_end(q).isoformat()
        start = (quarter_end(q) - timedelta(days=365)).isoformat()
        vals = [p for d, p in dated if start < d <= end]
        out.append(int(statistics.median(vals)) if len(vals) >= MIN_N else None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="patch priceLevel into the JSON")
    args = ap.parse_args()

    E = json.loads(JSON_PATH.read_text())
    quarters = E["quarters"]

    client = get_client()
    gc, sm = client["Gold_Coast"], client["system_monitor"]

    per_sub, pooled_events = {}, {}
    for suburb in SUBURBS:
        counters = defaultdict(int)
        events = load_domain_history(gc, suburb, counters) + load_onthehouse(sm, suburb, counters)
        sales = dedupe_sales(events)
        per_sub[suburb] = sales
        # address_key includes the street address; prefix with suburb to be collision-safe
        pooled_events.update({(f"{suburb}|{k}", d): p for (k, d), p in sales.items()})
        print(f"{suburb}: {len(sales)} deduped sales")

    levels = {"pooled": rolling_levels(pooled_events, quarters)}
    for suburb in SUBURBS:
        levels[suburb] = rolling_levels(per_sub[suburb], quarters)

    # sanity: tails + implied YoY vs the shipped momentum
    for k, lvl in levels.items():
        tail = [(quarters[i], lvl[i]) for i in range(len(quarters) - 4, len(quarters))]
        print(f"{k} tail: {tail}")
        yoy = [round((lvl[i] / lvl[i - 4] - 1) * 100, 2)
               if lvl[i] and lvl[i - 4] else None for i in range(len(quarters))]
        ref = E["price"].get(k, [])
        comp = [(a, b) for a, b in zip(yoy, ref) if a is not None and b is not None]
        close = sum(1 for a, b in comp if abs(a - b) < 1.0)
        print(f"  implied-YoY vs shipped momentum: {close}/{len(comp)} within 1pp "
              f"(display series is the union median; momentum panel keeps its own series)")

    # the walkthrough circles the pooled peak inside the 3-year window — assert it exists
    i0 = quarters.index("2023-Q3")
    win = levels["pooled"][i0:]
    peak_rel = max(range(len(win)), key=lambda i: win[i] or 0)
    peak_q = quarters[i0 + peak_rel]
    print(f"pooled 3y-window peak: {peak_q} = ${win[peak_rel]:,}")
    if peak_rel == len(win) - 1:
        raise RuntimeError("pooled level peaks at the FINAL quarter — no visible peak to "
                           "circle; the narration ('declined from early 2026') would be "
                           "contradicted. Investigate before shipping.")

    if args.write:
        E["priceLevel"] = levels
        JSON_PATH.write_text(json.dumps(E, separators=(",", ":")))
        print(f"WROTE priceLevel to {JSON_PATH}")
    else:
        print("dry-run only (use --write to patch the JSON)")


if __name__ == "__main__":
    main()
