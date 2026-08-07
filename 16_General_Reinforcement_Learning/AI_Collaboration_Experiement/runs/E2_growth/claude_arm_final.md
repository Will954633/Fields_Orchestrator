# claude_arm_final — E2_growth

Opus 5, read-only, identical brief to the GPT arm.

---

## FINDING 1: The on-demand listing builder has never once succeeded — its cron line does not export `.env`, so BrightData is off and Domain discovery returns 0 URLs every time

CATEGORY: conversion
CLAIM: Every visitor who opens an `/off-market/:slug` page for a home that is *currently listed* is 302-redirected to a `noindex` "we're building our coverage" dead-end, because the queue drainer that is supposed to build the real listing page fails 100% of the time — and the job reports `success` to the health board while doing it.
EVIDENCE:
- Cron line 34 (`crontab -l`, user `projects`): `*/3 * * * * source /home/fields/Fields_Orchestrator/.env && source /home/fields/venv/bin/activate && python3 .../scripts/build_listed_property.py --drain` — **no `set -a` / `set +a`**, unlike the neighbouring lines (e.g. line 227, the discovery-nightly job, which has it).
- Reproduced the exact cron env: `bash -c 'source .env && source venv/bin/activate && python3 -c "…"'` → `BRIGHTDATA_API_KEY: False`, while `COSMOS: False` yet `DB reachable: system_monitor` (because `shared/db.py:72` falls back to `config/settings.yaml`). `.env` contains `BRIGHTDATA_API_KEY` (36 chars) and has zero `export` lines. `build_listed_property.py` never calls `load_dotenv` (contrast `scripts/google_indexing.py:53-58`, which does and therefore works).
- `/home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/run_curlffi_suburb_scrape.py:271`: `use_unlocker = bool(os.environ.get('BRIGHTDATA_API_KEY'))` → `False` → direct fetch from the Akamai-blocked VM IP.
- `logs/build-listed.log:3486-3508`: `[Burleigh Waters] Page 1: 0 urls / 0 listed` → `Discovery complete: 0 unique URLs found` → `[build] FAILED 2/90 Christine Avenue … address not found among 0 live listings`. `scripts/build_listed_property.py:119-122` is the line that emits that text.
- A/B proof it is environmental, not upstream: the *same* `CurlCffiSuburbScraper('Burleigh Waters','4220').discover()` run from the orchestrator (systemd, `EnvironmentFile=/home/fields/Fields_Orchestrator/.env` → properly exported) found **59 URLs** at 2026-08-06 10:47 UTC — `system_monitor.listing_coverage` `{suburb: 'Burleigh Waters', discovered_urls: 59, domain_expected: 56}`. The drainer got 0 at 2026-08-06 01:14 and 2026-08-07 04:24.
- `system_monitor.property_build_requests`: **10/10 docs `status: "failed"`**, 8 distinct addresses, 2026-07-31 23:52 → 2026-08-07 04:24, every `detail` = "address not found among 0 live listings".
- `system_monitor.job_runs` latest for `listed_property_builder`: `status: success, detail: "queue drained"`, 0.0h ago.
- Live, right now: `curl -sL https://fieldsestate.com.au/off-market/28-parkside-circuit-robina` → `302` → `https://fieldsestate.com.au/building/28-parkside-circuit-robina`, `<title>28 Parkside Circuit — coverage in progress</title>`, `robots: noindex, nofollow` (`src/routes/building.$slug.tsx:52`). That slug is a real organic entry path in `system_monitor.organic_journeys` (session 019fa4ad…, 2026-07-27, `referring_domain: www.google.com.au`).
- The escape hatch on that page is one phone field (`src/routes/building.$slug.tsx:128-146` → `/.netlify/functions/building-alert`). `system_monitor.building_alerts` count = **0**.
- Redirect gate: `src/routes/off-market.$slug.tsx:143-146` — `if (listed?.on_market) { await enqueueListingBuild(doc); throw redirect('/building/…', 302) }`. `system_monitor.listing_status_cache`: 9 slugs currently `on_market: true` of 195 cached.
STATUS: VERIFIED — I inspected the cron line, reproduced its environment, read the scraper's gate line, read the failure log, counted the queue, and fetched the live redirect.
IMPACT: PostHog `sessions` (last 7 days): `/building` was the **entry path for 6 sessions, all 6 Organic Search** — 3.7% of the 163 organic sessions in that window, ≈26/month, ≈1/day. These are the single highest-intent cohort on the site: a Google searcher for an address that *just came to market*. All of them currently receive a `noindex` page with a phone form that has captured zero leads in its lifetime, and none of them will ever be forwarded to a real page. Zero of the 10 queued builds completed. Fixing this also restores the `/property/:slug` page + editorial that the whole redirect exists to deliver.
CONFIDENCE: HIGH
EFFORT: 15 minutes (add `set -a` / `set +a` to the cron line, or add `load_env()` to `build_listed_property.py`). Then ~1 hour to drain the 8 stuck addresses and re-check.
PROPOSED ACTION: Change cron line 34 to `*/3 * * * * set -a && source /home/fields/Fields_Orchestrator/.env && set +a && source /home/fields/venv/bin/activate && python3 …`. Better: add `from shared.env import load_env; load_env()` at the top of `scripts/build_listed_property.py` so it cannot depend on the caller. Then make the failure loud: `build_one()` should distinguish "discovery returned 0 URLs" (an infrastructure failure) from "address genuinely not listed", and `job_run` should record `status="error"` when discovery yields 0 for a suburb we know has 50+ live listings — today it reports `success`. Also fix the 6 other cron lines missing `set -a` (lines 8-13 of `crontab -l`).
FALSIFIED BY: Run `set -a && source .env && set +a && python3 scripts/build_listed_property.py --address "2/90 Christine Avenue" --suburb burleigh_waters --postcode 4220` and see it still report `0 live listings` — that would mean the block is upstream (BrightData zone dead, Domain layout change) rather than environmental. Alternatively, finding `BRIGHTDATA_API_KEY` set in the real cron process environment (e.g. via a `BASH_ENV` I did not find).

