#!/usr/bin/env python3
"""
Log KNOWN-CONTACT site activity to the "Activity" tab of the Live Leads Tracker.

The gap this closes
-------------------
crm_sync.py already reconstructs a per-visitor journey from PostHog every hour and
stores it on system_monitor.crm_contacts (journey.page_sequence, probable_address,
offmarket_home, ...). live_leads_to_sheet.py already writes the "All Leads" roster.
But nothing ever noticed "a person we can actually REACH came back and read X" —
`returning` was only ever a static tag (crm_sync.py:318), and the All Leads tab is
insert-once-per-lead, so a repeat visit produced no row and changed nothing.

This script is that missing middle. Every run it:
  1. builds the set of contacts we have a communication pathway to (email / phone /
     a postal address — confirmed, submitted, or inferred) AND a PostHog id;
  2. pulls their raw events from PostHog for the lookback window;
  3. splits each person's events into visits (>30 min gap = a new visit);
  4. keeps visits where the contact was ALREADY KNOWN to us before the visit began
     (that is the business definition of "returning" — it also catches an FB lead-ad
     contact browsing the site for the first time, which matters just as much);
  5. writes one verbose row per visit to the "Activity" tab.

It deliberately does NOT message anyone. There is no newsletter/mailer/SMS system
yet (system_monitor.subscribers has never been sent anything). The point is a
durable, legible activity ledger that a later trigger can be built on top of.

Honesty rules this script follows (they matter — Will acts on these rows)
------------------------------------------------------------------------
  * Engaged time comes from max(time_on_page.duration), NOT last-event-minus-first.
    The time_on_page milestones fire at 10/30/60/120/300s of ACTIVE time and stop at
    300, so a tab left open for 40 minutes must never be reported as 40 minutes of
    reading. Wall-clock span is reported separately and labelled as such.
  * Every postal address says where it came from. "owner-confirmed" and "inferred
    from an off-market lookup" are very different things to act on, so the Reach Via
    column always carries the provenance rather than implying we were given it.
  * "Already sent" is read from real send records (crm_contacts.communications +
    system_monitor.email_sends), so "nothing sent yet" is a fact, not an assumption.
  * The Opportunity column is deterministic rules over what they actually read — no
    LLM call (agents are off, and it must stay cheap + reproducible).

Dedupe: system_monitor.engagement_activity_ledger, keyed by "<contact_id>:<visit
start>". Rows are inserted at the TOP (newest first) exactly like live_leads_to_sheet
so manual edits and formatting shift down intact. A row deleted by hand is never
resurrected.

Usage:
  python3 scripts/engagement_activity_to_sheet.py --dry-run
  python3 scripts/engagement_activity_to_sheet.py
  python3 scripts/engagement_activity_to_sheet.py --hours 168   # backfill a week
  python3 scripts/engagement_activity_to_sheet.py --include-first-visit
"""
from __future__ import annotations
import argparse
import os
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_client
from crm_sync import posthog_query, INTERNAL_IDS, BOT_CITIES
from job_status import job_run
from live_leads_to_sheet import (
    LIVE_SPREADSHEET_ID, get_sheets, tab_id, set_env_from_file, AEST,
)

TAB = "Activity"
LEDGER_DB = "system_monitor"
LEDGER_COLL = "engagement_activity_ledger"

# A gap this long between two events means they left and came back.
VISIT_GAP_MIN = 30
# time_on_page milestones stop at 300s, so this is the ceiling of what we can honestly
# claim as engaged reading time on a single page.
ENGAGED_CAP_S = 300

HEADERS = ["Date", "Time (AEST)", "Who", "Reach Via", "Contact Detail", "Visit",
           "Channel", "Location", "Engaged", "What They Did", "Already Sent",
           "Opportunity", "Activity ID"]
ACTIVITY_ID_COL = 12  # 0-indexed -> column M (hidden, dedupe key only)

CATEGORY_LABELS = {
    "crash-risk": "crash risk",
    "sell-now": "should I sell now",
    "buy": "is it a good time to buy",
    "overview": "market overview",
    "direction": "where the market is heading",
    "suburb-compare": "suburb comparison",
    "houses-vs-units": "houses vs units",
}

