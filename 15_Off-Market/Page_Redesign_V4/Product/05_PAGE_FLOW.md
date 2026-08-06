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

**Never make the reader admit intent.** Inherited from the mini-site. Nothing on this page asks
whether they are selling, and no section may imply it. Where we name what they might be
weighing, we hedge — *"You may be…"* — because it is offered as a hypothesis. **The hedge is
load-bearing and may not be strengthened.** Never *"we know how stressful this is."*

**Every number gets a translation line** (`SoWhat`, shipped in the mini-site). Its rule: *no
stat tile, comp count, scarcity figure or competitor number ships without one.* One or two
sentences saying why a reader should care — *"the translation of evidence into risk-reduction,
not a second paragraph."* The diagnosis behind it applies to us unchanged: **the product is
data-first when the reader is fear-first.**

**Every claim names its source** (`CitationStrip`). Its rule is absolute: *if a claim doesn't
have a source, the block should not have rendered.*

**Columns run thesis → applied, not free → locked.** The shipped `FearSection` splits the
general finding on the left and the same data anchored to this home on the right. Moving right
gets **more** personal, so the page reads as deepening rather than withholding. Asks sit
beneath, never in the right column.

**The arc:** recognise → answer → prove → explain → apply → widen → protect → hand over
control. The reader is given the number early, then shown the working, and only then told why
other numbers differ. Proof before criticism — leading with why everyone else is unreliable,
before demonstrating our own method, is the weaker position and reads as defensive. Each section ends on a question the next one actually answers. Forward cues must be
honest — a promise the next section doesn't keep is the fastest way to lose someone who is
already sceptical.

---

## The mechanics — taken from the live V3 deck

The shipped deck is more crafted than this document was. Four devices carry it, and all four
transfer. **Nothing from the Matrix intro or the glass-shatter outro comes across.**

### M1 · The chained question — the strongest structural device in the deck

Every card closes with **the reader's own next question, in their voice**, and the next card
opens by answering it:

> *…What was interesting?* → **"Here's what stood out."**
> *…So what did you find?* → **"Your backdrop is the story."**
> *…Why does that matter?* → **"A buyer can renovate a house. They can't manufacture a park at the back fence."**
> *…So what will buyers actually pay for in mine?* → **"Here's what carries the price."**
> *…And who is that buyer?* → **"Someone is already looking for a home like yours."**
> *…So where does that put its value?* → **"Based on everything we've analysed…"**

Each card is a closed loop — `answer` → `headline` → `next`. The reader is never deciding
whether to continue; they are being handed the question they already had. **This document had
"each section ends on a question the next answers" as a rule and never wrote the questions.
They must be written, in the reader's voice, not ours.**

### M2 · The curiosity gap — name that something exists, withhold what it is

Card 02 never says what it found:

> *"There's one thing right at your boundary that very few homes nearby can claim — and it
> keeps quietly removing your competition."*

Card 03 reveals it. This is a textbook information gap: curiosity is strongest when you know an
answer exists and don't have it. It is per-angle — `copy.yaml` carries a distinct hook line for
all twelve `lead_angle` values, so the tease is specific without being the answer.

> ⚠ **Apply the gap to the FEATURE, not the valuation.** V3 delays the number to card 07 of 9,
> which on our measured funnel — 47–57% never advance past the first card — is seen by roughly
> one session in seven. The reader came for the range. **Give the range at §1 and put the
> curiosity gap on the feature that explains where in the range they sit.** The hook was always
> about the boundary, not the number.

### M3 · The emblem system — personalisation at scale, and it is already built

`angle_media.yaml` maps `lead_angle` → drawing → caption → detach element. **87% of 18,070 built
decks carry an emblem.**

| Angle | Share | Emblem | Caption |
|---|---|---|---|
| parkland | 32.4% | bushbirds | *The bushland at your boundary* |
| school_walk | 12.8% | satchel | *The walk, not the drive* |
| water_adjacent | 12.6% | reeds | *Lakeside reeds · the edge that stays open* |
| land_prestige | 12.4% | dog | *Room to run · what the block actually buys* |
| beachside | 9.3% | pandanus | *Pandanus · the coastal marker* |

Plus `kind_routes` sub-routing — a golf course gets a flag, bushland gets banksia — off
`green_space.premium.kind`.

