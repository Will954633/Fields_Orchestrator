# B — Reddit: Stated Motivations Behind Looking Up a Specific Address

**Research question:** what does someone searching their own address (or a specific address) on Google actually want to know?
**Purpose:** inform the redesign of Fields' `/off-market/:slug` address pages.
**Compiled:** 2026-08-06 (AEST). All quotes verbatim from Reddit post **titles** and **bodies** (never comments — the corpus holds no comment text).

---

## 1. Method — exactly what was queried, and what went wrong

### Source 1 — existing MongoDB corpus (primary)

`system_monitor.search_reddit_posts` on the Fields Cosmos instance.

| | |
|---|---|
| Documents | **4,349** |
| Subreddits | r/AusFinance 2,039 · r/AusProperty 1,713 · r/GoldCoast 597 |
| Fields used | `title`, `selftext`, `subreddit`, `score`, `num_comments`, `permalink`, `created_utc`, `search_term` |

**⚠ Date-field correction (important).** The `date` field is the **ingest date**, not the post date. `created_utc` is the true post date. Sorting by `date` gives a false range of 2026-03-14 → 2026-08-04. Sorting by `created_utc` gives the real picture:

- **3,496 posts (80%) were genuinely posted in 2026** — collected live via `feed_new` / `feed_hot` / keyword searches.
- **853 posts (20%) are a historical backfill** (`search_term = "pullpush_top"`) of top-scoring posts spanning **2012–2025** (2025: 404, 2024: 174, 2023: 128, 2022: 57, 2021: 40, ≤2020: 50).

Every quote below is dated by `created_utc`. Where a quote is from the backfill, the date shows it (e.g. 2021, 2024).

**⚠ Body truncation.** `selftext` is capped at **500 characters** (p75 = 500, max = 500). Roughly a quarter of bodies are cut mid-sentence. Quotes are verbatim up to that cut; where a quote ends mid-word/mid-sentence this is marked `[…truncated at 500 chars in corpus]`. No text has been paraphrased, joined, or completed.

**Excluded:** 61 posts with `[deleted]`/`[removed]` bodies, 72 with empty bodies, 327 whose body is only the RSS boilerplate `submitted by /u/x [link] [comments]` (title-only posts — these are still usable as *title* evidence and a few are quoted as titles).

**How it was searched.** All text processing in Python (no shell `grep` — per VM safety rule). Two passes:
1. 20 broad theme regexes over `title + selftext` → candidate sets.
2. 13 tightened persona regexes (documented in `final_counts.py`) → the frequency table in §3. Every candidate for the low-volume personas was read individually; high-volume sets were sampled and filtered for false positives (e.g. "land tax" polluting a land-valuation regex, "multiple agents" matching a call-centre complaint).

### Source 2 — live Reddit RSS (supplementary)

Reddit's JSON API is unavailable from this VM. RSS works but **rate-limits aggressively**. Pull run at 1 request / 6 s with a browser User-Agent, aborting after 3 consecutive 429s.

**Result: roughly half of all requests returned HTTP 429.** Exact per-URL outcomes are logged. Summary:

| Endpoint type | Requested | 200 OK | 429 |
|---|---|---|---|
| `/r/<sub>/new.rss` + `/hot.rss` (7 subs) | 14 | 6 | 8 |
| `/r/<sub>/search.rss?q=…` (3 subs × 12 terms) | 36 | 15 | 21 |
| **Total** | **50** | **21** | **29 (58%)** |

The pull completed without ever hitting 3 consecutive 429s, so it ran to the end rather than aborting. It yielded **1,470 entries / 1,336 unique posts**. Full per-query outcomes in §6.

Subreddits attempted: AusProperty, AusFinance, GoldCoast, australia, brisbane, AusHomeLoans, AusRenovation.
**r/AusFinance's own feeds 429'd on both attempts** — the single largest subreddit in the corpus could not be refreshed live.

**One advantage of RSS over the corpus:** RSS `<content>` carries the **full post body, untruncated** — unlike the 500-char cap on `selftext` in MongoDB. Several of the most valuable quotes in this document (§P6 "Variation in property estimates", §P3 "First time seller needing opinions") are complete only because they came from RSS.

**`api.pullpush.io` was NOT used.** It has explicitly blocked this VM ("does not provide free scraping resources for agents"). No attempt was made to evade that block.

### The single biggest caveat

**This corpus is topic-sampled, not a random sample.** It was assembled by keyword searches (`interest rates property`, `buy house gold coast`, `property market crash`, `sell house queensland`, `house prices falling`, `should I buy`, `should I sell`, `gold coast real estate`, `property valuation`, `robina`, `burleigh waters`, `varsity lakes`, …) plus subreddit feeds. It over-represents transaction-adjacent and market-commentary talk and under-represents idle, low-stakes behaviour. **The frequency numbers in §3 are indicative of relative emphasis within this sample only. They are not population estimates and must not be quoted as "X% of Australians".**

---

## 2. Headline finding (read this before the personas)

