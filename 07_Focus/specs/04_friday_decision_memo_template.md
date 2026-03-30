# Friday Decision Memo Template

## Header
- **Date:**
- **Owner:**
- **Week:**
- **Goal of the week:**

## Decision Rules
- **Double-down:** Surface beats target, quality is acceptable, and no major guardrail breaks.
- **Continue:** Surface shows enough promise to keep running, but not enough to scale yet.
- **Cut:** Surface misses threshold badly enough that keeping it live is not worth the distraction.
- **Defer:** Do not decide yet because sample size, traffic, or instrumentation is not good enough.

## Minimum Evidence Rule
- Do not make a hard decision on a surface if tracking is broken.
- Do not make a hard decision if the surface has not hit its minimum review sample.
- If minimum sample is not met, default to `defer`, not `cut`.

## Weekly Snapshot
- **Traffic into buyer proof surfaces:**
- **Traffic into seller surfaces:**
- **Total leads captured this week:**
- **Any tracking gaps:**
- **Any major UX changes shipped mid-week:**

## Surface Scorecard

### 1. Track This Property
- **Surface:** Property-page inline email capture
- **Minimum review sample:** 200 module views
- **Primary metric:** submit conversion rate from module views
- **Secondary metrics:** submit count, email confirmation / reply rate, return visits to tracked property
- **Guardrails:** property-view rate, page bounce, complaints/unsubscribes

**Decision thresholds**
- **Double-down:** `>= 5%` submit conversion, `>= 15` submits for the week, and no meaningful drop in property-page engagement
- **Continue:** `3% to 4.9%` submit conversion and guardrails stable
- **Cut:** `< 2%` submit conversion after minimum sample, or property-page engagement drops by `> 10%`
- **Defer:** fewer than `200` module views, or tracking incomplete

**This week**
- Module views:
- Submit conversion:
- Submit count:
- Guardrail read:
- Decision:
- Why:

### 2. Analyse Your Home
- **Surface:** Dedicated seller capture page
- **Minimum review sample:** 80 page visits
- **Primary metric:** submit conversion rate from page visits
- **Secondary metrics:** qualified seller lead count, reply rate, booked call rate
- **Guardrails:** bounce rate, rage-click / abandonment signals, traffic source quality

**Decision thresholds**
- **Double-down:** `>= 6%` submit conversion and `>= 5` qualified seller leads in the week
- **Continue:** `3% to 5.9%` submit conversion, or lower volume with strong lead quality
- **Cut:** `< 2%` submit conversion after minimum sample, or lead quality clearly weak
- **Defer:** fewer than `80` visits, or seller traffic was not intentionally routed there

**This week**
- Page visits:
- Submit conversion:
- Qualified leads:
- Reply / booked-call rate:
- Decision:
- Why:

### 3. Embedded Seller CTA On Buyer Proof Surfaces
- **Surface:** Owner-focused module on property pages, articles, or suburb proof rails
- **Minimum review sample:** 150 module views
- **Primary metric:** submit conversion rate from module views
- **Secondary metrics:** seller lead count, assisted visits to `/analyse-your-home`
- **Guardrails:** article read depth, property-page progression, CTA blindness from repeat exposure

**Decision thresholds**
- **Double-down:** `>= 4%` submit conversion and proof-surface engagement stays flat or improves
- **Continue:** `2% to 3.9%` submit conversion with stable guardrails
- **Cut:** `< 1.5%` submit conversion after minimum sample, or proof-surface engagement drops by `> 10%`
- **Defer:** fewer than `150` views, or placement/testing is inconsistent across surfaces

**This week**
- Module views:
- Submit conversion:
- Assisted seller-page visits:
- Guardrail read:
- Decision:
- Why:

### 4. Decision Feed / Compare-Mode Lead CTA
- **Surface:** Post-trust CTA after active browsing or 5+ cards viewed
- **Minimum review sample:** 100 CTA exposures and the underlying feed experiment at decision-grade traffic
- **Primary metric:** lead submit conversion from CTA exposures
- **Secondary metrics:** property views per user, compare depth, downstream seller or buyer intent
- **Guardrails:** session depth, exit spikes, internal-traffic contamination

**Decision thresholds**
- **Double-down:** `>= 4%` submit conversion and compare-mode usage improves evaluation depth
- **Continue:** `2% to 3.9%` submit conversion with clean traffic
- **Cut:** `< 1.5%` submit conversion after minimum sample, or CTA interrupts evaluation
- **Defer:** fewer than `100` CTA exposures, mixed internal traffic, or experiment not yet decision-grade

**This week**
- CTA exposures:
- Submit conversion:
- Property views per user:
- Traffic quality read:
- Decision:
- Why:

## Cross-Surface Calls
- **Best-performing surface this week:**
- **Worst-performing surface this week:**
- **Surface to route more traffic to next week:**
- **Surface to simplify or remove next week:**
- **Instrumentation fixes required before next Friday:**

## Founder Decision Summary
- **Continue:**
- **Cut:**
- **Double-down:**
- **Defer:**

## Notes
- Prefer decisions based on intent quality, not raw lead count alone.
- Seller surfaces can run at lower volume than buyer surfaces, but low quality is still a fail.
- If a surface hits conversion target but harms the main proof journey, do not scale it blindly.

## Sprint Call
- CONTINUE
