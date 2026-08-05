# C — First-party behaviour on Fields address-level pages

**Written:** 2026-08-06 (AEST)
**Question:** the Google query that brings someone to an address page is a bare address and carries no
intent signal. On-page behaviour is therefore the only revealed-preference evidence we have. What do
they actually do?

**Bottom line up front:** the address-level page is a **single-screen, single-page, single-address,
single-visit** surface. 93.6% of off-market visitors arrive from Google, 87.5% of their sessions are
one pageview and nothing else, 2.2% look at a second address, 1.1% touch `/analyse-your-home`. The
one behaviour that varies enormously and that we control is **whether the first card earns a second
card** — and the two first-card treatments we have run differ by a factor of ~2.2 on that (71.7% vs
32.9%).

---

## Method

### Source 1 — PostHog (first-party, own instrumentation)

Project "Default project" `348370`, org Fields Real Estate. Queried by HogQL through the PostHog
query API (`POST /api/projects/348370/query/`, `POSTHOG_ALL_ACCESS_KEY` from
`/home/fields/Fields_Orchestrator/.env`) — the MCP server exposed to this session has no
`execute-sql` tool, only `query-trends`-style insight tools, so the raw API was used instead. Helper
script used for every query below is reproduced at the end of this file.

Window: **last 90 days = 2026-05-08 → 2026-08-06.** All queries filtered to
`properties.$host = 'fieldsestate.com.au'` unless stated (Netlify deploy-preview hosts contributed 5
pageviews and are excluded).

**Exclusions.** Custom events carry an `is_internal` boolean set by our own SDK wrapper; every custom
event query below filters `properties.is_internal = false`. `$pageview` and `$autocapture` do **not**
carry that property. For those, the one person known to be an internal tester
(person UUID `fd1964b9-eee3-5343-88d2-ac2d74eebbdc`, recorded in
`memory/posthog_internal_tester_labelling.md`; 86 events, all in a single session on 2026-07-24) is
excluded by `person_id` where it materially changes a number, and that is stated inline. PostHog's
own "filter internal users" toggle does **not** retroactively apply here: person-on-events snapshots
person properties at ingest time, and the flag was set on 2026-07-24 after those events landed, so
`person.properties.is_internal_tester` reads `unset` for all 2,277 pageviews in the window.

**Denominator sanity check.** Whole-site totals in the window: **2,277 `$pageview` events from 1,467
distinct persons**. That is ~1.55 pageviews per person across the entire site — the shape of a
search-arrival, one-page site, and also confirms the traffic is not dominated by a handful of
internal sessions.

### Source 2 — Samantha chat logs

Read `scripts/samantha_chat/README.md` (canonical) and `scripts/samantha_chat/service.py`, the
systemd journal for `fields-samantha-chat`, and every chat/conversation-shaped collection in
MongoDB `system_monitor` (207 collections enumerated; `chat_agent_usage`,
`voice_agent_conversations`, `agent_messages`, `ceo_chat_messages`, `builder_chat_messages`,
`website_feedback` inspected). Result reported in §2 — **the source is empty of real-visitor
questions, and that is a finding, not an inconclusive result.**

---

## 1. PostHog findings

### (a) Volume and arrival channel

```sql
SELECT multiIf(properties.$pathname LIKE '/property/%','/property/:id',
               properties.$pathname LIKE '/off-market/%','/off-market/:slug',
               properties.$pathname = '/analyse-your-home','/analyse-your-home', ...) AS page_type,
       count() AS pageviews, uniq(person_id) AS people, uniq(properties.$session_id) AS sessions
FROM events
WHERE timestamp >= now() - INTERVAL 90 DAY AND event = '$pageview'
  AND properties.$host = 'fieldsestate.com.au'
GROUP BY page_type ORDER BY pageviews DESC
```

