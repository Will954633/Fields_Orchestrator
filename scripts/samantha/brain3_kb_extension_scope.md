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

## ⚠⚠ AXIS CORRECTION (2026-07-18, after first classify run): firewall = CONFIDENTIALITY, not authorship
First pass classified on authorship (internal-we-wrote vs external-third-party). WRONG axis: it put
96 PRIVATE docs (bank statements — "Combined_Statement_Commonwealth Bank_William_Simpson", client
invoices — "Invoice - 0029_Alice Wright") into the "public-safe" pool, because an invoice is
third-party-authored → "external". Authorship and confidentiality are ORTHOGONAL: an invoice is
external-authored but PRIVATE; a book we publish is internal-authored but PUBLIC.
**The firewall MUST key off confidentiality: PUBLIC-SAFE (published books, academic papers, external
articles) vs PRIVATE (invoices, statements, bank, meeting notes, strategy, financials, PII).** Rules:
- **HARD-PRIVATE regex overrides the LLM** (never overridable into public, fail CLOSED to private):
  `invoice|statement|bank|tax|receipt|payslip|payment|acc[:_ ]|_FY\d|PII`. ~275 KB docs match.
- Classifier question becomes "is this PUBLIC-SAFE or PRIVATE?", default PRIVATE on any doubt.
- **CURATED ALLOWLIST, not ingest-everything:** the `general/` folder (773) is largely a document
  DUMP (bank statements, receipts, tax PDFs — high-sensitivity, zero knowledge value). Ingest only
  actual knowledge (books, papers, articles, business strategy/meeting notes); EXCLUDE the storage
  junk. This removes ~275 sensitive PDFs AND raises signal. Do NOT annotate until reclassified.

## (superseded framing) the KB is MIXED internal + external — provenance is PER-DOCUMENT, not per-category
The category names are misleading for provenance (confirmed by sampling `metadata.original_file`):
- **EXTERNAL published/research** (public-safe, same class as Brain 1 coaching): `book` (ABX Blueprint, Kindle scrapes), most of `financial` (academic papers — "Cooling auction fever", "Real Estate Economics 2008 textbook"), most of `marketing` (external articles — "OverpricingAdvertising", "3 Types of Prices"), and part of `strategy`/`general` (external research).
- **INTERNAL (firewalled):** `meeting_notes` (Business Partners docs, listing-presentation guides), `internal_projects`, `operational`, `code`, and the Fields-specific parts of `strategy`/`project` ("1% Agent Fee Brand.docx").
- NB: Fields' REAL financials live in the separate accounting system (samantha-accounting), NOT the KB `financial` folder.

**Therefore the firewall keys off a per-document PROVENANCE CLASS, not the folder.** Ingestion must classify every doc INTERNAL vs EXTERNAL (+ subtype: our-data / book / academic / external-article) and route:
- EXTERNAL → external-knowledge pool (public-safe; can inform public content, joins Brain-1-style retrieval).
- INTERNAL → Brain 3 (firewalled; Samantha reasoning + internal briefs only).
One pipeline, `provenance` tag drives both routing and the firewall.

## What CHANGES (the actual build)
1. **`kb_ingest.py` (new):** read KB json → emit unit records. `unit_id` = stable hash of category+chunk_id; `src = {source:"KB", provenance:"internal|external", subtype, category, filename, doc_type, chunk_id, date}`. **Includes a provenance-classification pass:** derive from `metadata.original_file` path signals (Kindle_Scraper/academic titles → external; .docx working docs/our brand → internal) where unambiguous, else a cheap Haiku per-doc label. ~1 day (was half — the classifier adds scope).
2. **`brain3_annotate.py` (clone of `brain1_annotate.py`):** Haiku on Max, durable resumable cron. **Schema tweaks:** keep `concepts / claims / relationships / answers_questions / key_quotes`; **DROP** coaching-only `channels` (PRIMARY/USED/AVOIDED); **ADD** internal facets `decision / initiative / metric / status` (seed from existing `key_initiatives`/`success_metrics`). Apply the ThreadPool concurrency we built (6 workers) so it's faster than the coaching overnight grind. Cost ≈ 6–8M Haiku tokens. Runtime: overnight (~8–12h).
3. **Graph build:** run `brain1_graph.py` pointed at KB units → `brain3_build/package.json`. Add a `--package` flag to `brain1_deep.py` so it can target Brain 1, Brain 3, or (later) both.
4. **Normalize (optional, after validation):** `brain1_normalize.py` on the KB concept vocab → densify. Second overnight run; defer until annotation is validated.

## NEW constraints the coaching corpus did NOT have (must design in)
- **⚠ CONFIDENTIALITY FIREWALL (top risk):** keys off the per-doc `provenance` class (above), NOT the folder. INTERNAL units + quotes are **internal-only** — any public-facing generator MUST exclude `provenance:"internal"`. EXTERNAL KB material (books, academic papers, articles) is public-safe like Brain 1. Getting the classification wrong in either direction is the top risk: firewalling valuable external research, or leaking internal strategy that sat in an innocuous folder.
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
1. **Provenance split first:** classify the whole KB internal vs external up front, then build EXTERNAL first (public-safe, immediately usable for content, low risk) and INTERNAL second (firewalled)? Recommended — it de-risks the firewall and gives value fastest.
2. Firewall rule confirmed: `provenance:"internal"` never feeds public content — Samantha reasoning / internal briefs only; external KB material is public-safe like Brain 1.
3. Where does EXTERNAL KB material live — folded into the Brain-1 external-knowledge pool (unified external retrieval) or its own package? (Lean: unified external, since it's the same class.)
4. Same `brain3_build/` sibling-dir + symlink pattern as `brain1_build/`?
