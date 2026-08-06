# 01 — UI brief (Will, 2026-08-06)

**This is the design spec of record.** It settles the two open questions:

1. **Page, not deck.** "A single vertically scrolling page with an editorial main path and layered
   evidence drawers." Normal vertical scrolling — no scroll-jacking, no forced horizontal swiping,
   no compulsory card carousel.
2. **Warm editorial register, not the V3 dark cinematic treatment.**

---

## The product concept

> A private, guided property investigation: a calm vertical journey that gives the homeowner the
> answer immediately, then progressively proves it through a sequence of increasingly surprising
> discoveries. Closer to opening a beautifully prepared private dossier than using a property portal.

**In one sentence:** *Answer first. Prove it gradually. Surprise them periodically. Ask almost nothing.*

REA and Domain own the commodity layer — attributes, estimate, sales history, local listings.
Fields does not win by adding dashboard modules. Fields wins by:

- showing **why particular sales count**
- showing **what changed** when each sale was adjusted
- exposing **uncertainty and historical error**
- revealing something **surprising about that exact home**
- connecting value to the homeowner's **possible next decision**
- doing all of it **without converting curiosity into an agent lead**

Supported by research on transparent automated systems: full technical detail up front distracts
and undermines the simple mental model people need first; simplified feedback then progressive
disclosure works better.

---

## Visual character

Quiet · premium · highly specific · editorial rather than corporate · evidence-led rather than
sales-led · slightly mysterious, never theatrical or ominous.

| use | avoid |
|---|---|
| warm off-white / very light stone background | bright portal-style blue cards |
| dark charcoal text (not pure black) | pure black |
| one Fields accent colour | gradients suggesting "AI magic" |
| generous space between sections | stock real-estate imagery |
| large serif / editorial display for **discoveries** | heavy icon use |
| clean sans-serif for **facts, sources, controls** | |
| real property imagery, aerial, maps | |

**Reference:** private report + high-end editorial feature + forensic evidence file.
**Not** real-estate software.

### Dimensions

**Desktop** — full-width canvas; primary reading column **720–800px**; evidence panels may widen to
**1,050–1,200px** for maps and comparables; generous margins; occasional full-width visual moments.

**Mobile** — one column; **20–24px** side padding; no horizontally scrolling tables; comparables
become stacked cards; deeper evidence opens in a bottom sheet or full-screen panel.

**Design mobile first.** People arriving from Google are standing in the kitchen or on the couch,
often discussing it with a partner — not sitting down to a desktop dashboard.

---

## The eight moments

The visible main path stays concise. All analytical depth remains available, one tap deeper.

### 1 — Recognition and privacy
Occupies most of the first mobile screen. Small logo, discreet "Private property report", date. No
nav clutter. Real property image, else aerial/elegant map — **never a generic house image**. Address,
facts, last recorded sale. Then the three private questions and the privacy promise: *"Nothing here
starts a selling process, and nobody calls unless you ask."* Forward cue.

**Do not ask** whether they own it, whether they're selling, for an email, for a mobile, or whether
they want an appraisal.

### 2 — The answer
The most important card. Visually decisive but not a portal estimate. Range, then the rounded centre,
then the basis (28 relevant sales, 8 strongest). *"The width is not hidden. It reflects what can — and
cannot — be concluded without seeing inside the home."*

⚠ **Do not hide the valuation behind a reveal.** They Googled the address principally to see the
value; withholding it reads as manipulative. **Curiosity should come from understanding the answer,
not from withholding it.**

Animation: range line draws, figures fade in, centre appears, basis appears. **No slot-machine
counting, no dramatic loading bar, no fake analysis animation** when the calculation already exists.

### 3 — The surprising nearby sale
**Before** the comparable table, because it is more emotionally intelligible. Split card: nearby sale
vs this home, then the movement `$2.325m sale ──→ ~$2.00m adjusted position`. *"Same area. Different
home. The headline price was never the whole comparison."* Control: **See exactly what changed**.

Does five jobs: challenges the neighbour-sale anchor, proves we're not averaging, introduces the
adjustment method, creates curiosity about the other sales, and gives them something memorable to
discuss with another person. This is where the visitor thinks *"this is different from Domain"* —
**you never need to say it.**

### 4 — The comparable evidence
Show **three** strongest by default, not all eight. Each a visual card with adjusted position and main
differences. Then "See all eight". Clean rejection funnel — 2,999 searched → 28 retained → 8 shown —
then "36 property characteristics were considered". ⚠ **Do not mix 2,999 sales with 7,066 nearby
homes**; that was the funnel that didn't narrow.

Desktop: side panel, list stays visible. Mobile: full-height bottom sheet, swipe down to close. The
user should never lose their place.

