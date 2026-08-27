#!/usr/bin/env python3
"""
refresh_card01.py — swap the refreshed card 01 ("{Suburb} / Analysis" eyebrow) onto the
live Owner-Market ads.

Meta ad creatives are immutable, so "refresh the image" means: re-upload the cards, build a
NEW creative identical to the current one but with the new card-01 image, then repoint the
existing AD at the new creative (ad_id is preserved; the ad re-enters review but keeps
delivering on the old creative until approved — no downtime, no re-learning of the ad object).

Reuses launch_forms.create_creative / launch_campaign.create_creative verbatim so the rebuilt
creatives match the originals field-for-field (form CTA, links, primary text, card names).

Refreshes BOTH campaigns:
  - FORMS   (OUTCOME_LEADS)  — LIVE, ads ACTIVE  -> forms_ids.json
  - CAROUSEL(OUTCOME_TRAFFIC)— ads PAUSED         -> campaign_ids.json
Safe to run anytime; does not change budgets, targeting, or active/paused status.
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import launch_forms as lf
import launch_campaign as lc

print("· uploading 15 refreshed cards (Meta dedupes unchanged 02-05 by hash)")
hashes = lf.upload_images()   # same cards dir; shared by both campaigns

def refresh(mod, label, build_creative):
    state = json.load(open(mod.IDS_PATH))
    for sub in mod.ORDER:
        arm = state["arms"][sub]
        new_cid = build_creative(sub, arm, hashes)
        mod._call("POST", arm["ad_id"], mod.TOK, creative={"creative_id": new_cid})
        arm["prev_creative_id"] = arm.get("creative_id")
        arm["creative_id"] = new_cid
        print(f"  {label} {sub}: ad {arm['ad_id']} -> creative {new_cid}")
        json.dump(state, open(mod.IDS_PATH, "w"), indent=2)
    return state

print("\n· FORMS campaign (LIVE)")
refresh(lf, "forms", lambda sub, arm, h: lf.create_creative(sub, arm["form_id"], h))

print("\n· CAROUSEL campaign (ads paused)")
refresh(lc, "carousel", lambda sub, arm, h: lc.create_creative(sub, h))

print("\nDONE — new creatives repointed. IDs updated in forms_ids.json + campaign_ids.json.")
