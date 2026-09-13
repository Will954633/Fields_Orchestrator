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
from collections import defaultdict
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
       properties.$geoip_city_name, properties.pct
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
            "city": r[8], "pct": r[9],
        })
    return out


def build_metrics(events: list[dict], weeks: list[date]) -> dict[str, dict[date, float]]:
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
            s = sessions[sid] = {"person": person, "week": wk, "first_ts": e["ts"],
                                 "max_eng": 0.0, "pages": set(), "content_read": False,
                                 "ref": e["ref"], "utm": e["utm"]}
        if e["ts"] < s["first_ts"]:
            s["first_ts"] = e["ts"]
            s["ref"], s["utm"] = e["ref"], e["utm"]   # entry attribution = first hit
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

    return m


def channel_bucket(ref, utm) -> str:
    c = channel_for(ref, utm)
    return {"Facebook / IG": "facebook", "Search": "search",
            "Direct / internal-ref": "direct", "Other referral": "other"}[c]


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

            metrics = build_metrics(events, weeks)
            for k, d in crm_metrics(sm, weeks).items():
                metrics[k] = d

            total_sessions = sum(metrics["_att_total"].values())
            beat.detail = f"{len(weeks)} weeks, {len(events)} events, {int(total_sessions)} sessions"
            beat.metrics = {"weeks": len(weeks), "events": len(events),
                            "sessions": int(total_sessions)}

            if args.dry_run:
                print_dry(weeks, metrics)
                return

            svc = get_sheets()
            if args.rebuild:
                old = tab_id(svc, args.spreadsheet_id, TAB)
                if old is not None:
                    svc.spreadsheets().batchUpdate(
                        spreadsheetId=args.spreadsheet_id,
                        body={"requests": [{"deleteSheet": {"sheetId": old}}]}).execute()
                    print(f"[rebuild] dropped '{TAB}'.")
            sid = ensure_tab(svc, args.spreadsheet_id)
            write_grid(svc, args.spreadsheet_id, sid, weeks, metrics)
            print(f"Done. '{TAB}' updated — {len(weeks)} week columns.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
