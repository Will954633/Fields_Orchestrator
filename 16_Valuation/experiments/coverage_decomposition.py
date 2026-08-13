import sys
sys.path.insert(0,"/home/fields/Fields_Orchestrator")
from shared.db import get_client
from collections import Counter
def dig(d,p):
    c=d
    for k in p.split("."):
        if not isinstance(c,dict): return None
        c=c.get(k)
    return c
db=get_client()["Gold_Coast"]
tot=0; house=0; addressable=0; addr_valued=0
fail=Counter(); nonaddr=Counter(); addr_fail=Counter()
per=Counter()
for s in ["robina","varsity_lakes","burleigh_waters"]:
    for d in db[s].find({"listing_status":"for_sale"}):
        tot+=1
        ct=d.get("classified_property_type")
        rv=dig(d,"valuation_data.confidence.reconciled_valuation")
        reason=dig(d,"valuation_data.summary.exclusion_reason") or dig(d,"valuation_data.confidence.exclusion_reason")
        dr=dig(d,"valuation_data.confidence.directional_reason")
        conf=dig(d,"valuation_data.confidence.confidence")
        if ct!="House":
            nonaddr[("attached",ct)]+=1; continue
        house+=1
        # a house is ADDRESSABLE unless the envelope refused it or it's acreage
        if dr in ("above_design_ceiling","price_above_threshold","below_design_floor"):
            nonaddr[("envelope",dr)]+=1; continue
        if reason=="acreage":
            nonaddr[("acreage",reason)]+=1; continue
        addressable+=1; per[(s,"addressable")]+=1
        if rv: addr_valued+=1; per[(s,"valued")]+=1
        else: addr_fail[reason or conf or "(none)"]+=1
print(f"live for-sale total          : {tot}")
print(f"  classified House           : {house}")
print(f"  NOT addressable (by design): {tot-addressable}")
for k,v in nonaddr.most_common(): print(f"      {k}: {v}")
print(f"\nADDRESSABLE (detached house, envelope did not refuse): {addressable}")
print(f"  valued  : {addr_valued}  ({100*addr_valued/addressable:.1f}%)")
print(f"  unvalued: {addressable-addr_valued}")
for k,v in addr_fail.most_common(): print(f"      {k}: {v}")
print("\nper suburb addressable coverage:")
for s in ["robina","varsity_lakes","burleigh_waters"]:
    a=per[(s,"addressable")]; v=per[(s,"valued")]
    print(f"  {s:16s} {v}/{a}  ({100*v/a:.1f}%)" if a else f"  {s}: 0")
