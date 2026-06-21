# Compliance Audit — "Your Home" Digital Appraisal Mini-Site

**Prepared:** 21 June 2026 · **Author:** Fields VM operations agent
**Subject:** `https://fieldsestate.com.au/your-home/:slug` (e.g. `/your-home/20-silkyoak-court-burleigh-waters`)
**Premise:** The "your home" mini-site is a **digital property appraisal**. It is what a homeowner receives when they ask Fields what their property is likely to sell for. It must therefore meet the legal obligations and industry best practices that apply to the real-estate appraisal process.

**Source documents reviewed:**
- *Sales and Marketing — Part 1* (REIQ/CPPREP-style training), **Chapter 3 — The Appraisal Process** (ss 3.1–3.9) and Ch.1.7 (legal/ethical marketing).
- *Property Occupations Act 2014 (Qld)* ("PO Act") — relevant sections extracted below.
- *Competition and Consumer Act 2010 (Cth)* — the provided PDF is **Volume 4: Schedules** and does **not** contain the operative Australian Consumer Law (ACL) sections; the ACL obligations below are taken from the training material's authoritative summary and the PO Act's own cross-reference to ACL s 30 (PO Act s 210). This should be verified against the full ACL (Schedule 2) text before any external sign-off.

---

## 1. Executive Summary

The mini-site is, on the whole, an **unusually strong, transparent appraisal product** — its evidence layer, named-and-dated comparables, line-item adjustments, conditional language, "no advice" editorial discipline, and human-review gate put it well ahead of a typical agent's CMA on the dimensions that matter most for the *reasonable-basis* and *misleading-conduct* tests.

However, because it **is** an appraisal delivered in response to a seller's request for a price (which squarely engages **PO Act s 215**), several legal and best-practice obligations that normally attach to a written appraisal are currently **missing or under-served**. None of the findings suggest bad faith; they are gaps between a very good marketing artefact and a *legally complete appraisal document*.

**Highest-priority items (fix first):**

| # | Finding | Risk |
|---|---------|------|
| A | Comparable cohort is **18–24 months**, not the statutory **6-month / 5 km / ≥3 sales** CMA definition | PO Act s 215 + Sch 2 (CMA definition) |
| B | **Comparative superiority claim against Domain** ("Fields publishes its accuracy. Domain does not", MAE 11.4% vs 15.0%) — contradicts our own internal finding that Domain beats us in core suburbs | ACL s 18/s 29; PO Act s 212(4)–(5) reverse onus; internal memo |
| C | Document is called a **"valuation"** but is legally an **appraisal/estimate**; the appraisal-vs-valuation distinction is never explained | ACL s 18/s 29; PO Act s 212 (misleading as to nature of service) |
| D | **No appraisal-specific disclaimer/qualifications on the report itself** (only a generic article disclaimer one click away) | Best practice (Ch 3.6); ACL omission risk |
| E | **No "valid until" / currency date** on the appraisal | Best practice (Ch 3.6) |
| F | **No licensee/agent identification** (agency name + Licence No. 4832971) on the report | PO Act marketing rules (ss 209/215); best practice |

The remaining findings (G–N) are medium/low severity and are detailed in §5.