| Page | Pageviews | Distinct people | Sessions | Instrumented since |
|---|---|---|---|---|
| `/off-market/:slug` | **314** | 266 | 281 | **2026-07-20** (17 days, not 90) |
| `/analyse-your-home` | 304 | 268 | 287 | full window |
| `/property/:id` | **261** | 180 | 193 | full window |
| `/market-intelligence*` | 249 | 134 | 144 | full window |
| `/articles/*` | 187 | 160 | 162 | full window |
| `/for-sale-v3` | 323 | 249 | — | full window |
| `/` (home) | 109 | 89 | 94 | full window |

⚠ **The off-market page has only existed for 17 days.** 314 pageviews in 17 days vs 261 in 90 days
for `/property/` means off-market is already running at roughly **6× the daily rate** of the property
page. Every off-market rate below is computed on that 17-day window; do not read it as a 90-day rate.

Referring domain (`properties.$referring_domain`, same filter, grouped by page type):

| | `/off-market/:slug` | `/property/:id` |
|---|---|---|
| Google (`google.com` + `google.com.au`) | **294 (93.6%)** | 159 (60.9%) |
| Bing / Yahoo / DuckDuckGo | 0 | 22 (8.4%) |
| **All search** | **294 (93.6%)** | **181 (69.3%)** |
| `$direct` | 20 (6.4%) | 36 (13.8%) |
| Internal (`fieldsestate.com.au`) | **0 (0.0%)** | 27 (10.3%) — but from only **3 people** |
| Facebook (`m.`/`l.`/`lm.`/`facebook.com`) | 0 | 17 (6.5%) |

Two things worth naming:

1. **Nobody reaches an off-market page from inside our own site.** Zero internal referrals in 314
   pageviews. The page has no entrance except Google. Whatever the redesign does, it cannot assume
   the visitor has seen any other Fields page first — they have not.
2. The property page's 10.3% "internal" referral is **3 people**, not a channel.

### (b) What people actually click — settling the prior finding

```sql
SELECT properties.$event_type, properties.$el_text, count(), uniq(person_id)
FROM events
WHERE timestamp >= now() - INTERVAL 90 DAY AND event = '$autocapture'
  AND properties.$host = 'fieldsestate.com.au'
  AND (properties.$pathname LIKE '/property/%' OR properties.$pathname LIKE '/off-market/%'
       OR properties.$pathname = '/analyse-your-home')
GROUP BY 1,2 ORDER BY 3 DESC
```

**Click reach (the denominator that matters):**

| Page | Distinct viewers | Distinct people who clicked *anything* | Reach |
|---|---|---|---|
| `/off-market/:slug` | 266 | **37** (excl. internal tester) | **13.9%** |
| `/property/:id` | 180 | **18** | **10.0%** |

**86% of off-market visitors and 90% of property visitors never click a single element.** Autocapture
under-counts scroll-driven interaction (the deck also advances by scroll — see (c)), but it is the
correct measure of "did they choose to act on something".

**`/off-market/:slug` — 191 clicks by 37 people (internal tester excluded):**

| What | Clicks | Distinct people |
|---|---|---|
| **Advance card** (`›`, `Next`, `Continue`) | **149** | **26** |
| **In-card CTA** (`See …`) | **22** | **9** |
| Back a card (`‹`) | 7 | 5 |
| Site navigation / logo / menu | 10 | 9 |
| Untitled element | 3 | 3 |

In-card CTA text, ranked:

| CTA text | Clicks | People |
|---|---|---|
| **"See what it may be worth"** | **9** | **8** |
| "See how this home might sell today" | 5 | 4 |
| "See how it has grown" | 2 | 2 |
| "See what it means for this home" | 2 | 2 |
| "See where this home sits" / "See the market now" / "See what's driving it" / "See which way it's moving" | 1 each | 1 each |

The single most-clicked piece of copy on the entire off-market page — the only one reaching more than
four people — is **"See what it may be worth."** n=8 people. Small, but it is the modal answer and
every other CTA is a long tail below it.

