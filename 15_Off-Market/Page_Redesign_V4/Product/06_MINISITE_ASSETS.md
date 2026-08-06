# What the house mini-site already holds that the V4 flow should take

**Compiled:** 2026-08-06. **Source:** `11_House_Mini_Site/` — V1 shipped, V2 specified.
**For:** `05_PAGE_FLOW.md`.

Mini-site **Session 1** ("Where your home stands right now") answers almost exactly the job
`/off-market/:slug` answers — *"Is the number real, and what is happening around my home?"* It
is further developed than our flow in several places. This is the salvage list.

---

## 1. Copy devices worth taking outright

### 1.1 "The three questions" — a stronger opening than our §0

> **You may be trying to answer three questions privately.**
>
> Is the number attached to this home real? Is this the wrong time to move? And if you sold,
> where would you go next?
>
> This is a private walkthrough of those questions for **{address}**. Nothing here starts a
> selling process, and nobody calls unless you ask.

Our §0 confirms the address and states a fact. This does that **and names what they came for**
without making them say it. It is the better opening.

**Its rules travel with it:**
- **"You may be" is load-bearing and may not be strengthened.** The psychological read is *"a hypothesis, not a finding"* — hedging is how a hypothesis is offered, and a reader who doesn't recognise themselves reads past it harmlessly. **Never** *"we know how stressful this is"*, never *"it's natural to feel uncertain"*.
- **Never make the reader admit intent.** The card deliberately does not ask whether they are selling, and nothing later may either. **Our flow never stated this rule and should.**

### 1.2 "Two true things that point in different directions" — better than our §7

> **The median Robina house sold in 34 days last quarter, and 45.7% of sales still moved
> quickly. But far fewer homes are selling at all, and the median took 24.5 days a year
> earlier.**
>
> Both readings are true, and they support opposite conclusions — which is why a single market
> headline cannot resolve the decision for this home.

Our §7 says *"we're not going to tell you where this goes next"*, which is a refusal. This is
better: it **shows** the ambiguity rather than announcing that we won't resolve it. Name it,
give both readings, let the reader draw the inference.

Its rule: **never characterise the market** — cooling, softening, holding up, resilient are
predictions in disguise, and "robust market" is a banned phrase.

### 1.3 Suppression as a credential — this solves our hardest problem

> Quarterly figures for Robina are not shown. The recent quarters hold too few sales to carry
> a quarter-on-quarter claim.

And the rule behind it: *"saying why a number is missing is worth more than the number. Every
competitor draws the line anyway. **Refusing to is a credential.**"*

**This reframes the no-range state entirely.** Our §1 currently says *"we don't hold enough
detail on this home to build a range yet"* and moves on apologetically. The mini-site's posture
is the opposite: **stating precisely why a figure is absent is itself the demonstration of
method.** That converts the majority state from an embarrassment into the strongest possible
proof that we don't make numbers up.

Rewrite §1's fallback in this register.

### 1.4 Confirmations of things we already had

- *"Forty-one sales reviewed; eight close enough to use"* — *"beats any claim about thousands of records."* Confirms A12.
- The error-rate card is *"the single most powerful trust asset we hold"* — publishing that the method has been out by 11.1%, and that this is *why* a band is given rather than a figure, *"demonstrates institutional honesty rather than marketing confidence."* Confirms §3.
- **94% of these visitors view exactly one address** — *"the signature of a private self-check rather than browsing."*
- Recorded search behaviour is decision-rehearsal: *"should I sell now or wait 2026"*, *"cost of selling a house QLD"*.

---

## 2. ⚠ The operational landmine — read before shipping "nobody calls unless you ask"

**`offmarket-intent-alert.mjs` already fires a Telegram alert to Will when a visitor merely
reaches the end of a deck, having asked for nothing.**

The mini-site spec is unambiguous about what that means:

> *"The alert does not break this promise; **acting on it would.** This line commits Fields to
> a rule: an intent alert is not permission to make contact. It must be ratified before this
> card ships. Every commitment must be operationally true before real traffic, and this is the
> one a reader would feel most betrayed by."*

**"Nobody calls unless you ask" appears twice in our flow and is load-bearing both times.** It
is our single strongest differentiator (A6). A live system currently tells Will when someone
reads to the end. **The promise is only true if he does not act on it, and that has to be a
ratified rule, not an intention.**

---

## 3. The print edition — a ready-made spec for our §1 ask

Our §1 ask is *"post the full report to this address."* The mini-site has already designed
exactly that artefact, and its constraints are hard-won:

**A4 folded to A5, four sides. No CTA anywhere.**

