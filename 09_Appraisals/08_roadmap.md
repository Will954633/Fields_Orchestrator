# Roadmap — From Today to v1 to v2

A 90-day delivery plan that converts the strategy into shipping work. Indexed to the production plan in `06_production_plan.md`.

The plan is sequenced for **single-operator** delivery. Designer + print partner are external contractors brought in at the right moments. Will is on the critical path; Claude / agent infrastructure removes blockers in parallel.

---

## Operating tempo

We work in **two-week sprints** (per `sprint_framework_preference.md`). Daily checkpoints at start of session. Weekly summary on Sundays. Quarterly retrospective.

Three concurrent tracks at all times. No track ever blocks more than one other.

---

## Phase 0 — Stabilise (Week 1: 6–12 May 2026)

**Goal:** stop the regression. Restore the April 10 v2 quality on the May 6 design.

| Day | Task | Owner | Output |
|---|---|---|---|
| Mon 6 | This strategy folder finalised | Claude + Will | 9 docs |
| Tue 7 | Editorial prompt diff: April 10 vs May 6 | Will + Claude | Diff report → restored prompt |
| Tue 7 | Spec data fix (5bd vs 6bd issue) | Will | Bug closed |
| Wed 8 | Editorial review checklist coded as `--strict` flag in `generate_appraisal_report.py` | Claude | `--strict` working |
| Wed 8 | Re-render 13 Terrace Court report (FA design + v2 content) | Will | Reference render |
| Thu 9 | Internal QA + screenshot comparison vs v2 reference | Will | Sign-off PDF |
| Fri 10 | Lock the editorial prompt + template in git tag `appraisal-v0` | Will | Tag pushed |
| Weekend | Plan Phase 1 module priorities | Will | Updated plan |

**Phase 0 success bar:** the next appraisal that ships is at least as good as the April 10 v2 in content quality, and looks like the FA design.

---

## Phase 1 — Add the modules that nobody else has (Weeks 2–3: 13–26 May)

**Goal:** ship two new modules that no Australian competitor includes. These are the moat-builders.

### Sprint 1 (13–19 May)

| Module | Why now | Effort |
|---|---|---|
| **M6 Limits of Our Evidence** | Vulnerability + competence; pratfall effect; trust-builder. | 2 days |
| **M11 Saturday-morning narrative** | Narrative transportation; the page sellers will quote to friends. | 3 days (incl. reflection-pass tuning) |

**Deliverables:**
- New editorial prompt sections for M6 and M11.
- Reflection-pass discipline for M11 (up to 3 generations, evaluator critic, escalate if no pass).
- Two new template partials.
- Test render for 13 Terrace Court showing both modules.
- 2 additional test renders for Robina and Burleigh Waters properties (different price tiers, different voices).

### Sprint 2 (20–26 May)

| Module | Why | Effort |
|---|---|---|
| **M13 Risk + Protection panel** | The single biggest underrated moat — addresses the buyer's first three Google searches. | 4 days |
| **M22 Outcome projection** | Loss aversion fully operationalised. | 2 days |

**Deliverables:**
- Flood + DA + infrastructure data already exist for Burleigh; extend to Merrimac, Robina, VL.
- `outcome_projection.py` calculator using Taylor 1999 + Zillow 2019 effect sizes.
- Templates for both new pages.
- 3 fresh test renders.

**Phase 1 success bar:** A 16-page digital edition that includes M6, M11, M13, M22. No competitor has any of these. The cover-to-back read takes ~25 minutes.

---

## Phase 2 — Microsite v0 (Weeks 4–5: 27 May – 9 June)

**Goal:** every report gets a persistent URL that extends beyond the email send.

### Sprint 3 (27 May – 2 June)
- New website route `appraisals/<slug>?token=<id>` with light gate.
- Hydrate from `system_monitor.appraisal_renders` (new collection).
- Reuse `tracking-server` page-by-page renderer for fallback PDF view.
- Microsite shows the same content as the digital edition, in a scrolling responsive layout.
- Telemetry firing on view, scroll depth, time-on-section.

### Sprint 4 (3–9 June)
- "What We Got Wrong" feedback form (M32) → `appraisal_corrections` collection → triggers re-render via `appraisal-poller`.
- Conversation calendar (M33) → `conversation_requests` collection → Telegram + Gmail.
- Microsite update notifications: when a new comparable lands, send the seller an opt-in email pointing them back to the microsite.

**Phase 2 success bar:** Dee's appraisal has a live microsite. Engagement metrics return ≥ 3 separate sessions on average across the first 5 sellers.

---

## Phase 3 — Print master (Weeks 6–9: 10 June – 7 July)

**Goal:** a 36-page printed Print Master that we'd hand-deliver with confidence.

### Sprint 5 (10–16 June): Designer brief + spec
- Extend `Property_Report_Designer_Brief.md` from current 4 deliverables to all 36 page styles per `02_report_blueprint.md`.
- Brief the existing FA designer (or a comparable) for the full set.
- Confirm typography decision (Poppins-only vs Poppins + display serif).
- Print partner shortlist (3 candidates, sample runs).

### Sprint 6 (17–23 June): Designer delivery + integration
- Designer delivers HTML+CSS for all 36 page styles.
- Engineer wires data via Jinja2 partials.
- First end-to-end test render for 13 Terrace Court.

