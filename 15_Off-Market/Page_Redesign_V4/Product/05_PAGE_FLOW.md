# `/off-market/:slug` — the flow, in copy

**Status:** Draft copy for V4. **Compiled:** 2026-08-06. Supersedes the spec-form version.
**Reads with:** `04_ADVANTAGES_AND_SECTIONS.md` (advantages, limitations, kill list) · `03_CLAIMS_REGISTER.md` (what may be said publicly) · `01_USER_JOBS_AND_GAPS.md` (the evidence).

Copy is written out in full. `{braces}` are per-property values. Every section carries **why
it works** and, where there is one, **the ask** — a chance for the reader to request something
that opens a conversation.

---

## The voice

**Steady, not exciting.** The strongest tonal finding in the research: *"Every emotional
reaction to a value in the corpus is negative or anxious… Zero delight."* Nobody arrives
pleased. They arrive uncertain and slightly braced. Copy that performs enthusiasm will read as
a pitch; copy that is calm and specific will read as competence.

**Short sentences. Real numbers. No adjectives doing work a figure could do.** Banned:
stunning, nestled, boasting, rare opportunity, robust market. Never a single valuation figure
as a headline. Never advice. Never a prediction.

**The arc:** recognise → answer → prove → explain → apply → widen → protect → hand over
control. The reader is given the number early, then shown the working, and only then told why
other numbers differ. Proof before criticism — leading with why everyone else is unreliable,
before demonstrating our own method, is the weaker position and reads as defensive. Each section ends on a question the next one actually answers. Forward cues must be
honest — a promise the next section doesn't keep is the fastest way to lose someone who is
already sceptical.

---

# §0 — Arrival

> ## {street_number} {street_name}
> ### {suburb}, QLD {postcode}
>
> {land_size} m² · {property_type}
>
> **Last recorded sale ${last_sale_price}, {last_sale_month} {last_sale_year}. Held
> {years_held} years since.**
>
> We've put together what the sales around it say it would be worth today, and shown our
> working. It takes about a minute to build.
>
> *Nobody calls unless you ask.*

**Why this works.** The reader typed a bare address, so the first job is to confirm they are
in the right place, then immediately prove we hold something real about it. The last-sale line
is the exact fact that ranked us **#3 on Google, above Domain at #4**, while a page opening
with marketing copy ranked #6. Specific and checkable beats persuasive.

The privacy line is here, not at the end, because the anxiety arrives with them — *"Am I
declaring that I am selling?"* — and 87.5% of sessions never reach a second page. Reassurance
at the end reassures nobody.

**"It takes about a minute to build"** is doing two jobs: it sets an honest expectation for a
valuation that genuinely takes 30–90 seconds, and it makes the wait feel like work being done
rather than a page being slow.

> ⚠ **Never "We found your home."** Zero positive reactions to that framing across 5,685
> Reddit posts, and three hostility artefacts. The reader must feel they arrived, not that
> they were located.
> ⚠ **No ask here.** Never gate or interrupt the opening.

---

# §1 — The range

> ## What the sales around it say
>
> **${range_low} – ${range_high}**
>
> Built from {n_comps} sales, each adjusted for how it differs from this home.
> Worked out {computed_date}. The sales behind it are a median of {median_comp_age} months
> old.
>
> That's a range, not a figure — and the width of it is the honest part.

**Why this works.** They came for a number and we give it immediately. Three competing
automated estimates already sit above us on the same Google results page, so withholding ours
loses them for nothing.

The two lines nobody else writes are the **date it was worked out** and the **age of the
evidence**. Portal estimates carry neither, and *"Domain estimates and REA always lag (3-4
months)"* is a live complaint. Stating both costs us nothing and quietly raises a question
about every other number they've seen.

**No confidence label.** Ours don't discriminate — `high` 56.0% versus `medium` 57.5%.

**When the build can't run:** say so in one line and move on. *"We don't hold enough detail on
this home to build a range yet — here's what we can tell you."* Then jump to §4, which needs
nothing about this home at all.

> ### The ask
> **"Post the full report to this address"**
> One field, already filled with the address they're looking at. It goes in the mail.
>
> This is the highest-yield, lowest-friction ask on the page, and it is **self-verifying** —
> only the owner receives post at that address, so ownership is proved without asking anyone
> to prove anything. Postal reach is 176 against 29 for email.

---

# §2 — The working

