#!/usr/bin/env python3
"""
growth_ideation.py — Samantha's per-session GROWTH IDEATION brief.

Purpose: the difference between "instructed to experiment" and "actually does it" is
FACILITATION — a decision-ready brief of the current funnel so she doesn't have to
reassemble it ad hoc every session (which is why hypothesis_queue had 2 null stubs and
change_ledger 3 unmeasured entries). This assembles the contextual data across the five
growth areas and prints pointed ideation prompts, then records the run so a skip is visible.

Five areas (Will, 2026-07-27): (1) A/B test candidates, (2) funnel engagement,
(3) conversion, (4) lead capture, (5) new ad concepts (ad concepts = PREP for the
scheduled Will session, not autonomous launch — see daily_tasks Task D/G).

Usage:
  python3 scripts/samantha/growth_ideation.py            # print the brief
  python3 scripts/samantha/growth_ideation.py --record   # print + stamp samantha_state.growth_ideation
"""
from __future__ import annotations
import argparse, datetime as dt, os, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.mongo_client_factory import get_mongo_client

NOW = datetime.now(timezone.utc)

def _dt(v):
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        for f in ("%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S",
                  "%Y-%m-%d %H:%M:%S.%f","%Y-%m-%d %H:%M:%S","%Y-%m-%d"):
            try:
                d = datetime.strptime(v.replace("Z","+0000"), f)
                return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def _recency(coll, fields=("created_at","timestamp","submitted_at","ts","date","updated_at","sent_at",
                           "session_start","first_seen","last_seen","entry_time","built_at","window_end","completed_at")):
    """Return (total, 7d, 30d, newest) for a collection, trying common date fields."""
    d7=d30=0; newest=None; tot=0
    try:
        tot = coll.estimated_document_count()
        for doc in coll.find({}, limit=3000):
            d=None
            for f in fields:
                if doc.get(f) is not None:
                    d=_dt(doc.get(f));
                    if d: break
            if not d: continue
            age=(NOW-d).days
            if age<=7: d7+=1
            if age<=30: d30+=1
            if newest is None or d>newest: newest=d
    except Exception:
        pass
    return tot,d7,d30,newest

