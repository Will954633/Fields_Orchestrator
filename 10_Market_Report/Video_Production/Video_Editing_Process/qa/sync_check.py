import json, re
words = json.load(open('words.json'))
def norm(s): return re.sub(r'[^a-z0-9]','',s.lower())
wn = [norm(x['w']) for x in words]
ws = [x['start'] for x in words]
eng = open('/home/fields/Feilds_Website/01_Website/src/components/MarketFlowProto/MarketFlowProto.engine.ts',encoding='utf-8').read()
arr = json.loads(re.search(r'var WALK_SEGMENTS=(\[\[.*?\]\]);', eng, re.S).group(1))
segs = [(float(t), txt) for t,txt in arr]

import bisect
rows=[]
for st, txt in segs:
    toks=[norm(w) for w in txt.split() if norm(w)]
    key=toks[:5]
    if not key: rows.append((st,None,None,0,txt[:46])); continue
    # candidate word indices within +/-18s of declared start
    lo=bisect.bisect_left(ws, st-18); hi=bisect.bisect_right(ws, st+18)
    best=None; bestscore=0; bestdist=1e9
    for i in range(lo,hi):
        s=0
        for k in range(len(key)):
            if i+k<len(wn) and wn[i+k]==key[k]: s+=1
            else: break
        if s>=2:
            dist=abs(ws[i]-st)
            if s>bestscore or (s==bestscore and dist<bestdist):
                best=i; bestscore=s; bestdist=dist
    if best is not None:
        rows.append((st, ws[best], round(st-ws[best],2), bestscore, txt[:46]))
    else:
        rows.append((st, None, None, 0, txt[:46]))

matched=[r for r in rows if r[1] is not None]
flagged=[r for r in matched if abs(r[2])>0.6]
print(f"segments {len(segs)}  matched {len(matched)}  |drift|>0.6s {len(flagged)}")
drifts=[r[2] for r in matched]
print(f"mean {sum(drifts)/len(drifts):+.2f}s  max {max(drifts):+.2f}  min {min(drifts):+.2f}")
print("worst 10 (high-confidence only, score>=4):")
for r in sorted([x for x in flagged if x[3]>=4],key=lambda x:-abs(x[2]))[:10]:
    print(f"  decl {r[0]:6.1f}  act {r[1]:6.1f}  drift {r[2]:+5.2f}  score {r[3]}  | {r[4]}")
# corrected: apply actual only when score>=4 AND |drift|>0.5 AND |drift|<=9 (guard against bad jumps)
corr=[]; nfix=0
for i,r in enumerate(rows):
    st,txt=segs[i]
    if r[1] is not None and r[3]>=4 and 0.5<abs(r[2])<=9:
        corr.append([round(r[1],2),txt]); nfix+=1
    else:
        corr.append([st,txt])
# enforce monotonic non-decreasing starts
for i in range(1,len(corr)):
    if corr[i][0]<corr[i-1][0]: corr[i][0]=corr[i-1][0]
open('walk_segments_corrected.txt','w').write("var WALK_SEGMENTS="+json.dumps(corr,separators=(',',':'))+";")
print(f"applied {nfix} corrections -> walk_segments_corrected.txt")