> ## The sales behind that range, and what we changed about each one
>
> We looked at {n_assessed} sales and kept {n_comps}.
>
> No sale is a match. Each one differs from this home in ways that are worth money, so we price
> those differences and adjust.
>
> **{comp_address}** — sold ${comp_price}, {comp_date}, {comp_distance} away
> One more bedroom here **+${adj_bed}**
> {sqm_diff} m² more floor area **+${adj_floor}**
> That home is better renovated **−${adj_reno}**
> **Adjusted to ${comp_adjusted}**
>
> *[each comparable, the same way]*
>
> Every line is here because you should be able to disagree with one.

**Why this works, and why it comes second.** The moment someone is handed a number, *"why
should I believe that?"* is automatic. This answers it directly, with their own home's
figures, before we say a word about anybody else.

It converts an assertion into an argument. You can't argue with "$1,550,000". You can argue
with *"one more bedroom, +$113,110"* — and being able to argue with it is what makes it
trustworthy. That is precisely what a black-box estimate cannot offer.

It also does the work that §4 would otherwise have to do by assertion: watching a $1,300,000
sale become $1,521,873 **is** the demonstration that method moves a number by hundreds of
thousands of dollars. §4 then generalises something they have already seen happen.

**Its job is to be seen to exist, not to be read.** Only 13.9% of visitors click anything and
cards are skimmed in under two seconds. Show one comparable fully expanded, the rest collapsed.
The visible existence of the working does the persuading; a wall of it gets scrolled past by
the very people it was written for.

> ⚠ Blocked: `adjusted_price` and the component adjustments are **not persisted**. This
> section cannot render until they are.
> ⚠ Show the **distance** on every comparable. There is no radius filter — comparables have
> reached 2.57 km. Never write "near your street" unless the number supports it.

> ### The ask — the most important one on the page
> **"Ask us to review this"**
> *If something here looks wrong — a sale we shouldn't have used, a feature we've got wrong, a
> comparison that doesn't hold — tell us and a person will look at it.*
>
> The strongest thing we can put behind a claim: it **genuinely requires knowing it's your
> home**, and nobody offers it. The dominant grievance in the research is having no recourse —
> *"I contacted them to get a true reflection and after over 20 emails back and forward they
> said they couldn't or wouldn't change it."* A homeowner whose estimate was too low was told
> to go and hire an agent.
>
> It is also the best conversation starter we have: they open it by telling us something
> specific about their own home.

---

# §3 — How it's made, and how wrong it can be

> ## What this is, and what it isn't
>
> This is an estimate built from comparable sales. It is not a formal valuation, and it isn't
> an appraisal — a valuer inspects the property and carries professional liability for the
> figure. Nobody has been inside this home.
>
> **What we do:** take sales of homes near this one, adjust each for the ways it differs, weight
> them by how good a comparison they are, and publish the spread.
>
> **What we won't do:** use anything that happened after the fact. Every sale behind this figure
> closed *before* today. That sounds obvious; it is the single easiest way for a number like
> this to flatter itself, and it's worth knowing we've ruled it out.
>
> **Across the homes we've tested, adjusting narrows the spread by about 40%, and narrows it at
> all nine times out of ten.**
>
> **How wrong we are:** across {backtest_n} homes, our estimate is a median {error_rate}% away
> from what the home actually sold for. We publish that because a number without an error rate
> is just a number.

**Why this works.** The only topic on the page with **validated market demand** — the Fields
article on estimate accuracy outperformed on Facebook. Add 85 autocomplete searches for how
valuation works and what gets checked, plus the trust hedges people actually type: `actually
worth`, `really worth`.

Publishing the error rate is also armour. Zillow's defence when it was sued over its estimates
was its own published accuracy. Nobody in Australia publishes one.

*"What this isn't"* does double duty — the safest framing of our own output, and the boundary
for people searching valuations for probate, divorce, capital gains or an aged pension
assessment.

> ⚠ Pin **one** error-rate figure with its sample and date. Both 11.1% and 11.6% are in
> circulation.
> ⚠ Never frame it as better than any portal or agent. We have no valid comparison, in either
> direction.

> ### The ask
> **"Send me the method in full"** — the long-form explanation, posted. Low commitment, high
> signal: someone who requests this is doing real research.

---

# §4 — Why you've seen other numbers

