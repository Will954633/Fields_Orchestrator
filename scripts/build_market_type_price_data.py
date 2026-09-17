#!/usr/bin/env python3
"""Data for the inventory + market-by-type artifact (2017→now).

Two coherent layers, each from the source that can honestly carry it:
  STOCK (unsold) aging   -> SQM total-property-listings monthly counts by age band
                            (reused from inventory_artifact_data.json; filtered to 2017+)
  SOLD market by type    -> system_monitor.domain_sold, 6-MONTH ROLLING per month:
                            per property type — volume share, median sale price + IQR
                            ($ middle-50%), and median days-on-market (selling speed).
                            Period-accurate: a 2017 hover shows 2017 prices, a 2026 hover 2026.

Why sold (not on-market) for price/type: we have no historical on-market listing-level
price/type. Domain sold is 94-98% priced, 86-97% DOM, 2016→now — the only source that gives
a *time-varying* price and speed read. The >180d SOLD band is too thin to price by type
(most stale listings withdraw, not sell), so type/price/speed is market-wide per period,
NOT sliced by the SQM age band.
"""
import json, sys, bisect, statistics, collections
from datetime import date, timedelta
sys.path.insert(0,"/home/fields/Fields_Orchestrator")
from shared.db import get_client
from shared.env import load_env; load_env()

SRC="/tmp/claude-1001/-home-fields-Fields-Orchestrator/efc87bbe-977c-4ee5-ace0-d4daf2a584d2/scratchpad/inventory_artifact_data.json"
OUT="/tmp/claude-1001/-home-fields-Fields-Orchestrator/efc87bbe-977c-4ee5-ace0-d4daf2a584d2/scratchpad/market_type_price_data.json"
START="2017-01"
TYPES=["House","Unit/Apt","Townhouse","Villa/Duplex"]

def norm_type(pt,dw):
    pt=(pt or "").strip()
    if pt=="House": return "House"
    if pt=="Townhouse": return "Townhouse"
    if pt in ("Unit","Apartment","ApartmentUnitFlat","Flat","Studio","Penthouse"): return "Unit/Apt"
    if pt in ("Duplex","DuplexSemi-detached","Semi-Detached","Villa","Terrace"): return "Villa/Duplex"
    return "House" if dw=="house" else "Unit/Apt" if dw=="unit" else "Other"

def month_end_exclusive(ym):
    y,m=int(ym[:4]),int(ym[5:7])
    return date(y+(m//12), (m%12)+1, 1)   # first day of next month

def main():
    base=json.load(open(SRC))
    gc_monthly=[r for r in base["gc_monthly"] if r["ym"]>=START]
    core3={n:{"postcode":v["postcode"],
              "series":[p for p in v["series"] if p["ym"]>=START]} for n,v in base["core3"].items()}

    # ---- Domain sold rows (priced), sorted by date ----
    ds=get_client()["system_monitor"]["domain_sold"]
    rows=[]
    for d in ds.find({"sold_date":{"$ne":None},"sale_price":{"$gt":10000}},
                     {"sold_date":1,"sale_price":1,"dom_days":1,"dwelling":1,"property_type":1}):
        sd=str(d["sold_date"])[:10]
        if len(sd)!=10 or sd<"2016-07": continue
        try: dt=date.fromisoformat(sd)
        except: continue
        rows.append((dt,d["sale_price"],d.get("dom_days"),norm_type(d.get("property_type"),d.get("dwelling"))))
    rows.sort(key=lambda r:r[0])
    dates=[r[0] for r in rows]
    print(f"domain_sold priced rows: {len(rows)}  ({dates[0]} → {dates[-1]})")

    def q(vals,k):
        s=sorted(vals)
        if len(s)<8: return None
        return round(statistics.quantiles(s,n=4)[k])
    def med_int(vals):
        s=sorted(v for v in vals if isinstance(v,(int,float)) and 0<=v<400)
        return round(statistics.median(s)) if len(s)>=8 else None

    sold_by_period={}
    for r in gc_monthly:
        ym=r["ym"]; end=month_end_exclusive(ym); lo=end-timedelta(days=182)
        win=rows[bisect.bisect_left(dates,lo):bisect.bisect_left(dates,end)]
        per=collections.defaultdict(lambda:{"price":[],"dom":[]})
        for dt,pr,dom,t in win:
            per[t]["price"].append(pr); per[t]["dom"].append(dom)
        types={}
        for t in TYPES+["Other"]:
            pv=per[t]["price"]
            if not pv: continue
            types[t]={"n":len(pv),"med":q(pv,1),"p25":q(pv,0),"p75":q(pv,2),"dom":med_int(per[t]["dom"])}
        sold_by_period[ym]={"n":len(win),"types":types}

    out={"generated":base["generated"],"start":START,
         "bands":base["bands"],"band_labels":base["band_labels"],
         "gc_monthly":gc_monthly,"core3":core3,
         "type_order":TYPES,"sold_by_period":sold_by_period}
    json.dump(out,open(OUT,"w"))
    # sanity print
    for ym in ["2017-06","2021-06","2024-06","2026-06"]:
        s=sold_by_period.get(ym)
        if s and "House" in s["types"]:
            h=s["types"]["House"]; print(f"  {ym}: sold n={s['n']:>4}  House med ${h['med']:,} IQR ${h['p25']:,}-${h['p75']:,} dom {h['dom']}d")
    print("wrote",OUT,"months",len(gc_monthly))

if __name__=="__main__": main()