## FINDING 2: `google_indexing.py submit-new` has submitted 0 URLs for 9 consecutive nights, discards the error text, and advances its watermark anyway — so ~760 new pages were silently dropped and will never be retried

CATEGORY: seo
CLAIM: The nightly Google Indexing API push reports `Submitted 0/N URLs` every night since 2026-07-29, prints no error, has no `job_run` heartbeat, and unconditionally writes a new `last_run` watermark — so each night's failed batch is permanently excluded from the next night's "new/changed" window.
EVIDENCE:
- `logs/google-indexing.log`, last 9 daily runs (cron `0 1 * * *`, line 34 region): `Submitted 0/75`, `0/78`, `0/88`, `0/87`, `0/87`, `0/85`, `0/88`, `0/85`, `0/84 URLs.` Earlier runs in the same log succeeded: `109/109`, `110/110`, `81/81`, `82/82`, `87/87`.
- Error suppression: `scripts/google_indexing.py:154-161` `submit_url()` returns `{"status":"error","error":str(e)}`; the `submit-new` loop at `:365-373` counts `ok` but **never prints `result["error"]`** — unlike `cmd_submit_all` at `:279-281`, which does. The failing progress counter at `:371` prints `Submitted {i+1}/{len(urls)}` (attempts), which is why the log *looks* like it worked until the final line.
- Watermark advanced regardless: `:375-378` writes `{"last_run": now}` outside any success check. `logs/indexing-last-run.json` = `{"last_run": "2026-08-06T15:01:40Z"}`, mtime Aug 7 01:01.
- No heartbeat: `system_monitor.job_runs.distinct("job")` contains no `google_indexing`/`indexing` entry (only `seo_dashboard`, `seo_cycle`, `rl_seo_signal`, `seo_dispatch`, `samantha_seo_improvement`). This violates CLAUDE.md Rule 7, which is exactly why it went unnoticed for 9 days.
- A prior 429 burst is in the same log (`:1658-1667`, `DefaultPublishRequestsPerDayPerProject` limit 200) from a one-off `submit-batch 200` run — but the daily batches are 75-88 URLs, well under 200, so quota alone does not explain 9 straight zero-days.
STATUS: VERIFIED for the symptom, the error-suppression code path, the watermark bug and the missing heartbeat. The *root cause* of the API rejection is not established, because the error string is thrown away and I did not run the script (it mutates external state).
IMPACT: 75+78+88+87+87+85+88+85+84 = **757 URL submissions dropped and unrecoverable** through the incremental path. For a business where Organic Search is 85.8% of last-7-day sessions and 15,252 of 16,868 sitemap URLs are `/off-market` decks, the Indexing API is the primary mechanism for getting a newly built deck or a new listing crawled quickly. `seo_dashboard` currently reports 80.5% indexed on a sample of 87 — the ~19% unindexed tail is consistent with submissions failing.
CONFIDENCE: HIGH on the defect; MEDIUM on the magnitude of SEO harm (sitemap resubmission is a partial backstop).
EFFORT: 1 hour.
PROPOSED ACTION: (a) print/aggregate `result["error"]` in `cmd_submit_new` exactly as `cmd_submit_all` does, so the next run names the cause; (b) only write `indexing-last-run.json` when `ok > 0`, or persist a `failed_urls` list that the next run re-queues; (c) wrap the run in `job_run("google_indexing_submit_new", cadence_hours=24, …)` so `Submitted 0/N` surfaces as ERROR on the Process Registry; (d) re-submit the 757 dropped URLs with `submit-batch` once the cause is fixed.
FALSIFIED BY: Running `submit-new` with error printing enabled and seeing `0/N` accompanied by a benign reason (e.g. every URL already had a recent `notifyTime`), or GSC coverage showing those 757 URLs indexed anyway within days.

## FINDING 3: The middle step of the entire strategy has still never executed — 21 print-ready personalised mailers sit on disk and 39 addresses are cleared for postage, with zero dispatched and no postal vendor in existence

