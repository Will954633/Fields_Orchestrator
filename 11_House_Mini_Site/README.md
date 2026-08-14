# House Mini Site

The per-property seller report at `/your-home/<slug>`. Two generations live here.

*Reorganised 2026-08-05 — V1 build material and V2 session material had been sharing one
flat folder.*

---

## Structure

| Folder | What |
|---|---|
| **`Version_One/`** | The shipped tabbed report — plans, design, content, case studies, the PMF gap analysis, and the scripts and assets that built it |
| **`Version_1.5/`** | The deterministic build of V1 — same nine tabs, same pipeline, LLM prose replaced by Python templates. **A build mode, not a new codebase.** Start here for the sub-2-second work |
| **`Version_Two/`** | The guided-session rebuild. Start at `00_SESSION_SYSTEM.md` |
| **`_shared/`** | Spans both generations — the direct-mail generator, the off-market flow reference, the adjusted-comparables evidence |

Loose at this level, because they span V1 and V1.5:
`AI_DEPENDENCY_AUDIT_AND_DETERMINISTIC_STRATEGY.md` (the audit behind V1.5) ·
`corpus_cost_model.py` (corpus AI + imagery costs).

---

## Version One — what shipped

A nine-tab report: `01 Your Home's Data` · `02 Competition` · `03 Valuation` ·
`04 The Right Buyer` · `05 Process Decisions`, plus Agent, FAQ, Messages and Next Steps.

Code lives at `/home/fields/Feilds_Website/01_Website/src/pages/YourHomePage/`.

**Read first:** `Version_One/README.md` (engineering state) · `Version_One/Design.md` (IA
and design brief) · `Version_One/Content-Plan.md` (copy conventions) ·
`Version_One/Gap_Analysis_11th_Jun/12_MINISITE_PMF_ANALYSIS.md` (the honest verdict).

**The verdict that produced V2**, from the consultant review:

> "Right now it says: 'Look how much we know.' The final version needs to say: 'Here are
> the few things that matter most before you sell — and here is the evidence.'"

---

## Version Two — the guided sessions

Seven short sessions replacing the tabbed report, each answering one question and ending
by naming the next. Also posted as printed booklets to `/off-market` leads.

**Read in this order:**

1. `Version_Two/00_SESSION_SYSTEM.md` — the build contract
2. `Version_Two/PSYCHOLOGY_LAYER.md` — what the reader must feel, and why
3. `Version_Two/REVISION_PLAN.md` — what changed on 2026-08-05
4. The session files

| # | Session | Fields' role |
|---|---|---|
| 1 | Where your home stands right now | Orient me honestly |
| 2 | Where you'd go next | Understand my situation |
| 3 | The number it goes to market with | Show the working and the limits |
| 4 | Priced campaign or auction | Translate my priorities into a method |
| 5 | What's worth doing before launch | Tell me what's worth spending on — and what isn't |
| 6 | How buyer competition is created | Demonstrate campaign expertise |
| 7 | What happens if you choose Fields | Make commitments and take responsibility |

`Version_Two/_superseded/` holds the first draft of the sessions — kept for its evidence
sweeps and open-item records, which carried forward.

---

## Status

**V1 is live. V2 is specification only — nothing is built.**

Per the V2 build order: rework Session 1's opening, build Session 2, measure
session-to-session continuation, and only then build the rest. That number decides whether
the session model earned the rebuild.

**Blockers carried into V2** *(detail in each session's Open items)*
`adjusted_price` not persisted · printed QR cannot save an answer (no `device_token`) ·
the September–December seasonality band contradicts `homeFixture.ts` · three charts
unusable (`ch7-1-buyer-pool` inverted, `ch7-4-portal-traffic` drifted, `ch7-3-marketing-benefit`
unsourced) · three new question ids not yet server-whitelisted · D6 licence status blocks
Session 7.
