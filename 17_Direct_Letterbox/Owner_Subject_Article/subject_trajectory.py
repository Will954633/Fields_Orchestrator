#!/usr/bin/env python3
"""
subject_trajectory.py -- four point-in-time valuations of ONE home, for the
article's price-trajectory section.

Backed by the backtest in `trajectory_backtest.py`, which established (n=60,
three suburbs) that a home's own comparable-based trajectory tracks its suburb's
12-month rolling median in DIRECTION 98% of the time over 18 months, correlation
0.80, typical magnitude gap ~4pp -- but that individual 6-month segments are
noise (correlation ~0). So this module produces the four anchor estimates and the
suburb median beside them, and the copy that consumes it speaks ONLY to the full
18-month direction, never to a single segment.

Method (identical to the backtest, so the page cannot disagree with the study):
run the real `precompute_valuations.precompute_property_valuation` engine as-of
each anchor date, with `time.time()`/`datetime.utcnow()` frozen at the anchor and
the sold-comparable pool filtered to sales on/before it -- no lookahead, no engine
edits. The estimate is the midpoint of the reconciled ±band; the band low/high are
carried through so the chart can draw the home's uncertainty honestly.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from statistics import median

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

import precompute_valuations as pv          # noqa: E402  the real engine

DAY_MS = 24 * 3600 * 1000
ANCHORS_MONTHS = [18, 12, 6, 0]             # months-ago, oldest first
_MONTH_DAYS = 30.44


# ------------------------------------------------------------------ as-of clock

class _AsOfDatetime(datetime):
    _frozen = None

    @classmethod
    def utcnow(cls):
        return cls._frozen

    @classmethod
    def now(cls, tz=None):
        return cls._frozen


@contextmanager
def _as_of(t_ms: float):
    t_s = t_ms / 1000.0
    _AsOfDatetime._frozen = datetime.utcfromtimestamp(t_s)
    real_dt, real_time = pv.datetime, pv.time.time
    pv.datetime = _AsOfDatetime
    pv.time.time = lambda: t_s
    try:
        yield
    finally:
        pv.datetime = real_dt
        pv.time.time = real_time


# ------------------------------------------------------------------ helpers

def _sale_ms(doc) -> float | None:
    raw = doc.get("sale_date") or doc.get("sold_date")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw[:10]).replace(
                tzinfo=timezone.utc).timestamp() * 1000
        except (ValueError, TypeError):
            return None
    return None


def _pool_as_of(sold_list: list, t_ms: float) -> list:
    """Dated sales on/before t_ms. Undated sales dropped (can't confirm age)."""
    out = []
    for d in sold_list:
        ms = _sale_ms(d)
        if ms is not None and ms <= t_ms:
            out.append(d)
    return out


def _q_ordinal(q_key: str) -> int:
    try:
        q, y = q_key.split()
        return int(y) * 4 + (int(q[1]) - 1)
    except Exception:
        return -1


def _quarter_key_of_ms(t_ms: float) -> str:
    dt = datetime.utcfromtimestamp(t_ms / 1000.0)
    return f"Q{(dt.month - 1)//3 + 1} {dt.year}"


def _rolling_12m_at(series: list, q_key: str) -> float | None:
    """rolling-12m median labelled at q_key, or the latest at/before it."""
    target = _q_ordinal(q_key)
    best = None
    for p in series:
        qk, val = p.get("period"), p.get("rolling_median")
        if not qk or val is None or p.get("is_in_progress"):
            continue
        o = _q_ordinal(qk)
        if o <= target and (best is None or o > best[0]):
            best = (o, val)
    return best[1] if best else None


def _pct(a: float, b: float) -> float | None:
    return (b - a) / a * 100.0 if a else None


# ------------------------------------------------------------------ engine setup

class TrajectoryEngine:
    """Loads the per-suburb caches once, then values any subject in that suburb
    as-of the four anchors. Reuse the instance across addresses in one suburb."""

    def __init__(self, client, suburb_key: str):
        self.client = client
        self.db = client["Gold_Coast"]
        self.suburb_key = suburb_key
        # full sold history for this suburb (we filter by date per anchor)
        self._all_sold = pv._load_sold_comparables(
            client, only_suburbs=[suburb_key]).get(suburb_key, [])
        self._coord = pv._preload_gc_coordinates(client, [suburb_key])
        self._timeline = pv._preload_gc_timelines(client, [suburb_key])
        idoc = self.db["precomputed_indexed_prices"].find_one({"_id": suburb_key}) or {}
        self._series12 = idoc.get("rolling_12m_median_series") or []

    def _estimate(self, subject_doc, t_ms):
        pool = _pool_as_of(self._all_sold, t_ms)
        median_cache = pv._build_suburb_median_cache({self.suburb_key: pool})
        street_cache = pv._build_street_premium_cache(
            {self.suburb_key: pool}, median_cache)
        with _as_of(t_ms):
            vd = pv.precompute_property_valuation(
                self.db, subject_doc, None, {self.suburb_key: pool},
                self._coord, self._timeline, median_cache, street_cache)
        if not vd:
            return None
        conf = vd.get("confidence") or {}
        rng = conf.get("range") or {}
        lo, hi = rng.get("low"), rng.get("high")
        point = conf.get("reconciled_valuation")
        if lo and hi:
            return {"mid": (lo + hi) / 2, "low": lo, "high": hi}
        if point:
            return {"mid": point, "low": None, "high": None}
        return None

    def compute(self, subject_doc, now_ms: float | None = None) -> dict | None:
        """Returns the trajectory bundle, or None if any anchor could not be
        valued (an incomplete trajectory must not be shown -- a missing point
        would read as a real dip)."""
        if now_ms is None:
            now_ms = datetime.now(timezone.utc).timestamp() * 1000
        anchors = [(m, now_ms - m * _MONTH_DAYS * DAY_MS) for m in ANCHORS_MONTHS]

        subj = {}
        for m, t in anchors:
            e = self._estimate(subject_doc, t)
            if e is None:
                return None
            subj[m] = e

        q = {m: _quarter_key_of_ms(t) for m, t in anchors}
        med12 = {m: _rolling_12m_at(self._series12, q[m]) for m in ANCHORS_MONTHS}
        if any(med12[m] is None for m in ANCHORS_MONTHS):
            return None

        base_m = ANCHORS_MONTHS[0]                      # 18
        end_m = ANCHORS_MONTHS[-1]                      # 0
        subj_full = _pct(subj[base_m]["mid"], subj[end_m]["mid"])
        med_full = _pct(med12[base_m], med12[end_m])
        if subj_full is None or med_full is None:
            return None

        # indexed to base = 100 (the honest common scale for two different levels)
        def idx(v):
            return v / subj[base_m]["mid"] * 100.0

        def idxm(v):
            return v / med12[base_m] * 100.0

        anchor_t = {m: t for m, t in anchors}

        def _month_year(t_ms):
            return datetime.utcfromtimestamp(t_ms / 1000.0).strftime("%b %Y")

        points = []
        for m in ANCHORS_MONTHS:
            e = subj[m]
            points.append({
                "months_ago": m,
                "label": "now" if m == 0 else f"−{m}m",
                "date_label": _month_year(anchor_t[m]),
                "mid": e["mid"], "low": e["low"], "high": e["high"],
                "subj_index": idx(e["mid"]),
                "band_low_index": idx(e["low"]) if e["low"] else None,
                "band_high_index": idx(e["high"]) if e["high"] else None,
                "median": med12[m], "median_index": idxm(med12[m]),
                "quarter": q[m],
            })

        return {
            "points": points,
            "subject_full_pct": subj_full,
            "median_full_pct": med_full,
            "same_direction": (subj_full >= 0) == (med_full >= 0),
            "subject_mid_now": subj[end_m]["mid"],
            "subject_mid_start": subj[base_m]["mid"],
            "median_now": med12[end_m],
            "median_start": med12[base_m],
            "span_months": base_m,
        }


def compute_trajectory(client, subject_doc, suburb_key, now_ms=None):
    """One-shot convenience wrapper."""
    return TrajectoryEngine(client, suburb_key).compute(subject_doc, now_ms)
