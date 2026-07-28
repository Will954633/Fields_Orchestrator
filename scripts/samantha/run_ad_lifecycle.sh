#!/usr/bin/env bash
# Samantha ad-lifecycle DAILY run — invoked by cron (12:40 AEST, just after the
# 12:00 fb-metrics refresh so cull decisions use fresh ad_profiles data).
#
# Does both coded behaviours with live action:
#   1. cull-scan  — pause clear underperformers (>=2d, exposure floor, laggard vs
#                   sibling), Brain-2 archive + backfill first, log ad_decisions,
#                   drop a replacement brief in Will's running doc.
#   2. organic-promote — at most ~1/month, repost a genuine winner's creative as an
#                   organic page post (editorial-compliance gated).
# Self-reports to Systems Health via job_run("samantha_ad_lifecycle"). See CLAUDE.md
# Rules 3 (ad_decisions) + 7 (self-monitoring). Also run in-session by Samantha.
set -euo pipefail
cd /home/fields/Fields_Orchestrator
set -a
source ./.env
set +a
export GH_CONFIG_DIR=/home/projects/.config/gh
exec /home/fields/venv/bin/python3 scripts/samantha/ad_lifecycle.py run --execute "$@"
