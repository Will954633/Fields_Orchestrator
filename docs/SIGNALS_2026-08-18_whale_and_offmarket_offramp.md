# Two signals worth acting on — whale trigger, and the off-market dead end

**Written:** 2026-08-18, late evening AEST, from Will's direction at end of session.
**Origin:** analysis of visitor `019feb00-5692-7d6a-a478-9e642a9b4fa0` — see
[USER_JOURNEY_2026-08-18_warm_return_offmarket_download.md](USER_JOURNEY_2026-08-18_warm_return_offmarket_download.md).
**Status:** ⬜ Nothing built. This is a briefing to pick up cold tomorrow.

Data window throughout: **last 90 days**, PostHog project 348370.
Population: **1,724 distinct visitors, 2,614 pageviews — ~19 visitors/day.**
Baseline: **89 visitors (5.2%) returned on a different calendar day.**

Every rate below was tested with a two-sided Fisher's exact test, not eyeballed. Where a result is
confounded, it says so — those are the ones most likely to waste a week.

---

## Start here tomorrow

**Thread 1 — whale.** The 20.8% return rate is real but **confounded by construction** (the trigger
only fires on people who were already reading). Will's proposed fix — show it to everyone —
**correctly breaks that confound** and is the right next step. ⚠ But **do not measure it on return
rate**: at 19 visitors/day a believable effect needs 104–210 days and the season closes in 43.
Measure **"learn more" click-through** and **within-session continuation** instead.

**Thread 2 — off-market offramp.** Worse than Will suspected, and in a specific way:

> **96.3% of off-market sessions never reach another page** (464 of 482).
> The Fields logo on the live V4 arm is a **bare `<img>`** — not a link, no tracking
> (`ReportHeader.tsx:78`). **There is no path to the homepage on a working V4 page at all.**
> Two people did click a logo and escape — on 24 July, on the older DiscoveryDeck arm, which had a
> six-link site nav. **That nav was dropped in the V4 port.** Both then toured the whole site.

So this is a **regression to fix**, not a feature to invent. Cheapest version is one line.

**Two things I'd check first:** (1) was dropping the nav deliberate or an oversight in the V4 port;
(2) the stale comment at `off-market.$slug.tsx:960` that misstates which arm is live.

---

# Thread 1 — The whale trigger

## The observation

| Session-1 cohort | Returned another day | Rate | p (vs rest) |
|---|---|---|---|
| Fired `whale_dismissed` | 5 / 24 | **20.8%** | **0.006** |
| Fired `whale_shown` | 5 / 37 | **13.5%** | **0.039** |
| Everyone else | 84 / 1,700 | 4.9% | — |

Both significant. `whale_dismissed` is a 4× return rate against baseline.

## ⚠ Why this cannot be read as "the whale causes return"

**The trigger selects its own audience.** `useWhaleTrigger.ts` only fires on `scroll_reversal`
after a `MIN_DWELL_MS` (8s) threshold — i.e. exclusively on people who were already reading, then
stopped. `docs/WHALE_MONITOR.md` states this explicitly and refuses to attempt the comparison:

> *"unlike anything comparing whale-seers to non-seers, which is confounded by construction (the
> trigger SELECTS people who stopped reading, so they were always going to leave more often)."*

So the honest reading today is: **`whale_shown` is a good detector of engaged visitors.** It is not
yet evidence of a good intervention. A thermometer, not a lever.

## ✅ Why Will's proposed next test is the right move

> *"Next test would be to show it to everyone with a 'learn more' option that opens popup text box
> over the page with more information."*

**Showing it to everyone is exactly what breaks the confound.** If the overlay renders independent
of `scroll_reversal`, the audience is no longer self-selected, and any difference between arms
becomes causal evidence rather than selection. This is the correct experimental instinct and it
should be preserved in whatever gets built: **the arm assignment must not depend on visitor
behaviour.**

## ⚠ But the experiment as framed is not powered — read this before building

At **19 visitors/day site-wide**, with a 4.9% baseline return rate:

