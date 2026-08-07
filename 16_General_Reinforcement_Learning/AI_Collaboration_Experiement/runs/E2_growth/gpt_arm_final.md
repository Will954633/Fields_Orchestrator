# gpt_arm_final

Model `gpt-5.6-terra` via openai · recovered from 50 recorded tool calls · 30,192 in / 3,257 out · ~$0.07

## FINDING 1: The address-to-post funnel has generated 126 print-only appraisals but records no completed physical delivery
CATEGORY: conversion  
CLAIM: The proposed core acquisition mechanism—posting a tailored appraisal to an address that has shown intent—has not been evidenced as completed for any of the 126 print-only appraisal-pipeline records.  
EVIDENCE: Mongo aggregate, `system_monitor.appraisal_pipeline` (tool call 33): 94 records are `delivery_method: "print_only", stage: "draft_ready"` and 32 are `delivery_method: "print_only", stage: "report_generating"`; no delivered/mailed stage appeared in the grouped results. `scripts/owner_article/build_owner_article.py:7,145,208,766` implements a printed piece posted to the subject address and guards against mailing listed homes.  
STATUS: VERIFIED — I inspected the current pipeline-stage aggregate and the generator code; I could not establish whether any mail was sent manually outside this database.  
IMPACT: 126 prepared or partly prepared print-only items are not evidenced as mailed. The measurable address-intent sample is small but real: `all_conversions` contains 13 submissions, including six Organic Search entries landing on property/off-market pages, and all 13 have `contact_captured: false` (Mongo aggregate, `system_monitor.all_conversions`, tool call 36). Physical mail is therefore the only evidenced follow-up mechanism aligned with those captured addresses.  
CONFIDENCE: HIGH  
EFFORT: 3–5 days for a controlled first wave  
PROPOSED ACTION: Within one week, run a 25–50 address mail pilot: (1) select fresh, non-listed, owner-occupier candidates; (2) generate and print the existing owner article/appraisal; (3) physically lodge the batch; (4) assign each piece a unique QR/short URL; and (5) add immutable `printed_at`, `lodged_at`, `delivery_wave`, and response fields to `appraisal_pipeline` so “draft ready” cannot be mistaken for delivery. Use the existing candidate logic, which excludes contactable leads, listed/sold properties, and investor-occupied properties (`scripts/samantha/flyer_candidates.py:44-55`).  
FALSIFIED BY: A re-checkable mail-house receipt, Australia Post lodgement record, or an external delivery register tied to the 126 pipeline IDs shows that these records were physically mailed despite having no mailed/delivered state in `appraisal_pipeline`.

## FINDING 2: The only measured off-market “high-intent” signal was historically a false-positive stream, not an owner-enquiry channel
CATEGORY: correctness  
CLAIM: Off-market deck intent alerts did not identify actionable owner interest: all 30 recorded signals were `reached_end`, with zero CTA-click signals, and the recorded trigger was known to fire on page mount for one-card decks and internal devices.  
EVIDENCE: Mongo aggregate, `system_monitor.offmarket_intent_signals` (tool call 35): 30 signals, 37 hits, 26 distinct IDs, 25 addresses, all `_id: "reached_end"`, latest `2026-08-04`. `logs/fix-history/2026-08-07.md:644-660` records that all 30 historical signals were `reached_end`, zero were `cta_click`, 24 one-card deck exits occurred in 30 days, internal IDs generated alerts, and 3-card “completion” occurred in 8–10 seconds. `netlify/functions/offmarket-intent-alert.mjs:1-17,30-37` shows that the endpoint records anonymous deck signals and explicitly maintains an internal-device exclusion list.  
STATUS: VERIFIED — I inspected the signal aggregate, the incident record, and the live function’s captured-input/internal-ID definitions.  
IMPACT: 30/30 recorded “high-intent” signals (100%) were the non-action trigger type; none demonstrate a CTA action by a prospective homeowner. This means the alert stream cannot yet be used to decide whom to mail or contact, and it risks consuming operator attention with misleading Telegram alerts.  
CONFIDENCE: HIGH  
EFFORT: 4–8 hours  
PROPOSED ACTION: Treat `cta_click` and a qualified long-dwell/full-deck event as separate funnel stages, not as one “intent” bucket. Add a daily dashboard or query showing: raw reaches, qualified reaches, CTA clicks, unique non-internal IDs, matched physical addresses, and subsequent mail/QR responses. Do not create outreach tasks from historical `reached_end` records; use only post-fix, threshold-qualified events after validating them against session replay/PostHog properties.  
FALSIFIED BY: A post-fix query showing that historical or new `reached_end` records reliably correspond to non-internal visitors who subsequently submit an address, scan a mail QR code, or otherwise identify themselves at a materially higher rate than unqualified deck visitors.

