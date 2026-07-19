# Brain 3 (KB) — Graph Extension Scope

_2026-07-18. Next step after Brain 1 completion. Applies the proven Brain-1 pipeline (annotate → graph → normalize → completeness-first deep query → quote-verify) to the internal Knowledge Base. YouTube is a separate later step. **Supersedes** the embeddings/vector-store design in `brain3_scoping_and_development.md` PART 2 §2.3–2.4 — we use the Max-only graph+judge architecture, no embeddings, no vector DB._

## What the KB actually is (grounded)
- **1,647 docs / 7,469 chunks / ~5.9M tokens** at `/home/fields/knowledge-base/<category>/*.json`.
- **Already chunked** — a KB `chunk` maps 1:1 to a Brain-1 "unit". No segmentation/batching step needed (the coaching corpus's hardest prep step is free here).
- Chunk schema: `{chunk_id, content, document_type, tags, description, token_count, key_initiatives, success_metrics, ...}` — `content` is the raw text; the rest is a weak pre-classification we can seed from.
- **Categories = the per-source dimension** (counts): general 773, meeting_notes 426, operational 96, strategy 79, code 78, marketing 71, project 41, book 18, internal_projects 13, financial 6, conversations 1.
- `search-kb.py` is lexical keyword scoring — same family as `brain1_query`, so retrieval reuses cleanly.

## What transfers UNCHANGED (reuse, ~0 new logic)
- `brain1_graph.py` — deterministic graph builder (units → typed edges + cooccur + concept_index).
- `brain1_normalize.py` — Sonnet concept normalization (densifies the graph).
- `brain1_deep.py` — per-source retrieve + Haiku relevance judge + map-reduce + id-verify. Already generalises: pass KB **categories** as the source list → no crowd-out (meeting_notes 426 can't bury financial 6).
- `brain1_verify.py` — quote-level verify + `--fix-citations`. Works on any (quote, id) brief.

## What CHANGES (the actual build)
1. **`kb_ingest.py` (new, small):** read KB json → emit Brain-1 unit records into `/home/fields/brain3_build/`. `unit_id` = stable hash of category+chunk_id; `src = {source:"KB", category, filename, doc_type, chunk_id, date}`. ~half day.
2. **`brain3_annotate.py` (clone of `brain1_annotate.py`):** Haiku on Max, durable resumable cron. **Schema tweaks:** keep `concepts / claims / relationships / answers_questions / key_quotes`; **DROP** coaching-only `channels` (PRIMARY/USED/AVOIDED); **ADD** internal facets `decision / initiative / metric / status` (seed from existing `key_initiatives`/`success_metrics`). Apply the ThreadPool concurrency we built (6 workers) so it's faster than the coaching overnight grind. Cost ≈ 6–8M Haiku tokens. Runtime: overnight (~8–12h).
3. **Graph build:** run `brain1_graph.py` pointed at KB units → `brain3_build/package.json`. Add a `--package` flag to `brain1_deep.py` so it can target Brain 1, Brain 3, or (later) both.
4. **Normalize (optional, after validation):** `brain1_normalize.py` on the KB concept vocab → densify. Second overnight run; defer until annotation is validated.

## NEW constraints the coaching corpus did NOT have (must design in)
- **⚠ CONFIDENTIALITY FIREWALL (top risk):** KB holds financial, meeting_notes, internal strategy. Brain 3 units + quotes are **INTERNAL ONLY** — must never leak into public-facing content (editorial rules). Every unit carries `source:"KB"`; any public-facing generator MUST exclude it. Brain 1 (external coaching) can inform public content; Brain 3 cannot.
- **Temporality / staleness:** internal docs get superseded (a 2024 strategy may be dead). Carry `processed_date` through; retrieval must surface recency and never present an old internal decision as current. Coaching content was timeless; KB is not.
- **Mixed signal density:** code/financial chunks are low-value for "what have we learned/decided" intelligence. Completeness says annotate all + let the judge filter, but to control cost, **phase it.**

## Phased plan + effort
- **Phase A (recommended first):** high-signal categories — strategy, meeting_notes, marketing, book, general, project, internal_projects (~1,395 docs). Ingest → annotate (overnight) → graph → validate with a few deep queries + quote-verify.
- **Phase B:** operational, code, financial, conversations (~180 docs) — add once A is proven.
- **Phase C:** normalize (densify) + add `--package both` for cross-brain queries (Coaching × KB).
- **Total new code:** `kb_ingest.py` + `brain3_annotate.py` (clone) + a `--package` flag. ~2–3 build days + 1–2 overnight runs. ~80% reuse.

## The payoff (why this next, not YouTube)
Brain 3 unlocks the cross-brain synthesis that makes Samantha genuinely smart: **Brain 1 (what coaches say works) × Brain 3 (what we've decided/learned/know) × Brain 2 (what we've measured).** E.g. "coaches say expired-listing outreach is the #1 first-listing source — what have WE already decided/tried about that, and does our data support it?" YouTube is additive external content and can slot in as another Brain-1-style source later without blocking this.

## Open decisions for Will
1. Phase A scope OK, or annotate all 7,469 chunks in one pass?
2. Confirm the firewall rule: Brain 3 never feeds public content — internal briefs / Samantha reasoning only.
3. Same `brain3_build/` sibling-dir + symlink pattern as `brain1_build/`?