| Target return rate | Relative lift | n per arm | Total | Days at 19/day |
|---|---|---|---|---|
| 6.0% | +22% | 6,684 | 13,368 | **704** |
| 7.0% | +43% | 1,991 | 3,982 | **210** |
| 8.0% | +63% | 985 | 1,970 | **104** |
| 10.0% | +104% | 415 | 830 | **44** |
| 14.7% | +200% | 144 | 288 | **15** |

(80% power, α=0.05 two-sided.)

**And the season closes.** `SEASON_MONTHS = (7, 8, 9)` in both `useWhaleTrigger.ts` and
`scripts/whale_moment_monitor.py`. As of 18 Aug there are **43 days of season left.** Only the
"triples the return rate" row fits inside that window — and if the effect were really that large we
would not need a test.

**Conclusion: do not measure this experiment on return rate.** It cannot resolve in this season, at
this traffic, for any believable effect size.

## What IS measurable at 19 visitors/day

Pick outcomes that are **immediate and within-session**, where every exposed visitor contributes a
data point on the same day:

1. **"Learn more" click-through rate.** A simple proportion. At ~100 exposures you can tell 5% from
   25%. This is the primary metric and it directly answers "does anyone want more information?"
2. **Post-overlay continuation** — did they view another page / scroll further after the overlay,
   versus after dismissing today's version. Within-person, needs no control group, and
   `WHALE_MONITOR.md` already uses this shape for its `harm` check at n=20.
3. **Dwell delta on the popup content itself** — if the popup holds attention, that is a content
   finding regardless of the return question.

Return rate stays as a **secondary, descriptive** number — reported, never used to declare a
winner this season.

## Open questions for tomorrow

- What should the "learn more" popup actually *say*? The journey doc found two independent signals
  that **the valuation method is the product** (a `valuation_info_scroll` CTA click one second
  after dismissing the whale; `comps` the longest-read deck section at 42s of 224). That is a
  strong candidate for the popup's content.
- Does showing it to everyone break the `harm` metric in `whale_moment_monitor.py`? The monitor
  assumes a scroll-reversal-gated audience. **It will need updating in the same change** — see
  Rule 7b: a monitor that silently keeps reporting on a changed population is worse than none.
- Is the seasonal gate wanted at all for the "everyone" arm, or does that become a year-round
  overlay with different creative?

---

# Thread 2 — The off-market dead end

## The observation

> **96.3% of off-market sessions never reach another page on the site.**
> 482 sessions touched an `/off-market/:slug` page. **18** (3.7%) reached any non-off-market page.

And across the whole population:

| Surfaces touched | People | Returned another day |
|---|---|---|
| Neither | 1,049 | 3.2% |
| Off-market only | 425 | 3.8% |
| Property only | 249 | 4.4% |
| **Both** | **10** | **70%** |

**⚠ The 70% is largely circular** — 7 of those 10 crossed *between* sessions, so touching both
surfaces required a second visit. Do not quote it as an uplift.

**The non-circular fact underneath is the real finding:**

> **Only 3 people out of 1,733 have ever moved between a property page and an off-market deck
> inside a single session.**

The off-market family is **~15,252 pages producing 57% of impressions and 66% of clicks**
(`OffMarketSuburbLinks.tsx`). It is two-thirds of our search footprint, and it is a separate
website.

## This is already half-known

`src/components/OffMarketSuburbLinks/OffMarketSuburbLinks.tsx` documents the same problem,
independently discovered:

> *"it was a complete dead end in the site graph: a sample of 400 found 0 with any non-sitemap
> internal referrer, and 18/18 sampled pages emitted ZERO outbound content links… The intent is NOT
> to improve off-market recrawl — this only fixes the outbound direction; those pages still have no
> inbound internal link."*

So the outbound direction has a fix. The measured 3.7% escape rate is the post-fix number.

## Does anyone click the logo? Yes — but the exit they used no longer exists

Will's assumption was *"we probably don't know, but it's not linked to our home page."*
**Half right, and the half that's wrong matters more than the half that's right.**

**We DO know — PostHog `$autocapture` catches it.** `Fields ▪` was clicked **3 times by 2 people**
in 90 days, and both clicks navigated successfully to `/`.

