# Brain 1 / 2 / 3 — reliability fixes handoff

**Written:** 2026-08-01, after using `brain1_deep.py` for a real decision (printed market-report length + format for The Fields Quarterly).
**For:** a Claude Code session picking this up cold.
**Status of the brains:** all three are LIVE and in nightly use. Nothing here is theoretical — every defect below was observed in a real run or confirmed by reading the code.

**Read first:** `10_Market_Report/research/brain1_deep_recall_review.md` — a prior three-pass review of a *recall* failure (canonical units dropped despite passing the judge). This document is about *fidelity* failures and is complementary, not a replacement. Several root causes there (RC5 entity drop, non-deterministic facets) are still unfixed and are restated here with code-level confirmation.

---

## 0. How to reproduce the run this came from

```bash
cd /home/fields/Fields_Orchestrator
source /home/fields/venv/bin/activate
set -a && source .env && set +a
python3 scripts/samantha/brain1_deep.py "How did agents use printed market reports to \
establish themselves and win listings? Contrast a LARGE substantial report against a SHORT \
eight-page quarterly review — what did each achieve, how were they distributed, what length \
did practitioners actually recommend, and what evidence is there about whether recipients \
read them?" --facets 10
```

Runtime ~23 min. Judged 2,542 candidate units, carried 302 relevant. **The answer was genuinely
useful** — it surfaced a specific practitioner account (an eight-page quarterly booklet, 3,264-contact
database, four mailings a year each paired with a phone call) that no amount of reasoning would have
produced. Do not "fix" this tool into uselessness: the retrieval works. The problem is that **its
citations cannot be trusted as published**, which for a business whose entire positioning is
methodology transparency is a hard blocker on using output in public work.

---

## 1. CONFIRMED DEFECTS — Brain 1

### 1.1 Quote misattribution — 5 of 49 quotes (89.8% fidelity) · HIGH
Observed verbatim in the run:

```
[quote-verify] 49 quotes | 44 verified | 5 MISATTRIBUTED | 0 NOT_FOUND | 89.8% fidelity
   ✗ MISATTR cited u0202        -> actually u0001 (cov 1.0): "substantial = authority"
   ✗ MISATTR cited u0449        -> actually u0645 (cov 1.0): "We have four phone calls a year..."
   ✗ MISATTR cited u0202,u0449  -> actually u0509 (cov 1.0): "a document,"
   ✗ MISATTR cited u0202,u0449  -> actually u0016 (cov 1.0): "beautiful glossy booklet"
   ✗ MISATTR cited u0202,u2267  -> actually u0061 (cov 1.0): "14-day taper"
```

Coverage 1.0 means the quoted text **does exist in the corpus** — the synthesis is not
hallucinating text, it is attaching real quotes to the wrong unit ids. Note the pattern: the wrong
ids are nearly always `u0202` and `u0449`, i.e. it is **anchoring on a few salient ids and
attributing everything nearby to them**. That is a strong hint the map-reduce shards lose the
id↔quote binding (see 1.3).

`brain1_deep.py:284-297` detects this and prints `⚠ NOT publication-ready`. **Detection is good and
must be preserved.** What is missing is any *repair* step.

**Fix direction:** the verifier already knows the correct id (`-> actually uXXXX`). Add a
rewrite pass that substitutes the verified id back into the synthesis before output, then re-verify.
Only fall back to the warning if a quote genuinely cannot be located.

### 1.2 Invented unit id · HIGH
```
[verify] 28 cited | 27 in shortlist ✓ | 0 exist-not-in-shortlist | 1 INVENTED
[verify] ⚠ INVENTED ids: ['u5850349667']
```
One fabricated id in 28 citations. Note its shape — 10 digits where real ids are 4 (`u0202`). A
cheap format guard (`^u\d{4}$`) would catch this class at generation time, not just after.

`brain1_deep.py:274-280`.

### 1.3 Map-reduce sharding degrades citation fidelity · HIGH — likely ROOT CAUSE of 1.1
```
[synth] overflow (86,466 tok) -> map-reduce over 6 shards
```
`brain1_deep.py:203-210`, `shard_n = 60`. `MAX_SINGLE_UNITS = 150` (`:42`) is documented as a
*fidelity ceiling* — above it, "single-context synthesis stops citing real unit ids and
confabulates (empirically ~1000 units -> 0 real citations)".

