# Tinny Giveaway — Pilot Test Brief

**Prepared:** 2026-08-27 · **Goal:** before committing real budget, run a small, structured pilot that
tells us — with attributable numbers — **what a lead costs, how far people will go in the form, and how
many are real prospects.** Companion to `LEGAL_COMPLIANCE_BRIEF.md`, `TERMS_AND_CONDITIONS_DRAFT.md`,
`INSTANT_FORM_SPEC.md`.

---

## 1. The questions this pilot answers

1. **Cost per lead (CPL)** — and cost per *qualified* lead (local + owner-occupied + consented + intent).
2. **Funnel conversion** — impression → form-open → completion, at each ask level.
3. **Will they enter their address?** (the key asset) — measured as a voluntary fill rate *and* as the
   completion cost of making it mandatory.
4. **Will they consent to marketing — by channel?** Separate opt-in rates for **email, SMS, phone**.
5. **Will they declare buy/sell intent?** Answer rate + the distribution across 6-month / 12-month /
   buying / selling / just-curious.
6. **Lead quality** — % local, % owner-occupied (our data), % contactable.

The design principle: **change one thing per arm** so each drop-off is attributable, and make the
"willingness" questions **optional** so we *observe* real behaviour without destroying the lead.

---

## 2. Method — three form arms, one variable each

Run **three Instant Forms simultaneously**, identical in everything (creative, targeting, budget,
placements, prize) **except the form**. This makes the form the only variable.

| Arm | Form | What it measures |
|---|---|---|
| **A — Lean baseline** | First name + phone only | CPL floor, max completion rate |
| **B — Full / optional** | + address *(optional)* + intent *(optional)* + per-channel consent *(optional)* | **Voluntary** fill/opt-in rates for address, consent, intent — the core behavioural read |
| **C — Full / required** | + address *(required)* + one required consent + intent *(optional)* | The **completion cost** of forcing address + consent |

- **A vs B** → what the extra *asks* cost in completion when they're optional (usually little, since
  they're skippable).