> ## Why the other estimates say something different
>
> You've almost certainly seen other figures for this home. Here's what explains the gap.
>
> You just watched a sale at $1,300,000 become $1,521,873 once we priced the differences. That
> is what choosing a different set of sales does to the answer.
>
> Most valuations are built on three of them. Pick three similar sales nearby, see where the
> home sits between them.
>
> We tested what that actually produces. We took 512 homes that have since sold, found every
> set of three comparable sales that could reasonably have been chosen, and worked out what
> each set would have said.
>
> **The gap between the highest and lowest defensible answer was a median of $469,000 — about a
> third of the home's value.** On 77% of homes it was more than 20% of the value.
>
> The part that surprised us: a near-perfect comparable — one landing within 2% of the eventual
> sale price — was sitting in the available sales on **73.6%** of those homes. The worst choice
> available was more than 20% out on **73.4%**.
>
> **The right answer is nearly always there. Three sales just can't tell you which one it is.**

**Why this works here rather than earlier.** By this point they have watched our method move a
number in their own home's figures. This section generalises what they have already seen —
it is confirmation, not setup.

That also fixes the tone. Placed before our own working it reads as pre-emptive criticism;
placed after, it is an explanation of something they genuinely want explained — the competing
estimates already sitting above us on the same Google results page.

It names nobody, uses only public sales data, and criticises a **method** rather than people.

> ⚠ **Tone check.** Fields is a licensed agency that could use that method. Write it as *"here
> is why we don't do it that way"* — never *"agents are unreliable."*
> ⚠ **Do not attach an accuracy claim.** Against that method we are a dead heat: a randomly
> chosen set of three beats us **exactly 50.0%** of the time. The claim is that our answer
> doesn't move depending on who picked the sales — **determinacy**, not accuracy.

> ### The ask
> None. This section's job is to land, then hand over to §5.

---

# §5 — If someone else has given you a number

> ## Bank valuations, and why they're usually lower
>
> If you've had a figure from a lender, it probably sat below this range. That's normal, and
> it isn't a comment on your home.
>
> A lender isn't asking *what would this sell for*. It's asking *what could we recover if we
> had to sell it in a hurry*. Those are different questions, and the second one is deliberately
> conservative.
>
> **The top of this range is ${range_high}**, worked out {computed_date}.
>
> If you're taking a figure to a lender or a broker, the number matters less than being able to
> show where it came from — which is what the previous section is for.

**Why this works.** The **Equity Checker is the single largest group in the research (~115
posts)** and nothing currently serves them. What they say, almost word for word: *"Anyone else
had an experience where the bank undervalued their property? And not by just 1-3% but by a
lot?"* and *"Try to hit the maximum number the bank will accept."*

They need the **upper bound stated plainly**, the **date**, and an explanation for the gap.
This section gives all three and needs to know nothing about their finances.

> ⚠ **The privacy line runs through here.** Their equity, loan balance or LVR is derived
> financial inference and is banned. The one clear privacy violation in the whole corpus was
> exactly this: *"what absolutely floored me was they had even estimated what we owe on it."*
> Explain the category difference. Never compute their position.

> ### The ask
> **"Send this in writing"** — the range, the date, and the sales behind it, as a document they
> can hand to a broker. Genuinely useful, and a strong reason to give us an address.

---

# §6 — What's moving

> ## What's changed around this home
>
> {n_sales} homes like this one have sold in {suburb} in the last twelve months, at a median of
> ${suburb_median}. Twelve months earlier it was ${suburb_median_prior}.
>
> Homes here are taking a median of {dom} days to sell, against {dom_prior} a year ago.
>
> {n_active} are on the market now. {n_matching} are close enough to this home to be competing
> for the same buyer.
>
> We're not going to tell you where this goes next — nobody knows, and anyone who says
> otherwise is guessing. What we can do is show you the same indicators we watch, and tell you
> when they move.

**Why this works.** The largest adjacent topic by a distance — roughly **670** persistence
across `gold coast property market forecast`, `forecast for next 5 years`, `crash prediction`
and `crash`.

It's also the *living* answer, and the reason to come back: a static number is worth
something, a number that explains its own movement is worth returning to. It speaks directly
to the loudest volatility complaint: *"In the last 3 months my house has dropped 40k increased
50k and dropped 40k, is this even possible."*

> ⚠ **Rule 5 binds hardest here.** Report indicators. Conditional language only. Never a
> forecast, never "prices will fall", never advice. The demand is for a prediction; what we may
> supply is evidence — and saying so plainly is itself differentiating.

> ### The ask
> **"Tell me when this changes"** — an alert when the range moves, with the reason it moved.
> Requires somewhere to send it, so it's an honest reason to ask.

---

# §7 — What sits under it

> ## Flood and overlays
>
> {flood_status_line}
>
> Source: {source}, {source_date}. {limitation_line}
>
> This is what the public mapping shows for this address. It isn't a survey, and it doesn't
> account for work done since. What it's for is knowing which questions to ask.

