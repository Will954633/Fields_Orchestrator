# SEO (Google organic) — standing brief

**Last updated:** 2026-08-13 by Will + Samantha (first briefing session)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not background reading. Work
> inside §1 Direction and §4 Standing Authorisations is executed autonomously and reported
> afterwards. Work outside it is proposed and waits.
>

---

## 1. Direction — what we are doing here and why

Six stated goals, in Will's words, in his order:

1. **`/for-sale-v3` on page one for general home-search queries in our target area** — e.g.
   "houses robina". ⚠ *We do not currently know what those search terms are.* Finding them
   and checking where we rank is the first job, not an assumption to skip past.
2. **Top 3 results for `/property` and `/off-market` pages.**
3. **Excellent page-one showing for "Fields Real Estate" and "Fields Estate"** — the brand SERP.
4. **Good search traffic into the market-intelligence pages.**
5. **Articles ranking highly — ideally #1.** Will's reasoning: *"there are very few authors
   writing about our specific Gold Coast, southern Gold Coast, and specific suburb articles.
   We don't compete with others here."* This is an uncontested niche; treat a non-#1 ranking
   on a genuinely local query as a defect, not as competition.
6. **Work towards Google News inclusion** — articles good enough to apply.

**Work with the articles domain.** Will explicitly wants these two talking: *"The SEO domain
agent should be able to communicate feedback to the article agent so they can work together
to optimise articles."* You have a channel:

```bash
python3 conductor_state.py directive --domain articles --from seo --text "<specific, evidenced feedback>"
```
That arrives as a peer NOTE, attributed to you, which articles reads at its next cycle start.
Use it for concrete things — this query has no article, this article's title is losing clicks
at position 4, this topic ranks and should be extended. Not for vague direction.

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| Canonical business name | **"Fields Real Estate"** — Will's ruling 2026-08-13 | Site currently also uses "Fields" and "Fields Estate"; drift blocks entity resolution. |
| Brand SERP | **Standing responsibility** | First thing a seller sees when researching us. |
| `/for-sale-v3` target queries | **UNKNOWN — must be discovered** | Will: "I don't know what the search terms are, we need to get them and check that we are ranking." |
| GSC search-intent collector | **Broken** since 08-10 (`invalid_scope`) | Patch queued. Brand + query measurement is degraded until it lands. |
| Property `<title>` hybrid | Proposed (REC-seo-001), draft written | 92 page-1 pages ready. |
| Google News | **Aspiration, not yet applied for** | Needs article quality first — coordinate with articles. |

## 3. Goals — what good looks like

1. `/for-sale-v3` on page 1 for general area home searches (terms TBD).
2. Top 3 for `/property` and `/off-market`.
3. Page-one dominance for "Fields Real Estate" / "Fields Estate".
4. Growing organic traffic into market-intelligence pages.
5. Articles at #1 for their local queries.
6. Article quality sufficient to apply for Google News.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

- Titles, meta descriptions, headings and on-page copy.
- Schema and structured data, including the site-wide rename to "Fields Real Estate".
- Sitemap, robots, canonicals, redirects, internal linking.
- Indexing submissions (IndexNow, Bing) and recrawl requests.
- **Fixing indexing and de-indexing bugs** — including the on-market false positive that is
  handing back page-1 off-market URLs (REC-seo-002). This is a bug defeating stated intent;
  fix it rather than proposing it.
- Keyword and SERP research to discover the target query set.
- Sending evidenced feedback to the articles domain via `--from seo` notes.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money,
editing the crontab, editing monitoring/health-check code, contacting a real person,
deleting data, Gold Coast go-live.

- (none beyond the global list — Will granted public copy authority on 2026-08-13)

## 6. Context the agent cannot get from data

- The channel is SMALL: 3,494 impressions / **52 clicks** over 28 days. Nothing reaches
  significance; reason about mechanisms and say so.
- Brand volume is ~10 impressions/week for "fields real estate" at avg position 3.4. This is
  about trust for a few high-intent researchers, not traffic.
- **Google IGNORES our meta descriptions on key pages** and writes snippets from body copy.
  Do not "fix" a tag Google does not use — check the live page against the SERP first.
- `/for-sale-v3` body copy contains single-property valuation figures ("valuation of
  $1,726,668") which Google surfaced into the brand SERP — a Rule 5 breach originating in
  body copy, not the tag.
- An unrelated agent (Ben Fields, PRD Burleigh Heads) ranks 3rd on our own brand name.

## 7. Open questions — Will to answer

- [ ] Is a QLD real estate licence held? (Gates the GBP category, REIQ membership, and how we describe the business.) **Still unanswered.**
- [ ] Google Business Profile: confirm the service-area-business route from the home address.

## 8. Changelog

- 2026-08-13 — seeded by Samantha from measured data.
- 2026-08-13 — **first briefing session held with Will.** §1-§7 written from his words.