So the author already knew fidelity breaks with scale and added map-reduce to mitigate it. The
observed 89.8% suggests **the mitigation itself leaks** — a Haiku map step extracting
"citation-preserving findings" per shard, then an Opus reduce, gives two chances to detach a quote
from its id. Worth testing: does a run whose `relevant` count stays under 150 (single-context)
produce 100% quote fidelity? If yes, the shard boundary is the culprit and the map step needs a
stricter contract (e.g. emit `{id, quote}` pairs as structured JSON, never prose).

### 1.4 Relevance judge fails open on a JSON parse error · MEDIUM
```
[judge] FAIL-OPEN (kept all 18): Extra data: line 7 column 1 (char 47)
```
`brain1_deep.py:113-118`:
```python
    ids = set(json.loads(re.search(r"\[.*\]", out, re.S).group(0)))
    return [u for u in chunk if u["id"] in ids]
except Exception as e:
    sys.stderr.write(f"[judge] FAIL-OPEN (kept all {len(chunk)}): {e}\n")
    return list(chunk)  # fail-open: never silently drop relevant data
```
Fail-open is the **right** default (dropping relevant data is worse than keeping noise) — do not
change that policy. Two things are wrong with the implementation:

1. **No retry.** A transient parse failure permanently costs that batch its filtering.
2. **The regex is the actual bug.** `re.search(r"\[.*\]", out, re.S)` is greedy across the whole
   response; if Haiku emits prose after the array, or two arrays, the captured span is not valid
   JSON — which is exactly "Extra data: line 7 column 1". The same fragile pattern is used for
   facets at `:64`.

**Fix:** a shared `parse_json_array(text)` helper that tries, in order — direct `json.loads`,
fenced-block extraction, then a *balanced-bracket* scan (not a greedy regex) — with one retry at
temperature 0 before failing open. Apply at `:64` and `:114`.

### 1.5 Facet generation is non-deterministic · MEDIUM
`decompose()` (`:57-69`) calls Haiku with no seed, so the same question yields different facets run
to run — meaning **different candidate pools and therefore different answers to the same question**.
Already identified in `brain1_deep_recall_review.md`. For a tool used to make business decisions
this is a reproducibility problem: we cannot re-run a query to check an answer.

**Fix:** cache facets per (question-hash, n) so a repeat query reuses them, with `--refresh-facets`
to override. Cheaper and more effective than trying to make the model deterministic.

### 1.6 Named-entity retrieval is broken · MEDIUM (long-standing, still unfixed)
Confirmed at code level this session:

| file | `entities` occurrences |
|---|---|
| `brain1_annotate.py` | 1 |
| `brain1_normalize.py` | 0 |
| `brain1_graph.py` | 0 |
| `brain1_deep.py` | 0 |
| `brain1_query.py` | 0 |
| `brain_search.py` | 0 |

Entities are extracted at annotate time and then **never carried into the graph package**.
`brain1_graph.py:119-129` builds each unit from `src` + `quotes` + fields, with no entity field. So
a name-anchored query ("what did Alex Jordan say about market reports") can only match where the
name happens to leak into `src` or a quote — 8 units out of ~33 that actually concern him.

**Practical impact this session:** I had to deliberately phrase the query around *concepts*
("printed market report", "eight-page quarterly review") rather than names. It worked, but only
because I knew about the bug. Anyone asking the obvious question gets a bad answer and no warning.

**Fix:** carry `entities` through `brain1_graph.py` into the unit doc and include it in the
searchable text. Prior review estimates name-anchored recall 17→~33 units.

### 1.7 Three of ten sources returned zero relevant units · LOW (investigate before fixing)
```
KB:financial   : 0 relevant /  96 judged
KB:general     : 0 relevant / 310 judged
KB:project     : 0 relevant /  14 judged
```
420 units judged for zero yield. May be entirely correct for this question. Worth a one-off check
against a question those libraries *should* answer, to distinguish "correctly irrelevant" from
"systematically unreachable".

