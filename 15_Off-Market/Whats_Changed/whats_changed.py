#!/usr/bin/env python3
"""
whats_changed.py — "What's changed recently", per property.

Three to five dated bullets covering the last six months, in date order, each
one either measured on THIS home or measured on its suburb and paired with it.

    python3 whats_changed.py --slug 5-chantilly-place-robina
    python3 whats_changed.py --sample 3 --out MOCKUP.md

THE THREE LAYERS, IN ORDER OF HOW MUCH THEY BELONG TO THE READER
───────────────────────────────────────────────────────────────────────────────
1. THIS HOME    a comparable that sold in the window, and what including it did
                to the figure — computed by re-reconciling without it, never
                asserted. This is the only layer that is genuinely about them.
2. THIS SUBURB  measured movement in our own series: median, days on market,
                active listings.
3. EVERYWHERE   dated national/state events from the monthly research, each
                paired with the local reading, never published alone.

WHY THE PROPERTY LAYER IS COMPUTED RATHER THAN NARRATED
───────────────────────────────────────────────────────────────────────────────
"13 Waitara Place sold for $1,610,000 and moved your figure" is a claim with a
number behind it: drop that comparable, re-normalise the remaining weights,
reconcile again, and the difference IS the effect. Anything else is a sentence
that sounds quantitative. The arithmetic is exact and cheap because the engine
already stores every comparable with its adjusted price and its weight.

⚠ WHAT THIS FILE MUST NEVER DO
───────────────────────────────────────────────────────────────────────────────
* No causal claims. Two series moving together is a coincidence in time and is
  written as one. "Coincided with", never "because of" (CLAUDE.md Rule 5).
* No forecasts, including attributed ones.
* No advice, no urgency, no "while conditions last".
* No suburb narrative the data cannot carry. Robina's own research note says
  no quarter-on-quarter median narrative is statistically supportable there —
  `MEDIAN_QOQ_UNSUPPORTED` encodes that, and the median bullet degrades to a
  level statement instead of a movement one.
* A layer with nothing honest to say renders nothing. Three real bullets beat
  five padded ones.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

import yaml
from shared.env import load_env
from shared.db import get_gold_coast_db

load_env()

WINDOW_DAYS = 185          # "the last six months"
MIN_COMP_EFFECT = 2_000    # below this a comparable did not move anything a reader would notice

# ⚠ Suburbs where the monthly research states a quarter-on-quarter median
# narrative is not statistically supportable. Sourced from the research's own
# §7, not from our confidence in the number.
MEDIAN_QOQ_UNSUPPORTED = {"robina"}


def money(v):
    return f"${round(v):,}" if v is not None else "—"


def as_dt(ms):
    try:
        return datetime.datetime.utcfromtimestamp(ms / 1000)
    except Exception:
        return None


# ── Layer 1: this home ───────────────────────────────────────────────────────

def reconcile(points):
    """Σ(adjusted × weight) ÷ Σ(weight) — the engine's own reconciliation."""
    num = den = 0.0
    for p in points:
        w = (p.get("weight") or {}).get("normalized") or 0
        v = (p.get("adjustment_result") or {}).get("adjusted_price")
        if w and v:
            num += v * w
            den += w
    return (num / den) if den else None


def comp_events(doc, now):
    """Comparables that sold inside the window, with the measured effect of each
    on this home's figure. Re-normalising after the drop is what makes the
    counterfactual honest: without it the removed comparable's weight simply
    vanishes and every remaining number is understated."""
    vd = doc.get("valuation_data") or {}
    pool = [p for p in (vd.get("recent_sales") or []) + (vd.get("comparables") or [])
            if (p.get("adjustment_result") or {}).get("adjusted_price")
            and (p.get("weight") or {}).get("normalized")]
    if len(pool) < 3:
        return []
    base = reconcile(pool)
    if not base:
        return []

    out = []
    for c in pool:
        sold = as_dt(c.get("sale_date"))
        if not sold or (now - sold).days > WINDOW_DAYS:
            continue
        without = reconcile([p for p in pool if p is not c])
        if not without:
            continue
        effect = base - without          # what including this sale did
        if abs(effect) < MIN_COMP_EFFECT:
            continue
        out.append({
            "date": sold,
            "kind": "property",
            "text": (
                f"**{sold:%-d %B %Y}** — {c['address'].split(',')[0]} sold for "
                f"{money(c.get('price'))}. Adjusted to this home and weighted with the "
                f"other comparable sales, including it moved the centre of this "
                f"home's range {'up' if effect > 0 else 'down'} by about "
                f"{money(abs(effect))}."
            ),
            "source": "Fields comparable-sales engine · effect measured by re-reconciling without this sale",
            "magnitude": abs(effect),
        })
    out.sort(key=lambda e: -e["magnitude"])
    return out[:2]                        # at most two — the rest is noise


