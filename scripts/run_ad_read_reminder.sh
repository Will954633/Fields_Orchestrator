#!/bin/bash
# One-time reminder — 2-day ad-performance read for the 6 Halo/Sabri copy tests.
# Set 2026-07-15 to fire 2026-07-17 09:00 AEST. Self-removes after firing.
cd /home/fields/Fields_Orchestrator
set -a && . .env && set +a
/home/fields/venv/bin/python3 scripts/telegram_notify.py "🔬 *2-Day Ad Read due* — the 6 Halo/Sabri address-entry copy tests now have ~2 days of data.

Prompt Claude on the VM to:
• Pull impressions / spend / CTR / link-clicks + downstream address-entries (Lead) and mini-site engagement per ad — *filtering datacenter-bot geo*
• Rank the variants (fear vs curiosity vs ease; headline vs none)
• Recommend cut / keep / reallocate
• Graduate the winner's optimisation to the Lead / minisite-engaged custom conversions

(proposer-only — approve before any spend/optimisation change)" >> logs/ad-read-reminder.log 2>&1

# Self-remove so it only fires once.
crontab -l 2>/dev/null | grep -v "run_ad_read_reminder.sh" | crontab -
