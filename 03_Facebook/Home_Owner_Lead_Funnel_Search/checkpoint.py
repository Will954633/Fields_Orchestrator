#!/usr/bin/env python3
"""
checkpoint.py — 4-hourly performance checkpoint for the Home Owner Lead Funnel.

Pulls per-ANGLE performance for the out-of-market lead TEST (and the GC funnel when live):
spend, impressions, CTR, leads, cost-per-lead, and the selling-intent breakdown
(Yes/Maybe/No) from the captured test leads. Auto-pauses clear losers, flags winners,
appends a timestamped block to 03_MONITORING.md, and Telegrams Will a summary.

Kill rule : spend>=$15 & 0 leads  OR  spend>=$20 & CPL>$25   -> auto-pause the ad set.
Scale flag: CPL <= $8 (report), <= $5 (alerts)               -> flag to duplicate+vary.

Self-monitors via job_run (cadence 4h). Cron suggestion: 0 */4 * * *
Usage: python3 checkpoint.py [--no-pause] [--no-telegram]
"""
import os, sys, json, argparse, requests
from datetime import datetime, timezone
from dotenv import load_dotenv
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client
try:
    from job_status import job_run
except Exception:
    job_run = None

API="https://graph.facebook.com/v21.0"; TOKEN=os.environ["FACEBOOK_ADS_TOKEN"]
HERE=os.path.dirname(os.path.abspath(__file__))
MON=os.path.join(HERE,"03_MONITORING.md")
KILL_SPEND_ZERO=15.0; KILL_SPEND_CPL=20.0; KILL_CPL=25.0
SCALE_CPL_REPORT=8.0; SCALE_CPL_ALERTS=5.0

def insights(campaign_id):
    r=requests.get(f"{API}/{campaign_id}/insights",params={
        "level":"ad","date_preset":"maximum",
        "fields":"ad_id,ad_name,adset_id,spend,impressions,clicks,ctr,actions",
        "limit":200,"access_token":TOKEN},timeout=40).json()
    out={}
    for a in r.get("data",[]):
        acts={x["action_type"]:float(x["value"]) for x in a.get("actions",[])}
        leads=acts.get("lead",0) or acts.get("onsite_conversion.lead_grouped",0)
        spend=float(a.get("spend",0))
        out[a["ad_name"]]={"adset_id":a["adset_id"],"spend":spend,
            "impr":int(a.get("impressions",0)),"clicks":int(a.get("clicks",0)),
            "ctr":float(a.get("ctr",0) or 0),"leads":int(leads),
            "cpl":(spend/leads if leads else None)}
    return out

def intent_breakdown():
    """selling-intent Yes/Maybe/No per ad_name from captured test leads."""
    coll=get_client()["system_monitor"]["fb_leads"]
    agg={}
    for d in coll.find({"test_market":True},{"ad_name":1,"fields":1}):
        an=d.get("ad_name","?")
        si=str((d.get("fields") or {}).get("selling_intent","")).lower()
        b=agg.setdefault(an,{"yes":0,"maybe":0,"no":0,"other":0})
        if si.startswith("yes"): b["yes"]+=1
        elif si.startswith("maybe"): b["maybe"]+=1
        elif si.startswith("no"): b["no"]+=1
        else: b["other"]+=1
    return agg

def pause_adset(adset_id):
    return requests.post(f"{API}/{adset_id}",data={"status":"PAUSED","access_token":TOKEN},timeout=30).json()

def telegram(msg):
    t=os.environ.get("TELEGRAM_BOT_TOKEN"); c=os.environ.get("TELEGRAM_CHAT_ID")
    if not (t and c): return
    try: requests.post(f"https://api.telegram.org/bot{t}/sendMessage",
        json={"chat_id":c,"text":msg,"parse_mode":"Markdown"},timeout=20)
    except Exception: pass

