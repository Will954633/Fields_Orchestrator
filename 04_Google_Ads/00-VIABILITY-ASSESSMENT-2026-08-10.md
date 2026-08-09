# Google Ads Viability Assessment — Can paid search generate seller leads for Fields?

**Date:** 2026-08-10 · **Question from Will:** can simple Google advertising cater to the portion of the
market searching "real estate agent Robina" and similar phrases, and is there a pathway to leads fairly
quickly?

**Short answer:** **Not on "real estate agent Robina" — that query family is 3–5 clicks per month.**
There *is* a viable paid-search pathway, but it is a different keyword family (valuation/appraisal intent,
~100–160 clicks/month), and **one blocking defect must be fixed first** or the spend is blind again.

---

## 1. We have already run this experiment — and it produced zero leads

Pulled from the Google Ads API (account 997-572-4211), lifetime:

| Campaign | Impr | Clicks | CTR | Avg CPC | Cost | "Conv" |
|---|---|---|---|---|---|---|
| Zero Commission Launch — Gold Coast (Mar 2026) | 5,031 | 144 | 2.86% | $1.40 | $202.16 | 33 |
| Search: Property Listings — Google vs FB Test (Apr 2026) | 688 | 51 | 7.41% | $2.91 | $148.18 | 0 |
| **Total** | **5,719** | **195** | — | — | **$350.34** | — |

**The 33 "conversions" were 31 Page views + 2 Article reads.** Breakdown by conversion action confirms it.
Zero were leads.

**Lifetime conversion-action totals:**

| Action | Category | Lifetime |
|---|---|---|
| Page view | PAGE_VIEW | 31 |
| Article Read (30s+) | PAGE_VIEW | 2 |
| Property Search Click | PAGE_VIEW | 0 |
| **Contact Form Click** | **SUBMIT_LEAD_FORM** | **0** |

All four `launch_leads` records created during that campaign window are **Will's own test submissions**
(`WILLIAM SIMPSON`, `14 Ray St Runaway Bay`, `Test Property, Robina`).

**So: $350 spent, 195 clicks, 0 real leads.** The March 2026 ad audit already recorded the cause —
*"Google Ads spending $57/week with no conversion tracking installed."*

### ⚠ And it was worse than "untracked" — a large part of that spend was bots

`logs/fix-history/2026-03-17.md` `[LAUNCH-BOT-TRAFFIC]`, found mid-campaign at 77 clicks / $78.39:

> *"All 111 tracked sessions came from 11 AWS IPs — zero real human visitors… every session was from
> AWS data centres. This is ad-verification bot or click-fraud traffic."*
> *"A page-view conversion tag fired on every landing page load (`AW-17993173310/Rg0OCIGsqIQcEL6S6IND`,
> value $1.00), causing Google to report 32 'conversions' that were just bot pageviews. **This taught
> Google's algorithm to optimise for bot traffic rather than real users.**"*

**This is the "feedback loop of doom" from §5.4 — not as a theoretical risk, but as something that
already happened to this account.** It means the March campaign is *not* clean evidence that the offer
or the keywords failed; it is evidence that we bought bot clicks and then trained the algorithm to buy
more of them. The honest read is that **the Zero Commission thesis was never actually tested.**

**⚠ The trap was still live until 2026-08-10.** That fix removed the page-view tag from
`public/launch/{a,b,c}/index.html` but left the same label wired into the React app
(`PropertyPage.tsx:514` fires `page_view` on every property page load) **and left the conversion action
`primary_for_goal=True`**. Now fixed at the account level — see §2.

### What the search-term report tells us that is still useful

- Best CTR keywords were all **FSBO / commission-anxiety**, not agent-finder:
  `private sale gold coast` 14.71% · `sell house without agent` 10.71% · `how much do real estate agents
  charge` 5.11% (235 impr, 12 clicks, $4.84 CPC — our single highest-volume keyword).
- The buyer-listings ad got the **highest CTR of anything we've run (7.41%) and converted nothing.**
  CTR is not the metric. Worth remembering when an agency shows you a CTR chart.
- Search terms show heavy buyer/renter/investor leakage (`houses for sale gold coast under $500 000`,
  `buyers agent fees`, competitor names like `boris burcul`, `l j hooker nerang`).

---

## 2. ⚠ BLOCKING DEFECT — the one thing that converts is invisible to Google

