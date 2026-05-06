# Production Plan — How We Actually Build It

This document maps the strategy and blueprint to engineering reality. It enumerates: the existing pipeline, the gaps, the changes required, the new components to build, the engineering risks, the deployment path. Every "we should add X" statement in the strategy/blueprint cycles back to a build line here.

Read after `05_visual_system.md`. Read alongside `08_roadmap.md` for sequencing.

---

## 1. What already exists (audit, 2026-05-06)

### 1.1 Data layer
| System | What it does | Status |
|---|---|---|
| `Gold_Coast.<suburb>` collections | All property data, ~40K cadastral records | Production |
| `precompute_valuations.py` | Comparable selection, line-item adjustments, suburb-specific rates, confidence bands | Production, nightly |
| `valuation_data` field | Stored on property docs with comparables, range, summary | Production |
| `floor_plan_analysis`, `satellite_analysis`, photo analysis | AI-derived per-property data | Production |
| `flood_assessment` | City Plan + ICA overlay | Production for Burleigh; expand to Merrimac, Robina, VL |
| `nearby_pois.by_category` | Schools, parks, cafes, supermarkets, childcare | Production |
| `precomputed_market_charts`, `precomputed_indexed_prices` | Suburb stats, monthly index, seasonality | Production |
| Domain accuracy benchmark (1,689 estimates) | Audit dataset | Production |

### 1.2 Submission + lead pipeline
| System | What it does | Status |
|---|---|---|
| `analyse-your-home` page | Address entry + delivery method | Production |
| `analyse-lead.mjs` | Lead capture + Telegram + Gmail + welcome email + VM trigger | Production |
| `appraisal-poller.py` | systemd `fields-appraisal-poller` — polls, advances stages, triggers final-report email | Production |
| `system_monitor.appraisal_pipeline` | Workflow state machine | Production |

### 1.3 Report generation
| System | What it does | Status |
|---|---|---|
| `scripts/generate_appraisal_report.py` | 11-page PDF generator — Jinja2 → HTML → PyMuPDF | Production |
| `templates/seller_report_v2.html` | Current template (954 lines) | Production |
| Editorial AI agent | Claude Opus 4-20250514, max_tokens 6000, single call → JSON | Production |
| Output dir | `output/seller_reports/YYYY-MM-DD_<slug>_<client>_v2.pdf` | Production |

### 1.4 Delivery + tracking
| System | What it does | Status |
|---|---|---|
| `tracking-server/send_report.py` | Embeds tracking pixel + viewer link, sends via MS Graph | Production |
| `tracking-server/server.py` | Flask app on `vm.fieldsestate.com.au` with all tracking endpoints | Production |
| Telegram event firing | Open / view / page-view / download / session-end | Production |
| `system_monitor.email_tracking.events[]` | Engagement event log | Production |
| `system_monitor.crm_contacts.engagement` | Rolled-up engagement summary | Production |

### 1.5 Design assets
| Asset | What | Status |
|---|---|---|
| `4274 - Marty_Fields - Property Report_FA.pdf` (April 29) | InDesign FA cover + page 2 design | Reference; only 2 pages exist |
| `_Working Files/4274 - Fields - Property Report_FA.indd` | Native InDesign master | Reference |
| `Icons/` folder (light + dark) | Complete icon set | Production-ready |
| `current_template_reference.html` | HTML+CSS reference for designers | Production |
| `Property_Report_Designer_Brief.md` | Brief for HTML+CSS designer | Production |
| `2026-05-06_13-terrace-court_dee_designer-style.pdf` | Most recent render with FA cover applied | In progress; **content regression observed** (see `03_competitive_audit.md` §8) |

---

## 2. Gap analysis — what's missing for the ambitious blueprint

| Blueprint feature | Status | Build effort |
|---|---|---|
| **Section divider pages** (TRUTH / EVIDENCE / ACTION) | New | S — template add |
| **Methodology page** (M14, P4 Front + P15) | Partial — embedded in last page; needs dedicated page | M — template + data injection |
| **Photography Audit (M8)** | New; conditional on prior listing | L — needs new prompt + image source |
| **Limits of Our Evidence (M6)** | New | M — editorial prompt + template |
| **Saturday-morning narrative (M11)** | New | M — editorial prompt + reflection-pass discipline |
| **Risk + Protection panel (M13)** | Partial — flood exists; need school + DA + infrastructure | L — DA scrape + title-search integration |
| **Pre-sale ROI sidebar (M18)** | New | M — `pre_sale_roi.{suburb}` lookup + editorial prompt |
| **First Seven Days (M20)** | New; data already in seller book | S — template + chart reuse |
| **Negotiation Plan (M21)** | New | M — editorial prompt extension |
| **Outcome Projection (M22)** | New | M — calculator script + template |
| **Personalised microsite** | New | L — new web route + persistent storage |
| **Embedded video (M30)** | New | M — video pipeline + Will recording cadence |
| **Live comparable feed (M31)** | New | M — webhook from precompute_valuations to microsite |
| **What We Got Wrong feedback (M32)** | New | S — form + re-render trigger |
| **Conversation calendar (M33)** | New | S — Cal.com or self-hosted |
| **Print pipeline** | New | L — designer + print partner + packaging |
| **InDesign master refresh (full 36 pages)** | Partial — only cover + page 2 done | L — design partner work |
| **Property-type variants (M35–M38)** | New | L — variant rendering + per-type editorial prompts |
| **Editorial review checklist enforcement** | New | M — automated checks on render |

