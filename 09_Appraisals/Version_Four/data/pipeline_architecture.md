# Appraisal Report — Production Pipeline Architecture

**Purpose:** End-to-end design for producing a polished property appraisal PDF for any property in the southern Gold Coast catchment, with human-in-the-loop checkpoints for valuation confirmation and quality review.

**Status:** Draft. Locked once V5 design lands and the templating engine is chosen.

**Date:** 2026-05-12

---

## End-to-end flow

```
┌──────────────────────┐
│ 1. Property selected │   Trigger: Will picks an address via Ops dashboard,
│    (address + ID)    │   or auto-trigger from a "seller booked" event.
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────┐
│ 2. Data pull                     │   scripts/appraisal_data_pull.py
│    • Property record             │   Outputs: appraisal_data.json
│    • Valuation engine output     │   (~10–25 KB per property)
│    • Cohort medians              │
│    • Catchment demographics      │
│    • Backtest MAE                │
│    • AI editorial (if exists)    │
│    • Human-input slots (empty)   │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│ 3. AI editorial expansion                        │   New script (Phase 2.5)
│    Takes appraisal_data.json + universal copy →  │   Calls Claude Opus to fill:
│    • Persona narratives (×3)                     │     - persona evidence lines
│    • Anti-fit line                               │     - sample copy in levers
│    • Scarcity claim ("1 of only N")              │     - trade-offs prose
│    • Trade-offs prose for trust page             │     - synthesis paragraph
│    • Synthesis paragraph                         │
└──────────┬───────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────┐
│ 4. HUMAN CHECKPOINT — Will's review          │   Ops dashboard tab
│    Will reviews + edits:                     │   "Appraisal Review"
│    • Reconciled valuation (confirm/override) │
│    • Recommended list price (set)            │
│    • Target sale price range (set)           │
│    • WTP per persona (confirm/override)      │
│    • Persona selection (3 of N catalogue)    │
│    • AI editorial content (approve/edit)     │
└──────────┬───────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ 5. Template render                       │   scripts/render_appraisal.py
│    appraisal_data.json + universals →    │   Reads template, fills slots,
│    HTML rendered                         │   writes <output>/preview.html
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ 6. PDF generation                        │   Puppeteer (replaces headless
│    Headless Chrome / Puppeteer →         │   Chrome CLI for finer control:
│    final.pdf                             │   font embedding, page footers,
│                                          │   image-loading guarantees)
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ 7. HUMAN CHECKPOINT — Visual QA  │   Will reviews the PDF in Ops dashboard.
│    PDF preview displayed.        │   Approve → send to seller.
│    Approve / request fix.        │   Reject → loop back to step 4.
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ 8. Delivery                      │   Email to seller (Microsoft Graph),
│    + archive in MongoDB          │   archive in system_monitor.appraisals
└──────────────────────────────────┘
```

---

## Components and ownership

| Step | Component | Type | Status | Notes |
|------|-----------|------|--------|-------|
| 1 | Property selector (Ops dashboard) | React/Netlify | Future | Single dropdown + "Generate appraisal" button |
| 2 | `scripts/appraisal_data_pull.py` | Python CLI | **Built** (2026-05-12) | Reads from Cosmos + ABS file |
| 3 | AI editorial expansion script | Python + Claude Opus | Future | Reuses Anthropic client + prompt template |
| 4 | Appraisal Review tab | Ops dashboard | Future | New tab in `system-monitor.mjs`; forms per data slot |
| 5 | Template render | Python (Jinja2) or Node (EJS/React) | Future — design eng | Depends on Phase 1 deliverable structure |
| 6 | PDF generation | Puppeteer (Node) or Playwright (Python) | Future | Move off CLI Chrome; need fine font/page control |
| 7 | Visual QA tab | Ops dashboard | Future | PDF.js preview + approve/reject buttons |
| 8 | Delivery + archive | Python | Future | Reuses existing email agent (samantha-email-agent) |

---

## Data flow contracts

### Input to template (step 5)

The template consumes one composite object:

```json
{
  "property": {...},          // from appraisal_data.json
  "valuation": {...},         // from appraisal_data.json
  "cohort": {...},
  "backtest": {...},
  "demographics": {...},

  "ai_editorial": {           // from step 3
    "persona_narratives": [...],
    "anti_fit_line": "...",
    "scarcity_claim": "...",
    "trade_offs_prose": "...",
    "synthesis_paragraph": "..."
  },

  "human_inputs": {           // from step 4 (Will's review)
    "seller_name": "Dee",
    "recommended_list_price": 1915000,
    "list_price_rationale": "Lower end of the derived range...",
    "target_sale_price_low": 2000000,
    "target_sale_price_high": 2050000,
    "target_sale_rationale": "Upper end of the derived range, reached through buyer competition.",
    "personas": [
      {"rank": "primary", "share_pct": 35, "wtp_low": 1850000, "wtp_high": 2050000, ...},
      {"rank": "secondary", "share_pct": 30, ...},
      {"rank": "tertiary", "share_pct": 20, ...}
    ]
  },

  "universals": {             // from constants file
    "tagline": "Smarter with data",
    "philosophy_lines": ["...", "..."],
    "six_forces": [...],
    "campaign_sequence": [...],
    "next_steps": [...],
    "fields_advantage_copy": {...},
    "static_stats": {
      "roy_morgan_trust_pct": 5,
      "photography_lift_pct": 118,
      "trust_premium_pct": 9.6
    }
  }
}
```

