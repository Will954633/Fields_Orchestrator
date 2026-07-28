# Samantha — Weekly SEO Improvement Workflow

This is a **special, once-per-week** run whose single job is to **raise the site's SEO
performance** — generally, and with particular focus on **`/for-sale-v3`** (the flagship
buyer feed and the page Will most wants ranking). It is separate from your daily run. A
monitor on the Fields Systems Health sheet (Process Registry → "Weekly SEO Improvement")
goes STALE if this workflow has not run in ~7 days, so it must produce a real, logged
improvement each week — not just analysis.

**North star for this run:** more qualified organic impressions and clicks landing on our
buyer pages over the coming weeks — especially `/for-sale-v3` and the `/houses-for-sale/:suburb`
landing pages — by making the pages easier to crawl, index, and click.

---

## The data you review (READ ALL OF IT FIRST)

1. **SEO & Indexation Dashboard** (the dedicated sheet, updated nightly):
   `https://docs.google.com/spreadsheets/d/1ePTElYggYG8ZQKag4FuLCuh8uYTYfVWhGg9X_dTzyYs/edit`
   Read every tab via the google-drive MCP (`read_file` exports each as CSV):
   - **Overview** — 28d clicks/impressions/CTR/position + WoW deltas; sitemap composition; indexation summary.
   - **Daily Trend** — is the trend up, flat, or down? Note inflections.
   - **Top Queries** — where are we getting impressions but **poor CTR** (title/meta opportunity) or **poor position** (content/authority opportunity)? Which queries are address-lookups vs category ("houses robina") vs informational?
   - **Top Pages** — which pages earn clicks; which earn impressions but no clicks.
   - **By Page Type** — which surfaces (property / off-market / market-metrics / houses-for-sale / articles / for-sale feeds) pull traffic and which underperform relative to their URL count.
   - **Indexation** + **Indexation Log** — per-page-type index coverage from live URL-Inspection sampling. Which page types have low **Indexed %** or high **Discovered/Crawled-not-indexed**? Is the trend improving?
2. **Live GSC**, if you need query×page detail the sheet doesn't hold: `scripts/seo_dashboard.py` shows the API you have (service account, `webmasters` scope) — you may run ad-hoc `searchanalytics` / `urlInspection` reads.
3. **The pages themselves** — fetch `/for-sale-v3` and a couple of `/houses-for-sale/<suburb>` pages as Googlebot (`curl -A Googlebot`) and read what a crawler actually sees (h1, title, meta, canonical, internal links, whether listing cards are in the SSR HTML). Cross-check against `07_Focus` and the memory note `forsale_v3_seo_positioning`.

---

## Diagnose → decide the highest-leverage move

From the data, pick the **one or two** highest-leverage improvements for THIS week. Bias toward
`/for-sale-v3` and its suburb landing pages. Good candidate levers (not exhaustive — let the data lead):

- **`/for-sale-v3` depth:** it currently SSRs ~40 listing cards + editorial hooks. Can more of the crawlable content help — richer per-listing snippets, more internal links to `/property` and `/houses-for-sale/:suburb`, a crawlable "browse by suburb / by bedrooms / by price" link block, an FAQ/answer block targeting informational queries ("how many houses for sale in robina")?
- **Per-suburb landing pages** (`/houses-for-sale/:suburb`): are they indexed yet? If newly crawled, submit them to the Indexing API and add more internal links pointing at them. Consider whether a 4th core-suburb page or a bedroom/price variant is worth it.
- **CTR wins:** for queries with high impressions + low CTR, sharpen the page's `<title>`/meta to match intent (within the editorial rules — ranges not single valuations, no advice, no forbidden words).
- **Indexation gaps:** the dashboard has flagged whole page types indexing poorly (e.g. Articles, Compare). Decide if that's fixable (thin content, missing canonical, noindex, orphaned/no internal links) or intentional — and fix or document.
- **Internal linking:** the biggest cheap lever for a low-authority site. Add contextual links from already-indexed, traffic-earning pages (property pages, market-metrics, news) to `/for-sale-v3` and the suburb pages.
- **Crawl budget:** the ~17k `/off-market/` URLs dilute crawl budget (see memory `seo_indexation_baseline`). If the data shows it's starving the buyer pages, propose (do not unilaterally execute a 17k-page noindex — that is a Will decision) — but smaller, safe internal-link/sitemap-priority tweaks are fair game.

---

## Act — ship at least ONE real improvement (this is mandatory)

Analysis alone does not count. Each week, **implement at least one concrete, safe, reversible
improvement** and verify it, OR — if the only worthwhile move is genuinely a Will-decision
(structural / large blast radius) — write a crisp, evidence-backed **proposal** and escalate it.
Prefer shipping something small and real over proposing something big.

Follow the standing production rules exactly (they are in CLAUDE.md — you have it loaded):
- **Website changes:** edit locally, verify with a real build (`react-router build`) + Googlebot fetch + a screenshot you actually read, then push. **Batch into ONE atomic commit** via the Git Trees API — never a burst of per-file `gh api` PUTs (that has paused the site; see memory `netlify_deploy_credit_cost`). Log the deploy + visually verify (CLAUDE.md Rule 4).
- **Editorial rules (Rule 5):** no advice, no predictions, comparable **ranges** not single valuations in headlines, no forbidden words, exact figures, cite sources.
- **New indexable URLs:** add to the sitemap and submit via the Indexing API where appropriate.
- Anything with large or irreversible blast radius → propose to Will, don't self-approve.

Record what you changed in your **change ledger** (`scripts/samantha/change_ledger.py`) so the
before/after effect can be measured next week.

---

## Deliver

1. **Google Doc** titled `Samantha SEO Weekly — {date_str}` in this run's session folder
   (`FOLDER=$(python3 scripts/samantha/session_folder.py ensure --quiet)`), containing:
   - **What the data shows** — the 3–5 findings that matter (with the numbers), trend direction.
   - **What I shipped this week** — the concrete change(s), the commit, the verification (screenshot read), and the specific SEO hypothesis (what metric you expect to move and roughly when).
   - **`/for-sale-v3` status** — its current indexation + performance and what moved it this week.
   - **Proposed for Will** — anything needing his decision, ranked.
   - **Next week's candidate** — the move you'd make next, so the workflow compounds.
2. **Telegram Will** a concise summary (finding → what you shipped → what you propose) with the Doc link, via `python3 scripts/telegram_notify.py "..."`.
3. Keep the report current as you go so a cut-off still delivers something.

Your run is wrapped in `job_status.job_run(...)`, so simply completing this workflow records the
weekly heartbeat that satisfies the monitor — you do not need to write it yourself. But the heartbeat
only means something if you actually **shipped or escalated** a real improvement, so make the run count.