**`/property/:id` — 58 clicks by 18 people:**

| Category | Clicks | Distinct people |
|---|---|---|
| Site navigation (Properties / Home / About / Contact / …) | 15 | 10 |
| Other | 11 | 7 |
| Untitled element | 8 | 5 |
| **FAQ: "What is *[address] [suburb]* worth in 2026?"** | **5** | **3** |
| Valuation/comps disclosure expand ("How we build this range", "See all 8 comparables", "+") | 4 | 3 |
| **FAQ: "Is *[suburb]* a good suburb to buy in right now?"** | **4** | **3** |
| Comparable-sale row expand ("Compared to 8 Dabchick Drive …") | 2 | 2 |
| **FAQ: "Should I sell before buying another property?"** | **2** | **1** |
| **FAQ: "Is *[address]* overpriced or fairly priced?"** | **2** | **2** |
| FAQ: "How much is my house worth in *[suburb]*?" | 1 | 1 |
| FAQ: "Is Fields Estate the listing agent for this property?" | 1 | 1 |
| FAQ: "How does this property compare to others in *[suburb]*?" | 1 | 1 |
| FAQ: "What is happening in the *[suburb]* property market in 2026?" | 1 | 1 |
| FAQ: "What comparable sales support the asking price?" | 1 | 1 |

