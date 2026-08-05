# Claims Register — what we can say, what needs checking, what we must never say

**Status:** Internal. **Compiled:** 2026-08-06. **Companion to:** `01_USER_JOBS_AND_GAPS.md`, `02_COMPETITOR_CAPABILITY_MATRIX.md`

**Why this exists.** The dossier is an internal evidence base. Almost none of it can appear verbatim in public copy — some because it is inference dressed as fact, some because it is a market-wide claim we cannot verify, some because CLAUDE.md Rule 5 forbids it. This register is the gate between the two.

**The governing precedent.** Fields' own draft carried the line *"We have not found another agency or portal that publishes theirs [error rate]."* The session review told us to delete it: *"This is an open-ended market-wide claim and shifts the card from disclosure into self-promotion."* The replacement it proposed is the right register for everything here:

> *"We publish ours so you can judge the range with its limitations attached."*

**State our own position. Do not characterise the market.**

---

## Tier A — defensible now, with citation

Safe for public copy as written, provided the citation travels with it.

| # | Claim | Basis | Note |
|---|---|---|---|
| A1 | "We publish our method's historical error rate." | 11.1%, internal | State the figure, the sample and the limits. Never as a comparison |
| A2 | "We show which sales the estimate was built from — how many were reviewed and how many were used." | e.g. 41 reviewed, 8 retained | The count is safe; the per-comparable adjustment block is **not renderable yet** (C4) |
| A3 | "Nobody calls unless you ask." | — | ⚠ **Only if it is an operational rule.** If any path leads to outbound contact, this cannot be said at all |
| A4 | "Fields is not paid by agents. No one pays to rank here." | Our own business model | True and verifiable about us. Do **not** extend it into a claim about them |
| A5 | Comparable **ranges** and **gaps** — "comps say $1.75M–$1.98M", "$98K between asking and comparables" | CLAUDE.md Rule 5, updated 2026-07-27 | Ranges and differences permitted. A single figure as "what your home is worth" is not |
| A6 | Address-specific hard facts — "Last recorded sale $175,000, Oct 1990, held 35.7 yrs" | Our own data | This exact snippet ranked us **#3 above Domain**. Specific and checkable beats persuasive |
| A7 | Flood/hazard context with source and limitations named | `config/flood_context_burleigh_waters.md` | Rule 5: data, source, limitation. No advice, no reassurance |
| A8 | "Queensland law prohibits an agent from giving a price guide for a property going to auction." | *Property Occupations Act 2014* | ⚠ **Important honesty check:** in our own market, no-price is often a *legislative* artefact, not a portal choice. Never imply the portal is hiding it |

---

## Tier B — internal only until verified

True on current evidence, but sourced from forum testimony, snippets, or absence-of-evidence. **Each is a strong argument and a live libel/accuracy risk.**

| # | Claim | Why it's held | Unblocking test |
|---|---|---|---|
| B1 | Portals withdraw the estimate exactly when a home goes to market | Five forum posters, no first-hand reproduction. *"They all just happen to hide it. Every one of them."* | Check one address's estimate before and after listing |
| B2 | "Contact Agent" listings carry an embedded numeric price the portal chooses not to show | Consistent across five posters, matches a named broker's public statement — still third-party claims about another company's internals | Inspect source; confirm price-band filtering returns it |
| B3 | Paid placement is not labelled to consumers | Absence-of-evidence reached without loading the live page | Load a search results page |
| B4 | REA's owner dashboard gives less than ours | **We have never looked inside it** (gap G1) | The teardown |
| B5 | Agents inflate reported sold prices to move a local market | One named forum account | Would need pattern evidence in our own sold data |
| B6 | Portals suppress negative agent reviews | Multiple reviewer **allegations**, not established fact | Do not restate as fact under any circumstances |

---

## Tier C — never say

| # | Claim | Why |
|---|---|---|
| C1 | "More accurate than Domain / PropTrack / CoreLogic" | **No incumbent publishes an accuracy figure**, so the claim is unfalsifiable and unsafe. Standing memory rule (`valuation_backtest_claim_constraints`) |
| C2 | "No other portal publishes their error rate" / "no one in Australia does this" | Open-ended market-wide claim we cannot verify — the exact line the session review told us to cut. Also **false** for owner dashboards: REA has 3M tracked properties |
| C3 | "Portals hide information from you" | `structural_conflict` is explicit that this does **not** follow from the revenue model and no document supports it. The narrower, documented claims — ranking by payment, lead monetisation — are stronger *and* true |
| C4 | "They inflate estimates to trigger seller leads" | **No evidence found.** Do not assert or imply |
| C5 | "The ACCC has found…" | A s.155 notice was issued May 2025. **No finding, no proceedings, no enforcement action.** Never imply otherwise |
| C6 | "More than half of Australian listings hide the price" / "70% in Sydney East" | Traced to an uncited blog. **Do not use** |
| C7 | "$75 in 2009 → $5,000 today" listing-fee escalation | Repeated widely, always sourced to unnamed agents. Never a citable figure |
| C8 | A single valuation figure as what a home is worth, in a headline | CLAUDE.md Rule 5 |
| C9 | Any prediction, or any instruction to act — "now is a good time", "you should sell" | Rule 5. Liability |
| C10 | **"We found your home"** or any variant implying we located the owner | Zero positive reactions to unsolicited "we found your property" framing across 5,685 Reddit posts; three verbatim hostility artefacts. **Currently shipped on card 0 — this is a removal, not a prohibition** |
| C11 | Derived financial inference — equity held, mortgage outstanding, what they owe | The one clear privacy violation in the corpus: *"what absolutely floored me was they had even estimated what we owe on it."* Stay on the public-record side |
| C12 | Any confidence label — "high accuracy", "medium confidence" | **Labels are inverted in parts of the backtest.** A Domain band labelled "high accuracy" that excluded the actual sale price is the exact failure we are criticising. Calibrate first |
| C13 | Any per-address claim about who owns or occupies a home | Zero demand evidence (260 `who owns` autocompletes, all corporate; 0 of 4,349 Reddit posts) and a direct privacy trigger |
| C14 | Forbidden words: stunning · nestled · boasting · rare opportunity · robust market | Rule 5 |

---

## Pre-flight checklist — any public-facing surface

1. Every $ figure is a **range or a gap**, never a single "your home is worth" figure in a headline.
2. Every statistic carries **source, date and limitation**. No rounded transaction prices.
3. No claim about what competitors do or don't do, beyond what is in **Tier A**.
4. No confidence label until the backtest is calibrated (C12).
5. No advice, no prediction, no instruction to act.
6. If a $ claim appears in an ad, the landing page **visibly shows the valuation methodology and confidence disclaimer** (Rule 5, 2026-07-27).
7. Any Tier B claim used must have been moved to Tier A first — not "probably fine."
8. Suburbs capitalised; `$1,250,000` format.
9. **The privacy promise is checked against what the system actually does**, not against what the copy says.

---

## Change log

| Date | Change |
|---|---|
| 2026-08-06 | Created from the eleven research files in `../Research/`. C10 recorded against currently-shipped copy |
