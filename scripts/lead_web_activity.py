#!/usr/bin/env python3
"""
lead_web_activity.py — pull each identity-bound LEAD's on-site journey onto their
crm_contact, so the website activity behind a lead is durable (PostHog retains
events only ~a rolling window; the CRM is forever).

The join key is `crm_contacts.lead_web.posthog_distinct_id`, written by
lead-link-visit.mjs when a lead clicks their tokenised SMS/email link (the parked
"lead-token identity join", now live). This reads that key and queries PostHog for
the visitor's pageviews — a targeted, INDEXED `distinct_id IN (...)` query, which
returns fast, unlike the `person.properties.email` full scan that 504s. Result is
stored as `lead_web.activity` and a one-line `lead_web.summary`.

Runs nightly as a step of nightly_lead_chain.py (after crm_sync). Heartbeat
`lead_web_activity` with a Rule-7b assertion: leads are bound but zero produced
activity => the PostHog query is broken, not the leads idle.

Usage:
  python3 scripts/lead_web_activity.py --dry-run
  python3 scripts/lead_web_activity.py
"""
import os
import sys
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_client                 # noqa: E402
from crm_sync import posthog_query               # noqa: E402 (hardened retry/limit helper)
from job_status import job_run                   # noqa: E402


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(s):
    """PostHog timestamps -> aware datetime. Tolerates 'Z', '+00:00', and fractional secs."""
    if not s or s == "None":
        return None
    s = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s.split(".")[0] + "+00:00")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# Events that build the reverse-chronological timeline + the article/CTA read signals.
# All already emitted client-side (posthog.ts / ArticlePage / OffMarketV5) — no new
# instrumentation. page_engagement carries the truth for "did they read it":
# engaged_seconds + wall_seconds + max_depth_pct, fired on unmount.
TIMELINE_EVENTS = ("$pageview", "page_engagement", "article_cta_click",
                   "offmarket_market_article_open", "offmarket_market_article_read")


def fetch_timeline(all_ids):
    """Chronological events per distinct_id — the raw material for the timeline, per-page
    dwell, and the article-read / market-update-CTA signals. One indexed query."""
    if not all_ids:
        return {}
    idlist = "','".join(i.replace("'", "") for i in all_ids)
    evs = ("'" + "','".join(TIMELINE_EVENTS) + "'")
    rows = posthog_query(f"""
        SELECT distinct_id, timestamp, event,
               properties.$pathname       AS path,
               properties.engaged_seconds  AS engaged,
               properties.wall_seconds     AS wall,
               properties.max_depth_pct    AS depth,
               properties.article_title    AS atitle,
               properties.source           AS src,
               properties.destination      AS dest,
               properties.page             AS pg,
               properties.kind             AS kind
        FROM events
        WHERE distinct_id IN ('{idlist}') AND event IN ({evs})
        ORDER BY distinct_id, timestamp
    """)
    by_id = {}
    for r in rows:
        by_id.setdefault(r[0], []).append({
            "ts": _parse_ts(r[1]), "event": r[2], "path": r[3],
            "engaged": _num(r[4]), "wall": _num(r[5]), "depth": _num(r[6]),
            "atitle": r[7], "src": r[8], "dest": r[9], "pg": r[10], "kind": r[11],
        })
    return by_id


def _is_market_update(path, title):
    p = (path or "").lower()
    t = (title or "").lower()
    return "market-update" in p or "market update" in t


