#!/usr/bin/env python3
"""
trajectory_backtest.py -- does a per-property comparable-based price trajectory
track the suburb rolling median?

The question
------------
The owner-subject article already shows the suburb's 12-month rolling median. We
want to ALSO show the subject home's OWN price trajectory, estimated at four
points in time (18, 12, 6, 0 months ago) from the comparable-sales engine, and
then speak to how that trajectory compares to the suburb median and to the macro
picture. Before we put a subject trajectory on the page we need to know: does it
actually track the suburb median, in DIRECTION and roughly in MAGNITUDE, or is it
noise?

How the point-in-time estimate is produced
------------------------------------------
We run the REAL production engine (`precompute_valuations.precompute_property_
valuation`) four times per subject, once as-of each anchor date T. No edits to
the engine: we

  * pre-filter the sold-comparable pool to sales with a parseable sale_date <= T
    (the engine's own 12-month filter has no upper bound -- this kills lookahead),
  * rebuild the suburb median + street-premium caches from that same <= T pool,
  * monkeypatch `time.time()` and the module's `datetime.utcnow()` to report T,
    so the 12-month window anchor, the comp time-adjustment target quarter and
    the regression's "current year" all move back to T.

So each anchor's estimate is built ONLY from what was knowable at T, using the
identical selection/adjustment/reconciliation math the live valuation uses. The
midpoint of the reconciled range is the estimate; its move across anchors is the
trajectory.

Suburb comparison series
------------------------
  * 12-month rolling median: read straight from Gold_Coast.precomputed_indexed_
    prices (`rolling_12m_median_series`), the same figure the article already
    prints, sampled at each anchor's quarter.
  * 3-month rolling median: reconstructed from the union pipeline's own loaders
    (precompute_union_prices.load_domain_history + load_onthehouse + dedupe_sales)
    re-bucketed to trailing calendar quarters of 3 months. Reliable only from the
    union coverage start (~2025-08); earlier months are Domain-only undercount and
    are flagged.

Output: a JSON report (per-subject rows + aggregate correlation/agreement stats)
and a short stderr summary. Read-only against the database.

    python3 trajectory_backtest.py --suburb robina --limit 20
    python3 trajectory_backtest.py --limit 40 --out report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time as _time_mod
from contextlib import contextmanager
from datetime import datetime, timezone
from statistics import median, mean

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

import precompute_valuations as pv          # noqa: E402  the real engine

SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
DAY_MS = 24 * 3600 * 1000
ANCHORS_MONTHS = [18, 12, 6, 0]             # months-ago for the four estimates


# ------------------------------------------------------------------ as-of clock

class _AsOfDatetime(datetime):
    """datetime subclass whose utcnow()/now() report a frozen instant.

    Subclassing (not a bare shim) so every other constructor the engine uses --
    fromtimestamp, fromisoformat, strptime -- keeps working unchanged.
    """
    _frozen = None

    @classmethod
    def utcnow(cls):
        return cls._frozen

    @classmethod
    def now(cls, tz=None):
        return cls._frozen


@contextmanager
def as_of(t_ms: float):
    """Freeze the engine's sense of 'now' at t_ms for the duration of the block."""
    t_s = t_ms / 1000.0
    frozen = datetime.utcfromtimestamp(t_s)
    _AsOfDatetime._frozen = frozen
    real_dt, real_time = pv.datetime, pv.time.time
    pv.datetime = _AsOfDatetime
    pv.time.time = lambda: t_s
    try:
        yield
    finally:
        pv.datetime = real_dt
        pv.time.time = real_time


# ------------------------------------------------------------------ anchor dates

def anchor_ms(now_ms: float, months_ago: int) -> float:
    """months_ago before now_ms, on a 30.44-day month (matches the engine's span
    arithmetic). Anchors are approximate by design -- we compare trajectories, not
    single figures."""
    return now_ms - months_ago * 30.44 * DAY_MS


def quarter_key_of_ms(t_ms: float) -> str:
    dt = datetime.utcfromtimestamp(t_ms / 1000.0)
    return f"Q{(dt.month - 1)//3 + 1} {dt.year}"


# ------------------------------------------------------------------ sold pool <=T

def _sale_ms(doc) -> float | None:
    raw = doc.get("sale_date") or doc.get("sold_date")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw[:10]).replace(tzinfo=timezone.utc).timestamp() * 1000
        except (ValueError, TypeError):
            return None
    return None


def pool_as_of(all_sold_by_suburb: dict, t_ms: float) -> dict:
    """Sold pool restricted to DATED sales on/before t_ms.

    Undated sales are DROPPED (the engine would keep them; for a backtest that is
    a silent leak of unknown-age stock). Returns a fresh dict of lists.
    """
    out = {}
    for sub, docs in all_sold_by_suburb.items():
        kept = []
        for d in docs:
            ms = _sale_ms(d)
            if ms is not None and ms <= t_ms:
                kept.append(d)
        out[sub] = kept
    return out


