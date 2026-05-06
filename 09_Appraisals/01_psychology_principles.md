# Psychology Principles — How the Report Earns Trust

This document lists every behavioural / cognitive principle we deliberately use in the Fields Appraisal Report, the citation behind it, and the concrete design / copy decision it justifies. Every principle is paired with a "where it shows up" line so it can be enforced in editorial review.

When two principles conflict (they will), the later one in this document wins, because it is sequenced from foundational → finishing.

---

## 1. The seller mental model — what is actually going on in their head

Pulled from the Fields Customer Pain Points analysis of 5,000 Australian property forum comments (`/home/fields/knowledge-base/marketing/Customer_Pain_Points_Working_Doc_docx_*.json`), Domain/REA seller surveys, and Tom Panos / REIQ vendor research.

### 1.1 The five fears (in order of prevalence)
1. **Picking the wrong agent** — "How do I tell who is actually competent before I sign?"
2. **Leaving money on the table** — "What if I sell for less than I should have?"
3. **Being conditioned down** — "Will the agent talk me into accepting a lower price to get a quick sale?"
4. **Public embarrassment / stale listing** — "What if it sits on the market and the neighbours see?"
5. **Process opacity** — "Once I sign, I won't know what's happening or whether they're working."

### 1.2 The five desires
1. **Certainty** — to know what their home is worth, to a degree they can defend at a dinner party.
2. **Validation** — to be told their renovation, their care, their choice of suburb mattered.
3. **Control** — to feel they made every decision, not that decisions were made for them.
4. **Status / story** — "We sold our home really well" is a story they want to tell for years.
5. **A trusted human** — someone who will return their calls and tell them the truth.

### 1.3 The five unspoken needs
1. **Permission to be cautious** — they don't want to be sold to. They want to make a decision.
2. **A reason to feel smart** — reading the report should make them feel more informed, not stupider.
3. **Proof of effort** — they want to feel the agent has worked hard *for them, before being hired*.
4. **Inoculation against regret** — when (not if) something goes wrong in the process, they want to know they chose carefully.
5. **An out** — they want to know they can walk away without offending anyone.

The report is engineered to address all fifteen of these. Every page maps to one or more.

---

## 2. Foundational cognitive biases (we exploit these for the seller's benefit)

### 2.1 Loss aversion — Kahneman & Tversky, *Prospect Theory* (1979)
**Finding:** Losses loom approximately 2.25× larger than equivalent gains. A homeowner fears "leaving $50,000 on the table" more than they are excited by "achieving $50,000 above the median".

**How we use it:** Every value-equation panel quantifies *both directions* — what the trade-off costs **and** what the compensating feature recovers. We frame premium-quality marketing as preventing loss ("avoiding the $50K–$100K gap between an adequate and excellent campaign"), not as buying upside. (Source: seller book v4, `Houses Sell Themselves` opening section.)

**Where it shows up:** Honest Assessment page. Pricing strategy page (overpricing penalty section). Marketing ROI page.

### 2.2 Endowment effect — Thaler 1980; Genesove & Mayer (2001)
**Finding:** Owners systematically overvalue assets they own. Genesove & Mayer's seminal Boston condo study found loss-averse sellers list 25–35% above the rational price after a market decline and refuse to sell below their original purchase price even when it's economically irrational.

**How we use it:** We do not contradict the seller's number. We *reframe the conversation away from any number and toward the comparable evidence*. By the time we present our valuation range, the seller is anchored to comparables, not to their pre-existing belief. We name the endowment effect implicitly: "Your renovation matters to your family. The market's response to it is a separate question, and that's what we're examining here."

**Where it shows up:** The Verdict page (only ever shown after the comparables page). Sequencing rule: comparables page **must** come before any single-figure valuation.

### 2.3 Anchoring — Tversky & Kahneman (1974)
**Finding:** The first number presented in a decision-making context disproportionately influences all subsequent judgment, even when the anchor is arbitrary.

**How we use it:** The first number a seller sees in our report is **the comparable-sales range built from evidence**, not our valuation. We anchor them to the methodology before the answer. The agent who tells them their Domain estimate was right is anchoring them to fantasy. We anchor them to data.

**Where it shows up:** Page 2 (The Fields Take) headline — leads with comparable evidence, not a number. Page 3 (Valuation) — shows the three comp adjustments *before* the headline range.

### 2.4 Reference-point dependence — Genesove & Mayer (2001)
**Finding:** Sellers' reservation price tracks their reference point (purchase price, peak market estimate) far more than market reality. Down markets see sharp listing-to-sale gaps because of this.