def run(do_pause=True, do_tg=True):
    ts=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    campaigns={}
    for name,fn in (("market_test_ids.json","TEST (SEQ ex-GC)"),("launch_ids.json","GC served")):
        p=os.path.join(HERE,name)
        if os.path.exists(p):
            campaigns[fn]=json.load(open(p))
    intents=intent_breakdown()
    lines=[f"\n### Checkpoint {ts}"]
    killed=[]; winners=[]
    total_spend=0.0; total_leads=0
    for label,ids in campaigns.items():
        data=insights(ids["campaign"])
        lines.append(f"\n**{label}** — campaign `{ids['campaign']}`")
        lines.append("| Angle | Spend | Impr | CTR | Leads | CPL | Intent Y/M/N |")
        lines.append("|---|--:|--:|--:|--:|--:|--|")
        for key,adid in sorted(ids["ads"].items()):
            # match by ad name (ads named by key, e.g. AN1_honest89 or AN1_honest89_TEST)
            row=next((v for an,v in data.items() if an.startswith(key)),None)
            if not row:
                lines.append(f"| {key} | — | — | — | — | — | — |"); continue
            total_spend+=row["spend"]; total_leads+=row["leads"]
            an=next((n for n in data if n.startswith(key)),key)
            ib=intents.get(an) or intents.get(key) or {}
            ibs=f"{ib.get('yes',0)}/{ib.get('maybe',0)}/{ib.get('no',0)}" if ib else "0/0/0"
            cpl=f"${row['cpl']:.2f}" if row["cpl"] else "—"
            lines.append(f"| {key} | ${row['spend']:.2f} | {row['impr']} | {row['ctr']:.2f}% | "
                         f"{row['leads']} | {cpl} | {ibs} |")
            # kill rule (TEST campaign only auto-pauses; GC handled by judgment)
            if "TEST" in label:
                kill = (row["spend"]>=KILL_SPEND_ZERO and row["leads"]==0) or \
                       (row["spend"]>=KILL_SPEND_CPL and row["cpl"] and row["cpl"]>KILL_CPL)
                if kill and do_pause:
                    pause_adset(row["adset_id"]); killed.append(f"{key} (${row['spend']:.0f}, {row['leads']} leads)")
                scale_thr = SCALE_CPL_ALERTS if "alert" in key.lower() else SCALE_CPL_REPORT
                if row["cpl"] and row["cpl"]<=scale_thr and row["leads"]>=2:
                    winners.append(f"{key} (CPL ${row['cpl']:.2f}, {row['leads']} leads)")
    # --- EARLY SIGNAL (before leads): impression share + dark/light + angle rollup ---
    tdata=insights(campaigns.get("TEST (SEQ ex-GC)",{}).get("campaign","")) if "TEST (SEQ ex-GC)" in campaigns else {}
    if tdata:
        ranked=sorted(tdata.items(),key=lambda kv:-kv[1]["impr"])
        top=[f"{an.replace('_TEST','')} ({v['impr']} impr, {v['leads']}L)" for an,v in ranked[:4] if v["impr"]>0]
        if top: lines.append(f"\n📈 **FB is favouring (impressions):** {', '.join(top)}")
        # dark vs light rollup
        bg={"dark":{"impr":0,"spend":0.0,"leads":0},"light":{"impr":0,"spend":0.0,"leads":0}}
        ang={}
        for an,v in tdata.items():
            for b in ("dark","light"):
                if an.endswith(b): bg[b]["impr"]+=v["impr"]; bg[b]["spend"]+=v["spend"]; bg[b]["leads"]+=v["leads"]
            base=an.replace("_dark","").replace("_light","")
            a=ang.setdefault(base,{"impr":0,"leads":0}); a["impr"]+=v["impr"]; a["leads"]+=v["leads"]
        lines.append(f"\n🌓 **Dark vs Light:** dark {bg['dark']['impr']} impr / {bg['dark']['leads']}L "
                     f"(${bg['dark']['spend']:.0f}) · light {bg['light']['impr']} impr / {bg['light']['leads']}L "
                     f"(${bg['light']['spend']:.0f})")
        angrank=sorted(ang.items(),key=lambda kv:-(kv[1]["leads"]*1000+kv[1]["impr"]))
        lines.append("🎯 **Angle rollup (both bg):** "+" · ".join(
            f"{b.replace('AN','A').split('_')[0]}:{d['leads']}L/{d['impr']}i" for b,d in angrank[:8]))
    if killed: lines.append(f"\n🔪 **Auto-paused (losers):** {', '.join(killed)}")
    if winners: lines.append(f"\n🏆 **Scale candidates:** {', '.join(winners)}")
    if not killed and not winners:
        lines.append(f"\n_(no kills/winners yet — total spend ${total_spend:.2f}, {total_leads} leads)_")
    block="\n".join(lines)
    with open(MON,"a") as f: f.write(block+"\n")
    if do_tg:
        tg=[f"📊 *Home Owner Funnel — {ts}*",f"Spend ${total_spend:.2f} · {total_leads} leads"]
        if winners: tg.append("🏆 "+"; ".join(winners))
        if killed: tg.append("🔪 paused: "+"; ".join(killed))
        telegram("\n".join(tg))
    print(block)
    return {"spend":round(total_spend,2),"leads":total_leads,"killed":len(killed),"winners":len(winners)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--no-pause",action="store_true")
    ap.add_argument("--no-telegram",action="store_true"); a=ap.parse_args()
    if job_run:
        # cadence 8h (not 1h): loop sleeps 11pm-8am, so a 1h cadence would false-STALE overnight
        with job_run("home_owner_funnel_checkpoint",cadence_hours=8,
                     title="Home Owner Funnel — checkpoint (hourly 8am-10pm)") as beat:
            r=run(not a.no_pause, not a.no_telegram); beat.metrics=r
            beat.detail=f"${r['spend']} spend, {r['leads']} leads, {r['killed']} killed, {r['winners']} winners"
    else:
        run(not a.no_pause, not a.no_telegram)

if __name__=="__main__": main()