`AnalyseYourHomePage.tsx` and `AnalyseYourHomeV2Page.tsx` **do not import `trackGoogleConversion`.**
The address submit fires `fireGtag('analyse_home_lead_submit')`, which is a **GA4 custom event** with no
`send_to` — it lands in GA4 property `G-5C5VS27X42` and **never reaches Google Ads `AW-17993173310`**.

Confirmed from both sides:
- Code: `grep -c trackGoogleConversion` → **0** in both AYH pages.
- API: only 4 conversion actions exist, none of them the AYH address submit.

**Consequence:** Smart Bidding has never had a real lead signal, and cannot get one. Any campaign launched
before this is fixed repeats March 2026 exactly.

**Fix:** add an `analyse_home_lead_submit` conversion action in Google Ads, add it to
`CONVERSION_LABELS` in `src/utils/gtagConversions.ts`, and call `trackGoogleConversion` alongside the
existing `phCapture('analyse_home_submit_success')`. Mark it the **only** Primary action and demote
`Page view` to Secondary — a page-view primary conversion actively teaches the algorithm to buy bounces.

---

## 3. The volume ceiling — Google's own forecast, Gold Coast geo

Two corrections to the CSV in this folder first:

1. **`real estate agent robina` = 110/mo is the AUSTRALIA-WIDE figure.** Scoped to Gold Coast it is
   **50/mo**.
2. Keyword Planner reports **the same aggregated volume for close variants** (`real estate agent gold
   coast`, `...gold coast australia`, `real estate gold coast agents` all show 720). Summing them
   triple-counts.

**Gold-Coast-scoped monthly volume (Keyword Planner API):**

| Keyword | Vol/mo | Top-of-page bid |
|---|---|---|
| real estate agent gold coast | 720 | $4.42–$24.39 |
| **real estate agent robina** | **50** | $1.13–$13.56 |
| real estate agent varsity lakes | 10 | $6.18–$14.63 |
| real estate agent burleigh waters | 0 | — |
| best real estate agent gold coast | 30 | $6.70–$49.41 |
| how much is my house worth | 90 | $1.29–$3.58 |
| property valuation gold coast | 70 | $1.40–$13.17 |
| property values gold coast | 70 | $1.40–$13.17 |
| real estate commission qld | 70 | $2.11–$7.68 |
| free property appraisal | 10 | $1.96–$8.84 |

**Our three target suburbs, agent-finder intent, combined: ~60 searches/month.**

### Google's own 30-day forecast (phrase match, Gold Coast, AUD)

| Scenario | Bid | Impr/mo | **Clicks/mo** | CTR | Avg CPC | Cost/mo |
|---|---|---|---|---|---|---|
| **A. Agent-finder, our 3 suburbs** | $4 | 161 | **3.0** | 1.83% | $2.98 | $8.79 |
| A. same | $10 | 241 | **5.5** | 2.30% | $5.55 | $30.79 |
| B. Agent-finder, whole Gold Coast | $4 | 927 | 16.4 | 1.76% | $2.40 | $39.21 |
| B. same | $10 | 1,250 | 28.0 | 2.24% | $4.85 | $135.91 |
| **C. Appraisal / valuation intent** | $4 | 2,126 | **104.1** | 4.90% | $2.63 | $273.50 |
| **C. same** | $10 | 3,032 | **161.3** | 5.32% | $5.58 | $899.39 |
| D. Commission / cost-of-selling | $4 | 483 | 12.1 | 2.50% | $2.43 | $29.37 |
| D. same | $10 | 590 | 24.4 | 4.14% | $5.88 | $143.72 |

**This is the answer to the question as asked.** Bidding the "real estate agent Robina" family buys
**3–5.5 clicks per month**. At even a generous 5% landing-page conversion that is **one lead every four
to six months**. It is not a channel; it is a rounding error.

**Valuation intent is 20–30× larger** (104–161 clicks/mo) and converts better (4.9–5.3% forecast CTR).

---

## 4. Who you'd be bidding against (from Will's screenshots)

Five sponsored slots on `real estate agent robina`; **four are national lead aggregators** —
LocalAgentFinder (×2 placements), OpenAgent, Vendo. Only GCSR is a local agency, and its offer is
**"Real Estate Robina QLD – Free Home Appraisal"**.

Why they outbid you, structurally: **they resell one lead to multiple agents.** Verified pricing:

| Aggregator | What an agent pays | Effective cost per listing won ($1.2M sale, ~2.5% comm ≈ $30k) |
|---|---|---|
| OpenAgent | 20–30% of commission | **$6,000–$9,000** |
| LocalAgentFinder | 0.375% of sale price + GST | **~$4,500** |
| AgentSpot | $1,000 + GST flat ($500 rebated), capped 5 agents/suburb | **~$500** |