## FINDING 3: Organic address submissions are being captured without contact details, but there is no evidenced operational hand-off from those submissions to physical outreach
CATEGORY: growth  
CLAIM: The site has captured address-level intent from Organic Search while capturing zero contacts in the conversion dataset, yet the available evidence does not establish a completed, tracked direct-mail follow-up from those address submissions.  
EVIDENCE: Mongo aggregate, `system_monitor.all_conversions` (tool call 36): 13 conversion records total, all `contact_captured: 0`; six are Organic Search entries from `/property/...` or `/off-market/...` pages, including `/off-market/3-avocet-avenue-burleigh-waters` on `2026-08-01`. `SCHEMA_SNAPSHOT.md:8812-8852` defines `all_conversions.submitted_address`, `entry_path`, `channel`, and `contact_captured`. Mongo aggregate, `system_monitor.appraisal_pipeline` (tool call 33) shows 126 print-only records remain in pre-delivery states rather than a completed mail state.  
STATUS: VERIFIED — I inspected the aggregate results; I could not establish whether every conversion record is eligible for mail, whether any was mailed manually, or the total organic-traffic denominator.  
IMPACT: At least six recorded organic submissions arrived through the exact property/off-market search-entry pattern the business is trying to monetize, but 0/13 recorded conversions captured contact details. The currently observed contact-capture rate in this dataset is therefore 0%; any value of these address submissions depends on rapid, compliant physical follow-up rather than email/phone nurture.  
CONFIDENCE: HIGH  
EFFORT: 1–2 days  
PROPOSED ACTION: Build an explicit daily “address admission → mail decision” queue sourced from `all_conversions.submitted_address`: deduplicate address/day, verify listing and occupancy status fresh, exclude ineligible properties, create an `appraisal_pipeline` record with source session/entry path, and require one terminal disposition—`mailed`, `suppressed`, `ineligible`, or `manual_review`. Measure time from submission to lodgement and QR-return rate by landing path.  
FALSIFIED BY: A traceable join from all eligible `all_conversions` records to a dated mail/delivery ledger shows that they already receive physical follow-up promptly and that the current appraisal-pipeline stages simply omit that operational state.

## FINDING 4: The lead worklist contains 49 non-test high/medium-priority address records, but its priority labels include stale-status warnings and should not be mailed without fresh verification
CATEGORY: process  
CLAIM: There is an immediately available prospect pool, but mailing it blindly would risk contacting already-listed homes because 29 of the 49 high/medium-priority records explicitly carry stale-status warnings or are already-listed classifications.  
EVIDENCE: Mongo aggregate, `system_monitor.lead_worklist` (tool call 37): 49 non-test, non-dismissed high/medium records with addresses: 1 high, 48 medium; 15 medium and 1 high carry `[status stale >14d — verify fresh first]`, while 8 medium records are explicitly classified “ALREADY LISTED.” `scripts/samantha/flyer_candidates.py:44-55` excludes records with email, `for_sale`/`sold` listing status, and investor occupancy; `scripts/samantha/flyer_candidates.py:16-18` requires fresh listing-status verification before a mail wave.  
STATUS: VERIFIED — I inspected the live worklist aggregate and the candidate-selection implementation.  
IMPACT: A maximum of 49 address-bearing high/medium records are available for review, but at least 8/49 (16.3%) are explicitly unsuitable as pre-market mail candidates because they are already listed; at least 16/49 (32.7%) carry a stale-status warning. These groups overlap cannot be determined from the aggregate, so the number safely mail-ready cannot be established.  
CONFIDENCE: HIGH  
EFFORT: 4–8 hours for verification and shortlist generation  
PROPOSED ACTION: Make the first mail pilot start with this pool only after a same-day listing/occupancy refresh. Produce a reviewed CSV with each exclusion reason and retain the snapshot used for the decision. Prioritize the one high-priority pre-market record and the medium records without an email address, current listing, investor status, or stale verification.  
FALSIFIED BY: A record-level review shows that the priority/reason aggregate was outdated or that the stale/already-listed labels do not correspond to actual current listing status.

## COVERAGE
CHECKED: `CLAUDE.md`; relevant `SCHEMA_SNAPSHOT.md` collection definitions; current aggregates for `appraisal_pipeline`, `all_conversions`, `offmarket_intent_signals`, and `lead_worklist`; the owner-article, flyer-candidate, nightly-lead-chain, off-market intent-alert, and seller-CTA source excerpts; `logs/fix-history/2026-08-07.md`; and the tail of `logs/nightly-lead-chain.log`.  
NOT CHECKED: Full PostHog traffic/session funnel and traffic denominator; live-page rendering and actual property-page CTA placement; complete Netlify-function execution logs; Messenger/Facebook lead-processing execution; mail-house/Australia Post records; individual appraisal records; and `system_monitor.job_runs` runtime status, because the supplied job-run query failed with a cursor/maxTimeMS error.  
MOST LIKELY BLIND SPOT: Physical mail or manual follow-up performed outside CosmosDB and therefore absent from `appraisal_pipeline`; I found no evidence of it, but the supplied record cannot rule it out.
