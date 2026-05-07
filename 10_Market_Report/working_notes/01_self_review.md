# Self-Review — Three Passes

**Reviewer:** Claude (the document author, reviewing its own work — declared bias)
**Date:** 2026-05-06
**Scope:** Strategy docs 01-07 + sample draft

The honest disclosure: a self-review is a weaker instrument than an external review. The point of these passes is to surface the obvious problems before Will sees the work, not to substitute for human review. Each pass uses a different lens.

---

## PASS 1 — Gaps, Weak Sections, Missing Data, Missing WOW

### What's missing or thin

1. **No SEO / discovery plan.** The strategy docs assume traffic lands on the report; they don't address how the report itself becomes discoverable beyond the existing FB / LinkedIn / press channels. A 12-month organic-search plan ("Burleigh Waters market report" SERP, suburb-page structured data, news sitemap registration) needs to be its own document — call it `08_seo_distribution_plan.md` or fold into the conversion architecture. Adding this gap to recommendations.

2. **No competitive intelligence mechanism.** When Knight Frank, CoreLogic, or Domain publish, Fields should react quickly with a one-page commentary that cites them, agrees on some points, dissents on others. This both keeps Fields in the conversation and accelerates citations the other way. Not in the strategy docs. Add as a recurring habit in `07_production_playbook.md` Section 11.

3. **No partnership / co-citation strategy.** The Informed Observer archetype (Section A.4 of the playbook) is supposed to amplify the report. The strategy currently *attracts* them passively (methodology, footnotes) but doesn't *engage* them actively. A specific outreach list — three local journalists, two brokers, two academics, two buyers' agents — should be in scope.

4. **The "Fields Conviction Index" calculation is illustrative, not built.** The blueprint and visual spec assume FCI exists; the production playbook flags it as not-yet-built. This is the largest engineering risk in Q2 2026. The next operational step is `pipeline/fci_calculator.py`. Without it, Issue 1 cannot ship as designed.

5. **The four-source reconciliation chart requires data parity that may not exist.** The sample draft uses Cotality / Domain / PropTrack / SQM lines. We have SQM (postcode-level). We may not have suburb-level Cotality access. PropTrack data access may require partnership. This is a flagged risk in `07_production_playbook.md` but the sample draft assumes it works.

6. **The Real Pain & Gain calculation depends on holding-cost assumptions** that I have stated illustratively. The actual numbers (e.g. "council rates 0.6%") need to be validated against actual Gold Coast council rate schedules per property type. If the assumptions move materially, the table moves materially.

7. **No specific plan for the photography refresh.** The playbook says "Will: shoot list + 2 days of fieldwork." That's a directional statement, not a plan. A shot list (30 frames, geographically distributed across the three suburbs, captioned with date and one observation) is the missing artefact.

8. **No dispute / takedown mechanism.** What happens if a named individual or business objects to a finding? (E.g. an agent named in the agent-concentration data, or a property owner whose specific transaction is anonymised but recognisable.) The methodology page mentions a correction policy but not a dispute process.

9. **The audio version's content is undefined.** Format is named (20-25 minutes, Will-narrated), distribution is named, but the actual editorial structure of the audio is not. Is it the editor's letter expanded? The tension chapter? A walkthrough of one suburb? This is a 1-page sub-strategy that should be added.

10. **No internationalisation thought.** The southern Gold Coast attracts overseas migration; the report writes for an Australian-domestic reader. If Singapore / Hong Kong / UK readers are part of the buyer pool (they are, per the migration Sankey), a brief "for international readers" footnote on macro context would matter.

### Where the WOW is concentrated

- The Fields Conviction Index (cover numeral): **strong WOW** if delivered as designed.
- The Fields Conviction Map: **strong WOW** if it becomes the screenshot people share.
- The four-source reconciliation chart: **medium-strong WOW** for Informed Observers; muted for Curious Owners.
- The Real Pain & Gain: **strong WOW** for finance-literate readers; **medium WOW** for others.
- The flood-data honesty panel (Burleigh Waters): **strong WOW** locally; lower elsewhere.
- The conviction tracker (Issue 2+): **strong WOW**, but compounds over time — Issue 1 doesn't have it.

### What's missing in the WOW department

- **No interactive WOW in Issue 1.** The "What's similar to your home?" tool is in the blueprint as an Issue 1 deliverable, but it's a separate engineering project. If it ships, it's the strongest single conversion driver. If it doesn't ship for Issue 1, it should at least be a teaser on the report's web edition.