S = ≤ 1 day, M = 2–5 days, L = > 1 week.

---

## 3. The four production tracks (parallel)

Each track has an owner, deliverables, and a success bar. The strategy ships when all four converge.

### 3.1 Track A — Content correctness (P0, urgent)
**Goal:** the May 6 design-style render must not regress from the April 10 v2 in content quality. (See `03_competitive_audit.md` §8.)

**Tasks:**
1. **Editorial prompt audit.** Diff the editorial agent prompt that produced the April 10 v2 (working) against what produced the May 6 render (regression). Restore the prompt elements that produced specific dollar-quantified strengths and the named-trade-off panel.
2. **Spec accuracy.** Fix the data quality bug that rendered "6bd + Study" when source was "5bd". Likely a confusion between `bedroom_count` and `bedroom_count + has_study` in template logic.
3. **Trade-off panel.** Replace the placeholder "Refer to the detailed comparable adjustment analysis…" with a generated, named-feature trade-off (per M5 template).
4. **Verdict comp set.** Verdict must name all 3 comparables, not 2.
5. **Editorial review checklist as pre-render gate.** No PDF renders if any check fails. Add as `--strict` flag to `generate_appraisal_report.py`.

**Owner:** Will + claude (editorial pipeline work).
**Success bar:** rendering 13 Terrace Court returns the v2 content with the FA design.

### 3.2 Track B — Print master (full 36 pages)
**Goal:** an InDesign / Affinity / HTML+CSS-to-print master that renders all 36 pages of the Print Master per blueprint.

**Tasks:**
1. Decide: full InDesign master *or* HTML+CSS+headless-Chrome for both digital and print. The HTML route is faster to integrate with our pipeline; the InDesign route gives finer typography control.
2. **Recommendation:** stay HTML+CSS for the entire pipeline. Reasons:
   - Already integrated with the data layer.
   - The May 6 render proves FA cover quality is achievable in HTML.
   - Print-quality A4 PDF from headless Chrome has matured (CSS Paged Media spec, `@page` rules).
   - Same template drives all three editions.
3. Brief the designer (we have a `Property_Report_Designer_Brief.md` — extend it from current 4 deliverables to all 36 page styles).
4. Designer delivers HTML+CSS for: section dividers, methodology page, honest-assessment panels (variant), risk-and-protection panel, pre-sale sidebar, negotiation-plan page, outcome-projection page, narrative-transportation page, photography-audit spread.
5. Engineer (Will) wires data into each new page style via Jinja2.
6. Print partner test: 1 trial run on 200gsm coated cover + 100gsm uncoated body. Inspect, iterate.

**Owner:** Will + designer + print partner.
**Success bar:** a full 36-page Print Master rendering for 13 Terrace Court that we'd be proud to hand-deliver.

### 3.3 Track C — Living microsite
**Goal:** a personalised URL per appraisal that extends the document into a 30+ day surface.

**Tasks:**
1. Add new website route: `fieldsestate.com.au/appraisals/<address-slug>?token=<id>`. Token gates the page (light gate: just enough to prevent random discovery; share-friendly).
2. Reuse existing `tracking-server` page-by-page renderer for the digital report, plus three new components:
   - **Animated cover loop** — hero video player.
   - **Embedded video** — Will's 90-sec verdict + optional 4-min walkthrough.
   - **Live comp feed** — pulls from `properties_for_sale` + `properties_recently_sold` filtered to the comp pool, surfacing new sales as they land.
3. **What We Got Wrong feedback** — form posts to a new `appraisal_corrections` collection; triggers a re-render job in the existing `appraisal-poller`.
4. **Conversation calendar** — Cal.com integration or simple form to a `conversation_requests` collection that pushes Telegram.
5. **Telemetry surfacing** — extend Will's existing Telegram firing to include microsite-specific events (video play, video complete, correction submitted, conversation booked).

