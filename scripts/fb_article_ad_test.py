#!/usr/bin/env python3
"""
fb_article_ad_test.py — reusable Facebook test harness for ARTICLES.

Why this exists
---------------
There are 14 one-off builders under
``03_Facebook/Home_Owner_Lead_Funnel_Search/build_cycle*_ads.py``. They are the working
reference for the Graph API shapes (campaign -> adset -> adcreative -> ad, image upload),
and this file deliberately reuses those shapes. What it does NOT reuse:

  * their targeting is the INVERSE of what is wanted here — Brisbane + Sunshine Coast
    with the Gold Coast explicitly EXCLUDED (that was out-of-market copy discovery);
  * they run ``DAILY = 1500`` = A$15/day with no cumulative ceiling at all.

This tool targets the middle-to-southern Gold Coast ONLY (Will, 2026-08-13) and refuses
to let a calendar week exceed A$20 total.

The three things it will not do
-------------------------------
1. **Target outside the Gold Coast.** Geo is a hard-coded, verified list of nine suburb
   centroids. Every centroid, and every centroid+radius edge, is asserted inside a Gold
   Coast fence at import time. There is no CLI flag that adds a location.

2. **Spend more than A$20 in an AEST calendar week.** Facebook's own budget caps are
   advisory — Meta will spend up to ~25% over a daily budget on any given day — so the
   ceiling here is computed by us, from our own recorded spend, before anything is
   created or unpaused. Unmeasured days are charged at the worst case, not at zero.

3. **Create an ad without a kill rule, or with a kill rule that keys on CTR.**
   A corpus built 2026-08-13 graded 47 lead ads: **21 of them delivered at or above
   median CTR and produced ZERO qualified sellers, on $431.54.** The three highest-CTR
   ads in the whole set (10.87%, 10.41%, 10.00%) produced nothing at all. A CTR-based
   kill rule would not have stopped one dollar of that; it would have *protected* the
   worst spenders. So kill rules here may only key on **spend** and **qualified leads**.
   Engagement metrics are rejected by name.

Usage
-----
    python3 scripts/fb_article_ad_test.py --status
    python3 scripts/fb_article_ad_test.py --article <slug> --kill-spend 8      # dry-run
    python3 scripts/fb_article_ad_test.py --article <slug> --kill-spend 8 --live
    python3 scripts/fb_article_ad_test.py --kill <ad_id> --reason "..."

``--dry-run`` is the default. ``--live`` is the only thing that touches the Graph API,
and it re-runs the budget and kill-rule gates immediately before it does.

⚠ OPEN GAP — the kill rule is EVALUATED, not ENFORCED
-----------------------------------------------------
``--status`` computes each ad's verdict and prints the exact ``--kill`` command when one
fires, but nothing runs ``--status`` on a schedule, so today a kill rule only fires when
a human looks. That is a Rule 7 self-monitoring gap and it is deliberate: this task was
not permitted to touch crontab. Before any ad here is unpaused, add something like

    */30 * * * * cd /home/fields/Fields_Orchestrator && set -a && . .env && set +a && \\
      /home/fields/venv/bin/python3 scripts/fb_article_ad_test.py --status

wrapped in ``job_run("fb_article_ad_test_watch", cadence_hours=1, ...)`` per Rule 7, with
the zero-output assertion of Rule 7b (raise if the registry has ACTIVE ads but the spend
read returned nothing — that means the collector died, not that the ads are free).
Until then the A$20 ceiling is enforced at CREATE time only, and the adset ``end_time``
is what stops delivery running past the week.

Env:  set -a && source .env && set +a ; source /home/fields/venv/bin/activate
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import textwrap
from datetime import datetime, date, time, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

# ──────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────

ACT = "act_1463563608441065"
PAGE = "889412530933297"
API = "https://graph.facebook.com/v21.0"

SITE = "https://fieldsestate.com.au"
ARTICLE_PATH = "/articles/{slug}"        # canonical; /article/:id 301-redirects here
                                         # (src/App.tsx + src/routes.ts, verified)

AEST = timezone(timedelta(hours=10))     # Queensland — no DST, ever

# The tag. Everything this tool creates carries it in the campaign, adset and ad name,
# and is written to system_monitor.article_ad_tests. Spend accounting unions both, so a
# manual rename in Ads Manager cannot orphan an ad from its own budget ceiling.
TAG = "FAT"
REGISTRY = "article_ad_tests"
CAMPAIGN_NAME = f"{TAG} | Article Test | Southern Gold Coast"

WEEKLY_CAP_AUD = 20.00
# Meta will deliver up to ~25% over a daily budget on any single day, balancing across
# the week. "Balanced across the week" is exactly the guarantee we cannot rely on when
# the whole week's ceiling is $20, so every projection is inflated by this factor.
OVERSPEND_FACTOR = 1.25
MIN_DAILY_AUD = 1.00                     # Meta's floor for impression-billed delivery
# When --daily is not given, spend at most this share of the remaining headroom. The
# largest daily that "fits" would hand the entire week to whichever article was tested
# first, which is a bad default for a test harness whose point is comparison. The hard
# maximum is still computed and shown; --daily overrides.
AUTO_HEADROOM_SHARE = 0.5

# ──────────────────────────────────────────────────────────────────────────
# Geo — middle-to-southern Gold Coast only
# ──────────────────────────────────────────────────────────────────────────
# NOT from memory. Each centroid is the mean of every geocoded cadastral parcel in that
# suburb's Gold_Coast collection (field `LATITUDE`/`LONGITUDE`, confirmed via
# `db_fields.py --find latitude` per Rule 8 — the lowercase `latitude` most people would
# guess is a *nested* path with single-digit fill). n and the p99 parcel distance from
# the centroid are recorded below so the radius is defensible rather than eyeballed:
# radius_km is p99 rounded up, i.e. it covers ~99% of the suburb's real parcels and
# little else. Computed 2026-08-13 over 66,072 parcels total.
#
#   suburb            n       centroid                p95      p99      max
#   robina            11,760  -28.0719, 153.3948      2.49km   2.88km   3.17km
#   varsity_lakes      7,635  -28.0868, 153.4115      1.39km   1.63km   1.84km
#   burleigh_waters    6,885  -28.0863, 153.4315      1.74km   2.13km   2.22km
#   mermaid_waters     6,169  -28.0489, 153.4228      1.73km   1.83km   2.19km
#   miami              4,783  -28.0696, 153.4397      1.13km   1.43km   8.79km
#   burleigh_heads     9,433  -28.0958, 153.4419      3.13km   3.45km   3.90km
#   palm_beach        10,706  -28.1149, 153.4659      1.79km   2.02km   2.73km
#   mudgeeraba         5,921  -28.0884, 153.3638      3.08km   4.64km   6.40km
#   reedy_creek        2,780  -28.1104, 153.3969      1.56km   1.77km   1.88km
#
# Note Miami's max of 8.79km against a p99 of 1.43km — a handful of parcels filed under
# Miami sit far outside it. Radius follows p99, not max, deliberately: chasing the tail
# would push the circle into suburbs Will did not ask for.

SUBURB_GEO = [
    # (label,             lat,       lon,        radius_km, n_parcels, p99_km)
    ("Robina",          -28.0719, 153.3948, 3, 11760, 2.88),
    ("Varsity Lakes",   -28.0868, 153.4115, 2,  7635, 1.63),
    ("Burleigh Waters", -28.0863, 153.4315, 3,  6885, 2.13),
    ("Mermaid Waters",  -28.0489, 153.4228, 2,  6169, 1.83),
    ("Miami",           -28.0696, 153.4397, 2,  4783, 1.43),
    ("Burleigh Heads",  -28.0958, 153.4419, 4,  9433, 3.45),
    ("Palm Beach",      -28.1149, 153.4659, 3, 10706, 2.02),
    ("Mudgeeraba",      -28.0884, 153.3638, 5,  5921, 4.64),
    ("Reedy Creek",     -28.1104, 153.3969, 2,  2780, 1.77),
]

# Hard fence. Not the suburb bounds — the outer limit of the Gold Coast area we are
# permitted to touch at all. Brisbane CBD is -27.4705 / 153.0260, about 68km north of
# the northernmost point below, so a fence breach is loud rather than subtle.
GC_FENCE = {"lat_min": -28.25, "lat_max": -27.90, "lon_min": 153.25, "lon_max": 153.55}


def _fence_check() -> None:
    """Assert every circle — centre AND edge — is inside the Gold Coast fence.

    Runs at import. If a future edit fat-fingers a coordinate or inflates a radius, the
    tool refuses to load rather than quietly buying impressions in Brisbane.
    """
    for label, lat, lon, radius_km, _n, _p99 in SUBURB_GEO:
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
        edges = {
            "north": (lat + dlat, lon), "south": (lat - dlat, lon),
            "east": (lat, lon + dlon), "west": (lat, lon - dlon),
        }
        for name, (elat, elon) in {"centre": (lat, lon), **edges}.items():
            if not (GC_FENCE["lat_min"] <= elat <= GC_FENCE["lat_max"]
                    and GC_FENCE["lon_min"] <= elon <= GC_FENCE["lon_max"]):
                raise SystemExit(
                    f"GEO FENCE BREACH: {label} {name} ({elat:.4f}, {elon:.4f}) "
                    f"is outside the Gold Coast fence {GC_FENCE}. Refusing to load."
                )


_fence_check()


def build_targeting() -> dict:
    """The targeting block, assembled only from the fenced list above."""
    return {
        "geo_locations": {
            "custom_locations": [
                {"latitude": lat, "longitude": lon,
                 "radius": radius_km, "distance_unit": "kilometer"}
                for _label, lat, lon, radius_km, _n, _p99 in SUBURB_GEO
            ],
            "location_types": ["home", "recent"],
        },
        "publisher_platforms": ["facebook", "instagram"],
        "targeting_automation": {"advantage_audience": 0},
    }


def geo_summary() -> str:
    lines = [f"  {'suburb':<16} {'lat':>9} {'lon':>10} {'radius':>7}   "
             f"{'parcels':>7} {'p99':>6}   covers"]
    for label, lat, lon, r, n, p99 in SUBURB_GEO:
        lines.append(f"  {label:<16} {lat:>9.4f} {lon:>10.4f} {str(r) + ' km':>7}   "
                     f"{n:>7,} {p99:>5.2f}km   {'OK' if r >= p99 else 'UNDER p99'}")
    lats = [lat for _l, lat, _o, _r, _n, _p in SUBURB_GEO]
    lons = [lon for _l, _a, lon, _r, _n, _p in SUBURB_GEO]
    lines.append(f"\n  envelope: lat {min(lats):.4f}..{max(lats):.4f}  "
                 f"lon {min(lons):.4f}..{max(lons):.4f}")
    lines.append(f"  fence:    lat {GC_FENCE['lat_min']}..{GC_FENCE['lat_max']}  "
                 f"lon {GC_FENCE['lon_min']}..{GC_FENCE['lon_max']}  [all circles inside]")
    lines.append("  Brisbane CBD (-27.4705, 153.0260) is ~68 km north of the "
                 "northernmost circle — not reachable by any radius above.")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────
# Kill rules
# ──────────────────────────────────────────────────────────────────────────

# Rejected by name. Each of these is an engagement proxy, and the 2026-08-13 corpus is
# the evidence that engagement proxies do not predict a qualified seller: 21 of 47
# graded ads cleared median CTR and returned zero, on $431.54.
BANNED_KILL_METRICS = {
    "ctr", "click_through_rate", "clicks", "link_clicks", "impressions", "reach",
    "cpm", "cpc", "frequency", "engagement", "engagement_rate", "post_engagement",
    "page_engagement", "likes", "like", "reactions", "post_reaction", "comments",
    "comment", "shares", "post_save", "saves", "video_views", "landing_page_views",
    "cost_per_link_click", "sessions", "unique_visitors", "bounce_rate", "scroll_depth",
}

ALLOWED_KILL_KEYS = {
    "metric", "max_spend_aud", "min_qualified_leads", "hard_max_spend_aud", "note",
}


def validate_kill_rule(rule) -> list[str]:
    """Return a list of reasons the kill rule is unacceptable. Empty list = acceptable."""
    problems: list[str] = []
    if not rule:
        return ["no kill rule supplied — every ad this tool creates must carry one "
                "(--kill-spend N, or --kill-rule '<json>')"]
    if not isinstance(rule, dict):
        return [f"kill rule must be a JSON object, got {type(rule).__name__}"]

    unknown = set(rule) - ALLOWED_KILL_KEYS
    if unknown:
        problems.append(f"unknown kill-rule key(s): {sorted(unknown)}; "
                        f"allowed: {sorted(ALLOWED_KILL_KEYS)}")

    metric = str(rule.get("metric", "")).lower()
    if metric != "spend_without_qualified_lead":
        problems.append(
            f'kill rule metric must be "spend_without_qualified_lead", got "{metric}"')

    # Belt and braces: reject an engagement metric appearing anywhere in the rule, not
    # just in `metric`. A rule smuggling "min_ctr" through `note` is still a CTR rule.
    blob = json.dumps(rule).lower()
    hit = sorted({m for m in BANNED_KILL_METRICS
                  if re.search(r"(?<![a-z_])" + re.escape(m) + r"(?![a-z_])", blob)})
    if hit:
        problems.append(
            f"kill rule references engagement metric(s) {hit} — FORBIDDEN. "
            "Kill rules may key on spend and qualified leads only. On 2026-08-13, 21 of "
            "47 graded lead ads delivered at or above median CTR and produced ZERO "
            "qualified sellers on $431.54; the top three by CTR (10.87%, 10.41%, "
            "10.00%) produced nothing. A CTR rule automates that failure.")

    spend = rule.get("max_spend_aud")
    if not isinstance(spend, (int, float)) or not (0 < spend <= WEEKLY_CAP_AUD):
        problems.append(f"max_spend_aud must be a number in (0, {WEEKLY_CAP_AUD:.2f}], "
                        f"got {spend!r}")

    leads = rule.get("min_qualified_leads", 1)
    if not isinstance(leads, int) or leads < 1:
        problems.append(f"min_qualified_leads must be an integer >= 1, got {leads!r}")

    hard = rule.get("hard_max_spend_aud")
    if hard is not None:
        if not isinstance(hard, (int, float)) or not (0 < hard <= WEEKLY_CAP_AUD):
            problems.append(f"hard_max_spend_aud must be in (0, {WEEKLY_CAP_AUD:.2f}], "
                            f"got {hard!r}")
        elif isinstance(spend, (int, float)) and hard < spend:
            problems.append("hard_max_spend_aud must be >= max_spend_aud")

    return problems


def describe_kill_rule(rule: dict) -> str:
    parts = [f"kill when spend >= A${rule['max_spend_aud']:.2f} and qualified leads < "
             f"{rule.get('min_qualified_leads', 1)}"]
    if rule.get("hard_max_spend_aud"):
        parts.append(f"kill unconditionally at A${rule['hard_max_spend_aud']:.2f}")
    return "; ".join(parts)


# ──────────────────────────────────────────────────────────────────────────
# Week arithmetic (AEST)
# ──────────────────────────────────────────────────────────────────────────

def aest_now() -> datetime:
    return datetime.now(AEST)


def week_window(now: datetime | None = None) -> tuple[date, date, int]:
    """(monday, sunday, days_remaining_inclusive_of_today) for the AEST calendar week."""
    now = now or aest_now()
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday, (sunday - today).days + 1


def week_end_dt(now: datetime | None = None) -> datetime:
    _mon, sunday, _rem = week_window(now)
    return datetime.combine(sunday, time(23, 59, 0), tzinfo=AEST)


# ──────────────────────────────────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────────────────────────────────

def get_db():
    from shared.db import get_client
    return get_client()["system_monitor"]


def tagged_ads(db) -> dict[str, dict]:
    """Every ad this tool is responsible for, keyed by ad_id.

    Union of two independent sources so neither can silently under-report spend:
      * the registry we write at creation time (authoritative for daily_budget); and
      * ad_profiles whose ad/adset/campaign name carries the tag (catches anything
        created by an older run of this tool, or restored from Ads Manager).
    """
    ads: dict[str, dict] = {}

    for doc in db[REGISTRY].find({}):
        ads[str(doc["ad_id"])] = {
            "ad_id": str(doc["ad_id"]),
            "ad_name": doc.get("ad_name"),
            "article_slug": doc.get("article_slug"),
            "daily_budget_aud": doc.get("daily_budget_aud"),
            "created_at": doc.get("created_at"),
            "status": doc.get("status"),
            "kill_rule": doc.get("kill_rule"),
            "source": "registry",
        }

    rx = re.compile(r"(?<![A-Za-z])" + re.escape(TAG) + r"(?![A-Za-z])")
    for doc in db["ad_profiles"].find(
            {}, {"ad_id": 1, "name": 1, "adset_name": 1, "campaign_name": 1,
                 "created_time": 1, "effective_status": 1, "lifetime": 1}):
        names = " ".join(str(doc.get(k) or "")
                         for k in ("name", "adset_name", "campaign_name"))
        if not rx.search(names):
            continue
        aid = str(doc.get("ad_id") or doc.get("_id"))
        entry = ads.setdefault(aid, {"ad_id": aid, "source": "ad_profiles"})
        entry.setdefault("ad_name", doc.get("name"))
        entry.setdefault("daily_budget_aud", None)
        entry.setdefault("kill_rule", None)
        entry["effective_status"] = doc.get("effective_status")
        entry["fb_created_time"] = doc.get("created_time")

    # Attach the profile lifetime + effective status to registry-sourced entries too.
    if ads:
        for doc in db["ad_profiles"].find(
                {"ad_id": {"$in": list(ads)}},
                {"ad_id": 1, "lifetime": 1, "effective_status": 1, "created_time": 1}):
            e = ads.get(str(doc["ad_id"]))
            if e is not None:
                e["lifetime_spend_aud"] = float(
                    (doc.get("lifetime") or {}).get("spend_aud") or 0.0)
                e["effective_status"] = doc.get("effective_status")
                e["fb_created_time"] = doc.get("created_time")
    return ads


# Facebook returns created_time as "2026-07-30T12:09:48+1000" — a bare four-digit
# offset. Python 3.10's fromisoformat (this VM runs 3.10.12) rejects that and only
# accepts "+10:00". Left unhandled, every ad parses as unknown, `lifetime_applies` goes
# False for all of them, and the lifetime cross-check that exists to catch a lagging
# metrics collector silently never fires. Caught 2026-08-13 by a simulated week.
_TZ_COMPACT = re.compile(r"([+-]\d{2})(\d{2})$")


def _parse_dt(raw) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    s = _TZ_COMPACT.sub(r"\1:\2", s)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _created_date(entry: dict) -> date | None:
    """AEST creation date, or None if genuinely unknown.

    Callers must treat None as "assume created this week" — the branch that makes
    lifetime spend count, i.e. the higher estimate. An unparseable date must never be
    the reason a ceiling is under-counted.
    """
    dt = _parse_dt(entry.get("fb_created_time") or entry.get("created_at"))
    return dt.astimezone(AEST).date() if dt else None


def week_spend(db, now: datetime | None = None) -> dict:
    """Week-to-date spend for tagged ads. Deliberately pessimistic.

    Per ad, three numbers are reconciled:

      measured   sum of ad_daily_metrics.spend_aud for dates inside the week;
      lifetime   ad_profiles.lifetime.spend_aud — used only when the ad was CREATED
                 inside this week, where lifetime spend and week spend are the same
                 thing, and it catches days the metrics collector has not written yet;
      assumed    any day the ad was live but has NO ad_daily_metrics row is charged at
                 daily_budget x OVERSPEND_FACTOR, i.e. the most Meta could have taken.

    A missing metrics row means we do not know, and "we do not know" must cost us the
    full amount rather than nothing. The collector runs twice a day, so today's row is
    normally absent for part of the day; charging it at zero is how a $20 ceiling
    quietly becomes a $35 one.
    """
    now = now or aest_now()
    monday, sunday, _rem = week_window(now)
    today = now.date()
    week_dates = [monday + timedelta(days=i) for i in range((today - monday).days + 1)]
    week_strs = [d.isoformat() for d in week_dates]

    ads = tagged_ads(db)
    if not ads:
        return {"week_start": monday, "week_end": sunday, "today": today,
                "ads": {}, "total_aud": 0.0, "measured_aud": 0.0, "assumed_aud": 0.0}

    rows: dict[str, dict[str, float]] = {}
    for doc in db["ad_daily_metrics"].find(
            {"ad_id": {"$in": list(ads)}, "date": {"$in": week_strs}},
            {"ad_id": 1, "date": 1, "spend_aud": 1}):
        rows.setdefault(str(doc["ad_id"]), {})[doc["date"]] = float(doc.get("spend_aud") or 0)

    detail: dict[str, dict] = {}
    for aid, entry in ads.items():
        days = rows.get(aid, {})
        measured = round(sum(days.values()), 2)

        created = _created_date(entry)
        lifetime = float(entry.get("lifetime_spend_aud") or 0.0)
        # None = unknown creation date. Treat as created-this-week so lifetime counts:
        # the conservative branch. Never let an unparseable timestamp lower the estimate.
        lifetime_applies = created is None or created >= monday
        base = max(measured, lifetime) if lifetime_applies else measured

        # Days the ad could have been delivering but for which we have no row.
        live = str(entry.get("effective_status") or entry.get("status") or "").upper()
        is_live = live in {"ACTIVE", "PENDING_REVIEW", "IN_PROCESS", "CAMPAIGN_PAUSED"} \
            or live == "" and entry.get("status") == "ACTIVE"
        daily = entry.get("daily_budget_aud")
        assumed = 0.0
        missing: list[str] = []
        if is_live and daily:
            start = max(created, monday) if created else monday
            for d in week_dates:
                if d < start:
                    continue
                if d.isoformat() not in days:
                    missing.append(d.isoformat())
            assumed = round(len(missing) * float(daily) * OVERSPEND_FACTOR, 2)

        detail[aid] = {
            "ad_name": entry.get("ad_name"),
            "article_slug": entry.get("article_slug"),
            "effective_status": entry.get("effective_status") or entry.get("status"),
            "daily_budget_aud": daily,
            "measured_aud": measured,
            "lifetime_aud": lifetime,
            "lifetime_applies": lifetime_applies,
            "unmeasured_days": missing,
            "assumed_aud": assumed,
            "week_aud": round(base + assumed, 2),
            "kill_rule": entry.get("kill_rule"),
        }

    return {
        "week_start": monday, "week_end": sunday, "today": today,
        "ads": detail,
        "measured_aud": round(sum(d["measured_aud"] for d in detail.values()), 2),
        "assumed_aud": round(sum(d["assumed_aud"] for d in detail.values()), 2),
        "total_aud": round(sum(d["week_aud"] for d in detail.values()), 2),
    }


def budget_gate(db, daily_aud: float | None, now: datetime | None = None) -> dict:
    """Can we afford `daily_aud`/day for the rest of this AEST week?

    Returns a dict with `ok`, full arithmetic, and (when daily_aud is None) the largest
    daily budget that fits. Every term is retained so the refusal can show its working.
    """
    now = now or aest_now()
    monday, sunday, days_remaining = week_window(now)
    spend = week_spend(db, now)

    # Already-running tagged ads keep costing money for the rest of the week. That
    # commitment is spent as far as this gate is concerned.
    committed = 0.0
    committed_lines = []
    for aid, d in spend["ads"].items():
        live = str(d.get("effective_status") or "").upper()
        if live not in {"ACTIVE", "PENDING_REVIEW", "IN_PROCESS"}:
            continue
        daily = float(d.get("daily_budget_aud") or 0)
        # An ad with no recorded daily budget is the dangerous case, not the free one.
        if not daily:
            daily = WEEKLY_CAP_AUD / 7.0
            note = " (no recorded budget — charged at cap/7)"
        else:
            note = ""
        # Today is already counted in `assumed` where its row is missing; count the
        # remaining days only, so we do not double-charge today.
        fwd_days = max(days_remaining - 1, 0)
        amt = round(daily * fwd_days * OVERSPEND_FACTOR, 2)
        committed += amt
        committed_lines.append(
            f"{aid} {daily:.2f}/day x {fwd_days}d x {OVERSPEND_FACTOR} = "
            f"{amt:.2f}{note}")
    committed = round(committed, 2)

    headroom = round(WEEKLY_CAP_AUD - spend["total_aud"] - committed, 2)
    max_daily = math.floor(
        max(headroom, 0) / (days_remaining * OVERSPEND_FACTOR) * 100) / 100 \
        if days_remaining else 0.0

    auto_daily = math.floor(
        max(headroom, 0) * AUTO_HEADROOM_SHARE / (days_remaining * OVERSPEND_FACTOR) * 100
    ) / 100 if days_remaining else 0.0
    # If half the headroom cannot clear Meta's minimum but the full headroom can, use the
    # full headroom rather than refusing — one test at the floor beats no test at all.
    if auto_daily < MIN_DAILY_AUD <= max_daily:
        auto_daily = max_daily

    if daily_aud is None:
        daily_aud = auto_daily
        auto = True
    else:
        auto = False

    new_worst = round(daily_aud * days_remaining * OVERSPEND_FACTOR, 2)
    projected = round(spend["total_aud"] + committed + new_worst, 2)

    reasons = []
    if spend["total_aud"] >= WEEKLY_CAP_AUD:
        reasons.append(
            f"week-to-date spend A${spend['total_aud']:.2f} already meets or exceeds "
            f"the A${WEEKLY_CAP_AUD:.2f} weekly cap")
    if projected > WEEKLY_CAP_AUD:
        reasons.append(
            f"projected week total A${projected:.2f} exceeds the A${WEEKLY_CAP_AUD:.2f} cap")
    if daily_aud < MIN_DAILY_AUD:
        reasons.append(
            f"affordable daily budget A${daily_aud:.2f} is below Meta's A${MIN_DAILY_AUD:.2f} "
            f"minimum — there is not enough room left in the week to run anything")

    return {
        "ok": not reasons, "reasons": reasons, "auto_daily": auto,
        "week_start": monday, "week_end": sunday, "today": spend["today"],
        "days_remaining": days_remaining,
        "spend": spend, "committed_aud": committed, "committed_lines": committed_lines,
        "headroom_aud": headroom, "max_daily_aud": max_daily, "auto_daily_aud": auto_daily,
        "daily_aud": round(daily_aud, 2), "new_worst_case_aud": new_worst,
        "projected_total_aud": projected, "cap_aud": WEEKLY_CAP_AUD,
    }


def render_budget_arithmetic(g: dict) -> str:
    s = g["spend"]
    out = [
        f"  AEST week          {g['week_start']} (Mon) .. {g['week_end']} (Sun); "
        f"today {g['today']}, {g['days_remaining']} day(s) remaining incl. today",
        f"  weekly cap         A${g['cap_aud']:.2f}",
        "",
        f"  week-to-date spend, ads tagged '{TAG}' ({len(s['ads'])} ad(s)):",
    ]
    if not s["ads"]:
        out.append("    (none — this tool has never created an ad, so A$0.00 is measured, "
                   "not assumed)")
    for aid, d in s["ads"].items():
        out.append(f"    {aid} {d.get('ad_name') or ''} [{d.get('effective_status')}]")
        out.append(f"      measured (ad_daily_metrics)  A${d['measured_aud']:.2f}")
        out.append(f"      lifetime (ad_profiles)       A${d['lifetime_aud']:.2f}"
                   f"{'  <- applies (created this week)' if d['lifetime_applies'] else '  (pre-dates this week; not used)'}")
        if d["lifetime_applies"] and d["lifetime_aud"] > d["measured_aud"]:
            out.append(f"      lifetime EXCEEDS measured by "
                       f"A${d['lifetime_aud'] - d['measured_aud']:.2f} — metrics "
                       f"collector is behind; lifetime is used")
        if d["unmeasured_days"]:
            out.append(f"      unmeasured days {d['unmeasured_days']} charged at "
                       f"{d['daily_budget_aud']} x {OVERSPEND_FACTOR} = A${d['assumed_aud']:.2f}")
        out.append(f"      => week            A${d['week_aud']:.2f}")
    out += [
        f"    measured total               A${s['measured_aud']:.2f}",
        f"    assumed (unmeasured days)    A${s['assumed_aud']:.2f}",
        f"    ------------------------------------------",
        f"    week-to-date (A)             A${s['total_aud']:.2f}",
        "",
        f"  forward commitment of ads already running (B):  A${g['committed_aud']:.2f}",
    ]
    for line in g["committed_lines"]:
        out.append(f"    {line}")
    if not g["committed_lines"]:
        out.append("    (no tagged ad is currently delivering)")
    out += [
        "",
        f"  headroom = cap - A - B = {g['cap_aud']:.2f} - {s['total_aud']:.2f} - "
        f"{g['committed_aud']:.2f} = A${g['headroom_aud']:.2f}",
        f"  largest daily that fits = headroom / (days_remaining x {OVERSPEND_FACTOR}) "
        f"= {g['headroom_aud']:.2f} / ({g['days_remaining']} x {OVERSPEND_FACTOR}) "
        f"= A${g['max_daily_aud']:.2f}/day   [hard maximum]",
        f"  default daily = {int(AUTO_HEADROOM_SHARE * 100)}% of headroom "
        f"= A${g['auto_daily_aud']:.2f}/day   [leaves room for a 2nd test this week]",
        "",
        f"  proposed daily (C)   A${g['daily_aud']:.2f}/day"
        f"{'  [auto-sized]' if g['auto_daily'] else '  [--daily]'}",
        f"  worst case for it    {g['daily_aud']:.2f} x {g['days_remaining']}d x "
        f"{OVERSPEND_FACTOR} = A${g['new_worst_case_aud']:.2f}",
        f"  PROJECTED WEEK TOTAL A + B + C = {s['total_aud']:.2f} + "
        f"{g['committed_aud']:.2f} + {g['new_worst_case_aud']:.2f} "
        f"= A${g['projected_total_aud']:.2f}  vs cap A${g['cap_aud']:.2f}",
        f"  -> {'PASS' if g['ok'] else 'REFUSE'}",
    ]
    for r in g["reasons"]:
        out.append(f"     * {r}")
    return "\n".join(out)


# ──────────────────────────────────────────────────────────────────────────
# Qualified leads
# ──────────────────────────────────────────────────────────────────────────

def qualified_leads(db, ad_id: str) -> dict:
    """Qualified outcomes for an ad. Never clicks, never engagement.

    Two independent substrates:
      * `fb_leads`     — an instant-form submission attributed to this ad_id;
      * `ad_downstream.converters` — a visitor from this ad who fired a site conversion
        event (address submit, analyse-home submit, off-market qualify, ...).

    `ad_downstream` is recomputed periodically and can lag. Lag makes the count LOWER,
    which makes a kill MORE likely — the safe direction. A kill rule must never be
    prevented from firing by a stale read.
    """
    form_leads = db["fb_leads"].count_documents({"ad_id": str(ad_id)})
    down = db["ad_downstream"].find_one(
        {"ad_id": str(ad_id)}, {"converters": 1, "conversion_events": 1, "computed_at": 1}) or {}
    converters = int(down.get("converters") or 0)
    return {
        "form_leads": form_leads,
        "site_converters": converters,
        "conversion_events": down.get("conversion_events") or {},
        "downstream_computed_at": down.get("computed_at"),
        "total": form_leads + converters,
    }


def evaluate_kill(db, ad_id: str, rule: dict, week_aud: float) -> dict:
    q = qualified_leads(db, ad_id)
    reasons = []
    if rule.get("hard_max_spend_aud") and week_aud >= rule["hard_max_spend_aud"]:
        reasons.append(f"spend A${week_aud:.2f} >= hard_max_spend_aud "
                       f"A${rule['hard_max_spend_aud']:.2f}")
    need = rule.get("min_qualified_leads", 1)
    if week_aud >= rule["max_spend_aud"] and q["total"] < need:
        reasons.append(f"spend A${week_aud:.2f} >= A${rule['max_spend_aud']:.2f} with "
                       f"{q['total']} qualified lead(s) < {need} required")
    return {"should_kill": bool(reasons), "reasons": reasons, "qualified": q}


# ──────────────────────────────────────────────────────────────────────────
# Editorial gate (Rule 5)
# ──────────────────────────────────────────────────────────────────────────

# Rule 5: "No single valuation in headlines: Use comparable ranges, not single figures."
# editorial_gate.check_text does not cover this — it is an ad/headline-specific rule —
# so it is enforced here on the headline only, alongside the shared gate.
RANGE_HINT = re.compile(
    r"(\$[\d,]+\s*(?:-|–|—|to)\s*\$?[\d,]+)|(\brange\b)|(\bbetween\b)|(\bgap\b)|(\bmore than\b)|(\bover\b)|(\bunder\b)",
    re.IGNORECASE)
DOLLAR_FIG = re.compile(r"\$\s?[\d,]{4,}")


def headline_valuation_breach(headline: str) -> list[str]:
    figs = DOLLAR_FIG.findall(headline or "")
    if len(figs) == 1 and not RANGE_HINT.search(headline):
        return [f'no-valuation-in-headline: single figure "{figs[0].strip()}" in the '
                f'headline with no range/gap framing — Rule 5 requires comparable '
                f'ranges, not a single figure']
    return []


def editorial_check(headline: str, message: str, description: str) -> list[str]:
    from editorial_gate import check_text
    breaches: list[str] = []
    for label, text in (("headline", headline), ("primary text", message),
                        ("description", description)):
        for b in check_text(text or ""):
            breaches.append(f"[{label}] {b}")
    breaches += [f"[headline] {b}" for b in headline_valuation_breach(headline)]
    return breaches


# ──────────────────────────────────────────────────────────────────────────
# Article
# ──────────────────────────────────────────────────────────────────────────

def load_article(db, slug: str) -> dict:
    doc = db["content_articles"].find_one(
        {"$or": [{"slug": slug}, {"_id": slug}, {"ghost_id": slug}]})
    if not doc:
        raise Refusal(f"no article found with slug/id '{slug}' in "
                      f"system_monitor.content_articles")
    if doc.get("status") != "published":
        raise Refusal(
            f"article '{slug}' has status '{doc.get('status')}', not 'published'. "
            f"Refusing to buy traffic to a page that is not live — the ad would send "
            f"paid clicks to a 404 or a draft.")
    return doc


def compose_copy(doc: dict, headline: str | None, message: str | None,
                 description: str | None) -> dict:
    slug = doc.get("slug") or str(doc["_id"])
    url = SITE + ARTICLE_PATH.format(slug=slug)
    url += ("?utm_source=facebook&utm_medium=paid&utm_campaign=article_test"
            f"&utm_content={slug}")
    excerpt = (doc.get("custom_excerpt") or "").strip()
    return {
        "slug": slug,
        "url": url,
        "headline": (headline or doc.get("title") or "").strip(),
        "message": (message or excerpt or doc.get("title") or "").strip(),
        "description": (description or "Fields analysis. Data only, no pitch.").strip(),
        "feature_image": doc.get("feature_image"),
        "published_at": doc.get("published_at"),
    }


# ──────────────────────────────────────────────────────────────────────────
# Payload construction
# ──────────────────────────────────────────────────────────────────────────

class Refusal(Exception):
    pass


def build_payloads(copy: dict, daily_aud: float, end_dt: datetime,
                   image_hash: str | None) -> dict:
    cents = int(round(daily_aud * 100))
    slug = copy["slug"]
    # Names carry the TAG because spend accounting matches on it. Keep enough of the slug
    # that two article tests cannot collide — truncating to 60 would have merged several
    # of the "sold-for-..." slugs, which share a long prefix.
    name = f"{TAG} | {slug[:150]}"

    campaign = {
        "name": CAMPAIGN_NAME,
        "objective": "OUTCOME_TRAFFIC",
        # Deliberately NOT special_ad_categories:["HOUSING"]. These are editorial market
        # analyses, not housing offers; and where the category IS enforced it forces a
        # minimum radius (15 miles in the US) that would push these circles far outside
        # the Gold Coast. The absolute constraint here is geo, so the category stays off
        # and `verify_geo_readback` re-reads the adset after creation to prove the radii
        # were not expanded by Meta.
        "special_ad_categories": [],
        "is_adset_budget_sharing_enabled": False,
        "status": "PAUSED",
    }

    adset = {
        "name": f"{name} | adset",
        # campaign_id filled in at creation time
        "optimization_goal": "LANDING_PAGE_VIEWS",
        # LANDING_PAGE_VIEWS, not LINK_CLICKS: a link click that never loads the page is
        # exactly the metric the 2026-08-13 corpus showed to be worthless. This is a
        # delivery goal only — the ad is JUDGED by the kill rule, on qualified leads.
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "daily_budget": cents,
        # Hard stop at the end of the AEST week. Meta enforces end_time; it does not
        # enforce our $20. Belt (this) and braces (budget_gate).
        "end_time": end_dt.isoformat(),
        "targeting": build_targeting(),
        "status": "PAUSED",
    }

    link_data = {
        "message": copy["message"],
        "name": copy["headline"],
        "description": copy["description"],
        "link": copy["url"],
        "call_to_action": {"type": "LEARN_MORE"},
    }
    if image_hash:
        link_data["image_hash"] = image_hash
    elif copy.get("feature_image"):
        link_data["picture"] = copy["feature_image"]

    creative = {
        "name": f"{name} | creative",
        "object_story_spec": {"page_id": PAGE, "link_data": link_data},
        "degrees_of_freedom_spec": {
            "creative_features_spec": {"standard_enhancements": {"enroll_status": "OPT_OUT"}}
        },
    }

    ad = {
        "name": f"{name} | ad",
        # adset_id / creative filled in at creation time
        "status": "PAUSED",
    }

    return {"campaign": campaign, "adset": adset, "creative": creative, "ad": ad}


def as_form_encoded(payload: dict) -> dict:
    """Exactly what goes on the wire: nested values are JSON strings, not objects."""
    return {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in payload.items()}


# ──────────────────────────────────────────────────────────────────────────
# Graph API (only ever reached from --live / --kill)
# ──────────────────────────────────────────────────────────────────────────

def _token() -> str:
    tok = os.environ.get("FACEBOOK_ADS_TOKEN")
    if not tok:
        raise Refusal("FACEBOOK_ADS_TOKEN is not set — "
                      "set -a && source .env && set +a")
    return tok


def graph_post(path: str, payload: dict) -> dict:
    import requests
    data = as_form_encoded(payload)
    data["access_token"] = _token()
    return requests.post(f"{API}/{path}", data=data, timeout=45).json()


def graph_get(path: str, fields: str) -> dict:
    import requests
    return requests.get(f"{API}/{path}",
                        params={"fields": fields, "access_token": _token()},
                        timeout=45).json()


def upload_image_from_url(url: str) -> str | None:
    """Fetch the article's feature image and upload it, so Meta serves our bytes."""
    import requests
    r = requests.get(url, timeout=45)
    if r.status_code != 200 or not r.content:
        return None
    files = {"article.jpg": ("article.jpg", r.content)}
    resp = requests.post(f"{API}/{ACT}/adimages",
                         data={"access_token": _token()}, files=files, timeout=90).json()
    imgs = resp.get("images") or {}
    return list(imgs.values())[0]["hash"] if imgs else None