> **⚠ This settles the prior claim, and mostly by deflating it.** The earlier analysis reported that
> the only clicks on the property page were on the FAQ items "What is X worth in 2026?" and "Is X
> overpriced?". The relative volume is now known: **17 FAQ clicks in 90 days, from exactly 3 distinct
> people.** Their per-person totals are 9, 6 and 3 clicks; each was a **single session** (2026-07-18,
> 2026-07-27, 2026-07-28); all three arrived from `www.google.com`. Site navigation out-clicks the
> whole FAQ block (15 clicks / 10 people vs 17 clicks / 3 people).
>
> **Do not build a redesign on the FAQ finding.** n=3 is an anecdote. What it *does* establish, weakly
> and consistent with the CTA data above, is direction: when someone on an address page clicks
> anything expressive at all, the thing they open is a **price/worth question about that specific
> address**, not a market-wide or lifestyle question. Both the strongest signal on the off-market page
> ("See what it may be worth", 8 people) and the strongest on the property page ("What is X worth in
> 2026?", 3 people) point the same way. Treat that as a hypothesis with converging weak evidence, not
> a measured preference.

`/analyse-your-home` is included for contrast — 141 clicks, and the top rows are an untitled element
(45 clicks / 22 people — the address input) and a `change` event (22 / 11), i.e. **people type there**.
That page is the only address surface where the dominant interaction is input rather than navigation.

### (c) Engagement: card, dwell, scroll, time

The discovery deck emits `card_viewed`, `card_dwell`, `deck_exit`, `deck_scroll_nudge`. All carry
`is_internal`, `arm`, `slug`, `suburb`, `rendered_index`, `card_id`, `initial_referrer`.

**How far people get through the deck.** Per-session max card index, `card_viewed`,
`is_internal = false`, 152 sessions (instrumented from 2026-07-25):

```sql
SELECT max_idx, count() AS sessions FROM (
  SELECT properties.$session_id AS sid, max(toInt(properties.rendered_index)) AS max_idx
  FROM events WHERE event='card_viewed' AND timestamp >= now() - INTERVAL 90 DAY
    AND properties.is_internal = false
  GROUP BY sid) GROUP BY max_idx ORDER BY max_idx
```

| Reached at least card | Sessions | % of 152 |
|---|---|---|
| 0 (landed) | 152 | 100% |
| **1** | **80** | **52.6%** |
| 2 | 64 | 42.1% |
| 3 | 51 | 33.6% |
| 4 | 45 | 29.6% |
| 5 | 30 | 19.7% |
| 6 | 26 | 17.1% |
| 7 | 22 | 14.5% |
| 8 | 13 | 8.6% |
| 10 | 4 | 2.6% |

**Just under half of everyone who lands on the deck never sees a second card.**

Corroborated independently by `deck_exit` (130 sessions, 95 people, 92 distinct addresses,
instrumented from 2026-07-29): **74 of 130 (56.9%) exited with `max_index_reached = 0`.** Only 2 of
130 (1.5%) reached card 10.

**⚠ The first card is the whole game, and the two first-card treatments differ hugely.** Three arms
are live, each with a different card 0:

| Arm | Card 0 | Sessions | Stopped at card 0 | **Advanced to card 1** | Reached card 4+ | Window |
|---|---|---|---|---|---|---|
| `discovery` | `recognition` | 60 | 17 (28.3%) | **43 (71.7%)** | 27 (45.0%) | 07-31 → 08-04 |
| `ladder_dark` | `hero` | 82 | 55 (67.1%) | **27 (32.9%)** | 12 (14.6%) | 07-25 → 08-05 |
| `v3` | `found` | 10 | 0 | **10 (100%)** | 6 (60.0%) | 08-04 → 08-05 |

Restricted to the overlapping window 2026-07-31 → 2026-08-05 to control for date:
`discovery` 43/60 advanced (71.7%), `ladder_dark` 4/13 (30.8%), `v3` 10/10 (100%). The ranking holds,
but `ladder_dark` n drops to 13 and `v3` n is 10 — **these are not statistically settled results.**
The `discovery` vs `ladder_dark` gap (71.7% vs 32.9% on n=60 and n=82 all-time) is large enough to act
on as a working hypothesis; the `v3` 100% is on ten sessions and should be ignored until it has volume.

**What holds attention, per card.** `card_dwell`, `is_internal = false`, median (not mean — see the
caveat below), `discovery` arm ordering:

| Idx | Card | Views | People | Median dwell |
|---|---|---|---|---|
| 0 | `recognition` | 49 | 40 | 4.9 s |
| 1 | `hook` | 55 | 40 | 1.7 s |
| 2 | `reveal` | 32 | 23 | 2.3 s |
| 3 | `explanation` | 32 | 23 | 1.6 s |
| 4 | `competition` | 22 | 15 | 2.0 s |
| 5 | `value_drivers` | 15 | 8 | 1.5 s |
| **6** | **`buyer`** | 13 | 7 | **9.0 s** |
| **7** | **`valuation`** | 8 | 6 | **11.7 s** |
| 8 | `strategy` | 3 | 3 | 5.6 s |

Cards 1–5 are **skimmed at 1.5–2.3 s median** — that is scroll-past speed, not reading. The only two
cards anyone stops on are `buyer` and `valuation`, and they sit at positions 6 and 7, where only
17% and 14.5% of sessions ever arrive. ⚠ n=7 and n=6 people respectively. But the direction is
consistent with (b): the content people stop for is who-would-buy-it and what-is-it-worth, and it is
currently buried behind five cards that nobody reads.

Means are unusable here: the mean dwell for the card-0 bucket in `deck_exit` is **994 s** (16.5 min)
against a median of 6.3 s — backgrounded tabs. Median `final_dwell_ms` across all 130 deck exits is
**6.3 s**, p90 64.6 s.

**Time on page.** `time_on_page` is a milestone heartbeat (fires at 10/30/60/120 s), not a duration.
Per session, max milestone reached, `is_internal = false`:

| Page | Sessions | ≥30 s | ≥60 s | ≥120 s |
|---|---|---|---|---|
| `offmarket_report` | 128 | 68 (53%) | 42 (33%) | 25 (20%) |
| `property_page` | 132 | 76 (58%) | 53 (40%) | 35 (27%) |
| `market_metrics` | 126 | 74 (59%) | 63 (50%) | 50 (40%) |
| `article_page` | 153 | 68 (44%) | 31 (20%) | 18 (12%) |

**Time to first scroll** — the reliable engagement metric (per the bimodal-page-height caveat below).
Single-pageview sessions, `dateDiff('second', first $pageview, first scroll_depth)`:

| Page | n | p25 | **Median** | p75 |
|---|---|---|---|---|
| `property_page` | 97 | 3 s | **7 s** | 13 s |
| `offmarket_report` | 43 | 5.5 s | **10 s** | 24 s |
| `article_page` | 31 | 16.5 s | **24 s** | 29.5 s |
| `market_metrics` | 25 | 25 s | **52 s** | 108 s |

Address pages are scrolled **3–5× sooner** than any editorial or data page. The visitor arrives,
does not accept the top of the page as the answer, and starts hunting within seconds. On the property
page a quarter of them are scrolling within **3 seconds** — before the page could plausibly have been
read.

> ⚠ **Scroll-depth percentage is deliberately not used as a headline metric.** Property page height is
> bimodal (plain 1,970–3,885 px vs editorial 12,824–15,009 px), so "% reached bottom" is not comparable
> across page types. For completeness, per-session max `scroll_depth`: `property_page` n=131 → 80%
> reached 50%, 53% reached 75%, 31% reached 100%; `offmarket_report` n=52 → 77% / 71% / 50%. Those
> numbers are recorded, not interpreted.

**Deck arrival channel vs engagement** (`deck_exit`, `initial_referrer`):

| Channel | Deck sessions | Stopped at card 0 | Reached card 4+ |
|---|---|---|---|
| Google | 125 | 74 (59.2%) | 30 (24.0%) |
| Direct | 5 | 0 (0%) | 4 (80%) |

Direct arrivals engage far more, but n=5. Unusable as a result; recorded so nobody re-derives it.

### (d) What people do next — second address, or `/analyse-your-home`

Session-shape query over every session containing at least one address page:

```sql
SELECT entry_type, count() AS sessions, countIf(pv = 1) AS single_pageview_sessions,
       countIf(addr_pages >= 2) AS sessions_2plus_addresses,
       countIf(saw_ayh) AS sessions_touching_ayh, round(avg(pv),2) AS avg_pageviews
FROM ( ... GROUP BY $session_id ... )
GROUP BY entry_type
```

| Session type | Sessions | Single-pageview | 2+ distinct address pages | Touched `/analyse-your-home` | Avg pageviews |
|---|---|---|---|---|---|
| Contains an off-market page | **279** | **244 (87.5%)** | **6 (2.2%)** | **3 (1.1%)** | 1.22 |
| Contains a property page | **191** | **147 (77.0%)** | **11 (5.8%)** | **6 (3.1%)** | 1.90 |
| Contains both | 2 | 0 | 2 | 0 | 2.00 |

Person-level (across sessions):

| | Distinct people | Returned in a later session | Viewed >1 address |
|---|---|---|---|
| `/off-market/:slug` | 266 | 12 (4.5%) | 11 (4.1%) |
| `/property/:id` | 180 | 10 (5.6%) | 11 (6.1%) |

**The answer to "do they look up a second address" is: essentially no — 2.2% within a session, 4.1%
ever.** The address searcher is not browsing. They came for one house and they leave.

Where the minority who do continue actually go (other pathnames appearing in those sessions):
`/for-sale-v3` 30, `/market-intelligence/Robina` 21, `/analyse-your-home` 15, `/` 12, `/for-sale` 5,
then a long tail of `/analyse-your-home/building/<address>` and `/your-home/<address>` (i.e. the
mini-site for a *specific* address, not a list).

**`/analyse-your-home` conversion** (`is_internal = false`, 90 days):

| Step | Events | Distinct people | % of AYH viewers |
|---|---|---|---|
| `analyse_home_page_view` | 264 | **225** | 100% |
| `analyse_home_address_submit` | 20 | **11** | **4.9%** |
| `analyse_home_submit_success` | 16 | 9 | 4.0% |
| `analyse_abandoned` | 6 | 3 | 1.3% |
| `analyse_home_submit_error` | 3 | 2 | 0.9% |
| `analyse_home_currently_listed` (guard fired) | 1 | 1 | 0.4% |

### (e) What people type

`address_search` fires **per keystroke**, so event counts are not attempt counts. 184 events in the
window, **all** `is_internal = false`, from **16 distinct persons / 21 person-sessions**.

Where the search box was used:

| Path | Events |
|---|---|
| `/analyse-your-home` | 167 |
| `/analyse-your-home/building/<address>` | 10 |
| `/property/17-pitta-place-burleigh-waters` | 4 |
| `/your-home/<address>` | 2 |
| `/analyse-your-home/` | 1 |
| **`/off-market/*`** | **0** |

⚠ **Zero address searches originate from an off-market page — the deck has no search box.** Given
(d), that is not obviously a loss (people do not want a second address), but it means we have **no
first-party evidence at all** about what an off-market visitor would type if given the chance.

**What they typed** (terminal query of each keystroke cluster, deduplicated). These are verbatim:

| Date | Terminal string typed | Recorded `result_count` |
|---|---|---|
| 2026-06-07 | `7B/52 G` | — |
| 2026-06-16 | `18 silvabank ` | — |
| 2026-06-19 | `3 emerald place murwillumbah` | — |
| 2026-06-19 | `38 riverwalk drive robina` | — |
| 2026-06-24 | `41 pring street ` (also `41 pring streey`) | — |
| 2026-07-15 | `3 Woodland Drive Reedy Creek ` | — |
| 2026-07-15 | `18 collingw` / `16 collingw` / `18 calool` / `37 ` / `135` | — |
| 2026-07-16 | `15 bentleigh ` (also `15 bent`, `15 bwn`) | — |
| 2026-07-16 | `1 Dotteral drive 4220` (also `1 doller`) | — |
| 2026-07-17 | `52 Atlantis boul` | — |
| 2026-07-20 | `4/44 Frascott Avenue ` | — |
| 2026-07-24 | `10 Seville street` | — |
| 2026-07-24 | `43 curru` / `1 dabc` | — |
| 2026-07-27 | `41 quamn` (41 Quambone Street, Worongary) | — |
| 2026-07-28 | `20 GLEN EAG` | — |
| **2026-07-30** | **`120 Gleneagles Drive, Robina`** — see below | — |
| 2026-07-30 | `69 port jackson boule` | 1 |
| 2026-07-31 | `819 Legend Trail, Robina` and `819-legend-trail-robina` | 1 |
| 2026-07-31 | `70 Burleigh Street, Burleigh Waters, Qld 4220` | 2 |
| 2026-08-01 | `6 avoce` | 2 |
| 2026-08-03 | `120 ` | 8 |

Two things stand out.

**1. One visitor fought the search box for over an hour and appears never to have won.** On
2026-07-30 a single person produced ~50 `address_search` events across three sessions
(00:54, 01:00, 01:57) trying to reach one address, cycling through at least fifteen spellings:
`120 evans drive` → `120 gl` → `120 Gel` → `120 Gen` → `120 leneages drive ` → `120 gleneages drive `
→ `120 Gleneages rive ` → `120 Gleneages Drive, Robi` → `120 Gleneages Drive, Robin` →
`120 Gleneages Drive, Robion` → `120 Gleneages Drive, Robina` → `120 Gleneasgle` →
`120 Gleneagles drive, ` → `120 Gleneagles drive, r` → `120 Gleneagles drive, ri` →
`120 Gleneagles drive, Robina` → `120 Gleneagles Drive`. No `result_count` was recorded on any of
them. (Separately, on 2026-07-28 another person typed `20 GLEN EAG` and stopped.) The address is
`120 Glen Eagles Drive, Robina` — **two words**, which is exactly what the visitor never tried.
This is the single most vivid piece of first-party evidence in the dataset: a person who wanted one
specific house badly enough to come back three times, and the product could not get them to it.

**2. Roughly a third of typed addresses are outside the three target suburbs.** Murwillumbah (NSW),
Reedy Creek, Worongary, Clear Island Waters — plus, from the lead form, Mudgeeraba. People do not
know or care about our coverage boundary; they arrive with an address and expect it to work.

⚠ **`result_count` is only populated on 5 of 184 events** (values 1, 1, 1, 2, 2, 8). It is therefore
**not** possible to claim "X% of searches returned nothing" — the field is absent, not zero. What can
be said is that only five attempts in three months are recorded as having produced a result set.

---

## 2. Samantha chat logs — the source is empty

**There are no real-visitor chat questions to report. Not "few" — none.** Established by:

1. **`scripts/samantha_chat/service.py` never persists a conversation.** The whole record of a turn
   is a Telegram message to Will's private chat (`_telegram(...)`, lines 462–471, containing
   `Them: {last[:300]}` / `Her: {reply[:400]}`). There is no MongoDB write, no file log, no PostHog
   capture of message text. Telegram's Bot API cannot read a bot's own outbound history, so those
   messages are not recoverable programmatically.
