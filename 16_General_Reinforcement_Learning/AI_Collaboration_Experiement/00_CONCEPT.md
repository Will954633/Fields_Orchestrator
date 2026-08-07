# AI Collaboration Experiment — Claude Opus × GPT-5.6-terra

**Status:** concept explored, harness spine built and route verified. No article run yet.
**Created:** 2026-08-07
**Test case:** one polished article for homeowners in Robina, Varsity Lakes and Burleigh Waters that
acknowledges and resolves their greatest confusions, concerns, anxieties, needs and wants.

This document is the design. It was written after a live design-critique turn with GPT-5.6-terra
(`runs/000_design_review/GPT_DESIGN_CRITIQUE.md`), and GPT's objections changed it substantially —
that critique is the first evidence the pairing does something a single agent would not.

---

## 1. Why pair two models at all

The honest answer is not "two heads are better than one." It is that **Claude has been inside this
system for months and has absorbed its assumptions.** GPT has not. GPT does not know which numbers we
are proud of, which pipeline we built, or which angle we have already half-written in our heads. That
naivety is the asset. Everything below is machinery for protecting it.

The corollary: if the harness lets Claude narrate reality to GPT, the asset is destroyed and we get
something *worse* than a solo article, because it arrives wearing a "dual-reviewed" badge it did not
earn. GPT named this precisely:

> **"The experiment's largest risk is epistemic laundering through context compression."** Claude
> researches, selects excerpts, explains database methods, drafts, renders charts and then supplies GPT
> a bounded packet. GPT's apparent independent critique can make Claude's assumptions look externally
> validated, even when GPT never saw the omitted counterevidence, query logic, source conflicts, or
> pipeline provenance.

Design everything against that sentence.

---

## 2. The asymmetry, and GPT's rebuttal to my first attempt

Claude has: filesystem, bash, Cosmos (~40k property records, precomputed suburb medians), web search,
chart rendering, internal briefs. GPT has: an API endpoint and whatever Claude pastes.

My first design said "roles are asymmetric but power is equal — GPT gets data requisitions and a veto."
GPT rejected that as insufficient, and it was right:

> "A veto without guaranteed access to the underlying evidence is mostly a power to delay, not a power
> to govern. […] I become either an obstructionist demanding endless paste-ins, or a ceremonial sceptic
> who eventually accepts Claude's account because the alternative is stalling. Neither is peer review."

So requisitions alone do not fix the asymmetry. Two things replace them.

### 2.1 The evidence packet standard

No claim capable of changing the article's conclusion reaches a draft without a packet containing:

- exact claim text
- source, access date, source class
- query / script / pipeline identifier
- time window and geography
- numerator, denominator, sample size, exclusions
- the relevant raw output or a sufficiently complete tabular extract — **not a prose summary**
- known limitations
- classification: directly observed fact / calculated statistic / interpretation
- a stable artifact path + hash, so a later reviewer can prove the input did not change

### 2.2 The omission log

Every packet ships with what is *missing*: sources searched, sources excluded and why, conflicting
figures found, queries that failed, reliability warnings still unresolved. Without this, GPT is
reviewing a curated record and cannot know it.

### 2.3 Provenance labels on GPT's own output

GPT labels every approval `DIRECTLY INSPECTED` / `REPORTED BY CLAUDE` / `UNFULFILLED`. Only
`DIRECTLY INSPECTED` may be described internally as reviewed. This stops the run from quietly
accumulating false assurance — and it is GPT's own idea, which makes it likelier to be honoured.

### 2.4 The median pipeline needs a machine-readable assertion

Our medians are valid only from the Domain ∪ onthehouse union pipeline, and a different script has
silently overwritten them three times. So a median may not be consumed unless a provenance assertion
passes: pipeline name/version, overwrite-check result, sample size, 90% CI, sale period, and a pass/fail
comparison against the protected source. `scripts/check_union_median_integrity.py` already does most of
this; the harness calls it rather than trusting the field.

---

## 3. The three failure modes this design targets

**A. Sycophantic convergence.** Two models agreeing warmly, producing confident mush. Prompt
exhortations ("be critical") do nothing. Only mechanism works — §4.

**B. Epistemic laundering.** §1. Countered by the packet standard, the omission log and provenance
labels.