**How we use it:** Where the comparable range is below the seller's anchor (Domain estimate or purchase price + appreciation), we explicitly **show the gap and explain it** rather than hide it. Sarah & Mark's chapter in the seller book is the template: a $150K gap, surfaced and reasoned through, kills the anchor more effectively than any rebuttal could.

**Where it shows up:** Optional "Comparison Notes" page when the seller's prior anchor diverges materially from the range.

### 2.5 Ambiguity aversion — Ellsberg (1961); Fox & Tversky (1995); Gneezy, List & Wu (2006)
**Finding:** People prefer known risks to unknown ones, and the aversion grows with stakes. In real estate, this is why 72% of buyers skip auction listings without price guides (REA Group internal data, 2014).

**How we use it twice:** First, the report itself is the antidote to ambiguity — every claim sourced, every number dated, every methodology shown. Second, we use it as evidence in the auction-vs-private-treaty section: "buyers feel the same way you do about uncertainty, and 72 of every 100 walk past."

**Where it shows up:** Methodology footnotes on every page. Auction discussion in Pricing & Strategy.

---

## 3. The credibility stack — how we earn belief in 30 seconds

A reader does not have time to verify each claim. They form a snap judgment about whether to trust the document, and read the rest under that frame. The stack:

### 3.1 Halo effect via design — Nisbett & Wilson (1977)
**Finding:** Readers' impression of one quality (visual polish) propagates to perceptions of unrelated qualities (data accuracy, expertise).

**How we use it:** Print-grade typography, deliberate restraint with colour, generous white space, FT/Monocle-quality information design. We spend disproportionately on the first three pages — they set the halo for everything else. (See `06_visual_system.md`.)

### 3.2 Specificity heuristic — Janiszewski & Uy (2008); Schindler & Yalch (2006)
**Finding:** Precise numbers are perceived as more credible than round numbers. In real estate specifically, Cardella & Seiler (2016) found precise listing prices ($1,748,500) generated higher final sale prices and smaller buyer discounts than round prices ($1.75M) across 538 transactions.

**How we use it:** Every figure in the report is precise. $1,765,000–$1,825,000, not $1.75M–$1.85M. 13,585 sales not "thousands of sales". 60+ studies, 14 academic papers — verifiable counts. *Including precise numbers in the body language of the document signals competence even when the reader doesn't pause to verify them.*

**Where it shows up:** Every numerical claim. Editorial review enforces this with a regex-style check (no rounded $X.YM in body text).

### 3.3 Authority cues — Cialdini, *Influence* (1984)
**Finding:** Six universal influence levers; authority and social proof are most relevant here. Authority is signalled by credentials, citations, and methodology rigour.

**How we use it sparingly.** We do **not** lead with credentials. The Harvard negotiation training is mentioned once in a footnote-style panel, not as a hero claim. The authority signal is delivered through the *quality of the work itself*, which is more durable than any badge. Our citations (Taylor 1999, Anglin/Rutherford/Springer 2003, Cardella & Seiler 2016) function as authority transfer.

**Where it shows up:** Methodology note in front matter. Footnotes throughout. A single "Why Fields" panel on the back.

### 3.4 Inoculation effect — McGuire (1961, 1964)
**Finding:** Pre-emptively raising weak counter-arguments makes the audience more resistant to those arguments when an opponent later presents them. The classic vaccination metaphor.

**How we use it everywhere.** Every property weakness is raised by us first, then reframed. Every limit of our methodology is acknowledged. ("This valuation assumes the property analyst's inspection confirms the condition score we have estimated remotely.") When a competing agent later says "their valuation is conservative because they didn't see inside" — the seller has already considered that and has our framing.