2. **The systemd journal records timestamps and status codes only** — `POST /chat HTTP/1.1 200`, with
   no message text. Total successful turns since the 2026-08-04 launch: **27** (19 on 2026-08-04,
   8 on 2026-08-05). The 2026-08-04 traffic is interleaved with `systemd` restart lines every few
   minutes, i.e. it is Will's own build-and-verify loop, not visitors.
3. **PostHog holds zero break-glass or Samantha events.** `BreakGlass.tsx` imports `phCapture` and
   passes dynamic event names through, but querying every event name recorded since 2026-08-04
   returns 33 event types and **not one** matches `chat`, `glass`, `samantha`, `ask` or `question`.
   Either nobody has pulled the lever on production, or the instrumentation is not landing. **This is
   a live instrumentation gap and should be fixed regardless of the redesign** — the feature was
   shipped explicitly "to find out whether anyone engages at all", and right now the only way to find
   out is Will reading his phone.
4. **No public chat log exists elsewhere in MongoDB.** All 207 `system_monitor` collections were
   enumerated. `chat_agent_usage` (23 docs) and `voice_agent_conversations` (3 docs) are Will's own
   internal ops assistant — sample `user_text` values are `"hi, just testing the usage tracker"`,
   `"I need cheap accommodation on the Gold Coast tonight. Can you find it?"`,
   `"List the files in the voice-agent directory and tell me how many there are."` Not visitors.
   `agent_messages`, `ceo_chat_messages`, `builder_chat_messages` are internal agent traffic.
   `search_paa_questions` (37,350 docs) is scraped Google "People Also Ask" — third-party, not
   first-party, and out of scope for this document.