That spread is the real benchmark. A Google Ads program producing a listing under ~$4,500 all-in beats
LocalAgentFinder; under ~$500 it beats AgentSpot.

**OpenAgent's own published funnel is the most useful number in the whole review:** ~15,000 leads/month
in → ~2,000 referred out. **87% of raw seller leads fail qualification** — with a 60-person outbound
calling team. Of survivors, 35% go to market within 3 months → **~4.5% raw-lead-to-market**.

---

## 5. What works and what fails (external evidence, 2025–2026)

**⚠ The benchmark you will be quoted is not your benchmark.** LocaliQ 2026 (894 US campaigns) shows Real
Estate at 7.61% CTR / $3.22 CPC / 3.70% CVR / **$102.51 CPL** — but that average is carried by rentals
and property management (10.24% CVR). Isolate agent services:

| Subcategory | CTR | CPC | CVR | CPL |
|---|---|---|---|---|
| Property Management | 6.66% | $3.94 | 10.24% | $76.71 |
| Homes for Sale by Agent | 5.87% | $3.90 | 1.83% | $142.59 |
| Real Estate Broker | 7.29% | $3.71 | 1.53% | $162.39 |
| **Residential Real Estate Agent** | 8.00% | $3.19 | **1.29%** | **$157.59** |

Real Estate had the **largest YoY CPC rise of all 23 industries (+27.3%)**, and Residential Real Estate
Agent was the only subcategory whose CVR *fell*. Caveat: min. 11 campaigns per subcategory, US only.

**There is no primary Australian real-estate PPC benchmark dataset.** Every AU "benchmark" page checked
either republishes the US WordStream figures with a dollar sign, or states no methodology. Plan against
US structure, not AUD forecasts.

### Format verdicts

| Format | Verdict |
|---|---|
| **Search — appraisal/valuation intent** | ✅ The only format with a defensible thesis. Expensive, low volume, but real. |
| **Search — agent-finder** | ❌ Aggregator territory; 3–5 clicks/mo locally. Not a channel. |
| **Search — buyer intent** | ❌ Portal territory (REA/Domain). And buyers don't pay us. We already proved it: 7.41% CTR, 0 conversions. |
| **Performance Max** | ❌ **Contraindicated** — without closed-loop data it optimises to form fills and finds bot form fills ("feedback loop of doom"). |
| **Display / YouTube / Demand Gen** | ❌ No evidence of listings. Demand Gen baseline ~0.8% CTR. The "403% more inquiries with video" stat is a zombie with no primary source. |
| **Local Services Ads** | ❌ **VERIFIED unavailable in Australia** (Google's own country list: AT/BE/CA/FR/DE/IE/IT/ES/CH/UK/US). And "real estate agent" isn't even a US LSA category. Any AU agency claiming otherwise is wrong. |
| **Google Business Profile + reviews** | ✅ **Highest-leverage Google surface, and free.** 81% read reviews; 53% of sellers interview only one agent; 66% come via referral. |

### ⚠ The structural finding that constrains everything

Google's **offline conversion import hard-cuts at 90 days** after last click (63 days for enhanced
conversions for leads). Sellers consider selling **2–4 months** before listing; valuation leads reportedly
nurture 6–18 months.

**So the real outcome — a signed listing — physically cannot be imported back to train Smart Bidding for
most leads.** This is structural, not an execution problem. Design around it: optimise to a **mid-funnel
proxy inside 63 days** (booked appraisal / address submitted), and do true attribution in our own CRM via
stored GCLID.

**No verifiable published case exists of a small independent agent profitably winning listings from
agent-finder keywords.** In an industry that loves case studies, that absence is meaningful.

---

## 6. Copy — what the evidence actually supports

**Honest position: real-estate-specific ad-copy A/B data does not exist publicly.** Every "headlines that
convert" page is an agency blog with no test data. Anyone claiming "adding a price lifts CTR by X%" in
real estate is making it up.

**The one real dataset** (Optmyzr: 22,000+ accounts, 1M+ ads, cross-vertical):