- **A vs C** → the true friction of *requiring* address + consent (the config we'd run live).
- **B** → the headline behavioural numbers: of people who complete, what share *voluntarily* give
  address, tick each consent channel, and answer the intent question.

*(If budget/volume is tight, run just A + B — B alone answers most of Will's questions; add C when
scaling.)*

---

## 3. The form fields (exact)

**Standard (all arms):** `FIRST_NAME` + `PHONE` — both auto-prefill.

**Address** (B optional / C required): `CUSTOM` free text — "Your home's street address."

**Buy/Sell intent** (B & C, **optional** multiple-choice):
> *"Are you thinking about buying or selling property?"*
> - Selling in the next 6 months
> - Selling in 6–12 months
> - Buying in the next 12 months
> - Both buying and selling
> - Just curious / not right now

**Consent — as an optional, per-channel multi-select** (B; measures willingness *and* gives express
consent for whatever they tick):
> *"I'm happy for Fields to contact me about property by:"* ☐ Email ☐ SMS ☐ Phone
> *(ticking a box = express consent for that channel — measurable per channel.)*

**Consent — required (C only):** a single required tickbox = *"I consent to Fields contacting me by
phone, SMS and email about property services (opt out anytime)"* + the QLD-30+/T&Cs declaration.
This mirrors the live-campaign consent from `INSTANT_FORM_SPEC.md`.

> ⚠ Whatever channels a person consents to is the **only** lawful basis to contact them (DNCR / Spam
> Act). In Arm B, non-consenters are measured, **not** contacted.

---

## 4. Metrics & definitions

| Metric | Formula |
|---|---|
| CPL | arm spend ÷ leads |
| Cost per **qualified** lead | arm spend ÷ (local ∧ owner-occupied ∧ consented ∧ intent-positive) |
| Form-open rate | form opens ÷ impressions |
| Completion rate | submissions ÷ form opens |
| **Address supply rate** (B) | valid in-area addresses ÷ submissions |
| Address "tax" | completion(A) − completion(C) |
| **Consent opt-in** (B) | per channel: ticks ÷ submissions (email / SMS / phone separately) |
| **Intent answer rate** (B) | answered ÷ submissions; + the % in each option |
| Local rate | GNAF-matched QLD/GC ÷ submissions |
| Owner-occupied rate | our occupancy classification ÷ submissions |

**Qualified lead = local + owner-occupied + consented to ≥1 channel + selling-intent (6–12mo).** That
count, divided by spend, is the number that actually decides whether to scale.

---

## 5. Budget, volume & duration (and the honest stats caveat)

- **Why a giveaway is a good pilot vehicle:** the prize drives a low CPL and high volume, so we reach
  statistically-useful sample sizes **cheaply and fast**.
- **Target ≥ ~100 completed leads per arm** for the rate comparisons to mean something (≥150 is better;
  below ~50/arm the numbers are directional only).
- **Suggested spend:** **$20–25/day per arm**, **ABO (ad-set budget, not campaign budget)** so each arm
  gets equal spend — *do not* use Advantage campaign budget, which would starve the "harder" arms.
- **Duration:** **10–14 days** — long enough to clear Meta's learning phase (~50 conversions/ad set)
  and span two weekends.
- **Rough envelope:** 3 arms × $22/day × 12 days ≈ **$790 total** for ~300–600+ leads. (Scale to 2 arms
  or shorter if you want a cheaper first look.)
- ⚠ **Caveat:** a pilot gives **direction, not precision.** Treat a 5-point difference between arms as
  noise; act on the big gaps (e.g. "half of completers give a real address" or "only 15% consent to
  phone"). Prize-hunters will skew intent toward "just curious" — that's a real, useful signal, not a
  flaw.

---

## 6. Validity guardrails

- **One variable per arm** — forms differ, nothing else. Same creative, copy, audience, placements,
  daily budget.
- **Run simultaneously**, not sequentially (avoids day-of-week / news confounds).
- **ABO budgets** so Meta doesn't reallocate spend and bias the comparison.
- **Validate addresses post-hoc** (GNAF match + our `Gold_Coast` data) to separate real in-area
  addresses from junk/typos — raw "address supplied" overstates quality.
- **De-dupe** entries; watch serial comp-enterers.
- Keep the **creative about the boat** (not a valuation service) so Meta doesn't reclassify it Housing
  and change the audience mid-test.

---

## 7. Data capture & analysis

- Leads (with all field answers + consent + timestamp) pull via **`scripts/fb-lead-puller.py`**; spend
  and delivery via **`fb-metrics-collector.py`**; funnel/engagement via **PostHog**.
- Enrich each lead's address through our **occupancy classification** (owner-occupied vs leased) and
  **GNAF/suburb match** for the local + quality flags.
- Output a single comparison table (the metrics in §4) per arm, plus the intent-answer distribution.
- I can wire a small `pilot_report.py` that joins lead exports + spend and prints the table on demand.

---

## 8. Decision criteria (set the bar before you look)

Define go/scale thresholds up front so the result isn't rationalised after. Suggested starting bar
(tune with Will):

- **Cost per qualified lead ≤ $[X]** (the number that beats our other channels).
- **Address supply (voluntary, Arm B) ≥ 40%**, or completion cost of requiring it (A−C) **≤ 15 pts**.
- **Phone consent ≥ 25%**, **SMS/email ≥ 40%**.
- **Selling-intent (6–12mo) ≥ 10%** of completers.

**Outcomes:** (a) all bars cleared → scale with Arm C config; (b) address kills completion but voluntary
supply is decent → run address optional + enrich the rest ourselves; (c) intent/consent too low → the
giveaway attracts prize-hunters, pivot to the warm seller-intent funnel (the alternative in our earlier
strategy note).

---

## 9. Legal / compliance (applies even to a pilot)

The pilot still collects name/phone/address + consent, so the same law applies: a **QLD-only, free-entry
promotion** with **T&Cs**, **Meta disclaimer**, **privacy notice**, and **express consent per channel**
before any contact. Use the `TERMS_AND_CONDITIONS_DRAFT.md` (solicitor-reviewed) and only follow up on
consented channels. See `LEGAL_COMPLIANCE_BRIEF.md`.

---

## 10. Next steps

1. Confirm the prize + dates (needed for the T&Cs and the form).
2. Solicitor sign-off on T&Cs + consent wording.
3. I build the **3 pilot forms + 3 ad sets PAUSED** (launcher modelled on `launch_reel_leads.py`), ABO
   $22/day each, boat creative, QLD/GC targeting — and log `ad_decisions`.
4. Activate on your go-ahead; let it run 10–14 days; I produce the comparison report.

*Cheapest useful first cut: Arms A + B only, $25/day each, 10 days (~$500) — answers "what CPL, will
they give address, will they consent by channel, will they declare intent" without the third arm.*
