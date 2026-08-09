# ⚠ Verification status — read before quoting any of this

**Last updated 2026-08-10.**

## What has been checked

✅ **Independent provenance sweep against `package.json` (9,145 units).** Performed during the
synthesis. Findings:

- **Fabricated unit ids: 0.** Every cited id resolves to a real unit.
- **Self-citation loop (prior Brain 1 briefs re-ingested from Drive): 0 detected.** The three
  `external:drive/` units cited are genuine academic PDFs, not our own prior output.
- **⛔ Nine citations resolve to "Before You List" — Fields' own seller book**, ingested from
  Drive and handed back as though it were practitioner evidence. Two were additionally attributed
  to **Ryan Serhant, who did not write them** (`k02039`, `k02077`). Affected ids: `k02039`,
  `k02070`, `k02072`, `k02076`, `k02077`, `k02081`, `k02053`, `k02054`, `k02047`, `k02040`;
  `k01957` is of uncertain authorship and treated the same way. **None of these may be used as
  corroboration for a Fields decision.**
- **⛔ Four citation errors from a systematic id-truncation bug**, repaired: the map-reduce step
  drops the leading `9`/`0` from `u9####` and `u0###` ids, silently converting a US/BLAC SALT
  citation into an unrelated RealEstate_Gym one. `u1781`→`u901781`, `u1685`→`u901685`,
  `u2202`→`u2186`, plus zero-padding fixes in brief 04. **A truncated id usually still resolves to
  a real-but-wrong unit, so an existence check passes it silently.**

## `brain1_verify.py` — SUPERSEDED BELOW: the gate itself was broken, and is now fixed

> ⚠ **Everything in this section is superseded by the "FINAL STATUS" section at the bottom of this
> file.** It is kept because the reasoning about meta-document artefacts remains correct and
> because the both-directions truncation warning was found here first.

The first run against the briefs returned only a header. A run was completed against
`00-SYNTHESIS.md` on 2026-08-10:

```
42 quoted spans | 24 attributable | 15 verified | 2 MISATTRIBUTED | 7 NOT_FOUND | 18 unverifiable
fidelity 62.5% (of attributable quotes)
```

**62.5% against the ~96.8% this tool has historically reported.** This read as a fail on the publish
gate. **It was not — the tool was broken.** See FINAL STATUS.

⚠ **But read the failures before believing the number.** The synthesis is a *meta-document* — a
document about citations — so the verifier repeatedly parsed its own prose and correction tables as
though they were quotes. These are artefacts, not defects:

- `NOT_FOUND: u0119 — "* (**u0119**, Agent School, *The Real Estate Growth System*). Same uni"` —
  a markdown fragment.
- `NOT_FOUND: k02077 — " claim with **k02077**, which is **Fields' own "` — the synthesis's own
  warning text.
- `MISATTRIBUTED: cited k02039 … — "Ryan Serhant's material"` — the synthesis's own correction
  **table** being re-flagged as an error.

**Genuinely unresolved, and these are the ones that matter:**

| Verdict | Unit | Quote |
|---|---|---|
| NOT_FOUND | `u2075` | "It's not me saying it, it's coming from the buyers" |
| NOT_FOUND | `u1749` | "When you ask questions, you learn when you make statements, they judge" |
| NOT_FOUND | `u900953` | "On the third question, you usually get to their genuine reason" |
| NOT_FOUND | `u901225` | "in the absence of value, people will select you on fee" |
| ✅ NOT_FOUND | `u2174` | "expired listings over 60-day filter" — **confirms the synthesis's own finding** that this is an entity label, not a quote |
| MISATTRIBUTED | `u901685`, `u900339` | "500 call connections per week" — actually in `u1685`, `u1821`, `u2438` |

⚠ **The last row is the interesting one.** The synthesis corrected `u1685` → `u901685` for the
anniversary-card quote, and that correction was right. But it appears to have been applied **too
broadly** — the "500 call connections" quote really is in the *un*-truncated `u1685`. **The fix for
the truncation bug introduced a new error of the opposite kind.** Both directions have to be checked
per quote; neither id form can be trusted as a blanket rule.

