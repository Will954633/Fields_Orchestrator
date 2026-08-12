# Listing page V2 — working prototype

**Live:** <https://vm.fieldsestate.com.au/concepts/on-market/index.html>
**Built:** 2026-08-10 · **Regenerate:** `python3 build.py`

> ⚠ **Prototype, not a deploy.** Nothing here has been pushed to the website. It is served
> statically from `/concepts/` (noindex, no-store, no build step), like the off-market mocks.

---

## What it is

A working implementation of `03_Audit/LISTING_PAGE_V2_CONTENT_SPEC.md` and
`03_Audit/V2_INTERACTION_AND_RETURN_DESIGN.md`, rendered from **real data** for a real live listing.

**Subject:** 38 Glen Eagles Drive, Robina — chosen because it exercises almost every hard case at once:

| Feature | Why this property |
|---|---|
| **“Offers Over $1,479,000”** | Demonstrates the price-type explainer — a Form 6 **minimum**, not an estimate |
| **12 recorded price events** | The richest campaign timeline in the inventory |
| **Withdrawn 10 June, relisted 7 July** | Portal shows **33 days**; true cumulative is **137** |
| **−17.6% from first price** | The largest reduction measured across live stock |
| **Ask below the range floor** | Forces the arithmetic line to work in the *unusual* direction |
| High-confidence range, 8 adjusted comps, floor plan, 13 measured rooms, 14 photos, battle-axe block | Every section has something real to render |

---

## Verified working

Tested headlessly against the served page:

- **11 openable controls**; `aria-expanded` toggles, `+` → `−`, body hidden/shown correctly
- **Comparable adjustments reveal** (9 line items on the first comp)
- **Address field opens a new browser tab** (2 → 3 tabs) — `window.open()` fires *synchronously*
  inside the click handler, which is the whole reason it isn't blocked
- **Follow-this-sale** per-event opt-in, including the nearby-owner checkbox
- 0 console errors, 0 network errors, mobile 375px and desktop 1440px

### Editorial / legal audit — passes
No banned words · no verdict on a listing (“Overpriced” is gone) · no advice or directive language ·
no predictions · no motive or tactic language (C4) · no accuracy claim · no single valuation figure in
a headline · no rounded `$1.4M`-style figures.

Positive requirements present: range not point estimate · **published error rate** ·
“not a confidence interval” · “we do not claim to be more accurate” · not-the-listing-agent
disclosure · inspection times · POA s 216 cited · Form 2 gap · true vs portal DOM · address field ·
nearby-owner opt-in.

*(The audit script lives in the git history of this session; re-run it against `index.html` before
any future deploy.)*

---

## Real vs illustrative

**Real, from `Gold_Coast.robina`:** address, specs, land (cadastral), floor area, price and its raw
string, all 12 price events, 8 adjusted comparables with every itemised adjustment, the confidence
range, 13 measured rooms, floor plan, 14 photographs, zoning and lot/plan, inspection times, agent
name, battle-axe frontage (from `satellite_analysis`).

**Real, from measurements taken 2026-08-10:** the 75% / 48% / 79% market stats; the Fields-vs-Domain
disagreement figures; the ±12% band and its 61%/67% hit rates; MAE 10.5% / median 8.2% / within-10%
59%.

**Illustrative:**
- Robina median $1,490,000 — carried over from the `Whats_Changed` mock, **not recomputed here**.
- The two forms **do not submit anywhere**. They fire a toast explaining what would happen.
- Transfer duty, council rates, water and energy are deliberately rendered as **“not computed” /
  “not held”** — that is the P2 “unknown is a value” rule working, not missing work.

---

## Known issues to fix before any production build

1. **⚠ Photographs total ~46 MB** (largest single image **10.6 MB**). Inherited from the blob store,
   not from this design. **Production must serve resized derivatives.** Mitigated here with eager-first-4
   + lazy rest + intrinsic dimensions, but that is a bandage.
   → **Specced 2026-08-13: `03_Audit/IMAGE_DERIVATIVES_SPEC.md`.** Measured: a 14-photo gallery goes
   10.0 MB → 1.8 MB (82%) as pre-generated WebP renditions; ~21 GB of disk against 376 GB free.
   Not built yet.
2. **The `/off-market/` destination must be fast before the address door ships** — it currently
   measures TTFB 2.5–3.2 s and ~21.6 s full load. A new tab that hangs is worse than no tab.
   *(To be clear about what this destination is: the Layer 9 address field takes the **visitor's own
   home**, not this listing. The listed property stays on `/property/:id`. The visitor's home is by
   definition not for sale, hence `/off-market/:slug`.)*
2b. **The address door must hit the currently-listed guard.** `openOwn()` is a stub — it writes
   placeholder text into the new tab and never resolves an address. If the visitor's own home *is*
   currently listed, `/off-market/` has no page for it. Production already solves this
   (`analyse-your-home-submit.mjs` → `findLiveListing()` → redirect to `/property/:id`, no stub
   created), including the cadastral-twin fallback. Whatever ships must route through the same guard.
3. **Mobile new-tab behaviour is untested on a real device.** Test a slide-over against it.
4. **Suburb median is stale/hardcoded.** Wire to the live series.
5. **Rageclick instrumentation not added yet** — the pre-build task in the interaction spec.
6. **Legal sign-off outstanding** on POA Sch 2 marketeer status before the price-evidence sections go
   public.

---

## What this prototype demonstrates that the live page does not

- A **price that is explained**, not just displayed — the single largest content gap, on 79% of stock
- **True cumulative days on market** across a withdrawal and relist (137 vs the portal's 33)
- **Adjusted comparables with every adjustment shown** — global whitespace
- A **published error rate** next to the range — no Australian AVM does this
- **What is wrong with the property**, including the battle-axe block the photographs don't show
- A **campaign timeline that reports events and never motives** — the rule that makes it safe to
  publish without repelling the vendor we want
- **“Unknown” published as a value** in the costs and risk sections
- **Inspection times and a route to the agent** — absent from the live page entirely
- **One ask, after the value**, address-only, opening in a new tab so the buyer keeps the listing
- **Follow-this-sale** with the nearby-owner opt-in — a self-declared seller signal, volunteered,
  with no gate

## What it deliberately does not do

No “Overpriced” badge. No second valuation model. No six seller CTAs. No advice on what to offer or
when. No claim to be more accurate than anyone. No motive attributed to any seller.
