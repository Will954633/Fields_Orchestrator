# 09_Appraisals — Property Appraisal System

> **Mission:** Build the most thorough, transparent, beautifully-built appraisal report in the Australian market — so that, after reading it, choosing any other agent feels irrational.

This folder contains both the **strategic plan** for the next-generation Fields Appraisal Report and the **technical pipeline** that currently produces it.

---

## Strategy documents (read in order)

A nine-document strategy package designed to be read top-to-bottom. Each builds on the previous. Every claim cites a source.

| # | Document | Purpose |
|---|---|---|
| 00 | [Strategy](00_strategy.md) | The single sentence, the job-to-be-done, the three readers, the moat, the format strategy. The parent of every other doc. |
| 01 | [Psychology Principles](01_psychology_principles.md) | The science under every layout/copy decision — Kahneman & Tversky, Genesove & Mayer, Cardella & Seiler, McGuire, Loewenstein, Cialdini, peak-end rule, narrative transportation. With effect sizes. |
| 02 | [Report Blueprint](02_report_blueprint.md) | Page-by-page across three editions (Digital Quick-Read, Print Master, Living Microsite). Every page's job-to-be-done, reader takeaways at 5 / 60 / 600 seconds, data inputs, psychology applied. |
| 03 | [Competitive Audit](03_competitive_audit.md) | Where Australian agencies fall short; where international leaders fall short; the open positioning Fields can take; concrete authority numbers; the May 6 content regression flagged as urgent. |
| 04 | [Content Modules](04_content_modules.md) | 39 reusable building blocks (M1–M39). Each lists assertion, inputs, source, voice, length, where it appears, when to skip. The editorial review checklist that becomes a render-time gate. |
| 05 | [Visual System](05_visual_system.md) | Colour, typography, grid, photography rules, chart discipline (Tufte / FT), print object specs, what we don't do. |
| 06 | [Production Plan](06_production_plan.md) | Existing pipeline audit, gap analysis, four parallel build tracks, critical-path engineering changes, QA gates, cost model. |
| 07 | [Review Passes](07_review_passes.md) | Multi-angle critique — psychology / data / design / distribution / moat / legal / "would I sign?" passes. Where the strategy is strong vs vulnerable. |
| 08 | [Roadmap](08_roadmap.md) | 90-day delivery plan, Phase 0 → Phase 7. Sprint by sprint. Quarterly milestones. |

**The single highest-leverage action right now:** Phase 0 in [`08_roadmap.md`](08_roadmap.md) — restore April 10 v2 content quality on the May 6 design (the trade-off panel currently renders as placeholder boilerplate, the strengths bullets lost their dollar quantification, and the specs say "6bd" when source is 5bd). Once that is locked, ship the modules competitors don't have.

### Quick links into the strategy

- **Master moat:** [03 §2 — leaders win on one of three axes; Fields can take all three](03_competitive_audit.md)
- **Editorial review checklist (render gate):** [04 §G](04_content_modules.md)
- **Citation table (locked):** [01 §8](01_psychology_principles.md)
- **Page-by-page spec:** [02](02_report_blueprint.md)
- **Phase 0 — stop the regression (Week 1):** [08](08_roadmap.md)

### Outstanding follow-ups

- **Google Drive folder** at https://drive.google.com/drive/folders/1iydAwTm7SNWVhAwyKEFLzFfcUMeeb8AD could not be read (`invalid_grant` on stored OAuth credentials). Refresh credentials at `/home/fields/.gdrive-server-credentials.json` to unblock; review folder for any additional reference appraisals not yet incorporated into the strategy.
- **May 6 design-style render content regression** vs April 10 v2 — documented in [03 §8](03_competitive_audit.md). Highest-priority fix.

---

## Technical Pipeline (existing system)

