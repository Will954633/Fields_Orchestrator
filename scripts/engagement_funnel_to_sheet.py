#!/usr/bin/env python3
"""
Weekly "Engagements" tab on the Live Leads Tracker — a parasocial
relationship-progression ledger.

WHAT THIS IS (and is NOT)
-------------------------
This is NOT a web-analytics traffic dashboard. It is a weekly cohort view of how
people are moving UP a relationship ladder toward a possible listing — grounded in
the parasocial-relationship science (see Will's "Parasocial Relationships – Science
& Playbook" doc). The literature is explicit: length of exposure does NOT predict
bond strength (Rubin & McHugh 1987); what predicts it is RETURN, DEPTH of what they
consume, and staged progression over time. So the rows are stages, not vanity counts:

  REACH → ATTENTION → VIDEO → RETURN → DEPTH → IDENTITY → INTENT → CONVERSION

Weeks run left→right across the top (columns), metrics down the left (rows), exactly
as Will asked. Columns are keyed to a FIXED origin week and grow rightward — a given
week always lives in the same physical column, so hand-typed manual cells (selling
conversations, Form 6, DMs) never move under the automation's feet.

DATA SOURCES (honest about what is and isn't instrumented)
----------------------------------------------------------
  * On-site behaviour (REACH/ATTENTION/RETURN/DEPTH/VIDEO/part of INTENT): PostHog.
    Session unit = properties.$session_id, which is only reliably populated from
    ~2026-08-17, hence ORIGIN_MONDAY. Engaged time = max(time_on_page.duration),
    capped at 300s of ACTIVE reading (same honesty rule as engagement_activity_to_sheet:
    a tab open 40 min is 5 min of reading, never 40).
  * On-site VIDEO (walkthroughs on /news, the median-house article, /off-market):
    PostHog walkthrough_* events. video depth from walkthrough_progress.pct. Our video
    is entirely on-site — we have no YouTube channel; FB/IG only funnel to the site.
  * IDENTITY / INTENT: system_monitor.crm_contacts + property_reports.
  * CONVERSION (selling conversations, Form 6) and two-way interactions (DMs, replies,
    name-use): NO automated source exists yet — these are MANUAL rows. The script
    writes their label but NEVER overwrites the week cells, so Will fills them by hand
    and they persist across nightly runs.

Run:
  python3 scripts/engagement_funnel_to_sheet.py --dry-run
  python3 scripts/engagement_funnel_to_sheet.py
  python3 scripts/engagement_funnel_to_sheet.py --rebuild   # re-layout (wipes computed
                                                             # cells; manual cells lost too)
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import statistics
import warnings
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone, date

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_client
from crm_sync import posthog_query, INTERNAL_IDS, BOT_CITIES
from job_status import job_run
from live_leads_to_sheet import (
    LIVE_SPREADSHEET_ID, get_sheets, tab_id, set_env_from_file, AEST,
)

TAB = "Engagements"
# $session_id is only reliably captured from mid-August; before that a session-based
# grid would be mostly nulls. This is a forward-looking tracker, so we start here.
ORIGIN_MONDAY = date(2026, 8, 17)
ENGAGED_CAP_S = 300          # active-reading ceiling (see module docstring)
VIDEO_DEEP_PCT = 75          # "reached deep into the video"

# Events we pull. Everything else is noise for this grid.
PULL_EVENTS = ("$pageview", "time_on_page", "offmarket_report_view",
               "walkthrough_start", "walkthrough_progress", "walkthrough_complete",
               "walkthrough_return", "analyse_home_address_submit", "address_search")

# Path prefixes that count as "market / editorial content" for the DEPTH read signal.
CONTENT_PREFIXES = ("/market-intelligence", "/market-metrics", "/articles", "/news")


# ---- week helpers ------------------------------------------------------------
def aest_monday(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    d = dt.astimezone(AEST).date()
    return d - timedelta(days=d.weekday())


def parse_ts(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def week_list() -> list[date]:
    """Origin Monday → this week's Monday, inclusive, stepping a week."""
    start = ORIGIN_MONDAY - timedelta(days=ORIGIN_MONDAY.weekday())
    end = aest_monday(datetime.now(timezone.utc))
    out, w = [], start
    while w <= end:
        out.append(w)
        w += timedelta(days=7)
    return out


def week_label(m: date) -> str:
    return f"wk {m.day} {m.strftime('%b')}"


# ---- entry channel -----------------------------------------------------------
def channel_for(ref_domain: str | None, utm_source: str | None) -> str:
    """Coarse entry channel for the 'greatest performing funnel' block."""
    u = (utm_source or "").lower()
    rd = (ref_domain or "").lower()
    if "facebook" in u or "fb" in u or "ig" in u or "instagram" in u or "facebook" in rd or "instagram" in rd:
        return "Facebook / IG"
    if "google" in u or "google" in rd or "bing" in rd:
        return "Search"
    if not rd or rd == "$direct" or "fieldsestate" in rd:
        return "Direct / internal-ref"
    return "Other referral"


# ---- PostHog pull + session assembly -----------------------------------------
def fetch_events(hours: int) -> list[dict]:
    ints = ", ".join("'" + i.replace("'", "") + "'" for i in INTERNAL_IDS) or "''"
    bots = ", ".join("'" + b.replace("'", "") + "'" for b in BOT_CITIES) or "''"
    evs = ", ".join("'" + e + "'" for e in PULL_EVENTS)
    rows = posthog_query(f"""
SELECT distinct_id, timestamp, event,
       properties.$session_id, properties.$pathname, properties.duration,
       properties.$referring_domain, properties.utm_source,
       properties.$geoip_city_name, properties.pct,
       properties.utm_campaign, properties.article, properties.suburb
FROM events
WHERE event IN ({evs})
  AND timestamp > now() - INTERVAL {int(hours)} HOUR
  AND (properties.$geoip_city_name IS NULL OR properties.$geoip_city_name NOT IN ({bots}))
  AND distinct_id NOT IN ({ints})
  AND coalesce(properties.is_internal, '') != 'true'
ORDER BY timestamp ASC
LIMIT 50000
""")
    out = []
    for r in rows:
        ts = parse_ts(r[1])
        if ts is None:
            continue
        out.append({
            "person": r[0], "ts": ts, "event": r[2], "sid": r[3],
            "path": r[4], "duration": r[5], "ref": r[6], "utm": r[7],
            "city": r[8], "pct": r[9], "campaign": r[10],
            "article": r[11], "suburb": r[12],
        })
    return out


