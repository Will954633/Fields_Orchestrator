# SEO (Google organic) — standing brief

**Last updated:** 2026-09-15 by Will + Samantha (second briefing session)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not background reading. Work
> inside §1 Direction and §4 Standing Authorisations is executed autonomously and reported
> afterwards. Work outside it is proposed and waits.
>

---

## 1. Direction — what we are doing here and why

**⭐ PRIORITY PIVOT (Will, 2026-09-15): follow the evidence — spend cycles on RANK and
ADDRESS-SEARCH FINDABILITY, not on snippet/CTR tuning.** The 2026-08-15 title-CTR experiment
was the cleanest snippet intervention available and, graded 28 days later, it **did not move
CTR** — across every template this cycle, clicks tracked *position*, not snippet quality. At
~630 clicks / 28 days, polishing titles Google may rewrite anyway is not where the leverage
is. The leverage is:

1. **What actually moves RANK** for the pages that matter (`/for-sale-v3`, `/property`,
   `/off-market`), and
2. **ADDRESS-SEARCH FINDABILITY.** `[ADDRESS-SEARCH-INDEX-STALE]` — **1,843 core-suburb
   addresses are unfindable in our own index**, and address search carries a **45× conversion
   lift** (`searched_address` → `submitted_address` is the single strongest path in the whole
   funnel). An address the index can't find is a conversion that cannot happen. Drive this:
   diagnose it, measure it, and coordinate the fix (the index rebuild itself may be an ops/
   website job — own the findability outcome, hand off the mechanics if needed).

Snippet/meta CTR work is now **lower priority** — do it only where it's cheap and clearly
worth it (e.g. shipping the Rule 5 title guard, §4), not as a headline effort.

