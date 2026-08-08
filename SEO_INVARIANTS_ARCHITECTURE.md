# SEO state must be derived from shared invariants, not rebuilt per component

**Written 2026-08-08**, after six defects found in ~36 hours that are all the same
architectural failure. This is not a style guide; every claim below is a live incident
with a fix-history entry.

## The pattern

> A rule is implemented in one path. Later, another component becomes the production
> path — a redesign, a new route, a generator, an edge redirect — and does not inherit
> the rule. Nothing compares the two, so both remain "green".

The rule is never *deleted*. It is *stranded*. That is why monitoring built around
"did the job run?" cannot see it: every component is behaving exactly as written.

## The evidence

| # | Rule | Where it lived | What became production | Result |
|---|---|---|---|---|
| 1 | Crawler UA allowlist | `geo-block.js`, Google family | AI crawlers (GPTBot, ClaudeBot, PerplexityBot…) | 403 + noindex to every AI crawler, while `robots.txt` explicitly allowed them |
| 2 | Suburb nav links | `DecisionFeedV3Page` `loading` branch | loader began seeding `initialFeed`, so that branch stopped executing | 3 suburb pages orphaned — `referringUrls: None`, ranked for zero commercial terms |
| 3 | Address as `<h1>` | `DiscoveryDeck` (fixed 2026-07-31) | `DeckV3` became default 2026-08-04 | Two `<h1>`s, neither naming the property, on a family that ranks on exact-address queries |
| 4 | Unit-address exclusion | route: `address \|\| complete_address \|\| ADDRESS_STANDARD`<br>generator: `address` only | both shipped, never compared | **4,559 URLs** in the sitemap serving `noindex, nofollow` |
| 5 | Effective address | `off-market.$slug`: 3-field chain<br>`property.$id`: `address \|\| full_address` | both shipped, never compared | **115 sitemap URLs** serving 200 + "Property Not Found" + noindex for documents that resolved fine |
| 6 | Multi-lot suppression | detector discovered candidates via a query containing **its own output flag** | — | Self-cancelling oscillator: ~390 pages flipped `index`↔`noindex` nightly for 7 days |
| 7 | The canonical URL | route `meta()` (SSR, correct) | a hydrated `useEffect` calling `updateSeoMeta({url})` | `/market-intelligence/Varsity-Lakes` declared itself a duplicate of its own `/sell-now` tab and left the index. Google honoured our declaration exactly; the declaration was accidental |