**C. Evidence-availability bias — the one I had not seen.** GPT's answer to "what am I not seeing":

> "The harness will reward evidence availability over homeowner usefulness. […] Your process risks
> producing a scrupulously sourced answer to the wrong question. That is worse than an ordinary weak
> article because it feels authoritative."

Because Claude can produce medians, price changes and postcode comparisons on demand, the article will
drift toward *what we can chart* and away from *what an owner cannot resolve*. Countermeasure: angle
selection begins from an owner confusion, never from a dataset, and every candidate angle must pass:

1. What exact confusion does this resolve?
2. What will an owner understand afterwards that they did not before?
3. Is the answer locally specific?
4. Does the evidence permit an *answer*, or only a display of statistics?
5. What is lost if we do not publish this?

**If the answer to (5) is "they would have one less chart", the angle is killed.**

---

## 4. Anti-convergence mechanisms

Each is a rule the harness enforces, not an instruction either agent can forget.

| # | Mechanism | What it does |
|---|---|---|
| 1 | **Sealed commitments** | Blind-phase outputs are written to disk and hashed before either agent sees the other's. No anchoring. |
| 2 | **Changed-mind disclosure** | After reveal, each agent must name one conclusion they changed and the specific evidence that changed it. "No change" is allowed but must be justified. |
| 3 | **Forced opposition** | For the chosen angle, one agent writes the strongest case *against publishing it*, scored as a deliverable — not a conversational gesture. |
| 4 | **Asymmetric burden of proof** | The agent proposing a claim proves it. The critic need not prove the opposite. "Show the data supports *accelerating* rather than merely *higher than last year*" is by itself enough to stop the stronger wording. |
| 5 | **Disagreement budget** | A run must contain ≥3 substantively challenged assumptions, each tied to an audience consequence. Agreement rate is never rewarded. What is rewarded: correctly rejecting an attractive but unsupported claim. |
| 6 | **Disconfirming-evidence field** | Every major claim carries: strongest support, strongest contrary/limiting evidence, what a reader might wrongly infer, and the exact sentence preventing that overreach. A claim that cannot survive this field is not article-ready. |
| 7 | **Blind final answers** | Immediately before sign-off, each agent independently writes: what an owner should now understand; the single most likely misleading takeaway; the claim they are least confident in; what is absent that the headline implicitly promises. Revealed only after commitment. **Material divergence blocks sign-off** — the article achieved superficial agreement, not shared clarity. |
| 8 | **Separate gates, no aggregate score** | Factual support, inference validity, audience relevance, and legal/style compliance are four independent gates. A draft can pass regex and still mislead. |
| 9 | **Precommitment + calibration** | Before seeing suburb figures, each agent assigns confidence and falsifiers to the key narrative propositions. Scored later. Attacks confident mush better than agreement metrics. |

---

## 5. Phase structure

Revised from my first draft: GPT argued that full blind parallel *research* is "expensive theatre"
because it has no research tools, and worse, invites stale-market hallucination dressed as independence.
What survives is blind work on the dimensions where its independence is real — framing and evidentiary
standards.

| Phase | Who | Output |
|---|---|---|
| **0. Load** | harness | Constitution + audience brief injected. Route health-checked at realistic prompt size. |
| **1. Blind framing** (time/token-boxed) | both, sealed | (a) ranked owner-question map, (b) evidence plan — what would be required to answer each responsibly, (c) claim-risk register — seductive-but-unsafe conclusions, named *before* seeing figures. **Not** a parallel fact base. |
| **2. Reveal + reconcile** | both | Overlap and ranking divergence recorded. Changed-mind disclosure. Union of evidence needs, prioritising what one agent saw and the other missed. |
| **3. Research** | Claude | Evidence packets + omission log. GPT issues requisitions; each is fulfilled or marked `UNFULFILLED` with a reason. An unfulfilled requisition is a finding — it marks where the article must admit ignorance. |
| **4. Angle selection** | both, blind then scored | Each proposes 3 angles. Scored against the five §3 questions. Data-led angles rejected even when the data is rich. |
| **5. Draft** | Claude pen | Assembled from the **locked evidence ledger**, not memory. Every substantive sentence carries a claim ID. |
| **6. Adversarial review** | GPT | Evidentiary challenge + audience-confusion diagnosis, before any stylistic polish. Accepted objections must generate traceable edits. |
| **7. Dataviz** | Claude, GPT specs | Spec first, then build. Chart claims weighted heavily in retraction risk. |
| **8. Revised draft** | Claude | Factual claims locked. |
| **9. Clarity rewrite** | GPT pen | Opening, transitions, headings, chart captions, conclusion — the connective tissue, once facts are locked. |
| **10. Gates + sign-off** | both | Mechanical compliance gate, then the four §4.8 gates, then blind final answers (§4.7), then dual signature. |
| **11. Post-mortem** | both | Process-learning log (§7). |