### The one piece of real visitor free text we do have (n=1)

`system_monitor.website_feedback`, received 2026-07-27, unsolicited email from a visitor who signed
himself Richard. Verbatim, in full:

> "I just stumbled across your website and I just had to email you. I have never seen more of an
> excellent use of AI! Seriously. I am so impressed with how you've built it. This is one of the most
> awesome uses for AI I have seen and it really will make a difference for people looking for
> properties. Just had to come and tell you and give you some feedback. I truly am impressed. I hope
> it becomes more mainstream and grows to where the public can utilize your website to inform them
> better on purchases and selling. Good luck will. Well done mate. Just an FYI though... Your /ops
> endpoint is visible to public. The google, facebook, and posthog trackers are on every page without
> getting consent or privacy banners, against Australian policy...especially because of the session
> recording and heatmaps. There are actually 2 different fbook ids. Schema uses one and the footer
> uses a different one. Nevertheless, good work. Look forward to seeing the website finessed a
> little bit. **Making it a little easier to view any property across Australia visible and searchable
> instantly. Having reports prepared for every realestate.com.au listing or something. And make that
> your home page. That's the best part of your website.** Regards, Richard"

**n=1. It is one person's opinion and carries no statistical weight.** It is included because it is
the only unprompted free-text statement of want from a real visitor that exists anywhere in
first-party data, and because it independently converges with §1(e): the thing a visitor wants from
Fields is **an address, resolved instantly, with a report on it** — and the coverage boundary is
experienced as a defect.

