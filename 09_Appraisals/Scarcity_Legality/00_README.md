# Scarcity & Legality — Research Folder

**Prepared:** 2026-05-14 · **For:** Will Simpson (Fields Estate)
**Status:** Initial research complete. Five operational fixes identified. Pending legal review by Queensland-admitted counsel before live implementation.

---

## What this folder is

The question Will asked:

> Document research around possible legal ramifications of marketing properties using scarcity metrics we derive ourselves. What can we say, what can't we say, do we need to hold evidence, what disclaimers can we use, what if we get the statement wrong, can a buyer come back and sue us?

In the Australian model — the listing agent is the only agent in the transaction — liability flows **both ways**: from the **buyer** (post-purchase, claim relied on, paid too much) and from the **seller** (appraisal misled them on listing/agency decision). This research treats both.

The work product is the seven documents in this folder. Read them in order.

---

## How to read this folder

| # | File | What it does | Read if you want… |
|---|---|---|---|
| 00 | `00_README.md` (this file) | Index + executive summary | …to know what's here |
| 01 | `01_legal_framework.md` | The law that applies, in plain English: ACL s18, s30, s4, POA QLD, injurious falsehood, conduit defence, disclaimers | …to understand the legal rules |
| 02 | `02_claim_audit.md` | Every scarcity / comparison claim Fields currently makes, with risk rating | …to know what we're saying today |
| 03 | `03_safe_language_playbook.md` | Eight operational rules + specific rewrites for the high-risk claims | …to know what to say instead |
| 04 | `04_disclaimer_library.md` | Ready-to-use disclaimer text for listing pages, appraisal PDF, marketing collateral | …to copy-paste disclaimers |
| 05 | `05_liability_scenarios.md` | Concrete sue-back scenarios (buyer + seller), likely outcomes, defence strategies | …to understand the real-world exposure |
| 06 | `06_research_sources.md` | Every URL, case name, and statutory reference cited | …to verify a claim or go deeper |
| 07 | `07_amendments_and_operating_framework.md` | Specific page-by-page edits + the strategic pivot from "scarcity metrics" to "irreplaceability" + nine standing rules going forward | …to know what we're changing and how we work from here |

---

## Executive summary (the bottom line)

### Can Fields keep saying scarcity-style things?

**Yes — with discipline.** Australian law does not prohibit data-driven comparative claims. It requires that they be:
- **True** at the time made,
- **Defined** (geographic, temporal, dataset scope shown in equal prominence to the headline),
- **Substantiated** (you have the evidence file to produce in 21 days if the ACCC asks),
- **Current** (auto-generated claims are re-validated; stale ones are suppressed).

A claim like "*Largest lot in our active Burleigh Waters listing set as at 14 May 2026 (825m²)*" is defensible. The same claim as "*Largest lot for sale*" is not. The difference is the scope disclosure, not the underlying data.

### What can Fields **not** say?