| Finding | Data |
|---|---|
| **Ignore Google's Ad Strength meter** | "Excellent" had the **worst** CPA ($51) and CVR (3.0%); "Average" the best ($42 / 3.4%) |
| **Short headlines win** | 0–10 chars → $41 CPA / 3.1% CTR · 31+ chars → $48 CPA / 2.7% CTR (**17% worse CPA**) |
| **Long descriptions win** | 121+ chars → $40 CPA vs 0–40 chars → $48 |
| **Sentence case beats Title Case** | 0% title case → $40 CPA vs 75–100% → $44 |
| **Partial pinning beats both extremes** | some pinning $42 CPA; fully pinned worst |
| **≤3 form fields** | 3 fields 10.1% vs 9 fields 3.6% |
| **5th–7th grade reading level** | 11.1% conversion, ~56% better than 8th–9th grade |

The Optmyzr study contains **no** data on "free", $ figures, numbers, urgency, or suburb tokens. Those
remain untested hypotheses.

### Our own copy evidence (small samples — treat as directional only)

| Landing page | Impr | Clicks | CTR |
|---|---|---|---|
| `/launch/a/` "Sell With Zero Commission" (plain) | 120 | 5 | 4.17% |
| `/launch/c/` Data-Led | 4,775 | 136 | 2.85% |
| `/launch/b/` "$25K for Brochures?" | 136 | 3 | 2.21% |

Only `/launch/c/` has meaningful volume; A vs B is 5 clicks vs 3 and proves nothing.

### ⚠ QLD legal constraints — these bind us directly

- **Property Occupations Act 2014 s.212**: false or misleading representation re: sale of real property —
  **max 540 penalty units**. **Intent is irrelevant.** The test is the *overall impression*, and it covers
  **pictures, plans, verbal statements and conduct**, not just text.
- **Therefore a compliant landing page does not cure a misleading headline.**
- **ACL/ACCC** specifically polices **"free"** offers and requires you to **prove every claim advertised**.
- **A single-figure valuation headline is a representation Fields cannot substantiate**, given our own
  documented ±12% band that contains the sale price only 61% of the time. This aligns with the existing
  editorial rule (no single valuation in headlines) — the rule is also a legal shield, not just style.

### Copy direction I'd actually test

Given the above, the hypothesis worth running is **the opposite of the standard play**: a *qualified*
offer against the standard *unqualified* one, judged on **cost per qualified appraisal**, not per form fill.

- **Control (industry standard):** "Free Instant Home Valuation"
- **Challenger (Fields-native):** comparable-sales **range** + published methodology — e.g.
  headline `Robina Sold Prices` / `What 3 Comparables Say` / `See The Comps`, description carrying the
  substantiation and the honest error rate.

Rationale: "free" is the single strongest attractor of the 87% junk cohort. A CTR lift from "free" that
raises the junk rate is a loss — **and CTR is exactly the metric an agency will show you.** Keep headlines
under ~20 characters, sentence case, descriptions long, partial pinning, and 1-field form (address only —
which is what already converts for us).

---

## 7. The economics, using our own measured conversion rate

**Our real landing-page rate (PostHog, July 2026):** 316 `/analyse-your-home` pageviews → 18 address
submits → **15 leads created = 4.7% page→lead**. That is a genuinely healthy rate (all-industry median
6.6%; US agent-services 1.29%).

⚠ But per `ayh_conversions_no_contact`, these leads are **addresses with `email: null, phone: null`**.
That is by design — Will's strategy is address → posted appraisal → rapport → inbound call.

**Model — Scenario C (valuation intent), $4 bid:**

| | Optimistic (our 4.7%) | Conservative (US agent benchmark 2%) |
|---|---|---|
| Clicks/mo | 104 | 104 |
| Spend/mo | $273 | $273 |
| Address leads/mo | 4.9 | 2.1 |
| **Cost per address lead** | **$56** | **$130** |
| Leads/year | 59 | 25 |
| Listings/yr @ 1–2% raw-lead-to-listing | 0.6–1.2 | 0.25–0.5 |
| **GCI @ ~$30,800/listing** | **$18k–$37k** | **$8k–$15k** |
| Annual ad spend | $3,282 | $3,282 |

**Even the conservative case is ROI-positive on a single listing** — because one Gold Coast listing is
worth ~$30,800 and a year of this costs ~$3,300. That asymmetry is the entire argument for trying.

**But the model has one load-bearing assumption that has never been tested: the 1–2% lead→listing rate
depends on the nurture step, and per `lead_funnel_audit_2026-08` the mail step has never executed once —
399 PDFs generated, 0 posted.** Buying addresses we don't post to converts at 0%, not 1–2%.

---

## 8. Recommendation