**Where it shows up:** Honest Assessment page (the entire raison d'être). Trade-off panels. Methodology footnotes. Limits-of-our-evidence box.

### 3.5 Vulnerability disclosure — Brown (2012, *Daring Greatly*); Aronson, Willerman & Floyd (1966) "Pratfall Effect"
**Finding:** Competent people who admit a small mistake or limitation are perceived as more, not less, competent than those who project flawlessness. Will's "Vulnerable" chapter in the seller book is a textbook application.

**How we use it:** A short signed note from Will at the front of the report — one paragraph — describing a property he has gotten wrong, or what we have not yet been able to model. It costs us nothing in credibility (because the rest of the document is so strong) and earns us trust the way a thousand awards never could.

**Where it shows up:** Inside front cover, "A Note Before You Read" — 80–120 words.

### 3.6 Source disclosure — academic norm; FT / Economist editorial standard
**Finding:** Citing your sources is the strongest form of authority signal because it allows the reader to verify *if they want to*. Most never will. The signal is in the offer.

**How we use it:** Every chart has a Source line. Every claim has a footnote-style citation. Methodology is summarised on a dedicated page at the back. We treat the seller as we would treat a *Financial Times* reader.

**Where it shows up:** Every page. Methodology Appendix.

---

## 4. Narrative + emotional engineering

### 4.1 Narrative transportation — Green & Brock (2000)
**Finding:** Readers absorbed in a story are more persuaded than those consuming the same facts in expository form. Fictional vignettes with concrete protagonists shift attitudes and reduce counter-arguing.

**How we use it:** The lifestyle narrative (Saturday morning at the pool, Sunday minus a renovation to-do list) on the pricing page is doing actual persuasion work. We extend this by adding a one-paragraph "A morning in this home" sequence to the buyer-profiles page — a transport device for the seller, who imagines a buyer feeling exactly what the seller felt when they first walked in.

**Where it shows up:** Pricing & Strategy page. Buyer-Profiles page. (Optional) Photography brief page.

### 4.2 Peak-end rule — Kahneman, Fredrickson, Schreiber & Redelmeier (1993)
**Finding:** People judge an experience largely by its peak (best or worst point) and its end, not by sum or average.

**How we use it twice:** First, in our open-home strategy ("every inspection ends at the pool"). Second, in the report itself: the cover and the last page disproportionately determine the seller's overall judgment of the document. We over-invest in both. The very last thing the reader sees should be a moment of warmth, not a logo.

**Where it shows up:** Cover. Last page (a personal sign-off from Will, hand-lettered or scripted, naming the property).

### 4.3 Curiosity / information gap — Loewenstein (1994)
**Finding:** Curiosity arises from the perceived gap between what one knows and what one wants to know. The gap must be sized correctly — too small, no interest; too large, give-up.

**How we use it:** Section openers tease a question and answer it three paragraphs later. Headlines are gap-creating, not summarising. ("Why your most valuable feature is the one you almost didn't include" outperforms "Pool adds value" every time.)

**Where it shows up:** Section heads. Page-2 headline structure.

### 4.4 Specificity in the lifestyle layer
A generic "perfect for entertaining" sentence does no work. A specific Saturday morning with the kids in the pool and the kettle on the deck *transports*. The lifestyle narrative on Dee's report ("Saturday morning starts at the pool…") was the most-quoted passage in her engagement and is the model.

---

## 5. The decision architecture

### 5.1 Choice supportive bias — Mather, Shafir & Johnson (2000)
**Finding:** Once a decision is made, people remember the chosen option more positively than the rejected ones, regardless of objective quality.

**How we use it:** Make Fields the *easy* decision but make it feel like *theirs*. The report ends with three options ("review, conversation, decide") that the seller selects. The framing is one of agency, not closure.

**Where it shows up:** Next Steps page.

### 5.2 Reactance — Brehm (1966)
**Finding:** Direct attempts to control behaviour produce a reaction in the opposite direction. Telling someone "you should hire us" reliably reduces the probability they will.

**How we use it:** The report does not ask for the listing. Not once. The closing message is "If you'd like to explore selling with Fields, we'd build a tailored campaign. If not, this report is yours to keep." The latter half of that sentence is what makes the first half persuasive.

**Where it shows up:** Next Steps page. Final sign-off.

### 5.3 The Ben Franklin effect — Jecker & Landy (1969)
**Finding:** People come to like those they have done a small favour for. Asking the seller to do something *for us* (e.g., correcting a detail about their property in the report) builds reciprocity.

**How we use it:** A "What we got wrong" feedback panel inside the digital report — "If anything in here doesn't match your knowledge of the property, tell us so we can update it." This is a tiny ask, and accepting it makes the seller invested in our accuracy.

**Where it shows up:** Microsite + a tipped-in card in the print edition.

### 5.4 Commitment & consistency — Cialdini (1984)
**Finding:** Once people make a small commitment, they are more likely to make a larger consistent commitment.

**How we use it:** The address-submission moment on `analyse-your-home` is the first commitment. The report extends consistency by inviting micro-engagements (correcting a fact, watching the embedded video, returning to the microsite as new comparables arrive). By the time the listing conversation happens, multiple consistent commitments have stacked.

**Where it shows up:** Microsite design. Update emails. The full appraisal-poller cadence.

### 5.5 Default-effect — Thaler & Sunstein, *Nudge* (2008)
**Finding:** People disproportionately stick with defaults.

**How we use it:** The report's recommended next step is *a conversation*, not a signed listing agreement. The listing agreement is downstream, optional, and never the default ask. Making the immediate next step low-cost dramatically increases the probability of taking it.

**Where it shows up:** Next Steps page (three-step ladder: review → conversation → decide).

---

## 6. The trust-transfer moments

A homeowner's trust in Fields builds in discrete, identifiable moments. We name them so we can engineer for them:

| Moment | What earns trust here | Risk if mishandled |
|---|---|---|
| First page-flip (5 sec) | Visual polish, halo effect | "Looks like a brochure" → discounted as marketing |
| First number seen | Comparable-derived range, not a guess | Anchoring to a wrong number |
| First weakness named | Inoculation, vulnerability | Looks evasive if weaknesses hidden |
| First specific street/school named | Local mastery proof | Generic = "they could be anywhere" |
| First citation observed | Authority transfer | Empty page = vibes, not analysis |
| Trade-off reframe | Inoculation pays off | Reads as denial if reframe is weak |
| Last page (peak-end) | Personal sign-off, low-pressure CTA | Pushy close = retroactively colours everything |

These moments are auditable. Each has a checklist item in the editorial review.

---

## 7. The mistakes we will NOT make (and the principles that name them)

- **Persuasion-fatigue.** Every page that "sells" weakens every page that informs. Selling is concentrated to <10% of the report; the rest is data-as-persuasion. (Cialdini reactance.)
- **The fluency illusion.** Easy-to-read, well-designed content feels true even when it isn't. (Reber & Schwarz 1999.) We mitigate by making citations frictional — they require the reader to acknowledge the source even subliminally.
- **The single-figure trap.** Every single number is wrong. Every range is recoverable. We never publish a single-figure headline valuation. (Jensen-Shannon framing; FT Chart Doctor.)
- **The feature-bait swap.** Replacing comparables with photography would lose the analytical reader. Replacing prose with bullets would lose the deep reader. The report serves all three readers because it never substitutes one for another.

---

## 8. Citation quick-reference

For copy/editorial use. Pin this list in the writers' workspace.

| Field | Citation | Used for |
|---|---|---|
| Loss aversion (2.25× ratio) | Kahneman & Tversky 1979, *Econometrica* | Marketing-ROI framing |
| Endowment + reference dependence | Genesove & Mayer 2001, *Quarterly Journal of Economics* | Price-anchor handling |
| Anchoring | Tversky & Kahneman 1974, *Science* | Page-sequencing |
| Ambiguity aversion | Ellsberg 1961; Fox & Tversky 1995; Gneezy/List/Wu 2006 | Auction discussion |
| Halo effect | Nisbett & Wilson 1977, *J. Personality & Social Psych.* | Design investment |
| Specificity → credibility | Janiszewski & Uy 2008, *Psychological Science* | Number formatting |
| Precise pricing in real estate | Cardella & Seiler 2016, *J. Behavioral Finance* | List-price strategy |
| Inoculation | McGuire 1961, *Sociometry* | Honest-assessment page |
| Pratfall / vulnerability | Aronson, Willerman & Floyd 1966 | Will's note |
| Narrative transportation | Green & Brock 2000, *J. Personality & Social Psych.* | Lifestyle narrative |
| Peak-end | Kahneman et al. 1993; Redelmeier & Kahneman 1996 | Open-home + cover/back |
| Curiosity gap | Loewenstein 1994, *Psychological Bulletin* | Headlines |
| Reactance | Brehm 1966 | Soft CTA |
| Ben Franklin effect | Jecker & Landy 1969 | Feedback prompt |
| Commitment / consistency | Cialdini 1984 | Microsite engagement loop |
| Defaults / nudging | Thaler & Sunstein 2008 | Next-Steps ladder |
| Overpricing penalty | Taylor 1999; Anglin/Rutherford/Springer 2003; Knight 2002; Zillow 2019 (n=25,000) | Pricing discussion |
| Auction vs private treaty | Frino, Peat & Wright 2012 (n=1.2M); REA Group 2014 | Method-of-sale discussion |
| Range pricing → wider buyer pool | Nikiforou et al. 2022 (n=538) | Listing-range justification |

---

*Owner: Will Simpson. Updated 2026-05-06. Reading order: read after `00_strategy.md`, before `02_report_blueprint.md`.*