> ### IMPLEMENTATION STATUS — all items actioned 2026-06-21
> | Item | Status | What shipped |
> |------|--------|--------------|
> | A | ✅ Done | Statutory CMA layer (`statutory_cma.py` + `StatutoryCMA` component); see §4.A. |
> | B | ✅ Done | Removed the Domain head-to-head accuracy comparison + "Domain does not publish" line from the valuation; kept Fields' own MAE without superiority framing; removed "1,683 Domain valuations" references from `methodNotes` + `ValuationEvidence`. |
> | C | ✅ Done | "This is a market appraisal … not a sworn or formal valuation by a registered valuer" stated under the valuation headline + in the report footer. (Did NOT wholesale-rename "valuation"→"appraisal" — added the clarifying statement instead, to avoid churn/regression; flag if a full rename is wanted.) |
> | D | ✅ Done | Appraisal-specific disclaimer block in `ReportFooter` (estimate-not-valuation, third-party data, limitation of liability, link to /disclaimer). |
> | E | ✅ Done | "Prepared as at / valid until (90 days)" on the statutory CMA **and** the footer. |
> | F | ✅ Done | Licensee identity + **QLD Licence No. 4832972** in `ReportFooter`. Also corrected a wrong licence number (4832971→4832972) on Disclaimer/About/Editorial pages. |
> | G | ✅ Done | Buyer catchment shares + campaign reach explicitly labelled "modelled … not measured / not a guarantee" (BuyersTab). |
> | H | ✅ Done | "What this appraisal assumes — and what to verify" block (title/encumbrances, flood + GCCC FloodWise pointer, zoning/approvals) on the Valuation tab. |
> | I | ✅ Done | Ownership/authority acknowledgement line at the address-entry step (non-blocking, preserves zero-friction flow). |
> | J | ✅ Done | Costs + Form 6 reference on the Next tab (no published fee figures). |
> | M | ✅ Done | "General information, not financial/legal/tax advice" caveat in the FAQ editorial footer. |
> | K | ◐ Partial | Statutory CMA is now snapshotted on the report doc (reproducible as-at). Broader per-version snapshot retention still recommended. |
> | L, N | ▢ Process | Non-code: keep credential evidence (L); treat the editorial fact-check gate as the licensee check of record before marketing copy ships (N). |
> | ValuationAccuracyPage | ▢ Noted | The public /valuation-accuracy page references Domain methodologically (not a superiority claim on an appraisal) — left in place; revisit if any superiority phrasing is added.

---

## 2. The Obligations — What the Law and Best Practice Require

### 2.1 Property Occupations Act 2014 (Qld)

| Provision | Obligation | Relevance to the mini-site |
|-----------|-----------|----------------------------|
| **s 215 — Representation of price of property (real estate agent)** | If a person wanting to sell asks an agent for information about the likely sale price, and the agent decides to give it, the agent **must** give a **Comparative Market Analysis (CMA)** — or, if a CMA can't be prepared, a **written explanation** of how market value was decided. *Max 540 penalty units.* | **This is the operative section.** Entering an address to receive the report *is* a seller asking for price information. The mini-site is the agent's response → a CMA (or the s 215 "written explanation") is mandatory. |
| **Sch 2 — definition of "comparative market analysis"** | A document comparing the property with **at least 3 properties sold within the previous 6 months**, of **similar standard or condition**, and **within 5 km**. | Defines the minimum the CMA must contain. The site's 18–24 month cohort does not, on its face, guarantee this. |
| **s 212 — False representations about property (licensee/salesperson)** | Must not represent anything false or misleading about a property, **including its value at the date of sale**. **s 212(4)–(5): if you don't have *reasonable grounds* for a representation it is *taken to be misleading*, and the onus is on YOU to prove reasonable grounds.** *Max 540 penalty units.* | Every figure and comparative claim must be defensible. The transparent working strongly supports "reasonable grounds"; unsupported comparative claims (see B) do the opposite. |
| **s 207 / s 208 / s 209** | Marketeers must not engage in misleading conduct, unconscionable conduct, or false representations re residential property (incl. nature of interest, price, characteristics, value at sale, potential income). s 209(3)–(5) mirror the reverse-onus test. | General overlay on all report content. |
| **s 210** | ss 207–209 are **in addition to** other laws, expressly **ACL s 30** (false/misleading reps about sale of land). | Confirms the ACL also applies. |
| **Marketing (ss 209 & 215 per training table)** | Marketing/advertising must correctly state the features of a property and the client's price instructions, and be **checked by the Principal/Licensee**. | Report content and any onward marketing copy must be accurate and signed off. |
| **Part 4 / s 102 — Form 6** | An agent **cannot provide a real estate service unless validly appointed** via a Property Occupations **Form 6**. A defective Form 6 = no authority, no commission, possible penalties. | The appraisal is the *step before* appointment. The report should point to Form 6 as the formal next step (it currently does not). |
| **ss 153–156 — Beneficial interest disclosure** | Disclosure obligations if the agency acquires a beneficial interest. | Low direct relevance now, but note if Fields ever buys/options appraised stock. |