# What each thing they read implies, and what we could send. Deterministic — first
# match in this order wins, so the strongest seller signal beats a general read.
OPPORTUNITY_RULES = [
    ("own_minisite", "They re-opened their OWN home report. Strongest signal here — "
                     "offer the printed appraisal / a call about their place."),
    ("sell-now", "Actively weighing whether to sell. Highest-value follow-up: an "
                 "appraisal for their address and current buyer-demand data."),
    ("crash-risk", "Reading crash-risk data. Send the crash-risk explainer/video for "
                   "this suburb — answers the question they came with."),
    ("direction", "Reading where the market is heading. Send the market-direction "
                  "breakdown / latest Market Pulse for this suburb."),
    ("offmarket", "Looking up a specific address off-market. Send that property's "
                  "off-market report, or ask if it's their own home."),
    ("other_minisite", "Looking at OTHER homes' reports, not their own — researching "
                       "neighbours/comparables. Send comparable-sales data for the area."),
    ("valuation", "Looking at valuation/comparables. Send the comparable-sales range "
                  "for their address."),
    ("buy", "Buyer-side reading. Send the Five Property Friday shortlist."),
    ("suburb-compare", "Comparing suburbs. Send the suburb-comparison data."),
    ("houses-vs-units", "Comparing houses vs units. Send that breakdown."),
    ("overview", "General market reading for this suburb. Send the latest Market "
                 "Pulse summary."),
    ("for_sale", "Browsing live listings. Worth asking what they're looking for."),
    ("article", "Reading our articles. Newsletter candidate once we have a mailer."),
]


# ---- pathway resolution ------------------------------------------------------
def reach_for(c: dict) -> tuple[str, str] | None:
    """Return (how we can reach them, the actual detail) or None.

    Ordered by how directly actionable it is. Every postal address states its
    provenance — an address the owner confirmed and an address we inferred from an
    off-market page lookup are completely different things to act on, and a row that
    blurs them would invite contacting someone as if they'd given us their details.
    """
    email = (c.get("email") or "").strip()
    if email:
        return "Email", email
    phone = (c.get("phone") or "").strip()
    if phone:
        return "Phone", phone

    hc = c.get("home_confirmed") or {}
    if isinstance(hc, dict) and hc.get("address"):
        return "Postal address (owner-confirmed)", hc["address"]

    pa = (c.get("property_address") or "").strip()
    if pa:
        return "Postal address (they submitted it)", pa

    prob = (c.get("probable_address") or "").strip()
    if prob:
        src = c.get("probable_address_source") or "site activity"
        return f"Postal address (inferred — {src}, not given to us)", prob

    om = c.get("offmarket_home") or {}
    if isinstance(om, dict) and (om.get("address") or om.get("slug")):
        # Prefer the slug — offmarket_home.address is stored unpunctuated
        # ("13 4 Yodelay Street Varsity Lakes"), which is not a postable address.
        addr = slug_to_address(om["slug"]) if om.get("slug") else om["address"]
        return ("Postal address (inferred — off-market lookup, not given to us)", addr)
    return None


def who_for(c: dict, reach_detail: str) -> str:
    name = (c.get("name") or "").strip()
    if name:
        return name
    email = (c.get("email") or "").strip()
    if email:
        return email
    return f"Anonymous — known by address: {reach_detail}"


def already_sent(c: dict, db) -> str:
    """What we have actually sent this person, from real send records."""
    out = []
    for comm in (c.get("communications") or []):
        d = str(comm.get("date") or "")[:10]
        subj = (comm.get("subject") or comm.get("type") or "").strip()
        if subj:
            out.append(f"{d} {subj}")
    email = (c.get("email") or "").strip().lower()
    if email:
        for s in db.email_sends.find({"to": {"$regex": f"^{email}$", "$options": "i"}}):
            d = str(s.get("sent_at") or "")[:10]
            out.append(f"{d} {s.get('subject') or s.get('type') or 'email'}")
    if not out:
        return "Nothing sent to them yet."
    seen, uniq = set(), []
    for o in out:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    return f"{len(uniq)} sent — " + "; ".join(uniq[-4:])


# ---- page labelling ----------------------------------------------------------
KNOWN_SUBURBS = ["burleigh-waters", "varsity-lakes", "robina", "burleigh-heads",
                 "mermaid-waters", "merrimac", "worongary", "clear-island-waters"]


