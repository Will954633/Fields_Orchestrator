# The psychological architecture of the sequence

**2026-08-08** · How the pieces are designed to be read, and where the line is.

Inputs: Will's curiosity-gap brief · `15_Off-Market/Home_Owner_Perspective/Gold-Coast-Homeowner-Selling-Mindset-2026-08-02.md`
· `Owner_Subject_Article/README.md` §10 (the six shipped variants and the TEASE rule) ·
`../02_Research/02_Web/W4-novel-breakthrough-and-the-line.md` (the personalisation-creepiness
literature) · CLAUDE.md Rule 5.

---

## 1. The reader we are actually writing to

Not a prospect. A specific person in a specific state, profiled in the mindset brief:

- Their home has **never been worth more on paper, and they have never been less sure the number is
  real.**
- They have watched confident forecasters publicly reverse **twice in eighteen months**. Confidence
  is now a negative signal to them.
- What freezes them is not the price level. It is that **the local signal is genuinely ambiguous** —
  homes sell fast (26–34 days) but far fewer sell (292 → 161 across the three suburbs). "Nobody is
  buying" and "nobody is selling" are both consistent with the data, and they cannot resolve it from
  outside.
- Their ranked fears: **#1 the re-entry trap** ("if I sell I can't get back in"), #2 mistiming,
  **#3 "the number in my head might not be real."**
- The job to be done: *"Help me find out what my home is actually worth, and what that would mean
  for my options — **without starting something I can't stop**."*
- 94% of our own off-market visitors view **exactly one address** — the signature of a private
  self-check, not browsing.

**The single most important consequence: reassurance is the wrong instrument.** It reads as a sales
position to someone braced for one. Naming the ambiguity is what earns permission.

---

## 2. Two hard boundaries that come before any technique

### 2.1 Personalise about the **property**, never about the **person**

The strongest study in the file measures this directly. Gerber & Green: mail showing a household
**its own record** moved behaviour **+4.9pp**; mail showing it **the neighbours' records** moved it
**+8.1pp** — *and generated documented opt-out backlash and complaints.* **The more powerful lever
is the one that damages the relationship.**

The mechanism is confirmed from the other direction by the personalisation-creepiness literature
(Kim, Barasz & John): the line is drawn by **provenance, not depth**. Inferred attributes score
**3.11/7** on acceptability against **4.08** for stated ones, and *disclosing an inference is worse
than saying nothing* (2.52 vs 2.96).

So:

| Print this | Never print this |
|---|---|
| "Sold March 2019 for $1,240,000" (public record) | "You've been here six years, so you're probably thinking about moving" (inference) |
| "Four houses sold within 700 m of your address since December" | "We noticed you looked at this page on Tuesday night" (surveillance) |
| "Your land is 477 sqm against 980 at 16 Anglesea Court" (public cadastre) | "Homes like yours are owned by downsizers" (segment inference) |

**Behavioural triggering is legitimate. Behavioural disclosure is not.** What we know from the
website may decide *whether* we write. It must never appear *in* what we write, in any form, however
softened. A piece that says "since you were looking at…" ends the relationship with the exact person
we most want.

### 2.2 Name the source, in the piece

Naming where a fact came from **erased the entire covert-collection penalty** in one experiment and
lifted clicks 50% in another. It is also an **APP 7.6 obligation** for addressed direct marketing —
see [`04-LEGAL-AND-ETHICAL-GATES.md`](04-LEGAL-AND-ETHICAL-GATES.md).

Two things follow. Disclosure **multiplies provenance in both directions** — naming a defensible
source helps, naming an indefensible one is worse than silence. And it is a design constraint, not a
footnote: if a fact's provenance cannot be printed comfortably on the page, that fact does not go in
the piece.

### 2.3 What Opower's complainants actually complained about

Not privacy. The top complaint across 8.6 million households was **"the comparisons are unfair or
inaccurate."** Accuracy is the reputational risk here, not intrusion — which is precisely what the
Owner-Subject Article's factbook gate already defends against, and precisely why the
`directional_only` suppression must never be quietly overridden to make a mail list bigger.

And the number to keep in view: **34% of recipients had weakly negative willingness to pay for the
report while only 0.08–3.3% ever opted out.** **A low opt-out rate is inertia, not consent.** Do not
read a quiet mailbox as a happy one — instrument annoyance separately.