### 2.2 Australian Consumer Law (per training summary; verify against ACL Sch 2)

The ACL makes it unlawful to:
- **Directly or indirectly mislead** as to **price or value** (over/under-quoting) — *ACL s 18, s 30*.
- **Hide or omit material facts** likely to affect **saleability, amenity or value** — *omission as misleading conduct*.
- Make **false or inaccurate claims** — e.g. about **future values/rents/offers**, **capital gains**, **rental returns**, **development potential** — *s 30*.
- Make **misleading comparisons with competitors**, or claim you are the **"best/first/only"** without proof — *s 18, s 29*.
- Publish or solicit **non-genuine reviews/testimonials**, or **falsely claim awards/certifications/endorsements** — *s 29*.
- Engage in **unconscionable conduct** (pressure, exploiting weaker bargaining position) — *s 20–22*.

**Compliance test (training):** *"appraisals must be accurate and communicated honestly… be able to prove a reasonable basis for the agent's opinions… factor in and disclose everything relevant to the potential price… update sellers if market prices change during a campaign."*

### 2.3 Best-Practice Appraisal-Report Contents (Training Ch 3.6)

A professional appraisal report typically contains: **purpose of the appraisal · method of analysis (e.g. direct comparison) · market information (trends, days-on-market) · property description · unique factors · sources of data with date ranges · comparable properties supporting the opinion · estimated sale-price RANGE · the date the appraisal is valid until + disclaimers/qualifications · special circumstances · assumptions · limitations · proposed marketing plan incl. method of sale.**

Plus process best-practice: explain the **appraisal-vs-valuation distinction**; obtain (commonly) a **written agreement to conduct the appraisal** with a third-party-data disclaimer + limitation of liability; **verify ownership/identity / conduct a title search**; ascertain reason/timeframe for selling; **disclose likely fees, commission, marketing costs**; explain **Form 6** next steps; **retain a copy of the CMA + supporting information**; **follow up**.

---

## 3. What the Mini-Site Already Does Well (Compliance Strengths)

These are genuine strengths and should be preserved — several directly satisfy obligations that most agents handle poorly.

1. **Price expressed as a RANGE, never a single headline figure** — and properties **$2.5M+** show a comparable range only (directional). Satisfies the "no single valuation in headlines" rule and reduces s 212 value-misrepresentation risk. *(ValuationTab — derived range; ConfidenceDisplay $2.5M threshold.)*
2. **Auditable, named, dated comparables with line-item adjustments and per-comp weighting** (`ValuationEvidence.tsx`, `ValuationTab.tsx`). This is the strongest possible evidence of a **"reasonable basis"** under s 212(4)–(5) / s 209(4)–(5) and the ACL.
3. **Method fully disclosed** — direct-comparison method, suburb-specific adjustment rates, 90% CI methodology, "what the model can and can't see" (`AssumptionsPanel`). Matches the Ch 3.6 contents list (method, sources, assumptions).
4. **Conditional, non-predictive language; explicit "no advice" discipline** — "the final figure depends on buyer competition and negotiation no model can predict"; FAQ footer "We do not tell sellers what to do"; `RankedComparison` labels output "a comparability estimate — our documented method, **not a valuation or a recommendation**." Aligns with editorial rules + ACL future-claims prohibition.
5. **Human-review gate / due care** — "computed automatically each night… a property consultant then reviews every comparable… before the figure becomes a recommendation"; "Under review" / "Provisional" states. Demonstrates due care (Ch 3.1: the appraisal "must be carried out with due care").
6. **"Subject to physical inspection" caveat** and a dedicated lower-confidence card for off-market homes ("we can value the bones… not the inside"). Properly limits an estimate made without an interior inspection.
7. **Conflict-of-interest transparency** — "We're an agency — and we'll say so plainly… we are not a neutral observer" (`YourAgentTab`). Directly addresses unconscionable-conduct disclosure factors and the ethics test.
8. **No-pressure posture** — "Decide / walk away / keep the report regardless", no hard CTA. Avoids the scare-tactics/coercion conduct the training flags as unethical and s 211/s 208 as unlawful.
9. **Citation / Source Layer** — ~28 peer-reviewed papers, most with working URLs (22 mirrored on-site). Supports the factual-accuracy obligation and the "prove a reasonable basis" standard for the editorial claims.
10. **Privacy & consent** — private link, not indexed, marketing-consent checkbox at capture; "entering your address did not sign you up for anything."
11. **Marketing plan + method of sale present** — `ProcessTab` walks timing, preparation, auction-vs-private-treaty, marketing strategy, listing price. Satisfies the Ch 3.6 "proposed marketing plan including method of sale" item.