### Output

- `preview.html` — single static file rendered for review
- `final.pdf` — PDF for delivery
- Archive record in `system_monitor.appraisals`:
  ```json
  {
    "property_id": "...",
    "address": "13 Terrace Court, Merrimac",
    "seller_name": "Dee",
    "generated_at": "2026-05-12T...",
    "appraisal_data": {...},  // full input JSON
    "pdf_blob_url": "...",
    "status": "delivered" | "draft" | "reviewing",
    "delivered_to": "...",
    "delivered_at": "..."
  }
  ```

---

## Technology choices to lock with the design engineer

When the Phase 1 design engineer (the Upwork hire) delivers a static V5 HTML, several technology decisions become final:

1. **Templating engine.** Depends on what the design engineer uses:
   - If they write plain HTML + CSS → **Python + Jinja2** (matches our existing stack)
   - If they use React → **Vite + React** rendering pipeline
   - If they use Astro / Eleventy → match their choice
2. **PDF generator.** Move off CLI `google-chrome --print-to-pdf` to:
   - **Puppeteer** (Node) — best fine control, widely used for editorial PDF
   - Alternative: **Playwright** (Python or Node) — equivalent capability
3. **Asset hosting.** Currently fonts come from Google Fonts CDN. For print fidelity and offline rendering, **self-host all fonts** (especially given the designer is supplying specific document fonts).
4. **Image handling.** Property photos need a CDN or blob URL strategy. Currently scattered between Domain CDN, Azure Blob, and local PNG. **Recommend: all images served from `Azure Blob: appraisal-photos/` for the template render**, with the data pull script handling the upload if needed.

---

## Human-in-the-loop checkpoints (rationale)

| Checkpoint | Why a human |
|------------|-------------|
| Step 4 — Will's review | Valuation accuracy + pricing strategy require Will's professional judgement. Recommended list price applies the precise-pricing protocol from `Before You List Ch. 4` — judgement-based, not algorithmic. WTP bands per persona may need adjustment based on local context the model can't see. |
| Step 7 — Visual QA | Layout integrity — long suburb names, missing photos, edge-case adjustments breaking the receipts page. Final eye before the report goes to a seller. |

Everything else in the pipeline can run unsupervised.

---

## Open architectural questions

1. **Where does the AI editorial expansion live?** Three options:
   - (a) Standalone script invoked between data-pull and template render (recommended)
   - (b) Embedded in the data-pull script (couples them — harder to swap out the AI later)
   - (c) Service running continuously and triggered by webhook
   - **Recommend (a).** Clean separation, easy to swap models, easy to run manually.

2. **Persona catalogue vs persona generation?** The current report has 3 hand-picked personas. Going forward:
   - (a) **Catalogue approach** (recommended): define 6–8 persona archetypes (downsizer, multi-gen, relocator, investor, first-home upgrader, holiday-home buyer, etc.). For each property, the AI picks 2–4 most relevant; their narratives are AI-generated within fixed archetype templates.
   - (b) **Free-form generation**: AI invents personas from scratch per property. Higher creativity, higher consistency risk.

3. **Twilight photography requirement** — Page 15 in V4 needs a paired (standard + twilight) interior shot. Most active listings don't have twilight photography yet.
   - Option A: Skip the image-comparison page if twilight isn't available
   - Option B: Use AI image generation to create the twilight version (image-to-image)
   - Option C: Hold appraisals for properties without twilight photos
   - **Decision deferred to V5 design phase.**

4. **Locked pages 4–5 (Scarcity)** — currently flattened PNGs in V4. Phase 1 design engineer will likely rebuild these as HTML pages, but the dynamic data (scarcity claim, annotated satellite) requires:
   - A scarcity-query function: count homes matching subject's feature set in catchment
   - A satellite-annotation pipeline (could be hand-built per property, or use AI image generation)

5. **Where do appraisal PDFs live?** Two options:
   - `system_monitor.appraisals` with blob URL (recommended — queryable, integrates with ops dashboard)
   - Just on disk in `09_Appraisals/Generated/` (simpler, no DB integration)

---

## Timeline estimate (post Phase 1 design delivery)

| Task | Owner | Duration |
|------|-------|----------|
| Build AI editorial expansion script (step 3) | Me | 1 day |
| Build template render script (step 5) | Me | 0.5 day (once design eng delivers) |
| Migrate to Puppeteer PDF generation (step 6) | Me | 0.5 day |
| Build Appraisal Review tab in Ops dashboard (step 4) | Me | 1.5 days |
| Build Visual QA tab + delivery flow (steps 7–8) | Me | 1 day |
| Persona catalogue + selection logic | Me | 1 day |
| Scarcity-query function for locked pages | Me | 0.5 day |
| Test cohort: 3–5 real properties end-to-end | Me + Will | 1 day |
| **Total** | | **~7 working days** |

---

## What this document IS and ISN'T

**This document is:**
- The contract between data sources, AI generation, human review, and template output
- The brief for Phase 2 (productionise the template) once V5 design lands
- A reference for what each component owns and where boundaries sit

**This document is NOT:**
- A locked design. Architecture choices will be finalised once V5 design lands (templating engine, PDF generator, asset hosting).
- A schedule commitment. The 7-day estimate assumes V5 is a clean delivery and no V5 design changes mid-build.
- A justification for hiring more than one design engineer. Phase 1 is the single hire; everything else is in-house.