Pen ownership is **defined, not alternating** — GPT flagged that arbitrary alternation creates churn and
destroys provenance. Claude is the final assembler because the final artifact must be checked against
sources and rendered charts; but GPT's review is not a suggestion layer.

---

## 6. The dissent register

The unit is a **decision-impacting proposition**, not a comment and not a paragraph.

Good: *"The evidence supports describing Burleigh Waters' rolling-12-month median as higher
year-on-year, but does not support the verb 'accelerating' because no valid momentum series has been
supplied and the available sample is 48 sales."*

Bad: *"Tone feels too bullish."*

```
ID:
Proposition:
Type:            fact / inference / audience / compliance / form / unknown
Materiality:     blocking / major / minor
Claim IDs affected:
Objector:
Requested resolution:
Evidence needed:
Resolution:      accepted / rejected-with-reason / unresolved
Decision owner:
Reader-facing consequence:
```

**A blocking dissent does not need consensus to block.** It needs a defined basis: missing provenance;
a hard-constraint violation; a material inference exceeding its evidence; a known limitation hidden in a
way likely to mislead; or an angle failing the audience-purpose test. This is what stops veto from
becoming "I prefer another headline."

Two rules keep it from becoming paperwork:

- **Materiality threshold.** Register only what would change a headline, standfirst, chart, section
  heading, conclusion, numerical claim, causal/directional implication, compliance status, or the answer
  to a priority owner question. Line-level style is the pen-holder's call and never enters the register.
- **Expiry.** Once `rejected-with-reason`, a matter cannot be relitigated without new evidence or a
  demonstrated factual error. Otherwise the register is a loop generator.

And it must be visible in the work queue, not just archived. Every unresolved non-blocking dissent
resolves into one of: a limitation sentence, removal of the claim, a "not established by available data"
note, or a deferred research task. **There is no category called "we disagree but published as if we
did not."**

---

## 7. The learning signal — and why it is not yet RL

This folder is `16_General_Reinforcement_Learning`, but GPT's caution is worth honouring:

> "The RL layer should initially be a process-learning log, not genuine automated model optimisation.
> With very few runs and no outcome data, calling it reinforcement learning risks giving noise an
> undeserved scientific status."

So: **`process_log.jsonl` now, reward model later.** What gets measured at publication time:

1. **Claim provenance coverage** — % of substantive factual claims with complete packets. Missing
   provenance is a *fail*, not a lower score.
2. **Claim-to-source fidelity** — sampled audit: does the source support the exact scope, period,
   geography and wording, limitations included? Not merely "a source exists".
3. **Retraction-risk score** — claims resting on weak source classes, small samples, unreliable
   measures, unverified calculations or unsupported inference. Headline and chart claims weighted heavily.
4. **Constraint compliance** — advice, prediction, valuation-in-headline, banned words, number format,
   capitalisation, attribution, limitation disclosure. Regex catches a subset only; the rest is review.
5. **Dissent handling quality** — proportion of material dissents resolved by *evidence* rather than
   authority. Blocking dissents that reached publication improperly must be zero. Track whether rejected
   objections later prove correct.
6. **Evidence efficiency** — requisitions fulfilled vs unfulfilled, and whether fulfilment actually
   changed a decision, narrowed a claim, or prevented a bad one. More research is not automatically better.
7. **Audience-question coverage** — how many top-ranked owner questions are *answered* with local,
   comprehensible evidence. Answer quality, not mention.

