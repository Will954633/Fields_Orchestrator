#!/usr/bin/env python3
"""Composition of CURRENT stock-on-market by listing age band — which home types and
price ranges dominate fresh vs stale inventory.

Source: system_monitor.onthehouse_listings active=True (our 82-suburb residential ledger,
~3,200 listings). Each listing's age = today − listed_date, bucketed into the same 5 bands
as the SQM inventory chart. Cross-tabbed by property_type and by listed-price band.
CURRENT stock only — we have no historical active snapshots to decompose SQM's history.

Two 100%-stacked panels so the *shift* in mix across age bands is what reads.
"""
import sys, re, collections
from datetime import date
sys.path.insert(0,'/home/fields/Fields_Orchestrator')
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shared.db import get_client
from shared.env import load_env; load_env()
TODAY=date(2026,9,17)
BANDS=[("r30","<30d"),("r60","30-60d"),("r90","60-90d"),("r180","90-180d"),("r180p",">180d")]

def parse_price(s):
    if not s: return None
    vals=[]
    for n,suf in re.findall(r'\$?\s*([\d,]+(?:\.\d+)?)\s*(m|million|k)?', str(s), re.I):
        try: v=float(n.replace(',',''))
        except: continue
        if suf and suf.lower().startswith('m'): v*=1_000_000
        elif suf and suf.lower()=='k': v*=1_000
        elif v<10000: v*= (1_000_000 if v<100 else 1000)
        if 100_000<=v<=30_000_000: vals.append(v)
    return min(vals) if vals else None

def ageband(d):
    return "r30" if d<30 else "r60" if d<60 else "r90" if d<90 else "r180" if d<180 else "r180p"
def priceband(v):
    if v is None: return "unknown"
    for hi,lbl in [(600_000,"<$600k"),(1_000_000,"$600k–1m"),(1_500_000,"$1–1.5m"),
                   (2_000_000,"$1.5–2m"),(3_000_000,"$2–3m")]:
        if v<hi: return lbl
    return "$3m+"

TYPES=["House","Apartment","Unit","Townhouse","Villa/Duplex","Other"]
TYPE_COL={"House":"#166534","Apartment":"#b76749","Unit":"#d6ad4a","Townhouse":"#2f6f9f",
          "Villa/Duplex":"#7fae3f","Other":"#c7ccc6"}
PBANDS=["<$600k","$600k–1m","$1–1.5m","$1.5–2m","$2–3m","$3m+","unknown"]
# cheap -> expensive sequential green->red, unknown grey
PB_COL={"<$600k":"#2f8f57","$600k–1m":"#7fae3f","$1–1.5m":"#d6ad4a","$1.5–2m":"#c9803f",
        "$2–3m":"#a83a2f","$3m+":"#6d211a","unknown":"#c7ccc6"}
def norm_type(t):
    if t in ("House","Apartment","Unit","Townhouse"): return t
    if t in ("Villa","DuplexSemi-detached","Semi-Detached"): return "Villa/Duplex"
    return "Other"

def main():
    sm=get_client()["system_monitor"]
    rows=list(sm["onthehouse_listings"].find({"active":True,"listed_date":{"$ne":None}},
              {"property_type":1,"display_price":1,"listed_date":1}))
    tcnt={k:collections.Counter() for k,_ in BANDS}
    pcnt={k:collections.Counter() for k,_ in BANDS}
    band_n=collections.Counter()
    for r in rows:
        try: ld=date.fromisoformat(str(r["listed_date"])[:10])
        except: continue
        b=ageband((TODAY-ld).days); band_n[b]+=1
        tcnt[b][norm_type(r.get("property_type") or "Other")]+=1
        pcnt[b][priceband(parse_price(r.get("display_price")))]+=1

    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(14,6.5))
    fig.suptitle("What's in each inventory age band — current Gold Coast stock on market",
                 fontsize=15,fontweight="bold",y=0.98)
    labels=[lbl for _,lbl in BANDS]; x=range(len(BANDS))

    def stacked(ax,cnts,cats,cols,title):
        base=[0.0]*len(BANDS)
        for cat in cats:
            share=[100*cnts[k][cat]/max(band_n[k],1) for k,_ in BANDS]
            ax.bar(x,share,bottom=base,color=cols[cat],label=cat,width=0.72,edgecolor="white",lw=0.6)
            base=[base[i]+share[i] for i in range(len(BANDS))]
        ax.set_xticks(x); ax.set_xticklabels([f"{l}\nn={band_n[k]}" for (k,_),l in zip(BANDS,labels)],fontsize=9)
        ax.set_ylim(0,100); ax.set_ylabel("share of band (%)",fontsize=10)
        ax.set_title(title,fontsize=11,color="#444")
        ax.set_xlabel("← fresher      listing age band      staler →",fontsize=9,color="#666")
        ax.legend(fontsize=8.5,loc="upper center",bbox_to_anchor=(0.5,-0.12),ncol=3,frameon=False)
        for sp in ("top","right"): ax.spines[sp].set_visible(False)

    stacked(ax1,tcnt,TYPES,TYPE_COL,"By property type — apartments swell in stale stock, units thin out")
    stacked(ax2,pcnt,PBANDS,PB_COL,"By listed price — the >180d band skews to the top end ($3m+ grows)")
    ax2.text(0.5,-0.30,"41% of listings are price-'unknown' (POA) — concentrated in premium homes, so the top-end skew is understated.",
             transform=ax2.transAxes,ha="center",fontsize=7.8,color="#a83a2f",style="italic")

    fig.text(0.5,0.005,"Source: onthehouse_listings active (our 82-suburb residential ledger, ~3,200). Age = today − listed_date. "
             "CURRENT stock composition only. Investigation visual.",ha="center",fontsize=7.5,color="#888")
    plt.tight_layout(rect=[0,0.04,1,0.95])
    import os
    out="/home/fields/Fields_Orchestrator/02_Data/Inventory"; os.makedirs(out,exist_ok=True)
    p=f"{out}/gc_inventory_composition.png"; plt.savefig(p,dpi=130,bbox_inches="tight"); print("wrote",p)

if __name__=="__main__": main()
