# Brain 1 / 2 / 3 — reliability fixes handoff

**Originally written:** 2026-08-01, after using `brain1_deep.py` for a real decision (printed
market-report length + format for The Fields Quarterly).
**Rewritten:** 2026-08-01 19:55 AEST, after implementing the fixes. **The original version's
headline finding was wrong**, and it was wrong in an instructive way — see §1. The history is
preserved in `logs/fix-history/2026-08-01.md` under `[BRAIN-VERIFIER-COVERAGE-INVALID]`.
**For:** a Claude Code session picking this up cold.
**Status:** all three brains LIVE and in nightly use. Everything below was observed in a real run
or confirmed at code level.

**Read alongside:** `10_Market_Report/research/brain1_deep_recall_review.md` — a prior review of a
*recall* failure. Its RC5 (entity drop) is now FIXED (§3.6).

---

## 0. Reproduce the run this came from

```bash
cd /home/fields/Fields_Orchestrator
source /home/fields/venv/bin/activate
set -a && source .env && set +a
env -u CLAUDECODE python3 scripts/samantha/brain1_deep.py "How did agents use printed market \
reports to establish themselves and win listings? Contrast a LARGE substantial report against a \
SHORT eight-page quarterly review — what did each achieve, how were they distributed, what length \
did practitioners actually recommend, and what evidence is there about whether recipients read \
them?" --facets 10 --save-relevant /tmp/rel.json --out /tmp/answer.md
```

Runtime ~23 min. **Facets are now cached**, so a repeat run reuses the same decomposition and is
reproducible; add `--refresh-facets` to force new ones. `--save-relevant` writes the judged
evidence set so a later run can re-synthesise the *same* evidence via `--load-relevant` without
paying for retrieval again.

**The retrieval works and the answer was genuinely useful** — it surfaced a practitioner account
(an eight-page quarterly booklet, 3,264-contact database, four mailings a year each paired with a
phone call) that no amount of reasoning would have produced. Do not "fix" this tool into
uselessness.

---

## 1. THE MOST IMPORTANT THING: the fidelity metric was measuring noise

The original handoff led with:

> `49 quotes | 44 verified | 5 MISATTRIBUTED | 0 NOT_FOUND | 89.8% fidelity`
> …the wrong ids are nearly always `u0202` and `u0449`, i.e. it is **anchoring on a few salient
> ids** … a strong hint the map-reduce shards lose the id↔quote binding.

**That hypothesis was built on an artifact.** `brain1_verify.coverage()` summed *every*
`SequenceMatcher` matching block, including 1- and 2-character ones. Over a long unit blob those
scattered fragments reassemble almost any short needle. It was never a containment test:

| quoted span | normalized chars | units scoring ≥0.90 (of 9,525) |
|---|---|---|
| `"substantial = authority"` | 21 | **5,621** |
| `"beautiful glossy booklet"` | 24 | 2,480 |
| `"14-day taper"` | 12 | 2,549 |

So `-> actually u0001 (cov 1.0)` meant only "u0001 was hit first among thousands of spurious
matches". The `u0202`/`u0449` pattern was the verifier grabbing whatever id happened to sit on the
same line as a non-quote — not a synthesis behaviour at all.

It failed in **both** directions:
- **Inflated the headline** — quotes scored ≥0.85 against their cited unit by noise and were
  marked VERIFIED. True fidelity was *lower* than reported.
- **NOT_FOUND could never fire** — the true-source scan always found something at cov 1.0, so
  genuine fabrications were reported as misattributions. The run reported **0** fabrications;
  there were **4**.

Corrected measurement of the same brief:

| | reported before | actual |
|---|---|---|
| fidelity | 89.8% | **84.4%** (86.7% after repair) |
| misattributed | 5 | 3 → 2 after repair |
| fabricated (NOT_FOUND) | 0 | **4** |
| unverifiable coined labels | not a category | 9 |

**Generalisable lesson:** the verification apparatus is itself unverified code. Before trusting a
quality metric enough to design a fix around it, test the metric against a known case — here, "how
many units does this 21-character string match?" would have exposed it in one line.

---

## 2. WHAT WAS FIXED

### 2.1 `coverage()` is now a containment test · brain1_verify.py
Exact containment short-circuits to 1.0; fuzzy matching counts only blocks ≥8 chars. A real quote
with a transcription slip ("curl"→"cull") still scores ~1.0 (two long blocks either side); a short
needle assembled from noise scores 0.0. `"substantial = authority"` now matches **0** units;
`"beautiful glossy booklet"` matches exactly **1** (u0645 — the genuine source, which the old
verifier named as u0016).

### 2.2 A fourth verdict: UNVERIFIABLE
A quoted span under `MIN_ATTRIBUTABLE` (30 normalized chars) that appears verbatim nowhere is not
a citation — it is the synthesis's own coined label in quote marks (`"substantial = authority"`,
`"14-day taper"`). Reported separately with an advisory, and **excluded from the fidelity
denominator** so the metric no longer moves with the model's punctuation habits. They still warrant
a human look: quote marks beside a unit id imply verbatim to a reader.

