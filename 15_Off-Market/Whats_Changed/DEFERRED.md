# "What's changed recently" — what was deferred to ship on 10 August 2026

Shipped live inside V4 on 2026-08-10. Four things were consciously left out to
get it in front of readers the same day. **None of them can make the block say
something false** — that was the condition for deferring each one — but three of
them will make it go quiet if they are ignored, and one is a standing risk.

The safety property that made deferral acceptable: **both content layers
self-expire.** The generated suburb/macro layer stops rendering
`TIMELINE_MAX_AGE_DAYS` (45) after `TIMELINE_GENERATED_AT`; a watch point stops
the day after its date. A forgotten refresh costs a quieter page, not a wrong one.

---

## 1 · Events live in the website repo, not in Mongo — OWNER: whoever runs the monthly research

**What was planned:** a `system_monitor.whats_changed_events` collection, seeded
from `events.yaml`, so the monthly research pass could publish without a website
deploy — the way Market Pulse works.

**What shipped:** `events.yaml` → generated into
`src/pages/OffMarketPage/v4/whatsChangedData.ts`, checked in.

**The monthly job is therefore:**

```bash
# 1. update events.yaml from the new month's homeowner research
# 2. regenerate and push
python3 15_Off-Market/Whats_Changed/whats_changed.py \
    --emit-ts /home/fields/Feilds_Website/01_Website/src/pages/OffMarketPage/v4/whatsChangedData.ts
python3 scripts/push_website_files.py -m "whats-changed: <month> refresh" \
    src/pages/OffMarketPage/v4/whatsChangedData.ts
```

**Risk if ignored:** after 45 days the whole generated layer stops rendering and
the block falls back to the per-home points alone — which, on a home with fewer
than three of them, means the section disappears entirely.

**Do it properly when:** the monthly refresh has been missed once, or someone
other than the person who built it needs to run it.

## 2 · No expiry alerting — OWNER: unassigned ⚠ THE ONE WITH A DATE ON IT

**What was planned:** a daily `job_run`-wrapped check that warns us when a watch
point has passed its date with no `outcome` recorded, and when the generated
layer is approaching 45 days.

**What shipped:** the generator warns on stderr. Nobody reads stderr.

**The live example:** the RBA decision of **11 August 2026**. Write `outcome:`
into that watch in `events.yaml` on the 12th and it converts into an ordinary
dated timeline entry — which is the trigger point for the per-suburb commentary.
Write nothing and it silently vanishes from every page on the 12th, and the block
loses the only thing giving a reader a reason to return.

**Risk if ignored:** not a false statement — a lost feature, invisibly.

**Do it properly when:** the second watch point is added. One is trackable by
hand; a recurring calendar of them is not.

## 3 · No invariant tests — OWNER: unassigned

**What was planned:** executable checks over every generated string —

- no causal verbs (`caused`, `drove`, `led to`)
- no forecast markers (`expect`, `forecast`, `will likely`, `could mean`)
- every macro event carries a local reading or does not render
- every watch names a metric we actually publish
- suburb figures use the **rolling** basis, never single quarters

**What shipped:** all of these hold in today's strings, and are stated as ⚠
comments in `whats_changed.py`, `events.yaml` and `WhatsChangedSection.tsx`.

**Risk if ignored:** a future edit reintroduces one and nothing catches it. The
rolling-basis rule already failed once during development — the first run put
Robina at **−4.7%** on the same page where the market card said **+5.8%**.

**Do it properly when:** anyone other than the author edits `events.yaml`.

## 4 · No repeat-reader suppression — OWNER: product question, not a task

A reader returning in September sees the same May and June events. We hold a
device token and could suppress, but it is genuinely unclear that we should — a
report re-read monthly may benefit from the continuity. **Decide before building.**

---

## What was NOT deferred, and must not be quietly dropped later

- **The engine provenance gate.** The per-home layer returns nothing unless the
  engine produced the figure. Every sentence in it refers to "the centre of this
  home's range", and a declined valuation has no centre. 26% of homes take that
  path; verified live on 19 Manhattan Avenue — 0 per-home points, page intact.
- **Reconciling over the whole candidate pool**, not the 8 displayed comparables.
  Computing a sale's effect from the 8 answers a question about a method we do
  not ship, and that exact error produced a retracted finding on 2026-08-10.
- **The rolling median basis** for every suburb figure.
- **Dedupe of local readings.** Each measured figure appears once. The first
  render showed the same median sentence three times.