def slug_to_address(slug: str) -> str:
    """'44-28-castello-circuit-varsity-lakes' -> '44/28 Castello Circuit, Varsity Lakes'.

    Splits the suburb off the tail and restores the unit separator, so a row reads as
    a real address rather than a slug with the punctuation stripped out.
    """
    s = (slug or "").strip("-")
    if not s:
        return "—"
    suburb = ""
    for k in KNOWN_SUBURBS:
        if s.endswith("-" + k):
            suburb = k.replace("-", " ").title()
            s = s[: -len(k) - 1]
            break
    parts = s.split("-")
    # leading "<unit>-<street no>" pair -> "unit/number"
    if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
        parts = [f"{parts[0]}/{parts[1]}"] + parts[2:]
    street = " ".join(w.capitalize() for w in parts)
    return f"{street}, {suburb}" if suburb else street


def own_slugs_for(c: dict) -> set[str]:
    """Every address slug we believe belongs to THIS contact.

    Needed so a home report they opened is only ever called "their own" when it
    actually is theirs — they also browse neighbours' and comparables' reports, and
    a row telling Will "they re-opened their own home report" when they didn't would
    send him into a conversation on a false premise.
    """
    out = set()
    for k in ("probable_address_slug",):
        if c.get(k):
            out.add(c[k])
    hc = c.get("home_confirmed") or {}
    if isinstance(hc, dict) and hc.get("slug"):
        out.add(hc["slug"])
    om = c.get("offmarket_home") or {}
    if isinstance(om, dict):
        if om.get("slug"):
            out.add(om["slug"])
        out.update(om.get("slugs") or [])
    return {s for s in out if s}


def describe_path(path: str, category: str | None, suburb: str | None,
                  own: set[str] | None = None) -> tuple[str, str]:
    """(human label, rule tag) for one page path. `own` = this contact's own slugs."""
    own = own or set()
    p = (path or "").rstrip("/") or "/"
    parts = [x for x in p.split("/") if x]

    def minisite(slug: str, verb: str) -> tuple[str, str]:
        addr = slug_to_address(slug)
        if slug in own:
            return f"{verb} their OWN home report ({addr})", "own_minisite"
        return f"{verb} a home report for {addr} (not their own)", "other_minisite"

    if p == "/" or (parts and parts[0] == "news"):
        return "News & Research home", "article"
    if parts and parts[0] in ("market-intelligence", "market-metrics"):
        sub = (suburb or (parts[1].replace("-", " ") if len(parts) > 1 else "")).title()
        cat = category or (parts[2] if len(parts) > 2 else "overview")
        return f"{sub} market data — {CATEGORY_LABELS.get(cat, cat)}", cat
    if parts and parts[0] == "your-home":
        if len(parts) > 2 and parts[1] == "building":
            return minisite(parts[2], "waiting on")
        if len(parts) > 1:
            return minisite(parts[1], "opened")
        return "a home report", "other_minisite"
    if parts and parts[0] == "building":
        # interim "we're building it" page (see memory listed_vs_offmarket_guard)
        return minisite(parts[1], "waiting on") if len(parts) > 1 else ("a report being built", "other_minisite")
    if parts and parts[0] == "analyse-your-home":
        if len(parts) > 2 and parts[1] == "building":
            return minisite(parts[2], "waiting on")
        return "Analyse Your Home", "valuation"
    if parts and parts[0] == "off-market":
        if len(parts) > 1:
            addr = slug_to_address(parts[1])
            own_note = " — their OWN address" if parts[1] in own else ""
            return f"off-market report for {addr}{own_note}", "offmarket"
        return "off-market report", "offmarket"
    if parts and parts[0] == "property":
        # /property/<slug> — name the actual listing; "a for-sale listing" twice in a
        # row tells Will nothing he can act on.
        return (f"for-sale listing: {slug_to_address(parts[1])}" if len(parts) > 1
                else "a for-sale listing"), "for_sale"
    if parts and parts[0].startswith("for-sale"):
        return "for-sale listings", "for_sale"
    if parts and parts[0] == "articles":
        return f"article: {slug_to_address(parts[1]) if len(parts) > 1 else '—'}", "article"
    if parts and parts[0] == "discover":
        return "Discover feed", "for_sale"
    return p, ""


