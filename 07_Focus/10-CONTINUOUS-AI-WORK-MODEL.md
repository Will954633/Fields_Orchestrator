# Continuous AI Work Model — Run, Review, Reflect, Run Again

> **Date:** 2026-03-30
> **Key insight:** AI doesn't need to wait for tomorrow. The only constraints are: cost, need for human feedback, waiting on external results, or diminishing returns.

---

## The Problem With the Current Model

The CEO agents run once at 02:40 AEST. They produce proposals. Then they sit idle for 23.5 hours.

That's a human work schedule applied to a machine. The machine doesn't get tired. It doesn't need sleep. It doesn't need to wait until tomorrow to iterate on today's ideas.

---

## The New Model: Iterative Work Sessions

```
┌─────────────────────────────────────────────────┐
│              CONTINUOUS WORK LOOP                 │
│                                                  │
│   RUN → REVIEW → REFLECT → PLAN → RUN AGAIN     │
│    │                                    │        │
│    │         Keep going until:          │        │
│    │                                    │        │
│    │   ❌ Daily time/cost limit hit     │        │
│    │   ❌ Need Will's input → Telegram  │        │
│    │   ❌ Waiting on market/test data   │        │
│    │   ❌ Last 3 runs added no value    │        │
│    │                                    │        │
│    └────────────────────────────────────┘        │
└─────────────────────────────────────────────────┘
```

### How a Work Session Runs

**Phase 1: RUN**
Agent executes its task. Reads context, analyses data, produces output (proposal, content draft, code, research findings).

**Phase 2: REVIEW**
Agent reads its own output. Checks:
- Did I answer the actual question?
- Is the data accurate? Can I verify claims?
- Does this align with the current sprint and milestone?
- Is this actionable or just observation?

**Phase 3: REFLECT**
Agent assesses value-added:
- Did this run produce something NEW that the last run didn't?
- Did I find information that changes a decision?
- Is there a clear next action that would add more value?
- Am I repeating myself or genuinely advancing?

**Phase 4: PLAN**
Based on reflection, decide:
- **RUN AGAIN** — there's a clear next step that adds value
- **MESSAGE WILL** — need human decision, approval, or feedback → Telegram
- **WAIT** — need external data (market results, test data, ad performance) before next useful run
- **STOP** — last 3 iterations haven't produced substantial new value toward the milestone

---

## What This Looks Like in Practice

### Example: Content Brief Development

**Run 1 (02:40 AEST):** Standard overnight analysis. Review sprint plan, check metrics, produce proposals.

**Review 1:** "My content review was based on web research only. I have keyword data and ad history in my context now. I should use that."

**Run 2 (02:55 AEST):** Deep dive into `content_research_data.md`. Cross-reference every post in the content brief against top YouTube keywords, PAA questions, and ad performance history. Identify which topics have search demand and which don't.

**Review 2:** "Found 3 content brief topics that don't match any keyword demand, and 2 high-volume keywords with no content planned. This is actionable."

**Run 3 (03:10 AEST):** Rewrite the content brief with keyword-aligned topics. Draft specific rewrites for weak posts. Research competitive examples for the strongest topics.

**Review 3:** "Content brief is now data-backed. But I haven't checked whether the property data claims in the posts are verifiable."

**Run 4 (03:25 AEST):** Verify every property claim. Check listing status, prices, valuation data against live database context. Flag any stale or incorrect claims.

**Reflect:** "4 runs, each added clear value. Run 5 would be optimising copy tone — diminishing returns. Stop here. Send summary to Will via Telegram at 07:00."

**STOP.** Total time: ~45 min. Total cost: ~$0.80. Output: fully verified, keyword-aligned, rewritten content brief.

### Example: Backup Scraper Development

**Run 1:** Audit current state. SSH status, log analysis, coverage comparison.

**Review 1:** "Found 4 blocked agencies (403 errors). I can research their website structure and propose scraping approaches."