def aggregate_sales_point(doc, now):
    """Every comparable that settled inside the window, as one figure.

    A single sale moves this home's centre by a few thousand — real, and smaller
    than a homeowner means by "what changed". The set of them together is the
    honest larger number, and it is the same arithmetic: reconcile with the
    window's sales, reconcile without them, take the difference."""
    vd = doc.get("valuation_data") or {}
    pool = [p for p in (vd.get("recent_sales") or []) + (vd.get("comparables") or [])
            if (p.get("adjustment_result") or {}).get("adjusted_price")
            and (p.get("weight") or {}).get("normalized")]
    if len(pool) < 4:
        return []
    recent = [p for p in pool
              if as_dt(p.get("sale_date")) and (now - as_dt(p["sale_date"])).days <= WINDOW_DAYS]
    older = [p for p in pool if p not in recent]
    if len(recent) < 2 or len(older) < 2:
        return []
    base, without = reconcile(pool), reconcile(older)
    if not base or not without:
        return []
    effect = base - without
    prices = sorted(p["price"] for p in recent if p.get("price"))
    first = min(as_dt(p["sale_date"]) for p in recent)
    direction = ("up" if effect > 0 else "down") if abs(effect) >= MIN_COMP_EFFECT else None
    moved = (f"Together they moved the centre of this home's range {direction} by about "
             f"{money(abs(effect))}." if direction else
             "Together they left the centre of this home's range effectively unchanged.")
    return [{
        "date": now - datetime.timedelta(days=1),
        "kind": "property",
        "text": (f"**Since {first:%B %Y}** — {len(recent)} sales in this home's comparison set "
                 f"have settled, from {money(prices[0])} to {money(prices[-1])}. {moved}"),
        "source": "Fields comparable-sales engine · measured by reconciling with and without the window's sales",
        "magnitude": abs(effect),
    }]


# ── Layer 2: this suburb ─────────────────────────────────────────────────────