- **No "data we got our hands on that nobody else has" headline.** The four-source reconciliation is good but technical. A more lay-readable WOW would be e.g. "we walked every street in Burleigh Waters and analysed 142 sale photos for renovation state" — the *labor* WOW. Not in the strategy. Should be considered.

- **No physical artefact WOW.** The print edition is described well but a single tactile detail — embossed cover, gold-foil edition number, signed copy with hand-numbered limited print run — would push print credibility higher. Cost a few dollars per copy; massive trust signal.

### Weak sections in the strategy docs

- **`05_conversion_architecture.md` Section 11 (failure-mode plan)**: tactical, but not testable. Each "audit X" line should have a specific PostHog event or metric with a threshold. Without thresholds, "audit" is hand-waving.

- **`07_production_playbook.md` Section 7 (risk register)**: the data-error risk has only "two QA passes" as mitigation. Recommend adding: a statistical sanity-check against last quarter's published numbers; a third-party (a friend in the property industry) reads Issue 1 before publication.

- **`02_psychology_playbook.md` Section A.3 (Curious Owner)**: the strategy says "their primary CTA is subscribe, not enquire." But the Q3 deadline pressure means Curious Owners need a *parallel* conversion path — into the print edition request, the Position Report, or the Buyer Assist product. The current plan funnels everyone through the same nurture sequence. Some segmentation should be designed in.

### Weakness in the sample draft specifically

- The Allambi Avenue / two-streets-over example (used twice) is the strongest narrative-transportation device in the draft. It works. But it's used in both the Tension chapter and the Burleigh Waters identity page, which slightly diminishes its impact in the suburb section. Recommendation: use a different anonymised case in the suburb section.

- The Macro page (8) does not currently include a chart showing southern Gold Coast macro indicators specifically, only national. A "what the macro means for the southern Gold Coast" sidebar is missing.

- The closing letter (page 30) tries to do three things — reflection, soft CTA, invitation. It's doing too much. Recommendation: trim to two paragraphs (reflection + invitation), move the soft CTA to the back-page footer.

---

## PASS 2 — Conversion Psychology, Credibility, Editorial Compliance

### Conversion psychology audit

Going through each principle from `02_psychology_playbook.md`:

- **Loss aversion (B.1)** — Sample draft never displays a single number that triggers loss frame. Pass.
- **Endowment effect (B.2)** — Comparable-sale walkthroughs in §10 do *not* currently lead with the empathic framing ("the owners of this home priced from their kitchen renovation"). Adjustment needed in `03_content_blueprint.md` Section 5.10.
- **Anchoring (B.3)** — Cover headline number IS a single number (FCI = 108.4). This is on the boundary. Argument for: it's a *composite* number, not a price; it's defensible. Argument against: psychological anchoring still applies. Decision: keep as the cover device because the alternative (ranges) doesn't work for an index. Mitigation: the FCI scale interpretation (80-95 cooling, 95-105 balanced, etc.) is in the playbook but should be on the cover or facing page so the number is contextualised immediately.
- **Status-quo bias (B.4)** — Closing block of suburb sections uses signals not advice. Pass.
- **Sunk-cost (B.5)** — Sample draft does not yet include the Home-Improvement ROI sidebar (planned for Q1 2027 issue, not Q2). Acceptable.
- **FOMO/FOMM (B.6)** — Forbidden patterns absent. Hooks use questions and tensions. Pass.
- **Confirmation bias (B.7)** — "What surprised us" callouts present in the suburb sections. Pass.
- **Authority bias (B.8)** — Will named on cover, in editor's letter, in closing. Methodology demonstrates authority. Pass.
- **Narrative transportation (B.9)** — Allambi Avenue case opens the Burleigh Waters section. Robina and Varsity Lakes sections (abbreviated in the draft) currently *don't* have a named-but-anonymised opening case. **Gap. Fix in next pass: every suburb section needs one.**

### Trust architecture audit