# ------------------------------------------------------------------ suburb series

def rolling_12m_at(series: list, q_key: str) -> float | None:
    """The rolling-12m median labelled at quarter q_key, or the latest at/before it."""
    best = None
    target = _q_ordinal(q_key)
    for p in series:
        qk = p.get("period")
        val = p.get("rolling_median")
        if not qk or val is None or p.get("is_in_progress"):
            continue
        o = _q_ordinal(qk)
        if o <= target and (best is None or o > best[0]):
            best = (o, val)
    return best[1] if best else None


def _q_ordinal(q_key: str) -> int:
    # "Q2 2026" -> 2026*4 + 1
    try:
        q, y = q_key.split()
        return int(y) * 4 + (int(q[1]) - 1)
    except Exception:
        return -1


def build_3m_series(sub_key: str) -> dict:
    """Trailing-3-month (single-quarter) rolling median by quarter, reconstructed
    from the union pipeline loaders. Returns {q_key: {'median':, 'n':, 'union':bool}}.

    'union' is True only for quarters at/after the onthehouse coverage start; before
    that the median rests on Domain-only sales and undercounts, so the caller can
    flag it rather than trust it.
    """
    try:
        import precompute_union_prices as up
        from collections import defaultdict
        from shared.db import get_client
        client = get_client()
        gc = client["Gold_Coast"]
        sm = client["system_monitor"]
        counters = defaultdict(int)
        dom = up.load_domain_history(gc, sub_key, counters)     # list[(key,date,price)]
        oth = up.load_onthehouse(sm, sub_key, counters)         # list[(key,date,price)]
        union_from_ms = min([d for d in (_iso_ms(e[1]) for e in oth) if d], default=None)
        sales = up.dedupe_sales(dom + oth)                      # {(key,date): price}
    except Exception as e:                                   # reconstruction is best-effort
        print(f"  ! 3m-median reconstruction failed for {sub_key}: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return {}
    by_q: dict[str, list] = {}
    for (key, date_str), price in sales.items():
        ms = _iso_ms(date_str)
        if not ms or not price:
            continue
        by_q.setdefault(quarter_key_of_ms(ms), []).append(price)
    out = {}
    for qk, prices in by_q.items():
        if len(prices) < 5:                                 # same floor the pipeline uses
            continue
        q_start_ms = _q_start_ms(qk)
        out[qk] = {"median": median(prices), "n": len(prices),
                   "union": union_from_ms is not None and q_start_ms >= union_from_ms}
    return out


def _iso_ms(date_str) -> float | None:
    try:
        return datetime.fromisoformat(str(date_str)[:10]).replace(
            tzinfo=timezone.utc).timestamp() * 1000
    except (ValueError, TypeError):
        return None


def _q_start_ms(q_key: str) -> float:
    q, y = q_key.split()
    month = (int(q[1]) - 1) * 3 + 1
    return datetime(int(y), month, 1, tzinfo=timezone.utc).timestamp() * 1000


def series_3m_at(series3: dict, q_key: str) -> tuple[float | None, bool]:
    target = _q_ordinal(q_key)
    best = None
    for qk, v in series3.items():
        o = _q_ordinal(qk)
        if o <= target and (best is None or o > best[0]):
            best = (o, v)
    if not best:
        return None, False
    return best[1]["median"], best[1]["union"]


# ------------------------------------------------------------------ per subject

def pct(a: float, b: float) -> float | None:
    """% change from a (earlier) to b (later)."""
    if not a:
        return None
    return (b - a) / a * 100.0


def estimate_as_of(db, subject_doc, pool_t, coord, timeline, t_ms):
    """Reconciled midpoint + range for subject as-of t_ms, or None."""
    median_cache = pv._build_suburb_median_cache(pool_t)
    street_cache = pv._build_street_premium_cache(pool_t, median_cache)
    with as_of(t_ms):
        vd = pv.precompute_property_valuation(
            db, subject_doc, None, pool_t, coord, timeline,
            median_cache, street_cache)
    if not vd:
        return None
    conf = vd.get("confidence") or {}
    rng = conf.get("range") or {}
    lo, hi = rng.get("low"), rng.get("high")
    point = conf.get("reconciled_valuation")
    if lo and hi:
        mid = (lo + hi) / 2
    elif point:
        mid = point
    else:
        return None
    return {"mid": mid, "low": lo, "high": hi, "point": point,
            "n_comps": len((vd.get("comparables") or [])) or conf.get("comparable_count"),
            "directional_only": (vd.get("metadata") or {}).get("directional_only", False)}


def run_subject(db, subject_doc, sub_key, all_sold, coord, timeline,
                series12, series3, now_ms):
    anchors = [(m, anchor_ms(now_ms, m)) for m in ANCHORS_MONTHS]
    ests = {}
    for m, t_ms in anchors:
        pool_t = pool_as_of(all_sold, t_ms)
        e = estimate_as_of(db, subject_doc, {sub_key: pool_t.get(sub_key, [])},
                           coord, timeline, t_ms)
        ests[m] = e
    if any(ests[m] is None for m in ANCHORS_MONTHS):
        return None

    subj_mid = {m: ests[m]["mid"] for m in ANCHORS_MONTHS}
    # subject trajectory: full 18m and each 6m segment (18->12, 12->6, 6->0)
    subj_full = pct(subj_mid[18], subj_mid[0])
    subj_seg = [pct(subj_mid[18], subj_mid[12]),
                pct(subj_mid[12], subj_mid[6]),
                pct(subj_mid[6], subj_mid[0])]

    # suburb 12m rolling median at each anchor quarter
    q = {m: quarter_key_of_ms(t) for m, t in anchors}
    med12 = {m: rolling_12m_at(series12, q[m]) for m in ANCHORS_MONTHS}
    med12_full = (pct(med12[18], med12[0])
                  if med12[18] and med12[0] else None)
    med12_seg = [pct(med12[18], med12[12]) if med12[18] and med12[12] else None,
                 pct(med12[12], med12[6]) if med12[12] and med12[6] else None,
                 pct(med12[6], med12[0]) if med12[6] and med12[0] else None]

    # suburb 3m rolling median at each anchor quarter
    m3 = {}
    m3_union = {}
    for m in ANCHORS_MONTHS:
        v, u = series_3m_at(series3, q[m])
        m3[m], m3_union[m] = v, u
    med3_full = pct(m3[18], m3[0]) if m3[18] and m3[0] else None

    return {
        "address": subject_doc.get("address"),
        "suburb": sub_key,
        "subject": {
            "mid": subj_mid,
            "range": {m: [ests[m]["low"], ests[m]["high"]] for m in ANCHORS_MONTHS},
            "n_comps": {m: ests[m]["n_comps"] for m in ANCHORS_MONTHS},
            "full_pct": subj_full,
            "seg_pct": subj_seg,
        },
        "suburb_12m": {"at": med12, "full_pct": med12_full, "seg_pct": med12_seg,
                       "quarter": q},
        "suburb_3m": {"at": m3, "full_pct": med3_full, "union_ok": m3_union},
        "compare": {
            "same_dir_full": (subj_full is not None and med12_full is not None
                              and (subj_full >= 0) == (med12_full >= 0)),
            "gap_full_pp": (abs(subj_full - med12_full)
                            if subj_full is not None and med12_full is not None else None),
            "seg_same_dir": [
                (s is not None and d is not None and (s >= 0) == (d >= 0))
                for s, d in zip(subj_seg, med12_seg)],
        },
    }


# ------------------------------------------------------------------ aggregate

def pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs2, ys2 = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = mean(xs2), mean(ys2)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = sum((x - mx) ** 2 for x in xs2) ** 0.5
    dy = sum((y - my) ** 2 for y in ys2) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def aggregate(rows):
    full_subj = [r["subject"]["full_pct"] for r in rows]
    full_med = [r["suburb_12m"]["full_pct"] for r in rows]
    same_dir = [r["compare"]["same_dir_full"] for r in rows
                if r["compare"]["same_dir_full"] is not None]
    gaps = [r["compare"]["gap_full_pp"] for r in rows
            if r["compare"]["gap_full_pp"] is not None]
    # segment-level pooled (3 segments per subject)
    seg_subj, seg_med = [], []
    for r in rows:
        seg_subj += r["subject"]["seg_pct"]
        seg_med += r["suburb_12m"]["seg_pct"]
    seg_same = [(s >= 0) == (d >= 0) for s, d in zip(seg_subj, seg_med)
                if s is not None and d is not None]
    return {
        "n_subjects": len(rows),
        "full_18m": {
            "pearson_subject_vs_med12": pearson(full_subj, full_med),
            "same_direction_rate": (sum(same_dir) / len(same_dir)) if same_dir else None,
            "median_gap_pp": median(gaps) if gaps else None,
            "mean_gap_pp": mean(gaps) if gaps else None,
            "subject_full_median_pct": median([x for x in full_subj if x is not None]) if full_subj else None,
            "med12_full_median_pct": median([x for x in full_med if x is not None]) if full_med else None,
        },
        "segment_6m": {
            "pearson_subject_vs_med12": pearson(seg_subj, seg_med),
            "same_direction_rate": (sum(seg_same) / len(seg_same)) if seg_same else None,
            "n_segments": len(seg_same),
        },
    }


# ------------------------------------------------------------------ candidates

def candidates(db, sub_key, limit):
    """In-envelope, non-listed subjects with the features the engine needs."""
    gc = db
    out = []
    # Full documents (no projection): the engine's feature resolvers read many
    # nested paths (scraped_data, property_valuation_data, cadastral fields) and a
    # projection silently starves them, producing missing_floor_area exclusions.
    cur = gc[sub_key].find(
        {"valuation_data.adjusted_comparables": {"$exists": True},
         "listing_status": {"$nin": ["for_sale", "under_contract"]}}).limit(limit * 4)
    for d in cur:
        if (d.get("valuation_data", {}).get("metadata", {}) or {}).get("directional_only"):
            continue
        d["_collection"] = sub_key
        out.append(d)
        if len(out) >= limit:
            break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suburb", choices=SUBURBS)
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "trajectory_backtest_report.json"))
    ap.add_argument("--smoke", action="store_true",
                    help="one subject, print the 4 anchor estimates, exit")
    a = ap.parse_args()

    from shared.db import get_client
    client = get_client()
    db = client["Gold_Coast"]
    now_ms = datetime.now(timezone.utc).timestamp() * 1000

    subs = [a.suburb] if a.suburb else SUBURBS
    print("Loading sold comparables (all history)...", file=sys.stderr)
    all_sold = pv._load_sold_comparables(client, only_suburbs=subs)
    print("Preloading coordinates + timelines...", file=sys.stderr)
    coord = pv._preload_gc_coordinates(client, subs)
    timeline = pv._preload_gc_timelines(client, subs)

    series12_by_sub, series3_by_sub = {}, {}
    for s in subs:
        doc = db["precomputed_indexed_prices"].find_one({"_id": s}) or {}
        series12_by_sub[s] = doc.get("rolling_12m_median_series") or []
        print(f"Reconstructing 3-month median series for {s}...", file=sys.stderr)
        series3_by_sub[s] = build_3m_series(s)

    if a.smoke:
        s = subs[0]
        cand = candidates(db, s, 8)
        for subject in cand:
            r = run_subject(db, subject, s, all_sold, coord, timeline,
                            series12_by_sub[s], series3_by_sub[s], now_ms)
            if r:
                print(json.dumps(r, indent=2, default=str))
                return 0
        print("no smoke subject produced 4 estimates", file=sys.stderr)
        return 1

    rows = []
    for s in subs:
        cand = candidates(db, s, a.limit)
        print(f"{s}: {len(cand)} candidate subjects", file=sys.stderr)
        for i, subject in enumerate(cand):
            r = run_subject(db, subject, s, all_sold, coord, timeline,
                            series12_by_sub[s], series3_by_sub[s], now_ms)
            tag = "ok" if r else "skip(incomplete anchors)"
            print(f"  [{s} {i+1}/{len(cand)}] {subject.get('address')}: {tag}",
                  file=sys.stderr)
            if r:
                rows.append(r)

    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "anchors_months_ago": ANCHORS_MONTHS,
              "method": "real engine precompute_property_valuation run as-of each "
                        "anchor via time/datetime monkeypatch + <=T sold-pool filter",
              "aggregate": aggregate(rows) if rows else None,
              "subjects": rows}
    with open(a.out, "w") as fh:
        json.dump(report, fh, indent=2, default=str)

    agg = report["aggregate"]
    print("\n" + "=" * 64, file=sys.stderr)
    if agg:
        f = agg["full_18m"]
        g = agg["segment_6m"]
        print(f"subjects with 4 complete anchors: {agg['n_subjects']}", file=sys.stderr)
        print(f"[18m full move] pearson(subject, suburb-12m median) = "
              f"{_fmt(f['pearson_subject_vs_med12'])}", file=sys.stderr)
        print(f"[18m full move] same-direction rate = {_fmtpct(f['same_direction_rate'])}",
              file=sys.stderr)
        print(f"[18m full move] median |gap| = {_fmt(f['median_gap_pp'])} pp   "
              f"(subject median move {_fmt(f['subject_full_median_pct'])}%, "
              f"suburb {_fmt(f['med12_full_median_pct'])}%)", file=sys.stderr)
        print(f"[6m segments ] pearson = {_fmt(g['pearson_subject_vs_med12'])}, "
              f"same-direction = {_fmtpct(g['same_direction_rate'])} "
              f"(n={g['n_segments']})", file=sys.stderr)
    else:
        print("no subjects produced 4 complete anchors", file=sys.stderr)
    print(f"\nreport -> {a.out}", file=sys.stderr)
    return 0


def _fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def _fmtpct(x):
    return "n/a" if x is None else f"{x*100:.0f}%"


if __name__ == "__main__":
    sys.exit(main())