---

## 3. What we still cannot tell from this data

Stated plainly, so none of it gets inferred by accident later.

1. **Why 47–57% of deck visitors stop on card 0.** We can measure that they stop. We cannot
   distinguish "the card answered their question and they left satisfied" from "the card did not look
   like an answer and they bounced" from "they did not realise there was a card 2". The
   `deck_scroll_nudge` event exists (n=2) but has no volume. **A single well-placed exit question, or
   session replay reviewed on card-0 exits, would settle this and nothing in the current data can.**
2. **Whether the `discovery` vs `ladder_dark` first-card gap is real.** 71.7% vs 32.9% advance on
   n=60 / n=82, but the arms ran over different (only partly overlapping) date ranges and we have not
   verified the assignment is randomised per visitor rather than per deploy. It is a strong lead, not
   a result.
3. **What an off-market visitor would search for**, because the off-market page has no search box and
   emitted zero `address_search` events. All 16 searchers in the dataset came via
   `/analyse-your-home`, a page with a completely different arrival intent.
4. **Whether address searches succeed.** `result_count` is populated on 5 of 184 events. We cannot
   compute a success rate, only observe one person's hour-long failure.
5. **What visitors ask in their own words.** Samantha persists nothing (§2); the FAQ-click evidence is
   3 people. We have no corpus of real questions. The closest first-party proxy is which FAQ
   *accordion* got opened, which is a menu choice, not a question.