- **Methodology disclosure (C.1)** — Page 28 fulfils. Pass. Recommendation: add citation density (footnote numbers in the body that resolve to a numbered list on the methodology page) — currently citations are inline. Footnote density itself signals work.
- **Conditional language (C.2)** — Searched the sample draft for "will", "going to", "set to". Found one instance: "the four numbers we are watching" ("If volume returns first, prices accelerate" — this is conditional, acceptable). One borderline: "The structural shortage is real." Could read as forward-looking. Recommend: "The structural shortage is documented in the data."
- **Named author (C.3)** — Will signed. Pass.
- **What we don't know page (C.4)** — Page 29 fulfils. Pass.
- **Contrarian findings (C.5)** — Two contrarians present: (a) the Real Pain & Gain reframing ("94.9% profitable" is uninformative); (b) "the standoff is hitting the prestige tier first" (canal vs non-canal DOM divergence). Pass.
- **"We got it wrong" page (C.6)** — Issue 1 has a placeholder for the conviction tracker (page 12). Acceptable for first issue.
- **Photographic evidence (C.7)** — Photography brief is in `04_visual_format_spec.md` Section 9. Sample draft references one photo (page 20). Need to ensure all three suburbs get one each in the actual issue — the sample is abbreviated.
- **Citation density (C.8)** — Body cites Cotality, Domain, ABS, RBA, APRA, ICA. Methodology cites Abelson, Genesove & Mayer, Loewenstein, Northcraft & Neale. Adequate but could be denser — recommend adding a footnote numbering system for ease of reading and academic feel.

### Objection pre-empt audit (D)

| Objection | Where in draft | Pass / fail |
|---|---|---|
| "How do you know if you've never sold a house?" | Editor's letter + methodology | Pass |
| "Why trust this over CoreLogic / Domain?" | Methodology page sidebar describing differences | **Currently absent** — need to add to page 28 |
| "How does it help me right now?" | Three numbers we're watching closing each suburb section | Pass |
| "What's the catch?" | Page 1 colophon: funding model declared | Pass |
| "Are they going to sell my data?" | Page 1 colophon | Pass |
| "What's their angle?" | Page 1 colophon | Pass |
| "Won't a free report be shallow?" | Length, density, citations | Demonstrated implicitly. Pass. |
| "This is just last quarter's news" | Page 1 colophon: data closed date | Pass |

**One gap to fix:** add a "Where we differ from Cotality / Domain / RP Data / RPRP" sidebar to the methodology page.

### Editorial rules compliance

- **No advice** — searched sample draft for "you should", "consider", "recommend", "act now". Found none. **Pass.**
- **No predictions** — searched for "will", "going to", "set to", "expected to", "predicted". Found:
  - "the four numbers we are watching" — acceptable (signal, not prediction).
  - "If volume returns first, prices accelerate. If sellers capitulate first, the same data points re-form" — borderline. Reads like prediction even with conditional framing. **Soften to: "We can describe the conditions under which each scenario unfolds."** Already used; reinforces the same point. OK.
  - "this number is not a counsel against buying" — fine.