**Run 2:** Research each blocked agency's website. Identify which use JavaScript rendering, which serve static HTML, which have API endpoints.

**Review 2:** "2 of 4 agencies serve static HTML — straightforward to scrape. 1 uses Cloudflare. 1 has an API. I should write prototype scrapers."

**Run 3:** Write prototype scraper code for the 2 static HTML agencies in the sandbox.

**Review 3:** "Code written. But I can't test it from the sandbox — need deployment to the scraper VM."

**Reflect:** "Need Will or Claude Code to deploy and test. Message Will: 'Prototype scrapers ready for 2 Robina agencies. Ready for deployment to scraper VM. Approve?'"

**MESSAGE WILL** via Telegram. Stop. Resume after approval.

---

## Stopping Conditions (Explicit)

| Condition | What Happens |
|-----------|-------------|
| **Daily cost limit hit** | Stop all runs. Resume tomorrow. Start with $5/day limit, adjust based on value. |
| **Need Will's decision** | Message Will on Telegram with specific question. Stop this workstream. Continue other workstreams if available. |
| **Waiting on external data** | Log what data is needed and when it's expected. Stop this workstream. |
| **3 consecutive runs with no new value** | Agent explicitly logs: "Last 3 runs produced no substantial new information toward [milestone]. Stopping. Will resume when: [condition]." |
| **Milestone work complete** | All sprint checkpoint pre-work for the next 2 weeks is done. Stop. Message Will: "Sprint pre-work complete through [date]. Ready for review." |

---

## Cost Management

### Starting Budget
- **$5/day per agent** (~$0.20/run × 25 runs max)
- **$25/day total** for all 5 agents
- **~$750/month** (currently $18/month for once-daily runs)

### Value Assessment
At $25/day, the agents need to produce value equivalent to ~1 hour of a human specialist's time per day. Given what we've seen today (full strategic review, case studies, code prototypes, content rewrites), that threshold is easily met.

### Cost Controls
1. **Hard daily cap per agent** — enforced in the launcher script
2. **Diminishing returns detector** — if an agent's last 3 outputs are >80% similar to each other (simple text similarity), auto-stop
3. **Weekly cost review** — Chief of Staff reports total agent spend vs value produced
4. **Escalation threshold** — if any single run exceeds $1 (unusually long/complex), flag it

### Ramp-Up Plan
- **Week 1:** $5/day limit. Monitor value produced.
- **Week 2:** If value > cost by clear margin, raise to $10/day.
- **Week 3-4:** Assess and set sustained budget.

---

## Implementation Architecture

### Option A: Multi-Pass Launcher (Simplest)

Modify `ceo-agent-launcher.py` to support multiple passes:

```python
MAX_PASSES = 5
COST_LIMIT_PER_AGENT = 1.00  # dollars per day

for pass_num in range(1, MAX_PASSES + 1):
    # Run agent
    result = run_agent(agent_id, pass_num)

    # Check if agent wants to continue
    if result.get("stop_reason"):
        log(f"{agent_id} stopped after pass {pass_num}: {result['stop_reason']}")
        break

    # Check cost
    if cumulative_cost > COST_LIMIT_PER_AGENT:
        log(f"{agent_id} hit cost limit after pass {pass_num}")
        break

    # Check for Telegram message
    if result.get("needs_human_input"):
        send_telegram(result["telegram_message"])
        log(f"{agent_id} waiting for human input")
        break
```

Each pass includes the previous pass's output in context, so the agent builds on its own work.

### Option B: Autonomous Session (More Powerful)

Give each agent a longer codex session (30-60 min instead of 15 min) with explicit instructions to iterate:

```
You have 30 minutes and a budget of $1.00 for this session.

Work in passes:
1. First pass: Read all context, produce initial analysis
2. Review your own output: is it actionable? Data-verified? Sprint-aligned?
3. Second pass: Address gaps from review. Cross-reference keyword data. Verify claims.
4. Review again: did pass 2 add substantial value?
5. Continue until: you've exhausted useful work, hit the time limit, or need human input.

After each pass, explicitly state:
- CONTINUE: [reason for next pass]
- STOP: [reason] — last 3 passes didn't add enough value
- MESSAGE_WILL: [specific question needing human input]
- WAIT: [what external data is needed]
```

### Option C: Daemon Model (Most Powerful, Future)

A continuously running agent service that:
- Wakes on triggers (new data, sprint change, timer)
- Runs analysis passes until stopping condition
- Messages Will on Telegram when it has something
- Pauses when waiting for feedback
- Resumes when feedback arrives

This is the end-state but requires more infrastructure.

**Recommendation: Start with Option B (autonomous session).** It works within the existing codex exec model, just with longer sessions and explicit iteration instructions.

---

## Agent Prompt Addition: Iteration Protocol

Add to every agent's prompt:

```
## Iteration Protocol

You are not limited to one analysis pass. Work iteratively:

PASS 1: Read context, produce initial analysis/output.
REVIEW: Read your own output. Ask: Is this actionable? Is the data verified?
         Does this advance the current sprint milestone?
PASS 2: Address gaps. Cross-reference content_research_data.md. Verify claims.
         Research external case studies if relevant.
REVIEW: Did pass 2 add substantial new value?
PASS 3+: Continue if clear value remains. Stop if you're repeating yourself.

After EACH pass, state one of:
- CONTINUE: [what the next pass will add]
- STOP: [reason — diminishing returns / work complete / waiting on data]
- MESSAGE_WILL: [specific question — will be sent via Telegram]

Rules:
- Never run more than 5 passes in one session
- If passes 3-5 are >80% similar to pass 2, you're done
- If you need Will's approval for something, send the Telegram message and stop
- If all sprint pre-work is done for 2+ weeks ahead, stop and say so
- Every pass must reference the current sprint theme and milestone
```

---

## What Changes Tomorrow

### Immediate (Can Do Now)

1. **Extend tonight's CEO agent run to multi-pass.** Instead of 15-min timeout, give each agent 30 minutes. Add iteration protocol to the prompt.

2. **The agents should start working on Sprint 1 pre-work RIGHT NOW:**
   - Engineering: Build the leads collection schema, set up PostHog event taxonomy
   - Product: Write the conversion spec for price alerts (copy, placement, event schema, success metric)
   - Growth: Produce the ad pause/scale memo with specific ad IDs
   - Data Quality: Start feed_hook field generation for Sprint 2
   - Chief of Staff: Produce tomorrow's morning checkpoint with full context

3. **When they need Will's approval,** they message him on Telegram rather than waiting for a session.

### This Week (Sprint 1)

4. **Run agents 2-3x per day** instead of once:
   - 02:40 AEST: Overnight analysis (current slot)
   - 10:00 AEST: Mid-morning pass (after Will's first session, pick up any new context)
   - 16:00 AEST: Afternoon pass (before tomorrow's planning)

5. **Between scheduled runs,** Claude Code sessions can trigger ad-hoc agent runs for specific tasks.

### Sprint 2+

6. **Move to autonomous sessions** (Option B) — 30-min sessions with iteration protocol.
7. **Implement cost tracking** per agent per day.
8. **Build the diminishing returns detector.**

---

## The Philosophy

The agents should work like a startup team, not like a consulting firm that delivers a report once a day. A startup team:

- Works on the problem until it's solved, not until 5pm
- Iterates rapidly — ship, measure, iterate, ship again
- Stops when the work is done, not when the clock says stop
- Communicates when blocked, not at the next scheduled meeting
- Prioritises the most valuable work, not the work that was planned last week

The only constraints are: cost (managed), human decisions (Telegram), external data (wait), and diminishing returns (self-assessed). Everything else should be: work.