> *"This reaches an owner who did not ask for it; the moment it mentions appraisals or selling
> services it reads as solicitation."*

| Side | Contents |
|---|---|
| 1 (front) | The three questions, then the address. **QR-HOME** lower right |
| 2 | The home, and the band as the largest type on the page |
| 3 | The full sale table with distances; the two-true-things pair as a stat block |
| 4 (back) | The three readings and the limit. **QR-NEXT** centred |

**Print rules that transfer directly:**
- No single valuation figure anywhere, headline included. The band travels alone.
- The on-screen expansion becomes a printed side — on paper there is nothing to tap, so the proof is simply printed.
- Every number carries its source and review date **on the same side**.
- No "tap", "scroll" or "click".
- **No QR-ANSWER where the piece asks nothing** — see the defect below.

---

## 4. The reader-question model — and the defect that would break our loop

V2 defines ten whitelisted `questionId`s, stored at
`property_reports.selling_plan.answers.<questionId>` in `property-plan-submit.mjs`.

**⚠ The defect we would inherit.** Writes are gated on a `device_token` in localStorage:

> *"A reader arriving from a printed QR code has no token, so `PlanQuestion.persist()` returns
> early and the answer is **silently discarded** — the reader sees the option highlight and
> believes it saved."*

**This is exactly our post → QR → respond loop.** If we post a report with a QR and invite a
reply, the reply is dropped on the floor and the reader is shown a success state. Until a
signed `?plan_token=` is accepted server-side, **no printed piece may present a question as
answerable online.**

**Two design rules worth adopting:**
- **One question maximum per unit.** Sessions 1, 3 and 7 ask nothing at all. Our flow currently has six asks across ten sections — that is probably too many, and §1, §3 and §5 are the weakest of them.
- **Never ask the owner to design the campaign.** `open-homes-cadence` and `marketing-channels` were retired for exactly this: *"these asked the owner to design the campaign."* Ours must not drift the same way.

---

## 5. Data already wired

`market_pulse.data_snapshot` carries everything §7 needs: `current_median_price`,
`yoy_growth_pct`, `dom_median`, `dom_yoy_prev`, `dom_quick_sales_pct`, and —
usefully — **`qoq_suppressed_reason`**. The data model already supports stating *why* a figure
is withheld.

> ⚠ **Staleness trap.** `summary`, `data_snapshot` and `narrative.pillars` go stale
> independently, and a partial `$set` touches only what it names. Read `data_snapshot` only;
> anything from `narrative.*` must be verified live per CLAUDE.md Rule 6.

---

## 6. The gap the mini-site diagnosed, which we share

Its four conclusions the reader must reach:

| # | Conclusion | Mini-site state | **Our flow** |
|---|---|---|---|
| 1 | "They understand my exact property" | Very strong | **Strong** — §0, §2, §5 |
| 2 | "They tell me the truth even when it weakens their argument" | Strongest aspect | **Strong** — §3, §4, and the suppression posture |
| 3 | "They understand what is happening in my life" | **The major missing layer** | **Missing** |
| 4 | "They have a clear process and will protect me" | **Not yet built** | **Missing** |

*"The sessions as drafted are exceptionally credible, but more analytical than emotionally
guided."* **That diagnosis applies to our flow unchanged.** Conclusions 1 and 2 are close to
done; 3 and 4 are absent.

For `/off-market` this is less damaging than for a seller product — the reader is not
necessarily selling, so conclusion 4 belongs downstream. But **conclusion 3 is the reason "the
three questions" opening works**, and it is the cheapest available fix: naming what someone is
privately weighing is understanding their life without claiming to.

---

## 7. What NOT to take

- **The seven-session seller journey.** GPT is explicit that it is the deeper path, not the initial product. It stays in the mini-site.
- **Three charts, all unusable:** `ch7-1-buyer-pool` inverted, `ch7-4-portal-traffic` drifted, `ch7-3-marketing-benefit` unsourced.
- **Confidence grades.** The owner draft prints "confidence grade: high"; our measurement says the label is non-discriminating. Already C12.

---

## Actions for `05_PAGE_FLOW.md`

1. Replace the §0 opening with **the three questions**, hedging rules intact.
2. Add **"never make the reader admit intent"** to the voice section.
3. Rewrite §7 as **two true things that point in different directions**.
4. Rewrite §1's no-range fallback as a **credential**, not an apology.
5. **Ratify the intent-alert rule** before "nobody calls unless you ask" ships anywhere.
6. Adopt the **print spec** for the §1 ask, including *no CTA anywhere*.
7. Fix the **`device_token` defect** before any posted QR invites a reply.
8. Reconsider **six asks across ten sections** against the one-per-unit rule.