def verify_geo_readback(adset_id: str) -> list[str]:
    """Re-read the created adset and prove Meta did not widen our circles."""
    got = graph_get(adset_id, "targeting")
    locs = (((got.get("targeting") or {}).get("geo_locations") or {})
            .get("custom_locations") or [])
    problems = []
    want = {(round(lat, 4), round(lon, 4)): r
            for _l, lat, lon, r, _n, _p in SUBURB_GEO}
    if len(locs) != len(SUBURB_GEO):
        problems.append(f"adset has {len(locs)} custom locations, expected {len(SUBURB_GEO)}")
    for loc in locs:
        key = (round(float(loc.get("latitude", 0)), 4), round(float(loc.get("longitude", 0)), 4))
        if key not in want:
            problems.append(f"unexpected location {key} on the adset")
            continue
        unit = loc.get("distance_unit")
        radius = float(loc.get("radius", 0))
        km = radius if unit == "kilometer" else radius * 1.60934
        if km > want[key] + 0.51:
            problems.append(
                f"location {key} radius widened to {km:.1f}km (asked {want[key]}km)")
    return problems


# ──────────────────────────────────────────────────────────────────────────
# Rule 3 — ad decision logging
# ──────────────────────────────────────────────────────────────────────────

def log_decision(db, *, dtype: str, title: str, hypothesis: str, findings: list[str],
                 snapshot: dict, reasoning: str, tags: list[str]) -> None:
    db["ad_decisions"].insert_one({
        "date": aest_now().date().isoformat(),
        "type": dtype,
        "title": title,
        "hypothesis": hypothesis,
        "findings": findings,
        "data_snapshot": snapshot,
        "tags": sorted(set(["facebook_ads", "article_test", TAG.lower()] + tags)),
        "reasoning": reasoning,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ──────────────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────────────

def cmd_status(db) -> int:
    now = aest_now()
    g = budget_gate(db, None, now)
    print("=" * 78)
    print(f"  FIELDS ARTICLE AD TEST — STATUS   ({now:%Y-%m-%d %H:%M} AEST)")
    print("=" * 78)
    print("\n-- WEEK-TO-DATE BUDGET --\n")
    print(render_budget_arithmetic(g))

    print("\n-- RUNNING TESTS + KILL-RULE EVALUATION --\n")
    ads = g["spend"]["ads"]
    if not ads:
        print("  no tests registered.")
    for aid, d in ads.items():
        print(f"  {aid}  {d.get('ad_name') or ''}")
        print(f"    article        {d.get('article_slug')}")
        print(f"    status         {d.get('effective_status')}")
        print(f"    week spend     A${d['week_aud']:.2f}")
        rule = d.get("kill_rule")
        if not rule:
            print("    kill rule      MISSING — this ad predates the tool or was "
                  "created outside it. Treat as kill-on-sight.")
            continue
        print(f"    kill rule      {describe_kill_rule(rule)}")
        ev = evaluate_kill(db, aid, rule, d["week_aud"])
        q = ev["qualified"]
        print(f"    qualified      {q['total']} "
              f"(form leads {q['form_leads']}, site converters {q['site_converters']})")
        if q["conversion_events"]:
            print(f"    events         {q['conversion_events']}")
        print(f"    VERDICT        {'KILL' if ev['should_kill'] else 'continue'}")
        for r in ev["reasons"]:
            print(f"      * {r}")
        if ev["should_kill"]:
            print(f"      -> python3 scripts/fb_article_ad_test.py --kill {aid} "
                  f"--reason \"kill rule fired\"")

    print("\n-- GEO (fixed; no flag can change it) --\n")
    print(geo_summary())
    print()
    return 0


def cmd_test(db, args) -> int:
    now = aest_now()
    live = bool(args.live)
    mode = "LIVE" if live else "DRY RUN"

    print("=" * 78)
    print(f"  FIELDS ARTICLE AD TEST — {mode}   ({now:%Y-%m-%d %H:%M} AEST)")
    print("=" * 78)

    # ---- gate 1: kill rule -------------------------------------------------
    if args.kill_rule:
        try:
            rule = json.loads(args.kill_rule)
        except json.JSONDecodeError as e:
            raise Refusal(f"--kill-rule is not valid JSON: {e}")
    elif args.kill_spend is not None:
        rule = {"metric": "spend_without_qualified_lead",
                "max_spend_aud": float(args.kill_spend),
                "min_qualified_leads": int(args.kill_leads)}
        if args.kill_hard_spend is not None:
            rule["hard_max_spend_aud"] = float(args.kill_hard_spend)
    else:
        rule = None

    print("\n-- GATE 1: KILL RULE --\n")
    problems = validate_kill_rule(rule)
    if problems:
        print("  REFUSED\n")
        for p in problems:
            print(textwrap.fill(f"  * {p}", 76, subsequent_indent="    "))
        print("\n  Every ad this tool creates must carry a kill rule keyed on SPEND and "
              "\n  QUALIFIED LEADS. Example:\n"
              "    --kill-spend 8 --kill-leads 1")
        return 2
    print(f"  OK  {describe_kill_rule(rule)}")
    print(f"  rule: {json.dumps(rule)}")

    # ---- gate 2: article ---------------------------------------------------
    print("\n-- GATE 2: ARTICLE --\n")
    doc = load_article(db, args.article)
    copy = compose_copy(doc, args.headline, args.message, args.description)
    print(f"  slug         {copy['slug']}")
    print(f"  title        {doc.get('title')}")
    print(f"  status       {doc.get('status')}")
    print(f"  published_at {copy['published_at']}")
    print(f"  url          {copy['url']}")
    print(f"  image        {copy['feature_image']}")

    # ---- gate 3: editorial -------------------------------------------------
    print("\n-- GATE 3: EDITORIAL (CLAUDE.md Rule 5) --\n")
    breaches = editorial_check(copy["headline"], copy["message"], copy["description"])
    if breaches:
        print(f"  REFUSED — {len(breaches)} breach(es). Copy is NOT sanitised; supply\n"
              "  compliant copy with --headline / --message / --description, or fix the\n"
              "  article.\n")
        for b in breaches:
            print(textwrap.fill(f"  * {b}", 76, subsequent_indent="      "))
        return 3
    print(f"  OK  headline / primary text / description clean "
          f"(editorial_gate.check_text + no-single-valuation-in-headline)")

    # ---- gate 4: budget ----------------------------------------------------
    print("\n-- GATE 4: BUDGET (our arithmetic, not Meta's) --\n")
    g = budget_gate(db, args.daily, now)
    print(render_budget_arithmetic(g))
    if not g["ok"]:
        print("\n  REFUSED — see arithmetic above.")
        return 4
    daily = g["daily_aud"]

    # ---- payloads ----------------------------------------------------------
    end_dt = week_end_dt(now)
    payloads = build_payloads(copy, daily, end_dt, image_hash=None)

    print("\n-- RESOLVED GEO TARGETING --\n")
    print(geo_summary())

    print("\n-- PAYLOADS THAT WOULD BE SENT --\n")
    for label, path, payload in (
            ("1. CAMPAIGN", f"POST {API}/{ACT}/campaigns", payloads["campaign"]),
            ("2. ADSET", f"POST {API}/{ACT}/adsets", payloads["adset"]),
            ("3. ADCREATIVE", f"POST {API}/{ACT}/adcreatives", payloads["creative"]),
            ("4. AD", f"POST {API}/{ACT}/ads", payloads["ad"]),
    ):
        print(f"### {label}   {path}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print()
    print("  (nested objects are form-encoded as JSON strings on the wire; "
          "`access_token`\n   is appended by graph_post and is not shown)")
    print(f"\n  0. POST {API}/{ACT}/adimages  <- feature_image fetched and uploaded "
          f"first;\n     the returned hash replaces link_data.picture with "
          f"link_data.image_hash")
    print(f"\n  campaign_id -> adset.campaign_id, adset_id -> ad.adset_id, "
          f"creative id -> ad.creative")
    print(f"  everything is created status=PAUSED; adset end_time="
          f"{end_dt.isoformat()} (end of AEST week)")

    if not live:
        print("\n" + "=" * 78)
        print("  DRY RUN — nothing was sent. No campaign, adset, creative or ad exists.")
        print("  Re-run with --live to create (still PAUSED; you unpause in Ads Manager).")
        print("=" * 78)
        return 0

    # ---- live --------------------------------------------------------------
    print("\n-- CREATING (all PAUSED) --\n")
    # Re-run the budget gate immediately before spending anything: the dry-run print
    # above may be minutes old, and another run of this tool may have taken the headroom.
    g2 = budget_gate(db, daily, aest_now())
    if not g2["ok"]:
        print(render_budget_arithmetic(g2))
        raise Refusal("budget gate failed on re-check immediately before creation")

    img_hash = None
    if copy.get("feature_image"):
        img_hash = upload_image_from_url(copy["feature_image"])
        print(f"  image hash: {img_hash or 'FAILED — falling back to link_data.picture'}")
    payloads = build_payloads(copy, daily, end_dt, image_hash=img_hash)

    existing = db[REGISTRY].find_one({"campaign_name": CAMPAIGN_NAME}, {"campaign_id": 1})
    if existing and existing.get("campaign_id"):
        campaign_id = existing["campaign_id"]
        print(f"  campaign (reused): {campaign_id}")
    else:
        r = graph_post(f"{ACT}/campaigns", payloads["campaign"])
        if "id" not in r:
            raise Refusal(f"campaign create failed: {r}")
        campaign_id = r["id"]
        print(f"  campaign: {campaign_id}")

    payloads["adset"]["campaign_id"] = campaign_id
    r = graph_post(f"{ACT}/adsets", payloads["adset"])
    if "id" not in r:
        raise Refusal(f"adset create failed: {r}")
    adset_id = r["id"]
    print(f"  adset: {adset_id}")

    geo_problems = verify_geo_readback(adset_id)
    if geo_problems:
        graph_post(adset_id, {"status": "PAUSED"})
        raise Refusal("GEO READ-BACK FAILED — adset left PAUSED. "
                      + "; ".join(geo_problems))
    print("  geo read-back: OK (radii unchanged, all circles inside the fence)")

    r = graph_post(f"{ACT}/adcreatives", payloads["creative"])
    if "id" not in r:
        raise Refusal(f"creative create failed: {r}")
    creative_id = r["id"]
    print(f"  creative: {creative_id}")

    payloads["ad"]["adset_id"] = adset_id
    payloads["ad"]["creative"] = {"creative_id": creative_id}
    r = graph_post(f"{ACT}/ads", payloads["ad"])
    if "id" not in r:
        raise Refusal(f"ad create failed: {r}")
    ad_id = r["id"]
    print(f"  ad: {ad_id}  (PAUSED)")

    db[REGISTRY].insert_one({
        "_id": ad_id, "ad_id": ad_id, "ad_name": payloads["ad"]["name"],
        "adset_id": adset_id, "creative_id": creative_id,
        "campaign_id": campaign_id, "campaign_name": CAMPAIGN_NAME,
        "article_slug": copy["slug"], "article_title": doc.get("title"),
        "article_url": copy["url"],
        "daily_budget_aud": daily, "kill_rule": rule,
        "end_time": end_dt.isoformat(), "status": "PAUSED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "budget_arithmetic": {k: g2[k] for k in
                              ("cap_aud", "days_remaining", "committed_aud",
                               "headroom_aud", "daily_aud", "new_worst_case_aud",
                               "projected_total_aud")},
    })

    log_decision(
        db, dtype="new_campaign",
        title=f"Article test: {doc.get('title')}",
        hypothesis=("A published Fields article can attract middle-to-southern Gold "
                    "Coast homeowners at a cost that produces at least one qualified "
                    "lead before the kill-rule spend threshold."),
        findings=[
            f"week-to-date tagged spend A${g2['spend']['total_aud']:.2f} of "
            f"A${WEEKLY_CAP_AUD:.2f} cap",
            f"projected week total A${g2['projected_total_aud']:.2f}",
            f"kill rule: {describe_kill_rule(rule)}",
        ],
        snapshot={"ad_id": ad_id, "adset_id": adset_id, "campaign_id": campaign_id,
                  "article_slug": copy["slug"], "daily_budget_aud": daily,
                  "targeting_suburbs": [s[0] for s in SUBURB_GEO],
                  "kill_rule": rule, "status": "PAUSED"},
        reasoning=("Created PAUSED under the $20/week ring-fence. Budget verified "
                   "against ad_daily_metrics + ad_profiles.lifetime with unmeasured "
                   "days charged at daily x 1.25, not against Meta's advisory cap. "
                   "Kill rule keys on spend and qualified leads only; CTR rules are "
                   "rejected by the tool."),
        tags=["new_campaign", "traffic"])

    print("\n  registered + logged to ad_decisions. Ad is PAUSED — unpause manually.")
    return 0


def cmd_kill(db, ad_id: str, reason: str) -> int:
    entry = db[REGISTRY].find_one({"ad_id": str(ad_id)})
    if not entry:
        raise Refusal(
            f"ad {ad_id} is not in system_monitor.{REGISTRY} — this tool did not create "
            f"it and will not modify it. Use Ads Manager, or the script that built it.")
    now = aest_now()
    spend = week_spend(db, now)
    d = spend["ads"].get(str(ad_id), {})
    q = qualified_leads(db, ad_id)

    print(f"Pausing {ad_id} ({entry.get('ad_name')})")
    print(f"  week spend A${d.get('week_aud', 0):.2f}; qualified {q['total']} "
          f"(forms {q['form_leads']}, site {q['site_converters']})")
    print(f"  reason: {reason}")

    r = graph_post(str(ad_id), {"status": "PAUSED"})
    if not r.get("success") and "id" not in r:
        raise Refusal(f"pause failed: {r}")
    if entry.get("adset_id"):
        graph_post(str(entry["adset_id"]), {"status": "PAUSED"})

    db[REGISTRY].update_one(
        {"ad_id": str(ad_id)},
        {"$set": {"status": "PAUSED", "killed_at": datetime.now(timezone.utc).isoformat(),
                  "kill_reason": reason,
                  "kill_spend_aud": d.get("week_aud"),
                  "kill_qualified_leads": q["total"]}})

    log_decision(
        db, dtype="pause", title=f"Killed article test ad {ad_id}",
        hypothesis="Kill rule keyed on spend and qualified leads, never CTR.",
        findings=[f"week spend A${d.get('week_aud', 0):.2f}",
                  f"qualified leads {q['total']} "
                  f"(forms {q['form_leads']}, site converters {q['site_converters']})",
                  f"kill rule: {describe_kill_rule(entry['kill_rule'])}"
                  if entry.get("kill_rule") else "no kill rule on record"],
        snapshot={"ad_id": ad_id, "adset_id": entry.get("adset_id"),
                  "article_slug": entry.get("article_slug"),
                  "week_spend_aud": d.get("week_aud"), "qualified": q},
        reasoning=reason, tags=["pause", "kill_rule"])
    print("  PAUSED, registry updated, ad_decisions logged.")
    return 0


# ──────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Test a published article on Facebook, Gold Coast only, "
                    "hard A$20/week, kill rule mandatory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              --status
              --article my-article-slug --kill-spend 8
              --article my-article-slug --kill-spend 8 --kill-leads 1 --live
              --kill 120xxxxxxxxxxxxxxx --reason "spend $8, zero qualified"
        """))
    ap.add_argument("--article", help="slug (or _id) of a PUBLISHED article to test")
    ap.add_argument("--status", action="store_true",
                    help="week-to-date spend and running tests")
    ap.add_argument("--kill", metavar="AD_ID", help="pause an ad this tool created")
    ap.add_argument("--reason", help="required with --kill")

    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="default; print payloads, send nothing")
    ap.add_argument("--live", action="store_true",
                    help="actually create (still PAUSED). Requires all gates to pass.")

    ap.add_argument("--daily", type=float,
                    help="daily budget in A$; default auto-sized to the week's headroom")
    ap.add_argument("--kill-spend", type=float,
                    help="MANDATORY: kill if spend reaches this with too few qualified leads")
    ap.add_argument("--kill-leads", type=int, default=1,
                    help="qualified leads required by --kill-spend (default 1)")
    ap.add_argument("--kill-hard-spend", type=float,
                    help="optional unconditional spend stop")
    ap.add_argument("--kill-rule", help="full kill rule as JSON (alternative to --kill-spend)")

    ap.add_argument("--headline", help="override the ad headline")
    ap.add_argument("--message", help="override the ad primary text")
    ap.add_argument("--description", help="override the ad description")

    args = ap.parse_args()

    if not (args.status or args.article or args.kill):
        ap.error("one of --status, --article or --kill is required")
    if args.kill and not args.reason:
        ap.error("--kill requires --reason")

    db = get_db()
    try:
        if args.status:
            return cmd_status(db)
        if args.kill:
            return cmd_kill(db, args.kill, args.reason)
        return cmd_test(db, args)
    except Refusal as e:
        print(f"\nREFUSED: {e}\n")
        return 5


if __name__ == "__main__":
    sys.exit(main())