---

## 4. Deficits & Recommendations — High Severity

> **STATUS — IMPLEMENTED 2026-06-21.** Built `statutory_cma.py` (suburb-first ≥3 sold / 6 mo / 5 km / similar; 5 km cross-suburb ring only rescues thin suburbs; s 215 written-explanation fallback otherwise). Display + light support only — does not re-base the engine math. Surfaced via `StatutoryCMA` on the Valuation tab with the mandatory "as at / valid until" stamp (addresses item E for the appraisal). Data analysis confirmed core suburbs get 100% coverage (35–62 comps, ring never needed) and the ring lifts thin-suburb coverage 72%→98%. All 18 live reports backfilled + verified live. See fix-history 2026-06-21.

### A. Comparable cohort does not meet the statutory CMA definition (6 months / 5 km / ≥3 sales)
**Obligation:** PO Act **s 215** + Sch 2 CMA definition (≥3 properties **sold within the previous 6 months**, similar standard/condition, **within 5 km**).
**Finding:** The valuation layer selects from an **18-month** (ValuationTab/AssumptionsPanel) to **24-month** (`homeFixture` `soldCohortWindow: "Last 24 months"`, methodNotes "46-sale cohort over the last 24 months") sold cohort, weighted toward recency. There is **no enforced rule** in the resolver (`property-report.mjs`) that the report contains at least three sales within 6 months and 5 km. A 24-month window can produce a perfectly good *estimate* while still **failing the statutory CMA test** if fewer than three qualifying recent/near sales are surfaced.
**Why it matters:** s 215 is the operative obligation triggered the moment a seller asks for a price. The defensible positions are (i) deliver a **CMA that satisfies Sch 2**, or (ii) deliver the s 215 **"written explanation showing how the agent decided the market value."**
**Severity:** **High (statutory).**
**Recommendation:**
1. Ensure the comp engine **always surfaces, and the report explicitly flags, at least 3 comparable sales within the previous 6 months and within 5 km** (similar standard/condition). Where the wider 18–24 month set is used for the model, present the **statutory-compliant subset separately and prominently** ("CMA — sales within the last 6 months and 5 km").
2. Where 3 qualifying recent sales genuinely don't exist (thin markets, unusual property), the report should **explicitly adopt the s 215 alternative** — a clearly-labelled "written explanation of how market value was decided" — rather than implying a CMA it doesn't meet.
3. Add a short on-report line citing the standard: *"This comparative market analysis includes at least three comparable sales from the past six months within five kilometres, as required under the Property Occupations Act 2014 (Qld)."* (Only when true.)