CATEGORY: growth
CLAIM: The brief's claim is **confirmed and should be sharpened**: it is not that the mail artifact doesn't exist — it exists, addressed and QR-tracked — it is that no dispatch mechanism, vendor, or scheduler has ever existed, so the inbound funnel has never been tested.
EVIDENCE:
- Artifacts on disk: `/home/fields/Fields_Orchestrator/11_House_Mini_Site/_shared/mailer/output/` — **21 per-address mailer PDFs plus `all_mailers.pdf` (17.8 MB combined print file)**; 16 dated 2026-07-17 16:31, 6 dated 2026-07-27 14:12 (e.g. `12-beaconsfield-drive-burleigh-waters.pdf`, `213-acanthus-avenue-burleigh-waters.pdf`). Template `_shared/mailer/mailer_template.html` carries `{{ADDR_STREET}}`, `{{QR_IMG}}`, addressee block. Plus 184 appraisal PDFs in `artifacts/appraisals_v4/` (2026-05-15 → 2026-08-07).
- Dispatch fields, `system_monitor.property_reports` (`print_appraisal` sub-doc present on 70/103): `queued_at` non-null **0/70**, `dispatched_at` **0/70**, `delivered_at` **0/70**, `tracking_ref` **0/70**. `dispatch_hold`: 39 released (`False`), 13 held, 51 unset — **39 addresses cleared to post, none posted**.
- `system_monitor.appraisal_pipeline` (133 docs, 2026-04-10 → 2026-08-06): `delivery_method: print_only` = **126**; `stage` = `draft_ready` 97 / `report_generating` 32 / `error` 4. Every value ever seen in `stage_history` is `form_submitted, welcome_sent, report_generating, draft_ready, error` — **no `printed`/`posted`/`dispatched`/`delivered` stage has ever existed**. `posted_at`, `dispatched_at`, `printed_at`, `mailed_at`, `print_batch_id`, `postage`, `tracking_number`: all 0 non-null.
- No vendor integration anywhere: repo-wide grep of `*.py` for `auspost|australia_?post|smartmail|clickandsend|lob\.com|mailhouse|directmail` → **zero hits**. `print_post_queue` collection does not exist.
- No scheduler: `crontab -l` (34 entries), `/etc/cron.d`, systemd timers and `config/process_commands.yaml` contain **no** reference to `generate_mailers`, `owner_article`, or any print/flyer job. `logs/fix-history/2026-08-01.md` says it plainly: *"there is no mailer yet; this is the substrate a later trigger reads."*
- The one apparent counter-example is not one: `system_monitor.physical_attribution` has 1 doc (`18 Collingwood Avenue, Robina`, 2 QR scans) but `recipient_email: preview@fieldsestate.com.au`, and `tracking-server/server.py:141-159` creates that doc lazily on scan via `$setOnInsert` — its existence proves a scan, not a posting. `system_monitor.print_assets` has 1 doc whose only `asset_scans` rows are `user_agent: curl/7.81.0` from `34.40.230.132` (this VM) — a self-test.
- Mailing lists were built and never used: `output/flyer_candidates_extended_2026-07-17.csv` (7,693 rows), `flyer_top1000_sold3yr_excl_2026-07-17.csv` (1,000), `flyer_wave1_merged_2026-07-19.csv` (22).
- And the audience shape justifies it: `system_monitor.lead_worklist`, non-test = 429 → **340 have a postal address (79%), 27 have an email (6.3%), 3 have a phone (0.7%)**. `system_monitor.crm_contacts` = 650 → 29 emails, 2 phones. `normalize_addresses` runs nightly and reported `255/266 postable` 20h ago — and `grep -rn "postable"` across both repos returns only the producer (`scripts/normalize_addresses.py`) and a sheet writer (`scripts/engagement_activity_to_sheet.py`). **Nothing consumes the postable flag.**
STATUS: VERIFIED — artifacts counted on disk, dispatch fields counted in the DB, vendor/scheduler absence established by exhaustive grep.
IMPACT: The business has 340 postable owner addresses and a validated print artifact. At the vendor quote already recorded in the flyer notes (~$1.20–1.70/unit DL), posting all 340 costs **≈$410–580 once**. That single spend converts the entire inbound thesis from unfalsifiable to measured. Against it: 14 conversions across all channels in 60 days (see Finding 4) is the current alternative.
CONFIDENCE: HIGH that nothing has been posted. MEDIUM on response rate, because there is no prior — which is precisely the finding.
EFFORT: 2-3 days, of which the code is ~4 hours: a `print_post_queue` collection, a `--dispatch` mode that stamps `queued_at`/`dispatched_at`/`tracking_ref`, and one vendor account. The rest is Will's decision and money.
PROPOSED ACTION: Post the 39 already-cleared addresses as wave 1 this week — do not build more machinery first. Stamp `print_appraisal.queued_at` / `dispatched_at` when the envelopes go out, so `physical_attribution` QR scans finally have a denominator. Add a `job_run("print_dispatch", cadence_hours=168)` heartbeat so a wave that never goes out shows as STALE rather than as nothing at all.
FALSIFIED BY: A non-null `print_appraisal.dispatched_at` on any `property_reports` doc, a `physical_attribution` doc whose `recipient_email` is not `preview@fieldsestate.com.au`, or an invoice from a print/mail vendor.

## FINDING 4: 14 conversions in 60 days, every single one the same form — and the surface that receives 52-66% of organic entries converts at 0.98%

