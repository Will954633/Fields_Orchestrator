#!/usr/bin/env python3
"""Render a local PNG: GC sales-to-new-listings ratio (historical cycle) + the recent
market flip via days-on-market. Investigation/visual only — not a website chart.

Panel A: sales ÷ new-listings, quarterly 2016→2025 (property_timeline campaign-
derivation: new listings = campaign starts from sold + 'Listed - not sold' events,
list_date = event_date − days_on_market; sales = is_sold events). Solid to 2025-Q4;
2026 omitted — recent listings not yet concluded so the numerator is censored (would
read artefactually high). See market_pressure_metrics_scoping memory.

Panel B: GC-wide HOUSES median days-on-market, monthly 2024→2026, from domain_sold
(the fresh source) — shows the ~March-2026 strong→weak flip the ratio can't yet reach.
"""
import json, sys, statistics, collections
from datetime import date, timedelta
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shared.db import get_client
from shared.env import load_env
load_env()

GREEN="#166534"; COPPER="#b76749"; GREY="#9aa0a6"
c=get_client()

# --- Panel A data: ratio rows (from snlr_rows.json), keep to 2025-Q4 ---
rows=json.load(open("/tmp/claude-1001/-home-fields-Fields-Orchestrator/efc87bbe-977c-4ee5-ace0-d4daf2a584d2/scratchpad/snlr_rows.json"))["rows"]
def qkey(q): y,n=q.split("-Q"); return (int(y),int(n))
rows=[(q,s,n) for q,s,n in rows if qkey(q)<=(2025,4) and n]
qs=[q for q,_,_ in rows]; ratio=[s/n for _,s,n in rows]

# --- Panel B data: GC houses monthly sold + median DOM from domain_sold ---
ds=c["system_monitor"]["domain_sold"]
dom=collections.defaultdict(list); sold=collections.Counter()
for d in ds.find({"sold_date":{"$gte":"2024-01-01"},"dwelling":"house"},{"sold_date":1,"dom_days":1}):
    m=str(d["sold_date"])[:7]; sold[m]+=1
    dd=d.get("dom_days")
    if isinstance(dd,(int,float)) and 3<dd<365: dom[m].append(dd)
months=sorted(m for m in sold if m<="2026-08")   # drop part-month 2026-09
dom_med=[statistics.median(dom[m]) if dom[m] else None for m in months]

fig,(ax1,ax2)=plt.subplots(2,1,figsize=(12,9),gridspec_kw={"height_ratios":[3,2]})
fig.suptitle("Gold Coast — Sales vs New Listings, and the 2026 market turn",
             fontsize=15,fontweight="bold",y=0.98)

# Panel A
xa=range(len(qs))
ax1.plot(xa,ratio,color=GREEN,lw=2,marker="o",ms=3)
ax1.axhline(1.0,color=GREY,ls="--",lw=1)
ax1.text(0.3,1.02,"balance (1 sale per new listing)",color=GREY,fontsize=8)
def qi(q):
    return qs.index(q) if q in qs else None
for q,lbl,dy in [("2021-Q1","COVID boom —\nsales ≈ new supply (tight)",0.06),
                 ("2022-Q3","2022 rate shock —\nlistings pile up (soft)",-0.14)]:
    i=qi(q)
    if i is not None:
        ax1.annotate(lbl,(i,ratio[i]),fontsize=8,ha="center",
                     xytext=(i,ratio[i]+dy),color="#333",
                     arrowprops=dict(arrowstyle="-",color=GREY,lw=0.8))
ax1.set_ylabel("Sales ÷ new listings",fontsize=11)
ax1.set_title("Sales-to-new-listings ratio, quarterly (higher = tighter / seller's market)",
              fontsize=10,color="#555")
tk=[i for i,q in enumerate(qs) if q.endswith("Q1")]
ax1.set_xticks(tk); ax1.set_xticklabels([qs[i][:4] for i in tk],fontsize=9)
ax1.grid(axis="y",color="#f0ece1")
ax1.set_xlim(-0.5,len(qs)-0.5)
ax1.text(len(qs)-0.5,ax1.get_ylim()[0],
         " 2026 omitted — recent listings not yet\n concluded (numerator censored)",
         fontsize=7.5,color=COPPER,ha="right",va="bottom")

# Panel B
xb=range(len(months))
ax2.bar(xb,[sold[m] for m in months],color=GREEN,alpha=0.28,label="Houses sold / month")
ax2b=ax2.twinx()   # exception to one-axis rule: two different measures, clearly separated by color+label
ax2b.plot(xb,dom_med,color=COPPER,lw=2,marker="o",ms=3,label="Median days on market")
mar=months.index("2026-03") if "2026-03" in months else None
if mar is not None:
    ax2.axvline(mar,color=GREY,ls=":",lw=1)
    ax2.text(mar+0.2,ax2.get_ylim()[1]*0.9,"Mar 2026:\nvolume peaks,\nDOM starts rising",
             fontsize=8,color="#333")
ax2.set_ylabel("Houses sold / month",color=GREEN,fontsize=10)
ax2b.set_ylabel("Median days on market",color=COPPER,fontsize=10)
tkb=[i for i,m in enumerate(months) if m.endswith(("-01","-07"))]
ax2.set_xticks(tkb); ax2.set_xticklabels([months[i] for i in tkb],fontsize=8,rotation=0)
ax2.set_title("GC-wide houses, monthly (domain_sold) — the ~March-2026 strong→weak flip",
              fontsize=10,color="#555")
ax2.set_xlim(-0.5,len(months)-0.5)

fig.text(0.5,0.005,
         "Source: Domain via Fields scrapes. Panel A: property_timeline campaign-derivation (internally consistent basis). "
         "Panel B: domain_sold (fresh). Investigation visual.",
         fontsize=7.5,color="#888",ha="center")
plt.tight_layout(rect=[0,0.02,1,0.96])
import os
out="/home/fields/Fields_Orchestrator/02_Data/Sales_To_Listings"
os.makedirs(out,exist_ok=True)
path=f"{out}/gc_sales_to_listings.png"
plt.savefig(path,dpi=130,bbox_inches="tight")
print("wrote",path)
