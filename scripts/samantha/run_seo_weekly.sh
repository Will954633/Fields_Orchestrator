#!/usr/bin/env bash
# Samantha WEEKLY SEO-improvement run — invoked by cron (Sunday 08:00 AEST).
# Sources .env, sets gh config dir, runs the Max (Fable/Opus) agent on the SEO
# mission. The Python runner strips ANTHROPIC_API_KEY internally so billing is
# the Max subscription. Self-reports to Systems Health via job_run().
set -euo pipefail
cd /home/fields/Fields_Orchestrator
set -a
source ./.env
set +a
export GH_CONFIG_DIR=/home/projects/.config/gh
exec /home/fields/venv/bin/python3 scripts/samantha/seo_improvement_weekly.py "$@"