def build_metrics(events: list[dict], weeks: list[date]):
    """Returns (metrics, sessions, person_weeks) — the latter two feed attribution."""
    wset = set(weeks)
    m: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))

    # --- session assembly (on-site behaviour) ---
    sessions: dict[str, dict] = {}
    person_weeks: dict[str, set[date]] = defaultdict(set)   # person -> active weeks
    # video, keyed per week -> sets of persons
    vid: dict[date, dict[str, set]] = defaultdict(
        lambda: {"start": set(), "deep": set(), "complete": set(), "return": set()})
    offmarket_open: dict[date, set] = defaultdict(set)
    ayh_submit: dict[date, set] = defaultdict(set)
    addr_search: dict[date, set] = defaultdict(set)

    for e in events:
        wk = aest_monday(e["ts"])
        if wk not in wset:
            continue
        ev, person = e["event"], e["person"]

        # video signals are person-centric (parasocial = people, not plays)
        if ev == "walkthrough_start":
            vid[wk]["start"].add(person)
            continue
        if ev == "walkthrough_progress":
            try:
                if e["pct"] is not None and float(e["pct"]) >= VIDEO_DEEP_PCT:
                    vid[wk]["deep"].add(person)
            except (TypeError, ValueError):
                pass
            continue
        if ev == "walkthrough_complete":
            vid[wk]["complete"].add(person)
            continue
        if ev == "walkthrough_return":
            vid[wk]["return"].add(person)
            continue
        if ev == "offmarket_report_view":
            offmarket_open[wk].add(person)
            continue
        if ev == "analyse_home_address_submit":
            ayh_submit[wk].add(person)
            continue
        if ev == "address_search":
            addr_search[wk].add(person)
            continue

        # $pageview / time_on_page -> sessions
        sid = e["sid"]
        if not sid:
            continue
        s = sessions.get(sid)
        if s is None:
            s = sessions[sid] = {"sid": sid, "person": person, "week": wk, "first_ts": e["ts"],
                                 "max_eng": 0.0, "pages": set(), "content_read": False,
                                 "ref": e["ref"], "utm": e["utm"], "campaign": e["campaign"],
                                 "content_paths": set()}
        if e["ts"] < s["first_ts"]:
            s["first_ts"] = e["ts"]
            s["ref"], s["utm"] = e["ref"], e["utm"]   # entry attribution = first hit
            s["campaign"] = e["campaign"]
        if ev == "$pageview" and e["path"]:
            s["pages"].add(e["path"])
        if ev == "time_on_page" and e["duration"] is not None:
            try:
                dur = float(e["duration"])
            except (TypeError, ValueError):
                dur = 0.0
            s["max_eng"] = max(s["max_eng"], dur)
            path = e["path"] or ""
            if dur >= 30 and any(path.startswith(p) for p in CONTENT_PREFIXES):
                s["content_read"] = True
                s["content_paths"].add(path)

    # --- REACH / ATTENTION / DEPTH / funnel from sessions ---
    per_person_week_sessions: dict[tuple, int] = defaultdict(int)
    for s in sessions.values():
        wk, person = s["week"], s["person"]
        person_weeks[person].add(wk)
        per_person_week_sessions[(person, wk)] += 1

        eng = s["max_eng"]
        bucket = ("att_bounce" if eng < 10 else "att_skim" if eng < 30
                  else "att_read" if eng < 120 else "att_deep" if eng < 300
                  else "att_marathon")
        m[bucket][wk] += 1
        m["_att_total"][wk] += 1
        if eng >= 30:                       # engaged = read + deep + marathon
            m["att_engaged"][wk] += 1

        npages = len(s["pages"])
        m["_pages_sum"][wk] += npages
        if npages >= 3:
            m["depth_multipage"][wk] += 1
        if s["content_read"]:
            m["depth_content_read"][wk] += 1

        m[f"fun_{channel_bucket(s['ref'], s['utm'])}"][wk] += 1

    # REACH: unique / new / returning persons per week
    first_week = {p: min(ws) for p, ws in person_weeks.items()}
    for person, ws in person_weeks.items():
        fw = first_week[person]
        sorted_ws = sorted(ws)
        for wk in sorted_ws:
            m["reach_unique"][wk] += 1
            if wk == fw:
                m["reach_new"][wk] += 1
            else:
                m["reach_returning"][wk] += 1
            # RETURN loyalty depth: how many EARLIER active weeks by now
            prior = sum(1 for x in sorted_ws if x < wk)
            key = ("ret_1" if prior == 0 else "ret_2" if prior == 1
                   else "ret_3_4" if prior <= 3 else "ret_5p")
            m[key][wk] += 1

    # DEPTH average pages/session (decimal)
    for wk in weeks:
        tot = m["_att_total"].get(wk, 0)
        m["depth_avg_pages"][wk] = round(m["_pages_sum"].get(wk, 0) / tot, 1) if tot else 0

    # VIDEO
    for wk in weeks:
        v = vid.get(wk, {})
        starts = len(v.get("start", ()))
        comp = len(v.get("complete", ()))
        m["vid_plays"][wk] = starts
        m["vid_deep"][wk] = len(v.get("deep", ()))
        m["vid_complete"][wk] = comp
        m["vid_return"][wk] = len(v.get("return", ()))
        m["vid_completion_pct"][wk] = round(100 * comp / starts) if starts else 0
        m["intent_offmarket_open"][wk] = len(offmarket_open.get(wk, ()))
        m["intent_ayh_submit"][wk] = len(ayh_submit.get(wk, ()))
        m["intent_address_search"][wk] = len(addr_search.get(wk, ()))

    # HEALTH: saturation proxy = median sessions/week among returning visitors.
    # The mere-exposure effect is an inverted-U (Montoya 2017): watch this trend UP
    # over many exposures as an over-posting warning, not a goal to maximise.
    for wk in weeks:
        vals = [n for (p, w), n in per_person_week_sessions.items()
                if w == wk and len(person_weeks[p]) > 1]
        m["health_saturation"][wk] = round(statistics.median(vals), 1) if vals else 0

    return m, sessions, person_weeks


def channel_bucket(ref, utm) -> str:
    c = channel_for(ref, utm)
    return {"Facebook / IG": "facebook", "Search": "search",
            "Direct / internal-ref": "direct", "Other referral": "other"}[c]


# ============================================================================
#  ATTRIBUTION LAYER — decompose each metric into the segments that move it.
#
#  HONESTY: this is observational. A segment breakdown EXPLAINS a week-over-week
#  move (you can see which channel/campaign/content gained or lost); it does not
#  PROVE cause. Only a controlled A/B test proves cause. The "what we did" block
#  lists our actions that week as cause HYPOTHESES to line up against the moves.
# ============================================================================

def campaign_label(campaign, utm) -> str:
    c = (campaign or "").strip()
    if c:
        return c[:38]
    u = (utm or "").strip()
    if u:
        return f"(no campaign · {u[:20]})"
    return "(organic / direct — no campaign)"


def content_label(path: str) -> str:
    """A readable label for a content path, e.g. '/market-intelligence/Robina/sell-now'
    -> 'Robina · sell-now'; '/articles/robina-market-update-august-2026' -> the slug."""
    p = (path or "").rstrip("/")
    parts = [x for x in p.split("/") if x]
    if not parts:
        return "(home)"
    if parts[0] in ("market-intelligence", "market-metrics") and len(parts) >= 2:
        sub = parts[1].replace("-", " ")
        cat = parts[2] if len(parts) > 2 else "overview"
        return f"{sub} · {cat}"
    if parts[0] == "articles" and len(parts) > 1:
        return f"article: {parts[1][:34]}"
    if parts[0] == "news":
        return "News & Research" + (f" · {parts[1]}" if len(parts) > 1 else "")
    return p[:38]


def _add(store, key, dim, value, wk, unit):
    store[key][dim].setdefault(value, {}).setdefault(wk, set()).add(unit)


def build_attribution(events, weeks, sessions, person_weeks):
    """attr[metric_key][dim][value][week] -> distinct-unit count."""
    wset = set(weeks)
    store: dict = defaultdict(lambda: defaultdict(dict))  # sets, finalised at the end
    first_week = {p: min(ws) for p, ws in person_weeks.items()}

    # per (person, week): entry channel/campaign = their earliest session that week
    pw_entry, pw_ts = {}, {}
    person_first_channel = {}   # person -> channel of earliest session overall (for CRM join)
    pf_ts = {}
    for s in sessions.values():
        ch = channel_for(s["ref"], s["utm"])
        cam = campaign_label(s["campaign"], s["utm"])
        k = (s["person"], s["week"])
        if k not in pw_ts or s["first_ts"] < pw_ts[k]:
            pw_ts[k] = s["first_ts"]; pw_entry[k] = (ch, cam)
        if s["person"] not in pf_ts or s["first_ts"] < pf_ts[s["person"]]:
            pf_ts[s["person"]] = s["first_ts"]; person_first_channel[s["person"]] = ch

    # REACH — unique visitors by entry channel / campaign / new-vs-returning
    for (person, wk), (ch, cam) in pw_entry.items():
        if wk not in wset:
            continue
        _add(store, "reach_unique", "channel", ch, wk, person)
        _add(store, "reach_unique", "campaign", cam, wk, person)
        nr = "new" if wk == first_week[person] else "returning"
        _add(store, "reach_unique", "newret", nr, wk, person)

    # SESSION metrics — engaged (30s+), content read, multi-page
    for s in sessions.values():
        wk = s["week"]
        if wk not in wset:
            continue
        ch = channel_for(s["ref"], s["utm"]); cam = campaign_label(s["campaign"], s["utm"])
        nr = "new" if wk == first_week[s["person"]] else "returning"
        eng = s["max_eng"]
        targets = []
        if eng >= 30:
            targets.append("att_engaged")
        if s["content_read"]:
            targets.append("depth_content_read")
        if len(s["pages"]) >= 3:
            targets.append("depth_multipage")
        # Attribute by SESSION id, so channel/campaign/new-vs-returning columns sum back
        # to the metric total (which counts sessions). Content is the exception below —
        # one session can read several pages, so content columns can exceed the total.
        for key in targets:
            _add(store, key, "channel", ch, wk, s["sid"])
            _add(store, key, "campaign", cam, wk, s["sid"])
            _add(store, key, "newret", nr, wk, s["sid"])
        if s["content_read"]:
            for p in s["content_paths"]:
                _add(store, "depth_content_read", "content", content_label(p), wk, s["sid"])
                _add(store, "att_engaged", "content", content_label(p), wk, s["sid"])

    # EVENT metrics — video + intent (attribute by the event's own utm/referrer)
    ev_map = {"walkthrough_start": "vid_plays", "walkthrough_complete": "vid_complete",
              "offmarket_report_view": "intent_offmarket_open",
              "analyse_home_address_submit": "intent_ayh_submit",
              "address_search": "intent_address_search"}
    for e in events:
        key = ev_map.get(e["event"])
        if not key:
            continue
        wk = aest_monday(e["ts"])
        if wk not in wset:
            continue
        ch = channel_for(e["ref"], e["utm"]); cam = campaign_label(e["campaign"], e["utm"])
        _add(store, key, "channel", ch, wk, e["person"])
        _add(store, key, "campaign", cam, wk, e["person"])
        if key in ("vid_plays", "vid_complete"):
            # article can arrive as a boolean flag on some events — only a real
            # slug/title string is a content value; otherwise fall back to suburb.
            art = e["article"] if isinstance(e["article"], str) else None
            sub = e["suburb"] if isinstance(e["suburb"], str) else None
            content = art or sub
            if content:
                _add(store, key, "content", content[:38], wk, e["person"])

    # finalise sets -> counts
    attr: dict = {}
    for key, dims in store.items():
        attr[key] = {}
        for dim, values in dims.items():
            attr[key][dim] = {v: {wk: len(s) for wk, s in byweek.items()}
                              for v, byweek in values.items()}
    return attr, person_first_channel