CATEGORY: conversion
CLAIM: The measurable drop-off is not "owners don't convert" — it is that the off-market deck, which is where organic Google traffic actually lands, has essentially no working conversion path, while the only surface that ever converts (`analyse_home_address_submit`) is reached almost by accident.
EVIDENCE:
- Complete conversion count, all channels, 60 days: `logs/brain2-nightly-refresh.log:834` — `non-paid sessions: 995 | conversions(any channel): 14 | reconstructing: 624`. `system_monitor.all_conversions` = 13 docs.
- `system_monitor.organic_journeys` (619 reconstructed sessions, 2026-06-07 → 2026-08-06): `converted` = 11. `conversion_events` across all 11 = `analyse_home_address_submit` ×11, `analyse_home_submit_success` ×8. **No other conversion event of any kind fired in 60 days** — no price-alert, no booking, no ladder lead, no paid report.
- Conversion rate by entry-path prefix (same collection): `/off-market` 3/307 = **0.98%**; `/property` 3/175 = 1.71%; `/market-metrics` 1/47; `/analyse-your-home` 2/31 = 6.45%; `/articles` 0/11; `/for-sale` 0/3.
- **A concrete, named drop-off: 3 of the 11 submitted an address and never reached `analyse_home_submit_success` (27%).** The three: `/off-market/3-avocet-avenue-burleigh-waters` → submitted `6 Avocet Avenue, Burleigh Waters` (an in-coverage address); `/off-market/280-1-vue-boulevard-robina` → `43 Currumburra Road, Ashmore` submitted **twice**; `/` → `69 Port Jackson Boulevard, Clear Island Waters`. I then checked all 12 submitted addresses against the CRM: the 8 that succeeded each have a `property_reports` doc and a `lead_worklist` row; the 3 that failed have **0 rows in `leads`, `crm_contacts`, `property_reports` and `lead_worklist`**. Their addresses exist only as a PostHog event property. That is captured intent that is unreachable by any script we run.
- Engagement is not the constraint: 284 of 619 sessions exceeded 30s and **166 exceeded 120s**; the >120s-and-did-not-convert cohort is 44 on `/market-metrics`, 39 on `/off-market`, 28 on `/property`.
- Where organic actually lands (PostHog `sessions`, last 7 days, entry-path prefix, Organic Search only): `/off-market` 107 (65.6%), `/property` 35 (21.5%), `/market-intelligence` 7, `/building` 6, `/articles` 4. Over 30 days: `/off-market` 296 (52.3% of organic), `/property` 149 (26.3%).
STATUS: VERIFIED — counts and the 11 session traces come from `system_monitor.organic_journeys`; the channel/entry split from a HogQL query against the PostHog `sessions` table; the CRM cross-check from direct queries.
IMPACT: 14 conversions / 60 days = 0.23/day, and 11 of the 14 came through a form that only 31 of 1,520 sessions landed on directly. Recovering the 27% submit→success loss alone is +3 owner addresses per 60 days on today's volume (+27%). Bringing `/off-market` from 0.98% to `/analyse-your-home`'s 6.45% on 296 organic entries/30 days would be ~16 conversions/month versus today's ~7 across everything.
CONFIDENCE: HIGH on the numbers. MEDIUM on the cause of the 3 submit failures (I did not reproduce the form failure; two of the three addresses were out of coverage, which is a plausible unhandled path).
EFFORT: 2-3 days for the submit-failure path; 1 week for a real deck CTA.
PROPOSED ACTION: (1) Make `analyse-lead.mjs` persist the address on *every* submit, including out-of-coverage and build-failure paths — a lead row with `status: "no_coverage"` is worth more than a PostHog event nobody queries; today a failed submit leaves nothing actionable. (2) Instrument the gap: the funnel `analyse_home_address_submit` → `analyse_home_submit_success` is currently the only place we can see conversion die, and it is not on any dashboard. (3) On the discovery deck, the only capture is the intent *beacon* (no contact) and a strategy CTA — give the deck the same address-capture form that converts at 6.45%, positioned at the card where dwell peaks.
FALSIFIED BY: Finding conversion events other than `analyse_home_*` in PostHog for this window (which would mean `organic_journeys.CONV_EVENTS` is too narrow and my denominator-free claim "no other surface converts" is an artefact of the collector, not reality). This is the finding I would most want a second pair of eyes on.

## FINDING 5: `system_monitor.leads` is append-only — no code anywhere ever moves `status` off `"new"` or sets `first_response_at`, so the four real inbound leads (one of them from today) are structurally invisible as work

CATEGORY: process
CLAIM: Every lead that has ever arrived is still `status: "new"`, `first_response_at: null`, `next_action_at: null`, `lead_quality: null` — not because nobody replied, but because no write path exists that could record a reply.
EVIDENCE:
- The four non-test leads in `system_monitor.leads` (32 docs total; the rest are `will@fieldsestate.com.au`, `debug@test.com`, `offmarket_direct_test`, `000110003`):
  - `2026-04-09` `analyse_your_home` — `13 Terrace Court, Merrimac`
  - `2026-04-10` `analyse_your_home` — `21 Indooroopilly Court, Robina`
  - `2026-06-13` `price_alert` — `1701/116 Laver Drive, Robina`
  - **`2026-08-07T09:00:25Z` `price_alert` — `240/25 Lake Orr Drive, Robina`, i.e. 45 minutes before I ran the query**
  All four: `status='new'`, `owner='will'`, `first_response_at=None`, `next_action_at=None`, `lead_quality=None`, `notes=''`.
