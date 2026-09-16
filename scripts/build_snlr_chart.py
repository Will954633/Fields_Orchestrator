#!/usr/bin/env python3
"""Trailing-8-week sales-to-new-listings ratio (SNLR) — a snapshot leading indicator.

SNLR = sales in the trailing 8 weeks ÷ new listings that APPEARED in the trailing 8
weeks (both flows counted when they happen; new listings need NOT have concluded —
that's the point of a flow snapshot). Stepped weekly.

Sources (both onthehouse, free, complete incl. Valuer-General; houses):
  new listings / entries : system_monitor.onthehouse_listings   (by `listed_date`)
  sales / exits          : system_monitor.onthehouse_sold        (by `sold_date`, dwelling=house)

The onthehouse_listings ledger is append-only (retains listed_date + first_seen even
after a listing ends), so a window's new-listings count is stable. Core-3 has ledger
history from ~early 2026 (nightly job); GC-wide accrues from the 2026-09 seed forward.

Renders a local PNG. Investigation visual.
Usage: python3 scripts/build_snlr_chart.py [--scope core3|gcwide]
"""
import sys, argparse, collections
from datetime import date, timedelta
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shared.db import get_client
from shared.env import load_env
load_env()

GREEN="#166534"; COPPER="#b76749"; GREY="#9aa0a6"
CORE3={"robina-4226","burleigh-waters-4220","varsity-lakes-4227"}
WINDOW=56  # 8 weeks

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--scope",default="core3",choices=["core3","gcwide"])
    args=ap.parse_args()
    cl=get_client(); sm=cl["system_monitor"]; gc=cl["Gold_Coast"]
    sold=sm["onthehouse_sold"]
    # NEW LISTINGS: Domain first_listed (nightly for-sale scrape) — far more complete than
    # onthehouse's for-sale index (~30-40% only). Core-3 only. ⚠ ~26% retention on sold
    # docs, so older windows undercount listings (levels approximate; direction robust).
    # SALES: on-market only (exclude VG off-market transfers) to match the listings basis.
    label="Core 3 (Robina, Burleigh Waters, Varsity Lakes) — houses, on-market basis"
    listed=[]
    for s in ["robina","burleigh_waters","varsity_lakes"]:
        for d in gc[s].find({"first_listed_timestamp":{"$ne":None}},{"first_listed_timestamp":1}):
            listed.append(str(d["first_listed_timestamp"])[:10])
    sq={"suburb_key":{"$in":list(CORE3)},"property_type":"House"}
    sales=[str(d["sold_date"])[:10] for d in sold.find(sq,{"sold_date":1}) if d.get("sold_date")]
    listed.sort(); sales.sort()
    print(f"{args.scope}: {len(listed)} listing appearances ({listed[0] if listed else '-'}→{listed[-1] if listed else '-'}), "
          f"{len(sales)} house sales ({sales[0] if sales else '-'}→{sales[-1] if sales else '-'})")

    import bisect
    def count(sorted_dates, lo, hi):  # (lo, hi]
        return bisect.bisect_right(sorted_dates,hi)-bisect.bisect_right(sorted_dates,lo)

    # weekly steps; start where listing ledger has real coverage
    start=date(2026,1,1); end=date.today()
    xs=[]; snlr=[]; nlist=[]; nsale=[]
    d=start
    while d<=end:
        hi=d.isoformat(); lo=(d-timedelta(days=WINDOW)).isoformat()
        nl=count(listed,lo,hi); ns=count(sales,lo,hi)
        xs.append(d); nlist.append(nl); nsale.append(ns)
        snlr.append(ns/nl if nl>=5 else None)  # need a minimum base to be meaningful
        d+=timedelta(days=7)

    fig,ax=plt.subplots(figsize=(12,6))
    valid=[(x,y) for x,y in zip(xs,snlr) if y is not None]
    if valid:
        vx,vy=zip(*valid)
        # last 2 points provisional (sales posting lag)
        ax.plot(vx[:-2] or vx,vy[:-2] or vy,color=GREEN,lw=2.2,marker="o",ms=4)
        if len(vx)>2:
            ax.plot(vx[-3:],vy[-3:],color=GREEN,lw=2.2,ls=":",marker="o",ms=4,alpha=0.7)
    ax.axhline(1.0,color=GREY,ls="--",lw=1); ax.text(xs[0],1.02,"balance (1 sale per new listing)",color=GREY,fontsize=8)
    import datetime as _dt
    ax.axvline(_dt.date(2026,3,15),color=COPPER,ls=":",lw=1.2)
    ax.text(_dt.date(2026,3,17),ax.get_ylim()[1]*0.92 if valid else 1,"~Mar 2026\nmarket flip",color=COPPER,fontsize=9)
    ax.set_title(f"Sales-to-New-Listings Ratio — trailing 8 weeks, weekly  ·  {label}",fontsize=12,fontweight="bold")
    ax.set_ylabel("Sales ÷ new listings (8-wk)"); ax.grid(axis="y",color="#f0ece1")
    ax.text(0.99,0.03,"dotted = last 2 weeks provisional (sales posting lag)",transform=ax.transAxes,
            ha="right",fontsize=7.5,color=COPPER)
    fig.text(0.5,0.005,"Source: onthehouse — new listings by listedDate (entries ledger), house sales by sold_date. "
             "Houses. Investigation visual.",ha="center",fontsize=7.5,color="#888")
    plt.tight_layout(rect=[0,0.02,1,1])
    import os
    out="/home/fields/Fields_Orchestrator/02_Data/Sales_To_Listings"; os.makedirs(out,exist_ok=True)
    path=f"{out}/gc_snlr_trailing8w_{args.scope}.png"
    plt.savefig(path,dpi=130,bbox_inches="tight"); print("wrote",path)
    # print the recent series for the record
    print("recent trailing-8wk SNLR:")
    for x,y,nl,ns in list(zip(xs,snlr,nlist,nsale))[-12:]:
        print(f"  {x}  sales={ns:>3} newlist={nl:>3} snlr={(f'{y:.2f}' if y else '-')}")

if __name__=="__main__": main()
