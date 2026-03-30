# Leads Battle Plan — Every Resource Pointed at One Problem

> **The problem:** Can digital content generate real estate leads?
> **If yes:** Everything else follows. Revenue, agents, scale.
> **If no:** We learn that fast and pivot.
>
> **Date:** 2026-03-30
> **Status:** CONFIRMED DIRECTION — Will approved Phase 1 (Buyer Advocacy) and Phase 2 (In-House Sales)

---

## The Arsenal (What We're Working With)

Before sequencing the work, here's the honest inventory — what's loaded, what's half-built, what's unused.

### Weapons That Are Firing

| Asset | Status | Lead Generation Role |
|-------|--------|---------------------|
| **Facebook property-story ads** | Live, $0.16/LPV | Best acquisition channel. Proven: property-specific stories outperform generic 4x. |
| **101 published articles** | Live, 974 events tracked | Content that builds authority. "Domain Valuation Accuracy" (1,689 properties) is a trust nuke. |
| **Organic Facebook posts** | 2x/day, 15 templates | Consistent brand presence. Morning + evening rhythm established. |
| **Nightly data pipeline** | 37/37 steps healthy | Fresh data every day. 100% enrichment on core suburbs. |
| **AI editorial pipeline** | Multi-agent, fact-checked | Unique property analysis no competitor has. |
| **Valuation engine** | Comparable-sales, confidence-rated | The core value prop: "we know what this property is worth, and we'll tell you free." |

### Weapons Half-Built (High Potential, Need Finishing)

| Asset | What Exists | What's Missing | Lead Gen Impact |
|-------|------------|----------------|-----------------|
| **Decision Feed** (`/for-sale-v2`) | 13 React components, Netlify function, live mockup | Backend data integration, AI editorial fields (feed_hook, feed_catch, feed_quiz), view counts | **HIGH** — purpose-built for Facebook discovery traffic. Replaces the 95%-bounce article landing. |
| **Lead capture** | `LeadCapture.tsx` component, `analyse_leads` collection (1 record) | No systematic capture on property pages, no price-drop alerts, no email collection | **CRITICAL** — we drive traffic but capture nothing. This is the #1 gap. |
| **Search intent data** | 7 sources, 12,000+ signals, 4,459 PAA questions | Analysis only run twice. Content gaps identified but not filled. | **MEDIUM** — tells us exactly what people search for. Unfilled = free traffic left on the table. |
| **Marketing advisor** | Claude-powered decision engine, 48KB script | Not run regularly, recommendations not executed | **MEDIUM** — could automate ad optimisation decisions. |
| **A/B experiments** | PostHog flags set up, 2 website experiments | Both stuck at "early_blocked" — not enough traffic for significance | **LOW until traffic grows** — need volume first. |

### Weapons Not Yet Deployed

| Asset | What It Could Do | Blocker |
|-------|-----------------|---------|
| **"Analyse Your Home" page** | Seller lead capture — the big conversion | No form submission → lead notification workflow |
| **Price drop alerts** | "Get notified when this property drops" = buyer intent capture | Not built |
| **Suburb weekly digest** | "Get Robina's weekly market update" = subscriber capture | Not built |
| **Valuation reports** | Downloadable pre-sale analysis = seller lead magnet | Template not designed |
| **Google Ads high-intent keywords** | "houses for sale robina" = 1,300/mo searches | Running but expensive ($20/pageview vs FB $0.90). Needs landing page optimisation. |
| **YouTube** | Video warm-up hypothesis (Kara endorsed) | No channel exists. Parks until leads proven via existing channels. |

---

## The Funnel We're Building

