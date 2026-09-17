#!/usr/bin/env python3
"""Data for the interactive inventory artifact:
  - gc_monthly:  GC-wide monthly stock-on-market by age band (SQM, 2010→now)
  - core3:       Robina/Varsity/Burleigh monthly totals (SQM)
  - band_mix:    CURRENT stock composition per age band, by property TYPE and PRICE
                 (onthehouse ledger) — the only type data that exists; SQM history
                 cannot be decomposed. Rendered as the hover breakdown, labelled current.
"""
import re, json, sys, collections, statistics
from datetime import date
sys.path.insert(0,"/home/fields/Fields_Orchestrator")
from curl_cffi import requests as cr
from shared.db import get_client
from shared.env import load_env; load_env()

TODAY=date(2026,9,17)
BANDS=["r30","r60","r90","r180","r180p"]
GC_POSTCODES=["4207","4208","4209","4210","4211","4212","4213","4214","4215","4216",
              "4217","4218","4219","4220","4221","4222","4223","4224","4225","4226",
              "4227","4228","4229","4230"]
CORE={"4226":"Robina","4227":"Varsity Lakes","4220":"Burleigh Waters"}

def scrape(pc):
    r=cr.get(f"https://sqmresearch.com.au/total-property-listings.php?postcode={pc}",impersonate="chrome120",timeout=30)
    if r.status_code!=200: return None
    m=re.search(r"var\s+data\s*=\s*(\[.*?\])\s*;",r.text,re.DOTALL)
    if not m: return None
    try: arr=json.loads(m.group(1))
    except: return None
    out={}
    for row in arr:
        y,mo=row.get("year"),row.get("month")
        if not y or not mo: continue
        rec={b:(row.get(b,0) or 0) for b in BANDS}
        if sum(rec.values())==0: continue
        out[f"{y}-{mo:02d}"]=rec
    return out

def parse_price(s):
    if not s: return None
    vals=[]
    for n,suf in re.findall(r'\$?\s*([\d,]+(?:\.\d+)?)\s*(m|million|k)?', str(s), re.I):
        try: v=float(n.replace(',',''))
        except: continue
        if suf and suf.lower().startswith('m'): v*=1_000_000
        elif suf and suf.lower()=='k': v*=1_000
        elif v<10000: v*=(1_000_000 if v<100 else 1000)
        if 100_000<=v<=30_000_000: vals.append(v)
    return min(vals) if vals else None
def ageband(d): return "r30" if d<30 else "r60" if d<60 else "r90" if d<90 else "r180" if d<180 else "r180p"
def norm_type(t):
    if t in ("House","Apartment","Unit","Townhouse"): return t
    if t in ("Villa","DuplexSemi-detached","Semi-Detached"): return "Villa/Duplex"
    return "Other"
def priceband(v):
    if v is None: return "unknown"
    for hi,lbl in [(600_000,"<$600k"),(1_000_000,"$600k-1m"),(1_500_000,"$1-1.5m"),
                   (2_000_000,"$1.5-2m"),(3_000_000,"$2-3m")]:
        if v<hi: return lbl
    return "$3m+"

def main():
    per={}
    for pc in GC_POSTCODES:
        d=scrape(pc)
        if d: per[pc]=d
    gc=collections.defaultdict(lambda: collections.Counter())
    for pc,d in per.items():
        for ym,rec in d.items():
            for b in BANDS: gc[ym][b]+=rec[b]
    months=sorted(m for m in gc if m>="2010-01")
    gc_monthly=[{"ym":m, **{b:gc[m][b] for b in BANDS}} for m in months]
    core3={}
    for pc,nm in CORE.items():
        d=per.get(pc) or {}
        core3[nm]={"postcode":pc,"series":[{"ym":m,"total":sum(d[m].values())} for m in sorted(d) if m>="2010-01"]}

    # CURRENT composition per band
    sm=get_client()["system_monitor"]
    tmix={b:collections.Counter() for b in BANDS}
    pmix={b:collections.Counter() for b in BANDS}
    tprices={b:collections.defaultdict(list) for b in BANDS}  # band -> type -> [prices]
    bn=collections.Counter()
    for r in sm["onthehouse_listings"].find({"active":True,"listed_date":{"$ne":None}},
            {"property_type":1,"display_price":1,"listed_date":1}):
        try: ld=date.fromisoformat(str(r["listed_date"])[:10])
        except: continue
        b=ageband((TODAY-ld).days); bn[b]+=1
        t=norm_type(r.get("property_type") or "Other")
        tmix[b][t]+=1
        pv=parse_price(r.get("display_price"))
        pmix[b][priceband(pv)]+=1
        if pv: tprices[b][t].append(pv)

    def spread(vals):
        """Interquartile (middle-50%) price range for a type within a band."""
        if len(vals)<5: return {"n_priced":len(vals)}
        q=statistics.quantiles(sorted(vals),n=4)  # [p25,p50,p75]
        return {"n_priced":len(vals),"p25":round(q[0]),"p50":round(q[1]),"p75":round(q[2])}
    band_mix={b:{"n":bn[b],"type":dict(tmix[b]),"price":dict(pmix[b]),
                 "type_price":{t:spread(v) for t,v in tprices[b].items()}} for b in BANDS}

    out={"generated":TODAY.isoformat(),"bands":BANDS,
         "band_labels":{"r30":"< 30 days","r60":"30–60 days","r90":"60–90 days","r180":"90–180 days","r180p":"> 180 days"},
         "gc_monthly":gc_monthly,"core3":core3,"band_mix_current":band_mix,
         "onthehouse_total":sum(bn.values())}
    p="/tmp/claude-1001/-home-fields-Fields-Orchestrator/efc87bbe-977c-4ee5-ace0-d4daf2a584d2/scratchpad/inventory_artifact_data.json"
    json.dump(out,open(p,"w"))
    print("wrote",p)
    print("gc months:",len(gc_monthly),months[0],"→",months[-1],
          " latest total:",sum(gc[months[-1]].values()),
          " onthehouse current:",out["onthehouse_total"])

if __name__=="__main__": main()