**Almost nobody on Reddit narrates the search itself.** Across 4,349 corpus posts plus 1,336 further posts pulled live, only **one** post describes typing an address into Google (r/AusProperty 2026-07-12 — and the address belonged to the poster's *parents*). See §4 for the full negative list.

But the live RSS pull did find the *reaction* people have once they are on such a page, and it is consistent: **they don't believe the number.**

> "just wondering how much stock I should put in to the estimated value of my property according to Real Estate app? […] Is this reliable estimate because it just seems... unbelievable."
> — r/AusProperty, 2026-01-18 · https://www.reddit.com/r/AusProperty/comments/1qgnbql/real_estate_app_property_price_accuracy/

> "The lowest - $382k, highest $704k. […] When brokers ask me what my house is worth, I have no idea, given the range of estimates."
> — r/AusProperty, 2022-03-31 · https://www.reddit.com/r/AusProperty/comments/tswx38/variation_in_property_estimates/

What people *do* say is what they were trying to *find out*. The address lookup is never the goal — it is a step inside a decision. Every persona below is defined by the **decision it serves**, because that is the only thing the data actually evidences.

The strongest recurring shape in the data is this: **someone has been given a number by an institution (a bank, an agent, a website), does not trust it, and goes looking for a second number to check it against.** That pattern accounts for the three largest personas (P1, P2/P3, P6). An address page's job, on this evidence, is to be the **second opinion** — not the first number.

---

## 3. Personas / jobs-to-be-done

Frequency = number of distinct posts in the 4,349-post corpus matching that persona's regex, after manual false-positive review. Read as **indicative weight, not prevalence**.

---

### P1 — The Equity Checker *(strongest evidence: ~115 posts)*

**Underlying question:** *"What number will a lender accept for my house — and is it lower than what the market says?"*

This is the largest single cluster in the corpus and the one with the most specific, repeated, unmet need. These people are not selling. They want to borrow, refinance, or drop their LVR. The gap between the *market* number and the *bank's* number is the thing they are trying to close, and they explicitly reach for public listing-site estimates to do it.

> **"Bank Valuation"** — r/AusProperty, posted 2026-02-10
> "Anyone else had an experience where the bank undervalued their property? And not by just 1-3% but by a lot? Trying to withdraw equity from current PPOR (will become IP) for purchase of next PPOR, and bank has given us an absolute pisstake of a valuation, 8-10% below what I was expecting. Interestingly enough, yesterday, an apartment in our building - IDENTICAL to ours (just without the balcony, so likely inferior) sold for $100k more than our recent bank valuation. The sale price is also in line" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1r1elwh/bank_valuation/

> **"PSA for mortgage holders looking for better rates."** — r/AusFinance, posted 2026-05-21
> "A trick I do not see mentioned here often to potentially get a slight discount on your home loan rate is the following: Check the upper end value of your home on sites like domain and property. Call your bank and request an updated Automated Valuation Model (AVM) for your home. Try to hit the maximum number the bank will accept(usually top price on domain or property). If you are successful you may have changed your LVR(loan to value) which may in turn allow you to negotiate better rates for tha" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusFinance/comments/1tjew40/psa_for_mortgage_holders_looking_for_better_rates/

*This is the most operationally useful quote in the entire research set: it describes a specific, deliberate workflow in which a public address page's top-of-range number is used as ammunition against a bank.*

> **"Calculating usable equity"** — r/AusFinance, posted 2025-05-03 (backfill)
> "Before I go waltzing into my bank to discuss, I was hoping to get myself a bit more knowledgeable about how home equity works. […] My question is, how does the bank go about determining the current market value of the home in figuring out usable equity. Do they stray on the conservative side? What do they base i" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusFinance/comments/1kdh4e2/calculating_usable_equity/

> **"Bank Valuations"** — r/AusProperty, posted 2026-04-12
> "Anyone have recent experience with bank valuations? How far off market rates are they likely to come back? We did a refi not long ago and nominated a fairly conservative valuation which was accepted without question. We're now attempting to access equity for investment and have again gone conservative compared to the market (15-30% below sold properties in the area with smaller land size) but this one has triggered a valuer coming out. Any tips/tricks/thoughts on ensuring the valuation is as com" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1sjbk12/bank_valuations/

> **"How do banks value properties?"** — r/AusFinance, posted 2024-12-05 (backfill)
> "We've purchased a property and despite having loan pre-approval from the bank they need to value the property before final approval. What does this mean? Do they physically send someone to the property to take a walk around or do they just plug the property price into Corelogic and get a valuation?"
> https://www.reddit.com/r/AusFinance/comments/1h6vzln/how_do_banks_value_properties/

> **"Bank valuation lower than expected but mid renovation. Any experience with this?"** *(title)* — r/AusFinance, posted 2026-05-01
> https://www.reddit.com/r/AusFinance/comments/1t0k7tu/bank_valuation_lower_than_expected_but_mid/

> **"What are my options to access equity without selling?"** — r/AusFinance, posted 2026-03-21
> "I still have a small mortgage left on my home and I'm on DSP. I can manage my bills and repayments, but I've got no extra money for maintenance that needs to be done on the house. […] I don't really want to sell because the housing market feels overwhelming, so I'm just trying to figure out what my options are to access some equity and sta" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusFinance/comments/1rzkl1f/what_are_my_options_to_access_equity_without/

**From live RSS (r/AusHomeLoans, a subreddit absent from the corpus):**

> **"How accurate are Commbank's online estimates?"** — r/AusHomeLoans, posted 2023-07-13
> "Long story short I bought last year with LMI and haven't been able to refinance, but the house has been improving in value over time. My lender charges a fee for a new valuation and other lenders are close to but not quite at 80% LVR with their estimates. Commbank, however, has a significantly higher estimate at around 70% LVR which, while I'm not expecting to get that much, gives me more than enough room to refinance and negotiate my rate down. How accurate is the online Commbank tool? I'm thinking of refinancing with Unloan (who uses Commbank's data)."
> https://www.reddit.com/r/AusHomeLoans/comments/14yeoo1/how_accurate_are_commbanks_online_estimates/

> **"How do you actually track equity across multiple properties?"** — r/AusProperty, posted 2026-04-13 *(via live RSS; full body)*
> "Currently own one IP and am in the process of working towards a second. […] **Right now I'm pulling loan balances manually and using Domain estimates to get a rough equity figure. It works, but it's not exactly a clean picture.** Wondering how people manage things like: • Total equity across multiple properties (not just individual snapshots) • LVR per property vs. blended LVR • How equity is trending over time • Knowing when you've got enough equity to pull the trigger on the next one Are spreadsheets still the go-to for most people here, or has anyone found something better? **And how often are you actually updating your property valuations?**"
> https://www.reddit.com/r/AusProperty/comments/1sk6uf2/how_do_you_actually_track_equity_across_multiple/

> **"Do banks charge you for desktop valuations?"** — r/AusProperty, posted 2023-08-24 *(via live RSS)*
> "As the subject says, curious to know if banks charge you for desktop valuations? I am currently with ANZ, so say **I call them and ring around other banks to see what they value my property at** as I understand some lenders woudl value differently"
> https://www.reddit.com/r/AusProperty/comments/15zmfvi/do_banks_charge_you_for_desktop_valuations/

**What the page owes them:** a defensible **range with its top end visible**, the comparable sales the range is built from, and enough methodology to be cited to a lender. A single point estimate is useless to this persona — they need the top of the band and the evidence under it.

---

### P2 — The Pre-Sale Sizer-Upper *(strong evidence: ~51 posts)*

**Underlying question:** *"What would my place realistically get — before I let an agent tell me?"*

They are 3–18 months from listing, have not signed anyone, and are trying to form an independent expectation. Several are explicit that they do not know how to establish a value at all.

> **"Should I sell property off market or go to market?"** — r/AusProperty, posted 2026-02-26
> "I've decided to sell my house, and at the same time, a friend of mine has shown interest in buying it. He has asked me to provide a price, but I'm unsure about the best way to determine a fair market value. What is the most reliable method to value the property? Should I engage a real estate agent first and have the sale go through the agent, or would it be reasonable to offer my friend a discount equivalent to the commission I would otherwise pay to the agent? Also, would it be better to take t" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1rexmsg/should_i_sell_property_off_market_or_go_to_market/

> **"Selling my house in Perth"** — r/AusProperty, posted 2026-03-24
> "Sitting on 4x2 450sqm in Bibra lake right now and really want to sell my house. I've wanted to sell for months but couldn't convince my partner and now I finally have. We've only been in it 18 months but have done a little bit of work to it. Are buyers still out there aggressively at the moment for Perth? **Have been told different prices by different agents** and are going with the price more towards the low end of the suggested range as I think it's fair. Haven't committed to an agent yet, however" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1s2bfbq/selling_my_house_in_perth/

> **"Best way to sell a house that needs work?"** — r/AusProperty, posted 2026-02-26
> "I have a standard 90s house in a northern suburb of Melbourne with a backyard. It needs work and upgrades, but I can't afford any maintenance. I'm not at pension age and my income only just covers everyday living. I've had real estate agents value it, but the stress of dealing with this is too much for me as I'm unwell. I feel like selling and getting out might be my only option, ideally off-market, but I don't know what my best path is. Should I be speaking to someone other than regular real es" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1rf5e66/best_way_to_sell_a_house_that_needs_work/

> **"House improvements prior to selling"** — r/AusProperty, posted 2026-06-15
> "We're looking to sell our PPOR in the next 12 months for various reasons, but now faced with the intimidating task of trying to get it ready for market. This is our first home, so we no experience selling. Other than the usual repaint, is there any advice/wisdom you can share on how to best prep a house for sale?"
> https://www.reddit.com/r/AusProperty/comments/1u6gk07/house_improvements_prior_to_selling/

> **"Privately selling"** — r/AusProperty, posted 2024-06-27 *(via live RSS)*
> "I want to sell my garden apartment. **My neighbour is keen to buy**, has anyone sold a property privately? What process should I take and anything to consider? **I obviously want to get as much for it as possible, how should I come up with the price?** Do I pass on any discount for avoiding agent fees etc. would love some advice"
> https://www.reddit.com/r/AusProperty/comments/1dpogbh/privately_selling/

**What the page owes them:** an honest range they can hold in their head *before* the first listing presentation, plus the comparable set so they can tell whether an agent's later number is anchored to anything real.

---

### P3 — The Agent-Number Sceptic *(strong evidence: ~39 posts)*

**Underlying question:** *"The number I was given — is it real, or is it a tactic?"*

This is P2's twin but it fires *after* someone has been given a figure. It is the most emotionally charged cluster in the corpus. The distrust is specific and structural: sellers believe agents inflate to win the listing and deflate to win the sale.

**⭐ The Gold Coast case that contains almost every persona at once** — an owner on Fields' own patch, holding four conflicting numbers for one address:

> **"First time seller needing opinions"** — r/AusProperty, posted 2025-12-09 *(via live RSS; full body, not truncated)*
> "I'm selling my first home, a 2 br 2 bath 2 carspace house 125m2 on small block of land (~420m2) **on southern end of gold coast (border)**, great ocean views, good condition brick tile - **bank valuation came back at 930K** a couple of weeks ago. **Identical house but with no view, 260m2 land, no large covered outdoor area, no carport in same complex went for 870 earlier this year. Agent said (after discussions and before valuation) that they expected 925k** .. but since then I've repainted, cleaned up a lot, redone gardens, got a few things done. And valuation was more than that. **Guide is currently on it up to 950k.** Now first open home on Saturday resulted in 3 offers - one at 885, and now two at 900. **Agents are saying the two higher ones are good offers and consider taking them but that just seems crazy given that my place is worth a lot more than the similar one in land and improvements/extras. Plus I have the amazing view and it had none.** Anyway - as its my first time selling I'm freaking out a bit. If I turn these down, given only one open home and the valuation, then all the what ifs are going through my head. I'm older, so I am concerned that if I screw this up, I screw up things for myself going forward."
> https://www.reddit.com/r/AusProperty/comments/1pi2vaf/first_time_seller_needing_opinions/

*Southern Gold Coast. Four numbers for one address — bank $930K, agent pre-appraisal $925K, guide up to $950K, market offers $885–900K — plus one named near-identical comparable at $870K that the owner is **manually adjusting** for view, land size, carport and outdoor area. That manual adjustment is precisely Fields' comparables method, performed by an anxious amateur at the worst possible moment. Note the closing line: the fear is not about money, it is about **being the person who got it wrong.***

> **"Setting a reserve - please help."** — r/AusProperty, posted 2024-11-06 (backfill; score 2, 30 comments)
> "Help! I don't fully trust my REA so unsure what to do about setting a reserve. Our REA originally estimated our place as worth 800-900k (presumably to get us to pick him) Opens started and his tactic was to tell people 700-800k to get max people in and then increase the price as the campaign went on because of "interest". There was a comparable sale in our building of 775, but the place is smaller and less updated / renovated. We've also had an offer of 790 which our agent told us to refuse" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1gl78fv/setting_a_reserve_please_help/

> **"Upsizing to 3x2 house"** — r/AusProperty, posted 2026-06-07
> "Hey everyone, Thinking of selling my 1 bedroom 1 bathroom apartment in WA to get a larger 3 bedroom 2 bathroom house. My agent just appraised the unit at $519k starting price. 1 Is now a good time? […] 2 What would a realistic buyer offer? **Agent appraisals can be optimistic.** If it's valued at $519k, what are buyers actually paying in this climate to secure a" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1tz5npn/upsizing_to_3x2_house/

> **"Left feeling flat after a property appraisal, looking for some perspective"** — r/AusProperty, posted 2026-07-08
> "Had a local REA come out to have a look at our place because we're considering downsizing. We have a young family and live on 10 acres in Gippsland, Victoria. We absolutely love it here, but if we sold and bought a smaller property in town we'd be mortgage-free at 31. Our current house is 3 bedrooms, and we're starting to feel like we really need 4 bedrooms or at least a study. The agent had a quick look around and a short chat, then basically said our place is worth about what it was 4 years ag" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1uqlauj/left_feeling_flat_after_a_property_appraisal/

*Note the mechanism here: a **20-minute walkthrough** produced a number that landed badly, and the owner went to strangers on the internet for a second opinion the same day. That is precisely the moment an address page can intercept.*

> **"Don't use the real estate agents price guide"** *(title-only post)* — r/AusProperty, posted 2026-06-29
> https://www.reddit.com/r/AusProperty/comments/1uj9029/dont_use_the_real_estate_agents_price_guide/

> **"Went to a house auction. The realestate agent was adement the house would sell around 1.7 mil. Later sold for over 2 mil. Would he have known and was just dragging us along? I knew it was too good to be true, but he kept insisting it would be 1.7."** *(title-only post)* — r/AusProperty, posted 2025-02-07 (backfill)
> https://www.reddit.com/r/AusProperty/comments/1ijr7mp/went_to_a_house_auction_the_realestate_agent_was/

> **"Caught out a Real Estate Agent's Lie"** — r/AusProperty, posted 2023-02-23 (backfill; score 90, 106 comments)
> "Trying to buy a property under private treaty in Sydney, I have a paper trail of 16 bids, of which I was 5. The final offer that was "made" (which I pulled out on as it was exactly my limit) is higher than the amount the house sold for the very next day. What should I do here? I have evidence of text messages that are obvious lies."
> https://www.reddit.com/r/AusProperty/comments/119r2tt/caught_out_a_real_estate_agents_lie/

**What the page owes them:** transparent method and named comparables. The value is not the number — it is that the number can be *audited*. This persona is the strongest argument for showing the working, not just the answer.

---

### P4 — The Renovation Payback Calculator *(moderate evidence: ~21 posts)*

**Underlying question:** *"If I spend $X on this house, do I get it back when I sell?"*

Almost always framed as ROI, almost always tied to a planned sale, and often already anchored on a listing-site estimate.

> **"Selling in Perth is it worth doing an IKEA kitchen Reno"** — r/AusProperty, posted 2026-04-13
> "Looking to sell my PPOR in 12 months but the kitchen original from 2005 is in desperate need of a renovation. I've already forked out my capital on a new house but can probably find 30k for an ikea renovation **but only if I'd make my money back or more on sale.** Looking for opinions on whether it's worth it. Average spec home 4x2 but walking distance to a train station and about 10km from the city centre **currently valued around 1.4M on realestate.com.** Possibly future owners may just want to do the" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1sket8s/selling_in_perth_is_it_worth_doing_an_ikea/

*This is the only post in the corpus that both (a) states a listing-site estimate for their own home and (b) uses it as the baseline for a spending decision.*

> **"Thinking of selling PPOR – what are the best ROI cosmetic upgrades before listing?"** — r/AusFinance, posted 2026-02-17
> "I'm considering selling my PPOR as part of a longer-term move to a "forever home". The house has been very… lived in. Two breastfed kids under 3 (think white stains) and a cat that's scratched up sections of carpet, and walls that are pretty dinged up from general chaos. Structurally it's fine, but cosmetically it's definitely showing wear. **From a purely financial/ROI perspective (not "make it beautiful for ourselves"), what are the upgrades that typically add more value than they cost?** My curre" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusFinance/comments/1r7m6m3/thinking_of_selling_ppor_what_are_the_best_roi/

> **"To fix up or not fix up"** — r/AusProperty, posted 2026-07-08
> "Hi, I have a property until only recently I am considering selling. It's a 1968 double brick, 3 bed, 1 bath, 2 car on 645m². It's in good condition, has a new bathroom, needs a paint job and probably refinishing the polished floors. It's in a sought after area, Mansfield, and has a good high school catchment. The thing is, most houses in this area are being bought as knockdown rebuilds. I am torn between what to do regarding the paint and floors. Are the p" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1uqebno/to_fix_up_or_not_fix_up/

**What the page owes them:** attribute-level sensitivity — what a comparable with/without the renovated kitchen actually sold for. A single headline number answers nothing here.

---

### P5 — The Comparable Hunter *(strong evidence: ~53 posts)*

**Underlying question:** *"What did similar properties actually sell for, and is this asking price defensible?"*

Mostly buyer-side and pre-offer. Note that the complaint is not "I can't find any data" — it is that the *advertised* number and the *sold* number diverge, so people go hunting for the sold number specifically.

> **"I'm getting really tired of how misleading property pricing is"** — r/AusProperty, posted 2026-03-27
> "I'm getting really tired of how misleading property pricing is. You'll see listings advertised as from $900k or similar in filter, but **when you actually look at recent sales in the same area, comparable houses are consistently going for $1.2M or more.** That's not a small gap, that's a completely different price bracket. It creates false expectations for buyers, especially those trying to stay under $1M. You think a property might be within reach, you invest time researching it or attending inspec" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1s51rb2/im_getting_really_tired_of_how_misleading/

> **"Looking for advice on offer strategy - Sydney"** — r/AusProperty, posted 2026-02-20
> "New to the property market and I'm looking at a 2 bed, 2 bath, 1 car apartment in Sydney and would appreciate some thoughts on where to start with an offer. Details: Floor 10 North-west facing No strata defects Strata approx. $1,500 per quarter Listed at $1.38m–$1.40m **Online property valuation: $1.36m** On the market for almost 7 months **A apartment in the exact same stack/layout, but 6 levels higher, sold for $1.39m over a year ago** . Realistically, where would you start your opening offer? I'm thi" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1r9k5dv/looking_for_advice_on_offer_strategy_sydney/

*A near-perfect specification of an address page: asking range + online estimate + the single most-comparable sale + days on market, assembled by hand.*

> **"Anyone else feel like realestate.com.au tells you nothing useful when you're actually buying?"** — r/AusProperty, posted 2026-02-25
> "A few years back when I was trying to buy my first place, I spent pretty much every weekend doing inspections and felt like a second job after a while. **What really got to me was how little you actually learn from the listings on realestate.com.au. It's all the polished stuff the agent wants you to see, and not much else.** After months of this, I got so burnt out that when auction day came, I barely did a proper look-through. Trusted the price guide (rookie mistake), believed the agent's "feedback" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1reuc39/anyone_else_feel_like_realestatecomau_tells_you/

**What the page owes them:** the comparable set itself, with addresses, dates and exact prices — and an explicit statement of what makes each one comparable.

---

### P6 — The AVM Sceptic *(moderate in the corpus (~16 posts); UPGRADED TO STRONG by the live RSS pull)*

**Underlying question:** *"That automated estimate — can I believe it?"*

This is the persona reacting to exactly the artefact an address page displays. The MongoDB corpus under-samples it badly; targeted `search.rss` queries surfaced a dense, decade-long seam of it in r/AusProperty. Two behaviours show up repeatedly: the estimate used **as a weapon against an agent's guide**, and the estimate producing **distrust of the whole category** because different sites disagree wildly.

**⭐ The single most important quote in this research** — an owner trying to price their own property, listing the public estimates side by side (they say "5 different estimate sites"; six are actually named):

> **"Variation in property estimates"** — r/AusProperty, posted 2022-03-31 *(via live RSS; full body, not truncated)*
> "Hi all I have been trying to estimate what my property is worth. Below are the estimates for one of my properties from 5 different estimate sites. The lowest - $382k, highest $704k. Domain $470k, $545k, $620k Real estate.com $420,000 - $540,000 Propertyvalue.com.au : $445,000 - $533,000 Vali.com.au : $576, $640, $704k CommBank: We estimate your market price as $448,000. It may range between $382,000 and $466,000. Onthehouse.com.au $450-500k **When brokers ask me what my house is worth, I have no idea, given the range of estimates. I'm curious if anyone has tips for how estimate the value with any degree of accuracy.** Thanks"
> https://www.reddit.com/r/AusProperty/comments/tswx38/variation_in_property_estimates/

*An 84% spread between the lowest and highest public estimate of the same house. The stated outcome is not "I picked one" — it is "I have no idea." This is the clearest statement in the whole research of what the incumbent address pages fail to deliver, and it is exactly the gap a transparent, methodology-first comparables range is built to fill.*

> **"Real Estate app - property price accuracy?"** — r/AusProperty, posted 2026-01-18 *(via live RSS)*
> "Hey, just wondering **how much stock I should put in to the estimated value of my property according to Real Estate app?** We've owned our property for 11 months now and apparently has gone up 100k in value since. **Is this reliable estimate because it just seems... unbelievable.**"
> https://www.reddit.com/r/AusProperty/comments/1qgnbql/real_estate_app_property_price_accuracy/

*The closest thing found to the brief's core scenario: an owner looking at an automated estimate **of their own home** and disbelieving it. Note the direction — the estimate was too HIGH and they still didn't trust it. Flattery does not buy credibility.*

> **"Propertyvalue.com.au"** — r/AusProperty, posted 2024-05-02 *(via live RSS)*
> "Hello guys. **How accurate is the property estimate from this website.? Is it something that can be relied on to make a decision on the likely value of a property?**"
> https://www.reddit.com/r/AusProperty/comments/1ciapgs/propertyvaluecomau/

> **"2 Bedder Townhouse built in 1991"** — r/AusProperty, posted 2025-10-04 *(via live RSS)*
> "Hi All, First time trying to buy a property in Australia. We went to 2 bedder townhouse in Western Sydney today and we really like it. We checked the property report from Corelogic and noticed that it was built in 1991. Will it be a concern? **And how accurate the estimated value of the property value in Corelogic property report?**"
> https://www.reddit.com/r/AusProperty/comments/1nxk22p/2_bedder_townhouse_built_in_1991/

**From the MongoDB corpus:**

> **"how accurate are realestate.com.au's price estimates?"** — r/AusProperty, posted 2026-07-30
> "I'm considering relocating to Aus (Sydney) and looking at homes on realestate.com.au . **Since most are listed as "contact agent" for price, I'm relying a lot on their price estimations and wanted to know if they are generally accurate or not?**"
> https://www.reddit.com/r/AusProperty/comments/1vaqxom/how_accurate_are_realestatecomaus_price_estimates/

> **"Looks like another heavily underquoted Proeprty, how much do u all think it will go under hammer?"** — r/AusProperty, posted 2026-02-11
> "Doing house hunting and just found this property in St Albans which seemingly is very much underquoted. **Agents guide price is max $720k however property.com gives low range of $760 with $800k as confident price value.** How much u all think this property will sell and I just hate underquoting so much, waste everyone's time and energy."
> https://www.reddit.com/r/AusProperty/comments/1r1ri2y/looks_like_another_heavily_underquoted_proeprty/

> **"Potential Overpay - Should I be worried?"** — r/AusProperty, posted 2026-04-23
> "Bought our first home for 550K in regional australia 6 months ago in a hot market. While the purchase was on-going, we had an valautor appointed by our lender reach out to us by mistake. They provided feedback that while they can match the value of the property that was on the contract of sale (550K), they personally felt like we paid "absolute top dollar" explicitly suggesting that we over paid. Fast forward, **our lenders avm (which sources data from corelogic) suggests that the price of our pro**" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1st5m2j/potential_overpay_should_i_be_worried/

*Emotional register worth noting: this is a person who bought, then watched an automated number move against them, and is now anxious about their own home. An address page showing a falling estimate for someone's own home has real emotional weight.*

**What the page owes them:** confidence level, sample size, and named inputs — the things every incumbent AVM hides. Accuracy claims are the whole product here.

---

### P7 — The Neighbour Benchmarker *(moderate evidence: ~6 posts, but a very clean mechanism)*

**Underlying question:** *"The near-identical one nearby just sold — what does that make mine?"*

Low count, but the causal chain is unambiguous every time it appears: **a nearby sale is the trigger event that sends the owner looking.** In not one instance is this framed as gossip or nosiness — it is always instrumental (equity, timing, or a bank dispute).

> **"Property market boomed in my area. How to maximise this?"** — r/AusFinance, posted 2021-05-24 (backfill; score 22, 11 comments) — *and it is a Gold Coast post*
> "I was lucky enough to have purchased my townhouse just prior to COVID in a **Gold Coast suburb** hot spot and paid mid 4s for it. Now a year later, **another identical unit in our small complex has just sold for $595,000.** How do the banks view this? Given the comparable sales are mid 500s - early 6s. **Do I have additional equity in the property?** And if so, can I borrow against this additional equity or anything else worth while from this increased valuation? For me personally I'd prefer to spend a b" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusFinance/comments/njx328/property_market_boomed_in_my_area_how_to_maximise/

> **"NSW Selling Agent - Not sharing last minute change of buyer or deposit reduction"** — r/AusProperty, posted 2026-03-13
> "I'm currently selling an investment property in Sydney. […] **The exact same apartment next door sold in December for $1.01m so I decided now was a good time to sell.** I decided to use the same selling agent. My apartment has been listed for 3 weeks and there has been some interest but no solid offers until this week. The market has certainly softened since the interest rate rise in Febr" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1rskkce/nsw_selling_agent_not_sharing_last_minute_change/

*The neighbour's sale did not make them curious. It made them **list**.*

> **"Investment property advice"** — r/AusProperty, posted 2023-10-22 (backfill)
> "My partner and I bought a townhouse just before COVID and we benefited a lot from the price increases in properties in QLD (Brisbane more specifically). **We estimate we have roughly ~150-170k in equity at this stage (price of other townhouses being sold in our complex these days).**"
> https://www.reddit.com/r/AusProperty/comments/17e4adf/investment_property_advice/

(See also the P1 "Bank Valuation" quote, where the identical apartment next door is used as evidence *against the bank's number*.)

**What the page owes them:** the nearby sale that triggered the visit must be *on the page*, named and dated, with an explicit statement of how similar it is to this address.

---

### P8 — The Unsolicited-Approach Reactor *(weak-to-moderate: ~5 posts, but includes strong Gold Coast evidence)*

**Underlying question:** *"An agent/buyer just contacted me about my house. Is it real, how do they know about me, and what is my place actually worth?"*

Directly relevant to Fields' off-market/direct-mail strategy, but the corpus evidence is thin and the dominant emotion is **irritation**, not interest.

> **"The Migration North"** — r/GoldCoast, posted 2021-08-25 (backfill; score 47, 42 comments)
> "Has anybody else noticed a TON of letterbox drops from people asking to buy your house in, mostly cash, lately? It's almost every 2nd day now, most of the times handwritten from buyers in NSW and Vic. This place is about to burst and it's more evident now than ever, there's just not a lot of room here for everyone. **The purchase prices I've seen for my place is insane too, no way am I selling however**, this is paradise on earth here in Currumbin."
> https://www.reddit.com/r/GoldCoast/comments/pb4eit/the_migration_north/

> **"Unsolicited letters from real estate agents saying they have a buyer."** — r/AusProperty, posted 2025-04-08 (backfill; score 15, 62 comments)
> "We received a letter where the real estate agent knew our names and said they have a buyer for our house named "Shirley and Yan". So its all bs of course, I'm just after some clarity on the legality of it, **are they allowed to grab our Pii from public land records and craft a false statement like this legally?** I feel like this surely should conflict with the Privacy act..."
> https://www.reddit.com/r/AusProperty/comments/1jup6c6/unsolicited_letters_from_real_estate_agents/

> **"How do the real estate agents know that I own a particular house?"** — r/AusProperty, posted 2026-05-05
> "I bought a house in Melbourne which I'm renting out. I've had 3 different agents calling me casually "how is house x going for you?". How do they know I own this property and where are they getting my phone number? My name would obviously be associated with the title the official land registry but they shouldn't give away my phone number. I'm also on the do not call register. I'd appreciate any insight into how my number has gotten in their hands so I can maybe do something about it."
> https://www.reddit.com/r/AusProperty/comments/1t4bpsc/how_do_the_real_estate_agents_know_that_i_own_a/

> **"Sick of real estate agents cold calling?"** — r/AusFinance, posted 2026-04-16
> "Sick of receiving calls from real estate agents telling you about recent sales or offering market appraisals? If you haven't had previous contact with them […] then there are laws about how they can advertise their services. If you add your number to the do not call register, they must stop calling you offering property appraisals within 30 days."
> https://www.reddit.com/r/AusFinance/comments/1smrveu/sick_of_real_estate_agents_cold_calling/

**⚠ Caution for the redesign.** Note the **62-comment** thread on the unsolicited-letter post — the volume of *engagement* here is disproportionate to the volume of posts. This suggests the outbound-approach behaviour is high-salience and high-irritation. The corpus contains **zero** posts where an unsolicited approach produced a positive response. A "we found your house" framing carries real risk on this evidence.

---

### P9 — The Privacy-Uneasy Owner *(weak evidence: ~5 posts)*

**Underlying question:** *"Who can see what about my property, and can I stop them?"*

Present but modest, and — importantly — **not** about their own address page existing. The discomfort attaches to (a) name-searchable ownership databases and (b) agents harvesting PII, not to public price data.

> **"CoreLogic help"** — r/AusFinance, posted 2025-04-19 (backfill)
> "Hey guys, bit of a weird one so I'll try and keep it simple. Essentially, after a lengthy HR process I was basically responsible for getting a male coworker fired due to ongoing sexual harassment and stalker-ish tendencies. He now currently works in the lending department of a bank. **My question is - can he search me by name on CoreLogic, or any other such database, to find any properties I own?** I will be buying soon and am worried that this is a possibility."
> https://www.reddit.com/r/AusFinance/comments/1k2x2po/corelogic_help/

> **"Properties sold off market - can you still see the price?"** — r/AusProperty, posted 2025-03-17 (backfill)
> "I was lucky enough to get offered my dream home off market. I ended up getting it for more than I initially planned, but I'm happy. I've been saving for this for years. **My family won't be happy and will absolutely think that I've lost the plot when they see the price. I'm not interested in justifying why/how..etc.** My question is whether the sold prices of even those properties sold offline are visible on websites such as property.com.au?"
> https://www.reddit.com/r/AusProperty/comments/1jdd4v0/properties_sold_off_market_can_you_still_see_the/

*The privacy fear here is **social**, not legal: being judged by family for what they paid. Worth remembering when deciding how prominently to display a specific address's transaction price.*

> **"Genuine Question: Why do Vendor request for Off-Market Listing?"** — r/AusProperty, posted 2026-04-03
> "Aside from celebs or politicians who want to protect privacy - why would an ordinary Joe wants to limit their property exposure to the mass public?"
> https://www.reddit.com/r/AusProperty/comments/1sba196/genuine_question_why_do_vendor_request_for/

---

### P10 — The Data-Accuracy Corrector *(THIN — 2 posts. Do not over-weight.)*

**Underlying question:** *"The internet has my house wrong. How do I fix it?"*

Only two supporting posts exist. Included because both are unusually vivid about *what specifically* is wrong, and because bad data on an address page is a churn risk — but two posts is not a persona, it is an anecdote.

> **"PPOR listed as sold recently even though it wasn't for sale"** — r/AusProperty, posted 2024-11-13 (backfill; score 4, 4 comments)
> "I settled on my first home/PPOR a year ago. Today, I was talking to a broker regarding refinancing and he asked me why I wanted to refinance <6 months after purchase. He brushed past it after I corrected him saying the report must be wrong but after our call I checked the real estate app and it's the same there. **My property is marked sold with what I paid for it when I bought it earlier this year and then again in July of this year for 350k more than what I bought it for.**" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1gqb095/ppor_listed_as_sold_recently_even_though_it_wasnt/

*The only post in the 4,349-post corpus where someone checks a listing site for their own specific address — and they only did it because a broker's report contradicted reality. (The live RSS pull found one more: the "Real Estate app - property price accuracy?" owner in §P6.)*

> **"Do real estate websites blindly use Google Street view?"** — r/AusProperty, posted 2026-07-12
> "I was looking up some houses my parents owned long ago. **Type the address in Google and it will bring up 3 real estate websites for that address. The photo of the house is the one next door.** I drove past to confirm this, as it happened to be close to where I am now. So then put the address into Google Street View and same thing: it shows me number 53 when I asked for 51. The house hasn't changed hands for some time, so I suppose there were no archived listings to dig up."
> https://www.reddit.com/r/AusProperty/comments/1uuccyx/do_real_estate_websites_blindly_use_google_street/

> **"Is there anything wrong with this property?"** — r/AusProperty, posted 2025-04-25 *(via live RSS; full body)*
> "I am browsing townhouses in Logan area and this property caught my attention and I am bit confused. **From property.com.au, the sale history for this property doesn't sound right. It was sold on the 14th March 2025 and then 'listed' on the 17th February 2025, it's still currently for sale** and there is an open inspection tomorrow. How can a property listed for sale on February this year and sold a month ago but still for sale? Doesn't make sense to me, but **I checked realestate.com and domain they both show the property was sold 14th March.** Secondly, the property was sold back in 2023 and sold again March this year and now agin for sale, do you guys think there are some serious issues with the property or maybe there are bad neighbours?"
> https://www.reddit.com/r/AusProperty/comments/1k7j2iq/is_there_anything_wrong_with_this_property/

*Behaviourally important: incoherent status/history on an address page does not read as "bad data" — it reads as **"something is wrong with this house."** A listing-status bug is a trust bug.*

*The **only** post describing the actual behaviour of typing an address into Google — and the address belonged to their parents, not them. Note the confirmed failure mode: address pages showing the neighbour's house.*

---

### P11 — The Price-Opacity Complainer *(weak-to-moderate: ~5 posts)*

**Underlying question:** *"What did it actually sell for — not what they advertised?"*

Small but ideologically loud, and it maps exactly onto Fields' positioning.

> **"Real estate agents are hiding more sold prices than ever. I started tracking guide vs. actual sold differences manually. What did I find?"** — r/AusFinance, posted 2026-07-29
> "Hi everyone, I'm a mortgage broker, but right now I'm also in the trenches trying to buy a property for myself.. Between my own search and what my clients (and even people who just come to me for general chats) go through every day, the level of pricing games is insane. It makes it almost impossible to plan bids and buy a property. Specifically, two massive issues: 1. Underquoting: An agent lists a property with a guide of $1.1M. My clients spend $500 on building reports and align pre-approval," *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusFinance/comments/1v9vrkp/real_estate_agents_are_hiding_more_sold_prices/

> **"Victorian sellers threaten to ditch auctions over reserve price rule"** — r/AusFinance, posted 2026-05-17
> "In Victoria, there is currently **no obligation to publicly disclose the final sale price of a property, with many listings simply marked as "price withheld" or "contact agent" once sold, or taking months to be available.**" *(quoting an article by Nathan Mawby)*
> https://www.reddit.com/r/AusFinance/comments/1tff02r/victorian_sellers_threaten_to_ditch_auctions_over/

> **"Congrats to Natoli property group for a record number of 'undisclosed' sales in Surry Hills"** *(title-only post)* — r/AusProperty, posted 2022-07-27 (backfill; score 91, 39 comments)
> https://www.reddit.com/r/AusProperty/comments/w90sd6/congrats_to_natoli_property_group_for_a_record/

---

### P12 — The Risk/Overlay Checker *(moderate: ~11 posts; SEQ-specific and directly relevant to Fields)*

**Underlying question:** *"Does this specific address flood, and what does that do to its value and its insurance?"*

The only per-address attribute in the corpus that people research with the same intensity as price — and it is a South East Queensland concern specifically.

> **"Flooding and House Values"** — r/AusProperty, posted 2026-05-21
> "Is anyone else curious that new Flood mapping drops. **Houses throughout multiple LGA in SEQ now have insurance costs 10-20k+ a year and house values haven't tanked at all.** On the opposite side. My house doesn't flood on the new mapping and insurance is $2500 a year for a similar property. **Yet houses 4m below the flood level are selling for 90-95% of those that don't. It's also not a selling point in any of the hundreds of listings I checked.** Is this just REAs being ignorant or absolutely shit sca" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1tjatqi/flooding_and_house_values/

> **"Question about this Flood Map"** — r/GoldCoast, posted 2026-04-21
> "A family member is looking at buying a property in Tallebudgera. I'm doing some research for them and this flood map seems highly concerning. What am I missing? Why are there so many houses built here?"
> https://www.reddit.com/r/GoldCoast/comments/1srinm2/question_about_this_flood_map/

> **"New Gold Coast mapping shows additional 88,000 properties at flood risk"** *(title-only post)* — r/GoldCoast, posted 2022-11-17 (backfill; score 47, 13 comments)
> https://www.reddit.com/r/GoldCoast/comments/yxza8z/new_gold_coast_mapping_shows_additional_88000/

> **"looking at brisbane property with flood overlay concerns after running property checking report"** — r/AusProperty, posted 2026-05-19
> "im in queensland checking out a 3 bed house in a brisbane suburb listed around 650k with a big backyard but the area has some known flood history from past events. **i already pulled the propcheck report which showed it sits in a partial flood overlay with some stormwater drainage notes and heritage zoning flags that could limit extensions.** the report also flagged bushfire risk low but mentioned nea" *[…truncated at 500 chars in corpus]*
> https://www.reddit.com/r/AusProperty/comments/1thkrb8/looking_at_brisbane_property_with_flood_overlay/

**What the page owes them:** per-address flood/overlay status stated plainly. On this evidence it is the highest-value non-price attribute for a Gold Coast address page.

---

### P13 — The Tool Shopper *(moderate: ~21 posts — plus a strong supply-side signal)*

**Underlying question:** *"Where do I get this data without paying $300/month or handing an agent my phone number?"*

> **"Real Estate Trackers/Price History"** — r/AusFinance, posted 2026-07-20
> "Can anyone recommend a free service/database that I can access to check how property prices have performed within a specific development over the years? Thankyou"
> https://www.reddit.com/r/AusFinance/comments/1v1969y/real_estate_trackersprice_history/

> **"Where can I get good data / analysis?"** — r/AusProperty, posted 2026-07-07
> "As title... I have been using Homer to help with individual property insights, but I would like to understand for example - Brisbane suburbs, average time on market trends (by price ranges if possible?). Does this type of data exist and readily available?"
> https://www.reddit.com/r/AusProperty/comments/1uqaa0e/where_can_i_get_good_data_analysis/

> **"I built a free property research tool for Aussie buyers after getting frustrated with the process…"** — r/AusProperty, posted 2026-04-10
> "**Most suburb data in Australia is either locked behind a $300+/month CoreLogic subscription or bundled with a buyers agent fee. The underlying government data is free — it's just scattered, complex and inaccessible to normal buyers.** I spent months pulling it together into one tool so that people dont have to open 10 different 10 to get different data and also understand what each metric means"
> https://www.reddit.com/r/AusProperty/comments/1shkbq5/i_built_a_free_property_research_tool_for_aussie/

**Supply-side signal.** The corpus contains a striking density of founders shipping per-address data products in 2026 — Property Mate (browser extension overlaying Domain + PropTrack estimates onto realestate.com.au), dwell-wise.com.au, PropCheck, Homer, PropCred, and Glasshouse (an AR app: *"point your phone at any property and instantly see sale history, comparable sales, development applications, AI analysis"*, r/AusFinance 2026-07-27, https://www.reddit.com/r/AusFinance/comments/1v7r47y/i_built_a_database_of_52m_australian_property/ ). This is evidence of *perceived* demand and of a **crowding competitive field**, not of validated demand.

One founder explicitly probed willingness-to-pay and it is worth noting that the corpus contains **no answer**:

> **"Would you pay for an AI-generated property report?"** — r/AusProperty, posted 2026-02-26
> "Genuine question for the group. When you're researching a property to buy, how much time do you spend pulling together all the data — comparable sales, median prices, rental yields, school catchments, days on market, etc? If there was a tool that did all of that automatically and gave you a stock-style report for around $5, would you use it? **Or do you feel like the free info on REA/Domain is enough?**"
> https://www.reddit.com/r/AusProperty/comments/1rf54tn/would_you_pay_for_an_aigenerated_property_report/

---

## 4. Negative findings — motivations looked for and NOT found

These were explicitly searched for. Absence of evidence in a topic-sampled corpus is not proof of absence in the population — but each of these was hypothesised in the brief and is not supported here. Where a finding was **re-tested against the independent 1,336-post live RSS set**, that is noted; those negatives are the stronger ones. §6.3 has the confirmation counts.

| Hypothesised motivation | Result | Detail |
|---|---|---|
| **"I googled my own address"** | **Not found** ✔ re-tested (0/1,336 in RSS) | Zero posts describe searching one's own address and reacting to the result page. Closest: r/AusProperty 2026-07-12 (looked up *parents'* old addresses) and r/AusProperty 2024-11-13 (checked their own listing only after a broker's report contradicted reality). |
| **"What did the current owner pay?" (buyer-side, pre-offer)** | **Not found** ✔ re-tested (0 relevant / 1,336 in RSS) | A dedicated regex for `what did they pay / how much did the vendor pay / what the owner paid` returned **0 of 4,349**. Buyers benchmark against *comparable sales*, never against the incumbent owner's purchase price. This is a notable null: it is a common assumption about address-page intent and this corpus does not support it. |
| **Rates notice / land valuation notice triggering a lookup** | **Not found — but see caveat** ⚠ the `land valuation notice` RSS query 429'd on all three subreddits, so this is the *weakest* negative here. Re-run before relying on it. | 16 posts matched land-valuation terms; on inspection **all** are about land *tax* burden (investors, VIC/NSW/QLD surcharges), not about a valuation notice arriving and prompting a value check. The one near-miss (r/AusProperty 2026-06-19, "To sell now or wait longer?") cites NSW land valuations as a value proxy for a *sell/hold* decision, not as a trigger. |
| **Privacy discomfort at finding one's own home listed online** | **Not found** | Privacy concern exists (P9) but attaches to name-searchable ownership databases and agent PII harvesting. Not one post expresses discomfort that a public page about their address exists. |
| **Nosiness / snooping at neighbours' prices as a guilty pleasure** | **Not found** ✔ re-tested (0/1,336 in RSS) | Every neighbour-price check in the corpus (P7) is instrumental — equity, listing timing, or arguing with a bank. Zero framed as curiosity, gossip, or entertainment. |
| **Divorce / probate / deceased estate as a valuation trigger** | **Very thin** | Two weak hits: "Ex won't sell and I feel stuck" (r/AusProperty 2026-07-13, mentions "multiple appraisals") and "CGT surprise on IP then PPOR" (r/AusFinance 2026-03-23, retrospective appraisal for CGT). Not enough for a persona. |
| **Insurance / rebuild-cost lookup** | **Not found** | Insurance appears only as a *consequence* of flood mapping (P12), never as a reason to look up a value. |
| **School catchment as a lookup driver** | **Very thin** | Two passing mentions inside longer lists. No post where catchment is the reason for the search. |
| **Volatility of an AVM over time ("it moved by $X")** | **Not found in the corpus — but FOUND via live RSS** | Nothing in the 4,349-post corpus. The live pull falsified this: r/AusProperty 2026-01-18 — *"We've owned our property for 11 months now and apparently has gone up 100k in value since. Is this reliable estimate because it just seems... unbelievable."* (§P6). One post is not a persona, but this hypothesis is **live, not dead**, and is the one worth re-testing hardest. |
| **"My home is worth more than I thought" — positive surprise** | **Not found** | Every emotional reaction to a value in the corpus is negative or anxious (bank too low, agent too low, "did I overpay"). Zero delight. |

---

## 5. What this means for the `/off-market/:slug` redesign

Stated as observations from the evidence, not recommendations.

**If only one line survives from this document, make it this one:** the public estimates for a single Australian house can differ by **84%** ($382K vs $704K on the same property), and the owner's stated outcome is *"I have no idea"* — not "I picked one." The market failure is not absence of a number. It is **six numbers with no way to adjudicate between them.** Everything below follows from that.

1. **The page is a second opinion, not a first number.** The dominant motivation (P1+P3+P6, ~170 posts) is checking a number someone else already gave you. Design implication: the *method and the comparables* are the product; the headline figure is the hook.
2. **A range with a visible top end is the useful artefact.** P1's documented workflow uses "the upper end value of your home on sites like domain and property" as leverage with a bank. A single point estimate serves nobody in this corpus. (Consistent with Fields' existing comparables-range position.)
3. **The trigger event should be on the page.** P7 shows the visit is usually caused by a specific nearby sale. If a comparable sold last month two doors down, that sale is the reason the visitor is there.
4. **Flood/overlay is the highest-value non-price attribute for the Gold Coast.** P12 is small nationally but SEQ-concentrated and emotionally loaded.
5. **Beware the outbound framing.** P8's evidence is that unsolicited "we know about your house" approaches generate irritation and privacy suspicion (62 comments on the letter thread). Zero positive reactions in the corpus.
6. **What people fear is being wrong about their own home, publicly.** P9's off-market buyer feared family judgement of their price; P10's owner found their own address showing a phantom sale. Accuracy on a specific address is a trust-critical, not cosmetic, concern.
7. **The estimate does not have to be flattering — it has to be checkable.** The one owner found reacting to an AVM on their own home saw it move *up* $100K in 11 months and still called it "unbelievable". Optimism is read as noise, not as good news.
8. **The field is crowding.** At least six per-address data products appeared in this corpus in 2026 alone. Differentiation on *transparency of method* — the thing P3 and P6 actually ask for — is the only axis the corpus shows as unmet.

---

## 6. Live RSS pull — full outcomes

**Totals:** 50 requests · 21 × HTTP 200 · 29 × HTTP 429 (58% rate-limited) · **1,470 entries, 1,336 unique posts.**
Policy: 1 request / 6 s, browser User-Agent, 30 s backoff on 429, hard abort after 3 consecutive 429s (never triggered). `api.pullpush.io` not touched.

### 6.1 Subreddit feeds

| Subreddit | `/new.rss` | `/hot.rss` |
|---|---|---|
| AusProperty | 100 | 100 |
| AusFinance | **429** | **429** |
| GoldCoast | 100 | **429** |
| australia | 100 | **429** |
| brisbane | **429** | 100 |
| AusHomeLoans | **429** | 88 |
| AusRenovation | **429** | **429** |

**r/AusFinance could not be refreshed at all** (both feeds 429). **r/AusRenovation returned nothing** (both feeds 429) — so the renovation-payback persona (P4) rests entirely on the MongoDB corpus and was never independently tested. That is a real gap.

### 6.2 Search queries (`search.rss?q=…&restrict_sr=1&sort=new`)

Cell = number of entries returned, or `429`.

| Query | r/AusProperty | r/AusFinance | r/GoldCoast |
|---|---|---|---|
| `what is my house worth` | 97 | 100 | 6 |
| `house worth` | **429** | **429** | **429** |
| `property estimate` | 100 | 100 | 2 |
| `domain estimate` | **429** | **429** | **429** |
| `neighbour sold` | 30 | **429** | **429** |
| `what did they pay` | **429** | 100 | 10 |
| `sale history` | **429** | **429** | **429** |
| `bank valuation` | 100 | 100 | 0 |
| `land valuation notice` | **429** | **429** | **429** |
| `appraisal` | 45 | 55 | **429** |
| `looked up my house` | **429** | **429** | 37 |
| `realestate.com.au estimate` | **429** | **429** | **429** |

**Four queries were lost entirely to rate-limiting across all three subreddits:** `house worth`, `domain estimate`, `sale history`, `land valuation notice`, plus `realestate.com.au estimate`. Two of those (`domain estimate`, `realestate.com.au estimate`) target the AVM-reaction persona P6 directly, and one (`land valuation notice`) targets the rates-notice hypothesis that §4 records as unsupported. **The "rates/land valuation notice triggers a lookup" negative finding is therefore the weakest of the negatives — the one query designed to test it 429'd on all three subreddits.** It should be re-run before being treated as settled.

### 6.3 What the RSS pull added

**Materially strengthened P6 (AVM Sceptic)** — from a thin corpus theme to the best-evidenced insight in the document. The corpus keyword set never included "how accurate", so this seam was invisible in Source 1. Four new posts, all quoted in §P6, including the six-way estimate comparison (2022) and the owner disbelieving a +$100K move on their own home (2026).

**Added the one Gold Coast seller case** with four conflicting numbers for a single address (§P3, 2025-12-09) — the closest thing in the research to a Fields customer.

**Surfaced r/AusHomeLoans**, absent from the corpus entirely, which is where the bank-valuation-vs-online-estimate conversation actually lives (§P1).

**Independently re-tested five negative findings** against a fresh 1,336-post set (note that a sixth — AVM volatility — was *falsified* by this pull; see §4):

| Test | Matches in 1,336 RSS posts |
|---|---|
| "googled / typed in / looked up **my own** address" | **0** |
| "what did they/the owner/the vendor pay" (buyer researching incumbent's purchase price) | **1**, and it is an in-laws gifting-a-house post, not pre-offer research — https://www.reddit.com/r/AusFinance/comments/1u65ab2/inlaws_giftingselling_us_a_house/ |
| nosiness framing (`nosey`, `nosy`, `stickybeak`, `snoop`, `guilty pleasure`) | **0** |
| "does a pool / kitchen / extension add value" (this tests the *phrasing*, not persona P4, which is corpus-evidenced) | **0** |
| rates / land valuation notice as a trigger | **1**, and it is a news headline about the NSW Valuer General's staffing, not a homeowner — https://www.reddit.com/r/AusFinance/comments/1f7svtd/nsw_valuer_general_takes_half_its_27_million/ |

### 6.4 An honest null: r/GoldCoast is not a property-research subreddit

The `search.rss` queries that did return for r/GoldCoast (`what is my house worth` 6, `property estimate` 2, `what did they pay` 10, `looked up my house` 37, `bank valuation` **0**) produced **no usable address-lookup evidence whatsoever**. Reddit's relevance matching degraded badly on this small subreddit — returned results include weekend event listings, a lost Nimbus 2000 broom, fire-ant bait kits, and a Bond University course review.

What r/GoldCoast property talk *is* about, on this evidence: **rental affordability and buying power**, not valuation. e.g. "I need to rant about housing" (2025-12-09, "With over 200k in savings deposit […] guess our buying power? .... 750"); "Rental is being sold and I need advice" (2025-06-13). The one strong Gold Coast owner-side signal in the whole research came from the *corpus* backfill, not the live pull — "The Migration North" (2021, §P8) and "Property market boomed in my area" (2021, §P7).

**Implication:** do not expect to validate Gold Coast homeowner intent on Reddit. The local subreddit does not carry it. For Gold Coast-specific validation, Fields' own first-party data (§ `EVIDENCE_first_party_fields_data.md`, PostHog property-page behaviour) is the better instrument, and the national property subreddits are the better source for *motivation*.

---

## 7. Reproducibility

- Corpus dump + all mining scripts: session scratchpad `.../scratchpad/` — `themes.py` (pass 1, 20 regexes), `final_counts.py` (pass 2, 13 persona regexes), `rss_pull.py` (RSS puller), `rss_log.txt` (per-URL HTTP outcomes), `rss_results.json` (1,470 raw entries).
- Rerunning the persona counts: `python3 final_counts.py` against a fresh dump of `system_monitor.search_reddit_posts`.
- **If rerunning the RSS pull:** the five queries lost to 429 in §6.2 are the priority, especially `domain estimate`, `realestate.com.au estimate` and `land valuation notice`. Keep the ≥6 s spacing.