**Why this works.** `does burleigh waters flood` is the **most persistent search suggestion in
our entire corpus at 546 — two and a half times the next item** — and the only question-form
entry near the top. Plus 71 further hazard searches: flood zone, bushfire, heritage, asbestos.

It also resolves an apparent contradiction in our own research. No consumer was ever found
complaining that a listing omitted flood risk — because they don't complain to the portal.
**They go to Google instead.** Absence of complaint was mistaken for absence of demand.

> ⚠ Data, source, limitation. No advice, no reassurance. Burleigh Waters only for now.
> ⚠ Precedent: Trulia built crime layers, showed them off at the White House in 2012, and
> withdrew them in 2022 on fairness grounds. Flood stands up on measurement grounds where crime
> doesn't — but the source and its limits go on the page.

> ### The ask
> **"Send me the detail for this address"** — the underlying mapping and what it means here.

---

# §8 — What you can do about any of it

> ## This is your home's page. You can change it.
>
> Everything here was built from public records and sales data. Some of it will be wrong — a
> renovation we don't know about, a room count that's out of date, a sale that shouldn't have
> been used.
>
> Tell us, and we'll fix it and rebuild the figure in front of you.
>
> **Nobody calls unless you ask.** No agent is paying to appear here, and nothing you do on
> this page becomes a lead.

**Why this works.** *"It's wrong about my house and there's no way to fix it"* is a dominant,
repeatedly evidenced grievance — *"Our home is stunning and has everything you could ever want,
yet it still shows as vacant land."* Every reviewer in that cluster reports that nobody replied.

Correction is also the one thing that genuinely **requires** knowing it's their home, which
makes claiming a functional necessity rather than a toll.

And the last line is the sharpest contrast we own, defensible entirely from REA's own filings:
they report homeowner engagement to shareholders as *"valuable seller leads delivered to our
customers"*, with better-paying agents receiving **36% more** of them.

> ### The ask
> **"Correct something"** · **"Claim this page"**
> Claiming is offered *here*, at the end, after the page has already answered — never as the
> price of entry.

---

# The asks, collected

Nine sections, six asks. Each is a reason to talk, not a toll gate.

| § | The ask | What it gives us | Why they'd do it |
|---|---|---|---|
| 1 | Post the report to this address | **A verified owner + postal address** | Self-verifying, one field, 6× the reach of email |
| 2 | **Ask us to review this** | An opened conversation, in their words | Nobody else will fix a number about their home |
| 3 | Send me the method in full | A research-stage contact | Low commitment, high intent signal |
| 5 | Send this in writing | An address, and a live financial context | Genuinely useful to a broker |
| 6 | Tell me when this changes | A durable channel | The only page that explains its own movement |
| 7 | Send me the detail for this address | An address | 546 persistence says they want it |

**Capture by post or SMS — never a login.** The gate on `/for-sale` has converted **2 people**
in its lifetime. The SMS claim path already exists, works, and yields a phone number by
construction.

**Never gated:** the range, the comparables, the adjustments, the methodology, the error rate,
the market indicators, the hazard data. All of it is public record or our analysis of it, and
calling any of it "sensitive" to justify a gate would be a false claim (C15).

---

## Build state

| § | Copy | Data | Blocked by |
|---|---|---|---|
| 0 | ✅ ready | ✅ | — |
| 1 | ✅ ready | on-demand, 30–90s | load testing |
| 2 | ✅ ready | ❌ | `adjusted_price` not persisted |
| 3 | ✅ ready | error rate exists | pin one figure |
| 4 | ✅ ready | ✅ measured | — **the one thing blocked by nothing** |
| 5 | ✅ ready | ✅ | — |
| 6 | ✅ ready | ✅ | Rule 5 review |
| 7 | ✅ ready | Burleigh Waters only | other suburbs |
| 8 | ✅ ready | ❌ | review flow; "nobody calls" as an operational rule |

## Open

1. **Mobile.** Nine value-then-ask blocks stacked could read as nine paywalls. Prototype before committing.
1b. **Fallback order when there is no range.** §2 and §3 depend on a valuation; §4 does not.
   Where the build can't run, go §0 → §1 (plainly: not enough detail) → **§4** → §6. The page
   still has substance, but the arc inverts — say why numbers differ before we can show ours.
2. **Does §2 land as honest or as attack?** It criticises a method Fields is licensed to use.
3. **"Nobody calls unless you ask"** appears twice and is load-bearing both times. It cannot ship until it is an operational rule.