- No writer exists. Every occurrence of `first_response_at` in either repo is either an insert literal `null` (`price-alert-subscribe.mjs:277`, `analyse-lead.mjs:623`, `property-report-book-review.mjs:265`), a schema default, or documentation. `config/system_monitor_leads_schema.json:135` states the intended rule — *"Set first_response_at the first time status moves away from 'new'"* — and it is not implemented anywhere.
- All seven insert paths hardcode `status: 'new'`. The only `updateOne` against `leads` in the whole codebase is `property-report-book-review.mjs:243-248`, which touches `updated_at`, `last_review_request_at`, `$inc review_request_count` — never `status`. In Python, `scripts/crm_sync.py:532` and `scripts/samantha/lead_intelligence.py:235` only *read* `sm["leads"]`; there is no `update_one`/`update_many`/`find_one_and_update` against it.
- Notification does exist (I initially suspected it did not, and was wrong): all seven paths fire Telegram — `price-alert-subscribe.mjs:286-291`, `analyse-lead.mjs:679-688`, `property-report-book-review.mjs:389-391`, `offmarket-ladder-lead.mjs:74-78`, `square-payment.mjs:271-284`, `property-plan-submit.mjs:222-224`, `off-market-direct-test.mjs:251-257`.
STATUS: VERIFIED — grep-exhaustive across both repos plus direct queries on the four leads.
IMPACT: With 14 conversions per 60 days, every lead is ~7% of two months of output, and the system cannot answer "did we reply to this one?" or "how long did it take?". A price-alert lead landed today and there is no field that will ever change to show it was handled. Any SLA, follow-up-overdue, or response-time metric built on these fields returns a constant.
CONFIDENCE: HIGH
EFFORT: 3-4 hours.
PROPOSED ACTION: Add a two-field mutation to the ops dashboard's lead view (`status` dropdown, and set `first_response_at = now()` on the first transition off `new`), and a nightly `job_run("leads_unworked", cadence_hours=24)` that Telegrams any `status:"new"` lead older than 24h. At four real leads in four months the correct tool is a nag, not a CRM.
FALSIFIED BY: Any `leads` doc with `status != "new"` or a non-null `first_response_at`, or a mutation path I missed (e.g. a Google Apps Script writing back from the leads sheet).

## FINDING 6: The brief's "~91% of traffic from Google organic" is true only for the last 7 days; over 30 days organic is 37.2% and Paid Social is 40.5%

CATEGORY: growth
CLAIM: The stated organic share is an artefact of the Facebook campaign having been paused on 2026-07-30 — the 30-day picture is a roughly even paid/organic split, which matters because the funnel diagnosis differs sharply between the two.
EVIDENCE: HogQL against the PostHog `sessions` table (`brain2_util.hog_retry`, project 348370), grouping `$channel_type`:
- Last 7 days, 190 sessions: Organic Search 163 (**85.8%**), Direct 26 (13.7%), AI 1.
- Last 14 days, 468 sessions: Organic Search 300 (64.1%), Paid Social 104 (22.2%), Direct 58.
- Last 30 days, 1,520 sessions: **Paid Social 616 (40.5%)**, Organic Search 566 (37.2%), Organic Social 213 (14.0%), Direct 114.
- Last 60 days, 1,623 sessions: Paid Social 616 (38.0%), Organic Search 612 (37.7%).
- Corresponding entry pages, 30 days: `/analyse-your-home` 276 sessions of which **0 organic**; `/for-sale-v3` 256 of which 1 organic; `/article/*` 131 of which 0 organic. These are the paid landing pages.
- Also worth correcting: `system_monitor.organic_journeys` (which internal analysis leans on) is **not** a full-traffic sample. `scripts/brain2/organic_journey_build.py:217-227` reconstructs only "notable" sessions — those entering `/property`, `/analyse`, `/off-market`, or with ≥3 pageviews / >90s dwell. Its 80.1% organic share is therefore biased upward by construction. Its 14-conversion count *is* complete, because conversions are pulled separately for all channels at `:211-215`.
- The other quantified claims in the brief check out: `system_monitor.offmarket_discovery` = **26,297** docs, the nightly heartbeat reports **14,254 indexed**, and the live sitemap contains **15,252** `/off-market` URLs of 16,868 total (`curl https://fieldsestate.com.au/sitemap.xml | grep -c '<loc>'`). "~14,600 indexed" is fair. `/off-market` + `/property` = 87% of last-7-day organic entries, so "overwhelmingly bare-address searches on a single property page" holds.
STATUS: VERIFIED
IMPACT: Directional, not dollar-denominated: a strategy note that says "91% organic, so build for organic" is optimising for a traffic mix that only exists because spend stopped. Traffic is also small in absolute terms — 190 sessions in 7 days, ~27/day — which caps what any conversion-rate work can return and argues for Finding 3 (a channel that creates demand) over further on-site optimisation.
CONFIDENCE: HIGH
EFFORT: 1 hour (correct the memory note).
PROPOSED ACTION: Update `organic_offmarket_pivot_2026-07-23.md` to state the organic share *with its window*, and add a note to `organic_journey_build.py`'s docstring that its channel mix is a notable-session subset and must not be quoted as site-wide.
FALSIFIED BY: A PostHog bot/internal-traffic filter that inflates Paid Social specifically (e.g. ad-preview crawlers classified as Paid Social) — that would push the 30-day organic share back up.

## FINDING 7: The real-time high-intent owner alert stopped producing signals on 2026-08-04, and today's noise-suppression change makes it structurally impossible for the previous client bundle to ever alert again

