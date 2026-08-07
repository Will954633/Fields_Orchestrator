# GPT as Principal — the collaboration mode that actually works

**Status:** validated in production by Will, 2026-08-07/08, during an SEO optimisation session.
**Supersedes nothing.** This is a *different* mode from the peer-auditor experiment in
`00_CONCEPT.md`, and the evidence so far is that this one works and that one does not.

---

## 1. What it is

Claude runs the work. GPT answers **as Will** — approving, redirecting, correcting reasoning,
setting policy and sequencing the next move. Will relays messages in both directions and retains
the veto, but does not have to compose every reply himself.

```
Claude  --(findings, questions, "which of these two first?")-->  Will  --(paste)-->  GPT
GPT     --(decision, correction, policy, priority)------------>  Will  --(paste)-->  Claude
```

The critical distinction from the failed peer-auditor mode:

| | Peer auditor (00_CONCEPT.md) | **Principal (this doc)** |
|---|---|---|
| GPT's job | find defects Claude missed | decide what Claude does next |
| Needs tool access | yes — and it loses badly without it | **no** |
| Needs to verify claims | yes | no — it interrogates Claude's reasoning |
| Measured outcome | ~5:1 loss to Claude, and the test was rigged (§4) | Will judged it "far more productive than if it had just been me" |

**Why the asymmetry stops mattering here.** The peer-auditor mode asked GPT to compete at
*evidence gathering*, where a text-only model on a restricted shell is crippled by construction.
This mode asks it to compete at *judgement over evidence someone else gathered* — which is exactly
what an untooled model with a fresh perspective is good at, and what a sole operator has least time
for.

---

## 2. Evidence it works — five things GPT did in one session that changed the outcome

All five are from the 2026-08-07/08 SEO transcript. None required tool access.

**2.1 It caught Claude asserting a false causal mechanism.** Claude proposed adding outbound links
from `/off-market/` pages and justified it by "0/400 off-market pages have a non-sitemap referrer,
which explains their low recrawl priority." GPT separated the two effects:

> "Intervention 2 as currently designed adds: off-market page → suburb hub. That does not fix:
> site → off-market page. The page remains an orphan in the inbound-link sense. […] I would not
> claim that this contextual block will materially increase recrawl frequency of the
> `/off-market/` source pages."

Then it **reframed the hypothesis into a defensible one** — "use Fields' address-level organic
footprint to reinforce the suburb-level information architecture", not "fix off-market recrawl" —
and noted these are different hypotheses with different tests. That is a research-design
correction, not a code review.

**2.2 It rejected copy on liability/accuracy grounds Claude had not considered.** Claude proposed
"see what yours is measured against". GPT:

> "'measured against' could imply those 39 listings are literally the valuation/comparable set used
> to calculate this home's value. They are broader market competition."

That is precisely the class of error CLAUDE.md Rule 5 exists to prevent, caught in proposed copy
before it shipped.

**2.3 It refused a plausible convenience that would have created a false relationship.** On
suburbs with no listing page, Claude's design fell back to `/for-sale-v3`. GPT: *"No fake
fallback. The module should be generated from actual route availability."*

**2.4 It set forward-looking policy, not just a fix.** On removing 4,559 noindex URLs from the
sitemap, Will asked whether the imminent attached-homes launch should reverse the decision. GPT
said no — but added the instruction that mattered:

> "I would tell Claude not to encode 'slash in address = permanently excluded' as an SEO rule. It
> should instead be something like: supported property type + sufficient data + valid entity
> resolution = indexable."

That prevents a fix today from becoming an obstacle at launch. A peer auditor would not have said
it because it is not a defect — it is a design constraint that only the principal can impose.

**2.5 It corrected a technical belief we were both relying on.** Claude had reasoned that
`noindex, follow` preserves link equity indefinitely. GPT:

> "a page left noindex long enough may eventually be treated effectively like `noindex, nofollow`
> […] do not model them as reliable long-term PageRank conduits."

