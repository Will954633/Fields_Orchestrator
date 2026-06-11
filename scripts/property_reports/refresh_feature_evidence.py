"""Deterministic refresh of cohort premiums + featureEvidence for all reports
that have scarcity_features — applies the final per-sqm rung rules without
re-running Opus narratives. Flags any report whose narrative prose quotes a
figure no longer in the computed set (those need a full re-resolve)."""
import sys, json, re
sys.path.insert(0, '/home/fields/Fields_Orchestrator')
from shared.db import get_client, get_gold_coast_db
from shared.ru_guard import cosmos_retry
from scripts.property_reports.cohort_premiums import compute_cohort_premiums
from scripts.property_reports.scarcity_narrative import (
    cohort_premiums_to_feature_evidence, cohort_premiums_to_sold_cohort_premiums,
)

c = get_client()
gc = get_gold_coast_db()
coll = c['system_monitor']['property_reports']
needs_full = []
for doc in coll.find({'scarcity_features.cohort_premiums': {'$exists': True}}):
    slug = doc['slug']
    sf = doc['scarcity_features']
    premiums = compute_cohort_premiums(sf.get('notable_features') or [], gc, sf.get('catchment_suburbs') or [])
    fe = cohort_premiums_to_feature_evidence(premiums)
    legacy = cohort_premiums_to_sold_cohort_premiums(premiums)
    updates = {'scarcity_features.cohort_premiums': premiums}
    if doc.get('scarcity', {}).get('headline'):
        updates['scarcity.featureEvidence'] = fe
        updates['scarcity.soldCohortPremiums'] = legacy
    cosmos_retry(lambda u=updates: coll.update_one({'slug': slug}, {'$set': u}),
                 label=f'refresh_fe.{slug}')
    # validate narrative prose against the refreshed figure set
    allowed = set()
    for p in premiums:
        for f in ('premium_pct', 'like_for_like_pct', 'per_sqm_pct'):
            if p.get(f) is not None:
                allowed.add(round(abs(p[f]), 1))
    sc = dict(doc.get('scarcity') or {}); sc.pop('featureEvidence', None)
    blob = json.dumps({'s': sc, 'b': doc.get('buyers'), 'p': doc.get('positioning')}, default=str)
    stale = set()
    for m in re.finditer(r'([+-]?\d+(?:\.\d+)?)\s*%', blob):
        v = round(abs(float(m.group(1))), 1)
        # only flag values that look like premiums (skip common non-premium %s)
        if v in {round(abs(p['premium_pct']),1) for p in (doc['scarcity_features'].get('cohort_premiums') or []) if p.get('premium_pct') is not None} | \
                {round(abs(p.get('like_for_like_pct') or 0),1) for p in (doc['scarcity_features'].get('cohort_premiums') or [])}:
            if v not in allowed and v != 0.0:
                stale.add(v)
    nfeat = len((fe or {}).get('features', []))
    print(f"{slug}: refreshed ({nfeat} evidence features){' | STALE PROSE: ' + str(sorted(stale)) if stale else ''}")
    if stale:
        needs_full.append(slug)
print("\nNeeds full re-resolve:", needs_full or "none")
