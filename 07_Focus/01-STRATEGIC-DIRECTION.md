# Fields Real Estate — Strategic Direction & Goal Framework

> **Purpose:** Get crystal clear on where we're going, what milestones get us there, and what order to do things in. This document is the foundation — every daily work decision flows from it.
>
> **Date:** 2026-03-30
> **Status:** DRAFT — Will to review, challenge, confirm
> **Rule:** Nothing in this document is locked until Will explicitly confirms it.

---

## Part 1: Strategic Direction

### The Fork

Fields is at a decision point. The infrastructure is production-grade — 40K property database, comparable-sales valuations, AI editorial pipeline, automated content, advertising channels. The question isn't "can we build it?" — it's "build it for whom, and how do we get paid?"

Kara Johnson (industry consultant, March 18) laid out four paths. Here's the honest assessment of each:

| Path | Core Bet | Revenue Source | Time to First Dollar | Risk |
|------|----------|---------------|---------------------|------|
| **1. Platform-only** | Agents will pay for data tools | Agent subscriptions | 6-12 months | Competing with Domain, REA, PropTrack on their turf |
| **2. Buyer Advocacy** | Build buyer audience → become indispensable to sellers/agents | Seller reports, agent leads | 3-6 months | Requires proving buyer traffic converts to revenue |
| **3. In-house Sales** | Be the agent, use data as competitive moat | Commissions | 6-18 months | Will has no sales track record. Capital-intensive. |
| **4. Will as Agent** | Earn while learning | Commissions | 3-6 months | Slow, doesn't leverage the platform at all |

### Recommended Direction: Path 2 → Path 3

**Phase 1 (now → first revenue): Buyer Advocacy.**
Build the buyer audience. Prove that Fields can generate and warm leads at scale. Revenue from sellers wanting access to that audience (pre-sale reports, exposure) and agents wanting those leads.

**Phase 2 (after proof): In-House Sales.**
Once Fields has demonstrable buyer traffic and lead flow, recruit an experienced agent (part-time or subcontract). Fields becomes a sales agency with a data moat no competitor can replicate.

**Why this sequence:**
- Path 2 requires the least capital and no sales experience
- It tests the hardest assumption first: *can digital content generate real estate leads?*
- If Path 2 works, Path 3 becomes low-risk (recruit agent into proven lead flow)
- If Path 2 doesn't work, we learn that before committing to a sales agency