def channel_for(ref_domain: str | None, utm_source: str | None) -> str:
    if utm_source:
        return f"utm_source={utm_source}"
    rd = (ref_domain or "").lower()
    if not rd or rd == "$direct":
        return "Direct / no referrer"
    if "google" in rd:
        return "Google organic"
    if "facebook" in rd or "fb" == rd:
        return "Facebook"
    if "bing" in rd:
        return "Bing organic"
    if "fieldsestate" in rd:
        return "Internal"
    return rd


def fmt_engaged(engaged_s: int, span_s: int) -> str:
    """Engaged reading time, with the wall-clock span alongside and clearly labelled.

    Never conflate the two: time_on_page milestones cap at 300s of ACTIVE time, so a
    tab left open for 40 minutes is 5 min of reading, not 40.
    """
    if engaged_s <= 0:
        return f"<10s measured (page span {span_s // 60}m)" if span_s >= 60 else "<10s measured"
    cap = "+" if engaged_s >= ENGAGED_CAP_S else ""
    eng = f"{engaged_s // 60}m{cap}" if engaged_s >= 60 else f"{engaged_s}s{cap}"
    if span_s >= engaged_s + 120:
        return f"{eng} engaged (tab open {span_s // 60}m)"
    return f"{eng} engaged"


# ---- visit assembly ----------------------------------------------------------
def build_visits(events: list[dict]) -> list[dict]:
    """Split one person's ordered events into visits (>VISIT_GAP_MIN gap = new visit)."""
    visits, cur = [], None
    for e in events:
        if cur is None or (e["ts"] - cur["end"]) > timedelta(minutes=VISIT_GAP_MIN):
            cur = {"start": e["ts"], "end": e["ts"], "events": []}
            visits.append(cur)
        cur["end"] = e["ts"]
        cur["events"].append(e)
    return visits


def summarise_visit(v: dict, own: set[str]) -> dict:
    """Collapse a visit's events into ordered pages with engaged time + rule tags."""
    pages, order = {}, []
    for e in v["events"]:
        path = e["path"] or "/"
        if path not in pages:
            label, tag = describe_path(path, e.get("category"), e.get("suburb"), own)
            pages[path] = {"label": label, "tag": tag, "engaged": 0,
                           "first": e["ts"], "last": e["ts"]}
            order.append(path)
        p = pages[path]
        p["last"] = e["ts"]
        if e["event"] == "time_on_page" and e.get("duration"):
            p["engaged"] = max(p["engaged"], int(e["duration"]))
    ref = next((e.get("ref_domain") for e in v["events"] if e.get("ref_domain")), None)
    utm = next((e.get("utm_source") for e in v["events"] if e.get("utm_source")), None)
    city = next((e.get("city") for e in v["events"] if e.get("city")), "")
    country = next((e.get("country") for e in v["events"] if e.get("country")), "")
    return {
        "pages": [dict(pages[p], path=p) for p in order],
        "channel": channel_for(ref, utm),
        "location": ", ".join(x for x in (city, country) if x) or "Unknown",
        "start": v["start"], "end": v["end"],
    }


def narrative(c: dict, s: dict, prior_days: int, first_seen: str, reach: tuple[str, str]) -> str:
    """The verbose, plain-English line Will actually reads."""
    bits = []
    # Counted in DAYS, not visits — PostHog gives us visit_dates, and two sessions on
    # one day must not be reported as two separate "visits".
    if first_seen:
        d = f"active on {prior_days} earlier day(s), first seen {first_seen}" if prior_days \
            else f"known to us since {first_seen}"
        bits.append(f"Returning visitor — {d}. Arrived via {s['channel']}, from {s['location']}.")
    else:
        bits.append(f"First recorded visit. Arrived via {s['channel']}, from {s['location']}.")

    n = len(s["pages"])
    bits.append(f"Viewed {n} page{'s' if n != 1 else ''}:")
    for p in s["pages"]:
        span = int((p["last"] - p["first"]).total_seconds())
        bits.append(f"  • {p['label']} — {fmt_engaged(p['engaged'], span)}")

    deep = [p for p in s["pages"] if p["engaged"] >= 120]
    if deep:
        bits.append("Read " + " and ".join(f"“{p['label']}”" for p in deep[:2]) +
                    " properly, not a bounce.")
    how, detail = reach
    bits.append(f"Reachable by — {how}: {detail}")
    return "\n".join(bits)


