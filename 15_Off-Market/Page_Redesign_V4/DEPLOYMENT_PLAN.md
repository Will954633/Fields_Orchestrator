# V4 → `/off-market/:slug` — deployment plan

**Written 2026-08-08.** Decision: ship V4 as the live off-market page for all properties.

**⚠ This page carries ~14,600 indexed URLs and 91% of our traffic is organic.** Every step below is
ordered so that nothing user-facing changes until the data behind it is true.

---

## The one rule that orders everything

> **The copy must never make a claim the data cannot support.**

V4 says *"we widened the range until four in five of them landed inside it"*. That is true only of a
range computed by the new engine. Rendered over an old flat ±12% range it is **false** — ±12%
contained the sale 58% of the time. So **Phase 1 must complete before any V4 copy goes live**, and
that ordering is not negotiable.

---

## Phase 0 — done

| | status |
|---|---|
| Valuation methodology settled and shipped | ✅ MAE 8.05%, per-suburb 80% bands |
| Water geometry backfilled | ✅ 100% coverage |
| Receipts reconcile | ✅ verified per comparable |
| Live methodology pages corrected | ✅ commit `dcb3e58d` |
| V4 prototype content complete | ✅ incl. the three wired sections |

## Phase 1 — data truth (TODAY, running)

**1.1 Recompute every off-market valuation on the new engine.**

```bash
python3 scripts/batch_value_offmarket.py --force
```

~9 properties/second after cache build. 12,332 houses across the three suburbs.

**Acceptance:** `valuation_data.confidence.range_basis.measured_on == "2026-08-08"` on 100% of
off-market houses that get a figure at all. Verify with the coverage query in Phase 5.

**1.2 Confirm what legitimately has NO figure.** Expect a material share — this is correct
behaviour, not failure:

| reason | expected |
|---|---|
| outside the $1M–$2M design envelope | large |
| attached dwelling (GTP/BUP/CTS/SUP, floor-to-land > 0.70) | ~8% of stock |
| waterfront (canal/river/ocean — out of scope) | small |
| too few comparables | small |
| **no floor area at all** | **~49% of off-market homes** ⚠ |

⚠ **1.2 is the finding that most affects the rollout.** Roughly half of off-market houses resolve to
no floor area, and floor area is the largest adjustment in the method. Those pages will show a
directional treatment, not a range. **The V4 fallback path must be exercised on real examples before
launch** — see Phase 3.2.

**1.3 Rebuild the report layer.** V4 renders from `system_monitor.property_reports`, which currently
holds **103 docs, 0 marked done**. The 14.6k indexed pages are not backed by it. Either extend the
report builder across the book, or make the React port read `valuation_data` directly and treat
`property_reports` as optional enrichment. **The second is strongly preferred** — see Phase 2.1.

## Phase 2 — the port

### Progress

| # | piece | status |
|---|---|---|
| 0 | loader exposes `valuation` **with provenance** | ✅ `8828ac45` |
| 1 | answer block | ✅ `ccb099b6` |
| 2 | reliability section | ✅ shipped |
| 3 | comparables — **reuse `ValuationEvidence.tsx`** | ⚠ needs an adapter, see below |
| 4–8 | remainder | not started |

### ⚠ The comparables adapter — the one real surprise

`ValuationEvidence.tsx` takes a single `evidence` prop, so reuse is clean. But that payload is
written by `slot_resolver.valuation_evidence_from_engine()` into the **property report document**,
and only **103** of those exist against ~14,600 pages.

The resolver's own docstring says it "reads straight off `valuation_data` — no recomputation".
**So the transform is pure, and porting it to a TypeScript function in the loader unlocks a
1,068-line component (photo strips, per-feature adjustments, weight %, verified flags, evidence map)
for the whole book instead of 103 addresses.** That is the single highest-leverage remaining task.

⚠ Two things inside that component need handling when it is adopted:
- It rounds the working range to the nearest $100k "so the band reads as a considered estimate".
  Our band is a **measured 80% band** and rounding it changes what it means. Decide deliberately.
- It refers to "the consultant-signed final range" — a contact promise, which this page's central
  claim rules out.

### ⚠ Unresolved product decision, now load-bearing

The live deck is a **gated $15 unlock**; V4 gives the answer away. The answer block, already built,
renders the range for free. **The port cannot stay silent on this much longer** — it is a decision
about the business model, not the rendering, and it should be made deliberately rather than settled
by whichever component ships first.



**2.1 ⚠ Decide the data contract first.** V4's Python renderer reads `property_reports.cards`. The
live deck reads Mongo directly. Porting V4 as-is would make a 103-document collection a hard
dependency for 14,600 pages.

**Recommended:** the React port reads `valuation_data` (present on every property) for everything on
the primary path, and treats `property_reports` cards as progressive enhancement — a section that
renders only when its data exists, exactly as V4 already does for `acc`, `scarcity` and `activity`.

**2.2 Port in this order** (each is independently shippable and independently reversible):

