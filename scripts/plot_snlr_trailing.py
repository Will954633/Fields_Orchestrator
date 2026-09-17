#!/usr/bin/env python3
"""Trailing-8-week sales-to-new-listings ratio, per Will's spec (2026-09-17).

ONE consistent basis — the Domain property_timeline (same data behind
gc_sales_to_listings.png) — for the whole series:
  * listed in window = campaign STARTS in window  (list_date = event_date − days_on_market,
    from sold AND 'Listed - not sold' events; docs that carry days_on_market, matching the
    historical chart's basis).
  * sold in window   = is_sold events in window (by event_date).

Recent-90-day switch: within 90 days of today the timeline hasn't yet recorded listings
that are still on the market (haven't concluded), so the listed count is completed with
the CURRENT listings snapshot (onthehouse active, by listed_date). i.e. for the recent
window: listed = (listed-and-concluded, from timeline) + (listed-and-not-yet-sold, from
current listings); sold = timeline is_sold. Everything else stays timeline-only.

Trailing 8 weeks (56d), stepped weekly. Renders a local PNG.
"""
import sys, json, bisect
from datetime import date, timedelta
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shared.db import get_client
from shared.env import load_env
load_env()

GREEN="#166534"; COPPER="#b76749"; GREY="#9aa0a6"; BLUE="#0284c7"
SKIP=("precomputed_","sqm_","propradar_","address_","suburb_","schema_","system_","narrative_","coverage_","change_","complexes","unit_","property_attributes","offmarket_")
TODAY=date(2026,9,17)
CACHE="/tmp/claude-1001/-home-fields-Fields-Orchestrator/efc87bbe-977c-4ee5-ace0-d4daf2a584d2/scratchpad/snlr_timeline_cache.json"

def collect():
    import os
    if os.path.exists(CACHE):
        d=json.load(open(CACHE)); return d["list_dates"], d["sold_dates"], d["current_listed"], d["oth_sold"]
    cl=get_client(); gc=cl["Gold_Coast"]; sm=cl["system_monitor"]
    subs=[c for c in gc.list_collection_names() if not c.startswith(SKIP) and c.replace("_","").isalpha()]
    list_dates=[]; sold_dates=[]
    for s in subs:
        for d in gc[s].find({"scraped_data.property_timeline.days_on_market":{"$ne":None}},
                            {"scraped_data.property_timeline":1}):
            for e in (d.get("scraped_data",{}).get("property_timeline") or []):
                if not isinstance(e,dict): continue
                ed=str(e.get("date") or "")[:10]; dom=e.get("days_on_market")
                if len(ed)!=10: continue
                if e.get("is_sold"): sold_dates.append(ed)
                if e.get("is_sold") or e.get("type")=="Listed - not sold":
                    if isinstance(dom,(int,float)) and 0<=dom<1000:
                        try: list_dates.append((date.fromisoformat(ed)-timedelta(days=int(dom))).isoformat())
                        except: pass
    current_listed=[str(x["listed_date"])[:10] for x in
                    sm["onthehouse_listings"].find({"active":True,"listed_date":{"$ne":None}},{"listed_date":1})]
    # recent-window complete SOLD feed (onthehouse_sold, complete incl VG)
    oth_sold=[str(x["sold_date"])[:10] for x in sm["onthehouse_sold"].find({"sold_date":{"$ne":None}},{"sold_date":1})]
    for a in (list_dates,sold_dates,current_listed,oth_sold): a.sort()
    json.dump({"list_dates":list_dates,"sold_dates":sold_dates,"current_listed":current_listed,"oth_sold":oth_sold}, open(CACHE,"w"))
    return list_dates, sold_dates, current_listed, oth_sold

def cnt(sorted_dates, lo, hi):  # (lo, hi]
    return bisect.bisect_right(sorted_dates,hi)-bisect.bisect_right(sorted_dates,lo)

def main():
    list_dates, sold_dates, current_listed, oth_sold = collect()
    print(f"timeline: {len(list_dates)} list-events, {len(sold_dates)} sold-events; "
          f"current active listings: {len(current_listed)}; onthehouse sold: {len(oth_sold)}")
    cutoff=(TODAY-timedelta(days=90)).isoformat()   # recent-window switch
    xs=[]; snlr=[]; comp=[]  # comp: True where the recent complete-feed methodology applied
    E=date(2016,6,1)
    while E<=TODAY:
        hi=E.isoformat(); lo=(E-timedelta(days=56)).isoformat()
        recent = hi>cutoff
        if recent:
            # complete both flows from fresh sources: sold = onthehouse_sold;
            # listed = current still-active + timeline concluded-in-window
            sold=cnt(oth_sold,lo,hi)
            listed=cnt(current_listed,lo,hi)+cnt(list_dates,lo,hi)
        else:
            # historical: timeline both flows (internally-consistent, scale-free ratio)
            sold=cnt(sold_dates,lo,hi)
            listed=cnt(list_dates,lo,hi)
        xs.append(E); comp.append(recent)
        snlr.append(sold/listed if listed>=8 else None)
        E+=timedelta(days=7)

    fig,ax=plt.subplots(figsize=(14,6))
    pts=[(x,y) for x,y in zip(xs,snlr) if y is not None]
    vx,vy=zip(*pts)
    ax.plot(vx,vy,color=GREEN,lw=1.8)
    # mark the recent (completed-methodology) segment in blue
    rec=[(x,y) for x,y,c in zip(xs,snlr,comp) if y is not None and c]
    if rec:
        rx,ry=zip(*rec); ax.plot(rx,ry,color=BLUE,lw=2.4,label="recent 90d (timeline + current listings)")
    ax.axhline(1.0,color=GREY,ls="--",lw=1); ax.text(xs[2],1.03,"balance (1 sale per new listing)",color=GREY,fontsize=8)
    import datetime as _dt
    for d0,lbl,col in [(_dt.date(2021,3,1),"2021 boom",GREY),(_dt.date(2022,9,1),"2022 rate shock",GREY),
                       (_dt.date(2026,3,1),"~Mar 2026 flip",COPPER)]:
        ax.axvline(d0,color=col,ls=":",lw=1)
    ax.text(_dt.date(2026,3,5),max(vy)*0.9,"~Mar 2026\nflip",color=COPPER,fontsize=8)
    ax.set_ylabel("Sales ÷ new listings (trailing 8 wks)")
    ax.set_title("Gold Coast — Sales-to-New-Listings Ratio, trailing 8 weeks (weekly)  ·  timeline basis; recent 90d completed with current listings",
                 fontsize=11.5,fontweight="bold")
    ax.grid(axis="y",color="#f0ece1"); ax.legend(loc="upper right",fontsize=8)
    fig.text(0.5,0.005,"Listed = timeline campaign-starts (list_date = event − DOM); Sold = timeline is_sold. "
             "Within 90d of today, listed completed with onthehouse current active listings. Same basis as gc_sales_to_listings.png.",
             ha="center",fontsize=7.5,color="#888")
    plt.tight_layout(rect=[0,0.02,1,1])
    import os
    out="/home/fields/Fields_Orchestrator/02_Data/Sales_To_Listings"; os.makedirs(out,exist_ok=True)
    path=f"{out}/gc_snlr_trailing8w.png"; plt.savefig(path,dpi=130,bbox_inches="tight"); print("wrote",path)
    print("\nrecent trailing-8wk SNLR (last 12 weekly steps):")
    for x,y,c in list(zip(xs,snlr,comp))[-12:]:
        print(f"  {x}  snlr={(f'{y:.2f}' if y else '-'):>5}  {'(completed)' if c else ''}")

if __name__=="__main__": main()