**The detach mechanic is the best bit.** One element leaves the finished drawing, travels the
page, and comes to rest beside the next card's copy: the pandanus fruit, the dog's ball, the
golf ball. It carries the reader from 03 to 04 physically, so the scroll feels authored rather
than paginated. Only three emblems have one — the rest are an open question in `PLAN.md`.

**And the restraint is as good as the ornament.** Six angles are declared `text_only` on
purpose — `market_context`, `scarcity`, `thin_competition`, `scale`, `prestige_value`,
`renovation_upside` — because *"there is no object to draw, and the deck carries no decoration
anywhere else, so an image on a card that is not claiming a physical feature would be the only
decorative element on the page."* Keep that rule.

### M4 · The reframe — the emotional peak, and it costs nothing

Card 06 ends:

> **"Right now it's your home. To them, it's the one they've been waiting for."**

A perspective shift: the reader sees their own home through someone else's eyes. It is the one
line in the deck that isn't data, and it earns its place because six cards of evidence came
first. **One per page, at most, and only after the proof.**

---

# §0 — Arrival

> ## {street_number} {street_name}
> ### {suburb}, QLD {postcode}
>
> {land_size} m² · {property_type} · **Last recorded sale ${last_sale_price},
> {last_sale_month} {last_sale_year}. Held {years_held} years since.**
>
> **You may be trying to answer three questions privately.**
>
> Is the number attached to this home real? Is this the wrong time to move? And if you sold,
> where would you go next?
>
> This is a private walkthrough of the first of them. Nothing here starts a selling process,
> and **nobody calls unless you ask**.
>
> We're building it from the sales around this home now. It takes about a minute.

**Why this works.** The reader typed a bare address, so the first job is to confirm they are in
the right place, then immediately prove we hold something real about it. The last-sale line is
the exact fact that ranked us **#3 on Google, above Domain at #4**, while a page opening with
marketing copy ranked #6. Specific and checkable beats persuasive.

**The three questions are taken from the mini-site**, where they open Session 1. They name what
the reader came for without making them say it — and they do the one thing our evidence says we
were missing: *"they understand what is happening in my life."* Naming what someone is privately
weighing is understanding their situation without claiming to.

**Only the first question is promised here**, because it is the only one this page answers.
Naming the other two is honest and it is the hand-off to the mini-site. Never promise what a
later section doesn't keep.

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
> Most likely position: **around {anchor}** — rounded, deliberately, to the nearest $50,000.
>
> That's a range, not a figure, and the width of it is the honest part.

**Why this works.** They came for a number and we give it immediately. Three competing
automated estimates already sit above us on the same Google results page, so withholding ours
loses them for nothing.

The two lines nobody else writes are the **date it was worked out** and the **age of the
evidence**. Portal estimates carry neither, and *"Domain estimates and REA always lag (3-4
months)"* is a live complaint. Stating both costs us nothing and quietly raises a question
about every other number they've seen.

**The anchor is shipped** (`assemble._anchor`): the central figure is rounded to the nearest
$50,000 and spelled in millions — *"around $1.65 million"*. A deliberately approximate number
reads as a considered position; an exact one reads as false precision. It also keeps us clear of
Rule 5, which bars a single valuation figure as a **headline** — the range is the headline, the
anchor sits under it.

**No confidence label.** Ours don't discriminate — `high` 56.0% versus `medium` 57.5%.

**While it builds**, reuse `PendingPlaceholder` — a designed wait state with a status eyebrow
and an ETA line, rather than a spinner. Its mini-site copy reads *"Consultant review in
progress · Live within 3 business days"*; ours is seconds, not days, so the ETA line changes
but the pattern holds. A named, dated wait reads as work happening; an unnamed one reads as a
slow page.

**When the build can't run — state why, precisely, and treat it as a credential.** Taken from
the mini-site's suppression rule: *"saying why a number is missing is worth more than the
number. Every competitor draws the line anyway. **Refusing to is a credential.**"*

> We can't put a range on this home. We hold its land size and its last sale, but not the
> internal floor area — and floor area is one of the two figures every adjustment depends on.
> A range built without it would look the same as one built with it, which is the problem.

Then jump to §4, which needs nothing about this home at all. **This is the majority state on
off-market addresses. Written this way it is the strongest proof on the page that we don't
invent numbers.**