True-source claims now name *every* holding unit and mark the verdict ambiguous when several
qualify, instead of confidently asserting one.

### 2.3 The repair pass — and why the obvious wiring was wrong
`fix_citations()` already existed but had never been wired in. **Wiring it in as-written made
things worse, not better**: it anchored to "the first id within 60 chars AFTER the quote",
`count=1`, over the whole document. On a comparison-table row with two quotes and two ids it
rewrote the wrong id (breaking a *correct* attribution); where the id preceded the quote it matched
nothing. Measured: it reported `corrected 4` while fidelity did not move at all (90.7% → 90.7%).

Rewritten to repair only **unambiguous** bindings — the line must carry exactly one quoted span and
exactly one flagged id, and exactly one unit must hold the quote — then **re-verify and roll back
if the verified count did not increase**. The repair count can no longer overstate what happened.
Ambiguous cases are listed for manual review. On the real brief: 1 repaired, 2 correctly refused.

### 2.4 Shared JSON parsing · brain_json.py (new)
Four sites each hand-rolled their own extractor and all four broke the same way:

| site | old approach |
|---|---|
| `brain1_deep.decompose` | `re.search(r"\[.*\]", out, re.S)` — greedy |
| `brain1_deep._judge_chunk` | same greedy regex |
| `brain3_annotate.extract_json_array` | first `[` .. last `]` slice |
| `brain2/ad_annotate.extract_json_object` | first `{` .. last `}` slice |

All span to the LAST bracket, so trailing prose or a second array makes the span invalid JSON.
This reproduces the exact production error `[judge] FAIL-OPEN (kept all 18): Extra data: line 7
column 1 (char 47)`. Replaced with: direct parse → fenced block → **balanced-bracket scan**
(string/escape aware, returns the first complete value, cannot over-capture), plus one retry with
an explicit format reminder. 11 regression cases — run `python3 scripts/samantha/brain_json.py`.

**Fail-open policy on the judge is unchanged** (§5).

### 2.5 Shared `audit()` + verification for the casual path
`brain1_verify.audit(answer, by_id, shortlist_ids=…, repair=…)` is now the single contract:
id-shape guard → id membership → quote verification → repair → `⚠ NOT publication-ready`.

Wired into `brain1_deep.py` (replacing its inline block; **repair now runs BEFORE output**, so the
printed and `--out` brief is the corrected one) and into `brain1_query.py`, **which previously had
no citation verification whatsoever** — the path most likely to be used casually could misattribute
silently. It now emits the same fidelity line.

The id-shape guard derives valid shapes from the loaded package and flags `u5850349667` (10 digits
where real ids have 4) as MALFORMED — a generation artefact, distinct from "a real-looking id not
in the package".

### 2.6 Named entities reach the graph
`entities` was extracted at annotate time (5,981 of 6,400 units have them) and then dropped by
`brain1_graph.py` — it never reached the package, the retrieval blob, or the LLM. Now carried into
the unit doc, into `score_units`' searchable blob (with a rank bonus, since an entity hit means the
unit is genuinely *about* that person), and into `compact()`.

Measured, top-45 units genuinely about the person:

| name | before | after |
|---|---|---|
| Tom Panos | 6 | **32** |
| Alex Jordan (top-150, of 25) | 9 | **17** |

Package rebuilt and promoted; backup at `/home/fields/brain1_build/package.json.bak-pre-entities`.
Structurally identical to the previous build (same units/concepts/edges/questions) apart from the
new field. `brain3_ops` picks the change up on its nightly rebuild (03:35).

### 2.7 Reproducibility + source concentration
- Facets cached per (package, n, question) under `~/.cache/brain1/facets`; `--refresh-facets` to
  override. The same question now yields the same candidate pool, so answers can be re-checked.
- Source concentration measured and printed. When one library exceeds 50% of carried evidence the
  synthesis prompt now *requires* the brief to say so. (`RealEstate_Gym` supplied 203/302 = 67% in
  the original run and the brief read as industry consensus.)

---

## 3. CORRECTING THE CROSS-BRAIN AUDIT

The original §2 claimed the verification apparatus exists only in `brain1_deep.py` and that
"Brain 2 feeds ad decisions … a misattributed figure there becomes a spend decision". **Half right.**
Checked at code level:

| path | LLM? | citations? | status |
|---|---|---|---|
| `samantha/brain1_deep.py` | yes | yes | verified (+ repair) |
| `samantha/brain1_query.py` | yes | yes | **verification added this session** |
| Brain 3 **query** | — | — | it *is* `brain1_deep.py --package /home/fields/brain3_ops/package.json` — already verified |
| `samantha/brain3_annotate.py` | yes | **no** | ingest, emits structured JSON per unit — nothing to citation-verify; JSON parsing hardened |
| `brain2/ad_query.py` | **no** | no | pure MongoDB aggregation — every number comes straight from the DB |
| `brain2/ad_annotate.py` | yes | no | structured creative labelling — JSON parsing hardened |
| `brain2/*` (13 others) | no | no | deterministic builders/reporters |

So:
- **Brain 3's query path was never unverified** — the original table listed `brain3_annotate.py`,
  which is the *ingest* path. Brain 3 queries run through `brain1_deep.py` and always had the full
  apparatus.
- **Brain 2 has no LLM query path at all.** `ad_query.py` is deterministic aggregation; there are
  no citations to misattribute. The "unverified Brain 2 figure becomes an ad-spend decision" risk
  as stated does not exist. (`organic_journey_build.py` matched an "anthropic" grep only via
  `detect_ai()`, which classifies AI *referrer traffic* — not an LLM call.)
- What Brain 2 and 3 genuinely shared with Brain 1 was the **fragile JSON extraction** (§2.4), now
  fixed in all four places.

**Brain 2's real unverified surface is different and still open:** `ad_annotate.py` emits a fixed
schema of enum-ish labels (`primary_emotional_lever`, `hook_type`, `cta_semantic.hardness`) that
`ad_query.py` then groups by. Nothing validates those values against an allowed set, so a drifting
label silently becomes its own row in every rollup. That is a **schema-validation** job, not a
citation-verification one — see §4.

---

## 4. WHAT IS STILL OPEN

1. **Brain 2 annotation schema validation.** Validate `ad_annotate.py` output against the enum sets
   its prompt specifies; reject/retry on drift. This is the genuine Brain 2 integrity gap.
2. **The 4 fabricated quotes.** Now that NOT_FOUND actually fires, the map-reduce path is producing
   quotes that exist in no unit. This is the real fidelity defect and it was invisible before.
   Worth attacking via the map step's contract (see 3).
3. **Map-reduce shard-boundary experiment — deliberately NOT run.** Its premise was the
   5-misattribution pattern, now known to be mostly measurement error. The genuine misattributions
   are a single confusion (u0449 vs u0645 — two units about the *same* quarterly booklet), too thin
   to design a sharding change on. The scaffolding is now in place to do it properly, holding
   evidence constant across both paths:
   ```bash
   # one retrieval, two synthesis paths, identical evidence
   brain1_deep.py "<q>" --save-relevant /tmp/rel.json --limit-relevant 140 --force-path single
   brain1_deep.py "<q>" --load-relevant /tmp/rel.json --limit-relevant 140 --force-path mapreduce
   ```
   Do this after a few runs under the corrected verifier, so the comparison is against a
   trustworthy baseline. If sharding is implicated, the fix is to make the Haiku map step emit
   `{id, quote}` pairs as structured JSON rather than prose.
4. **Zero-yield libraries.** `KB:financial` (0/96), `KB:general` (0/310), `KB:project` (0/14) —
   420 units judged for zero carry. May be correct for this question. Test with a question those
   libraries *should* answer, to separate "correctly irrelevant" from "systematically unreachable".
5. **`brain_search.py`** does lexical retrieval only (no synthesis, no citations) so it needs no
   verifier — but it does benefit from entities, automatically, via `score_units`.

---

## 5. DO NOT BREAK

- **Fail-open on judge errors.** Dropping relevant data is worse than carrying noise. The parse is
  fixed and a retry added; the *policy* is unchanged and must stay.
- **The `⚠ NOT publication-ready` warning.** It is the reason any of this is known. Repair must
  still warn when repair fails or is refused.
- **`MAX_SINGLE_UNITS = 150`.** Encodes a real empirical finding (~1000 units → 0 real citations).
  Do not raise it to avoid sharding without re-measuring fidelity. `--force-path` bypasses it for
  experiments only and warns loudly when it does.
- **The judge's bias-to-include prompt.** A prior recall failure came from over-filtering; it
  deliberately keeps rare one-off mentions.
- **Repair rollback.** If a "fix" does not raise the verified count, it is discarded. Never report
  a repair count that is not backed by a re-verification.
- **The completeness principle** (per-source candidate pools, no global top-N) — corpus size is an
  accident of what footage exists, not a relevance signal.

---

## 6. WHY THIS MATTERS COMMERCIALLY

Fields' position is that we publish our method and are right because of it. A quote we cannot
attribute correctly is a quote we cannot print. But the deeper lesson from this session is narrower
and sharper: **we were reporting a fidelity number that was not measuring fidelity**, and it was
reassuring in exactly the places it should have alarmed (0 fabrications, when there were 4). An
unverified verifier is worse than no verifier, because it launders confidence. The fix was not more
intelligence — it was making the existing intelligence auditable, and then auditing the auditor.