**The goals, re-ordered to match (Will's words, new order):**

1. **Rank movers + address-search findability first** (the pivot above).
2. **`/for-sale-v3` on page one for general home-search queries** — e.g. "houses robina".
   Currently **position 13**. ⚠ *We still do not know the exact target query set* — discover
   it (this is the first concrete job, not an assumption to skip).
3. **Top 3 for `/property` and `/off-market` pages.**
4. **Page-one dominance for "Fields Real Estate" / "Fields Estate"** — the brand SERP.
   Names are now unified to "Fields Real Estate" (was three); keep it clean.
5. **Articles ranking highly — ideally #1** on genuinely local queries. Uncontested niche:
   *"there are very few authors writing about the southern Gold Coast… we don't compete with
   others here."* A non-#1 on a local query is a defect, not competition.
6. **Google News inclusion** — medium-term, gated on article quality (coordinate with articles).

**Work with the articles domain.** Will wants these two talking:

```bash
python3 conductor_state.py directive --domain articles --from seo --text "<specific, evidenced feedback>"
```
Concrete only — this query has no article, this title is losing clicks at position 4, this
topic ranks and should be extended. Not vague direction.

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| **Effort priority** | **Rank + address-search findability > snippet CTR** (Will, 2026-09-15) | CTR experiment showed no effect at this traffic; clicks track position. |
| Canonical business name | **"Fields Real Estate"** — unified, down from 3 | The 2026-08-23 `/about` work held; entity resolution unblocked. |
| Property `<title>` hybrid (REC-seo-001) | Shipped 08-15; graded **no_effect** | CTR 1.61%→1.43%. Live + working as designed, but the metric didn't move. |
| Off-market de-indexing (REC-seo-002) | Shipped 08-15; graded **worked** | noindex share 11/20→5/20; the page-1 placeholder bug is gone. |
| Rule 5 title guard (REC-seo-008) | **Ready to ship on this refresh** | Blocks `/property` titles asserting a single valuation; 8/75 hooks fall back to generic. |
| Brand-SERP seller copy | Drafted (`DRAFT_brand_serp_seller_entry_copy.md`), Rule 5 checked | Ready to ship. |
| Address-search index | **STALE — 1,843 core addresses unfindable** | Now a priority (§1). Index built March; needs rebuild. |
| GSC search-intent collector | Was broken (`invalid_scope`) | Verify it's live; query-dimension pull sees only ~9% of impressions (use `dims=page` for totals). |
| Google News | Aspiration, not applied | Gated on article quality — coordinate with articles. |

## 3. Goals — what good looks like

1. **Move rank** on `/for-sale-v3` / `/property` / `/off-market`, and **make the 1,843
   unfindable addresses findable** (45× conversion lift on address search).
2. `/for-sale-v3` on page 1 for general area home searches (discover the query set first).
3. Top 3 for `/property` and `/off-market`.
4. Page-one dominance for "Fields Real Estate" / "Fields Estate".
5. Articles at #1 for their local queries.
6. Article quality sufficient to apply for Google News.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

- **⭐ Ship REC-seo-008** — the Rule 5 title guard in `src/lib/propertyTitle.ts` (reject a hook
  with a single non-range valuation figure asserting the home's worth; fall back to the generic
  address title). This is a bug defeating editorial rules already agreed — ship and report.
- **⭐ Drive address-search findability** — diagnose/measure the stale index and the 1,843
  unfindable addresses; ship what's in your remit (indexing, sitemap, internal links, recrawl)
  and coordinate the index rebuild if it needs ops/website work.
- Titles, meta descriptions, headings and on-page copy (now a *lower-priority* lever — see §1).
- Schema and structured data, including the "Fields Real Estate" naming.
- Sitemap, robots, canonicals, redirects, internal linking.
- Indexing submissions (IndexNow, Bing) and recrawl requests.
- **Fixing indexing / de-indexing bugs** defeating stated intent (e.g. the off-market
  301-into-noindex residual: 46 URLs / 1,408 impressions, incl. 7 waterfront with no recovery
  path — investigate and fix rather than propose).
- Keyword and SERP research to discover the target query set.
- Ship the drafted brand-SERP seller copy.
- Sending evidenced feedback to the articles domain via `--from seo` notes.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money, editing the
crontab, editing monitoring/health-check code, contacting a real person, deleting data, Gold
Coast go-live.

- (none beyond the global list — Will granted public-copy authority 2026-08-13)
- **Article syndication is canonical-gated (Will, 2026-08-13):** no third-party platform may
  carry an article's full text without `rel=canonical` back to fieldsestate.com.au. Our
  articles rank 4–10 for exact-address queries — duplicates would compete against our strongest
  organic position. If articles proposes a syndication channel, this is your veto to apply.

## 6. Context the agent cannot get from data

- **The channel is SMALL** — ~72,000 impressions / ~1,490 clicks per 90 days; ~630 clicks / 28
  days. Nothing reaches significance; reason about mechanisms and say so. **This is exactly why
  the pivot in §1 is right: at this volume, CTR points don't compound into meaningful clicks.**
- **CTR work has not beaten position drift** at this traffic (the 08-15 title experiment). If a
  snippet intervention can't move the metric, spend the cycle on rank or findability instead.
- Brand volume is ~10 impressions/week for "fields real estate" at avg position 3.4 — trust for
  a few high-intent researchers, not traffic. An unrelated agent (Ben Fields, PRD Burleigh
  Heads) ranks 3rd on our own brand name.
- **Google IGNORES our meta descriptions on key pages** and writes snippets from body copy.
  Never "fix" a tag Google doesn't use — check the live page against the SERP first.
- **Field-path traps (Rule 8):** the API *flattens* valuation to top-level
  `reconciled_valuation` / `valuation_range_low/high`; the nested `valuation_data.confidence.*`
  path is the DB shape and returns `None` against the API. Confirm the shape before concluding.
- **The `dims=query` GSC pull sees only ~9% of impressions** (GSC drops anonymised-query rows).
  Use `dims=page` for channel totals and before/after.

## 7. Open questions — Will to answer

- [x] Re-authorise + priority pivot to rank + address-search findability? **Yes; pivot to (b).**
  (Will, 2026-09-15)
- [x] Will holds a FULL QLD real estate licence (confirmed 2026-08-13) — GBP category *Real
  estate agent*, REIQ membership available, may be described as a licensed agency.
- [ ] Google Business Profile: confirm the service-area-business route from the home address.
- [ ] (process, Samantha handling) `due-for-grading` stopped surfacing due recommendations, and
  `seo_landing_performance` stores a single overwritten snapshot so it can't answer before/after
  — both being fixed outside the brief.

## 8. Changelog

- 2026-08-13 — seeded by Samantha; first briefing session, §1-§7 from Will's words.
- 2026-09-15 — **second briefing session.** PRIORITY PIVOT to rank + address-search findability
  over snippet/CTR (Will chose (b) on the evidence that CTR work didn't move the metric).
  Goals re-ordered. Re-authorised: ship REC-seo-008 (Rule 5 title guard) + the brand-SERP copy;
  drive the 1,843-unfindable-address problem. Recorded graded outcomes (001 no_effect, 002
  worked) and the brand-name unification.
