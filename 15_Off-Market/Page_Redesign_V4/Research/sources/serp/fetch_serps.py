#!/usr/bin/env python3
"""Fetch real Google SERPs for bare-address queries via Bright Data Web Unlocker."""
import json, os, re, sys, time
from urllib.parse import quote_plus
import requests

OUT = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ["BRIGHTDATA_API_KEY"]
ZONE = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker2")

QUERIES = json.load(open(os.path.join(OUT, "queries.json")))

def fetch(q):
    url = "https://www.google.com/search?q=%s&gl=au&hl=en&num=20" % quote_plus(q)
    body = {"zone": ZONE, "url": url, "format": "raw"}
    last = None
    for attempt in range(3):
        try:
            r = requests.post(
                "https://api.brightdata.com/request",
                headers={"Authorization": "Bearer " + KEY,
                         "Content-Type": "application/json"},
                json=body, timeout=180)
            upstream = r.headers.get("x-brd-status-code")
            if r.status_code == 200 and len(r.text) > 20000:
                return r.text, upstream, None
            last = "http=%s brd=%s len=%s body=%s" % (
                r.status_code, upstream, len(r.text), r.text[:300])
        except Exception as e:
            last = "exc=%r" % e
        time.sleep(8 * (attempt + 1))
    return None, None, last

results = []
for item in QUERIES:
    slug = item["slug"]
    path = os.path.join(OUT, slug + ".html")
    if os.path.exists(path) and os.path.getsize(path) > 20000:
        print("skip (cached)", slug, flush=True)
        results.append({**item, "ok": True, "cached": True,
                        "bytes": os.path.getsize(path)})
        continue
    html, upstream, err = fetch(item["query"])
    if html:
        open(path, "w", encoding="utf-8").write(html)
        print("OK  ", slug, len(html), "brd=", upstream, flush=True)
        results.append({**item, "ok": True, "bytes": len(html),
                        "brd_status": upstream})
    else:
        print("FAIL", slug, err, flush=True)
        results.append({**item, "ok": False, "error": err})
    time.sleep(4)

json.dump(results, open(os.path.join(OUT, "fetch_log.json"), "w"), indent=1)
print("done", sum(1 for r in results if r["ok"]), "/", len(results))