6. **Whether the deck's card ordering is causal.** `buyer` and `valuation` hold attention (9.0 s and
   11.7 s median) while cards 1–5 are skimmed at 1.5–2.3 s. We cannot tell whether those cards are
   intrinsically more interesting or whether the ~15–20% of people who get that deep are simply a
   self-selected, more-engaged group. Moving them earlier is a testable hypothesis, not a conclusion.
7. **Anything about the visitor's relationship to the address.** Owner, neighbour, prospective buyer,
   valuer, nosy local — nothing in the data distinguishes them. The `offmarket_menu_*` chips are our
   only direct probe and have fired **9 times total** (`sell` 6 / 4 people, `market` 1, `else` 1,
   `surprise` 1). That 6-of-9 lean toward "sell" is far too small to describe as a finding.
8. **Off-market rates over a normal period.** Every off-market number rests on **17 days**
   (2026-07-20 onward), overlapping the page's own launch and iteration. Card-level data is narrower
   still (`card_viewed` from 07-25, `deck_exit` from 07-29).
9. **Mobile vs desktop.** Not segmented in this pass. Given that time-to-first-scroll is 3–7 s on
   property pages, device split may be doing real work in these numbers and should be the first cut
   added to any follow-up.
10. **Whether "no click" means "no engagement".** The deck advances by scroll as well as by button,
    so the 86% no-click figure understates interaction. `card_viewed` (152 sessions) is the better
    engagement denominator and is the one used for the funnel.

---

## Appendix — query helper

All HogQL in this document was run through:

```python
import json, os, urllib.request
KEY = os.environ['POSTHOG_ALL_ACCESS_KEY']      # from Fields_Orchestrator/.env
PID = '348370'
def q(sql):
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode()
    req = urllib.request.Request(
        f"https://us.posthog.com/api/projects/{PID}/query/", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    return d['columns'], d['results']
```

Note: `OFFSET` is rejected for personal-API-key queries — use keyset pagination on `timestamp`.