### B. Comparative superiority claim against a named competitor (Domain)
**Obligation:** ACL s 18/s 29 (misleading conduct; misleading competitor comparisons; "best/only" claims without proof); PO Act s 212(4)–(5) reverse onus.
**Finding:** The Valuation tab renders a backtest footer: *"{mae}% mean absolute error… Domain's equivalent on the same market: {domainMae}%. **Fields publishes its accuracy. Domain does not.**"* (fixture values 11.4% vs 15.0%). methodNotes adds "Backtested continuously against 1,683 Domain valuations." `ValuationEvidence` states the working range is "± a margin calibrated against 1,683 Domain valuations."
**Why it matters — two compounding problems:**
1. It is a **comparative/superiority claim against a named competitor**, which the training expressly lists as an ACL breach example ("ads that compare your achievements with those of competitors in a misleading way"; "claims that you are the 'best'… if there is no proof"). Under s 212(4)–(5) the **onus is on Fields to prove reasonable grounds** for the claim, current and suburb-specific.
2. **It contradicts our own internal finding.** Per the internal valuation-backtest constraints (memory: *valuation_backtest_claim_constraints*): *"Domain beats us in Robina + Burleigh Waters; 90% CI captures only 52%. NEVER claim 'more accurate than Domain' or quote the CI publicly."* A public claim of superiority while internal data shows the opposite in core suburbs is **misleading and indefensible.**
**Severity:** **High.**
**Recommendation:**
1. **Remove the head-to-head MAE comparison and the "Domain does not" line** from the public report. Publishing *Fields' own* accuracy is good practice and can stay; **comparing it favourably to Domain should not** until/unless a current, suburb-specific, statistically sound dataset supports it (which internal data currently contradicts for core suburbs).
2. Do **not** quote the confidence interval publicly (per internal constraint).
3. If any accuracy figure is retained, state the dataset, date, suburb scope, and limitations beside it.

### C. The document is labelled a "valuation"; the appraisal-vs-valuation distinction is never explained
**Obligation:** Training Ch 3.1 ("know the difference and be able to explain the distinctions to potential clients"); ACL s 18/s 29 + PO Act s 212 (misleading as to the *nature* of the service).
**Finding:** The word **"valuation"** is used pervasively (tab title "Valuation", "your home's price", "reconciled valuation", "the person reviewing your valuation"). A **formal valuation** is a distinct, regulated product produced by a **licensed/registered valuer** in writing to industry standards; an **appraisal** is an agent's estimate of likely selling price, not legally binding. Nowhere does the report explain that what the seller is reading is an **appraisal/estimate, not a sworn/formal valuation**. The terms "appraisal", "valuation" and "report" are used interchangeably across the codebase with no single defined term. The site does say elsewhere that "premium properties require a bespoke appraisal from a licensed valuer" (HowToValuePage) — but that nuance is not on the report.
**Why it matters:** A consumer could reasonably believe they hold a formal valuation usable for finance, probate, insurance, or legal purposes. That misimpression is the classic misleading-conduct risk.
**Severity:** **High.**
**Recommendation:**
1. Add a clear, prominent statement on the report (header note or top of Valuation tab + footer): *"This is a market **appraisal** — an estimate of likely selling price based on comparable sales. It is **not a formal or sworn valuation** by a registered valuer and must not be relied upon for mortgage, finance, probate, insurance, or legal purposes."*
2. **Standardise terminology.** Decide on "appraisal" as the public noun for the document; keep "valuation" only for the internal methodology where accurate. Update tab labels/headings accordingly.

---

## 5. Deficits & Recommendations — Medium Severity

### D. No appraisal-specific disclaimer / qualifications on the report itself
**Obligation:** Best practice Ch 3.6 ("disclaimers or qualifications on the data… any limitations on the appraisal"); ACL omission risk.
**Finding:** The only disclaimer is the **generic `/disclaimer` page** (last updated 27/02/2026, written "for article footers"), reachable via one footer link. It speaks to "articles and market reports", not to this appraisal. The report footer ("every comparable is named, every adjustment auditable") carries **no limitation-of-liability, third-party-data, or reliance disclaimer** on the document.
**Severity:** Medium.
**Recommendation:** Embed an **appraisal-specific disclaimer block** in the mini-site footer (and/or end of Valuation tab) covering: estimate-not-valuation (see C); reliance limitations; **accuracy of third-party data** (Domain/CoreLogic/government datasets — already named on the generic page); **limitation of liability** to the extent permitted by law; **market-movement caveat**; and the **assumptions** the estimate rests on (clear title, no undisclosed defects, accuracy of owner-supplied facts). Keep the dedicated `/disclaimer` link as well, but do not rely on it alone.

