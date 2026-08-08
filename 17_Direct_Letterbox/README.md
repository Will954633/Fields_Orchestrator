# 17_Direct_Letterbox

Everything about posting physical mail to homeowners: the strategy, the evidence behind it, and the
one asset that already builds.

**Status, plainly: nothing has ever been posted.** 399+ printable PDFs exist on disk. Zero have
reached a letterbox. One homeowner has ever received a Fields seller product, on 2026-04-10, in a
format since retired.

---

## Start here

| Read | For |
|---|---|
| ⭐ **[01_Strategy/00-STRATEGY-OPTIONS.md](01_Strategy/00-STRATEGY-OPTIONS.md)** | **The decision document.** Five options, costed, with kill criteria and a recommendation |
| [01_Strategy/01-WHAT-THE-EVIDENCE-SUPPORTS.md](01_Strategy/01-WHAT-THE-EVIDENCE-SUPPORTS.md) | What survived verification, and the eleven numbers that did not |
| [01_Strategy/02-AS-BUILT-REALITY.md](01_Strategy/02-AS-BUILT-REALITY.md) | What actually exists in code and in the database, as opposed to in markdown |
| [01_Strategy/03-PSYCHOLOGICAL-ARCHITECTURE.md](01_Strategy/03-PSYCHOLOGICAL-ARCHITECTURE.md) | How the pieces are designed to be read, and where the line is |
| ⚠ [01_Strategy/04-LEGAL-AND-ETHICAL-GATES.md](01_Strategy/04-LEGAL-AND-ETHICAL-GATES.md) | **Research, not advice.** What must clear a lawyer before anything is sent |

---

## The three findings that matter most

**1. The engagement trigger does not fire.** The rule that classifies an owner as a lead — 6 cards,
45 seconds, Telegram alert — is real code that nothing calls. DeckV3 became the default on
2026-08-04 and never wired it up. `offmarket_intent_signals` has no document after that date. What
creates a lead today is a nightly PostHog query for *the page having loaded*, with no depth
condition at all.

**2. "Post weekly" is not supported.** Mail stays live in-home 7.6 days and response peaks near three
weeks, a sender's own mailings cannibalise each other at ~63%, and the only measured tolerance
figure is one piece per month per sender. **Fortnightly-to-monthly is the defensible band.** The
weekly idea traces to one uncited coaching claim about 25-cent *unaddressed* drops aimed at
*recognition*, contradicted on outcomes by another operator in the same programme.

**3. The lever is specificity, not frequency.** Generic mail moves behaviour ~0.5pp; mail carrying
the recipient's own record moves it +4.9pp. An RCT on 300,000 insurance customers found printing
*last year's premium* lifted action 3.2pp while simplification and reminders did nothing. **Content
specificity beats frequency by roughly 16×** — and per-address specificity is the entire Fields
asset.

---

## Layout

```
00_SCOPING.md                  the original card + magnet concept (its response-rate section
                               is CORRECTED in place — the 4.4% figure was not real)
Houses_Surrounding_A_Just_Listed.md   Will's event-ripple idea. Became Option 3, and is the
                               most interesting thing in the folder

01_Strategy/                   the decision documents (above)

02_Research/
  01_Brain1/                   coaching-corpus deep queries (direct mail, cadence, farming,
                               copy, sequencing, giving away the analysis)
  02_Web/                      W1 evidence base · W2 frequency/decay · W3 format ·
                               W4 novel + backlash + AU law · W5 farming reality check
  03_YouTube/                  eXp Realty + BLAC SALT: pipeline, extracted passages, findings
  04_Psychology/               (reserved)

03_Pipeline/                   (reserved — the send layer, when it exists)

Owner_Subject_Article/         ✅ THE ASSET THAT WORKS. Per-address printed piece, 6 copy
                               variants, numeric + editorial gates, live PropRadar guard
```

---

## The asset that works

[`Owner_Subject_Article/`](Owner_Subject_Article/) generates a ~1,100-word printed piece about one
off-market home, addressed to that home: recent nearby sales each **adjusted to the recipient's own
property**, set against the national headlines, with no CTA and no single valuation figure.

It survives the research unusually well. Almost every constraint the evidence and the law impose —
range not figure, appraisal not valuation, public facts not inferences, close every gap in the same
piece, publish the confidence — was already enforced in `guardrails.py` and `factbook.verify()` for
editorial reasons, before any of this was known.

Three things it still needs before print: **a PDF path** (HTML only today), **aerial compression**
(~1.6 MB each), and the **s 215 recency gate** (≥3 comparables sold within 6 months within 5 km —
the current build accepts 8-month-old sales).

---

## What does not exist

No postal vendor integration (`postgrid|clicksend|lob|auspost|mailhouse` returns zero hits in any
`.py`, `.mjs` or `.ts`). No send queue — `print_post_queue` holds **0 documents**. No sequence state
machine, mail history, suppression list, scheduler or per-address asset code. No holdout mechanism.
No inbound instrument: **lifetime hard-evidenced inbound contacts from any channel: 1.**

The QR measurement rail, however, **is** built and correct — `/a/<asset_code>` → `print_assets` →
`asset_scans` with PostHog and Telegram. Asset codes are arbitrary strings, so per-address codes
need no infrastructure change. It currently holds 1 asset and 2 scans, one of which is our own VM.