Plus a **blinded quality rubric**: a separate evaluator instance that did not write the article, blind
to which agent wrote which section, judging whether it answers a question a non-listing owner actually
has, distinguishes the three suburbs only where evidence permits, makes uncertainty intelligible rather
than buried, keeps its conclusion proportionate to evidence, and could not be mistaken for a
recommendation. Blinding matters: otherwise we train for model identity and agreeable process.

**Deferred outcome signals** (when traffic exists): completion, scroll depth, chart interaction, return
visits, corrections/complaints, and whether later data invalidates the framing or merely moves a level.

Two hard rules on reward shape:

- **Do not optimise for clicks or time on page.** "Homeowner anxiety is highly clickable, and click
  optimisation will push the system toward alarmist headlines — the exact opposite of the trust asset."
- **A correction or retraction carries a very large negative reward**, especially when foreseeable from a
  limitation we already documented. And *"the number was technically correct but readers were predictably
  misled"* counts as a failure.

---

## 8. Two tensions to resolve with Will

**8.1 "No advice" vs. an evasive article.** GPT's read:

> "Your hard prohibition on advice is sensible, but can produce an article that is technically safe and
> emotionally evasive. 'Data only' must not mean 'numbers without interpretation.' The allowable middle
> ground is clearly labelled interpretation of what the data can and cannot establish — not a
> recommendation about what the reader should do."

I think this is right and consistent with the constitution, but it is close enough to the liability line
that Will should rule on the wording explicitly before we publish, not after.

**8.2 Artificial three-suburb symmetry.** Robina, Varsity Lakes and Burleigh Waters are not
interchangeable analytic units, and sample sizes differ. If the evidence is strong for one and weak for
another, the article must say so rather than manufacture equal treatment because all three are target
postcodes. This will make the article look lopsided. Confirm that is acceptable.

---

## 9. What is built

```
AI_Collaboration_Experiement/
├── 00_CONCEPT.md                     ← this file
├── lib/gpt_peer.py                   ← GPT transport. Constitution injected every turn;
│                                        every exchange appended to transcript.jsonl before return.
│                                        --health-check probes at realistic prompt size.
├── prompts/constitution.md           ← binding editorial + data-reliability rules, both agents
├── prompts/gpt_role.md               ← GPT's standing role and behavioural contract
└── runs/000_design_review/
    ├── transcript.jsonl
    └── GPT_DESIGN_CRITIQUE.md        ← the critique this document is built from
```

**Route verified:** `gpt-5.6-terra` responding, ~17.5k-char reasoned output on a real prompt.

### Not yet built

- The conductor (`run_article.py`) that walks phases 0–11 and enforces sealing/hashing
- Evidence-packet + omission-log schemas and the claim-ledger store
- Mechanical compliance gate (regex for forbidden words, `$1,250,000` format, advice/prediction phrasings)
- Dissent register store + blocking logic
- `process_log.jsonl` writer and the blinded rubric evaluator
- `job_run()` self-registration — required by CLAUDE.md Rule 7 the moment any part of this becomes
  scheduled. A one-off manual experiment does not need it; a recurring article run does.

---

## 10. Credential trap — read before running

Two OpenAI keys exist on this VM and **only one has credit**:

| Source | Tail | State |
|---|---|---|
| `OPENAI_API_KEY` in the shell environment / `.env` | `…GQWLIA` | credit-exhausted |
| `GPT API:` in `00_Run_Commands/gh-token-29Mar.txt` | `…8LqCIA` | funded — the one Will tops up |

`gpt_peer.py` therefore reads **the token file first** and the environment second (invert with
`GPT_KEY_SOURCE=env`). Two related traps:

- **A credit-exhausted account still answers tiny calls.** The quota reservation scales with prompt +
  `max_completion_tokens`, so `"say OK"` returns 200 while a real prompt returns 429
  `insufficient_quota`. A small smoke test is not proof the route works — that is why `--health-check`
  pads to ~2k prompt tokens.
- **The funded key belongs to the "Personal" org, not the default "Fields Real Estate" org.** Sending an
  explicit `OpenAI-Organization` header for the default org returns 401. Send no org header.

OpenRouter (`openai/gpt-5.6-terra`) is wired as a fallback but its balance was **negative** on
2026-08-07 ($13,748.48 credited / $13,748.62 used), so it 402s until topped up.