End-to-end map of the appraisal pipeline triggered when a homeowner submits their address at [https://fieldsestate.com.au/analyse-your-home](https://fieldsestate.com.au/analyse-your-home), through to the branded PDF report and Telegram-tracked engagement.

The first real customer to receive a report through this flow was **Dee** (13 Terrace Court, Merrimac, QLD 4226). Her PDF is saved here: [2026-04-10_13-terrace-court_dee_v2.pdf](2026-04-10_13-terrace-court_dee_v2.pdf).

A designer (Marty) later supplied a styled mock of the cover + Fields Take page — see [4274 - Marty_Fields - Property Report_FA.pdf](4274 - Marty_Fields - Property Report_FA.pdf). On 2026-05-06 the report template ([templates/seller_report_v2.html](../templates/seller_report_v2.html)) was rewritten to match that style, and Dee's report regenerated in the new style: [2026-05-06_13-terrace-court_dee_designer-style.pdf](2026-05-06_13-terrace-court_dee_designer-style.pdf). The pre-restyle template is preserved at `templates/seller_report_v2.html.bak.before-designer-style`.

### Designer assets in use

| Asset | Path | Used for |
|-------|------|----------|
| Light/Dark SVG icons | [templates/icons/](../templates/icons/) (mirrors `09_Appraisals/Icons/`) | Tick / House / Location bullets in the Strengths block, and any future icon usage |
| Outline F-mark (decorative) | inlined in template as SVG | Top-left ornament on the cover |
| Solid F-mark | inlined in template as SVG | Page-header right corner; "Smarter with Data" footer |
| Fields wordmark | [templates/fields-logo-white.png](../templates/fields-logo-white.png) | Top-right of cover |
| Brand colours | grass `#22382C`, copper `#B76749`, birch `#E6DDD2` | All pages |

### Per-property photo cache

Because the Azure blob image account is currently disabled, [scripts/generate_appraisal_report.py](../scripts/generate_appraisal_report.py) now falls back to `cache/property_photos/<property_id>/{hero,exterior,kitchen,living,aerial,pool}.jpg` when a remote download fails. Dee's photos were extracted from her existing PDF and seeded into `cache/property_photos/690bd7e68b8f5465926045fc/` for the 2026-05-06 regeneration.

---

## Flow at a glance

```
User on /analyse-your-home
        │  (1) address typed
        ▼
analyse-lead-address.mjs ──► system_monitor.crm_contacts (fire-and-forget save)
        │
        │  (2) email + delivery method submitted
        ▼
analyse-lead.mjs ──► system_monitor.analyse_leads
                  ├─► system_monitor.leads (canonical)
                  ├─► system_monitor.appraisal_pipeline (workflow row)
                  ├─► Telegram → Will (new lead)
                  ├─► Gmail   → Will (new lead)
                  ├─► Welcome email → lead
                  └─► system_monitor.trigger_requests (kicks VM job)
        │
        ▼  (VM, polled every 60s)
appraisal-poller.py
        │
        ▼  (manual or pipeline-driven)
scripts/generate_appraisal_report.py
        │  Jinja2 → HTML → PyMuPDF → 11-page PDF
        ▼
output/seller_reports/<date>_<slug>_<client>_v2.pdf
        │
        ▼
tracking-server/send_report.py
        │  creates tracking_id, embeds pixel, viewer link
        ▼
Microsoft Graph → recipient inbox
        │
        ▼  (every interaction)
tracking-server/server.py  (vm.fieldsestate.com.au)
        ├─► system_monitor.email_tracking (events array)
        ├─► system_monitor.crm_contacts.engagement.* (sync)
        └─► Telegram → Will  ("Email opened", "Viewing page 6", "PDF downloaded", "Session ended")
```

---

## 1. Frontend (entry point)

| File | Role |
|------|------|
| [analyse-your-home.tsx](../../Feilds_Website/01_Website/src/routes/analyse-your-home.tsx) | Route definition |
| [AnalyseYourHomePage.tsx](../../Feilds_Website/01_Website/src/pages/AnalyseYourHomePage/AnalyseYourHomePage.tsx) | Address entry, delivery method selection, form submission |
| [src/services/analyseHomeV2/](../../Feilds_Website/01_Website/src/services/analyseHomeV2/) | Address analysis services (v2) |
| [src/services/analyseHomeV3/](../../Feilds_Website/01_Website/src/services/analyseHomeV3/) | Address analysis services (v3, current) |
| [src/types/valuation.ts](../../Feilds_Website/01_Website/src/types/valuation.ts) | Shared TS response types |

The page calls `/api/analyse-lead-address` immediately on address entry (fire-and-forget, captures partial leads), then `/api/analyse-lead` on final submit.

## 2. Submission API (Netlify Functions)

| File | Role |
|------|------|
| [analyse-lead-address.mjs](../../Feilds_Website/01_Website/netlify/functions/analyse-lead-address.mjs) | Stores partial address in `crm_contacts` before full form submit |
| [analyse-lead.mjs](../../Feilds_Website/01_Website/netlify/functions/analyse-lead.mjs) | Main submission. Writes to `analyse_leads`, `leads`, `appraisal_pipeline`. Sends Telegram + Gmail + welcome email. Fires VM trigger. |
| [analyse-property.mjs](../../Feilds_Website/01_Website/netlify/functions/analyse-property.mjs) | Property analysis endpoint |
| [property-analysis.mjs](../../Feilds_Website/01_Website/netlify/functions/property-analysis.mjs) | Additional property analysis |
| [valuation.mjs](../../Feilds_Website/01_Website/netlify/functions/valuation.mjs) | Comparable-sales valuation API used by the page preview |
| [valuation-accuracy.mjs](../../Feilds_Website/01_Website/netlify/functions/valuation-accuracy.mjs) | Valuation accuracy tracking |
| [visitor-track.mjs](../../Feilds_Website/01_Website/netlify/functions/visitor-track.mjs) | Generic visitor tracking |

## 3. Backend pipeline (orchestrator VM)

| File | Role |
|------|------|
| [appraisal-poller.py](../appraisal-poller.py) | systemd `fields-appraisal-poller` — polls `appraisal_pipeline` every 60s, advances stages, triggers final-report email 2h after the analyst body is sent |
| [scripts/generate_appraisal_report.py](../scripts/generate_appraisal_report.py) | Generates the 11-page branded PDF. Pulls comparable sales from `Gold_Coast.<suburb>`, applies suburb-specific adjustment rates (Robina, Varsity Lakes, Burleigh Waters, Mudgeeraba, Merrimac, Reedy Creek, Worongary, Carrara), renders Jinja2 → PDF |
| [scripts/generate_seller_report.py](../scripts/generate_seller_report.py) | Older variant (Chromium-based PDF) |

**Output directory:** [/home/fields/Fields_Orchestrator/output/seller_reports/](../output/seller_reports/) — filename pattern `YYYY-MM-DD_<address-slug>_<client>_v2.pdf`.

## 4. Templates and assets

| File | Role |
|------|------|
| [templates/seller_report_v2.html](../templates/seller_report_v2.html) | Current 11-page report template (Jinja2) |
| [templates/seller_report.html](../templates/seller_report.html) | Older template |
| [templates/seller_book.html](../templates/seller_book.html) | Book-style variant |
| [templates/seller_book_reader.html](../templates/seller_book_reader.html) | In-browser reader variant |

PDF rendering uses **PyMuPDF (`fitz`)** server-side; `generate_seller_report.py` uses Chromium as an alternative path.

## 5. Email delivery + view tracking

| File | Role |
|------|------|
| [tracking-server/send_report.py](../tracking-server/send_report.py) | Creates `email_tracking` record (UUID), embeds tracking pixel + viewer link, sends via Microsoft Graph (OAuth refresh token) |
| [tracking-server/server.py](../tracking-server/server.py) | Flask app on `https://vm.fieldsestate.com.au`. Endpoints: `/track/pixel/<id>.gif`, `/track/view/<id>`, `/track/viewer-open/<id>`, `/track/page-view/<id>`, `/track/heartbeat/<id>`, `/track/download-pdf/<id>`. Renders the PDF page-by-page with PyMuPDF for the in-browser viewer. |

Tracking events are recorded in `system_monitor.email_tracking.events[]` and mirrored to `system_monitor.crm_contacts.engagement.*` (`pdf_downloaded`, `total_opens`, `pages_viewed`, `total_time_seconds`).

**Telegram notifications** fire on every event (except heartbeats):

- `*Email opened* by {name}` / `{address}` / `{time}`
- `*Report opened* by {name}`
- `*Viewing page X* — {name}`
- `*PDF downloaded* by {name}`
- `*Session ended* — {name} spent Xs on report`

Bot credentials: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` from `.env`.

## 6. MongoDB collections

| Database.Collection | Purpose |
|---------------------|---------|
| `system_monitor.analyse_leads` | Detailed lead form submissions from `/analyse-your-home` |
| `system_monitor.leads` | Canonical lead records (merged from `analyse_leads`) |
| `system_monitor.appraisal_pipeline` | Workflow state machine — stage, `analyst_email_body`, `report_path`, timestamps |
| `system_monitor.email_tracking` | Per-send record with `tracking_id` + full event log |
| `system_monitor.crm_contacts` | CRM contact with rolled-up engagement summary |
| `system_monitor.trigger_requests` | Generic trigger queue consumed by the VM |
| `Gold_Coast.<suburb>` | Property data used for comparable-sales selection |

## 7. Services

```bash
sudo systemctl status fields-appraisal-poller   # appraisal-poller.py
sudo systemctl status fields-valuation-api      # on-demand valuation HTTP service
sudo systemctl status fields-valuation-poller   # processes inbound valuation requests
sudo systemctl status fields-trigger-poller     # consumes trigger_requests
```

Logs:
- [logs/appraisal-poller.log](../logs/appraisal-poller.log)
- [logs/tracking-server.log](../logs/tracking-server.log)

## 8. Required env vars

`COSMOS_CONNECTION_STRING`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, plus Microsoft Graph OAuth (`MS_GRAPH_*`) for the report sender.

---

## Dee — first real customer

- **Property:** 13 Terrace Court, Merrimac, QLD 4226
- **Sent to:** `rossmax06@gmail.com` and `miss.dee.dcruz@gmail.com` (resends)
- **PDF actually emailed:** `2026-04-10_13-terrace-court_dee_v2.pdf` (saved here)
- **Sent on:** 2026-04-10
- **Tracking records:** 6 separate sends in `system_monitor.email_tracking`
- **Engagement (across sessions):** opened multiple times, all 11 pages viewed, longest single session ≈ 51 minutes on page 1, last interaction recorded **2026-05-01 06:52** AEST

Other PDF iterations on disk (not the version Dee received):
- `2026-04-09_13-terrace-court_dee.pdf` — first draft
- `2026-04-09_13-terrace-court_dee_v2.pdf` — v2 draft
- `2026-04-10_13-terrace-court_dee_v2_fixed.pdf` — post-send fix, never emailed

All four remain in [output/seller_reports/](../output/seller_reports/) for reference.