def crm_attribution(sm, weeks, person_first_channel):
    """New-CRM-contact attribution: join each contact to the entry channel of its
    PostHog person (if we saw a session for them), else 'no on-site session'."""
    wset = set(weeks)
    store: dict = defaultdict(lambda: defaultdict(dict))
    for c in sm.crm_contacts.find({}, {"created_at": 1, "posthog_ids": 1,
                                        "primary_posthog_id": 1}):
        wk = aest_monday(parse_ts(c.get("created_at")))
        if wk not in wset:
            continue
        ids = list(c.get("posthog_ids") or [])
        if c.get("primary_posthog_id"):
            ids.append(c["primary_posthog_id"])
        ch = next((person_first_channel[i] for i in ids if i in person_first_channel),
                  "no on-site session")
        _add(store, "id_new_contacts", "channel", ch, wk, str(c.get("_id")))
    return {k: {d: {v: {wk: len(s) for wk, s in bw.items()} for v, bw in vals.items()}
                for d, vals in dims.items()} for k, dims in store.items()}


# ---- "what we did" (cause hypotheses, GLOBAL — same on every section tab) -----
def what_we_did(sm, weeks):
    wset = set(weeks)
    wd = {wk: {"spend": 0.0, "launched": 0, "paused": 0, "changed": 0,
               "articles": [], "posts": 0, "deploys": []} for wk in weeks}
    LAUNCH = {"new_campaign", "new_ad", "new_ads_and_pause", "enable"}
    PAUSE = {"pause", "pruning"}
    for d in sm.ad_daily_metrics.find({}, {"date": 1, "spend_aud": 1}):
        wk = aest_monday(parse_ts(d.get("date")))
        if wk in wset:
            try:
                wd[wk]["spend"] += float(d.get("spend_aud") or 0)
            except (TypeError, ValueError):
                pass
    for d in sm.ad_decisions.find({}, {"date": 1, "type": 1, "title": 1}):
        wk = aest_monday(parse_ts(d.get("date")))
        if wk not in wset:
            continue
        t = d.get("type") or ""
        if t in LAUNCH:
            wd[wk]["launched"] += 1
        elif t in PAUSE:
            wd[wk]["paused"] += 1
        else:
            wd[wk]["changed"] += 1
    for a in sm.content_articles.find({"status": "published"}, {"published_at": 1, "title": 1}):
        wk = aest_monday(parse_ts(a.get("published_at")))
        if wk in wset and a.get("title"):
            wd[wk]["articles"].append(a["title"][:50])
    for p in sm.fb_page_posts.find({}, {"posted_at": 1}):
        wk = aest_monday(parse_ts(p.get("posted_at")))
        if wk in wset:
            wd[wk]["posts"] += 1
    for w in sm.website_change_log.find({}, {"date": 1, "title": 1}):
        wk = aest_monday(parse_ts(w.get("date")))
        if wk in wset and w.get("title"):
            wd[wk]["deploys"].append(w["title"][:50])
    return wd


# ---- section registry: which metrics each drill-down tab attributes ----------
# (metric label, metric key, [dims to break down])
SECTIONS = [
    ("REACH", ["reach_unique"], "Attr · Reach", [
        ("Unique visitors", "reach_unique", ["channel", "campaign", "newret"]),
    ]),
    ("ATTENTION", ["att_read", "att_deep", "att_marathon"], "Attr · Attention", [
        ("Engaged sessions (30s+ active)", "att_engaged", ["channel", "campaign", "content", "newret"]),
    ]),
    ("VIDEO", ["vid_plays", "vid_complete"], "Attr · Video", [
        ("Video shown (autostart)", "vid_plays", ["channel", "campaign", "content"]),
        ("Completed", "vid_complete", ["channel", "campaign", "content"]),
    ]),
    ("DEPTH", ["depth_content_read", "depth_multipage"], "Attr · Depth", [
        ("Read market/editorial content (30s+)", "depth_content_read",
         ["channel", "campaign", "content", "newret"]),
        ("Multi-page sessions (≥3)", "depth_multipage", ["channel", "campaign", "newret"]),
    ]),
    ("IDENTITY", ["id_new_contacts"], "Attr · Identity", [
        ("New CRM contact records", "id_new_contacts", ["channel"]),
    ]),
    ("INTENT", ["intent_address_search", "intent_ayh_submit", "intent_offmarket_open"],
     "Attr · Intent", [
        ("Address searched", "intent_address_search", ["channel", "campaign"]),
        ("Analyse-Your-Home submissions", "intent_ayh_submit", ["channel", "campaign"]),
        ("Off-market report opens", "intent_offmarket_open", ["channel", "campaign"]),
    ]),
]
# The RETURN + CONVERSION drill-downs are special (journeys, not channel/campaign breakdowns).
RETURN_TAB = "Attr · Return"
CONV_TAB = "Attr · Conversion"
HISTORY_DAYS = 240          # how far back to reconstruct a visitor's content chain

# metric key -> section tab title (for hyperlinking Engagements cells)
METRIC_TO_TAB = {k: title for _sec, keys, title, _specs in SECTIONS for k in keys}
METRIC_TO_TAB.update({k: RETURN_TAB for k in
                      ("reach_returning", "ret_2", "ret_3_4", "ret_5p")})
METRIC_TO_TAB.update({k: CONV_TAB for k in
                      ("intent_ayh_submit", "intent_offmarket_open", "conv_offmarket_unlock")})

DIM_TITLE = {"channel": "by entry channel", "campaign": "by campaign / source",
             "content": "by content (a visit can read several — may exceed the total)",
             "newret": "new vs returning"}
DIM_CAP = {"campaign": 8, "content": 10, "channel": 8, "newret": 2}


def fmt_num(v):
    if v is None or v == 0:
        return ""
    if isinstance(v, float) and not v.is_integer():
        return round(v, 1)
    return int(v)


def wow_mover(channel_dict: dict, weeks: list[date]) -> str:
    """Largest single-channel change between the two most recent weeks, in words."""
    if len(weeks) < 2 or not channel_dict:
        return ""
    w0, w1 = weeks[-2], weeks[-1]
    best = None
    for v, bw in channel_dict.items():
        a, b = bw.get(w0, 0), bw.get(w1, 0)
        d = b - a
        if best is None or abs(d) > abs(best[1]):
            best = (v, d, a, b)
    if not best or best[1] == 0:
        return ""
    v, d, a, b = best
    return (f"{v}: {a}→{b} ({'+' if d > 0 else ''}{d}) between {week_label(w0)} and "
            f"{week_label(w1)} — the biggest channel move")