---

## 3. The sequence problem, and how to resolve it honestly

Will's brief proposes a *psychological staircase* — each piece using a different mechanism,
progressive disclosure creating narrative momentum across the campaign. The instinct is right and
the mechanisms are real. But it collides head-on with a guardrail already shipped in
`guardrails.py`:

> **Every gap opened must be closed in the same piece, with real evidence.** In particular we never
> defer a gap to a later mailing: holding back information about someone's own home to make them
> wait is leverage over something that matters to them, and this reader has been burned by confident
> people twice in eighteen months. The **TEASE** rule class blocks "read on", "find out", "in our
> next letter", "you may be surprised".

That guardrail is correct and should not be relaxed. **The resolution is that a sequence can
progress in three different ways, and only one of them is withholding.**

| Mode | What carries the reader forward | Honest? |
|---|---|---|
| ❌ **Withholding** | We know something about their home and won't say it until piece 3 | **No.** Leverage over something that matters to them. Blocked by TEASE |
| ✅ **New subject** | Each piece answers a *different* complete question. The answer to one naturally raises the next | **Yes.** This is a magazine, not a cliffhanger |
| ✅ **New world** | The piece reports something that **has genuinely just happened** and was not knowable before | **Yes — and it is the strongest form available to us** |

### The third mode is the breakthrough, and it is uniquely ours

The only fully honest way to hold an open loop across a mail sequence is to **hitch it to a
real-world event that is genuinely unresolved — unresolved for us too.**

A house near them comes on the market. **Nobody knows what it will sell for. Including us.** Each
piece reports what actually happened since the last one. The loop stays open because *the world*
has not closed it, not because we are sitting on the answer. When the sale settles, the loop closes
with a real number, and the last piece can honestly say what that sale did to the evidence around
their own address.

This is the Zeigarnik effect obtained without manipulation, and it is available to Fields
specifically because we hold every sale event in four suburbs plus 53,313 historical events. It is
also the **Law of Because** from the coaching corpus made automatic: *"The reason I'm writing is
because 27 Smith Street has just come onto the market"* — a genuine, specific, dated reason to write
to an address that we did not manufacture.

It also happens to be the only structure that justifies a **fortnightly** cadence. Fortnightly
repetition of an argument is cannibalisation (~63%, van Diepen). Fortnightly reporting of a live,
moving, genuinely-new fact is not repetition at all.

---

## 4. The mechanisms, mapped to pieces — and which ones we must not use

### Use, in this order

**1. Self-reference — the load-bearing one.** Everything else is decoration on top of this. The
evidence is unambiguous: own-record mail outperforms generic by ~10×, and content specificity beats
frequency by ~16×. *"What buyers would compare your home with today"* not *"What Robina homes are
worth"*. Every piece must be unusable to the neighbour.

**2. Naming the ambiguity — the permission-earner.** This is the mindset brief's central finding and
it inverts normal marketing instinct. Lead with the thing they already can't resolve:

> *"Homes in Varsity Lakes sold in a median of 26 days last quarter. Thirty-two of them sold. Both
> of those numbers are true, and they point in different directions."*

No advice, no prediction, no urgency. It simply describes what they are already confused about,
which is the fastest way to be believed by someone braced for a pitch.

**3. Prediction error / pattern interruption.** Conventional agent mail is completely predictable —
headshot, "thinking of selling?", suburb median. Something unexpected re-engages attention:
*"We don't think your suburb median tells you much about your home."* The shipped `anomaly` variant
is our strongest version: *two sales near you point to very different numbers for your home* —
and the adjustment is the resolution, in the same piece.

**4. Publishing the confidence, not just the number.** From the mindset brief §8.2: *"Every
competitor draws the line anyway. Refusing to is a credential."* This aims directly at ranked fear
#3. It is also the only defensible position under Australian Consumer Law and the design envelope.

**5. Contrast.** Explain the method against the alternative rather than in isolation:
*automated estimate: suburb data → a number* versus *this: your home → the homes it competes with →
what each sale becomes once adjusted → a range and its width*. The reader concludes "different"
without us claiming "better" — which we could not substantiate anyway.

