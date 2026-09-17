#!/usr/bin/env python3
"""Emit per-window SNLR populations with FULL source provenance, for the interactive
HTML artifact. No methodology baked in — every candidate population is exposed per
weekly trailing-8-week window so the ratio can be recomputed client-side from any
combination of sources.

Populations per window (trailing 56 days, stepped weekly):
  SALES (numerator candidates):
    timeline_is_sold  : Gold_Coast property_timeline is_sold events, by event date
    onthehouse_sold   : system_monitor.onthehouse_sold, by sold_date (complete incl VG)
    domain_sold       : system_monitor.domain_sold, by sold_date (Domain GraphQL, agent-listed)
  NEW LISTINGS (denominator candidates), all by LIST date:
    tl_campaign_sold    : timeline campaign start of a SOLD event   (event_date − days_on_market)
    tl_campaign_notsold : timeline campaign start of a 'Listed - not sold' event
    current_active      : onthehouse_listings active=True, by listed_date
    domain_sold_listdate: domain_sold, by (sold_date − dom_days) — list date of a sold home
"""
import sys, json, bisect, collections
from datetime import date, timedelta
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client
from shared.env import load_env
load_env()

TODAY = date(2026, 9, 17)
WIN = 56
SKIP = ("precomputed_","sqm_","propradar_","address_","suburb_","schema_","system_",
        "narrative_","coverage_","change_","complexes","unit_","property_attributes","offmarket_")

def d10(x): return str(x or "")[:10]

def main():
    cl = get_client(); gc = cl["Gold_Coast"]; sm = cl["system_monitor"]
    subs = [c for c in gc.list_collection_names()
            if not c.startswith(SKIP) and c.replace("_","").isalpha()]

    tl_sold=[]; tl_camp_sold=[]; tl_camp_notsold=[]
    for s in subs:
        for d in gc[s].find({"scraped_data.property_timeline":{"$exists":True}},
                            {"scraped_data.property_timeline":1}):
            for e in (d.get("scraped_data",{}).get("property_timeline") or []):
                if not isinstance(e,dict): continue
                ed=d10(e.get("date")); dom=e.get("days_on_market")
                if len(ed)!=10: continue
                is_sold=bool(e.get("is_sold")); notsold=(e.get("type")=="Listed - not sold")
                if is_sold: tl_sold.append(ed)
                if isinstance(dom,(int,float)) and 0<=dom<1000:
                    try: cs=(date.fromisoformat(ed)-timedelta(days=int(dom))).isoformat()
                    except: cs=None
                    if cs:
                        if is_sold: tl_camp_sold.append(cs)
                        elif notsold: tl_camp_notsold.append(cs)

    oth_sold=[d10(x["sold_date"]) for x in sm["onthehouse_sold"].find(
              {"sold_date":{"$ne":None}},{"sold_date":1})]
    dom_sold=[]; dom_sold_listdate=[]
    for x in sm["domain_sold"].find({"sold_date":{"$ne":None}},{"sold_date":1,"dom_days":1}):
        sd=d10(x["sold_date"]); dom_sold.append(sd)
        dd=x.get("dom_days")
        if isinstance(dd,(int,float)) and dd>0:
            try: dom_sold_listdate.append((date.fromisoformat(sd)-timedelta(days=int(dd))).isoformat())
            except: pass
    cur_active=[d10(x["listed_date"]) for x in sm["onthehouse_listings"].find(
               {"active":True,"listed_date":{"$ne":None}},{"listed_date":1})]

    series={k:sorted(v) for k,v in {
        "timeline_is_sold":tl_sold, "onthehouse_sold":oth_sold, "domain_sold":dom_sold,
        "tl_campaign_sold":tl_camp_sold, "tl_campaign_notsold":tl_camp_notsold,
        "current_active":cur_active, "domain_sold_listdate":dom_sold_listdate,
    }.items()}
    for k,v in series.items():
        print(f"  {k:22} n={len(v):>6}  range {v[0] if v else '-'} → {v[-1] if v else '-'}")

    def cnt(a,lo,hi): return bisect.bisect_right(a,hi)-bisect.bisect_right(a,lo)
    pts=[]; E=date(2016,6,1)
    while E<=TODAY:
        hi=E.isoformat(); lo=(E-timedelta(days=WIN)).isoformat()
        pts.append({"end":hi,"lo":lo,
                    "pop":{k:cnt(v,lo,hi) for k,v in series.items()}})
        E+=timedelta(days=7)

    out={"generated":TODAY.isoformat(),"window_days":WIN,
         "first_seen":{k:(v[0] if v else None) for k,v in series.items()},
         "totals":{k:len(v) for k,v in series.items()},
         "points":pts}
    p="/tmp/claude-1001/-home-fields-Fields-Orchestrator/efc87bbe-977c-4ee5-ace0-d4daf2a584d2/scratchpad/snlr_artifact_data.json"
    json.dump(out,open(p,"w"))
    print("wrote",p,"with",len(pts),"windows")

if __name__=="__main__": main()