def _exists(sm, name):
    try:
        return name in sm.list_collection_names()
    except Exception:
        return False

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="stamp samantha_state.growth_ideation")
    a=ap.parse_args()
    sm=get_mongo_client()["system_monitor"]
    L=[]
    P=L.append
    P("="*78)
    P("GROWTH IDEATION BRIEF  —  %s AEST" % (NOW+timedelta(hours=10)).strftime("%Y-%m-%d %H:%M"))
    P("North star: grow INBOUND ENQUIRY (warm audience → surface intent → raised hand).")
    P("Produce >=1 evidence-cited hypothesis_queue entry per area below, or say why the surface is saturated.")
    P("="*78)

    # ---- 1. FUNNEL SNAPSHOT (stage volumes, 7d / 30d) ----
    P("\n[1] FUNNEL SNAPSHOT (new docs: 7d / 30d)  — where is the drop-off?")
    stages = [
      ("REACH", "organic_journeys"), ("REACH", "crm_contacts"),
      ("WARM", "property_reports"), ("WARM", "feed_interactions"),
      ("INTENT", "offmarket_qualification"), ("INTENT", "forsale_ladder_responses"),
      ("INTENT", "price_alert_subscriptions"),
      ("ENQUIRY", "report_review_bookings"), ("ENQUIRY", "fb_leads"),
      ("ENQUIRY", "leads"),
      ("CONVERT", "appraisal_pipeline"),
    ]
    for stage,name in stages:
        if not _exists(sm,name):
            P(f"   {stage:8} {name:28} — (collection absent)"); continue
        tot,d7,d30,newest = _recency(sm[name])
        ns = newest.strftime("%Y-%m-%d") if newest else "—"
        flag = "  <-- DEAD 30d" if d30==0 else ""
        P(f"   {stage:8} {name:28} {d7:>3} / {d30:>3}   (tot {tot}, newest {ns}){flag}")

    # ---- 2. LEAD-CAPTURE SURFACES ----
    P("\n[2] LEAD-CAPTURE SURFACES (are the raised-hand doors working?)")
    caps = ["analyse_leads","valuation_requests","report_review_bookings","subscribers",
            "five_property_friday_subscribers","price_alert_subscriptions","lead_signups",
            "offmarket_qualification","offmarket_orders","fb_leads"]
    for name in caps:
        if not _exists(sm,name):
            P(f"   {name:32} — (absent)"); continue
        tot,d7,d30,newest = _recency(sm[name])
        ns = newest.strftime("%Y-%m-%d") if newest else "—"
        status = "DEAD" if d30==0 else ("thin" if d30<3 else "live")
        P(f"   {name:32} 7d {d7:>2} / 30d {d30:>2}  [{status}]  newest {ns}")

    # ---- 3. ENGAGEMENT / CONVERSION CANDIDATES (worst-served high-traffic pages) ----
    P("\n[3] ENGAGEMENT / CONVERSION — high-traffic entry pages with weak engagement/conversion")
    try:
        if _exists(sm,"organic_landing_affinity"):
            rows=list(sm["organic_landing_affinity"].find({}))
            def sess(r): return r.get("sessions") or r.get("session_count") or 0
            rows=[r for r in rows if sess(r)>=3]
            rows.sort(key=lambda r: sess(r), reverse=True)
            P("   entry_path                              sess  engaged  conv")
            for r in rows[:8]:
                path=(r.get("entry_path") or r.get("_id") or "?")
                eng=r.get("engaged") or r.get("engaged_sessions") or 0
                conv=r.get("converters") or r.get("conversions") or 0
                P(f"   {str(path)[:40]:40} {sess(r):>4}  {eng:>6}  {conv:>4}")
        else:
            P("   organic_landing_affinity absent — pull entry-page engagement from PostHog instead.")
    except Exception as e:
        P(f"   (engagement read failed: {e})")

    # ---- 4. AD ANGLES (for the Will ad-review session prep) ----
    P("\n[4] AD ANGLES (prep for the scheduled FB ad-review session WITH Will — do NOT auto-overhaul)")
    try:
        if _exists(sm,"ad_content_affinity"):
            rows=list(sm["ad_content_affinity"].find({}))
            def conv(r): return r.get("conversions") or r.get("converters") or 0
            rows.sort(key=lambda r: (conv(r), r.get("sessions",0)), reverse=True)
            P("   angle/theme                    sessions  conv  note")
            for r in rows[:6]:
                ang=r.get("theme") or r.get("angle") or r.get("_id") or "?"
                P(f"   {str(ang)[:30]:30} {r.get('sessions',0):>8}  {conv(r):>4}  {str(r.get('note',''))[:24]}")
        else:
            P("   ad_content_affinity absent.")
        P("   NB: FB paid delivery stalled since ~22 Jul (billing ~$103) — recent ad reads are thin; split pre/post-collapse.")
    except Exception as e:
        P(f"   (ad read failed: {e})")

    # ---- 5. OPEN EXPERIMENT SLOTS ----
    P("\n[5] EXPERIMENT PIPELINE — what's live, what's queued, what surfaces are free")
    try:
        live=list(sm["samantha_changes"].find({"status":"live"}))
        P(f"   change_ledger LIVE tests: {len(live)}")
        for r in live:
            P(f"     - [{r.get('type')}] {str(r.get('title',''))[:56]} (verdict {r.get('verdict')})")
        due=[r for r in live if r.get("verdict") in (None,"too_early")]
        if due: P(f"   -> {len(due)} live test(s) still UNMEASURED — close the loop before adding more on that surface.")
    except Exception as e:
        P(f"   (change_ledger read failed: {e})")
    try:
        q=list(sm["hypothesis_queue"].find({"status":"queued"}))
        P(f"   hypothesis_queue QUEUED: {len(q)}")
        for r in q[:6]:
            P(f"     - {str(r.get('concept') or r.get('title') or '(unnamed)')[:56]} [{r.get('surface')}] score {r.get('score','?')}")
        if len(q)<=2:
            P("   -> queue is nearly empty: this session MUST add evidence-cited hypotheses (that's the point).")
    except Exception as e:
        P(f"   (hypothesis_queue read failed: {e})")

    # ---- 6. IDEATION PROMPTS (the 5 areas) ----
    P("\n[6] IDEATION — answer each with an action (add to hypothesis_queue) or 'saturated + why':")
    P("   (1) A/B TEST: which single surface above has enough traffic + a big expected effect to test now?")
    P("   (2) FUNNEL ENGAGEMENT: where is the biggest 7d/30d drop-off in [1]? what warming step is missing?")
    P("   (3) CONVERSION: which high-traffic page in [3] under-converts? what CTA/intent-tease would move it?")
    P("   (4) LEAD CAPTURE: which door in [2] is DEAD/thin? is it demand or a broken/absent capture step?")
    P("   (5) AD CONCEPTS: which angle in [4] to KILL, and what to bring to Will's session? (prep only)")
    P("\n   Log each as: python3 scripts/samantha/hypothesis_queue.py add --concept '...' \\")
    P("       --sources brain1,brain2 --evidence '<cite>' --surface <fb_ads|website|seo|email> \\")
    P("       --expected-effect '...' --est-power directional --score <1-10>")
    P("   Then mirror the top items to the KPI Monitor sheet 'Experiment Backlog' tab.")
    P("="*78)

    out="\n".join(L)
    print(out)

    if a.record:
        sm["samantha_state"].update_one(
            {"_id":"growth_ideation"},
            {"$set":{"last_run":NOW, "next_review_due":NOW+timedelta(days=1),
                     "run_by":"growth_ideation.py"}}, upsert=True)
        print("\n[recorded samantha_state.growth_ideation last_run=%s]" % NOW.isoformat())

if __name__=="__main__":
    raise SystemExit(main())