### E. No "valid until" / currency date on the appraisal
**Obligation:** Best practice Ch 3.6 ("the date the appraisal is valid until"); supports the ACL "figures may not reflect current market" caveat.
**Finding:** The header shows a **"Private Report · {address} · {reportDate}"** but there is **no `validUntil`/expiry field** anywhere in the fixture or resolver. A price estimate with no stated currency window can be relied on long after the market has moved.
**Severity:** Medium.
**Recommendation:** Add an explicit validity statement, e.g. *"This appraisal reflects market conditions **as at {reportDate}** and should be reviewed after **90 days** or upon a material market change."* Store a `validUntil` (or derive `reportDate + N days`) and render it in the header/footer and Valuation tab.

### F. No licensee / agent identification on the report
**Obligation:** PO Act marketing requirements (ss 209/215 per training table — features and identity correctly stated, checked by the licensee); best practice + transparency.
**Finding:** The agency licence (**Licence No. 4832971**) appears on the About, Disclaimer and Editorial-Policy pages but **not on the mini-site/appraisal**. The report identifies "Fields Estate" and "Will Simpson" by name but **does not state the licensed entity, its QLD real-estate licence number, or that the appraising person is a licensed agent.**
**Severity:** Medium.
**Recommendation:** Add to the report header or footer: **legal entity name + "Licensed Real Estate Agent (QLD) — Licence No. 4832971" + contact**. (`ReportFooter.tsx` is the natural home.) This also reinforces the s 215 framing that the price representation comes from a licensed agent.

### G. Modelled buyer "shares" and campaign "reach" presented as hard figures
**Obligation:** ACL s 18/s 29 (misleading re services / potential); future-claims-without-evidence prohibition; internal honesty constraints.
**Finding:** The Buyers/"Right Buyer" tab shows catchment **`loc.share`** values and **campaign-math reach stat-blocks** ("the reach we'd build"). A disclaimer is present and good — *"A targeting strategy, not a measured buyer register"* — but hard percentages and reach counts still read as measured facts. Internal memory (*minisite_buyer_reach_honesty*, *predictive_buyer_moat*) is explicit: the propensity/move-up models ("Track B") are **not built**, so **origin %s and letterbox counts must not be cited** as figures yet.
**Severity:** Medium.
**Recommendation:** Replace hard `share` percentages and absolute reach counts with **qualitative bands** or clearly-labelled **"modelled estimate"** language; ensure no figure implies measured or guaranteed reach. Keep the existing "targeting strategy, not a measured register" line and apply the same treatment to the campaign-math block. Avoid any phrasing that edges toward "potential capital gain / guaranteed buyers."

### H. Material-facts / known-issues disclosure not surfaced
**Obligation:** ACL (omitting material facts affecting saleability/amenity/value is misleading conduct); training "take reasonable steps to find out and verify any facts material to the sale."
**Finding:** The vision passes note "visible trade-offs" and "detractants", but there is **no structured material-facts section** — flood overlay status, easements/encumbrances, zoning, building/pool-safety approvals. For **Burleigh Waters**, *"Does Burleigh Waters flood?"* is the #1 search query; the appraisal does not address it, and the estimate implicitly assumes no such issues.
**Severity:** Medium.
**Recommendation:** Add a **material-facts / assumptions** section: title & encumbrance status (from title search), **flood-overlay status with a FloodWise-report pointer** (following the existing Burleigh flood editorial rules — never "underwater", never "never flooded"), and zoning. State explicitly that the estimate **assumes clear title and no undisclosed defects**, and will be revisited if material facts emerge.

