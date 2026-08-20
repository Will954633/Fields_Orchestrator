import os, time, json, requests, importlib.util
TOK=os.environ["FACEBOOK_ADS_TOKEN"]; B="https://graph.facebook.com/v20.0"
camp="120252341379830134"

def api(http, path, **f):
    for attempt in range(9):
        payload={k:(json.dumps(v) if isinstance(v,(dict,list)) else v) for k,v in f.items()}
        payload["access_token"]=TOK
        kw={"params":payload} if http in ("GET","DELETE") else {"data":payload}
        r=requests.request(http, f"{B}/{path}", timeout=60, **kw); j=r.json()
        err=j.get("error") if isinstance(j,dict) else None
        if err and err.get("code")==17:
            w=(attempt+1)*60; print(f"  rate-limited, backoff {w}s", flush=True); time.sleep(w); continue
        return j
    return j

print("waiting 90s for rate limit to clear...", flush=True); time.sleep(90)
r=api("GET", f"{camp}/adsets", fields="id,name,status", limit="50")
for a in r.get("data",[]):
    d=api("DELETE", a["id"])
    print("deleted orphan adset", a["id"], a.get("name"), d, flush=True); time.sleep(5)
print("orphans cleaned. building...", flush=True)

spec=importlib.util.spec_from_file_location("lmc","launch_messenger_carousel.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
orig=m._call
def patched(method, path, **fields):
    for attempt in range(9):
        try: return orig(method, path, **fields)
        except RuntimeError as e:
            if '"code": 17' in str(e):
                w=(attempt+1)*60; print(f"  build rate-limited, backoff {w}s", flush=True); time.sleep(w); continue
            raise
    raise RuntimeError("gave up after backoff")
m._call=patched
m.build()