**But Will was right that it isn't linked — on the arm that is live now.** A code audit
(2026-08-18) found:

> **`src/pages/OffMarketPage/v4/ReportHeader.tsx:78` renders the logo as a bare `<img>`.**
> No `<Link>`, no wrapper, no `onClick`, no `data-*` attribute, **and no analytics import in the
> file at all.**

**Both logo clicks were on 24 July, on the older DiscoveryDeck arm** — which had a real site nav
(`discovery/DiscoveryDeck.tsx:69-79` `buildNav()`: News & Research → `/`, Market Intelligence,
`/for-sale-v3`, `/analyse-your-home`, `/why-fields`, `/contact`, rendered at lines 518-522).

**That nav was not carried into DeckV3 or V4.** V4's hamburger menu
(`ReportHeader.tsx:96-124`) emits **only in-page `href="#section"` anchors** — it goes nowhere.

So the working exit those two visitors used has been removed. We would not even detect the loss,
because the live logo has no tracking on it.

**Both clickers had the deepest sessions in the dataset:**

- `019f939a…` (24 Jul 10:10 UTC, Chrome iOS, Brisbane): deck → logo → `/` → `/market-intelligence/Robina`
  → `/for-sale-v3` → `/analyse-your-home` → back to the deck.
- `019f9536…` (24 Jul 17:47 UTC, Mobile Safari, Sydney): deck → logo → `/` → `/market-intelligence/Robina`
  → `/analyse-your-home` → two `/analyse-your-home/building/:slug` pages → Robina → Varsity Lakes →
  Burleigh Waters → **read an article for 4 minutes**. Then returned to the deck and clicked the
  logo *again*.

**2 of 2 people who found the exit used it to tour the entire site.**

⚠ **Caveat, n=2.** Both on 24 Jul, both from `www.google.com`, both mobile, following similar
paths. Different OS, browser and city (Brisbane 4103 / Sydney 2200), and `is_internal: false` — so
probably real visitors, but QA cannot be fully ruled out and two people is an anecdote.

## ⚠ And when it did work, it was mis-aimed

Both logo clicks landed on `/`, which **immediately redirected to `/market-intelligence/Robina`** —
within ~1 second, before the visitor did anything.

Person 2 was reading a **Burleigh Waters** deck. They were sent to **Robina** news.

Per CLAUDE.md, `/` is `MarketIntelligencePage` (News & Research) and defaults to a suburb. So even
the working version of the offramp discarded the one thing we know for certain about the visitor —
**which suburb's home they were just reading about.**

## The complete exit inventory on the live V4 page

Verified by code audit, 2026-08-18:

| Exit | Destination | Condition |
|---|---|---|
| `See houses for sale in {suburb}` | `/houses-for-sale/:suburb` | `OffMarketSuburbLinks.tsx:80-90`; only if suburb ∈ `HOUSES_FOR_SALE_SUBURBS` **and** `dwellingClass !== "attached"` |
| `See the {suburb} property market` | `/market-intelligence/:suburb` | same block; only if suburb ∈ `MARKET_INTELLIGENCE_SUBURBS` |
| Report PDF/viewer | `target="_blank"` | `ReportSection.tsx:287`, only after a report is requested |
| ~~Logo~~ | — | **bare `<img>`, not a link** |
| ~~Site nav / header / footer~~ | — | **none rendered on V4** |
| ~~Homepage~~ | — | **no path to `/` exists on a working V4 page** |

Both real exits are **one full page-length scroll away, at the very bottom**, after 14 sections.
Both `SUBURB` sets are the same three: `robina`, `burleigh_waters`, `varsity_lakes`
(`src/utils/suburbNormalize.ts:63-98`).

**⚠ For any off-market page outside those three suburbs, `OffMarketSuburbLinks` returns `null`
(line 60) — the page has _zero_ outbound links.** Given the family is ~15,252 pages and only three
suburbs are covered, that is the overwhelming majority of them.

Good news: the block is built in the loader (`off-market.$slug.tsx:68-75, 305, 609`) and sits
beside the deck in the route, so it **is in raw SSR HTML** — no hydration or scroll dependency.