### I. Ownership/authority not acknowledged; "prepared for" is generic
**Obligation:** Training — confirm true ownership (title search), verify identity, (commonly) obtain written agreement to conduct the appraisal.
**Finding:** The flow captures a **generic marketing-consent checkbox** ("send me my home analysis and occasional insights"), not an acknowledgement that the requester is the **owner or authorised**. The report states *"Prepared for the owner of {address}"* without that being verified — anyone can enter any address.
**Severity:** Medium (best practice / anti-fraud; legal exposure is lower pre-appointment).
**Recommendation:** At address entry, add an **ownership/authority acknowledgement** ("I am the owner of, or authorised to request an appraisal for, this property") and a short terms note (estimate-not-valuation + third-party-data disclaimer — doubles as the Ch 3.4 "written agreement to conduct the appraisal"). Verify ownership at/before the consultant stage; retain the record.

### J. Fees, commission and marketing costs not disclosed; Form 6 not referenced
**Obligation:** Training Ch 3.7 — disclose likely costs, fees, commission, marketing budget; explain the **Form 6** appointment.
**Finding:** The FAQ "cost of sale" touches selling costs generically, but there is **no Fields-specific indicative fee/commission/marketing-cost** content, and **no mention of the Form 6** appointment as the formal next step. `NextTab` deliberately ends at "Decide" with "no fourth step" — a reasonable conversion choice, but it omits the regulatory reality that any engagement requires a Form 6.
**Severity:** Medium → Low (the appointment/fee conversation legitimately belongs to the human stage; this is completeness, not breach).
**Recommendation:** Add an indicative **"What it costs to sell with Fields"** note (or clearly state fees/commission/marketing are set out at the review), and a one-line factual reference that a formal engagement is made via a **Property Occupations Form 6**. This sets honest expectations and pre-empts any "hidden cost" perception (an ACL example: "promoting a flat fee if extra charges may apply").

---

## 6. Deficits & Recommendations — Low Severity / Polish

### K. Record-keeping & reproducibility of the CMA
**Obligation:** Training Ch 3.7 — "retain a copy of the CMA provided along with any supporting information."
**Finding:** Reports are stored in `property_reports`, but the live comp/market layers re-derive from nightly data. If the exact comps/figures shown to a seller on a given date aren't **snapshotted**, the report can't be reproduced "as at" its date if later questioned.
**Recommendation:** Confirm a retention policy that **snapshots the served CMA** (comps, adjustments, figure, sources, date) per report version, so any past appraisal is reproducible. Aligns with s 212(5) onus-of-proof readiness.

