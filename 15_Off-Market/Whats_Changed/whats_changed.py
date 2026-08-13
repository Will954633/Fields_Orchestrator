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
    """⚠ EVERY POINT HERE IS HOUSE-ONLY, so each is tagged `house_only`.

    The sources — `precomputed_indexed_prices` and `precomputed_market_charts` — are
    houses-only by construction (`precompute_union_prices.py` filters
    `classify_dwelling == "house"`), and there is no dwelling dimension in their keys.
    An attached dwelling's page drops these entirely rather than showing the reader a
    median that is not their market. The attached equivalent lives in
    `Gold_Coast.unit_market_series` and is rendered by the unit market section.
    """
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
        out.append({"date": now - datetime.timedelta(days=45), "kind": "suburb", "house_only": True, "text": text,
                    "source": f"Fields analysis of {suburb_name} sales", "magnitude": 0})

    dom = db["precomputed_market_charts"].find_one({"_id": f"{suburb_key}_days_on_market"}) or {}
    hist = [h for h in (dom.get("timeline") or []) if h.get("median_days_on_market")]
    if len(hist) >= 2:
        first, last = hist[max(0, len(hist) - 7)], hist[-1]
        if first["median_days_on_market"] != last["median_days_on_market"]:
            direction = "longer" if last["median_days_on_market"] > first["median_days_on_market"] else "shorter"
            out.append({
                "date": now - datetime.timedelta(days=30), "kind": "suburb", "house_only": True,
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
            word = "longer" if d1 > d0 else "less time"
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
        # ⚠ THE MACRO FACT AND THE LOCAL READING ARE SEPARATE FIELDS, ON PURPOSE.
        # `local` comes from suburb_reading(), which is HOUSE data — median house
        # price, house days-on-market, house listing counts. The macro statement (a
        # cash-rate move, a tax change) is national and true for every dwelling; the
        # local clause is about somebody else's market when the reader owns a unit.
        #
        # Emitting them concatenated is why an attached dwelling's page read "the
        # Robina median house price is broadly unchanged — $1,490,000". That was fixed
        # by hand in the GENERATED file on 2026-08-10 and silently undone on 2026-08-12
        # when this script next ran. Fixing generated output instead of its generator
        # buys about two days.
        # The same question answered with the reader's own market. See unit_reading.
        u_local = unit_reading(db, suburb_key, suburb_name, e.get("local_metric"), d)
        u2 = unit_reading(db, suburb_key, suburb_name, e.get("local_metric_2"), d)
        if u_local and u2:
            u_local = f"{u_local} {u2}"
        out.append({
            "date": d, "kind": "macro",
            "text": f"**{d:%-d %B %Y}** — {' '.join(e['statement'].split())}",
            "house_local": local,
            "unit_local": u_local,
            "source": e["source"], "magnitude": 0,
        })
    return out


def watch_metric_now(db, suburb_key, suburb_name, metric):
    """The CURRENT level of the number a watch point promises to re-read.

    Present tense and forward-facing: "the number we will be watching is X,
    currently Y". No movement claim, because the movement has not happened."""
    if metric == "days_on_market":
        dom = db["precomputed_market_charts"].find_one({"_id": f"{suburb_key}_days_on_market"}) or {}
        tl = [t for t in (dom.get("timeline") or []) if t.get("median_days_on_market")]
        if tl:
            return (f"The number we will be watching in {suburb_name} is how long homes take to "
                    f"sell — currently a median of {tl[-1]['median_days_on_market']:.0f} days.")
    if metric == "active_listings":
        al = db["precomputed_active_listings"].find_one({"_id": suburb_key}) or {}
        snaps = al.get("snapshots") or []
        if snaps:
            return (f"The number we will be watching in {suburb_name} is how many homes are on the "
                    f"market — currently {snaps[-1].get('active_listings'):,}.")
    if metric == "median_price":
        px = db["precomputed_indexed_prices"].find_one({"_id": suburb_key}) or {}
        roll = [r for r in (px.get("rolling_12m_median_series") or []) if not r.get("is_in_progress")]
        if roll:
            return (f"The number we will be watching in {suburb_name} is the median house price — "
                    f"currently {money(roll[-1]['rolling_median'])} on a 12-month rolling basis.")
    return None


def unit_series(db, suburb_key):
    """The attached-dwelling series — the unit equivalent of the house precomputes."""
    return db["unit_market_series"].find_one({"_id": suburb_key}) or {}


def unit_reading(db, suburb_key, suburb_name, metric, since):
    """The local clause for an ATTACHED dwelling.

    ⚠ WHY THIS EXISTS RATHER THAN JUST SUPPRESSING THE HOUSE LINE.
    `suburb_reading` is house data throughout — median HOUSE price, house
    days-on-market, house listing counts. Dropping it for units left the macro
    events with no local clause at all, and left the watch point quoting the
    HOUSE figure outright: unit pages read "how long homes take to sell —
    currently a median of 34 days" when the Robina attached median is 20.
    A unit owner reading 34 is reading somebody else's market.

    We hold the attached equivalents in `unit_market_series`, so the honest fix
    is to answer the same question with the right number, not to go quiet.
    """
    u = unit_series(db, suburb_key)
    if not u:
        return None
    if metric == "days_on_market":
        d = u.get("median_days_on_market")
        if d:
            return (f"Over the same period, attached homes in {suburb_name} have taken a "
                    f"median of {d:.0f} days to sell.")
    if metric == "active_listings":
        n = u.get("active_listings")
        if n:
            return (f"Since then, {n:,} attached homes are on the market in {suburb_name}.")
    if metric == "median_price":
        roll = [r for r in (u.get("rolling_12m") or [])
                if r.get("period") != u.get("in_progress_period") and r.get("rolling_median")]
        if len(roll) >= 2:
            prev, last = roll[-2], roll[-1]
            pct = (last["rolling_median"] - prev["rolling_median"]) / prev["rolling_median"] * 100
            steady = "broadly unchanged" if abs(pct) < 3 else ("higher" if pct > 0 else "lower")
            return (f"Locally the {suburb_name} median unit price is {steady} over the same "
                    f"period — {money(last['rolling_median'])} on a 12-month rolling basis in "
                    f"{last['period']}, {pct:+.1f}% on the quarter before.")
    return None


def unit_watch_metric_now(db, suburb_key, suburb_name, metric):
    """Present-tense level of the watched number, for an attached dwelling."""
    u = unit_series(db, suburb_key)
    if not u:
        return None
    if metric == "days_on_market":
        d = u.get("median_days_on_market")
        if d:
            return (f"The number we will be watching in {suburb_name} is how long attached "
                    f"homes take to sell — currently a median of {d:.0f} days.")
    if metric == "active_listings":
        n = u.get("active_listings")
        if n:
            return (f"The number we will be watching in {suburb_name} is how many attached "
                    f"homes are on the market — currently {n:,}.")
    if metric == "median_price":
        m = u.get("latest_rolling_median")
        if m:
            return (f"The number we will be watching in {suburb_name} is the median unit "
                    f"price — currently {money(m)} on a 12-month rolling basis.")
    return None


def watch_points(db, suburb_key, suburb_name, now):
    """The one dated thing ahead that will move this narrative.

    ⚠ NO FORECAST, IN EITHER DIRECTION. This says a decision is scheduled and
    names the local number it will be read against. It does not say what the
    decision will be, what it would mean, or what anyone expects — an attributed
    forecast is still a forecast on a homeowner's report.

    ⚠ SILENCE ON EXPIRY, LOUDLY. A watch whose date has passed with no `outcome`
    written renders NOTHING and warns on stderr. "Coming up 11 August" still
    sitting there on 15 August tells the reader nobody is maintaining this, which
    costs more than the point was ever worth.
    """
    cfg = yaml.safe_load((HERE / "events.yaml").read_text())
    out = []
    for w in cfg.get("watch") or []:
        d = w["date"]
        d = datetime.datetime.combine(d, datetime.time()) if isinstance(d, datetime.date) else d
        # ⚠ AEST CALENDAR DAYS, not a UTC timedelta. `now` is UTC, so on the
        # evening of 10 August AEST the floor of the difference is 0 and a
        # decision that is genuinely tomorrow renders as "today". The business
        # and the reader are both in Brisbane.
        aest_today = (now + datetime.timedelta(hours=10)).date()
        days = (d.date() - aest_today).days
        if days < 0 and not w.get("outcome"):
            print(f"  ⚠ watch '{w['id']}' expired {abs(days)}d ago with no outcome recorded "
                  f"— dropped from the report", file=sys.stderr)
            continue
        if w.get("outcome"):
            continue          # resolved: belongs in the timeline, not here
        # ⚠ FORWARD PHRASING, not `suburb_reading`. That function writes "over the
        # same period, homes have taken longer to sell" — past tense about a
        # thing that has not happened. What belongs here is the CURRENT level of
        # the number we are promising to re-read, so the reader can check us.
        reading = watch_metric_now(db, suburb_key, suburb_name, w.get("metric_to_watch"))
        u_reading = unit_watch_metric_now(db, suburb_key, suburb_name, w.get("metric_to_watch"))
        when = ("tomorrow" if days == 1 else "today" if days == 0
                else f"in {days} days")
        # ⚠ "Varsity Lakes's" — a name already ending in s takes a bare
        # apostrophe. The only suburb of the three it affects, and it reads as
        # carelessness on the one line asking the reader to trust us to come back.
        poss = f"{suburb_name}'" if suburb_name.endswith("s") else f"{suburb_name}'s"
        text = (f"**Coming up — {d:%-d %B %Y} ({when})** — {' '.join(w['statement'].split())} "
                f"We will re-read {poss} numbers against it and update this page.")
        # ⚠ DO NOT CONCATENATE THE READING INTO `text`.
        # It used to be appended here, which made it unfilterable — so every unit page
        # published the HOUSE days-on-market (34) as though it were the reader's own
        # market (20). Emitted as house_local/unit_local, the consumer picks the one
        # that matches the dwelling, exactly as the macro events already do.
        out.append({"date": d, "kind": "watch", "text": text,
                    "house_local": reading, "unit_local": u_reading,
                    "source": w["source"], "magnitude": 0,
                    "lead": days <= 7})
    return out


# ── Assembly ─────────────────────────────────────────────────────────────────

def build(db, doc, max_points=4):
    now = datetime.datetime.utcnow()
    suburb_key = doc.get("_suburb_collection") or (doc.get("suburb") or "").lower().replace(" ", "_")
    suburb_name = (doc.get("suburb") or suburb_key.replace("_", " ").title())
    suburb_name = suburb_name.title() if suburb_name.islower() else suburb_name

    points = (comp_events(doc, now)[:1]
              + aggregate_sales_point(doc, now)
              + suburb_events(db, suburb_key, suburb_name, now)
              + macro_events(db, suburb_key, suburb_name, now))
    points.sort(key=lambda p: p["date"])

    # ⚠ A WATCH POINT IS NOT PART OF THE TIMELINE — it is the reason to return,
    # so it leads when it is imminent (within a week) and otherwise closes the
    # list. Sorting it by date would bury tomorrow's RBA decision at the bottom
    # under things that already happened.
    watch = watch_points(db, suburb_key, suburb_name, now)
    lead = [w for w in watch if w.get("lead")]
    trail = [w for w in watch if not w.get("lead")]

    # Property-specific points always survive the cap: they are the only layer
    # that is about this home rather than about the postcode.
    if len(points) > max_points:
        prop = [p for p in points if p["kind"] == "property"]
        rest = [p for p in points if p["kind"] != "property"]
        points = sorted(prop + rest[: max_points - len(prop)], key=lambda p: p["date"])
    return lead + points + trail


MAX_GENERATED_POINTS = 3   # suburb + macro; the property layer adds up to 2 more

# Fingerprints of the local readings, so the same measured sentence cannot be
# attached to two different events. Keyed on the distinctive figure rather than
# the whole string, because the surrounding wording differs by event.
def _reading_key(text):
    import re as _re
    m = _re.search(r"(\$[\d,]+|\d+ days)", text or "")
    return m.group(1) if m else None


def _dedupe_readings(points):
    """Drop a point whose local reading repeats a figure already on screen.

    The event statement is always unique; the LOCAL half is what repeats, and it
    is the half a reader recognises. Keeping the earlier point is deliberate —
    it is the one whose date the reading was measured against.

    ⚠ EXCEPT AGAINST A `suburb` POINT, WHICH HAS NO REAL DATE TO BE MEASURED
    AGAINST. The "**Now** — homes are taking 34 days to sell" bullet is dated
    `now - 30d`, a synthetic value that exists only to sort it; nothing was
    measured "since" it. So "earlier wins" — which is sound between two macro
    events — silently ranked that bare restatement above a dated fact carrying
    the same figure. On 2026-08-13 that dropped the 11 August RBA decision from
    every page: the watch had promised we would re-read the local numbers
    against it and publish the result, and the result was the point discarded.
    A macro event is the same reading WITH its reason attached, so it outranks
    the restatement whatever the dates say; macro-vs-macro is still earliest.
    """
    rank = {"macro": 0, "property": 0, "suburb": 1}
    seen, out = set(), []
    for p in sorted(points, key=lambda x: (rank.get(x["kind"], 0), x["date"])):
        k = _reading_key(p["text"].split("—", 1)[-1])
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        out.append(p)
    return out


def emit_ts(db, out_path):
    """Write the suburb / macro / watch layers as a TypeScript constant.

    ⚠ THE HARNESS IS THE GENERATOR, NOT THE RUNTIME. These three layers are the
    same for every home in a suburb, so recomputing them per request would be
    three extra queries to say the same sentence 12,000 times. They are generated
    here and checked in, exactly as ACCURACY and ADJUSTMENT_BENEFIT are.

    ⚠ THE PROPERTY LAYER IS NOT IN HERE. It is per-home and is computed in the
    route loader from `valuation_data`, which the page already holds.

    `generatedAt` is load-bearing: the component renders nothing from this
    constant once it is older than 45 days, so forgetting to re-run this degrades
    the block to silence rather than to a stale claim.
    """
    now = datetime.datetime.utcnow()
    blocks = []
    for key, name in (("robina", "Robina"), ("varsity_lakes", "Varsity Lakes"),
                      ("burleigh_waters", "Burleigh Waters")):
        # ⚠ DEDUPE THE LOCAL READINGS, THEN CAP.
        # Three events each pair with a local metric, and the first render put
        # "$1,490,000 on a 12-month rolling basis, -1.7%" on screen THREE times
        # (12 May, Q2 2026, 31 July) and the 34-day figure twice. A reader counts
        # that as one fact repeated, not four facts — and repetition on a page
        # arguing for rigour reads as padding. Each metric now speaks once, and
        # the whole layer is capped so the block lands at Will's 3-5 points once
        # the property layer is added on top.
        suburb_pts = suburb_events(db, key, name, now)
        macro_pts = macro_events(db, key, name, now)
        pts = _dedupe_readings(suburb_pts + macro_pts)[:MAX_GENERATED_POINTS]
        pts += watch_points(db, key, name, now)
        rows = []
        for p in sorted(pts, key=lambda x: x["date"]):
            rows.append("      {\n"
                        f'        date: "{p["date"]:%Y-%m-%d}",\n'
                        f'        kind: "{p["kind"]}",\n'
                        f'        text: {json.dumps(p["text"])},\n'
                        f'        source: {json.dumps(p["source"])},\n'
                        # House-only clauses ride separately so the component can drop
                        # them for attached dwellings — see TimelinePoint.houseLocal.
                        + (f'        houseLocal: {json.dumps(p["house_local"])},\n'
                           if p.get("house_local") else "")
                        + (f'        unitLocal: {json.dumps(p["unit_local"])},\n'
                           if p.get("unit_local") else "")
                        + (f'        houseOnly: true,\n' if p.get("house_only") else "")
                        + (f'        lead: true,\n' if p.get("lead") else "")
                        + "      },")
        blocks.append(f'  {key}: [\n' + "\n".join(rows) + "\n  ],")

    ts = f"""// GENERATED — do not edit by hand.
//   python3 15_Off-Market/Whats_Changed/whats_changed.py --emit-ts <path>
//
// The suburb, macro and watch layers of "What's changed recently". Identical for
// every home in a suburb, so they are generated once rather than recomputed per
// request. The PROPERTY layer is per-home and is built in the route loader from
// `valuation_data` — see `whatsChanged.server.ts`.
//
// ⚠ REGENERATE MONTHLY, alongside the homeowner research that feeds
// `events.yaml`. `generatedAt` is enforced: `TIMELINE_MAX_AGE_DAYS` below makes
// the component drop this entire layer once it is stale, so a forgotten refresh
// costs a quieter page rather than a wrong one.

export type TimelinePoint = {{
  date: string;
  kind: "suburb" | "macro" | "watch";
  text: string;
  source: string;
  /** Forward-looking and imminent — renders first, not in date order. */
  lead?: boolean;
  /** ⚠ HOUSE-ONLY CLAUSE. Every suburb figure in this file — median price, days on
   *  market, listing counts — comes from a houses-only series. On an attached
   *  dwelling's page those sentences are about somebody else's market, so the
   *  component appends this only for houses. The macro fact in `text` is
   *  dwelling-neutral and always runs. Do NOT fold these back into `text`. */
  houseLocal?: string;
  unitLocal?: string;
  /** The whole entry is a house figure — dropped entirely for attached dwellings. */
  houseOnly?: boolean;
}};

export const TIMELINE_GENERATED_AT = "{now:%Y-%m-%d}";

/** Past this, the generated layer stops rendering. Roughly one missed monthly
 *  refresh plus a fortnight of slack. */
export const TIMELINE_MAX_AGE_DAYS = 45;

export const SUBURB_TIMELINE: Record<string, TimelinePoint[]> = {{
{chr(10).join(blocks)}
}};
"""
    Path(out_path).write_text(ts)
    print(f"  wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--out", default="MOCKUP.md")
    ap.add_argument("--emit-ts", default=None)
    args = ap.parse_args()

    db = get_gold_coast_db()
    if args.emit_ts:
        emit_ts(db, args.emit_ts)
        return
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