> ⚠ **Unresolved: does this trigger s 215?** Property Occupations Act 2014 (Qld) s 215 — when a
> seller asks an agent for a likely sale price, the agent must supply a CMA of at least three
> sales inside six months, similar standard, within 5 km, or a written explanation. **Fields is
> a licensed agency and §1 gives a homeowner a likely sale price.** `StatutoryCMA.tsx` already
> implements the compliant form, including the *"as at / valid until"* stamp the six-month
> window makes mandatory. **Resolve before §1 ships.**

> ### The ask
> **"Post the full report to this address"**
> One field, already filled with the address they're looking at. It goes in the mail.
>
> This is the highest-yield, lowest-friction ask on the page, and it is **self-verifying** —
> only the owner receives post at that address, so ownership is proved without asking anyone
> to prove anything. Postal reach is 176 against 29 for email.
>
> **What gets posted is already specified** (mini-site Session 1 print edition): A4 folded to
> A5, four sides, and — the load-bearing rule — **no CTA anywhere**. *"This reaches an owner who
> did not ask for it; the moment it mentions appraisals or selling services it reads as
> solicitation."* Every number carries its source and review date **on the same side**. No
> "tap", "scroll" or "click". The on-screen expansion becomes a printed side, because on paper
> there is nothing to open — the proof is simply printed.
>
> ⚠ **If the printed piece carries a QR that invites a reply, fix the token gap first.** Writes
> are gated on a `device_token` in localStorage; a reader arriving from print has none, so the
> answer is **silently discarded while they are shown a success state**. Until a signed
> `?plan_token=` is accepted server-side, no printed piece may present a question as answerable
> online.

---

# §2 — The working

> ## The sales behind that range, and what we changed about each one
>
> *[funnel, animating on open: {catchment_total} sales in the catchment → {in_band} in the
> price band → {ranked} ranked for similarity → **{n_comps} close enough to use**]*
>
> We looked at {n_assessed} and kept {n_comps}.
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
>
> ### That sale up the road isn't your comparison
>
> **{comp_address} — sold {comp_price}, {comp_distance}m away.**
>
> Looks like the same home. But against yours:
> • {delta_land}  • {delta_floor}  • {delta_build_year}
>
> **Same street, different home. The headline number was never the comparison.**
>
> ### Why it sits where it does in that range
>
> {n_matching} of the {n_active} homes on the market right now match this one on
> {scarcity_query}. {conditional_rarity_line}
>
> **What this means:** the range isn't wide because we're hedging. It's wide because homes
> with this combination don't come up often enough to pin it tighter.

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

**The funnel is taken from `RankedComparison`**, which animates the filtering *"so the seller
watches it happen."* Its standard is the right one: **honest theatre — every step is a
computation that genuinely ran.** Showing the filtering beats reporting its output.

**The obvious-comparable card is shipped and it is the sharpest device in the deck**
(`fact_bundle._obvious_comp`). It picks the **closest sale by distance** — the one a layperson
would seize on, and very likely the one already in the reader's head — then computes the
material differences arithmetically: land at ≥50 m², floor area at ≥20 m², build year at ≥8
years, plus any green-boundary difference. It pre-empts the objection they arrived with, and it
demonstrates the method on the single comparison they care most about. **It belongs here, ahead
of the general dispersion argument in §4.**

**Two-sided value drivers**, also shipped: *"What strengthens your position: ↑ land. Where a
buyer may focus: ↓ no pool. **Knowing both is how you hold your number.**"* Volunteering the
weakness is the trust move, and *"hold your number"* reframes it as something to prepare for
rather than a flaw.

**Scarcity is taken from `scarcity_features.py`**, and it belongs *here* rather than in a
section of its own. It is not a topic anyone searches for; it is the **explanation for where in
the range this home sits** — which is J1, the best-evidenced need we have. The engine counts
anchors only (land, floor, beds, pool), chosen relative to the suburb cohort, and deliberately
excludes sparse-coverage features *"so the ratio can never be inflated by missing data."*
`poi_rarity.py` supplies the conditional line — *"6 share your combination — only 2 are also
within a 5-minute walk of a park"* — the strongest narrowing device in either product.