Six of seven are **one policy expressed in two places that drifted**. The other (#6) is
the same disease inside one component: a rule whose input included its own output.

\#7 is the purest form of it. SSR owns the canonical; legacy client code, written when
this page was a client-rendered SPA, still believed it owned the canonical too. Both
were internally consistent. The later writer won, and it was wrong.

Note #4 and #5 are the *same field-chain question* answered differently by three
consumers. That is how a single ambiguity produced 4,674 broken URLs.

## Why the existing monitoring missed all of them

Every affected process self-reported and showed green. `job_run` records success on a
clean exit — CLAUDE.md rule 7 — and each component *did* exit cleanly. The sitemap cron
generated a sitemap successfully on the mornings it advertised 4,559 noindex URLs. The
multilot job reported `success` while doing the exact inverse of the previous night.

Rule 7b already says a heartbeat must assert an outcome. The lesson these six add:

> **An outcome assertion inside one component cannot detect disagreement between two
> components.** Each was individually correct. The defect existed only in the gap.

## The invariants

Stated as properties of the *site*, not of any component. Anything that can be phrased
this way can be enforced by comparison rather than by remembering.

0. **A URL has exactly ONE canonical authority.** Route/server metadata defines it.
   Hydrated components may not independently rewrite `<link rel="canonical">` — Google's
   own guidance is to put the canonical in the HTML source and not let JavaScript change
   it. (#7)
1. **One canonical address identity per property entity.** Every consumer resolves an
   address the same way. → `effectivePropertyAddress()` in `db.server.ts`, now the sole
   definition, used by `property.$id.tsx` and `off-market.$slug.tsx`. It deliberately
   excludes `ADDRESS_STANDARD`, which holds a datum code (`"UK"`), not an address.
2. **Every sitemap URL is healthy** — 200 **and** `index,follow` **and** self-canonical
   **and** not an empty-state template. A 200 alone is not health (#5 proved it).
3. **Every healthy, eligible, indexable URL appears in the appropriate sitemap.** The
   converse of 2; #4 and the `under_contract` gap are the two directions of one rule.
4. **Every important SEO landing page has at least one crawlable inbound internal link
   in raw SSR HTML** — not behind state, animation, hydration or a reveal (#2).
5. **Every address-detail page exposes its address prominently in SSR HTML** (#3).

## Enforcement status — honest

| Invariant | Enforced? | By what |
|---|---|---|
| 0 — one canonical authority | **No** | `updateSeoMeta` still *accepts* a `url`; three other callers pass one. Removing `setCanonical` from it, or a lint rule, would enforce it |
| 1 — one address identity | **Partly** | Shared function exists; nothing *prevents* a new consumer writing its own chain |
| 2 — sitemap URL healthy | **Yes** | `scripts/sitemap_robots_invariant.py`, nightly 07:00 |
| 3 — eligible ⇒ in sitemap | **Partly** | Same monitor, invariant B — sampled, and only for URLs GSC already knows |
| 4 — inbound link exists | **No** | Nothing checks it. #2 was found by hand |
| 5 — address in SSR `h1` | **No** | Nothing checks it. #3 was found by hand |

Two of five are unenforced. That is the honest state, and it is the backlog.

## What makes an invariant enforceable

The monitor works because of one property worth copying: **it compares two things that
already exist** — the published sitemap and the served page. It does not re-implement
"what should be eligible". A third copy of that policy would be a third thing to drift,
which is the disease, not the cure.

So the test for any future SEO check:

- **Good:** compare two existing artefacts (sitemap vs page, DB vs rendered HTML, route
  vs generator output).
- **Bad:** re-encode the policy in the checker. It will drift, and then the checker is
  wrong in a way nobody notices.

## Practical rules

1. **One definition per policy, imported — never re-derived.** If two files need the
   same address chain, filter or eligibility rule, one exports and the other imports.
   `FOR_SALE_LISTING_FILTER` and `HOUSES_FOR_SALE_LIMIT` are shared so a count rendered
   on one page cannot contradict the page it links to.
2. **A guard's input must never include its own output** (#6).
3. **SEO-relevant markup belongs on the path that always executes.** If a link or
   heading exists only in a branch, it will be lost the first time that branch stops
   running. The off-market suburb block is rendered in the route, outside all three deck
   arms, for exactly this reason.
4. **When a component is superseded, diff the SEO surface of old vs new** — headings,
   canonical, robots, internal links — before the old one stops being production (#3).
5. **Indexability is a capability decision**, not an address-syntax one. Prefer
   `entity resolved + supported property type + sufficient trustworthy data` over
   proxies like "the address has a slash". Attached homes are a planned surface; the
   unit filter in `generate-sitemap.mjs` is documented as current product eligibility so
   it relaxes when the route starts serving `index, follow`, rather than needing to be
   remembered and unpicked.
6. **Cross-component agreement needs its own monitor.** Per-component health cannot
   detect it.

## Open

- Invariants 0, 4 and 5 have no enforcement.
- **A canonical tag alone does not resolve duplication.** Measured 2026-08-08: the bare
  `/market-intelligence/Robina` hub is *byte-identical* to its `/sell-now` tab (15,910
  chars each, 99% token overlap, identical opening). Google treats canonicals as a
  signal and may still pick its own when pages are genuinely duplicate, so #7's fix is
  necessary but not sufficient — the hub needs distinct content or a deliberate
  redirect. The other tabs are genuinely distinct (35-46% overlap).
- `effectivePropertyAddress()` is shared but not *mandatory* — a lint rule banning
  raw `.address ||` chains outside `db.server.ts` would close it.
- `system_monitor.offmarket_entity_diagnostics` — 64 unresolved same-address groups.
- `ADDRESS_LEVEL_ENRICHMENT_PROPAGATION_ISSUE.md` — enrichment attached by address
  rather than resolved entity. Broader than SEO; affects valuation, comps, appraisals.
