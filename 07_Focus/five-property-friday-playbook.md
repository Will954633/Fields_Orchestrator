# Five Property Friday — Playbook

**Product:** A weekly, per-client email — the 5 for-sale homes in their target suburbs
"worth their attention," each with Fields' proprietary analysis. Not a listing digest;
a **weekly intelligence briefing** built around 5 properties. Feeds the buyer funnel and
surfaces future sellers (buyers who own a Gold Coast home).

**Source funnel:** Facebook lead form "Fields — Buyer Brief (5 that matter)" (v1 email;
v2 email+phone). Leads land in `system_monitor.fb_leads` via `scripts/fb-lead-puller.py`.

---

## Tone
Start **gentle** (data + a light view), sharpen the Fields judgement over weeks as the
relationship and brief deepen. Progressive: the more we learn them, the more licence to
be pointed — because by then it's genuinely personal.

## Compliance (non-negotiable)
- **No advice.** Data + view only — never "you should buy/offer." Reader concludes.
- **Valuation:** show a **range** around the adjusted-comparables number (e.g. our figure
  $1.27M → range $1.11M–$1.42M). Never a single hard figure in a headline. Fine to show
  privately by email to an opted-in buyer; **never** in public FB posts (Will's line).
- **Exact** transaction/asking prices (never rounded); our valuation **range** may round.
- Never claim we're "more accurate than Domain" publicly.
- Forbidden words: stunning, nestled, boasting, rare opportunity, robust market.

---

## Selection methodology  (`scripts/five_property_friday.py`)
1. **FILTER** — hard-match the brief: suburbs, beds ≥ min, baths ≥ min, `for_sale`, budget.
2. **SCORE** — rank by OUR signals: price-vs-value gap, situation (days-on-market, price
   cuts), valuation confidence. The 5 are the ones **where we have something worth saying** —
   not the 5 cheapest matches.
3. **SANITY** — any |gap| > 25% is **flagged for human review, never auto-surfaced** as a
   value call. Extreme gaps are usually a data mismatch (reno, land size, model miss); telling
   a client a home is "$800k under value" when we're wrong torches the one thing we sell.
4. **CURATE** — pick 5 with distinct **roles** so it reads as curation:
   Best value · Negotiation play · Premium priced-right · The stretch · One to watch.
   Only "The stretch" is allowed above budget.

**Run:**
```
python3 scripts/five_property_friday.py --suburbs robina --beds 3 --baths 2 --budget 1300000
python3 scripts/five_property_friday.py --lead-id <fb_leads _id>     # brief from the lead
```
Output is a **markdown draft for review — it never sends anything.**

### Known gap: budget is not on the form
The lead form captures suburb/beds/baths/timeframe but **not budget** — deliberately (kept
the form short for conversion). We capture budget in the **welcome email** (below), which also
seeds the two-way interaction pattern. Without a budget the shortlist is unanchored (the tool
warns). **Send the welcome email first; finalise the shortlist once they reply.**

---

## Welcome email (gentle, budget-seeding)
**Subject:** Your first shortlist — one quick thing first

> Hi [First name],
>
> Thanks for signing up. Your first shortlist lands this Friday.
>
> Here's how it works: each Friday we go through every home for sale in [their suburbs] and
> send you the **five worth your attention** — not everything, just the ones we think are
> genuinely worth a look, with the comparable-sales data behind each.
>
> To make that first one actually useful, one quick thing — **what's your budget range, and is
> there anything that's a must-have or a deal-breaker?** Just hit reply; a sentence is plenty.
>
> That's it. You'll hear from us Friday.
>
> — Will, Fields

Replies come back to Will and inform the shortlist (manual for the first cohort; automate
inbound parsing only if volume demands it). Each week is a chance to enrich the brief
(progressive profiling).

---

## Shortlist template (roles + price-vs-value)
**Subject:** Your 5 for Friday — [Suburb]

> **This week in [Suburb]:** [one market-pulse line — e.g. 37 three-bed homes on the market;
> several priced below what recent comparable sales support.]

Then 5 entries, each: **role — address · beds/baths · asking**, then a one-line Fields take
(price-vs-value range + situation), then the link. Close soft: *"Reply and tell us which to dig
into — or adjust your brief anytime."*

**Worked example (real listing):**
> **1. Best value — 23 Evergreen View, Robina** · 3 bed / 2 bath · asking Offers Over $1,100,000
> Asking $1,100,000 sits at the bottom of our comparable-sales range of $1,110,000–$1,420,000
> (medium confidence, 8 verified comps). On the comps, it's priced conservatively.

---

## Open items / next polish
- **Take-line variety:** the script emits a factual base take; the varied, sharper "Fields take"
  is the AI-editorial layer's job (hook to `scripts/backend_enrichment/generate_property_ai_analysis.py`).
- **Clean price-vs-value only on a subset:** ~⅓ of listings have both a clean numeric asking
  price and a full reconciled valuation; the rest are "Contact Agent"/"Offers over" (show our
  range vs the asking guide instead) or thin valuation data.
- **Market-pulse line:** pull from suburb metrics (median DOM, new-listing count).
- **Budget capture loop:** wire welcome-email reply → update brief → finalise shortlist.
