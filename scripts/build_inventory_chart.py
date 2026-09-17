#!/usr/bin/env python3
"""Gold Coast stock-on-market (inventory) chart from SQM Research.

SQM total-property-listings.php embeds `var data = [{year,month,r30,r60,r90,r180,r180p}]`
— monthly count of listings on market by listing AGE band (all dwelling types combined;
this endpoint does NOT split house/unit). Total stock = sum of the five bands.
  r30=<30d  r60=30-60d  r90=60-90d  r180=90-180d  r180p=>180d

Renders a 2-panel local PNG:
  A: GC-wide total stock, stacked area by age band (2010→now) — total inventory + how
     stale it is (the >180d band swelling = a softening market).
  B: core-3 suburb total-stock lines (recent years) for suburb-level detail.

Investigation visual. Cross-check: latest GC-wide total should sit near the onthehouse
live active count (~3,345 all-residential, 2026-09).
"""
import re, json, sys, collections, statistics
from datetime import date
sys.path.insert(0,"/home/fields/Fields_Orchestrator")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from curl_cffi import requests as cr

BANDS=[("r30","< 30 days"),("r60","30–60 days"),("r90","60–90 days"),
       ("r180","90–180 days"),("r180p","> 180 days")]
# fresh -> stale ramp (green to copper/red)
BAND_COL={"r30":"#2f8f57","r60":"#7fae3f","r90":"#d6ad4a","r180":"#c9803f","r180p":"#a83a2f"}
GREEN="#166534"; COPPER="#b76749"; GREY="#9aa0a6"
GC_POSTCODES=["4207","4208","4209","4210","4211","4212","4213","4214","4215","4216",
              "4217","4218","4219","4220","4221","4222","4223","4224","4225","4226",
              "4227","4228","4229","4230"]
CORE={"4226":"Robina","4227":"Varsity Lakes","4220":"Burleigh Waters"}

def scrape(pc):
    url=f"https://sqmresearch.com.au/total-property-listings.php?postcode={pc}"
    r=cr.get(url,impersonate="chrome120",timeout=30)
    if r.status_code!=200: return None
    m=re.search(r"var\s+data\s*=\s*(\[.*?\])\s*;",r.text,re.DOTALL)
    if not m: return None
    try: arr=json.loads(m.group(1))
    except: return None
    out={}
    for row in arr:
        y,mo=row.get("year"),row.get("month")
        if not y or not mo: continue
        tot=sum(row.get(k,0) or 0 for k,_ in BANDS)
        if tot==0: continue
        out[f"{y}-{mo:02d}"]=row
    return out

def main():
    per={}
    for pc in GC_POSTCODES:
        d=scrape(pc)
        if d: per[pc]=d; print(f"  {pc}: {len(d)} months, latest total={sum(list(d.values())[-1].get(k,0) or 0 for k,_ in BANDS)}")
        else: print(f"  {pc}: no data")
    # GC-wide = sum across postcodes per month/band
    gc=collections.defaultdict(lambda: collections.Counter())
    for pc,d in per.items():
        for ym,row in d.items():
            for k,_ in BANDS: gc[ym][k]+=row.get(k,0) or 0
    months=sorted(gc)
    months=[m for m in months if m>="2010-01"]
    latest=months[-1]; gc_latest=sum(gc[latest][k] for k,_ in BANDS)
    print(f"\nGC-wide latest {latest}: total stock={gc_latest}  (onthehouse live ~3,345)")

    fig,(ax1,ax2)=plt.subplots(2,1,figsize=(13,10),gridspec_kw={"height_ratios":[3,2]})
    fig.suptitle("Gold Coast — Stock on Market (inventory) and how stale it is",
                 fontsize=16,fontweight="bold",y=0.985)

    # Panel A: GC-wide stacked area by age band
    x=range(len(months))
    base=[0.0]*len(months)
    for k,lbl in BANDS:
        vals=[gc[m][k] for m in months]
        top=[base[i]+vals[i] for i in range(len(months))]
        ax1.fill_between(x,base,top,color=BAND_COL[k],lw=0,label=lbl)
        base=top
    totals=[sum(gc[m][k] for k,_ in BANDS) for m in months]
    ax1.plot(x,totals,color="#14201a",lw=1.1,alpha=0.5)
    # markers
    def mi(ym): return months.index(ym) if ym in months else None
    for ym,lbl,dy in [("2022-09","2022 rate shock",0.9),("2026-03","~Mar 2026 flip",0.82)]:
        i=mi(ym)
        if i is not None:
            ax1.axvline(i,color="#14201a" if "flip" not in lbl else COPPER,ls=":",lw=1.1,alpha=0.7)
            ax1.text(i+1,max(totals)*dy,lbl,fontsize=9,color=COPPER if "flip" in lbl else "#333")
    ax1.set_ylabel("Listings on market (count)",fontsize=11)
    ax1.set_title("GC-wide, all dwelling types — stacked by listing age (fresh = green, stale = red)",
                  fontsize=10.5,color="#555")
    tk=[i for i,m in enumerate(months) if m.endswith("-01")]
    ax1.set_xticks(tk); ax1.set_xticklabels([m[:4] for m in months if m.endswith("-01")],fontsize=9)
    ax1.set_xlim(0,len(months)-1); ax1.grid(axis="y",color="#eee")
    ax1.legend(loc="upper left",fontsize=8.5,ncol=5,frameon=False,
               title="listing age band",title_fontsize=8.5)
    ax1.annotate(f"latest {latest}: {gc_latest:,} on market",
                 (len(months)-1,totals[-1]),fontsize=8.5,color="#14201a",
                 ha="right",va="bottom",xytext=(len(months)-1,totals[-1]*1.02))

    # Panel B: core-3 total-stock lines, recent years
    for pc,nm in CORE.items():
        d=per.get(pc)
        if not d: continue
        mm=[m for m in sorted(d) if m>="2016-01"]
        tt=[sum(d[m].get(k,0) or 0 for k,_ in BANDS) for m in mm]
        ax2.plot(range(len(mm)),tt,lw=2,marker="",label=f"{nm} ({pc})")
        xref=mm
    ax2.set_title("Core suburbs — total stock on market, monthly (all dwelling types)",fontsize=10.5,color="#555")
    ax2.set_ylabel("Listings on market",fontsize=11)
    tkb=[i for i,m in enumerate(xref) if m.endswith("-01")]
    ax2.set_xticks(tkb); ax2.set_xticklabels([xref[i][:4] for i in tkb],fontsize=9)
    ax2.set_xlim(0,len(xref)-1); ax2.grid(axis="y",color="#eee"); ax2.legend(fontsize=9,frameon=False)
    im=xref.index("2026-03") if "2026-03" in xref else None
    if im is not None: ax2.axvline(im,color=COPPER,ls=":",lw=1.1)

    fig.text(0.5,0.005,"Source: SQM Research total-property-listings (monthly stock on market by postcode, all dwelling types). "
             "GC-wide = sum of GC postcodes. Investigation visual.",ha="center",fontsize=7.5,color="#888")
    plt.tight_layout(rect=[0,0.02,1,0.965])
    import os
    out="/home/fields/Fields_Orchestrator/02_Data/Inventory"; os.makedirs(out,exist_ok=True)
    p=f"{out}/gc_inventory_stock_on_market.png"; plt.savefig(p,dpi=130,bbox_inches="tight")
    print("wrote",p)

if __name__=="__main__": main()
