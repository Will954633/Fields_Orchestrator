# Product — Your Home's Hub (V4)

The evidence and positioning phase of the `/off-market/:slug` redesign. `../Research/` holds the eleven
input files; this folder holds what we concluded from them.

**Created:** 2026-08-06 · **Rescoped:** 2026-08-06

---

## Scope — the boundary these documents work inside

`/off-market/:slug` is a landing page for **one address**, and its only job is to convert **the owner of
that home** into claiming it and creating their **Home Hub**.

**Out of scope:** buyer jobs, listing jobs, anything about homes that are on the market — availability,
asking prices, "is this listing overpriced", price guides, underquoting, search filters, depth tiers.
The premise of the page is a home that is *not* for sale; the moment a job assumes an asking price or a
buyer, it is describing a different product.

**One bounded exception:** listing-side evidence is admitted only where it establishes *who pays the
incumbents and what that buys*, because that is the argument for why an owner shouldn't trust them about
their own home. It lives in dossier §1.3 and matrix §A2, and never becomes a user job.

---

## Reading order

| # | Document | What it is |
|---|---|---|
| 1 | **`01_USER_JOBS_AND_GAPS.md`** | The dossier. Seven **owner** jobs, what competitors give them today, where it fails, what Fields can do about each — with an honest register of what we cannot do yet |
| 2 | `02_COMPETITOR_CAPABILITY_MATRIX.md` | The table. Owner-facing capabilities (§A1), listing-side evidence of who pays (§A2), overseas benchmarks, and the four capabilities where we can be genuinely differentiated |
| 3 | `03_CLAIMS_REGISTER.md` | The gate between internal evidence and public copy. Tier A (say it), Tier B (verify first), Tier C (never) |

Start with the dossier's §0 and §1 — three findings constrain everything else.

---

## The three things most likely to be got wrong

1. **The feature gap is closed in Australia.** REA already has address estimates *and* a claim-your-home
   dashboard with 3M tracked properties. Any copy beginning "no one in Australia does this" is false and
   checkable in thirty seconds. We compete on accountability, workings and the absence of a lead-resale
   motive — not on novelty.

2. **Coverage is the ceiling, not design.** A comparable range exists on **7% of sold addresses**. The
   no-range state is the *majority* state and has to be designed as the primary one.

3. **Card 0 currently says "We found your home."** Across 5,685 Reddit posts there is not one positive
   reaction to an unsolicited "we found your property" approach. It's the highest-priority copy change
   in V4 and it's logged as C10 in the claims register.

---

## Status

Evidence phase complete. Nothing designed, nothing built. `Design/` and `Build/` folders come later and
should sit alongside this one.

**Four decisions are open for Will** — see dossier §8:

1. Is the Hub a persistent homeowner utility or a seller on-ramp? *(recommendation: the former, which is
   also the latter)*
2. How do we unblock Reddit? *(Bright Data KYC / paid PullPush / official Reddit API)*
3. Do we tear down REA's and Domain's owner dashboards before writing public copy? *(recommendation: yes —
   nobody has looked inside them, and it is the spine of the comparison)*
4. Does "nobody calls unless you ask" become an operational rule? *(if yes, possibly the most valuable line
   in the product; if no, it cannot be said at all)*

**Blocking verification** before anything public ships: the seven items in the matrix's verification queue,
and the calibration of confidence labels — currently inverted in parts of the backtest.

---

## One housekeeping note

`../Research/GTP_market_analysis.md` is **misnamed**. It is not market analysis — it is a GPT critique
transcript of the mini-site V2 sessions plus one section on address-search intent, and it contains no
competitor grievance evidence. Suggest renaming to `GPT_minisite_session_critique.md` so nobody reaches
for it expecting market data. Not renamed here, since it wasn't asked for.
