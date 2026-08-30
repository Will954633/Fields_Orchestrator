# ARTICLES CYCLE — 2026-08-30 10:00 AEST

**Briefing tier: `stale` (17d, last updated 2026-08-13) → NARROWED.**
Permitted: bug fixes restoring stated intent. Not permitted: new initiatives.
Everything shipped this cycle is a bug fix against copy that already breached
rules we had already agreed. Nothing new was started.

**Open recommendations at start: 0. At end: 0.** Nothing this cycle needed Will's
decision — it needed the work doing, and the work was inside the envelope.

---

## 1. What changed since last cycle

`fix_digest.py --days 8` returned 44 entries touching this domain. The three that
mattered:

- **`[SEO-QUERY-DIMENSION-BLINDNESS]`** — the measurement I have been reasoning
  from was a 9% sample. This invalidates my own 2026-08-16 conclusion. Detail in §2.
- **`[EDITORIAL-FALSE-CONFIDENCE-RANGE]`** — seo added a *detector* for false
  confidence language and correctly said the durable fix was at generation. This
  cycle wrote that fix.
- **`[EDITORIAL-ABBREVIATED-CURRENCY-IN-TITLES]`** — seo expanded 60 fields and
  asked me to fix the generator. The generator did not need fixing (§4).

Also checked and **not** re-raised: `[REC-ARTICLES-002/003-ALREADY-SHIPPED]`
confirm the 15 how-it-sold drafts and the generator feedback loop are already
live. Both are on my ledger as shipped and awaiting 2026-09-20 grading. Nothing
due for grading today.

---

## 2. The numbers, with denominators — and a premise I have to retire

My last note to seo said *"organic across all 90 published articles is 0 sessions
and 137 impressions / 1 click — there is no organic CTR worth quoting."* **That was
wrong, and it was wrong because Search Console silently drops rows when you request
the `query` dimension.** Corrected, re-running `articles_signal.py` against the
fixed `dims` field:

| | value |
|---|---|
| Articles | 102 |
| Impressions (90d) | **1,703** |
| Clicks (90d) | **27** |
| CTR | **1.6%** |
| Avg position (`/articles/`) | **9.4** |
| Sessions | 23 |
| **Conversions** | **0** |

That is 11× the impressions and 20× the clicks I had. **Articles are not
organically dead.** I retired that question on bad data and I am un-retiring it.

But the corrected picture is not good news — it relocates the problem. From
`reward_ledger.py` (n=951 users, 1,125 sessions, 13 conversions, base rate 1.4%):

| milestone | reached | conv | P(reward) | lift |
|---|---|---|---|---|
| `submitted_address` | 13 | 13 | 0.726 | **53×** ★reward |
| `searched_address` | 15 | 13 | 0.625 | **46×** |
| `return_visit` | 82 | 7 | 0.081 | 5.9× |
| `viewed_property` | 317 | 6 | 0.018 | 1.3× |
| `reached_site` | 951 | 13 | 0.014 | 1.0 |

**Mechanism I think is at work:** the funnel has exactly one gate, and it is the
address field. Everything that converts passes through it; 13 of 13. Articles
delivered 23 sessions and 27 clicks in 90 days and routed **none** of them to it.
So the article problem was never CTR — at 1.6% and position 9.4 the top of the
funnel is working about as well as a 102-article library should. The failure is
**onward routing**, which is precisely the "educate, then offer" McKinsey pattern
§1 of my brief asks for and which the current template does not implement.

**⚠ Denominators, honestly:** 13 conversions total. `searched_address` is 15
people. These lifts are directionally strong and mechanically plausible — one
gate, everyone passes through it — but 13 events cannot carry a precise effect
size, and I am not going to dress them as if they can. This is the same n that
produced the old system's discredited "26× address-search lever". I am reading it
as *where the gate is*, not *how big the lever is*.

**Topic/suburb detail** (all 0 conversions, so this ranks reach only): `how-it-sold`
42 articles / 575 impr is the largest block; `major-projects` is the efficiency
outlier at 5 articles / 380 impr / 11 sessions. By suburb, Robina 450 impr from 27
articles, Burleigh Waters 222 from 20. 17 articles are flat zero.

---

## 3. What I did autonomously

### (a) False confidence on live pages — root cause was our own prompt

seo reported the compliance check catching **2** live breaches. Walking the whole
`ai_analysis` document rather than a subset of fields, the real number is **20
published properties, 39 strings** — in `insights[].key_points`, `faqs[].answer`,
`cta_valuation.hook`, `next_steps[]` and `verdict`. Including one literal
**"90% confidence range"** (10 Glen Eagles Drive), the exact phrase CLAUDE.md
names as forbidden. seo's detector is a net with holes in it; I have told them
which fields it misses.

**The root cause was not the model. It was the prompt, in two places:**

1. Rule 9's own exemplar read *"...eight verified comparables, **medium
   confidence**, compiled from public sale records"* — modelling a confidence tier
   inside the very sentence that states the range.
2. PART 7B "CONFIDENCE TIERS" listed **"Fields valuation range"** under **HIGH
   CONFIDENCE**. The model read "the range is high confidence" and published
   exactly that.

The band is a flat ±12% of the reconciled estimate. It contains the actual sale
price 61% of the time; a true 90% band needs ±26.4%. So these were false
statements of fact on live public copy.

**Fixed in three layers:** exemplar corrected; new **rule 9a** banning
confidence/interval/band/% language on the band, with the measured figures and
WRONG/CORRECT pairs taken from the real breaches; PART 7B annotated that the tiers
are writer guidance and never published labels. Then — because prompt text alone
has already failed to hold the number-format rule — `_strip_false_confidence()`
applied deterministically in `_normalize_money_formats()` at save time, the same
belt-and-braces shape as `_expand_abbreviated_money()`. Tested against all 12 real
live phrasings before it touched anything.

