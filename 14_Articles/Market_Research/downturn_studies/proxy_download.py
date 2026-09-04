#!/usr/bin/env python3
"""Fetch bot-blocked study PDFs through the Bright Data unlocker proxy."""
import os, sys, requests

API = os.environ["BRIGHTDATA_API_KEY"]
ZONE = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker2")
h = {"Authorization": f"Bearer {API}"}
pw = requests.get(f"https://api.brightdata.com/zone/passwords?zone={ZONE}",
                  headers=h, timeout=30).json()["passwords"][0]
cust = "fieldsestate"
try:
    cust = requests.get("https://api.brightdata.com/status", headers=h, timeout=30).json().get("customer", cust)
except Exception:
    pass
proxy = f"http://brd-customer-{cust}-zone-{ZONE}-session-dl01:{pw}@brd.superproxy.io:33335"
proxies = {"http": proxy, "https": proxy}

jobs = [
 ("IMF_WP19-76_Ahuja-etal_Household-Debt-Consumption-Monetary-Policy-Australia.pdf","https://www.imf.org/-/media/files/publications/wp/2019/wpiea2019076.pdf"),
 ("IMF_SDN15-12_Cerutti-Dagher-DellAriccia_Housing-Finance-Real-Estate-Booms.pdf","https://www.imf.org/external/pubs/ft/sdn/2015/sdn1512.pdf"),
 ("IMF_WP12-217_Igan-Loungani_Global-Housing-Cycles.pdf","https://www.imf.org/external/pubs/ft/wp/2012/wp12217.pdf"),
 ("IMF_WP18-164_Geng_Fundamental-Drivers-House-Prices-Advanced-Economies.pdf","https://www.imf.org/-/media/files/publications/wp/2018/wp18164.pdf"),
 ("IMF_WP13-38_Hirata-etal_Global-House-Price-Fluctuations.pdf","https://www.imf.org/external/pubs/ft/wp/2013/wp1338.pdf"),
 ("IMF_WP2025-050_Not-All-Housing-Cycles-Are-Created-Equal.pdf","https://www.imf.org/-/media/files/publications/wp/2025/english/wpiea2025050-print-pdf.pdf"),
 ("IMF_2017_Mian-Sufi-Verner_Household-Debt-Business-Cycles-Worldwide.pdf","https://www.imf.org/-/media/files/conferences/2017-annual-research-conference/mian-s5.pdf"),
 ("IMF_WP20-11_Deghi-etal_Predicting-Downside-Risks-House-Prices_SSRN.pdf","https://papers.ssrn.com/sol3/Delivery.cfm/dp3623870.pdf?abstractid=3623870"),
 ("OECD_ECOWP746_Andre_Birds-Eye-View-OECD-Housing-Markets.pdf","https://www.oecd-ilibrary.org/a-bird-s-eye-view-of-oecd-housing-markets_5kmlh5qvz1s4.pdf"),
 ("Monash_WP54-15_Shi-etal_Dating-House-Price-Bubbles-Australian-Capitals.pdf","https://www.monash.edu/business/economics/research/working-papers/files/2015/5415timelinehousepriceshivaladkhanismythvahid.pdf"),
]
ok=fail=0
for fname,url in jobs:
    try:
        r = requests.get(url, proxies=proxies, timeout=120, verify=False)
        if r.status_code==200 and r.content[:4]==b"%PDF":
            open(f"pdfs/{fname}","wb").write(r.content)
            print(f"OK   [{len(r.content)//1024}K] {fname}"); ok+=1
        else:
            print(f"FAIL [{r.status_code} {r.headers.get('content-type','?')[:20]} {len(r.content)}b] {fname}"); fail+=1
    except Exception as e:
        print(f"ERR  {type(e).__name__} {fname}"); fail+=1
print(f"----- proxy: OK={ok} FAIL={fail}")
