# What the shipped mini-site holds that the V4 flow should take

**Compiled:** 2026-08-06. **Source:** `/your-home/<slug>` — the report that loads after an
address is submitted at `/analyse-your-home`. Code: `01_Website/src/pages/YourHomePage/`.
**For:** `05_PAGE_FLOW.md`.

This is a **shipped, working product** covering much of the same ground as our flow. Several
components solve problems `05_PAGE_FLOW.md` currently lists as open. Reuse, don't rebuild.

---

## 1. `SoWhat` — the rule that most improves our copy

> *"The consultant's core diagnosis: the product is data-first when the seller is fear-first.
> Every number, chart, table or comparison must answer 'why should a seller care?' in plain
> language. This is that line."*
>
> **Product rule: no stat tile, comp count, scarcity figure or competitor number ships without
> a paired `<SoWhat>`.** One or two sentences — *"the translation of evidence into
> risk-reduction, not a second paragraph."*

**Our draft copy fails this test repeatedly.** §4 hands the reader $469,000, 77%, 73.6% and
73.4% in a single block with no translation. §7 gives medians and days-on-market unattached to
meaning.

**Adopt the rule wholesale, and the component with it.** It also stays inside our editorial
constraints by design: *"Describe what the data means; never instruct."*

## 2. `FearSection` — Will's two-column pattern, already built, with a better split

```
HEADLINE  ─── fear restated in the seller's own words
SUBHEAD   ─── reframe in one sentence, with a number
┌──────────────────────────┬──────────────────────────┐
│ THESIS                   │ APPLIED TO YOUR HOME     │
│ the general finding      │ the same data, anchored  │
│ + chart                  │ to this property         │
└──────────────────────────┴──────────────────────────┘
CITATION STRIP
```

*"The pattern matches the V4 print system's six spreads — left page thesis, right page
applied."*

**This is the two-column idea, shipped — but split thesis/applied rather than free/locked.**
That is the better axis. The right-hand column becomes *more* personal as you move across, not
less accessible, so the page reads as deepening rather than withholding. It maps exactly onto
our §4: the 512-home dispersion finding is the thesis; their eight comparables are the applied.

**Recommendation: adopt thesis/applied as the primary column split, and let the ask sit
underneath rather than occupying the right column.**

## 3. `PositionAtAGlance` — a shipped opener answering four questions in five seconds

> *"A seller must feel the product is useful within five seconds. Replace the data-heavy opener
> with four cards that answer the four questions every seller actually wakes up with:"*
>
> 1. What is my home likely worth?
> 2. How many homes truly compete with mine?
> 3. Who is most likely to pay the top of the range?
> 4. What decisions could change my result?

Directly comparable to our §0/§1, and it has the five-second constraint already designed in —
which matches our measured 2-second time-to-first-scroll better than our current opener does.

> ⚠ Note honestly: questions 2 and 3 are the competition and buyer angles that our independent
> evidence audit found **no** support for. They are here as a Fields product decision, and
> GPT's reasoning agrees — but that is not the same as user evidence. Adopting the four-card
> shape does not import evidence for questions 2 and 3.

## 4. `ValuationEvidence` — our §2, already built, in three layers

> **L1 Evidence card** — strength badge, range bar, how many sales it's built from, how tightly
> they agree (CV), rate provenance.
> **L2 Comparable cards** — each included sale: SOLD → ADJUSTED, distance, recency, weight %,
> verified flag, plain-English adjustment narrative.
> **L3 Adjustment grid** — per comp, feature-by-feature.

Rendered *"from the engine's own output (no recomputation)"*.

**This is §2 of our flow, shipped.** It already carries the distance-per-comparable that L3 of
our limitations demands, and a plain-English narrative per adjustment.

> ⚠ Worth checking: our §2 is marked blocked because `adjusted_price` isn't persisted. This
> component renders adjusted prices today for `/your-home`, so the blocker may be specific to
> the off-market path rather than universal. **Verify before treating it as a blocker.**

## 5. `RankedComparison` — "honest theatre" we should steal for §2

> A **funnel** reconciling `active_total → in_band → ranked → close_tier`, *"animated on open so
> the seller watches the filtering happen. **Honest theatre: every step is a computation the
> matcher genuinely ran.**"*