def section_rows(sec_name, specs, metrics, attr, whatwedid, weeks, back_url):
    render = list(reversed(weeks))
    labels = [week_label(w) for w in render]
    HEADER = "Metric ↓  /  ← newer   Week   older →"
    rows = [
        [f"▸ {sec_name} — attribution & cause/effect"],
        [f'=HYPERLINK("{back_url}","← back to Engagements")'],
        ["Segments EXPLAIN a week-over-week move (which one gained/lost); they do NOT "
         "prove cause. 'What we did' below = hypotheses to line up. Only an A/B test proves cause."],
        [HEADER] + labels,
    ]
    for mlabel, key, dims in specs:
        total = metrics.get(key, {})
        rows.append([f"■ {mlabel}"] + [fmt_num(total.get(w)) for w in render])
        mv = wow_mover((attr.get(key, {}) or {}).get("channel", {}), weeks)
        if mv:
            rows.append([f"   ▸ biggest recent shift — {mv}"])
        for dim in dims:
            vals = (attr.get(key, {}) or {}).get(dim, {})
            if not vals:
                continue
            rows.append([f"   {DIM_TITLE[dim]}:"])
            ranked = sorted(vals.items(), key=lambda kv: -sum(kv[1].values()))
            cap = DIM_CAP.get(dim, 8)
            for v, bw in ranked[:cap]:
                rows.append([f"      ↳ {v}"] + [fmt_num(bw.get(w)) for w in render])
            rest = ranked[cap:]
            if rest:
                agg = defaultdict(int)
                for _v, bw in rest:
                    for w, c in bw.items():
                        agg[w] += c
                rows.append([f"      ↳ (+{len(rest)} more)"] + [fmt_num(agg.get(w)) for w in render])
        rows.append([])

    rows.append(["▸ WHAT WE DID (cause hypotheses — global, same on every attribution tab)"])
    rows.append([HEADER] + labels)
    cats = [("FB ad spend $ (week)", "spend"), ("Ads launched", "launched"),
            ("Ads paused", "paused"), ("Ads changed", "changed"),
            ("Articles published", "posts_art"), ("FB organic posts", "posts"),
            ("Site changes shipped", "deploys_n")]

    def cell(wk, ckey):
        w = whatwedid.get(wk, {})
        if ckey == "spend":
            return round(w.get("spend", 0)) or ""
        if ckey == "posts_art":
            return len(w.get("articles", [])) or ""
        if ckey == "deploys_n":
            return len(w.get("deploys", [])) or ""
        return w.get(ckey, 0) or ""

    for clabel, ckey in cats:
        rows.append([clabel] + [cell(w, ckey) for w in render])
    rows.append([])
    rows.append(["▸ DETAIL — what shipped each week (newest first)"])
    for w in render:
        wd = whatwedid.get(w, {})
        bits = []
        if wd.get("articles"):
            bits.append("Published: " + "; ".join(wd["articles"]))
        if wd.get("deploys"):
            bits.append("Site: " + "; ".join(wd["deploys"]))
        if wd.get("launched") or wd.get("paused") or wd.get("changed"):
            bits.append(f"Ads: {wd.get('launched', 0)} launched / {wd.get('paused', 0)} paused "
                        f"/ {wd.get('changed', 0)} changed")
        if wd.get("spend"):
            bits.append(f"Spend ${round(wd['spend'])}")
        if wd.get("posts"):
            bits.append(f"{wd['posts']} FB posts")
        rows.append([week_label(w), "  •  ".join(bits) if bits else "—"])
    return rows


def ensure_plain_tab(svc, ssid, title):
    """A section drill-down tab, created at the far right (appended) if absent."""
    sid = tab_id(svc, ssid, title)
    if sid is not None:
        return sid
    res = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
        "addSheet": {"properties": {"title": title, "gridProperties": {
            "rowCount": 200, "columnCount": 70,
            "frozenRowCount": 4, "frozenColumnCount": 1}}}}]}).execute()
    return res["replies"][0]["addSheet"]["properties"]["sheetId"]