def suburb_events(db, suburb_key, suburb_name, now):
    out = []

    price = db["precomputed_indexed_prices"].find_one({"_id": suburb_key}) or {}
    # ⚠ ROLLING 12-MONTH, NOT SINGLE QUARTERS. Reading year-on-year off
    # `indexed_series` compares two individual quarters and produced "-4.7%" for
    # Robina on the same day the report's own market card, and the monthly
    # research, both said +5.8%. Single quarters swing on which homes happened to
    # settle; the rolling series is the basis every other surface quotes, so it
    # is the basis this one must quote too.
    series = [dict(s, median_price=s["rolling_median"])
              for s in (price.get("rolling_12m_median_series") or [])
              if s.get("rolling_median") and s.get("period") and not s.get("is_in_progress")]
    if len(series) >= 5:
        latest, year_ago = series[-1], series[-5]
        pct = (latest["median_price"] - year_ago["median_price"]) / year_ago["median_price"] * 100
        if suburb_key in MEDIAN_QOQ_UNSUPPORTED:
            # Level, not movement — the research says the quarter-to-quarter
            # story is not supportable here in either direction.
            text = (f"**{latest['period']}** — the {suburb_name} median house price stands at "
                    f"{money(latest['median_price'])} on a 12-month rolling basis, {pct:+.1f}% on a year earlier. Quarterly "
                    f"sales volumes in {suburb_name} are too thin to read a quarter-to-quarter "
                    f"movement in either direction.")
        else:
            text = (f"**{latest['period']}** — the {suburb_name} median house price is "
                    f"{money(latest['median_price'])}, {pct:+.1f}% on a year earlier.")
        out.append({"date": now - datetime.timedelta(days=45), "kind": "suburb", "text": text,
                    "source": f"Fields analysis of {suburb_name} sales", "magnitude": 0})

    dom = db["precomputed_market_charts"].find_one({"_id": f"{suburb_key}_days_on_market"}) or {}
    hist = [h for h in (dom.get("timeline") or []) if h.get("median_days_on_market")]
    if len(hist) >= 2:
        first, last = hist[max(0, len(hist) - 7)], hist[-1]
        if first["median_days_on_market"] != last["median_days_on_market"]:
            direction = "longer" if last["median_days_on_market"] > first["median_days_on_market"] else "shorter"
            out.append({
                "date": now - datetime.timedelta(days=30), "kind": "suburb",
                "text": (f"**Now** — homes in {suburb_name} are taking a median of "
                         f"{round(last['median_days_on_market'])} days to sell, {direction} than the "
                         f"{round(first['median_days_on_market'])} days recorded six months earlier."),
                "source": f"Fields analysis of {suburb_name} listings", "magnitude": 0})

    return out


def suburb_reading(db, suburb_key, suburb_name, metric, since):
    """What OUR data did locally since `since` — a measured shift, not a level.

    ⚠ THE SHIFT IS COMPUTED PER SUBURB AND MAY POINT THE OTHER WAY. Measured
    2026-08-10 against the 12 May policy announcement: active listings rose 38%
    in Robina and 122% in Varsity Lakes, and FELL 21% in Burleigh Waters, whose
    days on market also got faster while the other two slowed. One written
    sentence would have been false for a third of the book. This is the same
    failure `TimingSection` already carries a warning about.

    ⚠ "Since", never "because". Two series moving in the same window is a
    coincidence in time, which is all we measured (CLAUDE.md Rule 5).
    """
    if metric == "active_listings":
        al = db["precomputed_active_listings"].find_one({"_id": suburb_key}) or {}
        snaps = sorted((al.get("snapshots") or []), key=lambda x: str(x.get("date")))
        before = [x["active_listings"] for x in snaps
                  if str(x.get("date"))[:10] < since.strftime("%Y-%m-%d") and x.get("active_listings")]
        after = [x["active_listings"] for x in snaps[-14:] if x.get("active_listings")]
        if len(before) >= 5 and after:
            b, a = sum(before) / len(before), sum(after) / len(after)
            if b:
                pct = (a - b) / b * 100
                word = "risen" if pct > 0 else "fallen"
                return (f"Since then, the number of homes on the market in {suburb_name} has {word} "
                        f"from an average of {b:.0f} before that date to {a:.0f} now "
                        f"({pct:+.0f}%).")
    if metric == "days_on_market":
        dom = db["precomputed_market_charts"].find_one({"_id": f"{suburb_key}_days_on_market"}) or {}
        tl = [t for t in (dom.get("timeline") or []) if t.get("median_days_on_market")]
        if len(tl) >= 2:
            prev, last = tl[-2], tl[-1]
            d0, d1 = prev["median_days_on_market"], last["median_days_on_market"]
            if d0 == d1:
                return (f"Over the same period, homes in {suburb_name} have taken a median of "
                        f"{d1:.0f} days to sell, unchanged on the previous quarter.")
            word = "longer" if d1 > d0 else "shorter"
            return (f"Over the same period, homes in {suburb_name} have taken {word} to sell — a "
                    f"median of {d1:.0f} days in {last['period']} against {d0:.0f} in {prev['period']}.")
    if metric == "median_price":
        px = db["precomputed_indexed_prices"].find_one({"_id": suburb_key}) or {}
        roll = [r for r in (px.get("rolling_12m_median_series") or []) if not r.get("is_in_progress")]
        if len(roll) >= 2:
            prev, last = roll[-2], roll[-1]
            pct = (last["rolling_median"] - prev["rolling_median"]) / prev["rolling_median"] * 100
            steady = "broadly unchanged" if abs(pct) < 3 else ("higher" if pct > 0 else "lower")
            return (f"Locally the {suburb_name} median house price is {steady} over the same period — "
                    f"{money(last['rolling_median'])} on a 12-month rolling basis in {last['period']}, "
                    f"{pct:+.1f}% on the quarter before.")
    return None


