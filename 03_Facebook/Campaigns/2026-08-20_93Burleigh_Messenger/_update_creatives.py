import os, time, json, importlib.util, requests
spec=importlib.util.spec_from_file_location("lmc","launch_messenger_carousel.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
orig=m._call
def call(method,path,**f):
    for a in range(9):
        try: return orig(method,path,**f)
        except RuntimeError as e:
            if '"code": 17' in str(e): w=(a+1)*60; print("rl backoff",w,flush=True); time.sleep(w); continue
            raise
    raise RuntimeError("gave up")
m._call=call
st=json.load(open("campaign_ids.json"))
print("uploading images for hashes...",flush=True)
hashes={}
for arm in "ABC":
    for stem,*_ in m.CARDS[arm]:
        if stem not in hashes: hashes[stem]=m.upload_image(arm,stem)
old=[]
for arm in "ABC":
    o=st["arms"][arm]; old.append(o["creative_id"])
    ncid=m.create_creative(arm,hashes)                     # uses updated PRIMARY (attribution)
    call("POST",o["ad_id"],creative=json.dumps({"creative_id":ncid}))
    print(f"arm {arm}: ad {o['ad_id']} -> new creative {ncid} (old {o['creative_id']})",flush=True)
    o["creative_id"]=ncid
    json.dump(st,open("campaign_ids.json","w"),indent=2)
    time.sleep(2)
# delete old creatives
for cid in old:
    try: call("DELETE",cid); print("deleted old creative",cid,flush=True)
    except Exception as e: print("del skip",cid,str(e)[:60],flush=True)
    time.sleep(2)
# verify attribution present in one new creative
c=call("GET",st["arms"]["A"]["creative_id"],fields="object_story_spec")
msg=c["object_story_spec"]["link_data"]["message"]
print("VERIFY A message tail:",msg[-70:],flush=True)
print("DONE",flush=True)