def write_section_tabs(svc, ssid, weeks, metrics, attr, whatwedid):
    base = f"https://docs.google.com/spreadsheets/d/{ssid}/edit"
    eng_gid = tab_id(svc, ssid, TAB)
    back = f"{base}#gid={eng_gid}"
    gids = {}
    for sec_name, _keys, title, specs in SECTIONS:
        sid = ensure_plain_tab(svc, ssid, title)
        rows = section_rows(sec_name, specs, metrics, attr, whatwedid, weeks, back)
        svc.spreadsheets().values().clear(
            spreadsheetId=ssid, range=f"'{title}'", body={}).execute()
        svc.spreadsheets().values().update(
            spreadsheetId=ssid, range=f"'{title}'!A1", valueInputOption="USER_ENTERED",
            body={"values": rows}).execute()
        # formatting: bold structural rows, widen col A
        reqs = [{"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 340}, "fields": "pixelSize"}}]
        for i, r in enumerate(rows):
            head = (r[0] if r else "")
            if head.startswith("▸") or head.startswith("■") or head == "Metric ↓  /  ← newer   Week   older →":
                shade = head.startswith("▸")
                cell = {"textFormat": {"bold": True}}
                if shade:
                    cell["backgroundColor"] = {"red": 0.90, "green": 0.93, "blue": 0.98}
                reqs.append({"repeatCell": {
                    "range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1},
                    "cell": {"userEnteredFormat": cell},
                    "fields": "userEnteredFormat.textFormat.bold" + (
                        ",userEnteredFormat.backgroundColor" if shade else "")}})
        svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": reqs}).execute()
        gids[title] = sid
    return gids


def link_engagement_cells(svc, ssid, gids):
    """Turn each attributed metric's label on Engagements into a link to its section tab."""
    base = f"https://docs.google.com/spreadsheets/d/{ssid}/edit"
    data = []
    for i, (kind, label, key) in enumerate(GRID):
        title = METRIC_TO_TAB.get(key)
        # the manual selling-conversations row links to the conversion drill-down too
        if kind == "manual" and "Selling conversations" in label and CONV_TAB in gids:
            title = CONV_TAB
        elif kind not in ("computed", "pct"):
            continue
        if not title or title not in gids:
            continue
        url = f"{base}#gid={gids[title]}"
        safe = label.replace('"', "'")
        # a manual row keeps its hand-typed week cells — we only rewrite col A here
        data.append({"range": f"'{TAB}'!{a1(i + 2, 1)}",
                     "values": [[f'=HYPERLINK("{url}","{safe}  ↗")']]})
    if data:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=ssid,
            body={"valueInputOption": "USER_ENTERED", "data": data}).execute()


# ============================================================================
#  RETURN JOURNEYS — the content chain each returning visitor was exposed to,
#  from their FIRST interaction with the brand. Per the parasocial science, it is
#  the SEQUENCE — not the count of returns — that carries the "why they came back"
#  signal, so we reconstruct the whole chain rather than aggregate it away.
# ============================================================================
RETURN_VISIT_GAP_MIN = 30
MAX_JOURNEYS = 80          # most-loyal first; note the cap on the tab


def chain_touch(ev, path, suburb) -> str | None:
    """A compact content label for one event; None for navigational noise."""
    if ev == "walkthrough_start":
        return f"▶video{(' ' + suburb) if isinstance(suburb, str) else ''}"
    if ev == "offmarket_report_view":
        return "off-mkt report"
    if ev == "analyse_home_address_submit":
        return "★AYH submit"
    if ev == "address_search":
        return "addr search"
    p = (path or "").rstrip("/")
    parts = [x for x in p.split("/") if x]
    if not parts:
        return None
    h = parts[0]
    if h in ("market-intelligence", "market-metrics") and len(parts) >= 2:
        cat = parts[2] if len(parts) > 2 else "overview"
        return f"{parts[1].replace('-', ' ')}:{cat}"
    if h == "articles" and len(parts) > 1:
        return f"article:{parts[1][:22]}"
    if h == "news":
        return "News"
    if h == "off-market" and len(parts) > 1:
        return f"off-mkt:{parts[1][:18]}"
    if h in ("your-home", "building") and len(parts) > 1:
        return f"home report:{parts[1][:16]}"
    if h == "property" and len(parts) > 1:
        return f"listing:{parts[1][:16]}"
    if h == "analyse-your-home":
        return "AYH page"
    return None


def build_identity_map(sm, returners: set) -> dict:
    out = {}
    for c in sm.crm_contacts.find({}, {"posthog_ids": 1, "primary_posthog_id": 1,
                                       "name": 1, "email": 1, "property_address": 1,
                                       "ayh_home": 1}):
        ids = list(c.get("posthog_ids") or [])
        if c.get("primary_posthog_id"):
            ids.append(c["primary_posthog_id"])
        ids = [i for i in ids if i in returners]
        if not ids:
            continue
        ah = c.get("ayh_home") or {}
        home = (c.get("property_address") or "").strip() or (
            ah.get("slug") if isinstance(ah, dict) else "")
        label = (c.get("name") or "").strip() or (c.get("email") or "").strip() or (
            f"home: {home}" if home else "")
        for i in ids:
            if label and i not in out:
                out[i] = label
    return out


def build_return_journeys(sm, returners: list):
    """(aggregate, journeys) for returning visitors. Journeys carry the ordered
    content chain across visits, first touch → each return."""
    if not returners:
        return {}, []
    ints = ", ".join("'" + i.replace("'", "") + "'" for i in INTERNAL_IDS) or "''"
    evs_ev = ("'$pageview','walkthrough_start','offmarket_report_view',"
              "'analyse_home_address_submit','address_search'")
    by_person: dict[str, list[dict]] = defaultdict(list)
    CHUNK = 120
    for i in range(0, len(returners), CHUNK):
        chunk = returners[i:i + CHUNK]
        id_list = ", ".join("'" + d.replace("'", "") + "'" for d in chunk)
        rows = posthog_query(f"""
SELECT distinct_id, timestamp, event, properties.$pathname,
       properties.$referring_domain, properties.utm_source, properties.suburb
FROM events
WHERE distinct_id IN ({id_list})
  AND event IN ({evs_ev})
  AND timestamp > now() - INTERVAL {HISTORY_DAYS} DAY
  AND distinct_id NOT IN ({ints})
ORDER BY distinct_id, timestamp ASC
LIMIT 50000
""")
        for r in rows:
            ts = parse_ts(r[1])
            if ts:
                by_person[r[0]].append({"ts": ts, "event": r[2], "path": r[3],
                                         "ref": r[4], "utm": r[5], "suburb": r[6]})

    idmap = build_identity_map(sm, set(returners))
    agg = {"first_channel": Counter(), "first_content": Counter(), "trigger": Counter()}
    journeys = []
    for did, evs in by_person.items():
        # split into visits (>30 min gap)
        visits, cur = [], None
        for e in evs:
            if cur is None or (e["ts"] - cur[-1]["ts"]) > timedelta(minutes=RETURN_VISIT_GAP_MIN):
                cur = []
                visits.append(cur)
            cur.append(e)
        if len(visits) < 2:
            continue   # not actually a returner within history
        vlist = []
        for v in visits:
            touches = []
            for e in v:
                t = chain_touch(e["event"], e["path"], e["suburb"])
                if t and (not touches or touches[-1] != t):
                    touches.append(t)
            vlist.append({"start": v[0]["ts"], "end": v[-1]["ts"], "touches": touches,
                          "ch": channel_for(v[0]["ref"], v[0]["utm"])})
        first_ch = vlist[0]["ch"]
        first_content = next((t for v in vlist for t in v["touches"]), None)
        trigger = next((t for t in vlist[1]["touches"]), None)  # opens the 1st return
        wks = len({aest_monday(v["start"]) for v in vlist})
        agg["first_channel"][first_ch] += 1
        if first_content:
            agg["first_content"][first_content] += 1
        if trigger:
            agg["trigger"][trigger] += 1
        journeys.append({
            "who": idmap.get(did, f"Anon {did[:8]}"),
            "first": f"{first_ch} · {first_content or '—'}",
            "wks": wks, "visits": len(vlist), "vlist": vlist,
        })
    journeys.sort(key=lambda j: (-j["visits"], -j["wks"]))
    return agg, journeys


def chain_string(vlist) -> str:
    """'1) Robina:overview → article:x  ⟶ +5d ⟶  2) off-mkt:y → ★AYH submit'
    Long journeys keep the first two + last three visits (first touch is essential)."""
    show = vlist
    elided = False
    if len(vlist) > 8:
        show = vlist[:2] + vlist[-3:]
        elided = True
    parts, prev_end = [], None
    for idx, v in enumerate(show):
        real_i = vlist.index(v)
        if elided and idx == 2:
            parts.append(f"  ⟶ …({len(vlist) - 5} more visits)… ⟶  ")
            prev_end = None
        gap = (v["start"] - prev_end).days if prev_end else None
        if gap is not None:
            parts.append(f"  ⟶ +{gap}d ⟶  ")
        parts.append(f"{real_i + 1}) " + " → ".join(v["touches"] or ["(browse)"]))
        prev_end = v["end"]
    return "".join(parts)


def write_return_tab(svc, ssid, agg, journeys, back_url):
    sid = ensure_plain_tab(svc, ssid, RETURN_TAB)
    rows = [
        ["▸ RETURN — why they came back: the content chain"],
        [f'=HYPERLINK("{back_url}","← back to Engagements")'],
        ["The chain is the signal (parasocial science): it's the SEQUENCE, not the count of "
         "returns, that says why. Each row = one returning visitor, first touch → each return. "
         "Watch what content recurs and what opens a return visit."],
        [],
        ["▸ WHAT HOOKS RETURNERS (cohort aggregate)"],
        ["First touch — entry channel", "returners"],
    ]
    for v, n in agg.get("first_channel", Counter()).most_common(8):
        rows.append([f"   ↳ {v}", n])
    rows.append(["First touch — content", "returners"])
    for v, n in agg.get("first_content", Counter()).most_common(10):
        rows.append([f"   ↳ {v}", n])
    rows.append(["What opens a return visit (return trigger)", "returners"])
    for v, n in agg.get("trigger", Counter()).most_common(10):
        rows.append([f"   ↳ {v}", n])
    rows.append([])
    rows.append([f"▸ RETURNER JOURNEYS — most loyal first"
                 + (f" (top {MAX_JOURNEYS} of {len(journeys)})" if len(journeys) > MAX_JOURNEYS else "")])
    rows.append(["Who", "First touch", "Wks", "Visits", "Content chain: first → each return"])
    for j in journeys[:MAX_JOURNEYS]:
        rows.append([j["who"], j["first"], j["wks"], j["visits"], chain_string(j["vlist"])])

    svc.spreadsheets().values().clear(spreadsheetId=ssid, range=f"'{RETURN_TAB}'", body={}).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range=f"'{RETURN_TAB}'!A1", valueInputOption="USER_ENTERED",
        body={"values": rows}).execute()
    # formatting
    reqs = [
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 220}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 1, "endIndex": 2}, "properties": {"pixelSize": 190}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 900}, "fields": "pixelSize"}},
        {"repeatCell": {"range": {"sheetId": sid, "startColumnIndex": 4, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
    ]
    for i, r in enumerate(rows):
        head = r[0] if r else ""
        if head.startswith("▸") or head == "Who":
            shade = head.startswith("▸")
            cell = {"textFormat": {"bold": True}}
            if shade:
                cell["backgroundColor"] = {"red": 0.90, "green": 0.93, "blue": 0.98}
            reqs.append({"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1},
                "cell": {"userEnteredFormat": cell},
                "fields": "userEnteredFormat.textFormat.bold" + (
                    ",userEnteredFormat.backgroundColor" if shade else "")}})
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": reqs}).execute()
    return sid


# ============================================================================
#  CONVERSION JOURNEYS — the path to conversion, from first touch.
#
#  A "conversion" here is a DATA-BACKED seller-intent act we can see: an AYH
#  address submission, an off-market unlock ($ paid), or an off-market report
#  open. True selling conversations (phone calls) are logged MANUALLY on the
#  Engagements tab — when a person is named, they can be folded in here the same
#  way. These are intent proxies, not confirmed listings.
# ============================================================================
# type -> (display, priority) — the strongest conversion a person reached anchors them
CONV_PRIORITY = {
    "offmarket_unlock": ("$ off-market unlock", 4),
    "analyse_home_address_submit": ("★ AYH submit", 3),
    "offmarket_report_view": ("off-market report open", 1),
}


def build_conversion_journeys(sm):
    ints_set = set(INTERNAL_IDS)
    ints = ", ".join("'" + i.replace("'", "") + "'" for i in INTERNAL_IDS) or "''"
    conv: dict[str, dict[str, datetime]] = defaultdict(dict)
    rows = posthog_query(f"""
SELECT distinct_id, event, min(timestamp) AS t0
FROM events
WHERE event IN ('analyse_home_address_submit', 'offmarket_report_view')
  AND timestamp > now() - INTERVAL {HISTORY_DAYS} DAY
  AND distinct_id NOT IN ({ints})
  AND coalesce(properties.is_internal, '') != 'true'
GROUP BY distinct_id, event
""")
    for r in rows:
        ts = parse_ts(r[2])
        if ts:
            conv[r[0]][r[1]] = ts
    for o in sm.offmarket_orders.find(
            {"payment_status": {"$in": ["paid", "succeeded", "captured"]}},
            {"posthog_distinct_id": 1, "created_at": 1}):
        did = o.get("posthog_distinct_id")
        ts = parse_ts(o.get("created_at"))
        if did and ts:
            conv[did]["offmarket_unlock"] = ts
    conv = {d: v for d, v in conv.items() if d not in ints_set and v}
    if not conv:
        return {}, []

    persons = list(conv)
    by_person: dict[str, list[dict]] = defaultdict(list)
    CHUNK = 120
    for i in range(0, len(persons), CHUNK):
        chunk = persons[i:i + CHUNK]
        id_list = ", ".join("'" + d.replace("'", "") + "'" for d in chunk)
        hist = posthog_query(f"""
SELECT distinct_id, timestamp, event, properties.$pathname,
       properties.$referring_domain, properties.utm_source, properties.suburb
FROM events
WHERE distinct_id IN ({id_list})
  AND event IN ('$pageview','walkthrough_start','offmarket_report_view',
                'analyse_home_address_submit','address_search')
  AND timestamp > now() - INTERVAL {HISTORY_DAYS} DAY
ORDER BY distinct_id, timestamp ASC
LIMIT 50000
""")
        for r in hist:
            ts = parse_ts(r[1])
            if ts:
                by_person[r[0]].append({"ts": ts, "event": r[2], "path": r[3],
                                         "ref": r[4], "utm": r[5], "suburb": r[6]})

    idmap = build_identity_map(sm, set(persons))
    agg = {"first_channel": Counter(), "first_content": Counter(), "closing": Counter(),
           "by_type": Counter(), "days": [], "touches": []}
    journeys = []
    for did, ctypes in conv.items():
        atype = max(ctypes, key=lambda t: CONV_PRIORITY.get(t, ("", 0))[1])
        conv_ts = ctypes[atype]
        conv_label, prio = CONV_PRIORITY.get(atype, (atype, 0))
        agg["by_type"][conv_label] += 1
        evs = by_person.get(did) or []
        visits, cur = [], None
        for e in evs:
            if cur is None or (e["ts"] - cur[-1]["ts"]) > timedelta(minutes=RETURN_VISIT_GAP_MIN):
                cur = []
                visits.append(cur)
            cur.append(e)
        pre_vlist, post_visits = [], 0
        for v in visits:
            if v[0]["ts"] <= conv_ts + timedelta(seconds=1):
                touches = []
                for e in v:
                    if e["ts"] > conv_ts + timedelta(seconds=1):
                        break
                    t = chain_touch(e["event"], e["path"], e["suburb"])
                    if t and (not touches or touches[-1] != t):
                        touches.append(t)
                pre_vlist.append({"start": v[0]["ts"], "end": v[-1]["ts"], "touches": touches,
                                  "ch": channel_for(v[0]["ref"], v[0]["utm"])})
            else:
                post_visits += 1
        if not pre_vlist:
            continue
        first_ch = pre_vlist[0]["ch"]
        first_content = next((t for v in pre_vlist for t in v["touches"]), None)
        closing = next((t for v in reversed(pre_vlist) for t in reversed(v["touches"])), None)
        days = max((conv_ts - pre_vlist[0]["start"]).days, 0)
        touches_before = sum(len(v["touches"]) for v in pre_vlist)
        agg["first_channel"][first_ch] += 1
        if first_content:
            agg["first_content"][first_content] += 1
        if closing:
            agg["closing"][closing] += 1
        agg["days"].append(days)
        agg["touches"].append(touches_before)
        journeys.append({
            "who": idmap.get(did, f"Anon {did[:8]}"),
            "conv": f"{conv_label} · {conv_ts.astimezone(AEST):%d %b}",
            "conv_ts": conv_ts, "prio": prio,
            "first": f"{first_ch} · {first_content or '—'}",
            "days": days, "post": post_visits, "vlist": pre_vlist,
        })
    # deliberate conversions (unlock, AYH submit) first, then most recent — so the
    # softer off-market opens don't bury the people who actively raised their hand.
    journeys.sort(key=lambda j: (j["prio"], j["conv_ts"]), reverse=True)
    return agg, journeys


def write_conversion_tab(svc, ssid, agg, journeys, back_url):
    sid = ensure_plain_tab(svc, ssid, CONV_TAB)
    med = lambda xs: round(statistics.median(xs), 1) if xs else 0
    rows = [
        ["▸ CONVERSION — the path to conversion, from first touch"],
        [f'=HYPERLINK("{back_url}","← back to Engagements")'],
        ["A 'conversion' here = a data-backed seller-intent act we can see (AYH submit, off-market "
         "unlock, off-market open). True selling conversations (calls) are logged manually on "
         "Engagements — name the person and they can be added here. Intent proxies, not confirmed listings."],
        [],
        ["▸ CONVERSIONS BY TYPE (strongest per person; deliberate acts first)"],
    ]
    for v, n in agg.get("by_type", Counter()).most_common():
        rows.append([f"   ↳ {v}", n])
    rows += [
        [],
        ["▸ WHAT PRODUCES CONVERTERS (cohort aggregate)",
         f"median {med(agg.get('days', []))} days & {med(agg.get('touches', []))} touches to convert"],
        ["First touch — entry channel", "converters"],
    ]
    for v, n in agg.get("first_channel", Counter()).most_common(8):
        rows.append([f"   ↳ {v}", n])
    rows.append(["First touch — content (what starts them)", "converters"])
    for v, n in agg.get("first_content", Counter()).most_common(10):
        rows.append([f"   ↳ {v}", n])
    rows.append(["Closing content (last thing seen before converting)", "converters"])
    for v, n in agg.get("closing", Counter()).most_common(10):
        rows.append([f"   ↳ {v}", n])
    rows.append([])
    rows.append([f"▸ CONVERTER JOURNEYS — most recent first"
                 + (f" (top {MAX_JOURNEYS} of {len(journeys)})" if len(journeys) > MAX_JOURNEYS else "")])
    rows.append(["Who", "Converted", "First touch", "Days", "Path: first touch → conversion"])
    for j in journeys[:MAX_JOURNEYS]:
        chain = chain_string(j["vlist"])
        if j["post"]:
            chain += f"   [+{j['post']} visit(s) after]"
        rows.append([j["who"], j["conv"], j["first"], j["days"], chain])

    svc.spreadsheets().values().clear(spreadsheetId=ssid, range=f"'{CONV_TAB}'", body={}).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range=f"'{CONV_TAB}'!A1", valueInputOption="USER_ENTERED",
        body={"values": rows}).execute()
    reqs = [
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 220}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 1, "endIndex": 3}, "properties": {"pixelSize": 170}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 900}, "fields": "pixelSize"}},
        {"repeatCell": {"range": {"sheetId": sid, "startColumnIndex": 4, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
    ]
    for i, r in enumerate(rows):
        head = r[0] if r else ""
        if head.startswith("▸") or head == "Who":
            shade = head.startswith("▸")
            cell = {"textFormat": {"bold": True}}
            if shade:
                cell["backgroundColor"] = {"red": 0.90, "green": 0.93, "blue": 0.98}
            reqs.append({"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1},
                "cell": {"userEnteredFormat": cell},
                "fields": "userEnteredFormat.textFormat.bold" + (
                    ",userEnteredFormat.backgroundColor" if shade else "")}})
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": reqs}).execute()
    return sid


# ---- CRM per-week ------------------------------------------------------------
def crm_metrics(sm, weeks: list[date]) -> dict[str, dict[date, float]]:
    wset = set(weeks)
    m: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))

    # New contacts entering the CRM
    for c in sm.crm_contacts.find({}, {"created_at": 1, "ayh_home": 1}):
        wk = aest_monday(parse_ts(c.get("created_at")))
        if wk in wset:
            m["id_new_contacts"][wk] += 1
        ah = c.get("ayh_home") or {}
        if isinstance(ah, dict) and ah.get("at"):
            awk = aest_monday(parse_ts(ah.get("at")))
            if awk in wset:
                m["id_home_reco"][awk] += 1

    # NOTE: AYH submissions are counted from the PostHog `analyse_home_address_submit`
    # event (a deliberate on-site user action), NOT property_reports — that collection
    # also holds FB-lead reports, e2e/diagnostic tests and system-generated report shells,
    # so a naive per-week doc count wildly overstates real submissions (165 in one week).

    # Off-market unlocks (paid $15). Currently ~0 real — kept for when it fires.
    for o in sm.offmarket_orders.find({"status": {"$nin": ["test", None]}},
                                      {"created_at": 1, "payment_status": 1, "status": 1}):
        if str(o.get("payment_status")) not in ("paid", "succeeded", "captured"):
            continue
        wk = aest_monday(parse_ts(o.get("created_at")))
        if wk in wset:
            m["conv_offmarket_unlock"][wk] += 1

    return m