### 5 — What makes this home different
Large statement, three visual attributes, the scarcity count, then the restraint: *"That does not set
a price by itself. It reduces the number of close substitutes a buyer can choose from."* Interactive
map answering one question only: **how many homes genuinely combine these things?**

**Avoid** "rare opportunity", "highly sought after", "knowing this is how you hold your price",
scarcity colours, countdown language. The visual evidence does the persuasive work.

### 6 — How reliable is the answer?
Unusually honest and simple. *"Tested against [sample] homes that later sold, the centre of the
estimate was out by [rate]% on average. That is why the page shows a range rather than pretending the
evidence supports one exact number."* Small sample of historical outcomes. Then "See the full test".

**Do not put in the primary card:** model terminology, nine-times-out-of-ten claims, multiple
competing error figures, uncalibrated confidence labels, unexplained acronyms.

Target feeling: *"They have measured how wrong they can be."* Not *"I need to understand their ML pipeline."*

### 7 — What is changing now?
**A.** Four homes buyers might compare with this one. **B.** Recent-change timeline (gives a reason to
return). **C.** One clean contradiction card — two true things pointing in different directions — then
a compact evidence table, with the sample-size explanation expandable.

### 8 — Correct the home
Interactive and prominent. *"You know this home better than the records do."* Named gap, simple
choices, then: control saves, analysis rebuilds, **show exactly what changed** — *"Two comparisons
changed weight. The rounded range remains unchanged"* or *"The lower end moved from $1.75m to $1.78m."*

Proves the model is responsive, the homeowner's knowledge matters, the figure is not static, and
Fields will revise its own answer. Privacy: *"Corrections update this property record. They are not
treated as a request for contact. Nobody calls unless you ask."*

**Never use internal language:** fact bundle, coverage audit, data gaps, lead score.

### Closing — the next private question
Closes value, opens the next question. *"If you sold, where would you actually go?"* → **Explore where
you could go next** · *Still private · no contact details required*.

The CTA is **not** get an appraisal / contact Will / talk to an agent / start selling / unlock report.
It is the next question already alive in their mind.

---

## Navigation, motion, evidence

- **Normal vertical scrolling.** Skim, scroll back, share, browser-search, open links normally.
- **Question-shaped forward cues** at section ends; clicking scrolls smoothly, ordinary scrolling stays.
- **Subtle sticky header** after the hero — address + "Private report"; desktop may add small chapter
  shortcuts, not a nav bar.
- ⚠ **No completion percentage.** No "3 of 9", no "42% complete". *That turns curiosity into homework.*
- **Two content levels** — Level 1 the story, Level 2 the working. Drawer on desktop, bottom sheet on
  mobile. Not multiple accordions that all stay open and make the page enormous.

**Motion explains, never decorates.** Good: comparable glides to adjusted position; range line draws
once; map dots filter 21 → 8; correction visibly changes the analysis; new competitor pulses; source
drawer slides. **Avoid:** shaking, alarms, blackouts, sound, confetti, slot-machine numbers, long fake
loading, compulsory animation, page hijacking.

> The off-market "break glass" experience can be theatrical because it is a curiosity device. **This
> address page is where trust becomes valuable. Its intrigue should feel like discovery, not spectacle.**

**Sources:** plain-language source in the card → full citation in the drawer → linked methodology.
Use *Government record · Peer-reviewed research · Fields analysis · Industry estimate · Unverified
claim not used* — immediately understandable. Not unexplained [A]/[B]/[C] grades.

---

## Not a lead funnel

No persistent "Request appraisal" / "Speak with an agent" / "Get exact value" / "Unlock full report" /
"Claim this property". First human-contact CTA only after substantial value, preferably after later
sessions. A small footer "Have Fields review this with you" may exist but must not compete with the
next-question CTA.

**The page's first conversion is not a phone number. It is: the visitor continues investigating.**

---

## Build order

**Prototype A — the five-minute spine.** Recognition · range+centre · Dotterel comparison · three
strongest comparables · error rate · current alternatives · property correction · Session 2 transition.
Enough to test whether the central concept works.

**Prototype B — deeper evidence.** Full comparable table · scarcity map · complete methodology ·
three-sale experiment · market contradiction · overlays.

**Prototype C — living property experience.** Change timeline · return-visit differences · saved
corrections · refreshed competitors · "since your last visit" · continuation into Sessions 2–6.

## Metrics

Not bookings, initially. Measure: % reaching the value · % opening a comparable adjustment · %
reaching the error-rate card · % opening full evidence · % correcting an attribute · % continuing to
"where you'd go next" · return visits to the same address · time excluding idle · booking rate **only
after meaningful engagement**.

> The strongest signal: **they looked at the proof and then continued to the next private question.**
> That indicates the page has earned trust, not merely satisfied curiosity.

---

## Target feeling

> *"Google found my address. Fields understood my home. Then it showed me something about it I did
> not already know."*