### 1.8 Single-source dominance is not surfaced to the caller · LOW
`RealEstate_Gym` supplied **203 of 302** relevant units (67%). The synthesis presents its
conclusions without noting that two-thirds of the evidence comes from one training organisation.
For our editorial standards that is a citation-integrity issue: it reads as industry consensus when
it is one school's doctrine.

**Fix:** print the source-concentration ratio in the output header, and have the synthesis prompt
require a caveat when any single source exceeds ~50% of carried units.

---

## 2. CROSS-BRAIN AUDIT — the important finding

**The entire verification apparatus exists only in `brain1_deep.py`.** Measured this session:

| file | judge | verify | quote-verify |
|---|---|---|---|
| `samantha/brain1_deep.py` | ✅ | ✅ | ✅ |
| `samantha/brain1_query.py` | ❌ | ❌ | ❌ |
| `samantha/brain3_annotate.py` | ❌ | ❌ | ❌ |
| `brain2/ad_query.py` | ❌ | ❌ | ❌ |
| `brain2/*` (15 files) | ❌ | ❌ | ❌ |

So:

- **Brain 1 shallow (`brain1_query.py`)** — the path most likely to be used casually — has no
  citation verification at all. It can misattribute exactly as the deep path does, silently.
- **Brain 2 (ads/PostHog)** — no verification anywhere. Its outputs feed ad decisions and the
  RL reward ledger. A misattributed figure here becomes a spend decision.
- **Brain 3 (internal knowledge)** — same.

**The 89.8% fidelity number is only known for Brain 1 because Brain 1 is the only one that measures
it.** Brains 2 and 3 are not verified-good; they are *unmeasured*. That is the single most important
thing in this document.

**Fix direction:** extract the verifier from `brain1_deep.py:264-299` into a shared
`scripts/samantha/brain_verify.py` exposing `verify_citations(answer, shortlist)` and
`verify_quotes(answer, units)`, then wire it into every brain's query path. Same warning contract,
same `⚠ NOT publication-ready` line.

---

## 3. SUGGESTED ORDER

1. **Shared `parse_json_array()`** (1.4) — smallest change, removes a whole failure class, unblocks clean measurement of everything else.
2. **Test the shard-boundary hypothesis** (1.3) — run a query whose relevant count lands under 150 and check quote fidelity. This determines whether 1.1 is a sharding bug or a prompt bug; do not attempt 1.1 before knowing.
3. **Quote-repair pass** (1.1) + **id format guard** (1.2).
4. **Extract the shared verifier and wire into Brains 2 and 3** (§2) — highest *business* risk, since those outputs drive spend.
5. **Facet caching** (1.5) — makes every later change measurable by making runs reproducible.
6. **Entities through to the graph** (1.6).
7. **Source-concentration caveat** (1.8), then investigate the zero-yield libraries (1.7).

---

## 4. DO NOT BREAK

- **Fail-open on judge errors.** Dropping relevant data is worse than carrying noise. Fix the parse, keep the policy.
- **The `⚠ NOT publication-ready` warning.** It is the reason we know any of this. If a repair pass is added, it must still warn when repair fails.
- **`MAX_SINGLE_UNITS = 150`.** It encodes a real empirical finding (~1000 units → 0 real citations). Do not raise it to avoid sharding without re-measuring fidelity.
- **The judge's bias-to-include prompt** (`:105-111`). A prior recall failure came from over-filtering; the current prompt deliberately keeps rare one-off mentions.

## 5. DEFINITION OF DONE

- A repeat of the §0 query returns **100% quote fidelity, 0 invented ids**, and the same facets on re-run.
- `brain1_query.py`, `brain2/ad_query.py` and the Brain 3 path all emit a fidelity line.
- A name-anchored query ("what did Alex Jordan say about market reports") returns his material.
- Every change logged to `logs/fix-history/` per CLAUDE.md rule 1 and pushed per rule 2.
- If any new scheduled process is added, it self-reports per rule 7.

## 6. WHY THIS MATTERS COMMERCIALLY

Fields' entire market position is that we publish our method and are right because of it. Brain 1's
retrieval is genuinely good and found material that changed a real format decision today. But a
quote we cannot attribute correctly is a quote we cannot print — and an unverified Brain 2 figure
is an ad-spend decision made on an unchecked number. The fix is not more intelligence; it is making
the existing intelligence auditable.
