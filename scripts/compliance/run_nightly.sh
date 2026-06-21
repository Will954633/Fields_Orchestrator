#!/usr/bin/env bash
# Nightly compliance record-keeping (PO Act 2014 / ACL — items K, L, N).
# Scheduled 23:55 AEST, after the 23:30 property-reports refresh, so it archives
# the freshest delivered appraisals.
#
#   1. appraisal_archive  — append-only, hash-chained snapshot of any new/changed
#                           delivered appraisal (K). Idempotent.
#   2. offsite_backup     — mirror all three compliance collections off the VM:
#                           GCS (guaranteed) + Google Drive (best-effort) (K/L/N).
#
# NOT run here: licensee_signoff baseline (one-time) and credential_register seed
# (run on demand when claims change). Ongoing sign-offs are event-driven.
set -uo pipefail
cd /home/fields/Fields_Orchestrator || exit 1
set -a; source /home/fields/Fields_Orchestrator/.env; set +a
PY=/home/fields/venv/bin/python

echo "===== $(date -Is) compliance nightly ====="
$PY -m scripts.compliance.appraisal_archive
$PY -m scripts.compliance.offsite_backup
echo "----- chain integrity -----"
$PY -m scripts.compliance.appraisal_archive --verify
echo "===== done $(date -Is) ====="