def build_timeline(events, last_seen=None):
    """From one lead's merged, time-sorted events build:
      - timeline: reverse-chron page visits, each with dwell_minutes (wall time on page,
        2dp) + engaged_minutes + max_depth_pct where a page_engagement fired;
      - articles: every article page they opened, with how deeply they read it;
      - cta_market_turned: did they click "The market has turned. Has your home? →".
    """
    evs = sorted((e for e in events if e["ts"]), key=lambda e: e["ts"])
    if not evs:
        return {"timeline": [], "articles": [], "cta_market_turned": None}
    pvs = [e for e in evs if e["event"] == "$pageview"]
    # The session's true end for the FINAL page's dwell: TIMELINE_EVENTS omit $web_vitals
    # etc., so the last event here can BE the final pageview (=> 0 dwell). last_seen (from
    # the full-event aggregate) is the real last activity — use whichever is later.
    last_ts = evs[-1]["ts"]
    ls = _parse_ts(last_seen)
    if ls and (not last_ts or ls > last_ts):
        last_ts = ls

    timeline = []
    for i, pv in enumerate(pvs):
        start = pv["ts"]
        end = pvs[i + 1]["ts"] if i + 1 < len(pvs) else last_ts
        gap_s = max(0.0, (end - start).total_seconds())
        # Attach page_engagement by TIME WINDOW, not $pathname: on SPA unmount the
        # engagement event's $pathname is often already the NEXT route, but it fired
        # while the visitor was on THIS page (before the next $pageview).
        eng = [e for e in evs if e["event"] == "page_engagement"
               and start <= e["ts"] <= end]
        wall = max([e["wall"] for e in eng if e["wall"] is not None], default=None)
        engaged = max([e["engaged"] for e in eng if e["engaged"] is not None], default=None)
        depth = max([e["depth"] for e in eng if e["depth"] is not None], default=None)
        # Wall time on the page: prefer page_engagement.wall_seconds (measured), else the
        # gap to the next pageview. engaged_minutes is ACTIVE time (may be < dwell).
        dwell_s = wall if wall is not None else gap_s
        timeline.append({
            "path": pv["path"],
            "at": start.isoformat(),
            "dwell_minutes": round(dwell_s / 60.0, 2),
            "engaged_minutes": round(engaged / 60.0, 2) if engaged is not None else None,
            "max_depth_pct": round(depth, 1) if depth is not None else None,
        })
    timeline.reverse()  # most recent first, most historical last

    # Article reading — one row per article page, best depth/engagement seen.
    articles = {}
    for e in evs:
        if e["event"] == "page_engagement" and (e["pg"] == "article_page"
                                                or (e["path"] or "").startswith("/articles/")):
            key = e["path"]
            a = articles.setdefault(key, {"path": e["path"], "title": e["atitle"],
                                          "engaged_seconds": None, "max_depth_pct": None,
                                          "at": e["ts"].isoformat(),
                                          "is_market_update": _is_market_update(e["path"], e["atitle"])})
            if e["engaged"] is not None:
                a["engaged_seconds"] = max(a["engaged_seconds"] or 0, e["engaged"])
            if e["depth"] is not None:
                a["max_depth_pct"] = max(a["max_depth_pct"] or 0, e["depth"])
            if e["atitle"] and not a["title"]:
                a["title"] = e["atitle"]
    for a in articles.values():
        es, dp = a["engaged_seconds"], a["max_depth_pct"]
        a["read"] = bool(es and es >= 30 and dp and dp >= 50)  # meaningful read
        a["engaged_minutes"] = round(es / 60.0, 2) if es is not None else None

    # The specific "The market has turned. Has your home? →" banner button.
    cta = None
    for e in evs:
        if e["event"] == "offmarket_market_article_open":
            cta = {"at": e["ts"].isoformat(), "source": e["src"]}
            break  # first click

    # Unified "did they read the market-update article?" across BOTH paths:
    #  (a) the full /articles/<...>-market-update-... route (page_engagement), and
    #  (b) the in-modal report opened by the banner button (offmarket_market_article_read,
    #      kind='market-update' — the same-origin iframe reader). Best depth/engagement wins.
    reads = []
    for a in articles.values():
        if a["is_market_update"]:
            reads.append({"depth": a["max_depth_pct"], "engaged": a["engaged_seconds"],
                          "via": "article_page", "at": a["at"]})
    for e in evs:
        if e["event"] == "offmarket_market_article_read" and e.get("kind") == "market-update":
            reads.append({"depth": e["depth"], "engaged": e["engaged"],
                          "via": "report_modal", "at": e["ts"].isoformat()})
    market_update = None
    if reads:
        best = max(reads, key=lambda r: ((r["depth"] or 0), (r["engaged"] or 0)))
        d, es = best["depth"], best["engaged"]
        market_update = {
            "opened": True, "via": best["via"], "at": best["at"],
            "max_depth_pct": round(d, 1) if d is not None else None,
            "engaged_seconds": es,
            "engaged_minutes": round(es / 60.0, 2) if es is not None else None,
            "read": bool(es and es >= 30 and d and d >= 50),
        }

    return {"timeline": timeline,
            "articles": sorted(articles.values(), key=lambda x: x["at"], reverse=True),
            "cta_market_turned": cta,
            "market_update": market_update}


def bound_leads(sm):
    """Contacts that have clicked a tokenised link (have a bound distinct_id)."""
    return list(sm["crm_contacts"].find(
        {"lead_web.posthog_distinct_id": {"$ne": None}}))


def ids_for(contact):
    """Every distinct_id this lead's on-site events could live under: the
    pre-identify anonymous id(s) AND the link_token (post-identify events carry the
    token as distinct_id). Both resolve to one PostHog person."""
    lw = contact.get("lead_web") or {}
    ids = set(lw.get("distinct_ids") or [])
    if lw.get("posthog_distinct_id"):
        ids.add(lw["posthog_distinct_id"])
    if contact.get("link_token"):
        ids.add(contact["link_token"])
    return sorted(i for i in ids if i)


