# Brain 1/2/3 Strategic Development — Considered Answer (2026-07-23)

Will asked directly: potential of the 3 brains, how to integrate/develop them, whether our data can
mimic reinforcement learning, what data sources are missing, and whether to score source usefulness.
This is that answer, not a status recap (the "all 3 built" fact is already in memory).

## What the 3 brains actually are, and the loop between them

- **Brain 1** (external, coaching-corpus knowledge graph): the source of *hypotheses* — real-estate
  sales/marketing techniques proven to work elsewhere.
- **Brain 2** (in-house measured data): the ONLY source of truth for what's actually worked for
  Fields specifically — `ad_downstream`, PostHog, the change ledger.
- **Brain 3** (internal ops knowledge): institutional memory of what's already been decided, tried,
  and why — prevents re-litigating settled questions or re-testing dead ideas.

**The integration that matters is the LOOP, not the three stores separately:** Brain 1 proposes →
an experiment runs → Brain 2 measures the real result → Brain 3 records the decision + reasoning →
the next Brain 1 query is informed by what Brain 3 already knows was tried. This loop already exists
informally (the experiment backlog, the change ledger, `ad_decisions`); the opportunity is making it
tighter and partly automatic rather than depending on a human/Samantha remembering to close it.

## Can our data mimic reinforcement learning? Loosely, yes — and there's a concrete next step

A genuine RL loop needs: state, action, reward, and a policy that updates from reward. We have rough
analogues already: state = current market/funnel situation (Brain 2+3), action = a hypothesis-driven
experiment (sourced from Brain 1), reward = the measured outcome (conversion rate, cost/session,
ultimately a listing appointment), policy update = recording the result so future hypothesis
selection favours what's worked. **We do NOT have anywhere near the traffic for a real bandit
algorithm** (Task 3's own discipline already says this — few, high-leverage tests, not volume) — but
the STRUCTURE can still mirror one without needing statistical scale for it to add value.

**Concrete, buildable next step:** turn the experiment backlog from a qualitative priority list into
an explicit scoring formula — score each queued Brain-1 hypothesis on (a) strength of external
evidence, (b) whether Brain 3 shows a similar concept already tried and how it went, (c) expected
effect size vs. the traffic available to detect it (per Task 3's existing "only test what can reach
significance" rule). This is a genuine, if small, policy function — it makes the "which hypothesis
next" decision systematically biased toward what the loop has already learned, which is the actual
spirit of the RL analogy, without pretending we have bandit-scale data.

## Should we score data-source usefulness? Yes — and this session found the framework already needed to exist

Score every pulled source on: **(a) reliability** (how often does it silently break — this session
alone found ABS API host migration, a dead Facebook-attribution cron for 4+ months, and a shared
OAuth token breaking 3 systems at once); **(b) actual decision-influence** (has any real entry in
`ad_decisions`/the change ledger ever cited this source? if never, it's dead weight); **(c) unique
coverage** (does another source already give us this, redundantly?). A source that's fragile (low a)
AND never actually cited in a decision (low b) is a clear candidate to drop or stop maintaining.
**This session's Systems Health additions are a partial start on (a)** — extend the same discipline
to periodically check (b) too (a source nobody's queried from `ad_decisions` in N months is worth
flagging, the same way a stale cron is).

## Data sources we're not pulling that we probably should

1. **Qualitative "why didn't you convert" signal.** We have rich quantitative funnel data (PostHog)
   but nothing structured captures WHY an AYH visitor or off-market-gate visitor left without
   converting. A single micro-survey/exit-intent question would close a real gap Brain 2 can't fill
   from behavioural data alone.
2. **Competitor agency pricing/positioning**, not just Domain's own valuation model — we compare
   against Domain's estimate, never against how an actual competing agent is pricing/marketing a
   comparable home. That's the audience we're actually trying to differentiate from.
3. **Behavioural-economics / conversion-psychology literature, distinct from Brain 1's real-estate-
   coaching corpus.** Product decisions already draw on this informally and uncredited — the
   off-market ladder deck cites Loewenstein's information-gap theory and the Hinge "Most Compatible"
   study directly in its own design brief (`07_Focus/decision_feed_brief.md`), but that's a different
   external-knowledge domain than Brain 1's real-estate-sales-technique corpus, and it isn't
   systematically indexed anywhere — it's whatever the person building that feature happened to know.
   Worth considering as a deliberate extension (a "Brain 1b"), not left ad hoc.

## Priority order if picking one to build next
The scoring-formula extension to the experiment backlog is the smallest, most immediately useful —
it directly strengthens a loop that already exists. The qualitative "why didn't you convert" signal
is the highest-leverage NEW data source (closes a real blind spot Brain 2 structurally can't see).
The data-source scorecard and the Brain-1b extension are valuable but lower urgency.