**Owner:** Will (web + backend integration).
**Success bar:** Dee's microsite is live, with all features working and a 30-day return-engagement curve measurable.

### 3.4 Track D — Video pipeline
**Goal:** a repeatable per-report video pipeline producing a 90-second verdict video and (optionally) a longer walk-through.

**Tasks:**
1. Will films one short verdict per report. Recording template: 30 second hook ("This is X, here's the verdict") + 30 second drivers + 30 second invitation. Plain background, single light, eye-line camera.
2. Recording bar: 12–16 takes per report (per the filming-and-production guide in memory). Eye contact, 15–25s bursts. The first take is rarely the best.
3. Editor (or Will's editing template) cuts to a single 90-sec piece.
4. Hosting: dedicate a private Vimeo / Mux / self-hosted endpoint. Embed via signed URL on the microsite.
5. Print integration: QR code on the inside back cover linking to the video.

**Owner:** Will.
**Success bar:** a video for every report that ships, < 24h turnaround.

---

## 4. Critical-path engineering changes

These code changes are the highest-leverage of the entire plan.

### 4.1 Editorial pipeline upgrades

**File:** `scripts/generate_appraisal_report.py`

**Changes:**
- **(P0) Add editorial-review checklist enforcement.** Pre-render, the script validates the editorial JSON against the checklist in `04_content_modules.md` §G. Any failed check raises and blocks the render. Failure modes: missing comp address in verdict, generic placeholder copy in trade-off, forbidden words present, abbreviated dollar figures, etc.
- **Add `--edition` flag.** Values: `digital`, `print`, `microsite_data`. Drives template selection and content depth.
- **Add new modules to editorial prompt:**
  - M6 Limits of Our Evidence
  - M11 Saturday-morning narrative (with reflection-pass discipline — up to 3 generation passes, judged by an evaluator agent against the narrative-transportation criteria)
  - M21 Negotiation Plan
  - M22 Outcome Projection
- **Add property-type variant resolution.** Detect property type → load matching prompt + template variant.
- **Tighten the verdict naming rule.** Verdict prose must contain ≥ 2 comparable addresses, ≥ 1 dollar figure, ≥ 1 named feature. Validated programmatically.

### 4.2 Template architecture

**File:** `templates/seller_report_v2.html` → `templates/appraisal/<edition>/`

Restructure as:
- `_base.html` — shared head, CSS imports, `@page` rules, color tokens.
- `digital.html` — extends `_base`; 12-page digital quick-read.
- `print.html` — extends `_base`; 36-page print master.
- `microsite_data.html` — outputs JSON consumed by the microsite renderer.
- `partials/` — every module (M1–M28) as a separate Jinja partial. Compose into pages.

This gives us:
- Shared content modules across editions.
- Easy A/B testing on individual modules without touching the master.
- Designers can deliver new modules in isolation.

### 4.3 Pre-sale ROI lookup

**New file:** `config/pre_sale_roi.{suburb}.yaml`

Initial values from seller book Chapter 5. Suburb-specific (Burleigh prepayment ROI ≠ Robina ≠ Merrimac). Each entry: action, typical_cost_low, typical_cost_high, expected_recovery_low, expected_recovery_high, conditional_on (e.g. "condition_score < 8 on flooring"), note.

### 4.4 Outcome projection calculator

**New file:** `scripts/outcome_projection.py`

Inputs: property's range, suburb, condition score. Outputs:
- Scenario A (correctly priced day 1): expected days to sale, probable final sale price (range), marketing cost.
- Scenario B (overpriced 12% + reduce after 42 days): expected days to sale, probable final price (range), marketing cost (with the reduction stigma effect from Knight 2002).
- Net-to-vendor difference.

Effect-size sources: Taylor 1999 (2–5× DOM); Zillow 2019 (50% less likely to sell in 60d); Anglin/Rutherford/Springer 2003 (downward spiral).

### 4.5 New Mongo collections

| Collection | Purpose |
|---|---|
| `system_monitor.appraisal_corrections` | "What we got wrong" feedback submissions |
| `system_monitor.conversation_requests` | Conversation bookings from microsite |
| `system_monitor.appraisal_video_events` | Video play / complete / share events |
| `system_monitor.appraisal_render_jobs` | Render audit log: prompt version, model, checklist results, render duration |

### 4.6 Microsite route + renderer

**New file:** `Feilds_Website/01_Website/netlify/functions/appraisal.mjs` and `src/pages/AppraisalPage/`.

Approach: server-side reads the appraisal data from `system_monitor.appraisal_renders` (new collection that stores the rendered editorial JSON keyed by tracking_id). Hydrates a React component that mirrors the print modules but as a scrolling, interactive document.

Reuse `tracking-server` for telemetry where possible. Reuse the page-by-page renderer for fallback PDF view.

---

## 5. The QA process

Every report passes through five gates before send.

### Gate 1 — Editorial review checklist (automated)
Per `04_content_modules.md §G`. Blocks the render if any check fails.

### Gate 2 — Data sanity check (automated)
- Specs match source (no "6bd" when source says 5).
- All comp adjustments have non-zero, non-undefined values.
- Range width < 25% of midpoint, otherwise flag as `directional_only`.
- All POI distances < 5km (otherwise data error).
- Hero photo is twilight or escalated to manual check.

### Gate 3 — Will's review (manual)
30-minute pass. Will reads the digital edition cover-to-cover, marking changes. Becomes faster once the prompt is well-tuned.

### Gate 4 — Designer review (manual; print only)
Visual integrity check. Type rendering, kerning, photography colour, chart legibility, foil-block placement.

### Gate 5 — Send confirmation
Final preview link to Will + a 30-minute hold before send. Reduces oh-no-send incidents.

---

## 6. Engineering risks

### Risk 1 — Editorial regression from prompt drift
**Already happened.** May 6 vs April 10. Mitigation: lock the editorial prompt in version control with a release process. Diff before deploy.

### Risk 2 — PDF rendering fidelity differences (digital vs print)
Headless Chrome's CSS Paged Media support is improving but inconsistent. Mitigation: separate CSS budgets for digital vs print; render proof PDF on every commit; visual-diff tooling (Percy.io or self-hosted).

### Risk 3 — Microsite scaling
A successful campaign could yield 50+ microsites/week. Mitigation: render microsite data once on send; serve from CDN; only re-render on correction.

### Risk 4 — Video bottleneck on Will
Per-report video is the most labour-intensive component. Mitigation: defer to a later phase. Print + microsite can ship first; video added when Will has rhythm. Or, per-suburb generic video supplements until per-property is feasible.

### Risk 5 — Print partner reliability
Quality variance from print partners. Mitigation: single-partner relationship after qualifying 2–3 candidates with sample runs. Hold a digital proof reference for every print run.

### Risk 6 — Designer dependency
The designer who produced the FA cover (`4274` filename suggests an external designer) needs to deliver another 30+ page styles. Mitigation: lock the design system in `05_visual_system.md` so any designer can deliver consistent work; ideally bring the existing FA designer back for the full set.

---

## 7. Cost model

Order-of-magnitude estimates for steady state (per report):

| Cost | Estimate |
|---|---|
| AI editorial pipeline (Claude Opus, ~6K tokens × 7 stages) | $1.50–$2.50 |
| Comparable selection + valuation (already nightly) | $0.05 |
| Image processing (already nightly) | $0.05 |
| PDF rendering | $0.02 |
| Microsite hosting (per report-month) | ~$0.10 |
| Video hosting (per report-month) | $0.50–$1.00 |
| Print run (1 report, 36pp lay-flat + slim box + business card) | $30–$60 |
| Hand-delivery / courier | $15–$25 |
| **Total per shipped report** | **~$50–$90** |

For comparison: a typical agency spends $5,000+ on per-listing marketing once won. Our per-appraisal cost to win the listing is < 2% of that figure. The unit economics support disproportionate investment in the report itself.

---

## 8. Production cadence

Today, lead → report → send takes ~3 hours of compute + ~24h waiting for Will's review (per `appraisal-poller.py` 2-hour-after-analyst-body trigger).

Target steady state:
- **Lead landed** → digital edition rendered + reviewed within 24h.
- **First conversation** → print edition delivered within 5 days.
- **Microsite live** at digital-send moment; updates persistent.
- **Video** within 48h of digital send (until Track D matures, can be deferred).

---

## 9. The minimum viable shipped product

If we have to ship something tomorrow, ship in this order:
1. **Track A complete** — content correctness restored. (Week 1.)
2. **Editorial review checklist enforced.** No more regressions. (Week 1.)
3. **Two new modules added** — M6 Limits of Our Evidence + M11 Saturday-morning narrative. (Week 2.)
4. **Microsite v0** — at minimum, a viewer-page URL persistent beyond the Gmail send. (Week 2.)
5. **Print pipeline v0** — render the existing 11–12 pages to print-grade HTML. Actual print run on the 5th report. (Week 3.)
6. **Print master full 36 pages** — designer delivers, engineer wires. (Weeks 4–8.)
7. **Microsite v1** — embedded video, live comp feed, feedback form. (Weeks 4–6.)

That's the order in `08_roadmap.md`.

---

*Owner: Will Simpson · Updated 2026-05-06 · Reading order: read after `05_visual_system.md`, before `07_review_passes.md`.*