### L. Agent-credential claims must be substantiable
**Obligation:** ACL s 29; training (don't exaggerate experience/skills/expertise).
**Finding:** `YourAgentTab` states Will's "background in financial analysis and fund management" and "negotiation training." Low risk **if accurate and evidenced**.
**Recommendation:** Keep documentary evidence for each credential claim; avoid superlatives. (No change needed if all claims are true and supportable.)

### M. "Tax" FAQ framing
**Obligation:** PO Act s 209(2)(b)(x)/s 212(2)(d) specifically list "how the purchase may affect income taxation" as a false-representation risk area; ACL.
**Finding:** A "tax" FAQ exists; the generic disclaimer covers "not financial/legal advice", but the report has no local caveat.
**Recommendation:** Keep tax content general and conditional, cite the ATO, and add "general information, not tax advice — consult your accountant."

### N. Confirm onward marketing copy is licensee-checked
**Obligation:** PO Act ss 209/215 (training table) — advertising must correctly state features and price instructions and be checked by the Principal/Licensee.
**Finding:** The positioning/vocabulary/sample-listing content is well-disciplined ("anchored to a verifiable fact"), but it becomes **listing advertising** downstream.
**Recommendation:** Ensure the documented editorial fact-check/sign-off gate is treated as the **licensee check** of record before any of this copy reaches a portal, and that price representations match the client's written instructions.

---

## 7. Prioritised Action List

| Priority | Item | Action | Owner area |
|----------|------|--------|-----------|
| **P1** | **B** | Remove Domain superiority comparison + "Domain does not" line; don't quote CI publicly | ValuationTab / fixture |
| **P1** | **C** | Add "appraisal, not a formal valuation" statement; standardise terminology | ValuationTab / ReportHeader / global |
| **P1** | **A** | Surface a Sch 2-compliant CMA subset (≥3 sold / 6 mo / 5 km) or adopt the s 215 "written explanation" framing explicitly | comp engine + ValuationTab |
| **P2** | **D** | Embed appraisal-specific disclaimer block on the report | ReportFooter |
| **P2** | **E** | Add "valid until / as at" currency date | ReportHeader/Footer + fixture |
| **P2** | **F** | Add licensee entity + Licence No. 4832971 to the report | ReportFooter |
| **P2** | **G** | Convert modelled buyer shares/reach to qualitative/"modelled" language | BuyersTab |
| **P3** | **H** | Add material-facts/assumptions section (flood, title, zoning) | YourHomeTab / new section |
| **P3** | **I** | Ownership/authority acknowledgement + terms at address entry | capture flow |
| **P3** | **J** | Indicative fees/commission + Form 6 reference | NextTab / ProcessTab |
| **P4** | **K–N** | Snapshot retention; credential evidence; tax caveat; licensee sign-off of marketing copy | backend / content ops |

---

## 8. One-Page Compliance Checklist (for the report template)

A legally-complete QLD appraisal document should carry **all** of the following. Current status:

- [x] Estimated **price RANGE** (not a single figure) — **present**
- [x] **Method of analysis** stated (direct comparison) — **present**
- [x] **Comparable sales** named, dated, adjusted — **present**
- [~] **CMA = ≥3 sold / last 6 months / within 5 km / similar** — **partial (18–24 mo cohort; not enforced)** → **A**
- [x] **Market information** (trends, days-on-market) — **present** (Market tab / competition)
- [x] **Property description + unique factors** — **present**
- [x] **Data sources with date ranges** — **present**
- [x] **Assumptions + what the model can't see** — **present**
- [ ] **"Appraisal, not a formal valuation" statement** — **missing** → **C**
- [ ] **Date valid until / currency date** — **missing** → **E**
- [ ] **Report-level disclaimer + limitation of liability + third-party-data** — **missing on report** → **D**
- [ ] **Material facts / known issues (flood, title, zoning)** — **missing** → **H**
- [ ] **Licensee identity + QLD licence number** — **missing on report** → **F**
- [x] **Proposed marketing plan incl. method of sale** — **present** (Process tab)
- [~] **Likely fees / commission / marketing costs** — **generic only** → **J**
- [~] **Next step / Form 6 appointment** — **conversation only, no Form 6 reference** → **J**
- [x] **No advice, no predictions, conditional language** — **present & disciplined**
- [x] **Reasonable basis demonstrable (auditable working)** — **present (strong)**
- [ ] **No misleading competitor comparison** — **fails on Domain claim** → **B**
- [~] **Ownership/identity acknowledged** — **generic consent only** → **I**

Legend: [x] met · [~] partial · [ ] missing.

---

## 9. Caveats on this Audit

- This is an **operational compliance review, not legal advice.** Before external sign-off, have a **QLD-qualified property lawyer** confirm the s 215 / Sch 2 CMA interpretation and review the disclaimer wording.
- The **CCA PDF supplied is the Schedules volume** and does not contain the operative ACL sections; the ACL points rest on the training summary + PO Act s 210's cross-reference. **Verify against the full ACL (Schedule 2) text.**
- Findings reflect the codebase and a fixture (Merrimac/Burleigh examples) as at 21 June 2026; numeric values (e.g. MAE 11.4/15.0) are example-fixture data — the **principle** (no competitor superiority claim) holds regardless of the live numbers.
