#!/usr/bin/env python3
"""
swap_forms_copy.py — repoint the 3 LIVE Owner-Market FORM ads at new creatives carrying
the updated closing CTA line + "Get Started" button (Will, 2026-08-28).

Meta creatives are immutable, so we rebuild each creative field-for-field via
launch_forms.create_creative (which now reads the new primary_text + CTA_TYPE), then
repoint the existing ad. Ad IDs are preserved; the ad re-enters review but keeps
delivering the old creative until approved — no downtime, no re-learning.

FORMS campaign only. Does not touch budgets, targeting, or active/paused status.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import launch_forms as lf

print("· uploading 15 cards (Meta dedupes unchanged by hash)")
hashes = lf.upload_images()

state = json.load(open(lf.IDS_PATH))
for sub in lf.ORDER:
    arm = state["arms"][sub]
    new_cid = lf.create_creative(sub, arm["form_id"], hashes)
    lf._call("POST", arm["ad_id"], lf.TOK, creative={"creative_id": new_cid})
    arm["prev_creative_id"] = arm.get("creative_id")
    arm["creative_id"] = new_cid
    print(f"  forms {sub}: ad {arm['ad_id']} -> creative {new_cid}")
    json.dump(state, open(lf.IDS_PATH, "w"), indent=2)

print("\nDONE — 3 FORM ads repointed to new creatives. forms_ids.json updated.")
