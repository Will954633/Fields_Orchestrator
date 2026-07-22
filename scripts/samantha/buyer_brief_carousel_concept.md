# Buyer Brief — Carousel Concept (draft, 2026-07-23)

**Status:** DRAFT for Will's review before launch. Not built/launched.

## Why this format

Current live ad (`120251570876350134`, "Buyer Brief v2") uses ONE static hero image + generic copy
("270+ properties... you need the 5 that matter") and has a weak conversion rate. The proven top
performer on the account (`120244636404650134`, "Who buys a home for $1,550,000...", 92 sessions,
7.6% conversion, 7 converters — the best of any ad checked) uses a completely different formula:
a specific-number hook question → concrete transaction detail → a dramatic reveal → "full story below."
Established learning (memory `fb_ads_experimentation_playbook.md`): specific property story beats
generic framing every time we've tested it.

**The gap:** Buyer Brief's actual underlying product IS five specific properties every week (the
"Five Property Friday" pipeline already generates this) — but the ad doesn't showcase any of them
specifically. A carousel is a natural fit: one card per property, each using the proven hook-story
formula, with the final card as the lead-capture CTA.

## Proposed structure (5-6 cards)

**Card 1 (hero/hook):** Reuses the winning ad's exact formula but pluralised —
> "5 homes just sold on the southern Gold Coast this week. One went $340K over what the agent quoted.
> Which one, and why?"
Image: best/most dramatic of the week's 5 properties (hero photo).

**Cards 2-5 (one per property):** Each mirrors the winning formula in miniature —
> "[Address] — sold for $[X]. [One striking fact: land value vs house, days-on-market surprise,
> price history swing, etc.]"
Image: each property's own hero photo. Pulls directly from the same weekly "Five Property Friday"
data already generated — no new content-generation work, just a new packaging.

**Final card (CTA):** "Every Friday we do this for 5 more. Get the next one before it's public."
→ existing lead form (email + phone, matches current v2 form fields — no funnel change).

## What this does NOT change
- Lead form fields (email + phone) — unchanged, already proven.
- Targeting, budget, campaign structure — unchanged, this is a creative-format test only.
- The underlying "Five Property Friday" content pipeline — reused as-is, zero new generation cost.

## What I need from Will before building
1. **Approve the concept** (or redirect it).
2. **Confirm image rights** — Domain-sourced property photos in ad creative; confirm this is already
   cleared (the current single-image ad presumably already uses a Domain-sourced photo, so likely fine,
   but flagging since a carousel uses 5-6 photos instead of 1).
3. Once approved: I can pull this week's actual 5 properties + draft the exact per-card copy for
   final review — holding off on that until the concept itself is confirmed, so I'm not drafting copy
   for the wrong direction.

## Change-ledger note (once launched)
This is a genuine format test (single image vs carousel) on an existing, already-tested funnel —
log to `change_ledger.py` with baseline = current v2 ad's conversion rate, metric = lead-form
completions, per the existing "one test at a time on a surface" discipline (Task 3).