**Do not launch on "real estate agent Robina."** Google's own forecast says 3–5.5 clicks/month. There is
no pathway there at any budget.

**There is a pathway on valuation/appraisal intent** — ~100–160 clicks/month, ~$275–$300/month, plausibly
2–5 address leads/month at $56–$130 each. But it is **not** "fairly quick" to revenue: the seller cycle
is 2–4 months minimum from serious consideration, and 6–18 months from a cold valuation request.
Expect **leads in weeks, listings in quarters.**

**Sequence — do not skip 1 and 2:**

1. **Fix the conversion tracking** (§2). Non-negotiable. Without it this is March 2026 again.
2. **Post one appraisal.** The paid-lead model multiplies the nurture step by ~100. If the nurture step
   is 0, the product is 0. Prove the mail loop on the leads we *already have* before buying more.
3. **Then** launch Scenario C only: Search-only, phrase/exact, Gold Coast geo, ~$10/day, Maximise Clicks
   until 30 conversions, then Maximise Conversions on the *address-submit* action. Not PMax. Not Display.
4. **Free first:** Google Business Profile + reviews is where 81% of seller evaluation actually happens
   and it costs nothing. Do this regardless of whether the ads run.
5. **Store GCLID at address submit** into the CRM so attribution survives past Google's 90-day ceiling —
   because for most of these leads, the listing will land outside it.

**Budget guardrail:** the existing `google_ads_manager.py` caps are $50/day per campaign and $500/month
total. Scenario C at $10/day fits comfortably. Treat $1,000 total as the falsification budget: if 3 months
and ~$900 produce fewer than 6 address leads, the thesis is dead and we stop.

---

## 9. Brain 1 — what the coaching corpus actually proves

Deep query over 560 judged-relevant units. **Full brief:** `scratchpad/brain1_google_ads.md`.

### The headline finding

