#!/usr/bin/env python3
"""Ad-hoc: sample off-market URLs and check GSC index status. Writes JSON result."""
import json, re, time, urllib.request, random, sys
from collections import Counter
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY="/home/fields/.gcp-floor-plan-vision.json"
SITE="https://fieldsestate.com.au/"
SITEMAP="https://fieldsestate.com.au/sitemap.xml"
OUT="/home/fields/Fields_Orchestrator/scratch_offmarket_index_sample.json"
N=int(sys.argv[1]) if len(sys.argv)>1 else 400
SEED=int(sys.argv[2]) if len(sys.argv)>2 else 20260915

def bucket(cov):
    c=(cov or "").lower()
    if "submitted and indexed" in c or c=="indexed": return "Indexed"
    if "discovered" in c: return "Discovered - not indexed"
    if "crawled" in c and "not indexed" in c: return "Crawled - not indexed"
    if "duplicate" in c or "alternate page" in c or "canonical" in c: return "Duplicate / canonical"
    if any(x in c for x in["excluded","noindex","blocked","redirect","not found","soft 404"]): return "Excluded (noindex/redirect/blocked)"
    if c.startswith("error"): return "Inspection error"
    return "Other: "+str(cov)

def main():
    xml=urllib.request.urlopen(SITEMAP,timeout=90).read().decode("utf-8","replace")
    urls=[u for u in re.findall(r"<loc>(https://fieldsestate\.com\.au/[^<]*)</loc>",xml) if u.startswith("https://fieldsestate.com.au/off-market/")]
    total=len(urls)
    rnd=random.Random(SEED); rnd.shuffle(urls)
    sample=urls[:N]
    creds=service_account.Credentials.from_service_account_file(SA_KEY,scopes=["https://www.googleapis.com/auth/webmasters"])
    svc=build("searchconsole","v1",credentials=creds)
    buckets=Counter(); errors=0; done=0
    for u in sample:
        try:
            r=svc.urlInspection().index().inspect(body={"inspectionUrl":u,"siteUrl":SITE,"languageCode":"en-AU"}).execute()
            cov=r.get("inspectionResult",{}).get("indexStatusResult",{}).get("coverageState")
            buckets[bucket(cov)]+=1
        except Exception as e:
            errors+=1; buckets["Inspection error"]+=1
            if "quota" in str(e).lower() or "429" in str(e):
                buckets["_quota_hit"]+=1; break
        done+=1
        if done%25==0:
            json.dump({"total_offmarket":total,"target":N,"done":done,"errors":errors,"buckets":dict(buckets)},open(OUT,"w"),indent=2)
        time.sleep(0.15)
    indexed=buckets.get("Indexed",0)
    valid=done-errors
    pct=(indexed/valid*100) if valid else 0
    res={"total_offmarket":total,"target":N,"done":done,"valid":valid,"errors":errors,
         "indexed":indexed,"indexed_pct":round(pct,1),
         "not_indexed_pct":round(100-pct,1),
         "est_indexed":round(total*pct/100),"est_not_indexed":round(total*(100-pct)/100),
         "buckets":dict(buckets)}
    json.dump(res,open(OUT,"w"),indent=2)
    print(json.dumps(res,indent=2))

if __name__=="__main__": main()