# ── Layer 3: everywhere ──────────────────────────────────────────────────────

def macro_events(db, suburb_key, suburb_name, now):
    cfg = yaml.safe_load((HERE / "events.yaml").read_text())
    out = []
    for e in cfg.get("events") or []:
        d = e["date"]
        d = datetime.datetime.combine(d, datetime.time()) if isinstance(d, datetime.date) else d
        if (now - d).days > WINDOW_DAYS:
            continue
        local = suburb_reading(db, suburb_key, suburb_name, e.get("local_metric"), d)
        if not local:
            continue                      # never publish the headline unpaired
        # A second local metric where the event has one — supply and price can
        # move in opposite directions in the same window, and that contrast IS
        # the local story. Optional: absent, the event still renders.
        local2 = suburb_reading(db, suburb_key, suburb_name, e.get("local_metric_2"), d)
        if local2:
            local = f"{local} {local2}"
        out.append({
            "date": d, "kind": "macro",
            "text": f"**{d:%-d %B %Y}** — {' '.join(e['statement'].split())} {local}",
            "source": e["source"], "magnitude": 0,
        })
    return out


# ── Assembly ─────────────────────────────────────────────────────────────────

def build(db, doc, max_points=5):
    now = datetime.datetime.utcnow()
    suburb_key = doc.get("_suburb_collection") or (doc.get("suburb") or "").lower().replace(" ", "_")
    suburb_name = (doc.get("suburb") or suburb_key.replace("_", " ").title())
    suburb_name = suburb_name.title() if suburb_name.islower() else suburb_name

    points = (comp_events(doc, now)[:1]
              + aggregate_sales_point(doc, now)
              + suburb_events(db, suburb_key, suburb_name, now)
              + macro_events(db, suburb_key, suburb_name, now))
    points.sort(key=lambda p: p["date"])

    # Property-specific points always survive the cap: they are the only layer
    # that is about this home rather than about the postcode.
    if len(points) > max_points:
        prop = [p for p in points if p["kind"] == "property"]
        rest = [p for p in points if p["kind"] != "property"]
        points = sorted(prop + rest[: max_points - len(prop)], key=lambda p: p["date"])
    return points


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--out", default="MOCKUP.md")
    args = ap.parse_args()

    db = get_gold_coast_db()
    docs = []
    if args.slug:
        for s in ("robina", "varsity_lakes", "burleigh_waters"):
            d = db[s].find_one({"url_slug": args.slug})
            if d:
                d["_suburb_collection"] = s
                docs.append(d)
                break
    else:
        for s in ("robina", "varsity_lakes", "burleigh_waters"):
            for d in db[s].find({"valuation_data.confidence.range.low": {"$exists": True}}
                                ).limit(max(1, args.sample)):
                d["_suburb_collection"] = s
                docs.append(d)

    lines = ["# What's changed recently — harness mock-up", "",
             f"Generated {datetime.datetime.utcnow():%-d %B %Y} · "
             f"`15_Off-Market/Whats_Changed/whats_changed.py`", ""]
    for d in docs:
        pts = build(db, d)
        lines += [f"## {d.get('address')}", ""]
        if not pts:
            lines += ["_No point in the last six months clears the bar._", ""]
            continue
        for p in pts:
            lines += [f"- {p['text']}", f"  <br><sub>{p['source']}</sub>", ""]
        lines.append("")

    Path(args.out).write_text("\n".join(lines))
    print(f"  wrote {args.out} ({len(docs)} properties)")
    print("\n".join(lines[:60]))


if __name__ == "__main__":
    main()
