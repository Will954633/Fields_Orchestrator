#!/usr/bin/env python3
"""
select_homes.py — the real, verified sold homes behind the "Before You List" cards,
and the query logic to re-find candidates when the campaign is refreshed.

Two things:
  1) FINAL_PICKS — the homes locked into the current creatives (documentation).
  2) find_candidates() — re-runs the windowed, fact-gated selection against Gold_Coast
     so a future refresh can surface fresh homes. Read-only. Never writes the DB.

Run:  python3 scripts/select_homes.py                 # prints candidate buckets
Env:  source /home/fields/venv/bin/activate ; set -a && source /home/fields/Fields_Orchestrator/.env && set +a

Rules baked in (CLAUDE.md): House + listing_status:sold; recency from the Domain
property-profile TIMELINE's newest Sale event (NOT sale_date, which can hold a prior
sale); DOM from that timeline event (seller-verifiable); non-waterfront only; every $
figure is a public sale price or a third-party (Domain) estimate gap.
"""
import sys, re, datetime as dt
sys.path.insert(0, "/home/fields/Fields_Orchestrator")

CORE = ["robina", "burleigh_waters", "varsity_lakes"]
WINDOW_DAYS = 180
WF_KW = ["waterfront", "canal", "pontoon", "lakefront", "riverfront", "water views", "absolute water"]

# ---------------------------------------------------------------- FINAL PICKS
# Cautionary homes are shown suburb-only (no street) in the creative; wins are named.
FINAL_PICKS = {
 "A1": dict(arm="A/loss",  named=False, label="A 5-bedroom Robina home",
            address="31 Huntingdale Crescent, Robina", beds=5,
            fig="Domain est $2,300,000 -> sold $1,910,000", dom=61, method="private treaty", sold="2026-03-09"),
 "A3": dict(arm="A/win",   named=True,  label="3 Whitehead Drive, Burleigh Waters",
            address="3 Whitehead Drive, Burleigh Waters", beds=4,
            fig="sold $1,965,000 (more than the A1 loss)", dom=2, method="private treaty"),
 "B1": dict(arm="B/trust", named=False, label="A 5-bedroom Varsity Lakes home",
            address="45 Majorca Crescent, Varsity Lakes", beds=5,
            fig="Domain est $2,120,000 -> sold $1,742,000 (est 22% too HIGH)", dom=23, sold="2026-04-02"),
 "B2": dict(arm="B/trust", named=False, label="A 4-bedroom Burleigh Waters home",
            address="130 Christine Avenue, Burleigh Waters", beds=4,
            fig="Domain est $1,440,000 -> sold $2,500,000 (est 42% too LOW, graded High)", dom=76, sold="2026-04-20"),
 "C1": dict(arm="C/win",   named=True,  label="29 Windemere Crescent, Varsity Lakes",
            address="29 Windemere Crescent, Varsity Lakes", beds=4,
            fig="sold $1,380,000", dom=2, method="private treaty"),
 "C2": dict(arm="C/win",   named=True,  label="56 Woody Views Way, Robina",
            address="56 Woody Views Way, Robina", beds=4,
            fig="sold $1,420,000", dom=10, method="private treaty"),
}
# Photos live in ../photos/<KEY>_<slug>.jpg  (pulled full-res via blobs.fieldsestate.com.au
# host-swap or bucket-api rewrite; Azure blob is decommissioned — see memory photo_full_res_serving).

# ---------------------------------------------------------------- candidate finder
def _num(v):
    s = re.sub(r"[^0-9]", "", str(v or "").split("-")[0]); return int(s) if s and len(s) >= 6 else None

def _sale_ev(d):
    v2 = d.get("scraped_data_v2") or {}; tl = v2.get("timeline") if isinstance(v2, dict) else []
    s = [e for e in (tl or []) if isinstance(e, dict) and e.get("category") == "Sale" and e.get("event_date")]
    s.sort(key=lambda e: str(e.get("event_date")), reverse=True); return s[0] if s else None

def _wf(d):
    desc = (d.get("agents_description") or d.get("description") or "").lower()
    return any(k in desc for k in WF_KW)

def _domain_mid(d):
    dv = d.get("domain_valuation_at_listing") or {}; return dv.get("mid") if isinstance(dv, dict) else None

def find_candidates():
    from shared.db import get_gold_coast_db
    db = get_gold_coast_db()
    cutoff = (dt.date.today() - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    over, trust, wins = [], [], []
    for col in CORE:
        for d in db[col].find({"listing_status": "sold", "property_type": "House"}):
            ev = _sale_ev(d)
            if not ev: continue
            sdate = str(ev.get("event_date"))[:10]; dom = ev.get("days_on_market")
            if sdate < cutoff or _wf(d) or not (d.get("address") or "").strip(): continue
            sp = _num(d.get("sale_price")); mid = _domain_mid(d); a = d.get("address")
            # OVERPRICING (loss): long DOM + sold below Domain estimate-at-listing
            if isinstance(dom,(int,float)) and dom >= 60 and sp and mid and mid > sp:
                over.append((round((mid-sp)/mid*100,1), dom, col, a, mid, sp))
            # TRUST: Domain estimate-at-listing vs actual, big miss either way
            if sp and mid and sp > 0 and abs((mid-sp)/sp) >= 0.15:
                trust.append((round((mid-sp)/sp*100,1), col, a, mid, sp, dom))
            # WIN: fast sale (proof homes) — prefer sold >= a comparable loss to avoid "cheaper=faster"
            if isinstance(dom,(int,float)) and 1 <= dom <= 12 and sp:
                wins.append((dom, col, a, sp))
    over.sort(key=lambda x:-x[0]); trust.sort(key=lambda x:-abs(x[0])); wins.sort(key=lambda x:(x[0],-x[3]))
    return {"cutoff": cutoff, "overpricing_loss": over[:12], "trust_estimate_miss": trust[:12], "fast_wins": wins[:15]}

if __name__ == "__main__":
    print("FINAL PICKS (locked into current creatives):")
    for k, v in FINAL_PICKS.items():
        print(f"  {k} [{v['arm']}] {v['label']}  |  {v['fig']}  |  DOM {v['dom']}")
    try:
        c = find_candidates()
        print(f"\nRE-FIND candidates (sold in last {WINDOW_DAYS}d, since {c['cutoff']}):")
        for bucket in ("overpricing_loss", "trust_estimate_miss", "fast_wins"):
            print(f"\n[{bucket}]")
            for row in c[bucket]: print("  ", row)
    except Exception as e:
        print("\n(candidate finder needs venv + .env loaded)", e)