- **No single valuation in headlines** — searched for $ amounts in headers. Found Burleigh Waters median ($1,830,000) inside body prose, framed in the bimodal context. Acceptable. Confirm no header is a single number. **Pass.**
- **Value framing** — Burleigh flood section frames overlay as evidence to weigh, not flaw. Pass. The "low-maintenance, lower entry price, walking distance to beach" pattern from the playbook is not yet used in the sample draft (probably because Burleigh canal-front *isn't* low-entry). Recommend: apply value framing to non-canal Burleigh — "non-canal Burleigh sits at a lower entry price than canal-front and within walking distance of the beach"... etc.
- **Forbidden words check** — searched: stunning, nestled, boasting, rare opportunity, robust market, unprecedented, hot market, must-see, gem, premium, exclusive. Found: "premium" used twice ("family-premium suburb", "prestige tier"). Need to substitute. Recommend: "family-tier" or "high-tier" instead of "family-premium".
- **Number format** — sample uses `$1,250,000` consistently. Pass.
- **Suburb capitalisation** — sample capitalises Burleigh Waters, Robina, Varsity Lakes consistently. Pass.

### Voice and hedging

- The voice is calm, considered, evidence-led. The "I built this" framing is in the editor's letter and closing. Strong.
- The hedging hierarchy is used appropriately. "The data is consistent with..." appears multiple times for medium-strength claims; "the data shows..." for strong claims; the report avoids the "weak" hedging level (because if a finding is that weak, it shouldn't be in the report).

### What still needs editorial pass

The sample is a draft. A real second pass would catch the dozens of small things — passive voice sentences, sentences that start with "the", paragraphs that are slightly too long. Those are not audit-pass concerns; they are line-edit concerns. Flagging but not fixing here.

---

## PASS 3 — "Set a Global Standard" Audit

The brief was: not just beat local agents, but **set a new standard globally**. This pass asks: what would Knight Frank, the FT, the Economist, or NYT Upshot do that we haven't?

### What we have that meets or beats global standard

- **Named author with personal accountability** — beats Knight Frank (anonymous), beats CoreLogic (institutional), matches HTW (valuer-by-valuer). **Strong.**
- **Suburb-level depth** — beats every global authority. None of them go below capital-city. **Strong.**
- **Methodology transparency** — matches Zillow Research (full disclosure), matches RBA (source line under every chart). **Strong.**
- **Vulnerability ("what we don't know") section** — beats virtually all property reports globally. **Strong.**
- **Conviction tracker (Issue 2+)** — beats all named property reports. Domain, Knight Frank, banks all forecast — none publish accuracy. **Strong differentiator.**
- **Real Pain & Gain after-cost returns** — beats CoreLogic Pain & Gain (which is nominal-only). **Original contribution.**
- **Four-source reconciliation chart** — beats all property reports. None reconcile. **Strong contribution if the data is achievable.**
- **Editorial-grade voice with no advice and conditional language** — matches FT / Economist standard. **Strong.**

### Where global standard demands more

1. **Visualisation craftsmanship.** The strategy specifies FT Visual Vocabulary discipline. But FT/NYT/Bloomberg achieve greatness through *years* of design polish. Issue 1 with even a Quarto+Typst template will look 80% there. The remaining 20% is hand-crafted by senior designers. Recommendation: contract a senior editorial designer for the cover and section-opener typography for Issue 1, even at higher cost. This is the difference between "looks like data journalism" and "is data journalism."

2. **Long-term archive moat.** Halifax index runs from 1983. PIRI runs since 2007. HTW Month in Review has 13+ years of archives. The single strongest moat in property reporting is *consistency*. Fields starts at zero. The only way to compete on this axis is to commit publicly to never missing an issue and to make the archive permanently accessible. Recommendation: add a public commitment ("We commit to publishing every quarter without exception, and to making every back issue freely available") to the colophon and the methodology page.

3. **Original primary research.** Knight Frank publishes the Family Office Survey — original primary data nobody else has. Fields can analogously publish:
   - A *Gold Coast Buyer Survey* — 100 surveyed buyers per quarter, what they want, what they fear, what they paid attention to. Could be administered as a one-question SMS at end of an inspection.
   - A *Gold Coast Seller Survey* — for sellers who recently sold, how the campaign actually went vs how it was sold to them.
   The first survey is in scope as an Issue 2-3 expansion. Recommend adding to a future-issues planning doc.

4. **Long-form thought-leadership pieces.** The Economist *Special Reports*, FT *Big Reads*, and Knight Frank's annual sub-themes (The Wealth Sizing of Asia, The Future of Office) are the deeper editorial layer. Fields should plan one annual long-form essay alongside the quarterly schedule. Topic for Year 1: "The southern Gold Coast in five years — what the data says about what could change." Conditional language only; not a forecast. Treat as the December 2026 / Issue 4 companion piece.

5. **Citations of the report by other outlets.** Global-standard reports get cited automatically because the report becomes the source of record. The way to engineer this is to (a) make the data freely available with citation guidance, (b) actively pitch the report to local journalists for first-look access, (c) write companion articles that themselves are citation-bait. The conversion architecture mentions outreach in passing; recommend a specific PR push for Issue 1 with names, beats, and a one-page press kit.

6. **An interactive web layer that exceeds the PDF.** The Knight Frank Wealth Report is excellent in PDF and very weak online. NYT Upshot and Bloomberg Graphics flip the priority. A truly global-standard web edition does scrollytelling, interactive charts, address-level personalisation, and ambient audio — not just a PDF reflowed for screen. The strategy mentions the web edition but doesn't detail this. Recommend a separate scrollytelling design doc for Issue 1's web edition.

7. **Accessibility and internationalisation.** Best-in-class reports are screen-reader accessible (alt text, structural headings), available in dark mode, and (for international subjects) include unit conversions and currency context. The production playbook mentions Lighthouse 90 and alt text — that's adequate but not exceptional. Recommend adding a small section in `07_production_playbook.md` on accessibility commitments and (later) translation for international reader segments.

8. **A signature visual identity that is recognisable from a thumbnail.** Economist red, FT salmon-pink, Knight Frank gold, Domain orange — readers identify the source from a 200-pixel thumbnail. The Fields deep ocean blue + cream palette is good but might not be distinctive enough at thumbnail. Recommend: in the cover design phase, develop one distinctive *device* — a wordmark, a chart-style fingerprint, a recognisable typographic decoration — that makes a Fields chart unmistakable on a social feed. This is a 1-day designer task; the payoff is years.

9. **Annual Year-in-Review owns December media.** Cotality's Best-of-the-Best owns December — every TV network runs it. The strategy includes a Q4 issue but doesn't fully exploit this. Recommend: pre-pitch the Year-in-Review to local media in October, with embargo for first Friday of December. The free CSV + chart pack accompany.

10. **The audio episode could be extraordinary or just adequate.** The strategy specifies 20-25 minutes Will-narrated. That's good. What pushes it to global-standard: production design (background music, edited transitions, sound design at section breaks), a guest segment (one local broker / academic / journalist per issue), and a public transcript with timestamps. None of this is currently in the strategy. Recommend extending `07_production_playbook.md` with an audio production sub-spec.

### What "global standard" specifically means we are NOT trying to do

- **We are not trying to match Knight Frank's global reach.** We are a Gold Coast operator. Our ambition is to be the *single best* property report for *one specific market*, not the broadest property report.
- **We are not trying to match Cotality on data volume.** We can never have more transactions than they do. Our advantage is local depth and editorial integration.
- **We are not trying to match Bloomberg's interactive infrastructure.** They have a 50-engineer graphics team. We can use Quarto+Typst plus modest React enhancements.
- **We are not trying to be a luxury brand like the Wealth Report.** Our identity is closer to *The Economist* — restraint and rigour, not ornament.

### The one paragraph that says whether we set the standard

> The Fields Quarterly sets a global standard for property reporting on a single specific market — the southern Gold Coast — by combining named authorial accountability, suburb-level analytical depth no national publisher can match, a transparent methodology that meets RBA and Zillow disclosure standards, an explicit "what we don't know" page that beats nearly every property publisher globally, the only annual after-cost real-returns analysis published in Australian property reporting, the only multi-source price reconciliation any publisher attempts, and an in-text conviction tracker that grades the publisher's previous quarter against subsequent data. We do not exceed the global standard everywhere; we exceed it where it matters for our reader, and we match it where the global standard is already excellent.

That's the sentence. If, after Issue 1 ships, that paragraph is still defensible — we have done what was asked.

---

## CONSOLIDATED ACTION LIST FROM REVIEWS

### Must-fix before Issue 1 ships
1. Build `pipeline/fci_calculator.py` — without it, Issue 1 cannot ship. **Highest-priority engineering task.**
2. Verify suburb-level data parity for the four-source reconciliation chart. If parity isn't achievable, replace with a different signature original.
3. Validate Real Pain & Gain holding-cost assumptions against actual GC council rate schedules.
4. Photography shoot list — 30 frames, 2 days fieldwork.
5. Add "Where we differ from Cotality / Domain / RP Data" sidebar to methodology page.
6. Substitute "premium" everywhere ("family-premium suburb", "prestige tier") with non-forbidden language.
7. Soften the borderline-forecasting line in the tension chapter: "We can describe the conditions under which each scenario unfolds."
8. Add named-but-anonymised opening case to Robina and Varsity Lakes suburb sections.
9. Apply value framing to non-canal Burleigh Waters explicitly.
10. Add public consistency commitment to colophon / methodology page.

### Should-add for Issue 1 if possible
11. Endow the Curious Owner archetype with a *parallel* conversion path (not just subscribe).
12. Develop a thumbnail-recognisable visual device (wordmark or chart-fingerprint).
13. Pre-publication PR pitch list (3 journalists, 2 brokers, 2 buyers' agents, 2 academics).
14. Add audio production sub-spec to `07_production_playbook.md`.
15. Add an "About this commitment" line: never miss an issue, archive permanently free.

### Plan for Issue 2-4
16. Gold Coast Buyer Survey (Issue 2-3 administration; Issue 3 publication).
17. Annual long-form thought-leadership essay (Q4 2026 / Issue 4 companion).
18. Dispute / takedown mechanism documented.
19. Internationalisation footnote for the international migration audience (in macro chapter).
20. Audio guest segment (one local figure per issue from Issue 2 onwards).

### Strategy doc gaps to fix
21. Add `08_seo_distribution_plan.md` — covered in distribution but deserves its own document.
22. Add "Competitive intelligence reaction" cycle to `07_production_playbook.md`.
23. Add specific PostHog event thresholds to `05_conversion_architecture.md` Section 11 (failure modes).
24. Add third-party pre-publication review to `07_production_playbook.md` Section 7 (data-error mitigation).

These 24 actions are the difference between a strong strategy and an excellent one. Most are <2 hours each; the FCI calculator is the only multi-day engineering item.
