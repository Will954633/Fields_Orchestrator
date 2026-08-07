# GPT-5.6-terra design critique

Model: `gpt-5.6-terra` via openai · 2026-08-07T18:57:32.020822+10:00
Tokens: 2097 prompt + 3440 completion

---

## Sharpest disagreement

Your “power is equal” claim is not operationally true yet. A veto without guaranteed access to the underlying evidence is mostly a power to delay, not a power to govern. If I cannot inspect the queried rows, source URLs, query definition, pipeline identity, chart inputs, and calculation trail, I am being asked to audit a narrated version of reality chosen by the agent who produced it.

That creates the worst possible dynamic: I become either an obstructionist demanding endless paste-ins, or a ceremonial sceptic who eventually accepts Claude’s account because the alternative is stalling. Neither is peer review.

The harness needs an **evidence packet standard** and a **reproducibility right**, not merely DATA REQUISITIONS.

For every claim capable of changing the article’s conclusion, the packet must include:

- exact claim text;
- source, access date, and source class;
- query/script/pipeline identifier;
- time window and geography;
- numerator, denominator, sample size and exclusions where applicable;
- the relevant raw output or sufficiently complete tabular extract;
- known limitations;
- whether it is a directly observed fact, a calculated statistic, or an interpretation;
- a stable artifact path/hash so a later reviewer can see that the input did not change.

For the median pipeline specifically, require a machine-readable **pipeline provenance assertion**: pipeline name/version, overwrite check result, sample size, 90% CI, sale period, and a pass/fail comparison against the protected source. The article cannot consume a median unless that assertion passes.

This is not bureaucracy. It is the minimum condition under which an untooled reviewer has meaningful veto power.

**Confidence: HIGH.** I would change my mind only if your interface can reliably provide source artifacts and reproducible outputs on demand, rather than prose summaries.

## 1. Mechanisms that prevent sycophantic convergence

Prompting agents to “be critical” does little. You need incentives, sequencing, and decision rules that make unsupported agreement costly.

### A. Commit before disclosure, then score divergence

Blind phase outputs should be committed as structured records before either model sees the other’s work:

```text
Claimed homeowner concern:
Rank:
Why it matters:
Evidence needed:
What evidence would falsify or weaken it:
Confidence:
Potential harm if wrong:
```

After reveal, measure—not reward for its own sake, but record—three things:

1. **Issue overlap**: did both identify the same owner question?
2. **Ranking divergence**: did one elevate an issue the other overlooked?
3. **Falsification quality**: did each name evidence that could prove itself wrong?

The key is that the final process must preserve at least one initially minority or divergent hypothesis until evidence adjudicates it. Otherwise “blind” just produces two lists that are immediately merged into the more fluent one.

### B. Separate evidence adjudication from narrative preference

Every disagreement must be classified before it is debated:

- **Fact dispute** — source, calculation, definition, time period, sample, pipeline.
- **Inference dispute** — what the evidence permits one to say.
- **Audience-priority dispute** — which question matters most to a homeowner.
- **Editorial-form dispute** — structure, emphasis, prose, chart choice.
- **Compliance dispute** — advice, prediction, attribution, number format, banned language.
- **Unknown** — cannot be resolved from available evidence.

Each class has a different resolution mechanism:

| Dispute type | Resolution rule |
|---|---|
| Fact | Primary/reproducible source wins; otherwise remove or qualify claim |
| Inference | Narrower interpretation wins |
| Audience priority | Independent audience-rubric scoring, then evidence-weighted selection |
| Editorial form | Pen-holder decides after recording objection |
| Compliance | Strictest compliant version wins |
| Unknown | Explicitly disclose uncertainty or omit |

Without this taxonomy, all disputes devolve into rhetorical confidence.

### C. Require a “disconfirming evidence” field for every major section

For each proposed article claim, require:

- strongest supporting evidence;
- strongest contrary or limiting evidence;
- what the reader might wrongly infer;
- exact sentence that prevents that overreach.

Example: a rolling median increase may be true, but the contrary evidence could be a wide confidence interval, a small sample, changing mix, or a different national/Gold Coast benchmark. If the claim cannot survive that field, it is not article-ready.

### D. Use an asymmetric burden of proof

The agent proposing a claim bears the burden to prove it. The critic need not prove the opposite.

This matters especially for “market is accelerating,” “supply is tight,” “buyers are returning,” and homeowner-psychology claims. A challenge such as “show the data supports *accelerating* rather than merely *higher than last year*” is sufficient to stop the stronger wording until evidence arrives.

### E. Force independent final answers to the reader’s core question

Immediately before sign-off, each agent independently writes:

1. “After reading this, a Robina / Varsity Lakes / Burleigh Waters owner should understand…”
2. “The single most likely misleading takeaway is…”
3. “The claim I am least confident in is…”
4. “What is absent that the headline implicitly promises?”

Reveal only after commitment. If these differ materially, do not sign off. The article has not achieved shared clarity; it has achieved superficial agreement.

