# Review Passes — Multi-Angle Critique

This document is the "is it actually good enough?" pressure test. Each pass walks the strategy through a different critical lens and surfaces the weaknesses before a competitor (or seller, or sceptical partner) does.

Run this checklist before any major change ships.

---

## Pass 1 — Psychology pass (does the report do real work in the seller's head?)

### What we want to be true
- The seller's first impression is "this is the most thorough thing anyone has ever produced about my home".
- By page 5, the seller's prior anchor (Domain estimate / dinner-party number / agent quote) has been replaced by the comp range.
- By page 8, the seller has noticed at least three named weaknesses and seen them reframed as value.
- By page 11, the seller has imagined themselves on the Saturday morning of the inspection.
- The seller closes the report with a single thought: *"They wrote this for me."*

### What could go wrong
1. **Halo without substance** — beautiful design, thin content. Reader praises it on first read, then notices nothing memorable when they come back two days later. (Mitigation: every page must answer Truth/Competence/Care, not just look the part.)
2. **Anchoring backwards** — if the verdict figure appears before the comparable evidence in the reader's flow, we've reinforced their prior anchor instead of replacing it. (Mitigation: verdict prose leads with "Based on N comparables…"; the figure is preceded by the methodology sentence.)
3. **Inoculation that backfires** — naming a weakness without a strong reframe reads as a confession, not a strength. (Mitigation: every honest-assessment panel ends with a bold, dollar-quantified reframe — never just a qualitative "this still works".)
4. **Reactance from over-claiming** — if any sentence sounds like sales copy, every preceding sentence is retroactively distrusted. (Mitigation: forbidden-word list; "we would" not "you should"; soft Next Steps.)
5. **Vulnerability disclosure overdone** — Will's "A Note Before You Read" needs to be brief and confident, not self-effacing. The pratfall effect requires competence as the dominant signal. (Mitigation: 80–120 word ceiling; one mistake-or-limitation, not several.)
6. **Specificity loss** — placeholder copy (May 6: "Refer to the detailed comparable adjustment analysis…") destroys the entire credibility stack. Every page that ships with placeholder copy ships the wrong report. (Mitigation: Track A in `06_production_plan.md`.)

### Outstanding questions for Will
- Is there a regional psychology variation between Burleigh Waters (premium / older buyer) and Robina (younger family) that should drive different narrative voice per suburb?
- How much should the report acknowledge the seller's emotional investment in their renovation vs the data showing renovations rarely return dollar-for-dollar? The seller-book Chapter 1 navigates this well; the appraisal needs to be more delicate because it's personal to *their* home.

### Pass verdict
**Strong on principle, vulnerable on execution.** The strategy is correct; the execution is one prompt regression away from looking generic. The editorial-review checklist is the load-bearing safeguard.

---

## Pass 2 — Data pass (does every claim trace?)

### What we want to be true
- Every dollar figure on every page traces to either (a) a comparable sale in `Gold_Coast.<suburb>`, (b) a stat from `precomputed_market_charts`, or (c) a citation in `01_psychology_principles.md §8`.
- Every percentage has a denominator visible somewhere in the document.
- Every "across N sales" claim has the dataset and time window stated.
- Every "research shows" claim has an author, year, and effect size.