**Backfilled** the 19 live published docs (39 strings). Re-scan: **0 remaining**,
and `editorial_compliance_check.py` no longer fires `false_confidence_range`.
Backup: `logs/backups/false_confidence_published_20260830.json`.

### (b) meta_title dropping the street number

29 of 237 generated `meta_title`s did not lead with the street number; **6
published**. "114 Florabella Drive" shipped as "Florabella Dr Sales Hit
$1,170,000". "4/44 Frascott Avenue" shipped as **"44 Frascott Ave" — a different
property**, which is worse than a weak match. Exact-address queries are the
strongest organic position we hold, and the number is the most discriminating
token in the query.

Added `_ensure_meta_title_street_number()` at both assignment sites. It repairs
only the safe case (title opens with the street name) and **warns rather than
guessing** otherwise, so it can never mangle a title it does not understand.
Repaired 3 published titles including seo's 2 Eagle Avenue; left 3 hook-led titles
that never contained the street name for regeneration.

### (c) Handed off a Rule 7b silent zero I found on the way

The still-open OpenAI directive named a check worth running. Running it found a
**different and larger** problem: pipeline **step 105 processes zero properties
every night across all six suburbs, prints "✅ completed successfully", and exits
0** — because `*.blob.core.windows.net` does not resolve from this VM. Its own log
line is `processed=0 skipped=105 errors=0`. Six-plus consecutive nights.

DNS is specific, not general: the blob host and `blob.core.windows.net` both fail
to resolve while `google.com` and `api.openai.com` resolve fine — which points at
an egress policy rather than an Azure outage. Step 106 is unaffected (it falls
back to Claude); 108 and 117 route via OpenRouter. 105 is the only one on the
broken path, and it feeds the vision inputs my editorial writes from.

I did **not** touch it — monitoring code and network config are outside my
authority and it is not my domain's process. Sent to `all` with the full repro,
the six-night history, and the assertion it needs
(`skipped==total and download_failures>0 -> raise`). Also re-verified the OpenAI
account: **still HTTP 429, zero credits, 7 days open.** Needs Will; costs money.

---

## 4. Where I corrected another domain

seo asked me to fix the generator so it stops emitting abbreviated currency
(`$1.4M`). **It does not.** `_expand_abbreviated_money()` has run over the whole
`ai_analysis` document at save time since 2026-07-24 `[EDITORIAL-NUMBER-FORMAT]`.
Checked every `ai_analysis` meta field in the three suburbs by generation date:

- abbreviated fields with `generated_at` **before** 2026-07-24: **149**
- abbreviated fields with `generated_at` **after** 2026-07-24: **0**

Every one of the 46 properties seo expanded was generated between 2026-03-28 and
2026-07-22. Those 60 were legacy stock, not a live source leak. The remaining 149
are all on non-published docs (archived/rejected/suppressed/draft) — none live —
so I left them.

I also flagged back to seo a breach I found but deliberately did **not** fix: the
same passages state our valuation to the dollar (`$1,726,668`, `$2,053,132`),
breaching rule 9 on live pages. Unlike a descriptive phrase, you cannot strip a
number without changing what the sentence claims. That needs regeneration, and at
`stale` tier it is not mine to call alone.

---

## 5. What I proposed — nothing, and why

Zero recommendations, from a starting position of zero open. Per contract §4 a
quiet ledger is a success, and per §7 the cap is on Will's attention, not my
effort — so being free to propose was not a reason to.

Everything I found this cycle was either (a) a bug defeating intent we had already
agreed, which the brief says to fix rather than ask about, or (b) another domain's
to action, which is what the directive channel is for. Nothing required a change
of direction, money, or an irreversible choice.

The two things that *will* need Will are already queued elsewhere and would be
duplicates if I raised them: the OpenAI credit top-up (costs money, 7 days open,
now re-evidenced) and the 20 published pages that state a valuation to the dollar.
The second is the stronger candidate for next cycle's recommendation — but it
wants a fresh briefing behind it, not a stale one.

**Nothing graded** — nothing was due. REC-articles-002/003 grade 2026-09-20,
REC-articles-005 on 2026-09-03.

---

## 6. The open question I most want answered next week

**Where does an article send a reader who is ready to act?**

The corrected data says articles reach people — 1,703 impressions, 27 clicks,
position 9.4 — and convert none of them, while 13 of 13 conversions passed through
an address field no article links to. That is a routing defect, not a content
defect, and it is exactly the "educate, then offer" pattern §1 of my brief already
authorises.

I did not build it this cycle because adding a new onward-routing module to the
article template is a **new initiative**, and at `stale` tier I may not start one.
**That is the single thing a refreshed briefing would unblock**, and it is worth
more than any topic I could pick.

**Briefing is 17 days old against a weekly cadence.** Refreshing it is the highest-
value five minutes available to this domain right now.

---

## Files touched

- `config/property_editorial_prompt.md` — rule 9 exemplar, new rule 9a, PART 7B annotation
- `scripts/backend_enrichment/generate_property_ai_analysis.py` — `_strip_false_confidence()`, `_ensure_meta_title_street_number()`, wired into both save and assignment paths
- `logs/fix-history/2026-08-30.md` — `[EDITORIAL-FALSE-CONFIDENCE-BAND-AT-SOURCE]`, `[META-TITLE-STREET-NUMBER-DROPPED]`
- `logs/backups/false_confidence_published_20260830.json`, `logs/backups/meta_title_street_number_20260830.json`
- `system_monitor.rl_articles_actions` — 5 actions logged
