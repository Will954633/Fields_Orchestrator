# August 2026 Rebuild — Handover

**Date:** 2026-08-02 · **Branch:** `august-2026-rebuild` · **Production untouched**

## 👉 Look at this first

**https://august-2026-rebuild--lambent-tapioca-86ef75.netlify.app/browse**

That is the rebuild, running on real data, on a branch preview. `main` is unchanged.

Try: scroll the rails · click a card (detail sheet) · **See the trade-offs ↓** ·
**See full analysis →** · and the **Enter your address** unlock on the top rail.

Compare against production: https://fieldsestate.com.au

---

## What is built

| | |
|---|---|
| **Mobile burger** | 7 accordion groups, 33 destinations. **Was specified in §9 and missed on the first pass — it appeared in NEITHER the built list NOR the deferred list here, which is exactly how it went unnoticed until Will asked.** |
| **8 rails** | Listings near you 🔒 · New this week · Robina · Varsity Lakes · Burleigh Waters · Market intelligence · News & research · Your home 🔒 |
| **Data** | Real. 81 editorial-complete listings across the 3 core suburbs, 21 market reports, live articles |
| **Chrome** | Permanent grass masthead + grass footer — the bookend, on every page |
| **Address unlock** | Works. Real 86k-row index → 12 nearest listings with distances |
| **Detail sheet** | AI headline, comparables range, strengths, verdict, trade-offs reveal, seam to `/property/:id` |
| **SEO** | 81 crawlable `/property` links in the server HTML · `noindex` while proven |
| **Responsive** | Clean at 1440 / 1024 / 390 · CLS **0** |
| **Performance** | LCP **436ms desktop / 628ms mobile — both GOOD**. CLS 0. Page 969KB |

## Decisions honoured

1. **3 core suburbs** — 210 listings, 39% editorial-complete (vs 2.7% site-wide)
2. **Hook first** — locked rail above the fold
3. **`/` stays News & Research** — browse ships at `/browse`; cutover is a separate later call
4. **`/for-sale-v3` kept** as the "see all" grid; rails link to it. No redirect

## Bugs found and fixed

**Mine, during the build:**
- Rail cards were `<button>` → **zero** crawlable links. Now `<a href>` with modified-click passthrough. 81 links verified.
- `listings-near` would have **collection-scanned 86,223 docs per call** (`address_search_index` has only `_id_` and no coordinates). Now one indexed lookup via the existing `address-search`.
- The unlock was filtering the ~210 listings already on the page — which only ever matches homes that are *themselves for sale*. Now queries the real index.

**Pre-existing production bugs this work surfaced:**
- **Site-wide mobile horizontal scroll.** A decorative header blob (520px, offset −220px, rotated) with a stale `overflow: visible` left from a removed dropdown. One line — `overflow-x: clip` — fixed it on **14 of 24** captures.
- **Mobile nav opened scrolled past its own first item** — `justify-content: center` inside a scroll container overflows both ways, making leading items unreachable.
- **Footer contrast failed AA** — copper on grass at 3.02:1. Now `--copper-on-dark`, 4.92:1.

## Performance

| | Before | After |
|---|---|---|
| LCP desktop | 3952ms POOR | **436ms GOOD** |
| LCP mobile | 4240ms POOR | **628ms GOOD** |
| Page transfer | 3757KB | **969KB** |
| JSON payload | 2907KB | **118KB** |
| One card image | 307KB JPEG | **6KB WebP** |
| TTFB warm | 3299ms | **33-42ms** |
| CLS | 0 | 0 |

**Three fixes, in order of impact:**
1. **`articles.json` — 2.9MB of article HTML** downloaded to render card titles.
   `fetch-articles.js` now also emits a slim card index (116KB gzipped); the full file
   still serves `/articles/:slug`. ⚠️ **This is a live-site problem too** — the current
   production homepage pays the same 2.9MB.
2. **Full-resolution images** — 307KB-3.6MB sources in 296x167 cards. Now via
   Netlify Image CDN: resized, WebP, edge-cached, 2x srcSet.
3. **CDN caching of the SSR response** — the loader hits three collections per request.

**What actually fixed it:** CDN caching (`s-maxage=300` + `stale-while-revalidate=600`), so a
visitor effectively never waits on a cold render.

**What did NOT fix it, despite my saying it would:** I also parallelised the three suburb
queries, believing serial execution was the bottleneck. Cold cache-busted TTFB was 1.59s/1.32s
*before* and 1.91s/1.40s *after* — within noise. The real cold cost is a **serverless cold start
plus Cosmos connection establishment** (first request in each run: 9.8s / 11.1s), not query time.
The change is still correct in principle and harmless, but it earned nothing and I am not
crediting it.

## Regression evidence

`node visual-check.mjs diff` — 24 captures, production baseline vs branch:

> **14 differences. Every one is `overflow: true → false`.** Nothing else changed.

## How the burger went missing (process note)

The layout route and theme mechanism below are listed as deferred, so they were
never lost. The burger was in neither list — not "built", not "deferred", just
absent. **A specified item that appears in no list is invisible; every item in
00_SCOPING.md must land in one column or the other before this document is
considered finished.**

## Deliberately NOT done, and why

- **Phase 2 layout route** (removing per-page chrome from ~20 files). Pure hygiene now the masthead is correct, and 20 live pages is real risk for zero visible gain. Left for a focused session.
- **Phase 3 theme mechanism** (`prefers-color-scheme`, user override). `/browse` sets `data-theme="dark"` directly, which is enough to prove the surface.
- **The 7,142-literal token backlog.** Only 167 literals across 6 files are in components the browse surface touches. The rest are light-only surfaces that never theme — touching 323 files would have burned the day for no functional gain. Inventory is in `token-audit.md`.

## Still open for you

1. **Does `/` eventually become the browse surface?** Deliberately deferred — measure `/browse` against the 57-click baseline first.
2. **Two pre-existing bugs logged, not fixed:** React **#418 hydration mismatch on `/`** (it did not reproduce on the branch — cause unconfirmed, so I am not claiming credit), and `<header>` landmark missing on six routes.
3. **`/browse` remains `noindex`** until you decide it is ready.

## Files

- `00_SCOPING.md` — the plan, §15 status, §16 build log
- `01_BUILD_PLAN.md` — the executable plan, with the two mid-build corrections recorded
- `visual-check.mjs` — regression harness (`baseline` | `after <url>` | `diff`)
- `token-audit.md` — the 7,309-literal inventory
- `baseline/` + `after/` — 48 screenshots
- Fix history: `logs/fix-history/2026-08-03.md`

## Two notes on my own process

Twice today my **instrument** was wrong rather than the code. Puppeteer's `clip` uses page
coordinates, not viewport, which made several screenshots look broken. And a synthetic
`element.click()` does not reach React's handler, which made a working unlock flow look broken
across two test runs — I nearly "fixed" code that was fine. The endpoint had already passed a
curl test, and that should have told me the fault was in the harness. Both are logged.

I also corrected two of my own estimates mid-build: the token refactor was 7,309 literals, not
~130; and the TypeScript baseline is 210 pre-existing errors, not 8. Both came from looking at
partial output and generalising.