**6. Endowment / micro-commitment.** *"Your home's figures are on the back of this page"* beats
*"request a report"*. The QR should resolve to **their address**, already loaded — the reader never
types anything. And the first ask must be tiny: **"see"**, not "book". *Book an appraisal* is
psychologically enormous to someone whose stated job-to-be-done ends with *"without starting
something I can't stop."*

**7. Social proof — but only the real, behavioural kind.** *"Trusted by homeowners"* is worthless.
We can do better because we have the data: *"107 addresses in these three suburbs were looked up on
our site last week."* True, checkable, and it quietly says *you are not the only one privately
wondering* — which is the exact reassurance this reader will accept, because it is about behaviour
rather than about the market.

**8. Cognitive fluency.** One idea per section, short paragraphs, figures highlighted, the charts
doing the work. Make the *question* intriguing and the *explanation* effortless. Note the FCA RCT
caveat, though: simplification, bullet points and helpful leaflets produced **nothing** on their
own. Fluency is hygiene. It is not a lever.

### Do not use

**❌ Loss aversion, in the form proposed.** Will's example — *"The risk isn't simply pricing too
high. It's using up your strongest buyer interest before you know where the market really sits"* —
is a strong sentence and it is **advice**, prohibited by CLAUDE.md Rule 5. It tells the reader what
risk to weigh and implies what to do about it. It also contains a soft prediction. The legitimate
version states the fact and stops: *"Homes that sold in Robina last quarter took a median of 34 days.
The ones that did not sell are not in that figure."* The reader draws the inference. We never do.

**❌ Urgency in any form** — "while conditions last", "before rates move", "the window is open".
Prohibited, and specifically fatal with a reader who has just watched forecasters reverse.

**❌ Maximal personalisation stacked.** Personalisation follows an **inverted U** — one experiment
found high personalisation cut click-through **58% below moderate**. A photo of their house *plus*
their name *plus* their sale history *plus* their neighbours' prices is past the peak. **The aerial
with their cadastral boundary is our strongest single personalisation cue; it should be the only
maximal element on the page.**

**❌ Any single valuation figure.** Rule, envelope, and the Queensland *Valuers Registration Act*
all point the same way. Ranges with method attached.

---

## 5. The shape of a piece

Not *headline → benefits → testimonials → call us*. Instead:

```
personal relevance   → this is about my address, visibly, in the first second
    ↓
intriguing observation → something true I did not know, and did not expect
    ↓
the evidence          → named, dated, checkable sales I can look up myself
    ↓
the resolution        → what those sales become once adjusted to my home: a range, and its width
    ↓
the honest limits     → what this cannot tell me, stated before I have to ask
    ↓
one small action      → see it for my address. Not book, not call
```

The shipped Owner-Subject Article already implements this, and its ordering is deliberate in a way
worth preserving: **the named, dated sales appear *before* the biggest question in every variant.**
A gap opened before credibility is established reads as a tease. Evidence first, then the question
it raises.

The six shipped variants are the mechanism library:

| Variant | The gap it opens | Aimed at |
|---|---|---|
| `report` | none — states the finding, then evidences it | the baseline control |
| `anomaly` | *two sales near you point to very different numbers* | prediction error — our strongest |
| `anchor` | *you already have a number for this address — where did it come from?* | ranked fear #3 |
| `features` | *what are your land, condition and floor area actually worth?* | maximum self-relevance |
| `timing` | *half sold within N days; which half would yours be?* | leads with time-on-market |
| `contradiction` | *the national numbers and your street disagree* | naming the ambiguity |

**These are the A/B axis for the pilot, not decoration.** They are six compositions of identical
data passing identical gates, which makes them a clean creative test — and creative tests this
clean essentially do not exist in this category.

---

## 6. The three things most likely to sink this on tone

1. **Sounding like we watched them.** Covered in §2.1. This is the one that ends relationships
   rather than merely wasting postage.
2. **Sounding certain.** This reader's trust is won by our willingness to say "this quarter's median
   is too noisy to draw a line through". Every hedge we print is a credential, not a weakness. The
   suppression rules are the product.
3. **Being wrong about their house.** Opower's own complainants said *the comparisons are unfair or
   inaccurate* more than anything else. One wrong land size, one comparable that is obviously not
   comparable, one figure that contradicts our own website, and the piece proves the opposite of its
   thesis. `factbook.verify()` and `check_surface_consistency()` exist for exactly this, and no
   address should be mailed that they have not passed **on the day of lodgement**.
