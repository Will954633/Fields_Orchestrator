# 20_Agent_Finder — a LocalAgentFinder competitor, Southern Gold Coast

**Live prototype:** https://vm.fieldsestate.com.au/concepts/agent-finder/index.html
(served by symlink `/home/fields/concept-previews/agent-finder` → `prototype/`; no build step)

Rebuild the data: `python3 20_Agent_Finder/build_data.py` → `prototype/data.json`

## What it is

LocalAgentFinder's funnel is: pick intent → property details → address → **contact gate** →
"we're searching" → results. This prototype mirrors that funnel exactly, so the two can be
compared like for like, and then diverges completely at the results screen.

LAF's results are a lead-broker product: agents pay to appear, and your details are the thing
being sold. Ours is a **record** — what each agent actually sold, from our own data — and the
seller sorts it themselves.

## The data

Two layers with very different depth, kept separate on purpose:

| Layer | Source | Depth | Carries |
|---|---|---|---|
| **Agent** | `Gold_Coast.<suburb>` docs, `listing_status: "sold"` | 3,081 sold docs → **220 agents** with ≥3 sales in 36mo | individual `agent_name`, `agency_name`, `sold_date`, `sale_price`, `property_type`, `days_on_market` |
| **Agency** | `scraped_data.property_timeline[]` sold events | 5,734 events in 24mo (**70,333** back to 2016) | `agency_name`, price, DOM — **no individual agent** |

⚠ Every numeric field on the sold documents is a **string** — `"$1,520,000"`, `"51"`, `"4"`.
`build_data.py` parses; it never assumes.

Coverage: 26 suburbs, Robina → Springbrook. 93 agents have sold a house in Burleigh Waters,
114 in Robina.

## The legal design constraint — read before changing the results page

`memory/on_market_buyer_research_2026-08.md`: **POA 2014 Sch 2 ss 207–209 bind us on
representations about the value of property — reverse onus (s 209(5)), 14-day compelled
substantiation (s 217).** RealAs drew two cease-and-desists for naming "most inaccurate
agents". Homer publishes comparable data unchallenged by framing it as neutral arithmetic
between two published markers.

So this page is built to that line, deliberately:

- **No score, no grade, no composite, no "best agent".** The seller picks a sort; we order
  by it and say so in the subheading. Order is not a verdict.
- **No claim any agent will get you more.** The method panel says the opposite explicitly:
  a higher median means more expensive streets, not a better agent.
- Every number is a count or a median of published transactions — arithmetic, not opinion.

**If anyone adds a ranked leaderboard with scores, that changes the legal position and needs
sign-off first.** It is not a styling decision.

## Sample size is handled in the ordering, not just in a warning

The first build sorted by median days on market and put an agent with **one** timed sale and
a 2-day median at the top. A warning underneath does not fix that — the ranking itself was
rewarding ignorance.

Each sort now declares what it needs to be comparable (`NEEDS` in `index.html`): the speed
sort needs ≥5 timed sales, the price sort ≥4 disclosed prices. Agents below the bar are
**held out of the ranking and shown beneath it, labelled**, never silently dropped and never
silently promoted. Counts of what is shown vs what exists are stated on screen.

## Disclosed on the page

- Co-listed sales are credited to **both** agents, so counts sum above transactions.
- Our sold capture **misses a material share** of transactions (Domain ≈53–66% of PropRadar) —
  counts are a floor, never a total.
- DOM is recorded on only **52%** of sales; missing shows as "not recorded", never imputed.
- Only "sales in your suburb" is suburb-specific; medians are region-wide across 26 suburbs,
  because a suburb-level median would rest on too few sales for most agents.

## Verified (headless, 2026-08-13)

Full funnel driven end to end: contact gate correctly disabled → enabled, searching sequence,
results render, all four sorts re-order, sales tables expand, agency context present.
**0 console errors, 0 page errors, no mobile horizontal overflow at 390px.**
Edge cases: empty result (Tugun/Townhouse), single result (Springbrook/Land), 93-agent result.

## Not done

- **Individual agent photos/profiles.** We hold none — `db_fields.py --find "agent photo profile"`
  returns nothing. Domain's agent pages (e.g. `/real-estate-agent/mitch-harrop-2028581/`) would
  supply them, but the VM IP is Akamai-blocked and this needs Bright Data. Cards use initials.
- **Rent path.** "Rent out" is accepted at step 1 but results are sale-only.
- **Address is not geocoded** — the suburb dropdown drives everything; the address field is
  captured but unused.
- **Not scheduled.** `build_data.py` is manual. If it is ever put on a cron it must be wrapped
  in `job_status.job_run()` per CLAUDE.md Rule 7, with the zero-agent assertion (already
  present as a `raise`) as its Rule 7b outcome check.
- No legal sign-off has been obtained.