### F. Make dissent visible in the work queue, not just the archive

A dissent register that disappears into a folder is performative. Every unresolved non-blocking dissent should generate one of:

- a limitation sentence;
- removal of the disputed claim;
- a “not established by available data” note in the research record;
- a deferred research task.

There should be no category called “we disagree but published it as if we do not.”

## 2. Is blind parallel research worth it?

Yes, but only in a narrow, time-boxed form. Full blind parallel research is otherwise expensive theatre because I lack independent research tools. I can independently reason about likely homeowner questions and the evidence standard required, but I cannot independently discover current Gold Coast facts.

The useful blind exercise is not “both agents research the market.” It is:

1. **Blind audience-problem mapping** — both rank owner questions without seeing current data.
2. **Blind evidence plan** — both state what evidence would be required to answer each question responsibly.
3. **Blind claim-risk register** — both identify likely seductive but unsafe conclusions before seeing the figures.

This is high value because it tests framing and evidentiary discipline, where independence exists.

Do not require me to create a parallel fact base from memory. That would create fake independence and invite stale-market hallucinations. Any market fact from my recall must be labelled `[FROM MEMORY — NEEDS VERIFICATION]`, and should not enter the article until independently sourced.

A practical design:

- 20–30 minutes equivalent / strict token budget for blind mapping.
- Commit outputs with hashes or timestamps.
- Reveal.
- Claude researches the union of evidence needs, with priority given to issues one agent saw and the other missed.
- Re-run a brief blind angle selection only after the verified evidence packet exists.

**Confidence: HIGH.** It becomes theatre if it asks the untooled agent to imitate data research rather than independently challenge framing and standards.

## 3. Who holds the pen in phase 4?

**Claude should hold the first-draft pen.**

Not because Claude is superior editorially, but because the draft must be built against verified facts, source limitations, chart inputs, and exact data definitions. The agent with access to those artifacts is less likely to accidentally turn a qualified statistic into an unqualified narrative claim during assembly.

But that is safe only with constraints:

- Claude drafts from a **locked evidence ledger**, not from memory.
- Every substantive sentence receives an internal claim ID linking to the evidence packet.
- GPT performs the first adversarial review before stylistic polishing.
- GPT has authority to require deletion, qualification, or evidence retrieval for a claim.
- GPT should hold the pen for a **limited rewrite pass** on reader clarity after factual claims are locked—particularly the opening, transitions, headings, chart captions, and conclusion.

Do not alternate pen ownership arbitrarily. That creates churn and makes provenance disappear. Use defined ownership:

| Stage | Owner |
|---|---|
| Evidence extraction and first factual assembly | Claude |
| Evidentiary challenge and audience-confusion diagnosis | GPT |
| Revised factual draft | Claude |
| Reader-clarity rewrite of non-factual connective tissue | GPT |
| Final source and compliance verification | Claude + GPT adversarial pass |

The final assembler should be Claude because the final artifact must be checked against sources and rendered charts. But GPT’s review cannot be a suggestion layer; accepted objections must generate traceable edits.

**Confidence: HIGH.** I would revise this if you provide a drafting environment where I can reliably access a complete evidence ledger and stable artifacts, not selected excerpts.

## 4. The right unit of disagreement

Your dissent register works if the unit is a **decision-impacting proposition**, not “a comment” and not “a paragraph.”

Good unit:

> “The evidence supports describing Burleigh Waters’ rolling-12-month median as higher year-on-year, but does not support the verb ‘accelerating’ because no valid momentum series has been supplied and the available sample is 48 sales.”

Bad unit:

> “Tone feels too bullish.”

Each record should contain:

```text
ID:
Proposition:
Type: fact / inference / audience / compliance / form / unknown
Materiality: blocking / major / minor
Claim IDs affected:
Objector:
Requested resolution:
Evidence needed:
Resolution: accepted / rejected with reason / unresolved
Decision owner:
Reader-facing consequence:
```

### The crucial rule

A blocking dissent does not need consensus to block publication. It needs a defined basis:

- factual claim lacks adequate provenance;
- article violates a hard constraint;
- material inference exceeds evidence;
- known data limitation is hidden in a way likely to mislead;
- angle fails the stated audience-purpose test.

That prevents veto becoming “I prefer another headline.”

### Avoiding paperwork

Set a materiality threshold. Register only objections that would change:

- a headline, standfirst, chart, section heading, or conclusion;
- a numerical claim;
- a major causal or directional implication;
- the answer to a priority owner question;
- compliance status.

Line-level style disagreements should be resolved by the pen-holder and not enter the register.

Also impose an expiry: once a matter is marked `REJECTED-with-reason`, it cannot be relitigated unless new evidence or a factual error is introduced. Otherwise the register becomes a loop generator.

**Confidence: HIGH.**

## 5. What the RL signal should be