- **Universal-negative comparisons about competitors** without same-sample, same-period, same-methodology evidence. ("No agency does X." → defamation/injurious falsehood territory if you can't prove it.)
- **Unqualified "only / first / largest"** claims that read as absolute statements about all listings in the market. (Auto-generated badges currently do this.)
- **Forward-looking numbers without a reasonable-grounds file** sitting somewhere a third party could audit. (Appraisal target sale prices, campaign forecasts.)
- **Specific quantitative comparisons against a named competitor** unless you've actually run the comparison on the same sample with the same methodology. (The "Domain accuracy 15.0%" claim is the highest single-item risk in the current materials.)
- **"Most appraisals…" / "Most agents…"** claims without survey evidence. (These are factual claims about industry behaviour, not puffery.)

### Do we need to hold evidence?

**Yes — for every quantitative claim, every forecast, every comparison.** The ACCC's s219 substantiation power means you must be able to produce the evidence in 21 days. ACL s4 means the burden of proof on forecasts is *yours*, not the buyer's or seller's. The 6-year limitation period means a claim made today can be sued on in 2032 — your evidence file needs to survive that long.

The good news: Fields already runs the analysis. The discipline is to *save the substantiation file at the moment the claim is made* — not reconstruct it later.

### What if we get a statement wrong?

**Buyers can sue. Sellers can sue. Regulators can fine us.**

- **Buyer suit:** ACL s18 damages = the price premium attributable to the misrepresentation. Typically $20k–$120k per single-buyer claim, plus legal costs.
- **Buyer-led class action:** if the misleading claim was a template (auto-generated, appeared on many listings), a litigation funder can aggregate buyers. This is the *systemic* risk and the most serious.
- **Seller suit:** misleading appraisal → seller chose Fields → lost money. Damages cap usually marketing fees + opportunity cost; $10k–$80k per seller.
- **ACCC/OFT action:** civil penalty up to **$100M corp / $2.5M individual** per contravention from 28 March 2026. Each separate misleading claim is a separate contravention. Plus QLD POA s212 — up to ~$90k per false representation by an individual licensee.
- **QCAT disciplinary:** licence conditions, suspension, cancellation, lifetime ban.
- **Domain (or other competitor) injurious-falsehood suit:** if the "Domain accuracy 15.0%" comparison is wrong or unsupported, Domain has standing to sue Fields. Corporations with >10 employees can't sue in defamation but can sue in injurious falsehood.

### What disclaimers work?

**Disclaimers cannot exclude ACL liability.** They can:
- **Narrow the universe** of the claim (geographic, temporal, dataset),
- **Establish equal-prominence context** to defeat the *ACCC v TPG* dominant-message doctrine,
- **Surface the methodology** so a reader sees the basis for the claim.

The disclaimer library (`04_disclaimer_library.md`) has ready-to-use text for:
- Property page inline rarity tooltips,
- Property page footer (data sources),
- Appraisal PDF cover-page disclaimer (full version),
- Per-page footnotes for the appraisal,
- Marketing collateral, email, Facebook,
- A new public `/methodology` page.

---

## The five operational fixes (ranked by impact)

From `05_liability_scenarios.md` Section 4. These five fixes capture ~80% of the risk reduction available, with effort measured in days, not months:

1. **Drop or rework the Domain accuracy comparison** (`02:B14`). Either build the same-sample backtest evidence file, or remove the public comparison. Highest single-item risk.
2. **Universe disclosure on every auto-generated rarity badge.** Inline tooltip with geography + dataset + date. See `03:Rule 1`.
3. **Page-render-time revalidation** of auto-generated rarity claims. Suppress when superseded; keep the audit trail. See `03:Rule 4`.
4. **Substantiation file for every forward-looking number** in the appraisal. Saved at issue time. Retained 7 years.
5. **Reframe universal-negative competitor claims as observations.** "We have not seen…" replaces "No agency does…". See `03:Rule 8`.

---

## Implementation status

| Fix | Status | Owner | Next step |
|-----|--------|-------|-----------|
| 1. Domain comparison rework | Pending decision | Will | Decide: drop or build same-sample backtest. If drop — edit appraisal template before next issue. |
| 2. Universe disclosure on rarity badges | Pending implementation | Will + Claude | Update `PropertyPage.tsx` to render tooltip + date stamp; update `calculate_property_insights.py` to embed scope in label string. |
| 3. Rarity claim revalidation | Pending implementation | Will + Claude | Add `valid_until` field to rarity insight; revalidate on page render; auto-suppress when stale. |
| 4. Appraisal substantiation file | Pending workflow | Will | Define the file structure; integrate into the appraisal generation script; retain 7 years. |
| 5. Reframe universal-negatives | Pending edit | Will | Apply playbook Rule 3 rewrites to `Version_Four/preview.pdf` template before next appraisal. |

---

## Important disclaimers about this research

This is **research synthesis, not legal advice**. Engage Queensland-admitted counsel before relying on any specific position for live marketing. Suggested counsel checks:

- The injurious-falsehood analysis for the Domain comparison — confirm injurious-falsehood standing for Domain in NSW (Domain's HQ jurisdiction).
- The reasonable-grounds defence for the v4 appraisal — counsel review of the comparable-sales methodology before next issue.
- The QLD POA s212 application to auto-generated claims — confirm OFT's current enforcement appetite.
- The disclaimer language drafts — counsel sign-off before publication.

The law evolves. The ACL penalty regime doubled on 28 March 2026; further changes are likely. Recheck the framework at least annually, and after any significant ACCC enforcement action involving real estate or comparative claims.