# ---- grid definition ---------------------------------------------------------
# (kind, label, metric_key). kind: section | computed | pct | manual | spacer
GRID = [
    ("section", "▸ REACH — people we reached (top of funnel · PSI)", None),
    ("computed", "Unique visitors", "reach_unique"),
    ("computed", "  · new (first seen this week)", "reach_new"),
    ("computed", "  · returning", "reach_returning"),
    ("spacer", "", None),

    ("section", "▸ ATTENTION — did they actually engage? (engaged reading time)", None),
    ("computed", "Bounce (<10s)", "att_bounce"),
    ("computed", "Skim (10–30s)", "att_skim"),
    ("computed", "Read (30s–2m)", "att_read"),
    ("computed", "Deep read (2–5m)", "att_deep"),
    ("computed", "Marathon (5m+ active)", "att_marathon"),
    ("spacer", "", None),

    ("section", "▸ VIDEO — on-site walkthroughs (/news, articles, /off-market)", None),
    ("computed", "Video shown (autostart — context, not intent)", "vid_plays"),
    ("computed", "  · reached 75%+  (real watch-depth)", "vid_deep"),
    ("computed", "  · completed", "vid_complete"),
    ("pct", "  · completion rate % (of shown)", "vid_completion_pct"),
    ("computed", "Returned to a video (PSR signal)", "vid_return"),
    ("spacer", "", None),

    ("section", "▸ RETURN — loyalty depth (the strongest early PSR signal)", None),
    ("computed", "1st week seen", "ret_1"),
    ("computed", "2nd week", "ret_2"),
    ("computed", "3rd–4th week", "ret_3_4"),
    ("computed", "5th+ week (regulars)", "ret_5p"),
    ("spacer", "", None),

    ("section", "▸ DEPTH — breadth & seriousness of consumption (PSR intensification)", None),
    ("computed", "Multi-page sessions (≥3 pages)", "depth_multipage"),
    ("computed", "Read market/editorial content (≥30s)", "depth_content_read"),
    ("pct", "Avg pages / session", "depth_avg_pages"),
    ("spacer", "", None),

    ("section", "▸ IDENTITY — we now know who they are (integration)", None),
    ("computed", "New CRM contact records", "id_new_contacts"),
    ("computed", "Home recognised (AYH self-typed)", "id_home_reco"),
    ("manual", "Two-way: DMs / replies / name-use  ⟵ manual", None),
    ("spacer", "", None),

    ("section", "▸ INTENT — trust transferring", None),
    ("computed", "Address searched", "intent_address_search"),
    ("computed", "Analyse-Your-Home submissions", "intent_ayh_submit"),
    ("computed", "Off-market report opens", "intent_offmarket_open"),
    ("manual", "Book-a-review / appraisal starts  ⟵ manual", None),
    ("spacer", "", None),

    ("section", "▸ CONVERSION & OUTCOME", None),
    ("manual", "★ Selling conversations started  ⟵ manual (THE conversion)", None),
    ("computed", "Off-market unlocks ($15 paid)", "conv_offmarket_unlock"),
    ("manual", "Form 6 signed  ⟵ manual (downstream outcome)", None),
    ("spacer", "", None),

    ("section", "▸ HEALTH — science guardrails (watch, don't maximise)", None),
    ("pct", "Median sessions/wk, returning visitors", "health_saturation"),
    ("manual", "CTA-heavy vs education content ratio  ⟵ manual", None),
    ("spacer", "", None),

    ("section", "▸ BY FUNNEL — entry channel (unique visitor sessions)", None),
    ("computed", "Facebook / IG", "fun_facebook"),
    ("computed", "Search (Google/Bing)", "fun_search"),
    ("computed", "Direct / internal", "fun_direct"),
    ("computed", "Other referral", "fun_other"),
]

