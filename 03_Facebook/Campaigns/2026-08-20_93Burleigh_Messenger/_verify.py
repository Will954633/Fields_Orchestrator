import os, time, json, requests, subprocess, shutil
TOK=os.environ["FACEBOOK_ADS_TOKEN"]; B="https://graph.facebook.com/v20.0"
st=json.load(open("campaign_ids.json"))
def api(http, path, **f):
    for a in range(9):
        p={k:(json.dumps(v) if isinstance(v,(dict,list)) else v) for k,v in f.items()}; p["access_token"]=TOK
        kw={"params":p} if http in ("GET","DELETE") else {"data":p}
        r=requests.request(http,f"{B}/{path}",timeout=60,**kw); j=r.json()
        e=j.get("error") if isinstance(j,dict) else None
        if e and e.get("code")==17: w=(a+1)*45; print("  rl backoff",w); time.sleep(w); continue
        return j
    return j

# campaign + adset + ad statuses
c=api("GET", st["campaign_id"], fields="name,objective,status,special_ad_categories")
print("CAMPAIGN:", c.get("name"),"|",c.get("objective"),"|",c.get("status"),"|",c.get("special_ad_categories"))
for arm,o in st["arms"].items():
    ad=api("GET", o["ad_id"], fields="name,status,effective_status")
    ase=api("GET", o["adset_id"], fields="name,daily_budget,optimization_goal,destination_type,status")
    print(f"  {arm}: adset[{ase.get('name')} ${int(ase.get('daily_budget',0))/100:.0f}/d {ase.get('optimization_goal')}/{ase.get('destination_type')} {ase.get('status')}] "
          f"ad[{ad.get('name')} {ad.get('effective_status')}]")

# previews
chrome=shutil.which("google-chrome") or shutil.which("chromium-browser")
for arm,o in st["arms"].items():
    pv=api("GET", f"{o['ad_id']}/previews", ad_format="MOBILE_FEED_STANDARD")
    body=pv.get("data",[{}])[0].get("body","")
    import re,html
    msrc=re.search(r'src="([^"]+)"', body)
    if not msrc: print(f"  {arm}: no preview iframe:", str(pv)[:200]); continue
    url=html.unescape(msrc.group(1))
    out=f"preview_live_{arm}.png"
    subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--hide-scrollbars",
                    "--force-device-scale-factor=1","--window-size=540,960",
                    f"--screenshot={out}",url],
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
    print(f"  {arm}: preview -> {out}", "OK" if os.path.exists(out) else "FAILED")
    time.sleep(2)