def fetch_activity(all_ids):
    """One indexed query for the whole cohort: pageviews + pages per distinct_id."""
    if not all_ids:
        return {}, {}
    idlist = "','".join(i.replace("'", "") for i in all_ids)
    agg = posthog_query(f"""
        SELECT distinct_id,
               countIf(event = '$pageview') AS pageviews,
               count(DISTINCT toDate(timestamp)) AS visit_days,
               min(timestamp) AS first_seen,
               max(timestamp) AS last_seen
        FROM events
        WHERE distinct_id IN ('{idlist}')
        GROUP BY distinct_id
    """)
    pages = posthog_query(f"""
        SELECT distinct_id, properties.$pathname AS path, count() AS n
        FROM events
        WHERE distinct_id IN ('{idlist}') AND event = '$pageview'
        GROUP BY distinct_id, path
        ORDER BY n DESC
    """)
    by_id = {r[0]: {"pageviews": int(r[1] or 0), "visit_days": int(r[2] or 0),
                    "first_seen": str(r[3]), "last_seen": str(r[4])} for r in agg}
    pages_by_id = {}
    for did, path, n in pages:
        pages_by_id.setdefault(did, []).append({"path": path, "count": int(n or 0)})
    return by_id, pages_by_id


def merge_activity(contact, by_id, pages_by_id, events_by_id=None):
    """Combine every distinct_id belonging to this lead into one activity doc."""
    ids = ids_for(contact)
    pv = days = 0
    firsts, lasts, page_counts = [], [], {}
    merged_events = []
    for did in ids:
        merged_events.extend((events_by_id or {}).get(did, []))
        a = by_id.get(did)
        if not a:
            continue
        pv += a["pageviews"]
        days = max(days, a["visit_days"])
        if a["first_seen"] and a["first_seen"] != "None":
            firsts.append(a["first_seen"])
        if a["last_seen"] and a["last_seen"] != "None":
            lasts.append(a["last_seen"])
        for p in pages_by_id.get(did, []):
            page_counts[p["path"]] = page_counts.get(p["path"], 0) + p["count"]
    if pv == 0 and not page_counts:
        return None
    top_pages = sorted(({"path": k, "count": v} for k, v in page_counts.items()),
                       key=lambda x: -x["count"])[:20]
    tl = build_timeline(merged_events, last_seen=(max(lasts) if lasts else None))
    return {
        "total_pageviews": pv,
        "visit_days": days,
        "first_seen": min(firsts) if firsts else None,
        "last_seen": max(lasts) if lasts else None,
        "pages_visited": top_pages,
        "timeline": tl["timeline"],
        "articles": tl["articles"],
        "cta_market_turned": tl["cta_market_turned"],
        "market_update": tl["market_update"],
        "refreshed_at": _now(),
    }


def summarise(act):
    if not act:
        return ""
    top = act["pages_visited"][0]["path"] if act["pages_visited"] else "?"
    last = (act.get("last_seen") or "")[:10]
    base = (f"{act['total_pageviews']} pageviews over {act['visit_days']} day(s); "
            f"last {last}; top: {top}")
    # Surface the two signals Will asked for inline in the one-line summary.
    mkt = act.get("market_update")
    if act.get("cta_market_turned"):
        base += "; clicked 'market has turned' CTA"
    if mkt:
        verb = "READ" if mkt.get("read") else "opened but skimmed"
        base += (f"; {verb} the market-update article "
                 f"({mkt.get('max_depth_pct')}% deep, {mkt.get('engaged_minutes')} min, "
                 f"via {mkt.get('via')})")
    return base


def run(dry_run=False):
    sm = get_client()["system_monitor"]
    leads = bound_leads(sm)
    all_ids = sorted({i for c in leads for i in ids_for(c)})
    by_id, pages_by_id = fetch_activity(all_ids)
    events_by_id = fetch_timeline(all_ids)

    updated = with_activity = 0
    for c in leads:
        act = merge_activity(c, by_id, pages_by_id, events_by_id)
        if not act:
            continue
        with_activity += 1
        if dry_run:
            print(f"  {c.get('name') or c.get('phone') or c.get('email')}: {summarise(act)}")
            continue
        sm["crm_contacts"].update_one(
            {"_id": c["_id"]},
            {"$set": {"lead_web.activity": act,
                      "lead_web.summary": summarise(act),
                      "updated_at": _now()}})
        updated += 1
    return {"bound_leads": len(leads), "with_activity": with_activity, "updated": updated}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.dry_run:
        print(run(dry_run=True))
        return 0

    with job_run("lead_web_activity", cadence_hours=24,
                 title="Lead on-site activity -> CRM") as beat:
        res = run(dry_run=False)
        beat.metrics = res
        # Rule 7b: leads are bound to a distinct_id but NONE produced any activity =>
        # the PostHog query is broken (or every event vanished), not "leads idle".
        # A genuinely empty cohort (no one has clicked a link yet) is bound_leads==0.
        if res["bound_leads"] > 0 and res["with_activity"] == 0:
            raise RuntimeError(
                f"{res['bound_leads']} leads have a bound distinct_id but 0 produced any "
                f"pageviews — PostHog query returned nothing, investigate before trusting.")
        beat.detail = (f"{res['with_activity']}/{res['bound_leads']} bound leads have "
                       f"on-site activity; {res['updated']} updated")
        print(beat.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