MANUAL_KINDS = {"manual"}


# ---- sheet -------------------------------------------------------------------
def ensure_tab(svc, ssid):
    """Create the Engagements tab (front position) if absent; return sheetId."""
    sid = tab_id(svc, ssid, TAB)
    if sid is not None:
        # keep it at the front
        svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": sid, "index": 0},
                "fields": "index"}}]}).execute()
        return sid
    res = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
        "addSheet": {"properties": {"title": TAB, "index": 0, "gridProperties": {
            "rowCount": len(GRID) + 5, "columnCount": 70,
            "frozenRowCount": 1, "frozenColumnCount": 1}}}}]}).execute()
    sid = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"Created '{TAB}' tab at front.")
    return sid


def a1(row: int, col: int) -> str:
    """1-indexed (row, col) -> A1 like 'B3'."""
    s = ""
    c = col
    while c > 0:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return f"{s}{row}"


def fmt_val(kind: str, v: float | None):
    if v is None:
        return ""
    if kind == "pct":
        return v
    return int(v) if float(v).is_integer() else v


def read_manual_by_week(svc, ssid) -> dict[int, dict[str, str]]:
    """{grid_index -> {week_label -> hand-typed value}} from the current sheet.

    Manual cells (selling conversations, Form 6, ...) are keyed to their WEEK label, not
    their column position — because the grid renders newest-week-LEFT, so a given week
    slides one column right every week. Carrying values by week identity keeps Will's
    entries attached to the right week across that shift.
    """
    try:
        grid = svc.spreadsheets().values().get(
            spreadsheetId=ssid, range=f"'{TAB}'!A1:BZ{len(GRID) + 1}").execute().get("values", [])
    except Exception:  # noqa: BLE001 — tab may not exist yet
        return {}
    if not grid:
        return {}
    old_labels = grid[0][1:] if grid else []
    out: dict[int, dict[str, str]] = {}
    for i, (kind, _lbl, _key) in enumerate(GRID):
        if kind != "manual":
            continue
        r = grid[i + 1] if i + 1 < len(grid) else []
        cells = r[1:] if r else []
        vals = {}
        for j, lab in enumerate(old_labels):
            v = cells[j] if j < len(cells) else ""
            if str(v).strip():
                vals[lab] = v
        if vals:
            out[i] = vals
    return out