**No unit in the corpus attributes a single closed listing to Google search ads with a CPL and
conversion rate attached.** Every quantified success in the corpus comes from *another* channel:
YouTube ("$65,000 in commission from YouTube, pure YouTube leads", u901497), BiggerPockets ("$1,500…
closed seven or eight transactions… $50 a piece", u901497), mailers (u901478), Instagram video
(u902170), and speed-of-follow-up (u900497 — $3,000 → $44,000 GCI, 300% ROI).

### The corpus argues paid search fails for agents *specifically* — and names the mechanism

- **u902145** (eXp Realty US, "CRM of Choice" — verified provenance): *"Google's Google for everybody.
  So if you want to do Google pay-per-click and compete with Zillow and Realtor.com and dollar for
  dollar compete with those, it's not a great strategy."* This unit's own index literally lists the
  question **"Why is Google PPC no longer recommended?"**
- **u901612**: *"I'm not a big fan of pay-per-click… they tend to be lower quality because they're not
  hyper local and you're competing with the Zillow of the world."*
- **u900373**: *"93% of all real estate transactions do not come from Google lead source"* alongside
  *"85% of sales… are originated by agent communication."*

**This independently reproduces the external finding** (§5) that no verifiable case exists of a small
independent agent profitably winning listings from agent-finder keywords.

### The pro-paid-search cluster is targets, not outcomes

CPL figures cluster at **$3–$5** (u2957: *"assuming probably a lead would cost me about five dollars"*;
u2973: *"$5 per lead is a good cap to start with"*) — but these are **stated plans, not measured
results**, and they are US/general. Brain 1 flagged the 10¢ Facebook CPL (u900855) as **superseded**.
The strongest genuine intent argument is u3077: *"seven times more likely to close a lead who comes to
you via a search engine."*

Lead→transaction reality check (u900109): *"1 to 3% of internet leads… but still a 16 to 24 month to
convert."* That is consistent with the OpenAgent-derived 1–2% used in §7 — and the **16–24 month**
figure is *worse* than the 90-day Google attribution ceiling by an order of magnitude.

### Where the corpus backs something hardest: Google Business Profile, not Google Ads

This is the highest-confidence, lowest-cost finding in the brief:
- **u900673** — agents receiving *"inbound leads for free without even spending money on ads"*; profiles
  make you *"2.7 times more likely to see you as reputable."*
- **u900166** — GBP carries *"about 60 to 70% weight"* in local ranking.
- **u900171** — the review ladder: *"At 20 reviews, people start to find you credible. Over 50 reviews…
  the specialist. Over 100 reviews, you should be getting leads coming in organically."*

Converges exactly with BrightLocal (81% read reviews) in §5. **Both evidence bases independently say
the free surface outperforms the paid one for this exact query family.**

### Speed-to-lead is the binding constraint on any paid lead

Near-unanimous: u900380 *"The first person to get to a seller after an inquiry, 80 to 90% of the time is
winning the business"*; u902265 *"80 plus percent of all listings are won normally by the agent that
gets to the seller first"*; u900143 *"Almost 50% of real estate leads never get followed up with"*;
u900182 *"We don't have a lead generation challenge. We have a lead follow-up challenge."*

**Direct implication for Fields:** a paid lead that isn't wired into the existing high-intent Telegram
alert / Messenger webhook path is a purchased follow-up failure, not a lead. This is the same structural
point as §7's mail-step problem, from a different direction.

### The one paid-search play the corpus does endorse

**u902286** — the anti-portal wedge: *"they look for Zillow, but they see your ad, there's something
super compelling there. Something like maybe off-market listings, VIP buyer list, listings before they
appear on Zillow."* Don't out-*bid* the portals on generic terms — out-*offer* them with something the
portal structurally cannot show.

Fields is uniquely positioned here: the off-market discovery deck (~14.6k indexed pages) is exactly that
asset. Paired with **u900746** — *"An address is a signal. That's far more powerful than a cold lead…
generating three times more seller signals"* — which is a direct endorsement of the address-first AYH
capture we already run.

Landing-page principles (k00514 Karin Carr, k01898–k01900): single purpose, **no navigation**, short
copy, minimal form fields. Consistent with the Optmyzr/Unbounce data in §6. Benchmark from u3061: *"One
in 10 visitors become leads on the best real estate agent websites"* vs ~1% average — **our measured
4.7% sits between the two**, i.e. genuinely above average but not best-in-class.

### ⚠ Two provenance caveats on this brief

1. **The "4× engagement" claim is circular — do not cite it as evidence.** Brain 1 surfaced k02072
   (*"Fields Estate's own advertising data confirms that property-specific content — individual homes
   with specific prices and addresses — generates 4 times more engagement than generic market
   content"*) and called it *"the strongest evidence in the entire brief for what your creative should
   say."* Provenance check: `src.lib = KB:book`, `course = "Before You List — Fields seller book"`. **It
   is our own book, re-ingested.** This is the self-citation loop documented in
   `brain1_deep_query_tool`. The underlying claim may well be true, but it must be re-verified against
   actual Facebook ad data before it steers ad creative — it is not independent corroboration.
2. **One citation was auto-repaired.** The verifier flagged `u00514` as invented/malformed
   (55 cited, 51 in shortlist, 1 invented); the repair pass correctly remapped it to **k00514**, which
   is real (Karin Carr, *YouTube for Real Estate Agents*). The guard worked as designed.

### Brain 1's bottom line

> *"The corpus does not justify Google Ads as a primary lead engine, and its most credible voices
> actively warn against fighting the portals on paid search."*

It endorses instead: max the free GBP + reviews engine; use small paid buys as a **keyword-discovery
thermometer** feeding the owned-content moat (k01889: *"Can you afford to rent your marketing?"*); wire
any paid lead into sub-5-minute follow-up; and if bidding at all, carry the **off-market/pre-list offer**
on an address-first, navigation-free landing page.

**Corpus limitation to keep in view:** Brain 1 assumes a human agent doing agent work, and contains **no
Australian or Gold Coast paid-search benchmarks** — it states this itself. The $3–$5 CPL targets cannot
be assumed to transfer to Robina.

---

## Appendix — evidence provenance

- **First-party:** Google Ads API (account 997-572-4211) lifetime campaign/keyword/search-term/conversion-
  action reports; Keyword Planner API (Gold Coast geo `1000665`) volumes; `GenerateKeywordForecastMetrics`
  30-day forecasts; PostHog trends (AYH funnel); `system_monitor` lead collections.
- **External:** full cited review at `/tmp/.../scratchpad/web_research_ppc.md` — graded [A] measured /
  [B] anecdote / [C] vendor / [D] unsourced, with corrections to several circulating claims
  (the "2.7% real estate landing page" figure is **not in Unbounce's report**; "403% more inquiries with
  video" is a zombie stat; one AU source's "seller leads $15–20" is inverted from every other source).
- **Brain 1:** deep query complete — 560 relevant units carried across RealEstate_Gym (191), eXp Realty
  (US) (128), KB:book (110), Sell It (61), BLAC SALT (AU) (40), Agent School (20). See §9.
