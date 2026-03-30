# Sprint 1 Checkpoint Status — LIVE TRACKING

> **Last updated:** 2026-03-31 08:25 AEST
> **Sprint:** Sprint 1 — Funnel Proof + Instrumentation + Ad Waste Cut
> **Days remaining:** 4 (ends Friday April 4)

---

## Monday March 31 — CHECKPOINT REVIEW

| Item | Status | Owner | Notes |
|------|--------|-------|-------|
| Leads DB collection | ✅ DONE | AI | system_monitor.leads created with 4 indexes |
| PostHog dashboards | ❌ NOT DONE | Will + AI | Need "Weekly Acquisition" + "Engagement Depth" dashboards created |
| Lead capture event schema | ❌ NOT DONE | AI | Design doc for impression/expand/submit_start/submit_success |
| Ad waste cut | ❌ NOT DONE | AI + Will approval | ad-review-dump.py never ran. No audit memo. No decisions logged. |
| Email triage (grind) | ❌ NOT DONE | Will | Inbox zero pass |
| Content brief | ✅ DONE | AI | Week 1 + Week 2 posts and video transcripts in agent-deliverables/ |
| Feed_hook generation | ❌ NOT DONE | AI | 0/126 core suburb properties have feed_hook fields. Sprint 2 BLOCKER. |
| Backup scraper audit | ❌ NOT DONE | AI | No audit ran. SSH to 35.201.6.222 and assess Robina coverage. |

## Tuesday March 31 — TODAY'S CHECKPOINT

| Item | Status | Owner | Notes |
|------|--------|-------|-------|
| Price alerts live + instrumented | ❌ NOT DONE | AI builds, Will reviews | Component on property pages: "Get notified if price changes." One email field + one button. |
| PostHog events firing | ❌ NOT DONE | AI | price_alert_impression, price_alert_submit_start, price_alert_submit_success |
| Telegram notification on lead | ❌ NOT DONE | AI | Every new lead → instant Telegram to Will |
| Test on 3 property pages | ❌ NOT DONE | Will | Test end-to-end after AI builds it |

## Wednesday April 1 — TOMORROW

| Item | Status | Owner |
|------|--------|-------|
| Analyse Your Home form wired | NOT STARTED | AI builds, Will reviews |
| PostHog events for Analyse Home | NOT STARTED | AI |
| Telegram alert on submission | NOT STARTED | AI |
| Auto-acknowledge email | NOT STARTED | AI |

## Thursday April 2

| Item | Status | Owner |
|------|--------|-------|
| First 48h capture data review | NOT STARTED | AI + Will |
| First Facebook content posted | NOT STARTED | Will |
| First data video recorded | NOT STARTED | Will (scripts ready) |

## Friday April 3

| Item | Status | Owner |
|------|--------|-------|
| Decision Feed CTA wired | NOT STARTED | AI |
| Sprint review with decisions | NOT STARTED | Will + AI |
| Ad pause/scale recommendations | ❌ OVERDUE FROM MONDAY | AI |

---

## OVERDUE ITEMS — AI MUST ACTION THESE NOW

These items were supposed to be done by Monday. They are blocking Sprint 1 progress.

### 1. Ad Audit + Pause Memo (OVERDUE)
**What:** Run `python3 scripts/ad-review-dump.py --active` and produce a specific pause/scale memo with ad IDs, spend, sessions, and recommended action for each.
**Why overdue:** Was Monday's checkpoint. Never ran.
**Owner:** AI — autonomous. Produce the memo, Will approves the actual pauses.

### 2. Feed_hook Generation (OVERDUE — SPRINT 2 BLOCKER)
**What:** Generate feed_hook, feed_catch, feed_best_for, feed_quiz fields for all 126 core suburb properties.
**Why overdue:** Decision Feed cannot launch in Sprint 2 without these. 0/126 done.
**Owner:** AI — autonomous. Use the editorial pipeline or a lightweight generator.
**Target:** 80+ by Friday, 126/126 by Sprint 2 Monday.

### 3. Backup Scraper Audit (OVERDUE)
**What:** SSH to 35.201.6.222, check backup scraper status, compare Robina coverage vs primary Domain scraper, identify blocked agencies.
**Owner:** AI — autonomous. SSH access available.

### 4. PostHog Dashboard Setup (OVERDUE)
**What:** Create 2 PostHog dashboards via API or document exact setup steps for Will.
**Owner:** AI can draft the API calls or step-by-step instructions.

### 5. Lead Capture Event Schema (OVERDUE)
**What:** Document the PostHog event taxonomy: event names, properties, triggers. Already drafted in config/posthog_lead_capture_taxonomy.json but needs verification.
**Owner:** AI — verify and confirm ready for frontend implementation.

---

## ITEMS ONLY WILL CAN DO

These require Will's time — agents should add them to will_tasks.json:
- Record data videos (scripts are ready)
- Film Burleigh Beach videos (scripts are ready)
- Email triage (inbox zero pass)
- Approve ad pause recommendations (after AI produces the memo)
- Review and approve content before posting
- Test lead capture end-to-end after AI builds it
- PAYG research
- Ray White invoice extraction

---

## HOW AGENTS SHOULD USE THIS FILE

1. Read this file at the START of every session
2. Work through the OVERDUE items FIRST — these are the highest priority
3. Then work on TODAY'S checkpoint items
4. Then pre-work for tomorrow and beyond
5. For items only Will can do — add to will_tasks.json with urgency "today"
6. Update this file's status when you complete something (write to agent-memory)