def write_grid(svc, ssid, sid, weeks: list[date],
               metrics: dict[str, dict[date, float]]):
    manual_prev = read_manual_by_week(svc, ssid)
    # Newest week on the LEFT (col B), oldest on the right — per Will 2026-09-13.
    render = list(reversed(weeks))
    labels = [week_label(w) for w in render]
    data = []
    # header row
    data.append({"range": f"'{TAB}'!A1",
                 "values": [["Metric ↓  /  ← newer   Week   older →"] + labels]})
    # rows
    for i, (kind, label, key) in enumerate(GRID):
        row = i + 2
        if kind in ("section", "spacer"):
            data.append({"range": f"'{TAB}'!{a1(row, 1)}", "values": [[label]]})
            continue
        if kind == "manual":
            # Carry Will's hand-typed values forward, keyed by week label so they follow
            # their week as columns shift right. A week he hasn't filled stays blank.
            prev = manual_prev.get(i, {})
            data.append({"range": f"'{TAB}'!{a1(row, 1)}",
                         "values": [[label] + [prev.get(lab, "") for lab in labels]]})
            continue
        vals = [label] + [fmt_val(kind, metrics.get(key, {}).get(w)) for w in render]
        data.append({"range": f"'{TAB}'!{a1(row, 1)}", "values": [vals]})

    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=ssid,
        body={"valueInputOption": "RAW", "data": data}).execute()

    # formatting: bold header, bold+shaded section rows, widen col A
    reqs = [
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 300}, "fields": "pixelSize"}},
    ]
    for i, (kind, label, key) in enumerate(GRID):
        if kind == "section":
            reqs.append({"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": i + 1, "endRowIndex": i + 2},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.90, "green": 0.93, "blue": 0.98}}},
                "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"}})
        elif kind == "manual":
            reqs.append({"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": i + 1, "endRowIndex": i + 2,
                          "startColumnIndex": 0, "endColumnIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"italic": True}}},
                "fields": "userEnteredFormat.textFormat.italic"}})
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": reqs}).execute()


def print_dry(weeks, metrics):
    show = list(reversed(weeks))[:6]   # newest first, matching the sheet
    hdr = "  ".join(week_label(w) for w in show)
    print(f"\n{'Metric':40} {hdr}")
    print("-" * (42 + len(hdr)))
    for kind, label, key in GRID:
        if kind in ("section", "spacer"):
            print(label)
            continue
        if kind == "manual":
            print(f"{label:40} {'(manual)':>8}")
            continue
        cells = "  ".join(f"{fmt_val(kind, metrics.get(key, {}).get(w)):>10}" for w in show)
        print(f"{label:40} {cells}")


def print_dry_attr(weeks, attr, whatwedid):
    show = list(reversed(weeks))[:6]
    for sec_name, _keys, title, specs in SECTIONS:
        print(f"\n{'='*70}\n{title}   [{sec_name}]\n{'='*70}")
        hdr = "  ".join(week_label(w) for w in show)
        print(f"{'':38} {hdr}")
        for mlabel, key, dims in specs:
            print(f"■ {mlabel}")
            mv = wow_mover((attr.get(key, {}) or {}).get("channel", {}), weeks)
            if mv:
                print(f"   ▸ {mv}")
            for dim in dims:
                vals = (attr.get(key, {}) or {}).get(dim, {})
                if not vals:
                    continue
                print(f"   {DIM_TITLE[dim]}:")
                ranked = sorted(vals.items(), key=lambda kv: -sum(kv[1].values()))
                for v, bw in ranked[:DIM_CAP.get(dim, 8)]:
                    cells = "  ".join(f"{fmt_num(bw.get(w)) or '':>10}" for w in show)
                    print(f"      ↳ {v[:34]:34} {cells}")
    print(f"\n{'='*70}\nWHAT WE DID\n{'='*70}")
    for w in show:
        wd = whatwedid.get(w, {})
        print(f"{week_label(w)}: spend ${round(wd.get('spend',0))}, "
              f"{wd.get('launched',0)}L/{wd.get('paused',0)}P/{wd.get('changed',0)}C ads, "
              f"{len(wd.get('articles',[]))} articles, {wd.get('posts',0)} posts, "
              f"{len(wd.get('deploys',[]))} deploys")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="drop the tab and rewrite layout from scratch (loses manual cells)")
    args = ap.parse_args()

    set_env_from_file()
    client = get_client()
    sm = client["system_monitor"]

    try:
        with job_run("engagement_funnel_to_sheet", cadence_hours=24,
                     title="Weekly Engagement Funnel → Live Leads Tracker") as beat:
            weeks = week_list()
            # lookback covers the whole grid + a day of overlap
            hours = (datetime.now(timezone.utc).date() - weeks[0]).days * 24 + 48
            events = fetch_events(hours)

            # 7b: an empty on-site event pull over weeks of expected traffic is a
            # broken PostHog query, not a quiet week. Fail loudly, don't write zeros.
            if not events:
                raise RuntimeError(
                    f"PostHog returned 0 events over {hours}h — refusing to overwrite "
                    "the grid with zeros (query/creds broken, not a quiet week).")

            metrics, sessions, person_weeks = build_metrics(events, weeks)
            for k, d in crm_metrics(sm, weeks).items():
                metrics[k] = d

            attr, person_first_channel = build_attribution(events, weeks, sessions, person_weeks)
            for k, dims in crm_attribution(sm, weeks, person_first_channel).items():
                attr[k] = dims
            whatwedid = what_we_did(sm, weeks)

            returners = [p for p, ws in person_weeks.items() if len(ws) >= 2]
            ret_agg, ret_journeys = build_return_journeys(sm, returners)
            conv_agg, conv_journeys = build_conversion_journeys(sm)

            total_sessions = sum(metrics["_att_total"].values())
            beat.detail = f"{len(weeks)} weeks, {len(events)} events, {int(total_sessions)} sessions"
            beat.metrics = {"weeks": len(weeks), "events": len(events),
                            "sessions": int(total_sessions),
                            "attributed_metrics": len(attr)}

            if args.dry_run:
                print_dry(weeks, metrics)
                print_dry_attr(weeks, attr, whatwedid)
                print(f"\n{'='*70}\n{RETURN_TAB}: {len(ret_journeys)} returner journeys "
                      f"(of {len(returners)} multi-week persons)\n{'='*70}")
                for j in ret_journeys[:8]:
                    print(f"{j['who'][:26]:26} {j['first'][:28]:28} v{j['visits']} "
                          f"w{j['wks']} | {chain_string(j['vlist'])[:110]}")
                if ret_agg.get("trigger"):
                    print("top return triggers:", ret_agg["trigger"].most_common(5))
                print(f"\n{'='*70}\n{CONV_TAB}: {len(conv_journeys)} converter journeys\n{'='*70}")
                for j in conv_journeys[:8]:
                    print(f"{j['who'][:26]:26} {j['conv'][:24]:24} {j['days']}d "
                          f"| {chain_string(j['vlist'])[:110]}")
                if conv_agg.get("closing"):
                    print("top closing content:", conv_agg["closing"].most_common(5))
                return

            svc = get_sheets()
            if args.rebuild:
                for t in [TAB, RETURN_TAB, CONV_TAB] + [title for _s, _k, title, _sp in SECTIONS]:
                    old = tab_id(svc, args.spreadsheet_id, t)
                    if old is not None:
                        svc.spreadsheets().batchUpdate(
                            spreadsheetId=args.spreadsheet_id,
                            body={"requests": [{"deleteSheet": {"sheetId": old}}]}).execute()
                print(f"[rebuild] dropped '{TAB}' + section tabs.")
            sid = ensure_tab(svc, args.spreadsheet_id)
            write_grid(svc, args.spreadsheet_id, sid, weeks, metrics)
            gids = write_section_tabs(svc, args.spreadsheet_id, weeks, metrics, attr, whatwedid)
            base = f"https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit"
            back = f"{base}#gid={sid}"
            gids[RETURN_TAB] = write_return_tab(svc, args.spreadsheet_id, ret_agg, ret_journeys, back)
            gids[CONV_TAB] = write_conversion_tab(svc, args.spreadsheet_id, conv_agg, conv_journeys, back)
            link_engagement_cells(svc, args.spreadsheet_id, gids)
            print(f"Done. '{TAB}' + {len(gids)} attribution tabs updated — {len(weeks)} weeks; "
                  f"{len(ret_journeys)} returner + {len(conv_journeys)} converter journeys.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