### What could go wrong
1. **Stale data.** Market context page references a median that has shifted. (Mitigation: the data lives in `precomputed_market_charts`, refreshed nightly. The report is rendered with the freshest snapshot. Microsite re-renders on data drift.)
2. **Comp set bias.** Comparable selection scoring favours recency over similarity (or vice versa) in a way that systematically biases the range. (Mitigation: log every comp-selection's score breakdown to `appraisal_render_jobs`. Will spot-checks 1 per week.)
3. **Confidence band disclosure.** Wide ranges that aren't labelled `directional_only` look uncertain rather than honest. (Mitigation: enforce the directional-only flag at range_width / midpoint > 25%.)
4. **Citation erosion.** When the editorial agent paraphrases a study, the cited effect size sometimes drifts from the source. (Mitigation: `01_psychology_principles.md §8` is the locked citation table; the editorial agent receives this table as a system-prompt frozen reference. Adding a new citation requires editing the table, not the prose.)
5. **Source-counting hubris.** Phrases like "60+ studies, 14 academic papers, 2,153 sales" are powerful but become a liability if a single number is wrong. (Mitigation: verify the count quarterly. Document the audit in `MEMORY.md`.)
6. **Domain estimate accuracy claim.** "89% overvalued, 1,689 estimates tested" is one of our strongest hooks. If it ages or changes (next quarter's audit might find 87%), the report must update. (Mitigation: pull this number live from a quarterly audit script, not a hardcoded value.)

### Outstanding questions
- Should we surface comparable-set quality directly to the seller? E.g. *"Six high-quality comparables with property-specific adjustment confidence scores ≥ 0.75."* It makes us look forensic. It also makes us look uncertain in the rare case that quality is low.
- For directional-only properties (>$2.5M), how do we communicate the absence of a single figure without losing the seller? The `valuation_directional.md` work has already partially solved this, but the appraisal version may need different framing.

### Pass verdict
**Strong on infrastructure, vulnerable on stewardship.** The data exists and the methodology is sound. The risk is curation drift — the wrong number creeping into a report we've sent. Quarterly audit + automated checks at render close the gap.

---

## Pass 3 — Design pass (does it look unmistakably ours?)

### What we want to be true
- A homeowner who flips through three agents' appraisals can identify ours without reading the title.
- The cover treatment, copper callout, twilight photography, and information density all carry the brand.
- Charts headline their conclusion, sources are cited, sparklines appear inline.
- Typography ramps deliberately; no rivers, no widows-and-orphans, no orphaned headings.

### What could go wrong
1. **Generic feel via stock typography.** Poppins is a competent default but used by thousands of agencies. (Mitigation: consider a paired display serif — GT Sectra, Larken — for headlines. Or commission a custom display weight.)
2. **Photography compromise.** Twilight isn't always available; mid-day photos kill the cover. (Mitigation: editorial photographer roster; pre-approved twilight slot per property; defer report send if photo isn't ready.)
3. **Chart noise.** Default chart libraries produce gridlines, axis labels, default palettes. None of which we want. (Mitigation: locked chart palette; FT-style title-as-conclusion; matplotlib templates checked into repo.)
4. **Inconsistent rendering across editions.** Headless-Chrome PDF renders differently on different machines. (Mitigation: containerised render environment; visual diff on every commit.)
5. **Print over-design.** Designer adds visual flourishes that don't survive in headless-Chrome, and HTML+CSS doesn't reach InDesign-level kerning quality. (Mitigation: design system constraints in `05_visual_system.md`; explicit "what we don't do" list.)
6. **Designer-engineer translation gap.** The designer delivers visuals; the engineer wires data; quality slips at the seam. (Mitigation: HTML+CSS is the only delivery format. Designer paints in the same medium we render in.)

### Outstanding questions
- Is the FA cover (April 29) the canonical direction, or does it need a refresh once the full 36-page system exists? The cover should be the strongest piece, not the only piece, in the visual system.
- Does the print edition warrant true InDesign typography, or does the HTML+CSS path get us 95% of the way at 30% of the cost?

### Pass verdict
**Strong on intent, dependent on execution.** The visual system is articulated. The risk is dilution as the system scales to 36 pages and many edge-case templates. Disciplined editorial review prevents drift.

---

## Pass 4 — Distribution / object pass (is the *thing* worthy of being on the dining table?)

### What we want to be true
- The print edition is the second most beautiful object in the seller's home, after their wedding album.
- The package — slim matte box, foil-blocked logomark, sealed envelope, business card pocket — feels deliberate.
- The microsite extends the print, doesn't compete with it. The seller can return on day 7, day 14, day 30 and see something new.
- The video isn't a sales pitch; it's a 90-second narration of the verdict by Will, who is identifiable as a person, not as an agent.

### What could go wrong
1. **Print quality variance.** Different print partners produce different colour, paper, binding outcomes. A sub-par print run undoes the digital halo. (Mitigation: single-partner relationship; mandatory proof on every run; quality guarantee in the partnership.)
2. **Packaging cost vs perceived value.** A $30 slim box is exceptional; a $5 envelope is forgettable. The economics support the higher spend. (Mitigation: lock the package spec in `05_visual_system.md §8`. Don't compromise.)
3. **Microsite under-investment.** A printed report without the microsite is half the deliverable. Sellers used to instant digital expectations will judge us by both surfaces. (Mitigation: ship microsite v0 in parallel with v0 print, even if minimal.)
4. **Video labour.** Per-report video is the most time-consuming track. Will burns out; videos slip. (Mitigation: defer per-report video to Phase 2; fall back to per-suburb generic video for early reports until cadence builds.)
5. **Hand-delivery scaling.** Per-report courier is fine at 1/week; not at 5/week. (Mitigation: at 5+/week, a Fields runner. Don't scale that until the unit economics demand it.)
6. **Microsite token security.** Random discovery of someone else's appraisal would be reputational. (Mitigation: sufficiently entropic tokens; rate-limited; no SEO indexing.)

### Outstanding questions
- Should we send the digital edition first, then the print edition only after the first conversation? Or both at first contact? The two-step approach builds anticipation; the single-step is operationally simpler.
- Is hand-delivery the brand-builder, or is courier acceptable? The hand-delivery moment is itself part of the experience.

### Pass verdict
**Strong on ambition, dependent on operations.** The distribution moment is half the story. Execution there determines whether the report is a remarkable object or just a polished PDF.

---

## Pass 5 — Competitive moat pass (can a competitor copy this in 12 months?)

### What we want to be true
- The original-data layer (2,153+ Gold Coast sales analysed, suburb-specific adjustment rates, Domain accuracy audit) cannot be replicated without rebuilding our pipeline.
- The editorial method (7-stage AI pipeline producing dollar-quantified, locally-named, citation-backed prose) cannot be replicated without rebuilding the prompt engineering and the data integration.
- The visual + interactive layer cannot be replicated without rebuilding the design system, the print pipeline, and the microsite + video architecture.
- The combination cannot be replicated by any single competitor in 12 months.

### What could (already does) go wrong
1. **CoreLogic / Pricefinder ships their own AI summary.** Their advantage is the data; ours is the editorial. They're not editorial-strong. But if they build it, every franchise gets it. (Mitigation: stay editorial-dominant; the moat shifts from data to prose.)
2. **A premium agency hires a magazine designer.** Visual moat is the easiest to erode. (Mitigation: doubles the importance of the data + editorial moats; visual is the icing, not the cake.)
3. **A franchise-wide template ships AI-generated CMA.** This is the most likely existential threat. The good news: Australian franchises are slow; the bad news: when one ships, all of them get it. (Mitigation: ship our v1 within Q3 2026 before this threat lands.)
4. **The pipeline-induced regression problem.** Our own moat regresses if the editorial prompt drifts (May 6 incident). (Mitigation: locked checklist + version control + automated review.)
5. **The "Will burns out" risk.** Will is a single point of failure for editorial review, video, hand-delivery, and operations. (Mitigation: as Track D + Track B mature, the system becomes more autonomous. Defer hand-delivery scaling and per-report video until volume justifies a second human.)
6. **Buyer-side acquisition not scaling.** The whole funnel assumes sellers reach `analyse-your-home`. If acquisition stalls, the report is unread. (Mitigation: addressed in the `Focus_System` initiative — sellers are pulled in via the seller book, market intelligence pages, and FB content. Not the appraisal team's problem to solve.)

### Outstanding questions
- Is the moat 12 months or 24 months? Aggressive estimate is 12; conservative is 24. Either way, ship v1 hard.
- When CoreLogic / Pricefinder eventually ships AI-CMA, what does our v3 look like? Probably: real-time market dashboards, post-listing decision-support, full CRM integration. We can be planning that already.

### Pass verdict
**Strong on layering, dependent on speed.** Each individual moat is partially defensible; the combination is highly defensible; the time window is finite. Build aggressively, then iterate to widen each layer.

---

## Pass 6 — Ethical / legal pass (can any sentence get us into trouble?)

### What we want to be true
- No advice given. Every recommendation framed as "we would" not "you should".
- No predictions stated. Conditional language only ("the data suggests", "historically this pattern has preceded").
- No price guarantees. Implied or otherwise.
- No claims about a property's future value, condition, or marketability that exceed what the data supports.
- No comparisons to specific competitor agencies that could be construed as defamatory.

### What could go wrong
1. **Implicit guarantee in pricing strategy.** "Recommended listing range $1,765,000–$1,825,000" can be read as a guarantee even if labelled. (Mitigation: every range includes "subject to property analyst inspection". The disclaimer language is locked.)
2. **Forecast language drift.** Editorial agent occasionally writes "the market will…" instead of "the market has historically…". (Mitigation: editorial review checks for forbidden phrases.)
3. **Comparative claims.** Statements like "we charge a slightly higher fee because we deliver better results" risk substantiation issues if a complaint is made. (Mitigation: keep these claims to "we" not "we vs them"; cite our own evidence; avoid named comparisons in writing.)
4. **Body corporate / strata claims.** For unit reports, an implied claim about strata health that turns out wrong creates liability. (Mitigation: source language: "based on the most recent strata search disclosure"; defer to legal advice for adverse findings.)
5. **Domain accuracy claim.** "89% overvalued, 1,689 estimates" is comparative. If Domain disputes the methodology, we need to be able to defend it. (Mitigation: keep the audit dataset and methodology documented; happy to share with Domain if asked.)
6. **Editorial Voice / No-Advice rule** is documented in `feedback_no_advice_data_only.md` (memory). Enforced.

### Outstanding questions
- Are we comfortable naming specific competitors (Ray White, McGrath, Kollosche) in the strategy doc here, or should those be coded references?
- The competitive audit doc names competitor weaknesses. That's internal-only; ensure it doesn't leak into customer-facing copy.

### Pass verdict
**Acceptable risk profile.** Strict rules embedded in editorial review. As long as the review is enforced, this is well-controlled. Internal docs (this folder) include competitor names; customer-facing copy does not.

---

## Pass 7 — The "would I sign?" pass (the seller's first read)

### Walk a hypothetical seller through the report
- Lisa is 48, lives in Robina, four-bed home, raising two teens. Husband Mark is the analytical one. They've had Domain on their phone for years and have a number in their head: $1.6M.
- They submit the address on a Tuesday night. Wednesday morning, they receive a "we'll be in touch in 24h" email.
- Thursday afternoon, they get the digital report. They open it on Lisa's iPad while making dinner. Mark joins after 30 minutes.

### What they should think, page by page
- **Cover** — *"This looks different. Like a magazine."* (Halo effect.)
- **The Fields Take** — *"Three comparable sales… $1,725,000 to $1,925,000…"* Lisa adjusts her mental anchor downward, but only slightly because the range is reasonable. The strengths panel makes her feel her renovation mattered (the dual-living mention). The trade-off panel acknowledges the two-storey layout. Both Lisa and Mark feel: *"They're not just flattering us."*
- **The Comparable Evidence** — Mark is now driving. He's read the line items, checked the maths, and approved. The subject's dollar adjustments are credible.
- **Honest Assessment** — Lisa pauses on "658 m² lot, 107 m² less than the nearest comp". She'd never thought of the lot size as a weakness. The reframe ("the outdoor infrastructure more than compensates for the land gap") feels honest, not defensive.
- **Property Through Our Eyes** — They smile. The room scoring is fair. The 8/10 main bathroom matches their own assessment.
- **Location & Lifestyle** — *"They knew about the wetland reserve."* The named-everything paragraph is the moment local mastery is established.
- **Buyer Pool** — Lisa imagines the family who would buy from them. Narrative transportation works.
- **Pricing Strategy** — Mark sees the academic citations. He recognises Cardella & Seiler from a *Forbes* piece he read. *"This is real."*
- **Campaign + Photography + Open Home** — Lisa likes the twilight photography emphasis. Mark likes the structured timeline.
- **Why Fields + Next Steps** — They both notice that the report doesn't ask for the listing. *"They want a conversation, not a contract."* Reactance avoided.
- **Final note** — A handwritten note from Will, named, signed. *"He read this. He wrote this. He cares."*
- **Closing thought** — *"Of the three reports we'll get, this is the one we'll show our friends. Of the three agents we meet with, he's the one we want to start with."*

### What could break this experience
- **Placeholder copy** anywhere kills the spell.
- **One bad number** kills the spell.
- **One forbidden word** ("nestled in a sought-after pocket") kills the spell.
- **A weak photograph** kills the cover spell. The photo is the first credibility test.
- **A pushy CTA** at the end kills the reactance management.
- **Generic city-wide stats** instead of suburb stats kills the local mastery proof.

### Pass verdict
**The system is designed to deliver this experience. Reviews 1–6 surface the operational risks. As long as Track A (content correctness) is held, the experience is reproducible.**

---

## Summary — where the strategy is strong, where it's vulnerable

| Pass | Strength | Vulnerability |
|---|---|---|
| 1 — Psychology | Principles correct, science load-bearing | One prompt regression from generic |
| 2 — Data | Infrastructure sound, methodology rigorous | Stewardship — drift if not policed |
| 3 — Design | Direction clear, FA cover proven | Translation gap from designer to engineer |
| 4 — Distribution | Print + microsite + video covers all surfaces | Operational overhead, especially per-report video |
| 5 — Competitive moat | Three layers, hard to copy in combination | Time window is finite; ship v1 fast |
| 6 — Ethical / legal | Rules clear, disclaimers locked | Editorial drift toward advice/predictions |
| 7 — Seller experience | The full design produces the right reaction | Any single component breaking breaks the whole |

**The single most leveraged action:** lock the editorial review checklist (`04_content_modules.md §G`) as a hard pre-render gate. It defends every other pass.

---

*Owner: Will Simpson · Updated 2026-05-06 · Reading order: read after `06_production_plan.md`, before `08_roadmap.md`.*