> ⚠ In the mini-site, scarcity renders only behind a `ConsultantBadge` — a human approves it.
> That cannot scale to 26,297 pages. Either design the un-approved state or write the claim so
> it never needs approval.
> ⚠ Reuse `ValuationEvidence` (L1 evidence card / L2 comparable cards / L3 adjustment grid).
> It renders adjusted prices on `/your-home` today, so **verify whether the `adjusted_price`
> blocker is specific to the off-market path** before treating it as universal.

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
> **What this means:** two honest people, working from the same sales, can hand you numbers
> half a million dollars apart and both be following standard practice.
>
> The part that surprised us: a near-perfect comparable — one landing within 2% of the eventual
> sale price — was sitting in the available sales on **73.6%** of those homes. The worst choice
> available was more than 20% out on **73.4%**.
>
> **The right answer is nearly always there. Three sales just can't tell you which one it is.**
>
> **What this means:** the problem isn't a shortage of evidence. It's that three sales can't
> carry the weight of choosing between them — which is why we use eight and show you all of
> them.

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

# §5 — What it's done since you bought it

> ## Bought {last_sale_month} {last_sale_year} for ${last_sale_price}
>
> {years_held} years. Over that time the sales evidence in {suburb} has moved from
> ${suburb_index_then} to ${suburb_index_now} for homes of this type.
>
> Applied to what you paid, that puts this home somewhere in the **${range_low} – ${range_high}**
> we arrived at from the sales themselves — two different routes to a similar place.
>
> *[fan chart: purchase price → today's low/high, stepped by real quarterly index points]*
>
> The line isn't smoothed. Each step is an actual quarter, because a smooth curve would suggest
> we know more about the years in between than we do.

**Why this works.** *"Has it gone up since we bought it? By how much?"* is the first question
GPT lists after the number itself, and *"Did buying this home turn out to be a good decision?"*
is the emotional version of it. Independent support is moderate — **144 autocomplete searches**
in the sale-history category, `history` appearing **4×** in Google's own refinements, and our
own #3-above-Domain result on exactly this fact.

It also does something no other section does: **it corroborates the range by a second route.**
Comparable sales and an index applied to their purchase price are independent methods, and
showing them land in the same place is a stronger proof than either alone.

`CapitalGainChart.tsx` is already built — a fan chart from purchase price to today's range,
stepped by real quarterly index points, deliberately unsmoothed because curve-fitting *"would
imply false precision."* It is wired into `OffMarketDeck` (the ladder), not the live deck.
Data: `scraped_data.property_timeline`, **70.4% Robina / 83.2% Varsity Lakes / 90.8% Burleigh
Waters**.

> ⚠ **The privacy line runs through here.** Purchase price → today's range is public-record
> arithmetic and is fine. Their equity, loan balance or LVR is derived financial inference and
> is **banned** (C11) — the one clear privacy violation in the whole corpus was exactly this:
> *"what absolutely floored me was they had even estimated what we owe on it."*
> ⚠ Evidence here is **moderate, not strong** (`own_address_search_intent` §6.3). Instrument it.

> ### The ask
> None. This section's job is to reassure and corroborate, then hand to §6.

---

# §6 — If someone else has given you a number

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

# §7 — What's moving

> ## What's changed around this home
>
> {n_sales} homes like this one have sold in {suburb} in the last twelve months, at a median of
> ${suburb_median}. Twelve months earlier it was ${suburb_median_prior}.
>
> Homes here are taking a median of {dom} days to sell, against {dom_prior} a year ago.
>
> `● Live — competitor set re-checked nightly, last {last_checked}`
>
> **{n_matching} homes are competing with this one right now.**
>
> *[the closest active listings — photo, address, price, beds/baths, and for each one an
> explicit line: how it differs from this home]*
>
> **What this means:** these are the homes a buyer shopping in this band would be choosing
> between. Not a list of what's for sale nearby — a list of the substitutes.
>
> ### Who that combination suits
>
> **{buyer_portrait}** — e.g. *"A family who'd rather walk the kids to Robina State School than
> drive, and settle into Robina for good."*
>
> What a cheaper home can't give them: {drivers}.
>
> **Right now it's your home. To them, it's the one they've been waiting for.**
>
> ### What's moved in the last 30 days
>
> {change_log_items} — price changes, new listings, withdrawals, sales.
>
> {aperture_note}
>
> **Two true things that point in different directions.**
>
> Homes here are still selling quickly — a median of {dom} days. But far fewer are selling at
> all, and a year ago the median was {dom_prior} days.
>
> Both readings are true and they support opposite conclusions, which is why a single market
> headline can't settle anything about this home.
>
> {qoq_suppressed_reason}
>
> `Source: Fields analysis of {suburb} sold records · Last reviewed: {review_date}`

**Why this works.** The largest adjacent topic by a distance — roughly **670** persistence
across `gold coast property market forecast`, `forecast for next 5 years`, `crash prediction`
and `crash`.

It's also the *living* answer, and the reason to come back: a static number is worth
something, a number that explains its own movement is worth returning to. It speaks directly
to the loudest volatility complaint: *"In the last 3 months my house has dropped 40k increased
50k and dropped 40k, is this even possible."*

**The structure is taken from the mini-site**, which is stronger than announcing a refusal:
name the ambiguity, give both readings, let the reader draw the inference. Its rule —
*"the reader draws the inference. We never state it."*

> ⚠ **Rule 5 binds hardest here.** Report indicators. Conditional language only. Never a
> forecast, never "prices will fall", never advice.
> ⚠ **Never characterise the market** — cooling, softening, holding up, resilient are
> predictions in disguise. "Robust market" is banned outright.
> ⚠ **State suppressions on the card.** Where a quarter-on-quarter figure is too thin to carry,
> say so — `market_pulse.data_snapshot.qoq_suppressed_reason` already holds the reason.
> ⚠ **Staleness trap:** read `data_snapshot` only. `summary` and `narrative.pillars` go stale
> independently and a partial `$set` touches only what it names (CLAUDE.md Rule 6).

**On the buyer portrait, honestly.** The earlier audit found no independent *search* support for
"who would buy this home" as a topic, and that stands. But the shipped version is not a topic —
it is **the expression of the scarcity finding**: *this combination suits this person*. It is
a sentence about a behaviour, not a demographic, and it is generated from the same POI and
feature data as the rarity line (`_buyer_portrait`, `_persona_fit`). Will reports it resonating.
**Keep it as the human form of the scarcity result, never as a standalone section**, and
instrument it.

### ✅ Both halves of this are already live — corrected 2026-08-06

An earlier draft folded competition into two lines and scoped "what's changed" as a post-claim
feature, on the assumption both were unbuilt. **They are running nightly.**

`scripts/refresh_property_reports.py` → `refresh_comparables_for_doc()` is described in its own
docstring as **"config-free, EVERY report"**. Only the legacy market/article timeline is
hard-coded to one Merrimac demo slug. The generic path:

- Re-runs the competitor matcher against tonight's freshly-scraped listings — **"cheap, DB-only — no vision / Opus / scraping"**
- Produces `closest_active` and `closest_sold`
- **Diffs into a durable change log** — *"re-running the matcher is what makes the 'what changed' stream actually accumulate over time: it picks up price drops, method switches, withdrawals, and sales since the prior snapshot"*
- Carries an **aperture ring** and label, so it can state honestly when it had to widen the search to find any activity at all

Evidence it works: **all 70 `property_reports` carry activity items** (2–12 each), and
`price_change_events` holds **760** records.

**The important design consequence — the change log accrues per property whether or not anyone
ever claims.** So it splits cleanly:

| | Gated? |
|---|---|
| *"What's moved in the last 30 days"* | **No.** Free, ungated, works on first visit |
| *"What's changed **since you last looked**"* | **Yes** — genuinely requires knowing who they are |

That is a much better claim benefit than anything I had listed: it needs identity by
construction, it improves the longer they leave it, and it is already built
(`WhatChangedBanner` handles both the first-load digest and the return delta).

> ⚠ **The one real dependency.** The job iterates `system_monitor.property_reports` — 70 docs,
> created on `/analyse-your-home` submission. Running this for off-market addresses needs either
> report docs minted for those slugs, or `SlotResolver` pointed at off-market subjects directly.
> Because it is DB-only and cheap, unlike the 30–90s valuation, it could plausibly run nightly at
> scale **or** on demand fast enough to be invisible.

> ### The ask
> **"Tell me when this changes"** — an alert when the range moves, with the reason it moved.
> Requires somewhere to send it, so it's an honest reason to ask.

---

# §8 — What sits under it

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

# §9 — What you can do about any of it

> ## This is your home's page. You can change it.
>
> Everything here was built from public records and sales data. Some of it will be wrong — a
> renovation we don't know about, a room count that's out of date, a sale that shouldn't have
> been used.
>
> **[ See everything we hold on this home ]**
>
> Tell us what's wrong, and we'll fix it and rebuild the figure in front of you.
>
> **Nobody calls unless you ask.** No agent is paying to appear here, and nothing you do on
> this page becomes a lead.

**Why this works.** *"It's wrong about my house and there's no way to fix it"* is a dominant,
repeatedly evidenced grievance — *"Our home is stunning and has everything you could ever want,
yet it still shows as vacant land."* Every reviewer in that cluster reports that nobody replied.

Correction is also the one thing that genuinely **requires** knowing it's their home, which
makes claiming a functional necessity rather than a toll.

**Pair it with `DataRecordDrawer`** — the shipped slide-in listing *"every data point Fields
holds on a home, grouped and sourced… every group prints its source so each row stays
auditable."* You can only correct what you can see, so the drawer is the precondition for the
ask, not an extra. It is also the most complete answer we have to *"what do you actually know
about my house"*, and it renders straight off existing data.

And the last line is the sharpest contrast we own, defensible entirely from REA's own filings:
they report homeowner engagement to shareholders as *"valuable seller leads delivered to our
customers"*, with better-paying agents receiving **36% more** of them.

> ### The ask
> **"Correct something"** · **"Claim this page"**
> Claiming is offered *here*, at the end, after the page has already answered — never as the
> price of entry.

---

# The asks, collected

Ten sections, six asks. Each is a reason to talk, not a toll gate.

| § | The ask | What it gives us | Why they'd do it |
|---|---|---|---|
| 1 | Post the report to this address | **A verified owner + postal address** | Self-verifying, one field, 6× the reach of email |
| 2 | **Ask us to review this** | An opened conversation, in their words | Nobody else will fix a number about their home |
| 3 | Send me the method in full | A research-stage contact | Low commitment, high intent signal |
| 6 | Send this in writing | An address, and a live financial context | Genuinely useful to a broker |
| 7 | Tell me when this changes | A durable channel | The only page that explains its own movement |
| 8 | Send me the detail for this address | An address | 546 persistence says they want it |

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

## What is deliberately NOT a section

| Candidate | Evidence | Verdict |
|---|---|---|
| **Who would buy this home** (the `buyer` card) | Absent from autocomplete categories, stored persistence, Google refinements and the Reddit personas. The only support was deck dwell, which is position-confounded and survivorship-biased | **Cut, or ship as a labelled test.** A Fields-invented interest, not a user-expressed one |
| ~~**What's competing with it right now**~~ | ⚠ **Reassessed.** Live and generic in `refresh_comparables_for_doc` — `closest_active` with a per-home difference line. Independent *search* demand is still absent, but like scarcity this is an **explanation, not a searched topic** | **Promoted** — a full beat in §7 with the substitute framing from `MatchCards` |
| **"What's changed since you last looked"** | GPT: *"a major opportunity… the static answer is valuable; the living answer is defensible."* **Already accumulating** in the durable change log | **Split.** The 30-day movement is ungated and in §7; *"since you last looked"* is the claim benefit — it needs identity by construction |
| **The deeper journey** — what selling could make possible, where they'd go next, launch number, method, preparation, buyer competition, the Fields process | GPT's own list, and it maps one-to-one onto mini-site V2 sessions 1–7 | **Not this page.** *"The selling journey is not the initial product. It is the deeper path that becomes relevant once Fields has answered the address search better than anyone else."* |

---

## The chained questions, written out

Each section closes on the reader's next question, in their voice. Written here so they are
designed as a sequence rather than improvised per section.

| § | Closes on | Next section opens |
|---|---|---|
| 0 | *…So what is it worth?* | **What the sales around it say** |
| 1 | *…How did you get to that?* | **The sales behind that range** |
| 2 | *…But that place up the road sold for more?* | *(answered inside §2 — the obvious comparable)* |
| 2 | *…So how wrong could you be?* | **What this is, and what it isn't** |
| 3 | *…Then why do the other numbers disagree?* | **Why the other estimates say something different** |
| 4 | *…What has it actually done for me?* | **Bought {month} {year} for ${price}** |
| 5 | *…The bank said something lower — why?* | **Bank valuations, and why they're usually lower** |
| 6 | *…And what's happening around it now?* | **What's changed around this home** |
| 7 | *…Is there anything under it I should know?* | **Flood and overlays** |
| 8 | *…What if something here is wrong?* | **This is your home's page. You can change it.** |

⚠ **The forward cue must be honest.** A question the next section doesn't actually answer is
the fastest way to lose someone already sceptical — the mini-site review found four
bait-and-switch cues in the V2 sessions and treated every one as a defect.

---

## Taken from the shipped mini-site

| Concept | Where it lands | Source |
|---|---|---|
| **"The three questions"** opening, with the load-bearing *"You may be"* hedge | §0 | Session 1 `s1-open` |
| **Never make the reader admit intent** | Voice | Session 1, Rule 11 |
| **`SoWhat`** — no number ships without a translation line | Voice; applied in §4 | `SoWhat.tsx` |
| **`CitationStrip`** — no source, no block | Voice | `CitationStrip.tsx` |
| **Thesis / applied column split** (not free/locked) | Voice | `FearSection.tsx` |
| **Suppression as a credential** | §1 no-range fallback | Session 1 `s1-market` |
| **s 215 CMA obligation** | §1, unresolved | `StatutoryCMA.tsx` |
| **Honest-theatre funnel** — watch the filtering happen | §2 | `RankedComparison.tsx` |
| **Scarcity as range-explanation**, anchors-only, cohort-relative | §2 | `scarcity_features.py` |
| **Conditional rarity** — *"only 2 are also within a 5-minute walk of a park"* | §2 | `poi_rarity.py` |
| **`ValuationEvidence`** L1/L2/L3 | §2 | `ValuationEvidence.tsx` |
| **"Two true things that point in different directions"** | §7 | Session 1 `s1-market` |
| **`qoq_suppressed_reason`** stated on the card | §7 | `market_pulse.data_snapshot` |
| **`WhatChangedBanner`** | post-claim | `WhatChangedBanner.tsx` |
| **`DataRecordDrawer`** | §9 correction ask | `DataRecordDrawer.tsx` |
| **`PendingPlaceholder`** | §1 build wait | `PendingPlaceholder.tsx` |
| **Print spec — no CTA anywhere** | §1 postal ask | Session 1 print edition |

| **`MatchCards`** — each competitor carries an explicit *how it differs* line | §7 | `MatchCards.tsx` |
| **`LiveMarketStatus`** — "live, checked nightly" status bar | §7 | `LiveMarketStatus.tsx` |
| **Durable change log**, ungated 30-day / gated since-you-last-looked | §7 + claim | `refresh_comparables_for_doc()` |
| **Aperture-widening honesty line** | §7 | same |

**Considered and not taken, with reasons:**

| Component | Why not |
|---|---|
| `PositionAtAGlance` four-card opener | Two of its four questions are the buyer and competition angles, which have no independent *search* support. The shape is good; adopting it would import those two questions unexamined |
| `SeasonalityStrip` | Timing is a seller-journey question — the mini-site itself places it on the Process tab. Our reader is not necessarily selling. Belongs downstream |
| `ShareMoment` | A share card built around the strongest scarcity claim. **Off-register here:** 94% of these visitors view exactly one address — *"the signature of a private self-check rather than browsing."* Sharing assumes an audience this reader is deliberately avoiding |
| The seven-session seller journey | GPT is explicit it is the deeper path, not the initial product |
| `ch7-1-buyer-pool`, `ch7-4-portal-traffic`, `ch7-3-marketing-benefit` | Inverted, drifted and unsourced respectively |
| Confidence grades | Non-discriminating on our own measurement (C12) |

---

## Open

1. **Mobile.** Ten value-then-ask blocks stacked could read as nine paywalls. Prototype before committing.
1b. **Fallback order when there is no range.** §2 and §3 depend on a valuation; §4 does not.
   Where the build can't run, go §0 → §1 (plainly: not enough detail) → **§4** → §6. The page
   still has substance, but the arc inverts — say why numbers differ before we can show ours.
2. **Does §2 land as honest or as attack?** It criticises a method Fields is licensed to use.
3. **"Nobody calls unless you ask"** appears twice and is load-bearing both times. It cannot ship until it is an operational rule.