def opportunity(s: dict, c: dict) -> str:
    tags = {p["tag"] for p in s["pages"]}
    for tag, text in OPPORTUNITY_RULES:
        if tag in tags:
            return text
    return "General site activity — no specific content match."


# ---- gather ------------------------------------------------------------------
def reachable_contacts(db) -> dict[str, dict]:
    """distinct_id -> contact doc, for every contact we can actually reach."""
    out = {}
    for c in db.crm_contacts.find({}):
        if not reach_for(c):
            continue
        ids = list(c.get("posthog_ids") or [])
        if c.get("primary_posthog_id"):
            ids.append(c["primary_posthog_id"])
        for i in ids:
            if i and i not in INTERNAL_IDS:
                out[i] = c
    return out


def fetch_events(dids: list[str], hours: int) -> dict[str, list[dict]]:
    """Raw PostHog events per distinct_id for the lookback window, oldest first."""
    by_person: dict[str, list[dict]] = {}
    CHUNK = 150  # keep the IN(...) clause a sane size
    for i in range(0, len(dids), CHUNK):
        chunk = dids[i:i + CHUNK]
        id_list = ", ".join("'" + d.replace("'", "") + "'" for d in chunk)
        bots = ", ".join("'" + b + "'" for b in BOT_CITIES)
        rows = posthog_query(f"""
SELECT distinct_id, timestamp, event, properties.$pathname, properties.duration,
       properties.category, properties.suburb, properties.$referring_domain,
       properties.utm_source, properties.$geoip_city_name, properties.$geoip_country_name
FROM events
WHERE distinct_id IN ({id_list})
  AND timestamp > now() - INTERVAL {int(hours)} HOUR
  AND (properties.$geoip_city_name IS NULL OR properties.$geoip_city_name NOT IN ({bots}))
ORDER BY distinct_id, timestamp ASC
LIMIT 50000
""")
        for r in rows:
            ts = r[1]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            by_person.setdefault(r[0], []).append({
                "ts": ts, "event": r[2], "path": r[3], "duration": r[4],
                "category": r[5], "suburb": r[6], "ref_domain": r[7],
                "utm_source": r[8], "city": r[9], "country": r[10],
            })
    return by_person


def known_before(c: dict, when: datetime) -> str | None:
    """Was this contact already known to us before this visit? Returns the date we
    first knew them, or None. Covers both a repeat site visitor and an FB lead-ad
    contact browsing the site for the first time — both are 'returning' to us."""
    cands = []
    for k in ("first_seen", "created_at"):
        v = c.get(k)
        if v:
            cands.append(str(v)[:10])
    for d in ((c.get("journey") or {}).get("visit_dates") or []):
        cands.append(str(d)[:10])
    cands = [d for d in cands if d and d < when.astimezone(AEST).strftime("%Y-%m-%d")]
    return min(cands) if cands else None


def build_rows(db, hours: int, include_first: bool) -> list[dict]:
    contacts = reachable_contacts(db)
    if not contacts:
        return []
    events = fetch_events(sorted(contacts), hours)
    rows = []
    for did, evs in events.items():
        c = contacts[did]
        cid = str(c.get("_id"))
        own = own_slugs_for(c)
        for v in build_visits(sorted(evs, key=lambda e: e["ts"])):
            first_seen = known_before(c, v["start"])
            if not first_seen and not include_first:
                continue
            # Earlier days only — a same-day earlier session isn't an "earlier day".
            vday = v["start"].astimezone(AEST).strftime("%Y-%m-%d")
            prior_dates = len({str(d)[:10] for d in
                               ((c.get("journey") or {}).get("visit_dates") or [])
                               if str(d)[:10] < vday})
            s = summarise_visit(v, own)
            local = v["start"].astimezone(AEST)
            reach = reach_for(c)
            rows.append({
                "activity_id": f"{cid}:{v['start'].isoformat()}",
                "date": local.strftime("%Y-%m-%d"),
                "time": local.strftime("%H:%M"),
                "who": who_for(c, reach[1]),
                "reach_via": reach[0],
                "contact_detail": reach[1],
                "visit": f"{prior_dates} earlier day(s)" if first_seen else "first visit",
                "channel": s["channel"],
                "location": s["location"],
                "engaged": fmt_engaged(max((p["engaged"] for p in s["pages"]), default=0),
                                       int((v["end"] - v["start"]).total_seconds())),
                "what": narrative(c, s, prior_dates, first_seen, reach),
                "already_sent": already_sent(c, db),
                "opportunity": opportunity(s, c),
                "_sort": v["start"],
            })
    rows.sort(key=lambda r: r["_sort"])
    return rows