CATEGORY: conversion
CLAIM: `system_monitor.offmarket_intent_signals` — the only *real-time* owner-lookup signal the discovery deck produces — has recorded zero new signals for three days, and the qualification floors added today require two fields the deployed client never sent, so any returning visitor on a cached bundle is now 100% suppressed. The change also breaks its own stated guarantee that every beacon is still recorded.
EVIDENCE:
- Signals by `created_at` (30 docs total): `2026-07-31` 6, `2026-08-01` 4, `2026-08-02` 3, `2026-08-03` 9, `2026-08-04` 8, then **nothing on 08-05, 08-06 or 08-07** — despite 107 organic `/off-market` entry sessions in the last 7 days.
- All 30 docs have `total_cards: None` and `dwell_ms: None` — the previous client never sent them.
- `netlify/functions/offmarket-intent-alert.mjs:52-61` `suppressionReason()`: `if (!Number.isFinite(totalCards) || totalCards < 6) return 'deck_too_short'; if (!Number.isFinite(dwellMs) || dwellMs < 45_000) return 'dwell_too_short';`. A beacon without those fields is therefore *always* suppressed — no grandfathering.
- Broken guarantee: the file header (`:26-27`) states *"Every beacon is still RECORDED (so nothing is lost and the floors can be re-tuned against real data); only qualifying ones send a Telegram."* But the client now gates **before** sending — `src/pages/OffMarketPage/discovery/DiscoveryDeck.tsx:365-371` only calls `fireIntentAlert(doc, "reached_end", …)` when `total >= MIN_CARDS_FOR_SCROLL_INTENT && deckDwellMs >= MIN_DECK_DWELL_MS` (constants at `:13-14`). Sub-threshold beacons never reach the server, so the data needed to re-tune the floors will never be collected. Comment and code disagree.
- The 6-card floor excludes a third of the estate: `offmarket_discovery` card counts over a 3,000-doc sample — 3 cards ×208, 4 ×46, 5 ×816, 6 ×142, 7 ×187, 8 ×360, 9 ×807, 10 ×434 → **1,070 (35.7%) of decks can never produce a scroll-intent alert by design**.
- No record of any alert ever having been sent: all 30 docs have no `alerted`/`notified` field (`{'None/None': 30}`).
STATUS: VERIFIED for the code contradiction, the missing-field suppression, the 35.7% figure, and the three-day gap. INFERRED for the *cause* of the 08-04 stop — today's change post-dates it, so something else (a deck bundle change, or the beacon path) stopped it first, and I did not isolate that.
IMPACT: This is the only signal that reaches Will while the owner is still on the page; everything else (`offmarket_home_signal` → `seller_intent` → worklist) is reconstructed the following night. It was firing 3-9/day. It is now firing 0/day, and on ~36% of decks it cannot fire at all.
CONFIDENCE: MEDIUM-HIGH on the mechanism; MEDIUM on why it stopped on 08-04 specifically.
EFFORT: 3-4 hours.
PROPOSED ACTION: Move the gate entirely server-side — have the client fire on every `reached_end` and let `suppressionReason()` decide, which is what the header already promises and what makes the floors tunable. Treat missing `totalCards`/`dwellMs` as `legacy_client` rather than as a suppression (record, don't alert). Then find the 08-04 regression by querying PostHog for the deck's scroll-depth/time-on-page events by day and comparing against the signal dates. Add a `job_run` heartbeat that goes STALE when a day passes with `/off-market` traffic but zero recorded beacons.
FALSIFIED BY: `offmarket_intent_signals` docs appearing with `created_at` on 08-05/06/07 that I missed because they were written under a different field name, or PostHog showing that nobody actually reached the end of a deck in those three days.

## FINDING 8: The PositioningCard email gate POSTs to a handler that does not exist — the email is discarded and the gate opens anyway

CATEGORY: correctness
CLAIM: A live email-capture form on the property page sends `{ action: 'positioning-lead' }` to `system-monitor`, which has no such action, then unlocks the gated content regardless — so it collects nothing and gates nothing.
EVIDENCE: `src/components/PositioningCard/PositioningCard.tsx` — form at `:275-287`; `handleEmailSubmit` at `:156-179` POSTs `{ action: 'positioning-lead', … }` to `/.netlify/functions/system-monitor` at `:162-172`; `:177-178` opens the gate unconditionally. `grep -rn "positioning-lead"` across the whole repo returns exactly **one** hit — that line. No handler in any `netlify/functions/*.mjs`. Mounted on the property page at `PropertyPage.tsx:1192-1211`, conditional on `positioning_analysis.status === 'published' && .public`.
STATUS: VERIFIED
IMPACT: Cannot be quantified from our data, which is itself the point — every email typed into it is lost with no trace, so there is no record of how many there were. It is one of only two email-capture forms on the highest-traffic page type (`/property` = 21.5% of last-7-day organic entries). Low absolute volume; near-zero cost to fix.
CONFIDENCE: HIGH
EFFORT: 1-2 hours.
PROPOSED ACTION: Either add a `positioning-lead` case to `system-monitor.mjs` that inserts into `leads` with `source: 'positioning_gate'` and fires the same Telegram as the other six paths, or remove the form. Leaving a form that silently discards input is worse than having no form. Add a CI check that every `action:` string sent from `src/` has a matching handler case — this class of bug is invisible to `tsc`.
FALSIFIED BY: A handler registered dynamically (e.g. an action map built from a directory scan) that my grep would not see.

## FINDING 9: `price-alert-subscribe` returns its response and closes the DB client before its notification promises resolve

CATEGORY: correctness
CLAIM: The only lead path that does not `await` its notifications is the one that produced 2 of the 4 real leads — so Will's Telegram, the email to Will, and the subscriber's own confirmation email can all be dropped when the Lambda container freezes on response.
EVIDENCE: `netlify/functions/price-alert-subscribe.mjs:284-290`:
```js
// Notifications (non-blocking)
const notifyData = { ...subscription, created_at: now };
Promise.all([ notifyTelegram(notifyData), notifyWill(notifyData), sendConfirmation(notifyData) ]).catch(() => {});
```
then `return new Response(...)` at `:292-295` and `finally { if (client) await client.close()… }` at `:302-304`. Every other lead path awaits: `analyse-lead.mjs:688` (`await Promise.all(notifications)`), `property-report-book-review.mjs:389`, `offmarket-ladder-lead.mjs:74`, `property-plan-submit.mjs:222`. All Telegram helpers early-return silently if `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are unset (e.g. `:15-17`) and swallow errors — there is no email/SMS fallback on Telegram failure anywhere.
STATUS: VERIFIED in code. The *consequence* is INFERRED: `system_monitor.telegram_sends` only begins 2026-08-05 and records VM-side sends, so I could not confirm whether the 2026-08-07 09:00 price-alert lead produced a Telegram or not.
IMPACT: 2 of the 4 real leads ever received came through this path, including today's. A dropped notification here means a genuine inbound owner is discovered only when someone opens the leads collection — which, per Finding 5, has no mechanism that would show it was unhandled. Also affects the subscriber's confirmation email, so the person who signed up may believe the alert did not register.
CONFIDENCE: MEDIUM-HIGH on the defect, LOW-MEDIUM on how often it actually bites (Netlify may finish in-flight promises before freezing).
EFFORT: 15 minutes.
PROPOSED ACTION: `await Promise.all([...])` before returning, as the other six paths do. Separately, record every outbound notification (including from Netlify functions) into `telegram_sends` so "was Will told?" becomes an answerable question — right now it is not.
FALSIFIED BY: A `telegram_sends`-equivalent record, or Will's Telegram history, showing a price-alert notification at 2026-08-07 19:00 AEST for `240/25 Lake Orr Drive`.

## FINDING 10: Four separate intent queues are written nightly and none has a field that could record acting on it

CATEGORY: process
CLAIM: The system is good at detecting intent and has no closing mechanism at all — the queues have no owner, action, status, or outcome field, so "worked" and "ignored" are indistinguishable by construction.
EVIDENCE:
- `system_monitor.lead_worklist`: 429 non-test rows, refreshed 19.5h ago. Fields are `priority` (`low` 339, `medium` 48, `test` 13, `high` 1, missing 40), `reason`, `signals`, `occupancy` — **no `status`, `contacted`, `worked`, `outcome`, `disposition`, or `action` field exists on any document**. The single `high`-priority row (`12 Beaconsfield Drive, Burleigh Waters`, owner-occupier, held 26.5y, currently withdrawn — a textbook pre-market seller) was first seen `2026-05-19` and its `reason` still reads *"Review + draft outreach."* Eleven weeks.
- `system_monitor.forsale_ladder_responses`: 22 rows (2026-07-27 → 2026-08-04), 15 with `answer_count >= 3` — anonymous visitors who answered 3-4 qualifying buying questions (suburbs, criteria). Only 3 `offmarket_ladder` rows exist in `leads`, all dated 2026-07-23 with phone `000110003` (test). So ~22 completed buyer briefs produced zero leads and zero follow-up.
- `system_monitor.offmarket_intent_signals`: 30 rows, no `alerted`/`notified` field at all (Finding 7).
- `system_monitor.property_reports`: 70 rows with a `print_appraisal` dispatch schema, all dispatch fields null (Finding 3).
- The one place a human is expected to act is a Google Sheet: `scripts/engagement_activity_to_sheet.py` writes `engagement_activity_ledger` (49 rows, 2026-07-15 → 2026-08-06, e.g. `"Anonymous — known by address: 41 Concord Circuit, Robina"`) and it is the sole consumer of `normalize_addresses`'s `postable` flag. The chain ends at a sheet.
STATUS: VERIFIED — field-presence counted across every document in each collection.
IMPACT: The detection layer is genuinely good and is the business's real asset: 262 contacts flagged from 285 Google→off-market sessions last night, 69 actionable seller-intent leads, 340 postable addresses. None of it can be measured as worked, so no learning loop can ever close — you cannot compute a contact-to-outcome rate on any of it. This is the reason Findings 3 and 5 have gone unnoticed for months.
CONFIDENCE: HIGH
EFFORT: 1 day for the schema + dashboard column; the discipline is the hard part.
PROPOSED ACTION: Add `{action_taken, action_at, outcome}` to `lead_worklist` and `offmarket_intent_signals`, default null, and one nightly `job_run("worklist_untouched", cadence_hours=24)` that Telegrams the count of `priority: high|medium` rows older than 7 days with `action_taken: null`. Today that alert would read "49 rows, oldest 80 days" — which is the number that should have been on a screen since May.
FALSIFIED BY: An outcome/status field living in a collection I did not check (e.g. `marketing_actions`, 6 docs, last written 2026-03-04 — I checked its recency but not whether it joins to worklist rows), or a Google Sheet column tracking dispositions that never writes back to Mongo.

## COVERAGE
CHECKED:
- `system_monitor.job_runs` — all 80 self-registered jobs, computed age vs `cadence_hours × 1.5`, and cross-checked every STALE row against `_PAUSED_JOBS` in `scripts/main_site_health_check.py:1460-1484`. **Null result worth stating: every stale heartbeat is correctly registered as deliberately paused** (RL/agent crons off 2026-07-30, Home Owner funnel off, `offmarket_sitemap_release`/`offmarket_coverage_scraper` off). I also verified the Nerang sitemap freeze is intentional, not a failure — `Gold_Coast.offmarket_sitemap_release` `{frozen: ['nerang'], frozen_note: "pulled back 2026-08-01 (Will)"}`. The silent failures I found are in jobs that have **no** heartbeat (`google_indexing`) or that report `success` while failing (`listed_property_builder`) — Rule 7's blind spot is not staleness, it is a wrapper that cannot tell success from failure.
- Full lead-path trace, server-side: all seven `system_monitor.leads` insert paths in `netlify/functions/`, their notification code, and every `first_response_at` / `status` writer in both repos.
- Every conversion surface on `/property` in DOM order (16 of them) and on the off-market deck; the `/off-market` → `/building` redirect gate; the `/building` page's poll-and-die loop.
- Live HTTP: `https://fieldsestate.com.au/off-market/28-parkside-circuit-robina` (302 → `/building/...`), `https://fieldsestate.com.au/sitemap.xml` (16,868 URLs, section breakdown).
- PostHog `sessions` via HogQL (project 348370): channel mix at 7/14/30/60 days, entry-path prefix × channel at 7/30 days, top entry pages at 30 days.
- Mongo: `leads` (all 32 docs individually), `lead_worklist` (429 non-test, field-presence audit), `crm_contacts` (650), `organic_journeys` (all 619, including the 11 converting sessions traced individually and cross-checked against `property_reports`/`crm_contacts`/`lead_worklist`), `property_build_requests` (all 10), `building_alerts`, `offmarket_intent_signals` (all 30), `forsale_ladder_responses` (all 22), `email_sends` (all 32), `telegram_sends` (18), `property_reports`, `appraisal_pipeline`, `print_assets`, `physical_attribution`, `engagement_activity_ledger`, `listing_coverage`, `listing_status_cache`, `offmarket_discovery` (card-count distribution), `Gold_Coast.offmarket_sitemap_release`, plus recency/count on ~25 other collections.
- Filesystem/config: `crontab -l` (all 34 entries, checked each for the `set -a` export gap), `/etc/cron.d`, systemd timers, `systemctl cat fields-orchestrator`, `logs/build-listed.log`, `logs/google-indexing.log`, `logs/brain2-nightly-refresh.log`, `scripts/build_listed_property.py`, `scripts/google_indexing.py`, `scripts/normalize_addresses.py`, `run_curlffi_suburb_scrape.py`, `scripts/brain2/organic_journey_build.py`, `shared/env.py`, `shared/db.py`, the mailer/owner-article/flyer toolchain and its 205 output PDFs.
- Reproduced the cron environment in a subshell to prove the `BRIGHTDATA_API_KEY` export gap, and confirmed the reverse case (`google_indexing.py` calls `load_dotenv` itself, so the same missing `set -a` does not break it — an important negative that stopped me from over-generalising the mechanism).

NOT CHECKED:
- Netlify function logs. Without them I cannot say whether today's price-alert Telegram actually fired (Finding 9), nor whether `offmarket-intent-alert` is receiving beacons and rejecting them versus not being called at all (Finding 7). This is the single largest gap in the report.
- I did not reproduce the `analyse_home_address_submit` → `submit_success` failure by submitting a form, so the 27% loss is measured but its cause is unconfirmed. Reading `analyse-lead.mjs`'s coverage/error branches end to end would likely name it.
- The Messenger auto-responder and the fridge-magnet `/fridge` landing page: I confirmed neither appears in any conversion event in 60 days but did not audit their code or webhook health. Both are named in the brief.
- Google Search Console directly — I used the mirrored `seo_landing_performance` (947 rows) and `seo_dashboard` heartbeat instead, so query-level intent (are the bare-address searchers owners or buyers?) is unexamined. That question is central to the whole strategy.
- The 42 paused RL/agent jobs' *outputs* (`rl_onsite_friction`, `rl_seo_actions`, `hypothesis_queue`, `ceo_proposals`) — a paused analyst may already have written the diagnosis I reconstructed by hand.
- Session recordings for the three failed address submits, which would show the failure directly.
- `/for-sale-v3` and `/for-sale-v4b` — 299 sessions over 30 days, entirely paid, and I did not open either page. Given the FB pause they are near-zero traffic now, but they were the second-largest entry surface last month.
- Cost: I quantified nothing in RU or dollars beyond the mailing estimate.

MOST LIKELY BLIND SPOT:
Finding 4 rests on `system_monitor.organic_journeys`, whose `CONV_EVENTS` list I did not read. If that list is narrower than the set of events the site actually fires, then "no surface other than the AYH form has converted in 60 days" would be an artefact of the collector rather than a fact about the business — and the `/off-market` deck's 0.98% could be understated. The 14-conversion total from `logs/brain2-nightly-refresh.log:834` derives from the same constant, so both numbers share the assumption. Everything else in this report I verified against two independent sources; this one I did not, and it is load-bearing for the ranking of Findings 4 and 7.

Secondarily: I found the `set -a` export gap on 7 cron lines and proved it breaks exactly one of them. I checked the counter-case (`google_indexing`) and it does not break, but I did not check the other five (`marketing-stage-tracker`, `build-article-index`, `extract-market-insights`, `post-performance-tracker`, `fb-photo-manager`) for whether they call `load_dotenv` or silently degrade the way the builder does. At least one of those is plausibly a second instance of Finding 1.
