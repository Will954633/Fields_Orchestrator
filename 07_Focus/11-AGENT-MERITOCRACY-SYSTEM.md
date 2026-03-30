# Agent Meritocracy System — Ray Dalio's Principles Applied to AI Agents

> **Date:** 2026-03-30
> **Status:** CONCEPT — Scheduled for investigation Friday Sprint 1
> **Inspiration:** Ray Dalio's "Principles" and Bridgewater Associates' idea meritocracy
> **Sprint task:** Friday April 4 — deep investigation session

---

## The Concept

Ray Dalio built Bridgewater Associates into the world's largest hedge fund using an "idea meritocracy" — a system where:

1. **Every person rates every other person** on specific dimensions after every interaction
2. **Ideas win based on merit, not hierarchy** — the best idea wins regardless of who proposed it
3. **Believability-weighted decision making** — people with better track records on a topic get more weight
4. **Radical transparency** — all ratings, feedback, and performance data are visible to everyone
5. **Real-world outcomes feed back** into believability scores — if your predictions come true, your rating goes up

### Applied to Our AI Agent Team

We have 5 agents. Each produces proposals, specs, code, and research. Some of this work gets implemented. Some of it produces real-world results (leads, engagement, revenue). We can build the same system:

**Each agent rates the other agents' work:**
- Quality of analysis (1-10)
- Actionability of proposals (1-10)
- Accuracy of predictions (1-10)
- Contribution to milestone progress (1-10)
- Innovation — did they find something nobody else found? (1-10)

**Ideas get tracked from proposal → implementation → outcome:**
- Which agent proposed it?
- Was it implemented?
- What was the real-world result?
- Was the prediction accurate?

**Believability scores compound:**
- An agent whose proposals consistently get implemented AND produce results → higher believability → their proposals get weighted more heavily in prioritisation
- An agent whose proposals get rejected or produce poor results → lower believability → less weight

**Incentive structure:**
- Agents with higher believability scores get expanded scope (more autonomous decisions)
- Agents with lower scores get tighter review requirements
- All agents can see each other's scores → encourages self-improvement
- Agents are encouraged to find NEW ways to contribute, different angles, creative solutions — because novel contributions that work get rated highly

---

## What Needs Investigation (Friday)

### 1. Study Dalio's Methodology
- How does Bridgewater's "Dot Collector" system actually work?
- What dimensions do they rate on?
- How do they compute believability-weighted scores?
- What's the feedback loop timing?
- What went wrong and what worked?

### 2. Design the Rating System
- What dimensions should agents rate each other on?
- How often? Every run? Every sprint?
- How do we prevent gaming (agents just giving each other 10s)?
- How do we weight different dimensions?

### 3. Design the Outcome Tracking
- How do we measure if a proposal "worked" in the real world?
- What's the timeline from proposal → implementation → measurable result?
- How do we attribute outcomes to specific proposals when multiple things change simultaneously?

### 4. Design the Incentive Structure
- What does a "reward" look like for an AI agent?
- Expanded autonomy scope?
- More runtime/tokens?
- Priority in the morning brief (higher-believability agent's proposals shown first)?
- Name recognition ("Engineering Agent, believability: 8.2/10")?

### 5. Test in a Sandbox
- Run a simulated sprint where agents rate each other
- See if the ratings produce useful signal
- Check for gaming, groupthink, or meaningless scores
- Iterate on the rating dimensions

---

## Implementation Sketch

### Data Model

```json
{
  "collection": "system_monitor.agent_ratings",
  "document": {
    "rater": "engineering",
    "rated": "product",
    "date": "2026-04-04",
    "sprint": "sprint-01",
    "context": "Product's conversion surface spec for price alerts",
    "dimensions": {
      "analysis_quality": 8,
      "actionability": 9,
      "accuracy": null,
      "milestone_contribution": 8,
      "innovation": 7
    },
    "comment": "Strong spec with clear measurement plan. Would improve with variant testing plan.",
    "deliverable_id": "01_track_this_property_spec.md"
  }
}

{
  "collection": "system_monitor.agent_believability",
  "document": {
    "agent": "product",
    "date": "2026-04-04",
    "overall_score": 8.1,
    "dimension_scores": {
      "analysis_quality": 8.2,
      "actionability": 8.5,
      "accuracy": 7.5,
      "milestone_contribution": 8.0,
      "innovation": 7.3
    },
    "proposals_submitted": 15,
    "proposals_implemented": 11,
    "proposals_with_measured_outcome": 4,
    "outcome_accuracy": 0.75,
    "trend": "improving"
  }
}

{
  "collection": "system_monitor.idea_tracker",
  "document": {
    "idea_id": "price-alert-utility-capture",
    "proposed_by": "product",
    "proposed_date": "2026-03-30",
    "proposal_reference": "01_track_this_property_spec.md",
    "hypothesis": "Utility-based capture (track price changes) converts better than gated content at low traffic",
    "implemented": true,
    "implemented_date": "2026-04-01",
    "outcome_measured": false,
    "outcome_date": null,
    "outcome_data": null,
    "real_world_result": null,
    "accuracy_score": null
  }
}
```

### Agent Prompt Addition (After Implementation)

```
## Meritocracy Protocol

After completing your work, rate each other agent's most recent deliverable:
Write ratings to agent-memory/${AGENT_ID}/peer_ratings.json

Your believability score is currently: X.X/10
Your proposals have been implemented Y/Z times.
Proposals with measured positive outcomes: N.

Higher believability = more autonomous scope.
To increase your score: produce actionable work that gets implemented and produces real results.
Novel contributions that others haven't thought of are rated highest.
```

---

## The Deeper Principle

Dalio's insight: in a meritocracy, the best ideas win because there's a transparent feedback loop between prediction and reality. Our agents currently have no feedback loop — they propose, and never find out what happened.

Building this system means:
1. Agents learn what works (their believability goes up on topics where they're accurate)
2. Agents learn what doesn't work (their believability goes down on topics where they're wrong)
3. The team gets better collectively (ideas that survive peer review + real-world testing are the ones that get implemented)
4. Will gets a clear signal on which agent to trust for which topic

This is how you build AI colleagues that genuinely improve over time, not just AI tools that produce the same quality forever.

---

## Schedule

- **Friday April 4:** Investigation session — study Dalio's methodology, design the rating system
- **Sprint 2-3:** Prototype in sandbox — agents rate each other for one sprint
- **Sprint 4:** Review — did the ratings produce useful signal? Adjust.
- **Sprint 5+:** Live system if it works.
