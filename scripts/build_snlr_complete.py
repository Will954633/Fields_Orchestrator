#!/usr/bin/env python3
"""Complete sales-to-new-listings ratio (SNLR) — historical + current, GC-wide.

The two halves of "new listings" are complementary and together complete:
  * CONCLUDED listings  → Domain property_timeline campaign starts
       (list_date = event_date − days_on_market, for sold AND 'Listed - not sold' events)
  * STILL-ACTIVE listings → onthehouse for-sale ledger (system_monitor.onthehouse_listings,
       active=True) by `listed_date` — these aren't in the timeline yet (haven't concluded)
The union covers every listing that appeared in any quarter, incl. the recent edge the
timeline alone under-counts. Deduped by (address_key, quarter).

Sales:
  * history (older quarters) → timeline is_sold
  * recent quarters (onthehouse coverage) → onthehouse_sold (fresh, complete incl. VG)

All-dwelling (houses+units), quarterly. Renders a local PNG. Both free sources.
Usage: python3 scripts/build_snlr_complete.py
"""
import sys, collections, statistics
from datetime import date, timedelta
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shared.db import get_client
from shared.env import load_env
load_env()

GREEN="#166534"; COPPER="#b76749"; GREY="#9aa0a6"
SKIP=("precomputed_","sqm_","propradar_","address_","suburb_","schema_","system_","narrative_","coverage_","change_","complexes","unit_","property_attributes","offmarket_")
def q(d):
    d=str(d); y,m=int(d[:4]),int(d[5:7]); return f"{y}-Q{(m-1)//3+1}"
def qsort(x): y,n=x.split("-Q"); return (int(y),int(n))

def main():
    cl=get_client(); gc=cl["Gold_Coast"]; sm=cl["system_monitor"]
    subs=[c for c in gc.list_collection_names() if not c.startswith(SKIP) and c.replace("_","").isalpha()]

    # --- NEW LISTINGS ---
    # (a) concluded campaign starts from timeline (address_key|quarter dedup)
    concluded=set(); ts_sold=collections.Counter()
    for s in subs:
        for d in gc[s].find({"scraped_data.property_timeline.days_on_market":{"$ne":None}},
                            {"scraped_data.property_timeline":1,"street_address":1}):
            addr=(d.get("street_address") or "")[:40].lower()
            for e in (d.get("scraped_data",{}).get("property_timeline") or []):
                if not isinstance(e,dict): continue
                ed=str(e.get("date") or "")[:10]; dom=e.get("days_on_market")
                if len(ed)!=10: continue
                if e.get("is_sold") or e.get("type")=="Listed - not sold":
                    if isinstance(dom,(int,float)) and 0<=dom<1000:
                        try: concluded.add((addr, q((date.fromisoformat(ed)-timedelta(days=int(dom))).isoformat())))
                        except: pass
                if e.get("is_sold"): ts_sold[q(ed)]+=1
    newl=collections.Counter(k[1] for k in concluded)
    # (b) still-active listings from onthehouse ledger (fill the recent edge)
    active_keys=set()
    for d in sm["onthehouse_listings"].find({"active":True,"listed_date":{"$ne":None}},
                                             {"listed_date":1,"address":1}):
        addr=(d.get("address") or "")[:40].lower(); qq=q(d["listed_date"])
        if (addr,qq) not in concluded and (addr,qq) not in active_keys:
            active_keys.add((addr,qq)); newl[qq]+=1

    # --- SALES: timeline is_sold for history, onthehouse_sold for recent coverage ---
    os_sold=collections.Counter()
    for d in sm["onthehouse_sold"].find({},{"sold_date":1}):
        if d.get("sold_date"): os_sold[q(d["sold_date"])]+=1
    oth_from=min(os_sold) if os_sold else "9999"
    sales={}
    allq=sorted(set(newl)|set(ts_sold)|set(os_sold), key=qsort)
    for qq in allq:
        # onthehouse_sold is complete from oth_from; before that timeline is the deep source
        sales[qq]= os_sold[qq] if qq>=oth_from and os_sold[qq]>=ts_sold[qq] else ts_sold[qq]

    # SNLR
    rows=[]
    for qq in allq:
        if qsort(qq)<(2016,1): continue
        nl=newl.get(qq,0); sl=sales.get(qq,0)
        if nl>=10: rows.append((qq,sl,nl,sl/nl))
    print(f"{'Q':8s} {'sales':>6s} {'newlist':>8s} {'SNLR':>6s}")
    for qq,sl,nl,r in rows[-14:]:
        print(f"{qq:8s} {sl:>6d} {nl:>8d} {r:>6.2f}")

    qs=[r[0] for r in rows]; snlr=[r[3] for r in rows]
    fig,ax=plt.subplots(figsize=(13,6))
    x=range(len(qs))
    ax.plot(x,snlr,color=GREEN,lw=2,marker="o",ms=3)
    ax.axhline(1.0,color=GREY,ls="--",lw=1); ax.text(0.3,1.02,"balance (1 sale per new listing)",color=GREY,fontsize=8)
    for qq,lbl,dy in [("2021-Q1","2021 boom\n(tight)",0.12),("2022-Q3","2022 rate shock\n(soft)",-0.18)]:
        if qq in qs:
            i=qs.index(qq); ax.annotate(lbl,(i,snlr[i]),fontsize=8,ha="center",xytext=(i,snlr[i]+dy),
                                        color="#333",arrowprops=dict(arrowstyle="-",color=GREY,lw=0.8))
    if "2026-Q1" in qs:
        i=qs.index("2026-Q1"); ax.axvline(i,color=COPPER,ls=":",lw=1.2)
        ax.text(i+0.15,max(snlr)*0.9,"~Mar 2026\nmarket flip",color=COPPER,fontsize=9)
    ax.set_ylabel("Sales ÷ new listings (quarterly)")
    ax.set_title("Gold Coast — Sales-to-New-Listings Ratio (higher = tighter / seller's market)",
                 fontsize=13,fontweight="bold")
    tk=[i for i,qq in enumerate(qs) if qq.endswith("Q1")]
    ax.set_xticks(tk); ax.set_xticklabels([qs[i][:4] for i in tk]); ax.grid(axis="y",color="#f0ece1")
    ax.set_xlim(-0.5,len(qs)-0.5)
    fig.text(0.5,0.005,"New listings = timeline concluded campaigns + onthehouse still-active (by list date). "
             "Sales = timeline (history) / onthehouse_sold (recent). All-dwelling. Both free sources.",
             ha="center",fontsize=7.5,color="#888")
    plt.tight_layout(rect=[0,0.02,1,1])
    import os
    out="/home/fields/Fields_Orchestrator/02_Data/Sales_To_Listings"; os.makedirs(out,exist_ok=True)
    path=f"{out}/gc_snlr_complete.png"; plt.savefig(path,dpi=130,bbox_inches="tight"); print("wrote",path)

if __name__=="__main__": main()