Our §2 states "we looked at 32 sales and kept 8" as a flat line. **Showing the filtering happen
is far stronger than reporting its output** — and the phrase *honest theatre* is the right
standard: theatre is fine where every frame is a real computation.

## 6. `CitationStrip` + `DataRecordDrawer` — the traceability layer

**`CitationStrip`:** *"It is the trust mechanism: **if a claim doesn't have a source, the block
should not have rendered.**"* Adopt as a rule.

**`DataRecordDrawer`:** a slide-in panel listing *"every data point Fields holds on a home,
grouped and sourced… every group prints its source so each row stays auditable (mini-site
principle: every claim names its source)."*

That drawer is a strong answer to *"what do you actually know about my house"* and it is
already built. It also pairs naturally with our §9 correction ask — you can only correct what
you can see.

## 7. ⚠ `StatutoryCMA` — a compliance question our flow has not answered

> *"Property Occupations Act 2014 (Qld) s 215 + Sch 2: when a seller asks an agent for a likely
> sale price, the agent must provide a CMA comparing the home with at least 3 properties SOLD
> within the previous 6 months, of similar standard, within 5 km — or, if a CMA can't be
> prepared, a written explanation of how market value was decided."*

**Our §1 gives a homeowner a likely sale price for their home, and Fields is a licensed
agency.** Whether that triggers s 215 is a real question and the mini-site has already built
the answer: a CMA of record with an *"as at / valid until"* stamp, and an s 215 written-
explanation notice when a compliant CMA can't be prepared — *"it never implies a CMA we don't
actually meet."*

**Do not ship §1 without resolving this.** It also independently reinforces our decision to
date the estimate: the six-month window makes the stamp mandatory.

## 8. `WhatChangedBanner` — GPT's missing layer, already built

> *"First visit: frames the curated starting view. Return visit: summarises the deltas since
> the seller's previous login — new listings, price changes, selling-method changes, sales —
> with an honest sub-line when the comparative aperture had to be widened to surface activity."*

This is *"what has changed since I last checked"*, which GPT calls the major opportunity and
which I scoped as a post-claim feature. **It exists.** The honest-widening sub-line is a nice
touch: it admits when we had to look further afield to find anything to report.

## 8b. Scarcity — built in both products, and I judged it by the wrong test

### ⚠ A correction

My earlier audit put "who would buy this home / what competes" on the no-independent-support
list because it is absent from the autocomplete categories, the stored persistence, Google's
refinements and the Reddit personas. **That test was wrong for scarcity.**

Scarcity is not a *topic users search for*. It is an **explanation we supply** — nobody googles
*"how rare is my house"*, just as nobody googles *"the reasoning behind my valuation"*. Judging
it by search demand is the same mistake as judging our working by search demand.

The right test is whether it serves a **needed job**, and it plainly does: **J1 — "six numbers
and no way to choose"** — whose unmet need is *a defensible reason to prefer one figure*.
*"Only 6 of 198 active listings match your combination"* is exactly such a reason. **Scarcity
belongs inside §2 as part of the working, not as a standalone "who would buy" section.**

That verdict is unchanged for *buyer profiling* as a topic in its own right — which is what the
`buyer` card actually is. Scarcity and buyer-profiling were being treated as one thing; they
aren't.

### What is already built

**`scripts/property_reports/scarcity_features.py`** — the production engine, rewritten
2026-06-07. Its design premise is the interesting part:

> *"The value of a home is rarely one rare feature — it is a **COMBINATION** of mostly-common
> features that together suit one buyer."*

- **Anchors** — the mainstream, big-ticket features buyers screen on (land, floor area, pool, beds), chosen **relative to the suburb cohort, not a fixed bar**: *"an 813 m² block can be an anchor in a suburb whose median is 600 m² even though it never clears a fixed 900 m²+ line."*
- **Differentiators** — single-level living, premium finish, walk-to-school — **deliberately not counted**, they only add prose colour.
- The load-bearing number is `active_matching_full_stack`, matched on anchors only.
- ⚠ The honesty guarantee, built into the engine: *"We do NOT fold sparse-coverage features into the count, **so the ratio can never be inflated by missing data**."*
- Reads the **same** `valuation_data.subject_property.features.basic` that drives the valuation — so scarcity and the range cannot drift apart.