## What Will asked for

> *"perhaps means we need an offramp that directs users from /offmarket to a well thought out page
> on our main website (which may well be our homepage, that could do the job nicely, but i dont
> know how we would get them there)"*

Four findings bear on this:

1. **The task is "build one", not "aim one".** The exit that worked on 24 July was removed when V4
   shipped. The logo is present but inert. This is a regression, not a gap in the original design.
2. **The cheapest possible fix is one line** — wrap `ReportHeader.tsx:78`'s `<img>` in a `<Link>`.
   That alone restores what the DiscoveryDeck arm had. Whether `/` is the right destination is a
   separate question (see below).
3. **The destination should be suburb-aware.** `/market-intelligence/:suburb` exists, and the deck
   knows its suburb (`suburb: burleigh_waters` is on every V4 event). Sending a Burleigh Waters
   reader to Robina news, as `/` currently does, throws away the strongest fact we have about them.
4. **`OffMarketSuburbLinks` already gets this right** — "their home → the inventory buyers can
   choose from → that suburb's market", conditional per suburb. The end-of-deck block is good; the
   problems are that it is 14 sections down, and that it renders **nothing at all** outside the
   three covered suburbs.

## Open questions for tomorrow

- **Where should the offramp live?** Header (always visible), mid-deck, or both? `019feb00…` exited
  at section index 7 of 13 — an end-of-deck-only exit never had a chance with them.
- **Is `/` the right destination given it redirects to a suburb page?** A "well thought out page"
  may need building rather than choosing. `/market-intelligence/:suburb` is the strongest existing
  candidate.
- **What about the ~15,000 pages outside the three covered suburbs?** They currently have zero
  outbound links. A generic-but-relevant fallback may beat `null`.
- **Instrument the logo.** Even before it becomes a link. Right now it has no tracking at all, and
  our only historical evidence is `$autocapture` matching the literal string `"Fields ▪"` — which
  breaks the moment the logo markup changes.
- **Why was the nav dropped?** `DiscoveryDeck.buildNav()` had six site links; DeckV3 and V4 have
  none. If that was a deliberate "no distractions in the report" decision, it is worth re-testing
  against a 96.3% dead-end rate. If it was an oversight during the V4 port, it is a straight bug.
- ⚠ **Fix the stale comment at `off-market.$slug.tsx:960`** — it claims the route "only sets `v4`
  when `?v4=1`", which line 328 contradicts (V4 is the default for the three suburbs, no flag).
  Anyone reasoning about which arm is live will be misled by it. Matches
  [[offmarket_v4_live]] — V4 is live with no flag.

---

# Where the numbers came from

```bash
cd /tmp && python3 - <<'EOF'
import sys; sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from whale_moment_monitor import hogql, _load_env   # raises on failure, never returns [] on error
_load_env()
print(hogql("""
  with s as (
    select distinct_id as did, properties.$session_id as sid,
      max(properties.$pathname like '/off-market/%') as on_om,
      countIf(properties.$pathname not like '/off-market/%' and event='$pageview') as offdeck_pv
    from events where timestamp > now() - interval 90 day group by did, sid
  )
  select count() as sessions, countIf(offdeck_pv>0) as escaped from s where on_om
"""))
EOF
```

**Caveats that apply to everything above:**

- **n is small everywhere.** 1,724 visitors, 89 returners, 2 report conversions in 90 days. Nothing
  here predicts *conversion* — that is unreachable at this traffic. Everything predicts *return*,
  the nearest measurable proxy.
- **PostHog is client-side and lossy** — ad blockers and `navigator.webdriver` drop events, so
  absence is not proof.
- **`is_internal` is not a reliable internal filter** — 0 events in 90 days are tagged `true`.
  Internal traffic is in these numbers somewhere.
- **`$autocapture` element text is brittle** — every logo finding depends on the literal string
  `"Fields ▪"`.

Related memory: [[first_warm_return_offmarket_conversion]], [[offmarket_v4_reading_analytics]],
[[whale_moment]], [[offmarket_v4_live]], [[property_page_visitor_behaviour]].