And it distinguished a real defect from an SEO myth — *"having two H1 elements is not, by itself,
the important defect"* — which stopped the fix being justified on the wrong grounds.

**Cumulative effect on the session:** it kept the two-hop redirect (correctly, citing Google's own
10-hop tolerance), killed a UX-damaging global footer, tightened the copy, sequenced sitemap-fix
before H1-fix, demanded a dry-run manifest before 4,559 URLs were removed, and specified the
invariant monitor's acceptance criteria (`200 + index,follow + valid self-canonical + real content`,
explicitly rejecting "200 alone"). That last one caught a **third** live defect immediately.

---

## 3. Why this is more valuable than a second auditor

**It attacks the bottleneck.** Fields is a sole operator. Claude can generate findings far faster
than one person can adjudicate them. The scarce resource is not defect discovery — today's battery
produced ~30 findings in an afternoon — it is *deciding which to act on, in what order, and on what
justification*. This mode manufactures that capacity.

**It resists Claude's characteristic failure.** Claude's failure mode in this codebase is
documented and consistent: it acts on a plausible mechanism before checking it. On 2026-08-07 it
repointed a chart at "better" data without checking that the new series had a different start date,
density and reliability semantics, and shipped a worse chart (`[CHART-INLINE-MEDIAN-2]`). It also
asserted twice that 757 dropped URLs "would retry automatically because the watermark was never
advanced" — the watermark file said otherwise and one `cat` would have caught it. **Both are
exactly what §2.1 shows GPT catching.** An independent reader who cannot run the code has to
interrogate the argument, which is the check Claude most needs and least applies to itself.

**It cannot be replaced by Claude reviewing itself.** Claude's self-review inherits its own frame.
GPT's value in the transcript came from not sharing the frame — it asked "which hypothesis are we
actually testing?", which is not a question that arises from inside the hypothesis.

---

## 4. ⚠ Correction to the record — the peer-auditor experiment was unfair, and I reported it as if it were not

Will challenged the round-2 conclusion ("Claude wins ~5:1") as biased. He was right. The
distortions, verified from the run artifacts:

**4.1 I penalised GPT for breaking a rule it was never given.** I reported that "2 of GPT's 8
findings were re-reports… a 25% noise rate despite a direct instruction." The shared exclusion
brief (`experiments/_already_fixed.md`) contains **zero** mentions of seasonality, price-tier
liquidity or the PropRadar coverage-gap queue — verified by grep. Those exclusions existed **only
in the Claude subagent prompt, which I wrote separately.** GPT reported findings it had no way to
know were stale, and I scored them as noise. That sentence was false.

**4.2 The tool surfaces were not comparable, and the gap maps directly onto the score.** GPT had 24
read-only shell commands (`ALLOW` in `lib/vm_agent.py`) — **no `python3`, no `curl`, no `sudo`, no
`gcloud`/`bq`, no authenticated HTTP**. The Claude arms had unrestricted Bash plus the PostHog MCP.
Claude's best findings came from precisely what GPT could not do:

- the 89%-of-a-core mongod find required `sudo` on `/var/log/mongodb/mongod.log`;
- the JustCall / Bright Data / OpenRouter cost finds required authenticated provider API calls;
- the per-resource dollar figures required `bq` against the billing export;
- most growth findings required PostHog HogQL.

So **E1 (cost) was structurally unwinnable for GPT** — and it said so, correctly, naming
provider-console access as its blind spot. I recorded its 0 findings under a table headed "Verdict:
Claude", which presents a harness limit as a capability result.

**4.3 The budgets differed by ~30x.** GPT: 4,513–6,200 output tokens per run, capped at 45 tool
calls. Claude arms: ~165,000–205,000 tokens, 58–83 tool calls, uncapped.

**4.4 I wrote the exclusion list in Claude's framing**, from round-1 findings that were
predominantly Claude's, and gave the Claude E4 arm a curated list of promising collections to
examine that GPT never received.