**In the shipped mini-site** (`MarketTab`): *"What makes your home rare — measured"*, a headline
scarcity claim, the combinatorial query result, and `soldCohortPremiums` — **each feature priced
against the suburb's last-24-month sold cohort**. Plus the standard it sets for itself:

> *"Scarcity, when it is real, is the single most reliable lever in property marketing. Most
> agencies describe it."* … *"Always visible — the scarcity claim is only persuasive if it's
> defensible."*

**In the off-market build:** `offmarket_intel.scarcity` (`active_total`, `active_matching`,
`notable`, `query`), plus `Page_Redesign_V2/poi_rarity.py` — a prototype for **conditional
rarity**:

> *"6 share your combination — only 2 are also within a 5-minute walk of a park."*

That is the best intrigue device in either product. It narrows honestly, in one sentence, and
it converts a common physical combination into a genuinely rarer one without overstating
anything. Still a standalone harness — *"promotion into the production engine is a separate,
deliberate step."*

### How it should sit in our flow

Inside **§2, as the reason the range sits where it does** — the bridge between the comparables
and the figure. It pairs naturally with `soldCohortPremiums`, which gives the dollar value of
each anchor feature, and with A10 (we already price renovation and condition in dollars).

> ⚠ **The scaling constraint.** In the mini-site, scarcity is gated behind `slotStatus` and a
> `ConsultantBadge` — a human approves it before it renders. That does not scale to 26,297
> off-market pages. Either the unapproved state is designed honestly, or the claim is written so
> it never needs approval.

---

## 9. Smaller pieces worth reusing

| Component | What it gives us |
|---|---|
| `PendingPlaceholder` | A designed wait state with an ETA line. Ours needs one for the 30–90s build — different duration, same pattern |
| `MatchCards` | Carries an explicit `differenceVsSubject` line, *"frames the row as COMPARISON, not as a list of alternatives"* |
| `SeasonalityStrip` | *"This is a pattern, never a prediction."* Same register §7 needs |
| `SummaryStrip`, `StatusBadge`, `TabHero` | Layout primitives already consistent with the house style |

---

## 10. From the V2 session spec (not shipped, but specified)

Covered in more detail in the previous revision of this file; the four that matter most:

1. **"The three questions" opening** — *"You may be trying to answer three questions privately."* Names what they came for without making them admit intent. Better than our §0. The hedge *"You may be"* is load-bearing and may not be strengthened.
2. **"Two true things that point in different directions"** — show the ambiguity rather than announcing we won't resolve it. Better than our §7.
3. **Suppression as a credential** — *"saying why a number is missing is worth more than the number… Every competitor draws the line anyway. Refusing to is a credential."* **This reframes our no-range fallback from apology to proof.**
4. ⚠ **`offmarket-intent-alert.mjs` already alerts Will when a visitor reaches the end of a deck having asked for nothing.** *"The alert does not break this promise; acting on it would."* "Nobody calls unless you ask" appears twice in our copy and cannot ship until that rule is ratified.

---

## Actions for `05_PAGE_FLOW.md`

1. **Adopt the `SoWhat` rule** — every number gets a translation line. Our §4 and §7 currently fail it.
2. **Switch the column split to thesis / applied-to-your-home**, with the ask beneath rather than in the right column.
3. **Replace §2's flat "32 assessed, 8 kept" with the animated funnel** from `RankedComparison`.
4. **Adopt `CitationStrip`'s rule:** if a claim has no source, the block doesn't render.
5. **Resolve the s 215 CMA question before §1 ships.**
6. **Reuse `ValuationEvidence` for §2** — and verify whether the `adjusted_price` blocker is really universal.
7. **Reuse `WhatChangedBanner`** as the post-claim returning-visitor layer.
8. **Reuse `DataRecordDrawer`** as the companion to the §9 correction ask.
9. **Fold scarcity into §2** as the reason the range sits where it does — using
   `scarcity_features.py` and `soldCohortPremiums`. Promote `poi_rarity.py`'s conditional-rarity
   line (*"6 share your combination — only 2 are also within a 5-minute walk of a park"*), and
   design the un-approved state, since consultant approval cannot scale to 26,297 pages.