| # | piece | source | notes |
|---|---|---|---|
| 1 | The answer block — range, centre, "why this wide", measured error, the hinge | new | the core claim; port first |
| 2 | Reliability section | new | per-suburb ACCURACY constants must come from `16_Valuation/accuracy/`, never hardcoded twice |
| 3 | Comparables | **`ValuationEvidence.tsx` already exists** | do NOT rebuild — see `Design/03_PORT_PLAN.md` |
| 4 | Seasonality + median chart | **`SeasonalityStrip.tsx`, `MedianPriceChart.tsx` exist** | already imported by `OffMarketPage/MarketCharts.tsx` |
| 5 | The nearby-sale contrast | new | |
| 6 | Timing | new copy, ported visuals | `timing_answer()` logic must move server-side or to a shared util |
| 7 | The three wired sections | new | localStorage only — **must not post** |
| 8 | Scarcity / buyer / next | new | lowest value, port last |

**2.3 ⚠ Two things must NOT come across** (from `03_PORT_PLAN.md`):
- *"The final figure is being reviewed by a property consultant"* — a contact promise; the page's
  central claim is that nothing here starts a conversation.
- The statutory CMA block — belongs on a requested appraisal, not a page nobody asked for.

**2.4 Keep the invariants.** `Prototypes/check_invariants.py` asserts no dead anchors and that every
cue resolves to the following section. The React port needs the equivalent as a test, or the
structural guarantees are lost at the port boundary.

## Phase 3 — verification before any traffic

**3.1 Render-verify, not just build-verify.** `tsc` passing is not evidence. Screenshot the built
page and read it. See `[[website_verification_gates]]` — a bare `tsc` checks zero files.

**3.2 ⚠ Test all four data states on real addresses**, not the happy path only:

| state | example |
|---|---|
| full engine valuation | 11 Placid Court, Varsity Lakes |
| **no floor area → directional** | pick from the ~49% |
| outside the envelope | any > $2M |
| attached / excluded | 24 Brooklyn Crescent, Robina |

A page that reads beautifully on the first and incoherently on the second is not ready, and the
second is roughly half the book.

**3.3 Copy guard.** No "90% confidence interval", no banned words, no claim of a method that did not
produce the number shown.

## Phase 4 — rollout

**⚠ Behind a flag, not a replacement.** Replacing 14,600 indexed pages outright leaves no baseline
to measure engagement against — which is the entire point of shipping. PostHog already carries
`for_sale_page_v1` and `discover_mode_v1`; add `offmarket_v4`.

| stage | traffic | gate to advance |
|---|---|---|
| internal | flag-forced only | all four data states read correctly |
| 10% | one week | scroll depth and dwell not worse than current deck |
| 50% | one week | no ranking loss on sampled URLs |
| 100% | — | |

**⚠ SEO:** these URLs are indexed and organic is 91% of traffic. Keep the URL, the `<title>`, the
meta description and the structured data stable across the change. A redesign at a stable URL is
safe; a URL change is not. Watch Search Console coverage for two weeks —
`[[geoblock_crawler_allowlist]]` is the standing trap here.

## Phase 5 — verification queries

```bash
# Coverage of the new methodology
python3 - <<'PY'
import sys; sys.path.insert(0,'/home/fields/Fields_Orchestrator')
from shared.db import get_gold_coast_db
db = get_gold_coast_db()
for s in ('robina','varsity_lakes','burleigh_waters'):
    q = {"listing_status": {"$nin": ["sold","for_sale"]}, "property_type": "House"}
    tot = db[s].count_documents(q)
    new = db[s].count_documents({**q, "valuation_data.confidence.range_basis.measured_on": "2026-08-08"})
    fig = db[s].count_documents({**q, "valuation_data.confidence.reconciled_valuation": {"$ne": None}})
    print(f"{s:<18}{tot:>7,} homes  {new:>7,} recomputed  {fig:>7,} with a figure")
PY
```

## What is NOT in scope

- Further valuation accuracy work — Will: *"I will return to improving valuation accuracy at a later
  date."* The open leads are recorded in `16_Valuation/`.
- Waterfront — out of scope by decision.
- The 48.7% missing floor area — a real gap, but it is a **data coverage** project, not a blocker for
  shipping the page, provided Phase 3.2 proves the fallback reads well.

## Standing obligations after launch

1. **The band is an output, not a constant.** Re-derive `_EMPIRICAL_80_BAND_PCT`,
   `_SUBURB_80_BAND`, `_SUBURB_CALIBRATION` and `_ADJUSTMENT_RELIABILITY` after any method change,
   and update `ACCURACY` in the renderer and the React port from
   `16_Valuation/accuracy/` — never by hand in two places.
2. **80% coverage is a promise.** If a re-measurement shows a suburb below 80%, the band widens.
3. **Anything ongoing gets a heartbeat** — CLAUDE.md Rule 7, and Rule 7b's outcome assertion.