**What the experiment actually measured:** how much a model can find when given broad privileged
access and a large budget, versus a restricted one. It did not measure the models. **The 5:1 figure
should not be cited.** My caveat at the time ("the harness caps GPT's ceiling") did not change the
conclusion I drew, which is the signature of a biased report rather than an honest one.

**Standing lesson for this folder:** an A/B between agents is only valid if tool surface, budget and
briefing are identical. If they cannot be made identical — and here they cannot, because GPT is
remote and unsandboxed — then **do not run capability comparisons at all.** Compare modes of
contribution instead, which is what §2 does.

---

## 5. Operating protocol

**Setup.** Paste into GPT at the start of a session:

1. `CLAUDE.md` Rules 1–7b (especially Rule 5 editorial constraints and 7b outcome assertions).
2. The business one-liner: pre-revenue, sole operator, buyer-first/seller-funded, North Star =
   inbound enquiry, three target suburbs.
3. This instruction: *"You are answering as Will. Claude executes; you decide. Interrogate its
   reasoning, especially any causal claim. You cannot run code — never imply you verified anything.
   Ask for evidence instead."*

**Per exchange.** Claude ends each substantive turn with an explicit decision request — options,
the tradeoff, and what it recommends. GPT replies with a decision, the reason, and any policy that
should outlive this fix. Will relays, and overrides whenever he disagrees.

**What GPT must be told to do.** Demand a dry-run manifest before any bulk change (it did this
unprompted for the 4,559 URLs and it was the right call). Distinguish "verified" from "inferred" in
Claude's reports. Name the hypothesis being tested. State acceptance criteria for verification.

**What GPT must never do — hard limits.**

- **Never treat its output as verified fact.** It has no tools. Every factual claim it makes about
  this system is a hypothesis for Claude to check. It was wrong about nothing in the SEO transcript
  because it stuck to reasoning and cited external Google guidance rather than asserting local facts.
- **Never let it authorise money, deletion, deployment to production, or anything outward-facing.**
  Those stay with Will. GPT can recommend; the decision is not delegable, and "GPT said yes" must
  never be recorded as approval. (This session's own system prompt is explicit that a notification
  or a relayed message is not user consent.)
- **Never let it rule on liability wording.** It can flag risk — §2.2 shows it doing that well —
  but Rule 5 judgements about published claims are Will's.
- **Watch for authority laundering.** The risk of this mode is the inverse of the peer-auditor
  mode's "epistemic laundering": there, GPT's blind review made Claude's assumptions look
  externally validated; here, GPT's *decisions* can make a course of action look Will-approved when
  Will only relayed it. Mitigation: Will reads GPT's decision before pasting it, and anything
  irreversible gets an explicit human yes.

---

## 6. Where to take it next

**Reduce the relay cost.** Today Will copy-pastes both directions. The obvious build is a thin
loop: Claude writes its decision request to a file, a script sends it to GPT with the standing
context, and the reply comes back — with Will on the channel and able to interject. `lib/gpt_peer.py`
already does the transport, injects a constitution on every turn, and logs both sides to
`transcript.jsonl`; it needs a principal role prompt instead of the peer one, and **no tool access at
all**, which makes it simpler than the auditor harness rather than harder.

**Keep the transcripts.** They are the record of *why* decisions were made, which the fix-history
does not capture. §2.1's hypothesis reframing is more valuable than any single fix in that session.

**Measure the right thing.** Not "did GPT find more than Claude" — that question is now retired.
The useful measures are: how often GPT's redirection changed the plan; how often a GPT-imposed
policy prevented a later problem; and whether Will's per-decision time falls. Those are all
observable from the transcript without a rigged comparison.

**One honest unknown.** Will's judgement that the session was "far more productive" is a sample of
one, from the participant. It is the best evidence available and it is not blind. The cheapest way
to strengthen it is to run a session in this mode and note, at the end, which decisions Will would
have made differently — not to construct another A/B.