**Briefs 01–04 were not individually verified** — only the synthesis was.

> ### ⛔ Operating rule that follows
> **No verbatim quote from this folder may be used in any asset, internal or public, without
> re-locating it against `package.json` first.** Nothing in the strategy documents depends on a
> quote: every Brain 1 input that survived into `00-STRATEGY.md` and `04_Content/` is carried as
> **paraphrase with a grade**, not as quotation.

## Standing rules for this material

1. **Never attribute a quote to a named practitioner in anything public.** Speaker names are
   machine-extracted entities and are frequently garbled — the same person appears as
   "Josh Tessolin", "Josh Tessla", "Josh Tesslan".
2. **Every bare statistic in the corpus is grade E** — no method, no n, no source, and each was
   told to an audience being sold coaching. Hypotheses only. Never publishable, never a
   business-case input.
3. **The corpus contains no conversion rate for this channel**, and says so.

---

# FINAL STATUS — 2026-08-10, after fixing the gate

## The gate was broken. It is fixed.

`brain1_verify.py` loaded **4 annotation files; the graph is built from 6.** Missing were
`/home/fields/brain1_yt/annotations.jsonl` (2,292 units — the entire **eXp Realty (US)** and
**BLAC SALT (AU)** corpus, i.e. every `u9#####` id) and `/home/fields/brain_drive/annotations_b1.jsonl`.
A quote whose unit is not in the index cannot be located anywhere, so it was reported `NOT_FOUND` —
the verifier's verdict for **fabricated**.

**41 false fabrications in brief 01 alone.** All sampled ones re-located at coverage **1.00** in
exactly the cited unit. Fixed in `scripts/samantha/brain1_verify.py` (index 9,525 → 12,662 units);
logged as `[BRAIN1-VERIFY-CORPUS-GAP]` in `logs/fix-history/2026-08-10.md`.

## All four briefs, re-verified under the fixed gate

| Brief | Spans | Verified | MISATTRIB | NOT_FOUND | Fidelity |
|---|---|---|---|---|---|
| 01 winning expired/withdrawn | 129 | 123 | 1 | 4 | **96.1%** |
| 02 seller psychology | 129 | 114 | 4 | 8 | **90.5%** |
| 03 long nurture | 142 | 95 | 41 | 4 | **67.9%** |
| 04 why it didn't sell | 115 | 102 | 12 | 0 | **89.5%** |

## ⛔ Brief 03 is the one to distrust

Its 41 misattributions are almost entirely the **id-truncation bug** (`u9####` → `u####`), so its
citations systematically point at the wrong **library**. The nurture-cadence material it presents as
Australian coaching doctrine is substantially **US brokerage-webinar** content. **Its findings
survive; its attributions do not.** Treat every `u####` id in brief 03 as unverified until
re-located. The true scale of the bug is **38 in brief 03, 12 in brief 04, 4 in brief 02** — not the
four found by hand.

## The synthesis's own citations

All **73** distinctive quotes in `00-SYNTHESIS.md` were checked per-quote against the fixed index.
**68 verified at coverage ≥0.9;** five were wrong and were corrected in place:
`u2075`→`u902075`, `u1749`→`u901749`, `u0380`→`u900380`, `u0382`→`u900382`, and — in the *opposite*
direction — `u901685`→`u1685` for the "500 call connections per week" figure.

**That last one is the standing warning:** `u1685` and `u901685` are both real, different units.
The anniversary-card quote is in `u901685`; the 500-calls quote is in `u1685`. **Correct per quote,
never by blanket rule, and check both directions.**

## What still stands from the original assessment

The circular-evidence finding (nine citations resolving to Fields' own "Before You List" seller
book, two of them misattributed to Ryan Serhant) is **unaffected by the gate fix** — `brain1_verify.py`
cannot detect that class at all, because the text genuinely is in the corpus. So are all three
standing rules above. The operating rule below also stands, and is now cheap to satisfy: with the
index fixed, re-locating a quote takes seconds.