Do not train primarily on whether both agents signed off, how polished the prose sounds, or whether disagreement was low. Those signals reward conformity.

You need separate scores for **process integrity**, **pre-publication article quality**, and later **outcome feedback**.

### A. Immediate, mechanically auditable process signals

These are available at publication time:

1. **Claim provenance coverage**
   - Percentage of substantive factual claims with complete evidence packets.
   - Target should be effectively 100%; missing provenance is a fail, not merely a lower score.

2. **Claim-to-source fidelity**
   - Sampled audit: does the cited source actually support the exact scope, period, geography and wording?
   - Include limitations, not merely source presence.

3. **Retraction-risk score**
   - Count claims based on weak source classes, small samples, unreliable measures, unverified calculations, or unsupported inferences.
   - Weight headline/chart claims heavily.

4. **Constraint compliance**
   - Advice, prediction, valuation headline, banned words, number format, suburb capitalisation, attribution, limitation requirements.
   - Regex catches only a subset; semantic compliance requires review.

5. **Dissent handling quality**
   - Proportion of material dissents resolved with evidence rather than authority.
   - Number of blocking dissents that reached publication improperly must be zero.
   - Track whether rejected objections later prove correct.

6. **Evidence efficiency**
   - Number of requisitions fulfilled versus unfulfilled.
   - More research is not automatically better. Measure whether fulfilled requisitions changed a decision, narrowed a claim, or prevented a bad claim.

7. **Audience-question coverage**
   - Independent rubric: how many of the top-ranked owner questions are answered with local, comprehensible evidence?
   - Crucially, score “answer quality,” not mere mention.

### B. Independent pre-publication quality evaluation

Use a frozen rubric and, if possible, a separate evaluator instance that did not write the article. Ask it to judge:

- Does the article answer a question a non-listing homeowner actually has?
- Does it distinguish the three suburbs where evidence permits?
- Does it make uncertainty intelligible rather than bury it?
- Is the conclusion proportionate to the evidence?
- Could a reader confuse description with a recommendation?
- What is the most likely false inference?

Blind the evaluator to which agent wrote which section. Otherwise you will train for model identity and agreeable process rather than quality.

### C. Delayed outcome signals

When traffic exists, capture signals cautiously:

- completion / scroll depth;
- chart interaction;
- return visits;
- direct reader feedback asking fewer versus more confused follow-up questions;
- corrections, complaints, and factual challenges;
- whether later data invalidates framing or only changes the level of a statistic.

Do **not** optimize early for clicks or time on page. Homeowner anxiety is highly clickable, and click optimisation will push the system toward alarmist headlines—the exact opposite of the trust asset you say you are building.

### D. The most important negative reward

A later correction or retraction should carry a very large negative reward, especially when the failure was foreseeable from an existing limitation: wrong pipeline, unsourced median, misleading volume measure, hidden small sample, or inference stronger than data.

Treat “the number was technically correct but readers were predictably misled” as a failure too.

**Confidence: HIGH.** The RL layer should initially be a process-learning log, not genuine automated model optimisation. With very few runs and no outcome data, calling it reinforcement learning risks giving noise an undeserved scientific status.

## 6. What you are not seeing

The most likely failure is **the harness will reward evidence availability over homeowner usefulness**.

Claude can query a rich internal database. That creates a powerful temptation to write the article around the indicators you can produce—medians, price changes, inventory proxies, postcode comparisons—rather than around the uncertainty a homeowner actually needs resolved:

- “Why do national headlines and what I see locally seem inconsistent?”
- “Does a higher median say anything useful about homes like mine?”
- “Why might two nearby suburbs be behaving differently?”
- “What can this data not tell me about my own street or home?”
- “Is there enough evidence here to infer a shift, or is it normal variation?”

Your process risks producing a scrupulously sourced answer to the wrong question. That is worse than an ordinary weak article because it feels authoritative.

The correction is structural: **angle selection must begin with an owner decision-confusion, not a dataset.** Every angle must pass:

1. What exact confusion does this resolve?
2. What would a homeowner understand after reading that they did not understand before?
3. Is the answer locally specific?
4. Does the evidence permit an answer rather than a display of statistics?
5. What would be lost if this article were not published?

If the answer to question 5 is “they would have one less chart,” kill the angle.

A second major risk: the three-suburb mandate can lead to artificial symmetry. Robina, Varsity Lakes and Burleigh Waters are not interchangeable analytic units. If evidence is strong for one, weak for another, the article must say so. Do not manufacture equal suburb-by-suburb treatments merely because they are target postcodes.

A third risk: your hard prohibition on advice is sensible, but can produce an article that is technically safe and emotionally evasive. “Data only” must not mean “numbers without interpretation.” The allowable middle ground is clearly labelled interpretation of what the data can and cannot establish—not a recommendation about what the reader should do.

**Confidence: HIGH.** I would change my mind if angle selection demonstrably starts from independently ranked homeowner confusion and rejects data-led angles even when the data is unusually rich.