### Sprint 7 (24–30 June): Print partner trial
- 1 trial print run on the chosen stock.
- Inspect physical: paper, colour, foil, binding, weight, lay-flat.
- Iterate to v0.5 print.

### Sprint 8 (1–7 July): First real delivery
- Pick the next live appraisal and produce the full pipeline (digital + microsite + print).
- Hand-deliver / courier in custom slim box.
- Capture seller reaction (informal — Will calls within 48h).

**Phase 3 success bar:** the first real seller receives the full kit and provides verbal confirmation it changed their decision.

---

## Phase 4 — Video pipeline (Weeks 10–11: 8–21 July)

**Goal:** a per-report 90-second video by Will that ships within 48h of digital send.

### Sprint 9 (8–14 July): Recording template
- Recording rig (lighting, audio, camera, eye-line) at Will's home or office.
- Recording template: 30s hook + 30s drivers + 30s invitation. Plain background.
- Filming-and-production-guide adherence (15–25s bursts, eye contact, faster delivery).
- 2 test recordings for past appraisals (13 Terrace, plus one Robina / Varsity).

### Sprint 10 (15–21 July): Editing + integration
- Editing template — automate cut points and intro/outro from the recordings.
- Vimeo / Mux private hosting.
- Microsite embed component.
- Print integration: QR code on inside back cover (M25 area).

**Phase 4 success bar:** Will has a sustainable recording rhythm; videos ship within 48h.

---

## Phase 5 — Property-type variants (Weeks 12–13: 22 July – 4 Aug)

**Goal:** the report ships correctly for all major Gold Coast property types.

### Sprint 11 (22–28 July)
- M35 Apartment / Townhouse variant
- M37 Investor-Held variant

### Sprint 12 (29 July – 4 Aug)
- M36 Acreage / Lifestyle variant
- M38 Deceased Estate / Probate variant

For each: (a) variant editorial prompt, (b) variant template overrides, (c) test render against a real address.

**Phase 5 success bar:** any incoming `analyse-your-home` lead — apartment, townhouse, acreage, probate — is handled by the correct variant without manual intervention.

---

## Phase 6 — Photography Audit + Pre-Sale Sidebar (Weeks 14–15: 5–18 Aug)

**Goal:** the two modules that complete the strategy doc but require more setup.

- **M8 Photography Audit** — only fires when prior listing photos exist (otherwise omitted). Editorial agent extension; image diff capability.
- **M18 Pre-sale ROI** — `config/pre_sale_roi.{suburb}.yaml` lookup tables (4 suburbs first); editorial prompt extension.

**Phase 6 success bar:** both modules ship for at least one real appraisal.

---

## Phase 7 — Authority & Marketing (Weeks 16+)

After v1 of the report ships steadily:
- A "**Sample Appraisal**" page on the public site, downloadable PDF (synthetic property), so prospective sellers see the quality before submitting.
- A "**This Is What Most Agents Send**" comparison page (anonymised) showing the structural gap.
- Outreach to `seller-book` readers offering a "Seller's Companion Appraisal" — bundled experience.
- Onboard a second photographer to extend twilight coverage.

This is the start of the second 90-day phase, planned at the end of Week 13.

---

## Risk register (this roadmap specifically)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Designer turnaround slips | Medium | High | Brief 2 designers, pick the faster |
| Print partner quality variance | Medium | High | 3 candidate trial runs before commitment |
| Editorial prompt drift again | Low (with checklist) | High | `--strict` flag is a hard gate |
| Will operational overload | High | High | Defer per-report video + hand-delivery scaling until volume justifies |
| New competitor ships AI-CMA | Low–Medium | High | Speed of execution is our defence; ship Phase 1 + 2 within 6 weeks |
| Lead volume spikes faster than print pipeline | Low (pre-revenue) | Medium | Print is opt-in for the first conversation, not first contact; throttles |

---

## Throughout: discipline rules

- **No new module ships without an editorial review checklist update.**
- **No template change ships without a regression test render.**
- **Every fix-history entry follows the standard format** (`logs/fix-history/YYYY-MM-DD.md`).
- **Every change is pushed to `Will954633/Fields_Orchestrator` via `gh api`** (per `CLAUDE.md` mandatory rules).
- **Memory updated when a new pattern emerges.** The Phase 1 reflection-pass discipline becomes a memory file once proven.

---

## Quarterly milestones

| Date | What's true |
|---|---|
| End May 2026 | Phase 0 + Phase 1 complete. v0.5 of digital report shipping with M6, M11. |
| End June 2026 | Phase 2 complete. Microsite live for all new reports. |
| End July 2026 | Phase 3 + Phase 4 complete. Print master in market. Video pipeline operational. |
| End August 2026 | Phase 5 + Phase 6 complete. All variants supported. |
| End Q3 2026 | First listing won via the report (per the runway memory: Q3 must show market interest/listings). |

The single most important milestone is the **first listing won that the seller credits to the report**. That is the moment the strategy is validated.

---

*Owner: Will Simpson · Updated 2026-05-06 · Reading order: read after `07_review_passes.md`. Last document in the strategy folder.*