**The constraint that unlocks everything (Kara's insight):**
> "If you can find leads, you solve the hardest problem in this industry — the rest follows by default."

Every goal below is reverse-engineered from this constraint.

---

## Part 2: The Five Goals

These are ordered by dependency. Goal 1 enables Goal 2, which enables Goal 3, and so on. You can't skip ahead.

### Goal 1: Prove Buyer Demand Exists
**Target:** 200 unique weekly visitors engaging with property content by end of May 2026
**Metric:** PostHog weekly unique users on `/for-sale`, `/property/*`, `/market-metrics/*`, article pages
**Why this number:** 200 engaged weekly visitors is the minimum viable audience to test lead capture. Below this, conversion experiments are statistically meaningless.

**Current state:** ~130 weekly pageviews from Facebook (mostly `/for-sale` and articles), 4 from Google. Unknown unique visitor count — need PostHog weekly uniques dashboard.

**What must be true:**
- Facebook proof-led creative continues performing ($0.16/LPV)
- Weak ads are cut (generic, buy-angle — currently bleeding budget)
- Content is compelling enough for return visits
- SEO starts generating organic traffic (currently near-zero from Google)

---

### Goal 2: Capture Leads
**Target:** 20 captured buyer leads per month by end of June 2026
**Metric:** Email/phone submissions via website (new system to build)
**Why this number:** 20 leads/month is enough to test whether leads convert to revenue. It's also enough to show an agent partner "we have active buyer interest."

**Current state:** Zero lead capture exists. The website has no email collection, no CTA that captures contact details, no subscriber system. Visitors come, browse, leave.

**What must be true:**
- Goal 1 achieved (enough traffic to convert)
- Lead capture mechanism built (email gate on valuations? Subscribe for alerts? "Get notified when price drops"?)
- Value exchange clear — what does the buyer get for giving us their email?
- CRM or at minimum a leads collection in MongoDB

---

### Goal 3: Prove Lead Value
**Target:** 3 leads that result in a meaningful buyer conversation by end of July 2026
**Metric:** Leads contacted → responded → conversation happened
**Why this number:** Revenue partners (agents, sellers) need proof that Fields leads are real people with real intent, not just email addresses.

**Current state:** No leads exist to prove anything with.

**What must be true:**
- Goal 2 achieved (leads captured)
- Will or a partner agent contacts leads and has real conversations
- Feedback loop: what did the lead want? Were they serious? Would they engage further?
- This is the point where Will's "digital warm-up reduces cold-call friction" hypothesis gets tested

---

### Goal 4: First Revenue
**Target:** First paying customer (seller or agent) by end of August 2026
**Metric:** A$ received for a Fields service
**Why this number:** One is enough. It proves the model works. It doesn't matter if it's $500 or $5,000.

**Possible first products:**
- **Pre-sale valuation report** — seller pays $X for a comprehensive comparable-sales analysis with AI editorial (we can already generate this, just need packaging + payment)
- **Listing exposure package** — seller pays $X to feature their property in Fields content/ads
- **Lead referral** — agent pays per lead (requires Goal 3 proof)

**What must be true:**
- Goal 3 achieved (proven lead quality)
- At least one revenue product packaged and priced
- Payment mechanism (even a Stripe link is fine)
- Trust built — the customer believes Fields adds value they can't get elsewhere

---

### Goal 5: Repeatable Revenue Model
**Target:** 3+ paying customers by end of October 2026
**Metric:** Revenue from multiple distinct customers
**Why this matters:** One customer could be a favour. Three is a pattern.

**What must be true:**
- Goal 4 achieved
- Product refined based on first customer feedback
- Acquisition channel identified (how do sellers/agents find out about Fields?)
- Unit economics understood (cost to acquire customer vs revenue per customer)

---

## Part 3: Milestone Breakdown — Goal 1

Goal 1 is the immediate focus. Here are its milestones in dependency order:

```
M1.1: Measurement baseline (know where we are)
  │
  ├── M1.2: Ad optimisation (stop wasting spend)
  │
  ├── M1.3: Content engine (give visitors a reason to come back)
  │
  └── M1.4: SEO foundation (earn free traffic from Google)
        │
        └── M1.5: Traffic target hit (200 weekly uniques)
```

### M1.1 — Measurement Baseline
**Status:** Partially done
**What:** Set up PostHog dashboards that answer:
- How many unique visitors per week? (not just pageviews)
- Where do they come from? (Facebook paid, Facebook organic, Google, direct)
- What do they look at? (which pages, how deep)
- Do they come back? (return visitor rate)
- Where do they drop off? (bounce rate by landing page)

**Steps:**
1. Create PostHog dashboard: "Weekly Acquisition" — unique users by source, by page
2. Create PostHog dashboard: "Engagement Depth" — pages per session, return rate, time on site
3. Baseline current numbers (this week = week zero)
4. Set up weekly Telegram digest of key metrics

**Owner:** AI can build dashboards and set up Telegram digest. Will reviews.
**Effort:** 1 session

---

### M1.2 — Ad Optimisation
**Status:** CEO agents have identified the moves, not yet executed
**What:** Reallocate ad budget from proven losers to proven winners.

**Steps:**
1. **Pause weak Facebook ads** — generic creative, buy-angle ads, anything >$0.50/LPV
2. **Scale proof-led creative** — property-specific stories performing at $0.16/LPV
3. **Reduce Google Ads** to minimum maintenance — $20.42/pageview vs Facebook $0.90 is unacceptable
4. **Redirect saved budget** to top 3 Facebook proof creatives
5. **Set up weekly ad performance review** — automated report comparing creative performance

**Owner:** AI can identify which ads to pause/scale (metrics are collected). Will approves changes. AI executes via ad manager scripts.
**Effort:** 1 session for audit + changes, then weekly maintenance

---

### M1.3 — Content Engine
**Status:** Infrastructure exists, cadence is inconsistent
**What:** Regular, compelling content that gives visitors a reason to return.

**Steps:**
1. **Weekly article cadence** — 1 new article per week minimum (AI-generated, Will-reviewed)
2. **Article topics from search intent** — use `search-intent-collector.py` data to write what people actually search for
3. **Property editorial backlog** — ensure every new listing gets AI analysis within 48h of scrape
4. **Facebook post quality** — audit the 14 organic templates, retire underperformers, add proof-led variants

**Owner:** AI generates articles and editorials. Will reviews before publish. AI manages Facebook post scheduling.
**Effort:** Ongoing — 1-2 hours/week of Will's time for review

---

### M1.4 — SEO Foundation
**Status:** Near-zero organic Google traffic (4 visits last week)
**What:** Make Google send us free traffic for Gold Coast property searches.

**Steps:**
1. **Index audit** — are key pages indexed? Use Google Search Console (or set up if not connected)
2. **Meta tags + structured data** — ensure property pages have correct schema.org markup
3. **Target keywords** — "Robina property prices", "Burleigh Waters real estate market", "Gold Coast property valuation" — are we ranking?
4. **Internal linking** — articles should link to property pages and market metrics
5. **Page speed** — check Core Web Vitals, fix any blockers
6. **Google indexing API** — `scripts/google_indexing.py` exists but may not be active

**Owner:** AI can audit and implement technical SEO. Will decides target keywords and content angles.
**Effort:** 2-3 sessions for foundation, then ongoing

---

### M1.5 — Traffic Target
**Status:** Not started (depends on M1.1-M1.4)
**What:** Hit 200 unique weekly visitors consistently (3 consecutive weeks).

**Tracking:** PostHog dashboard from M1.1
**Timeline:** End of May 2026 (8 weeks from now)
**Decision point:** If we're at 150+ by mid-May, stay the course. If below 100, reassess ad strategy or content approach.

---

## Part 4: Goal 2 Milestone Breakdown (Preview)

Not fully decomposed yet — depends on Goal 1 progress. But the shape is:

```
M2.1: Design lead capture mechanism (what do we offer in exchange for email?)
  │
  ├── M2.2: Build lead capture UI (subscribe, alerts, gated content)
  │
  ├── M2.3: Build lead storage + notification (MongoDB + Telegram alert to Will)
  │
  └── M2.4: Optimise conversion (A/B test capture placements)
        │
        └── M2.5: 20 leads/month target hit
```

**Lead capture hypotheses to test:**
- "Get notified when this property's price drops" (property-level alert)
- "Free valuation for your property" (seller lead capture — the big one)
- "Weekly market update for [suburb]" (subscriber capture)
- "See the full valuation breakdown" (gate valuation detail behind email)

Each of these has different trade-offs. Gating content reduces trust but captures leads. Open content builds audience but captures nothing. The right answer is probably: keep most content free, gate the highest-value item (full valuation report or price drop alerts).

---

## Part 5: The Reasoning Framework

This is how we decide "what should Will do in the next 2 hours?"

### Decision Rules (in priority order)

1. **Is something on fire?** Pipeline down, website broken, ad account suspended → fix it now.

2. **Is there a grind task overdue?** Email unanswered >48h, accounting not reconciled this month, ad performance not reviewed this week → do it now. Grind debt compounds.

3. **What is the current goal?** (Goal 1, 2, 3, 4, or 5)

4. **What is the current milestone within that goal?** (M1.1, M1.2, etc.)

5. **What is the next uncompleted step within that milestone?**

6. **Can AI do this step, or does Will need to?**

| If AI can do it | If Will must do it |
|----------------|-------------------|
| AI does it now or queues it | This is Will's next 2-hour block |
| Will reviews output when ready | AI prepares context/materials first |

7. **Is Will about to start something not mapped to any milestone?**
   - If yes → conscious choice: "I'm choosing to explore [X] instead of working on [milestone step Y]. I accept this delays the goal by ~[time]."
   - Not forbidden. Just visible.

### The AI's Role in This Framework

The AI (this agent, the chat agent, and the CEO agents) serves three functions:

**Navigator:** "Based on goals, milestones, and current state — here's what matters most right now."

**Executor:** "I can do steps X, Y, Z autonomously. Here are the results for your review."

**Mirror:** "You asked me to work on [new thing]. That's not mapped to any active milestone. Want to add it as a goal, park it, or continue knowing it's off-plan?"

The AI never blocks Will from doing what he wants. It makes the trade-off visible. That's the difference between a nag and a navigator.

---

## Part 6: What AI Does vs What Will Does

### AI Handles Autonomously (With Review)
- Article generation and fact-checking
- Ad performance analysis and pause/scale recommendations
- Pipeline monitoring and repair
- PostHog dashboard creation and metric tracking
- SEO technical audit and implementation
- Facebook organic post scheduling
- Email triage and draft responses
- Database maintenance and enrichment
- CEO agent proposal synthesis
- Weekly progress reports against milestones

### Will Must Do (AI Prepares)
- **Confirm strategic direction** (this document)
- **Set and revise goals** (quarterly)
- **Review and approve content** before publish
- **Approve ad changes** before execution
- **Contact leads** — real conversations with real people
- **Record videos** (if YouTube hypothesis is tested)
- **Meet agents/industry contacts** (relationship building)
- **Make pricing decisions** (what to charge, who to charge)
- **Approve revenue products** before launch

### Grey Zone (Discuss Case-by-Case)
- Writing the first pre-sale report (AI drafts, Will shapes)
- Designing lead capture UX (AI prototypes, Will decides)
- Recruiting agent partners (AI identifies candidates, Will has conversations)
- YouTube content strategy (AI researches, Will decides if and when)

---

## Part 7: The Pattern for Every Session

When Will opens a session, the workflow is:

```
1. ORIENT     → Read OPS_STATUS, check fires, check grind debt
2. LOCATE     → Where are we on the goal/milestone/step map?
3. RECOMMEND  → "Here's the highest-leverage thing for the next 2 hours"
4. CONFIRM    → Will agrees, redirects, or chooses something else
5. EXECUTE    → Do the work
6. LOG        → Update milestone progress, fix history if needed
7. PUSH       → GitHub
```

If Will chooses something different from the recommendation, that's fine — but the system logs it. Over time, the pattern of diversions reveals what Will actually values vs what the plan says he should value. That's useful data for the next goal-setting session.

---

## Part 8: Confirmed Answers (2026-03-30)

1. **Goal 1 → 5 sequence:** ✅ Confirmed correct.

2. **200 weekly uniques by May:** ✅ Achievable, probably more. Will is confident.

3. **YouTube:** Launching May 2026 — after Facebook rhythm and lead capture established. Strategy documented in `07_Focus/04-YOUTUBE-CHANNEL-STRATEGY.md`.

4. **Grind backlog (sized):**
   - PAYG amount due
   - 2025 tax return not submitted (overdue)
   - 46 Balderstone St rental (Ray White): all emails need recording, expenses tracked, invoices captured, ledger maintained
   - Bank reconciliation needed across 3 entities
   - WISE bank account data feed needs integration
   - API spend tracking needed: Anthropic, Google, OpenAI billing APIs
   - Emails not being checked regularly
   - Email → accounting pipeline needed (invoices from emails → ledger)

5. **Sprint framework:** ✅ Willing to test. Wants daily checkpoints modelled on Jim Collins' "20 Mile March" (Great by Choice) — Antarctic explorers who succeeded set achievable daily distances and hit them every day regardless of conditions. Each day is a checkpoint. Consistency compounds. Needs frequent review and adjustment.

6. **Runway / Timeline:**
   - **Q3 2026 (July-September):** Must have serious market interest or actual listings. If not, Will starts to lose hope.
   - **Q4 2026 (October-December):** If no traction by Q4, the business is in real trouble.
   - This is NOT open-ended. Every sprint must advance toward leads and listings by Q3.

---

## Part 9: What Happens Next

All strategic questions are answered. The planning phase is complete. What follows is execution:

1. **Build the sprint/checkpoint framework** — design what a week looks like, what daily checkpoints are, how progress is tracked
2. **Design Sprint 1** — the first week of checkpoints, mapped to Phase A of the battle plan (lead capture) + grind blocks
3. **Start building** — lead capture, content brief generator, Decision Feed completion
4. **Every session from now on:** ORIENT → LOCATE → RECOMMEND → CONFIRM → EXECUTE → LOG → PUSH