```
                    AWARENESS
                    ─────────
        Facebook Ads (property stories)
        Google Ads (high-intent keywords)
        Organic Facebook (2x/day)
        SEO (articles targeting search intent)
                       │
                       ▼
                   ENGAGEMENT
                   ──────────
        Decision Feed (/for-sale-v2)         ← Facebook traffic lands here
        Property pages (/property/:id)       ← Deep-dive after feed card
        Market articles (/articles/:slug)    ← SEO traffic lands here
        Market metrics (/market-metrics/)    ← Data-curious visitors
                       │
                       ▼
                    CAPTURE
                    ───────
        "Get notified when price drops"      ← Buyer intent (property-level)
        "Analyse your home"                  ← Seller intent (high value)
        "Weekly suburb market update"        ← Subscriber (nurture)
        Decision Feed lead capture CTA       ← Post-trust (after viewing 5+ cards)
                       │
                       ▼
                   CONVERSION
                   ──────────
        Email nurture sequence               ← Keep leads warm
        Personal outreach (Will)             ← High-intent leads
        Pre-sale report offer                ← Seller leads
        Agent referral                       ← Future: connect buyers to agents
```

Today we have the top of this funnel working (awareness → some engagement). The middle is broken (engagement doesn't lead to capture) and the bottom doesn't exist. The battle plan fixes this top-to-bottom.

---

## Sequenced Work Plan

### Phase A: Fix the Capture Layer (Week 1)
**Why first:** We're driving traffic right now and capturing nothing. Every day without capture = wasted ad spend.

#### A1. Property page lead capture — "Price drop alert"
**What:** Add an email capture to every property page: "Get notified if this property's price changes."
**Why this specific CTA:** It's the lowest-friction capture. Buyer is already looking at a property. The value exchange is obvious — "we'll watch this for you." No commitment, no spam feeling.
**Technical:**
- New component on PropertyPage (email input + suburb + property ID)
- Store in `system_monitor.leads` with `{email, property_id, suburb, source: "price_alert", created_at}`
- Telegram notification to Will on every new lead
- Simple — no email verification, no complex flows. Capture first, optimise later.
**Owner:** AI builds, Will reviews placement and copy.

#### A2. "Analyse Your Home" form completion
**What:** The page exists at `/analyse-your-home` but submissions need to → lead notification.
**Why:** This is the seller lead capture. Someone clicking "Analyse Your Home" is expressing seller intent — the highest-value lead type.
**Technical:**
- Ensure form submission writes to `system_monitor.leads` with `{source: "analyse_home", address, email, ...}`
- Telegram alert to Will immediately
- Auto-acknowledge email: "We've received your request. Will from Fields Estate will be in touch within 24 hours."
**Owner:** AI builds, Will writes the acknowledgement copy.

#### A3. Decision Feed lead capture integration
**What:** The LeadCapture component exists in DecisionFeed but needs backend wiring.
**Why:** The Decision Feed is designed to build trust through the scroll, then convert at the end. The CTA appears after the user has seen 5+ cards and built confidence in Fields' analysis.
**Technical:**
- Wire `LeadCapture.tsx` to write to `system_monitor.leads`
- CTA copy: "Want this analysis for your property?" (ties into Analyse Your Home)
- Same Telegram notification flow
**Owner:** AI builds.

**Phase A deliverable:** Three lead capture points live. Every lead → Telegram notification to Will within seconds.

---

### Phase B: Finish the Decision Feed (Week 1-2)
**Why second:** This is our best weapon for converting Facebook discovery traffic into engaged visitors. The current `/for-sale` page bounces 95% of Facebook traffic. The Decision Feed is purpose-built to fix that.

#### B1. AI editorial field generation for feed cards
**What:** Generate `feed_hook`, `feed_catch`, `feed_best_for`, `feed_quiz` fields for active listings.
**Why:** The Decision Feed cards need one-line hooks ("$180K under comparable sales in Robina") and quiz questions. Without these, cards fall back to generic property data — which defeats the purpose.
**Technical:**
- Extend `generate_property_ai_analysis.py` or create a lightweight feed-field generator
- Target: all properties with `valuation_data` in core suburbs (currently ~126)
- Fields needed: `feed_hook` (1 line), `feed_catch` (what's the trade-off), `feed_best_for` (buyer profile), `feed_quiz` (question + 4 answers)
**Owner:** AI builds and runs. Will reviews sample output.

#### B2. Backend data integration
**What:** Connect Decision Feed React components to the `decision-feed.mjs` Netlify function with live data.
**Why:** The mockup is static HTML. The components exist but aren't wired to real data.
**Technical:**
- Debug/complete `decision-feed.mjs` → returns ranked feed with all card types
- Wire `DecisionFeedPage` to fetch from API
- Test with real property data from core suburbs
**Owner:** AI builds.

#### B3. View count integration
**What:** Show "X views this week" on feed cards (social proof).
**Why:** Social proof drives engagement. "327 people looked at this property this week" creates urgency.
**Technical:**
- PostHog event aggregation or simple counter in MongoDB (increment on property page view)
- Display in FeedCard component
**Owner:** AI builds.

#### B4. Facebook ad routing
**What:** Point best-performing Facebook ads at `/for-sale-v2` instead of `/for-sale` or article pages.
**Why:** This is the conversion test. If Decision Feed retains Facebook traffic better than the grid page (target: <50% bounce vs current ~95%), we've found the engagement layer.
**Technical:**
- Update ad URLs for top 3 property-story campaigns
- Set up PostHog comparison: `/for-sale` vs `/for-sale-v2` bounce rate, time on page, scroll depth
**Owner:** AI prepares ad changes, Will approves before execution.

**Phase B deliverable:** Decision Feed live with real data, Facebook traffic routed to it, engagement metrics tracked.

---

### Phase C: Scale What Works (Week 2-3)
**Why third:** By now we have capture points and a better landing page. Time to increase volume.

#### C1. Ad budget reallocation
**What:** Cut all ads performing >$0.50/LPV. Redirect budget to proof-led property stories.
**Current waste:** 42.9% of spend ($222/$518 in last audit) produced zero sessions.
**Action:**
- Run `ad-review-dump.py --active` for current performance
- Pause losers, scale winners
- Create 3 new property-story ads using the template that works
**Owner:** AI audits and recommends. Will approves changes. AI executes.

#### C2. Content gap filling from search intent
**What:** Match the 4,459 People Also Ask questions against our 101 articles. Publish articles for the highest-volume gaps.
**Why:** Free Google traffic for questions people are already asking. "Does Burleigh Waters flood?" has 44x autocomplete volume and we have the data.
**Action:**
- Run `search-intent-analyser.py` to identify top 10 content gaps
- Generate articles for top 5 gaps (AI writes, Will reviews)
- Publish via `push-ghost-draft.py`
**Owner:** AI identifies gaps and drafts articles. Will reviews and approves publish.

#### C3. Google Ads landing page test
**What:** Test routing Google Ads to Decision Feed instead of article pages.
**Why:** Google Ads are expensive ($20/pageview) partly because landing pages bounce. If Decision Feed retains better, cost per engaged visitor drops.
**Owner:** AI sets up, Will approves.

#### C4. Organic Facebook proof-led templates
**What:** Add property-story templates to the organic 2x/day scheduler.
**Why:** If proof-led works in paid, it should work in organic. Currently organic uses 15 templates but none are property-specific stories.
**Action:**
- Create 2-3 new organic templates based on the "Someone bought this X months ago" format
- Add to `fb-content-scheduler.py` rotation
**Owner:** AI builds templates. Will reviews tone.

**Phase C deliverable:** Ad spend optimised, content gaps being filled, organic content upgraded.

---

### Parallel Track: Backup Scraper — Data Insurance (Week 1 onwards, AI-independent)

**CRITICAL RISK:** The entire Fields data pipeline depends on Domain.com.au access. If Domain improves bot detection and blocks us, we lose all property data overnight. This is an existential risk to the business — no data = no valuations = no content = no leads = nothing.

**The backup scraper** runs on a separate VM (35.201.6.222) and scrapes agent websites and other sources directly. It MUST NOT source any data from Domain.com.au. It exists specifically as insurance against Domain blocking us.

**Target:** 80%+ of Robina listing coverage compared to our current Domain scraper, using zero Domain data.

**Current state:** Running but operationally thin — HTTP 403 errors from some agencies, no structured health monitoring, 98MB unrotated log, limited coverage.

**This is an AI-independent workstream.** It runs in parallel with everything else. Will doesn't need to be involved until it's working. The AI (CEO Engineering agent + Claude Code sessions) can develop this autonomously because:
- It has SSH access to the backup scraper VM
- It has access to the Gold Coast database to compare coverage
- The success metric is objective: does the backup scraper find 80%+ of the Robina listings that Domain finds?
- No brand, product, or budget decisions involved — pure engineering

#### Backup Scraper Milestones

```
BS1: Audit current state (what works, what's broken, what agencies are blocked)
  │
BS2: Fix blocked agency scrapers (resolve 403s, add new agency sources)
  │
BS3: Robina coverage sprint — target 80% of Domain's Robina listings
  │     Measure: compare backup_scraper Robina URLs vs Gold_Coast.robina active listings
  │
BS4: Automated coverage comparison (daily report: backup vs primary, gap %)
  │
BS5: Expand to Burleigh Waters + Varsity Lakes (same 80% target)
  │
BS6: Failover-ready — if Domain goes dark, backup can sustain data pipeline
```

**Owner:** AI works on this independently. CEO Engineering agent monitors progress and proposes improvements daily. Claude Code sessions can SSH to the VM and develop.

**Sprint integration:**
- Sprint 1: BS1 (audit) — AI does this as background work
- Sprint 2-3: BS2-BS3 (fix agencies, Robina coverage sprint)
- Sprint 4-5: BS4 (automated comparison)
- Sprint 6+: BS5-BS6 (expand suburbs, failover-ready)

**Success metric:** When Domain goes down (not if — when), we can keep the pipeline running on backup data within 24 hours. That's the insurance policy.

**CEO Engineering agent directive addition:** "Monitor backup scraper health daily. Report coverage comparison: backup vs primary for Robina. Propose specific fixes for blocked agencies. This is a standing priority — data survival depends on it."

---

### Phase D: Measure and Iterate (Week 3-4)
**Why last:** By now we have enough data to make decisions.

#### D1. Lead quality assessment
**What:** Will contacts every captured lead. Were they real? What did they want? Would they engage further?
**Why:** 20 email addresses mean nothing if none are real buyers. This is the human step AI can't do.
**Owner:** Will only.

#### D2. Funnel analysis
**What:** Trace the full path: ad click → landing page → engagement → capture. Where do people drop off?
**Technical:**
- PostHog funnel: Facebook click → Decision Feed scroll → property page → lead capture
- Identify the biggest leak
**Owner:** AI builds dashboard. Will reviews.

#### D3. Decision Feed A/B refinement
**What:** Based on 3 weeks of data, adjust card ordering, copy, and CTA placement.
**Owner:** AI analyses data and proposes changes. Will decides.

#### D4. Weekly marketing advisor runs
**What:** Activate `marketing-advisor.py` on a weekly cadence. AI reviews all data, proposes next moves.
**Owner:** AI runs weekly, writes recommendations. Will reviews and approves.

---

## What AI Does vs What Will Does

### AI Handles (This Week)

| Task | How |
|------|-----|
| Build price-drop alert component | Code + deploy |
| Wire Analyse Your Home form → leads collection | Code + deploy |
| Wire Decision Feed lead capture | Code + deploy |
| Generate feed_hook/feed_catch fields for core suburb listings | Run editorial pipeline extension |
| Connect Decision Feed to live backend data | Code + deploy |
| Run ad performance audit | `ad-review-dump.py` |
| Identify top 10 content gaps | `search-intent-analyser.py` |
| Draft 5 articles for content gaps | AI generation + fact-check |
| Set up PostHog funnel dashboard | API calls |
| Configure Telegram lead notifications | Script |

### Will Handles (This Week)

| Task | Why Only Will |
|------|--------------|
| Review and approve lead capture copy/placement | Brand voice |
| Review and approve ad changes before execution | Budget decisions |
| Write "Analyse Your Home" acknowledgement email copy | Personal touch |
| Review Decision Feed with real data — does it feel right? | Product judgement |
| Review 5 drafted articles before publish | Editorial standards |

### Will Handles (Weeks 2-4)

| Task | Why Only Will |
|------|--------------|
| Contact every captured lead personally | Relationship building — the human part |
| Assess lead quality — real buyers or noise? | Judgement call |
| Decide: is digital lead gen working? | Strategic direction |
| Approve weekly marketing advisor recommendations | Budget + brand |

---

## Success Criteria (4-Week Check)

| Metric | Target | How We Measure |
|--------|--------|---------------|
| **Leads captured** | 20+ total across all capture points | `system_monitor.leads` count |
| **Decision Feed bounce rate** | <50% (vs ~95% on current `/for-sale`) | PostHog comparison |
| **Decision Feed scroll depth** | >40% reach card 5 | PostHog scroll tracking |
| **Ad cost efficiency** | <$1.00/engaged session (down from $2.31) | Facebook metrics |
| **Lead quality** | At least 3 leads respond to Will's outreach | Manual assessment |
| **Content from search intent** | 5+ new articles published targeting gaps | Article count |

If we hit these numbers, we've answered the question: **yes, digital content can generate real estate leads.** Then we move to Goal 2 (scale to 20/month) and Goal 3 (prove lead value through real conversations).

If we don't hit them, we'll know exactly where the funnel breaks and can adjust.

---

## The Reasoning Behind This Sequence

**Why capture before content?** Because we're already spending money driving traffic. Every day without capture = wasted spend. Capture first, even if imperfect.

**Why Decision Feed before SEO?** Because Decision Feed converts existing paid traffic better. SEO is slower (months to rank) and we need signal now.

**Why ad optimisation in Phase C not Phase A?** Because reallocation only matters if we have a good landing page. Sending more traffic to a page that bounces 95% just burns money faster.

**Why Will contacts leads personally?** Because the hypothesis isn't just "can we capture emails" — it's "can digital content create a warm enough relationship that a stranger will talk to us about their property?" That requires a human.

---

## Physical Mail — Quarterly Market Update Report

### The Decision

Two options for getting physical mail into homes:

| | Option A: Broad Mail (1,000-3,000 homes) | Option B: Warm Leads First |
|---|---|---|
| **What** | Quarterly market update report mailed to every home in target streets/suburbs | Mail only to people who've engaged digitally — Analyse Your Home submissions, price alert signups, email subscribers |
| **Cost** | ~$1.50-$3.00/piece (print + postage) = $1,500-$9,000/quarter | ~$0-$50/quarter initially (handful of leads), scales with audience |
| **Audience size** | 1,000-3,000 from day one | 0-50 initially, growing as digital capture works |
| **Targeting** | Geographic (every house on these streets) — most recipients won't care | Behavioural (already expressed interest) — every recipient is warm |
| **Brand effect** | High visibility in suburb, establishes presence even to uninterested | Low visibility, but high conversion potential per piece |
| **Data capture** | QR code / URL on report → measures who responds | Already captured — mail reinforces existing relationship |
| **Risk** | Significant spend before digital leads are proven. If nobody scans the QR code, you've learned nothing actionable. | Tiny audience means tiny impact. Doesn't build broad awareness. |

### Recommendation: Option B First, Option A Later

**Start with warm leads only.** Here's why:

1. **We haven't proven digital capture yet.** Broad mail before we know our digital funnel works is spending money based on hope. The whole strategy is: prove digital leads work first, then scale.

2. **The report itself becomes a conversion tool, not a spray tool.** Someone submits "Analyse Your Home" → they get a personalised market report in the physical mail 3-5 days later. That's a powerful touch. It says: "We actually did the analysis. Here's a physical report for your suburb. Call us."

3. **Cost discipline.** Pre-revenue, every dollar matters. $1,500-$9,000/quarter on broad mail is significant. $50/quarter on warm leads is negligible — and each piece has a much higher chance of converting.

4. **Broad mail works better when people already know the brand.** If someone has seen Will's face on YouTube and Facebook, then gets a Fields market report in the mail, the recognition compounds. If they've never heard of Fields, the report goes in the bin with the pizza flyers.

5. **We can still design the report now.** The quarterly market update report is worth designing regardless — it becomes:
   - A follow-up mailer for warm digital leads (Option B)
   - The Analyse Your Home deliverable (seller lead magnet)
   - A downloadable PDF on the website (content asset)
   - A future broad-mail piece once brand awareness exists (Option A, Q4 or later)

### The Trigger for Broad Mail

Move to Option A (broad mail) when:
- Digital capture is producing 20+ leads/month (Goal 2 achieved)
- YouTube + Facebook have built suburb-level brand recognition
- We know which streets/areas generate the most digital engagement (geo-target the mail)
- There's a revenue product ready (so the mail has a clear CTA beyond "visit our website")

At that point, broad mail becomes a multiplier on an already-working digital funnel, not a substitute for one.

### Digital Market Report — Launch Now as Lead Magnet

We don't need to wait for physical mail. AI can design and produce a digital quarterly market report now — advertise it on Facebook as a downloadable PDF. This becomes:

1. **A lead capture mechanism.** "Download the Q1 2026 Gold Coast Market Report — free" → email gate → lead captured.
2. **A Facebook ad creative.** The report itself is the content piece we promote. Property-story ads work at $0.16/LPV — a high-quality market report ad could perform similarly.
3. **A warm-lead follow-up asset.** Anyone who downloads the digital version is a warm lead. Later, when physical mail is ready, we mail them the next edition.
4. **Proof of authority.** A well-designed market report with real data, original analysis, and Fields branding is the single best credibility piece we can produce.

**Production:** AI pulls all data from pipeline (median prices, sales volumes, trends, notable sales, market direction indicators), generates the report content, produces the PDF. Will reviews and adds personal commentary. Can be done in 1-2 sessions.

**Facebook promotion:** "The Q1 2026 Gold Coast Market Report is out. We analysed every sale in Robina, Burleigh Waters, and Varsity Lakes. Download free → [link to gated landing page]."

**CEO agents should research:** What market report formats get the highest download rates? What do the best property market reports look like (CoreLogic, SQM, PropTrack)? What lead-magnet PDF benchmarks exist for local businesses?

**Add to Sprint 2-3 build list.**

### Physical Mail Report — Design for Later

The quarterly market update report itself should be designed in Sprint 4-5:

**Content (AI generates, Will reviews):**
- Suburb-level data: median price, sales volume, days on market, price trends
- 3-5 notable sales with brief analysis
- Market direction indicators (leading/lagging data)
- One opinion piece from Will (2-3 paragraphs)
- QR code → fieldsestate.com.au/analyse-your-home (seller capture)
- QR code → fieldsestate.com.au/market-metrics/[suburb] (engagement)

**Format:** A4 folded, 4-6 pages, professional print. Fields branding.

**Production:** AI pulls all data, generates the report content, designs the layout template. Will reviews, adds personal commentary, approves print.

**Schedule:** Produce Q2 report in June (when we have enough data + leads to make it worthwhile).

### Decision Needed From Will

**Confirm: start with warm leads only (Option B), design the report, move to broad mail when digital leads are proven?**

Or if Will feels strongly about broad mail sooner, we can plan a test: 200 homes in one target street, measure response rate, decide based on data.

---

## What Happens After Week 4?

If leads are flowing:
- Scale ad spend on winning creative
- Build email nurture sequence
- Design pre-sale report product (first revenue opportunity)
- Start YouTube (already planned for May)
- Design quarterly market report for warm lead follow-up

If leads aren't flowing:
- Diagnose: is it traffic (not enough people)? Engagement (they come but don't stay)? Capture (they stay but don't convert)?
- Adjust the weakest link
- Consider Kara's suggestion: Will works part-time at an existing agency to learn what buyers actually respond to
- Consider small broad-mail test (200 homes) as an alternative lead channel

Either way, we'll know more in 4 weeks than we know now. That's the point.