def row_values(r: dict) -> list[str]:
    return [r["date"], r["time"], r["who"], r["reach_via"], r["contact_detail"],
            r["visit"], r["channel"], r["location"], r["engaged"], r["what"],
            r["already_sent"], r["opportunity"], r["activity_id"]]


# ---- sheet -------------------------------------------------------------------
def ensure_tab(svc, ssid):
    sid = tab_id(svc, ssid, TAB)
    if sid is not None:
        return sid
    res = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
        "addSheet": {"properties": {"title": TAB, "gridProperties": {
            "rowCount": 2000, "columnCount": len(HEADERS), "frozenRowCount": 1}}}}]}).execute()
    sid = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range=f"'{TAB}'!A1", valueInputOption="RAW",
        body={"values": [HEADERS]}).execute()
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": ACTIVITY_ID_COL, "endIndex": ACTIVITY_ID_COL + 1},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
        # "What They Did" is a multi-line narrative — it must wrap, or the row is unreadable.
        {"repeatCell": {
            "range": {"sheetId": sid, "startColumnIndex": 9, "endColumnIndex": 12},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                           "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": 9, "endIndex": 10},
            "properties": {"pixelSize": 520}, "fields": "pixelSize"}},
    ]}).execute()
    print(f"Created '{TAB}' tab.")
    return sid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--hours", type=int, default=26,
                    help="PostHog lookback (default 26 — nightly with overlap)")
    ap.add_argument("--include-first-visit", action="store_true",
                    help="also log visits by contacts we only met during this visit")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    set_env_from_file()
    client = get_client()
    db = client["system_monitor"]

    with job_run("engagement_activity_to_sheet", cadence_hours=24,
                 title="Known-Contact Activity → Live Leads Tracker") as beat:
        rows = build_rows(db, args.hours, args.include_first_visit)
        seen = {d["_id"] for d in db[LEDGER_COLL].find({}, {"_id": 1})}
        new = [r for r in rows if r["activity_id"] not in seen]

        print(f"{len(rows)} visit(s) by reachable contacts in the last {args.hours}h; "
              f"{len(new)} not yet logged.")
        for r in new:
            print(f"\n--- {r['date']} {r['time']}  {r['who']}")
            print(f"    reach: {r['reach_via']} -> {r['contact_detail']}")
            print("    " + r["what"].replace("\n", "\n    "))
            print(f"    opportunity: {r['opportunity']}")

        beat.detail = f"{len(new)} new activity row(s)"
        beat.metrics = {"visits_seen": len(rows), "rows_added": 0 if args.dry_run else len(new)}

        if args.dry_run or not new:
            client.close()
            return

        svc = get_sheets()
        sid = ensure_tab(svc, args.spreadsheet_id)
        # Newest FIRST: the whole batch is written downward from row 2 in one update,
        # so the first element of the list is the row that ends up directly under the
        # header. (Sorting ascending here would bury today's activity at the bottom.)
        new.sort(key=lambda r: r["_sort"], reverse=True)
        svc.spreadsheets().batchUpdate(spreadsheetId=args.spreadsheet_id, body={"requests": [{
            "insertDimension": {
                "range": {"sheetId": sid, "dimension": "ROWS",
                          "startIndex": 1, "endIndex": 1 + len(new)},
                "inheritFromBefore": False}}]}).execute()
        svc.spreadsheets().values().update(
            spreadsheetId=args.spreadsheet_id, range=f"'{TAB}'!A2",
            valueInputOption="RAW", body={"values": [row_values(r) for r in new]}).execute()

        ts = datetime.now(AEST).isoformat()
        for r in new:
            db[LEDGER_COLL].update_one({"_id": r["activity_id"]},
                                       {"$setOnInsert": {"logged_at": ts,
                                                         "date": r["date"],
                                                         "who": r["who"]}}, upsert=True)
        beat.metrics = {"visits_seen": len(rows), "rows_added": len(new)}
        client.close()
        print(f"\nDone. {len(new)} row(s) added to '{TAB}'.")


if __name__ == "__main__":
    main()
