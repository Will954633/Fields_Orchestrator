# Brain 3 — Unified Internal Knowledge System

**Scoping + Development document**
Author: Samantha (drafted for Will Simpson) · 2026-07-15 · Status: DRAFT for decision

---

## Executive summary

Fields already has most of a "Brain 3." A document knowledge base of **1,644 indexed files / ~7,000 chunks** lives at `/home/fields/knowledge-base/`, with an ingestion pipeline at `/home/fields/samantha-knowledge-base/` and a query entrypoint (`scripts/search-kb.py`) already wired into the voice/chat agent. The problem is not that the system doesn't exist — it's that (a) retrieval is **keyword/tag matching only, no semantic embeddings** (`query_index.py` literally says "For production, you'd use semantic/vector search"), (b) **nothing re-runs it** — there is no nightly ingest cron, so it has drifted stale since ~March 2026, (c) coverage is **partial** — it does not index the live MongoDB operational data, the fix-history logs, GitHub state, or several high-value corpora like the *Before You List* seller book, and (d) there is **no knowledge-graph overlay** linking entities (e.g. the book ↔ the strategies that reference it ↔ the door-knock delivery method). My recommendation: **do NOT build a greenfield Brain 3. Upgrade the existing KB into it** — add embeddings, connect the missing sources (Mongo, fix-logs, GitHub, book), schedule a nightly incremental refresh, and layer a lightweight LLM-extracted knowledge graph on top. This is an extension project, not a new platform.

---

# PART 1 — SCOPING DOCUMENT

## 1. Problem statement

The motivating incident: earlier today I had no idea what the *Before You List* book was, or that it's a physical hard-copy Will hand-delivers to prospect doors. That is a knowledge blind-spot, and it's instructive because the data *was on the VM the whole time* — `/home/fields/Fields_Orchestrator/08_Seller-Book/` contains `Fields_book.pdf`, a `README.md` describing it ("Before You List — A Data-Driven Guide for Southern Gold Coast Homeowners, ~23,000 words, v4"), print-ready PDFs, and the generation scripts. I couldn't use it because:

1. **It was never ingested.** The `08_Seller-Book/` tree isn't in `/home/fields/knowledge-base/`.
2. **Even if it were, keyword search wouldn't have connected the dots.** The fact that the book is *hand-delivered to doors* is a relationship between three entities (the book, the door-knock outreach method, the seller-acquisition strategy). Keyword scoring over chunks can't represent or traverse that.

So the problem has two layers: **coverage** (we don't index everything we have) and **connection** (we don't model how things relate). Brain 3, as Will framed it, is the fix for both: "a method of accessing everything we have," with "semantics and relationships and knowledge graph," refreshed automatically each day.

## 2. What we already have (inventory of internal data)

Concrete, verified on the VM today. This is the corpus Brain 3 must cover.

### 2.1 The existing knowledge base (the seed of Brain 3)
- **`/home/fields/knowledge-base/`** — 1,644 JSON index files, ~42 MB. Category breakdown (real counts):
  `general` 773, `meeting_notes` 426, `operational` 95, `strategy` 79, `code` 78, `marketing` 71, `internal_projects` 58, `project` 41, `book` 17, `financial` 6, `conversations` 1.
- **Ingestion pipeline:** `/home/fields/samantha-knowledge-base/` — `samantha_processor.py` (orchestrator), `local_fs_processor.py`, `gdrive_processor.py`, `conversation_processor.py`, `historical_ingest.py`, `chunking_system.py` (800-token chunks), `processor_lib.py`. Classification + per-chunk metadata via OpenAI `gpt-4o-mini`.
- **Retrieval:** `scripts/search-kb.py` (keyword+tag scoring over chunk `description`/`content`/`tags`) and `scripts/save-to-kb.py` (ingest one doc). `samantha-knowledge-base/query_index.py` / `samantha_query.py` are the older query classes.
- **How Samantha uses it today:** the voice/chat agent (`voice-agent/gpt_agent.py`, `task_manager.py`, `router.py`) instructs workers to shell out to `python3 scripts/search-kb.py "query"`. So the query surface is already a plain CLI — easy to extend without touching the agent.
- **Gaps in the seed:** retrieval is lexical only (no vectors); `samantha-knowledge-base/ingest_sources.yaml` still points at **stale macOS paths** (`/Users/projects/Documents/...`) — it was authored on a Mac and never repointed to the VM; there is **no cron** running it (confirmed — no KB entry in crontab or `process_commands.yaml`).

### 2.2 VM filesystem (the raw corpus)
Top-level under `/home/fields/` with sizes:
- `Fields_Orchestrator/` (4.6 GB) — but most is logs/runs/venv/node_modules; the *knowledge* is `07_Focus/` (planning, playbooks, YouTube/content strategy), `08_Seller-Book/` (the book), `001_Our_Competitive_Advantages/`, `00_Run_Commands/`, `config/*.md` (editorial prompts, flood context), `src/` + `scripts/` (code), `logs/fix-history/*.md`.
- `Feilds_Website/` (1.6 GB) — React app + `netlify/functions/` (the API/business logic).
- `Property_Data_Scraping/` (1.2 GB) and `Property_Valuation/` (30 MB) — scraper + valuation model code.
- `samantha-accounting/` (55 MB), `samantha-email-agent/` (1.2 MB), `fields-automation/` (161 MB), `knowledge-base/` (42 MB).
- **Characterisation:** the high-value indexable text is a few hundred MB of markdown/PDF/code, not the multi-GB total (which is logs, images, `node_modules`, venvs). Brain 3 should index *curated roots*, not `du -sh` everything.

### 2.3 MongoDB (the live operational memory)
Local mongod, surfaced via `src/mongo_client_factory.get_mongo_client`. The strategically important database is **`system_monitor` (109 collections)** — this is Fields' operational nervous system and is *entirely absent* from the current KB. High-value collections (real counts today):
- `process_runs` (4,630), `repair_requests` (4,375), `watchdog_runs` (2,110) — pipeline/ops history.
- `ceo_memory` (600), `ceo_proposals` (73), `ceo_tasks` (302), `ceo_briefs`, `ceo_runs` — the CEO-agent brain.
- `content_articles` (223), `article_index` (96), `article_events` (1,486) — published editorial.
- `will_tasks` (87), `ad_decisions` (25), `website_change_log` (51), `website_deploy_events` (155), `marketing_stage_history`, `leads`, `analyse_leads`, `crm_contacts` (275), `appraisal_substantiation` (1,159), `case_study_library` (5), `market_pulse` (21).
- `agent_messages` (44), `voice_agent_conversations`, `chat_agent_usage` — agent activity.

Other DBs: `Gold_Coast` (98 collections; ~40K cadastral + listings/sold — this is **Brain 1/property-data territory, mostly structured facts, not narrative knowledge**), `property_data`, `Domain_Valuations` (14,985). Note: there are many `*_apr01` snapshot DBs and deprecated `Gold_Coast_Currently_For_Sale` / `_Recently_Sold` — Brain 3 must **exclude** these to avoid indexing stale duplicates.

### 2.4 GitHub (code + change history)
Repos owned by `Will954633`: `Fields_Orchestrator`, `Website_Version_Feb_2026`, `fields-automation`, `fields-ceo-sandbox`, `fields-ceo-context`, `samantha-accounting`, `fields-local-photography`. Most code already exists locally on the VM (index the working tree, not the API), but commit messages / PR history / the CEO sandbox proposals are GitHub-only signal worth capturing.

### 2.5 Google Drive
Custom MCP server at `mcp-servers/gdrive/index.mjs` (OAuth2, auto-refresh) plus a dedicated `gdrive_processor.py` in the ingest pipeline. Key folders: Research (`1AYkf2FPojjKTTPFjx8CkkqX9nXCsM1h9`), Seller Book, Seller Book V2. **Caveat:** Drive OAuth is testing-mode and expires weekly (per memory), and is currently expired — so Drive is a *known source* but not reliably automatable until the auth is hardened. Treat as Phase 2.

### 2.6 Fix history & other narrative logs
- `logs/fix-history/*.md` — daily engineering diary (latest `2026-07-15.md`). High-signal, currently un-indexed.
- The two existing "brains": **Brain 1** (external coaching-corpus knowledge graph, 980+ annotated units — hypotheses) and **Brain 2** (in-house marketing/results: FB Ads API, PostHog, `ad_decisions`, `analyse_leads`). Brain 3 must *reference* these, not duplicate them.
- **Emails** — MS Graph via `scripts/fields-email.py` / `samantha-email-agent/`, but auth not yet configured. Future source.
- **Task board** — Google Sheet (+ `will_tasks`/`ceo_tasks` in Mongo).

## 3. Goals / Non-goals

**Goals**
1. One retrieval call answers "what do we have about X?" across files, Mongo, fix-logs, and the book — with semantic (not just keyword) matching.
2. Entities and relationships are traversable ("the book" → strategies that cite it → the door-knock delivery method → seller-acquisition goal).
3. Freshness: an automatic daily incremental update, tied into the existing nightly job window.
4. Zero new query surface for consumers — Samantha's runs and the voice agent keep calling one CLI/tool; it just gets smarter underneath.

**Non-goals**
- Not a replacement for Brain 1 or Brain 2 — it indexes and *links to* them.
- Not a re-index of the 40K structured `Gold_Coast` property rows as prose (that's a property-data query, not knowledge). Index the *summaries/precomputed* collections and metadata only.
- Not a real-time system. Daily freshness is enough; nothing here needs sub-minute latency.
- Not a UI project. Consumption is programmatic (agents), with maybe a debug search CLI.

## 4. Who/what consumes it
- **Samantha's scheduled runs** — the primary consumer; needs to ground every decision in "everything we have."
- **The voice/chat agent** (`fields-voice-agent`, Haiku router + Opus workers) — already calls `search-kb.py`; inherits the upgrade for free.
- **Will** — occasional direct queries ("what did we decide about X", "where's the doc on Y").
- **The CEO agents** — could query it for context instead of the current bespoke context export.

## 5. The core question: do we even need this, or just extend Brain 2 / the existing KB?

Honest answer: **we do NOT need a new brain, and we should not extend Brain 2 either.**

- **Extending Brain 2 is the wrong fit.** Brain 2 is defined (in Samantha's charter) as *"the ONLY source of truth for our own results"* — measured marketing outcomes (ad metrics, leads, valuations). It is deliberately a **narrow, high-trust, numbers** brain. Dumping the fix-log, the book, orchestrator internals, and 5,000 process-run records into it would pollute exactly the property that makes it valuable: that when Samantha cites Brain 2, it's a measured fact. Keep Brain 2 pure.
- **A greenfield Brain 3 is wasteful.** We already have the ingestion pipeline, the chunk schema, the category taxonomy, the storage layout, and the agent integration. Rebuilding is throwing away working parts.
- **The right move is to promote the existing KB into "Brain 3"** by fixing its three real deficiencies (lexical-only search, no auto-refresh, partial coverage) and adding the graph overlay. This is the smallest change that delivers everything Will described.

So: **Brain 3 = the existing `knowledge-base` KB, upgraded and renamed.** Same doctrine as the charter's brain taxonomy — Brain 1 = outside world, Brain 2 = our measured results, **Brain 3 = everything we have written/built/logged internally, semantically indexed and graph-linked.**

## 6. Value vs cost

**Value**
- Eliminates blind-spots like the book incident — every future run has full recall of what Fields has built.
- Compounds: every fix-log entry, article, proposal, and decision becomes retrievable context, so the agents get less amnesiac over time.
- Cheap to run once built (nightly embed of only *changed* docs + one small extraction pass).

**Cost (estimated, see Part 2 §7)**
- Build: ~5–8 focused days of engineering across phases.
- One-time embedding backfill of ~7,000 existing chunks + new sources (~15–25K chunks total): a few dollars with a small embedding model.
- Ongoing: pennies/day for incremental embeds; the graph-extraction LLM pass is the main recurring cost and is optional/Phase-3.

## 7. Risks

- **Staleness** — the #1 risk and the reason the current KB failed. Mitigation: incremental nightly cron tied to the existing 20:30 pipeline, with a freshness metric surfaced in ops.
- **Cost / scope creep** — "index everything" invites indexing 40K property rows and gigabytes of logs. Mitigation: an explicit **allowlist of curated roots + collections**; hard exclude `*_apr01`, `node_modules`, `venv`, raw cadastral rows, blobs, logs/runs.
- **Cosmos RU limits** — the site DB is Cosmos serverless (~5000 RU/s) and RU exhaustion (error 16500) is a recurring pain. Mitigation: **do not put the vector index in the hot Cosmos site DB.** Read Mongo for ingest with the existing `cosmos_retry` wrapper and throttling; store vectors in a *separate* store (local mongod vector collection or a file-backed FAISS/SQLite index) so retrieval never competes with the website for RU.
- **Duplication / drift vs Brain 1 & 2** — Brain 3 could restate their content and cause contradictions. Mitigation: Brain 3 stores *pointers* to Brain 1/2 records, and its provenance always names the source.
- **Auth fragility (Drive, email)** — weekly-expiring Drive OAuth and unconfigured MS Graph mean those connectors will silently rot. Mitigation: sequence them late (Phase 2+), alert on connector failure, and don't block the core build on them.
- **Semantic-search false confidence** — embeddings can retrieve plausible-but-wrong chunks. Mitigation: keep provenance + a lexical re-rank; the agent must cite the source doc.

## 8. Recommendation

**Build Brain 3 as an upgrade of the existing `/home/fields/knowledge-base/` KB, in phases.** Phase 1 (highest ROI, ~2 days): repoint the ingest to real VM roots, add embeddings + a semantic search mode to `search-kb.py`, index the currently-missing high-value corpora (the seller book, `07_Focus/`, `logs/fix-history/`, and the `system_monitor` narrative collections), and schedule a nightly incremental refresh. Defer the knowledge-graph overlay and the fragile connectors (Drive, email) to later phases. Do **not** touch Brain 2's purity, and do **not** greenfield.

---

# PART 2 — DEVELOPMENT DOCUMENT

## 1. Design principles
- **Reuse, don't rebuild.** Keep the chunk JSON schema, category taxonomy, and the `scripts/search-kb.py` CLI as the stable contract. Everything else is swappable underneath.
- **One query surface.** Consumers keep calling `search-kb.py "query"`. We add a `--semantic` path and later a `--graph` path; we never ask the agents to learn a new interface.
- **Curated allowlist, not "everything."** Explicit source config; hard excludes.
- **Provenance always.** Every chunk carries `source_type`, `source_path/collection`, `source_id`, `ingested_at`, `content_hash`.
- **Freshness by hashing.** Re-embed only chunks whose `content_hash` changed since last run.

## 2. Architecture

```
                 ┌──────────────── INGESTION CONNECTORS ────────────────┐
  VM files ──►   │ fs_connector        (curated roots, md/pdf/code)     │
  MongoDB ──►    │ mongo_connector     (system_monitor narrative colls) │
  fix-logs ──►   │ fixlog_connector    (logs/fix-history/*.md)          │
  GitHub  ──►    │ git_connector       (commit msgs, CEO sandbox)       │
  Drive   ──►    │ gdrive_connector    (Phase 2, existing MCP/processor)│
  Email   ──►    │ email_connector     (Phase 3, MS Graph)             │
                 └───────────────┬──────────────────────────────────────┘
                                 ▼
                     normalize → chunk (800 tok, ~15% overlap)
                                 ▼
             content_hash → changed? ──no──► skip
                                 │yes
                                 ▼
        embed (small model)  +  LLM metadata (existing gpt-4o-mini pass)
                                 ▼
        ┌─────────────── STORAGE (separate from hot site DB) ───────────┐
        │ kb_chunks:   {chunk_id, content, embedding[], tags, meta,     │
        │               source_*, content_hash}   (local mongod coll)   │
        │ kb_graph:    {entities[], edges[]}       (Phase 3)            │
        │ (existing JSON index files kept as human-readable mirror)     │
        └───────────────────────────────────────────────────────────────┘
                                 ▼
        RETRIEVAL: search-kb.py --semantic  (vector kNN + lexical re-rank)
                   search-kb.py --graph      (entity lookup + 1–2 hop expand)
                                 ▼
             Samantha runs · voice agent · Will · CEO agents
```

### 2.1 Ingestion connectors (one module each)
- **`fs_connector`** — walks a curated allowlist (see §6), extracts text (reuse `processor_lib`/`save-to-kb.py` extractors: md, txt, pdf via PyPDF2, docx). This immediately fixes the book blind-spot by including `08_Seller-Book/`.
- **`mongo_connector`** — reads *narrative* `system_monitor` collections (`content_articles`, `ceo_proposals`, `ceo_memory`, `ceo_briefs`, `will_tasks`, `ad_decisions`, `website_change_log`, `case_study_library`, `market_pulse`, `appraisal_substantiation`, `repair_requests` summaries). Renders each doc to a short text card + metadata. Uses `cosmos_retry` and a low batch size. **Excludes** raw `Gold_Coast` property rows and all `*_apr01` snapshots.
- **`fixlog_connector`** — trivial: each `## [PROBLEM-ID]` block in `logs/fix-history/*.md` becomes a chunk with `problem_id`, date, files. High signal, near-zero cost.
- **`git_connector`** — `git log` over local working trees for commit messages; optionally `gh api` for CEO-sandbox proposals. Metadata only, cheap.
- **`gdrive_connector` (Phase 2)** — reuse existing `gdrive_processor.py` + MCP; gate on auth health.
- **`email_connector` (Phase 3)** — MS Graph once configured.

### 2.2 Chunking
Keep the existing paragraph-grouping chunker (`chunking_system.py`, 800 tokens) but add **~15% overlap** so semantic boundaries aren't lost. Structured Mongo docs are chunked as one card each (usually < 800 tokens).

### 2.3 Embedding model choice
- **Recommendation: OpenAI `text-embedding-3-small`** (1536-dim). Rationale: the pipeline already uses the OpenAI SDK + `OPENAI_API_KEY` (for `gpt-4o-mini` classification), so zero new dependency/credential; it's cheap (~$0.02 / 1M tokens → the whole backfill is a few dollars); quality is ample for internal recall.
- **Alternative if we want zero per-query API cost / offline:** a local `sentence-transformers` model (e.g. `bge-small-en` / `all-MiniLM-L6-v2`) on the VM. Trade-off: adds a heavy torch dependency and CPU inference on an e2-standard-2. Given the corpus is small (tens of thousands of chunks), the hosted small model is simpler. Decide with Will (open question §8).

### 2.4 Vector store
- **Recommendation: a dedicated `kb_chunks` collection in the local mongod** (the same instance the website reads via `34.40.230.132:27017`), separate database (e.g. `knowledge_base`). Do vector kNN either with a Mongo vector index if the local build supports it, or — given small scale — load embeddings into memory and brute-force cosine at query time (7–25K vectors × 1536 dims is trivial, < 100 ms).
- **Explicitly NOT** the Cosmos site DB path — keep RU pressure off the website.
- **Simplest viable alternative:** a single-file FAISS or even a NumPy `.npy` + SQLite metadata sidecar under `/home/fields/knowledge-base/vectors/`. This needs no DB at all and is easy to back up (GCS mirror). For Phase 1 this may be the fastest path.
- Keep the existing per-doc JSON index files as the human-readable mirror + fallback lexical search.

### 2.5 Retrieval interface (extend `search-kb.py`)
Add flags, keep the default behaviour backward-compatible:
- `search-kb.py "query"` — current lexical (unchanged).
- `search-kb.py "query" --semantic` — embed query → cosine kNN over `kb_chunks` → lexical re-rank of top-k → return with provenance.
- `search-kb.py "query" --hybrid` — union of lexical + semantic (recommended default once proven).
- `search-kb.py --entity "Before You List book"` — graph lookup (Phase 3).
The voice agent's prompts (`voice-agent/task_manager.py`, `gpt_agent.py`, `router.py`) get a one-line update to prefer `--hybrid`. No architectural change to the agent.

## 3. Knowledge-graph overlay (Phase 3)

Purpose: represent *relationships* keyword/vector search can't — the thing that would have told me the book is hand-delivered to doors and tied to seller acquisition.

- **Entities:** typed nodes — `Book("Before You List")`, `System("orchestrator")`, `System("mini-site")`, `Method("door-knock delivery")`, `Strategy("seller acquisition")`, `Goal("5 listing appointments")`, `Person`, `Suburb`, `Campaign`, `Article`, `Proposal`.
- **Edges (triples):** `(Before You List book) —delivered_via→ (door-knock)`, `(door-knock) —serves→ (seller acquisition)`, `(seller acquisition) —ladders_to→ (5 listing appointments)`, `(article X) —cites→ (market_pulse Y)`, `(fix PROBLEM-ID) —touches→ (orchestrator step 116)`.
- **How to build it:** an **LLM triple-extraction pass** (reuse `gpt-4o-mini`, or Opus for higher quality) over each chunk → `(subject, predicate, object)` with the chunk as provenance. Deduplicate/canonicalise entity names (the hardest part — maintain an alias table; e.g. "the book" / "seller book" / "Before You List" → one node). Store as `kb_graph.entities` + `kb_graph.edges`.
- **Retrieval with the graph:** entity lookup returns the node + 1–2 hop neighbourhood, and the chunks attached to each edge — so a query about the book surfaces the delivery method and the strategy automatically.
- **Scope honestly:** entity resolution is where these projects rot. Start with a *small curated ontology* (a dozen entity types, the key business objects) and LLM-extract only within it, rather than open-domain extraction. Ship the graph only after Phases 1–2 prove value.

## 4. Daily auto-update mechanism

- **Trigger:** a new step in the nightly window (pipeline runs 20:30 AEST). Add a `process_commands.yaml` process or a dedicated systemd timer `fields-kb-refresh` (~21:30, after the pipeline writes its run data so fix-logs/process_runs are fresh).
- **Incremental logic:** each connector lists current source items → compute `content_hash` → compare to stored hash → only new/changed items get re-chunked, re-embedded, re-extracted. Deleted sources get tombstoned. This keeps nightly cost to pennies and runtime to minutes.
- **Freshness telemetry:** write a `kb_refresh` record to `system_monitor` (last run, docs added/updated, failures per connector) and surface it in the ops dashboard so staleness can never silently return (the failure mode that killed v1).
- **Backfill:** a one-time `--full` run to embed the existing ~7,000 chunks + newly-connected sources.

## 5. Retrieval quality / evaluation
- Build a tiny **eval set** of ~20 real questions Samantha should be able to answer (including "what is the Before You List book and how is it delivered?") and check recall after each phase. This is the objective test of whether Brain 3 is working.

## 6. Curated source allowlist (initial)
**Include:** `08_Seller-Book/` (excl. images), `07_Focus/`, `001_Our_Competitive_Advantages/`, `00_Run_Commands/*.md`, `config/*.md`, `src/` + `scripts/` (code, as CODE type), `logs/fix-history/`, `Feilds_Website/netlify/functions/` (business logic), plus the `system_monitor` narrative collections listed in §2.1.
**Exclude (hard):** `node_modules/`, `venv/`, `logs/runs/`, `*.log`, blobs/images, `Gold_Coast` raw property rows, all `*_apr01` / deprecated snapshot DBs, `.env`/credentials.

## 7. Phased build plan + effort estimate

| Phase | Scope | Effort |
|-------|-------|--------|
| **0. Repoint + rerun** | Fix `ingest_sources.yaml` to real VM paths; run a fresh full ingest so the KB stops being 4 months stale; add the seller book + fix-logs immediately. Proves the pipeline still works. | ~0.5 day |
| **1. Semantic + missing corpora** | Add embeddings (`text-embedding-3-small`), vector store, `search-kb.py --semantic/--hybrid`; add `mongo_connector` (narrative `system_monitor`), `fixlog_connector`; wire voice agent to `--hybrid`; nightly incremental cron + freshness telemetry. **This delivers 80% of the value.** | ~2–3 days |
| **2. More connectors** | `git_connector`; harden + schedule `gdrive_connector` (fix weekly-OAuth first); eval set. | ~1–2 days |
| **3. Knowledge graph** | Curated ontology, LLM triple extraction, entity resolution/aliases, `--entity` retrieval + 1–2 hop expansion. | ~2–3 days |
| **4. Later sources** | Email (MS Graph once auth'd), task board sync, richer graph. | ongoing |

**Total to a genuinely useful Brain 3 (through Phase 1): ~3 days.** Full vision incl. graph: ~6–8 days. Recurring cost: a few $ one-time backfill, pennies/day incremental; graph extraction is the only non-trivial recurring cost and is Phase-3/optional.

## 8. Open questions for Will
1. **Embedding model:** hosted OpenAI `text-embedding-3-small` (simplest, ~$ trivial, tiny per-query cost) vs local `sentence-transformers` (no API cost, heavier VM footprint)? I lean hosted.
2. **How much of `system_monitor` counts as "knowledge"?** I propose the ~12 narrative collections in §2.1 and explicitly *excluding* the raw property/metric rows. Agree, or do you want specific collections in/out?
3. **Do we rename?** Formalise the existing KB as "Brain 3" in the charter and docs, so the three-brain model is explicit (1 = world, 2 = our measured results, 3 = everything we've built/written/logged)?
4. **Graph priority:** is the graph overlay worth Phase-3 effort now, or is semantic hybrid search over full coverage enough for the current "5 listings" north-star? (My honest take: Phase 1 first; only build the graph once we feel the *relationship* gap in practice.)
5. **Drive/email urgency:** are Drive docs and email high-value enough to justify fixing the weekly-OAuth and MS Graph auth now, or defer?
6. **Freshness SLA:** nightly is my recommendation. Any source (e.g. a live decision log) you'd want indexed within minutes instead?

---

*Verification note: all paths, collection names, file counts, and category breakdowns above were checked live on the VM on 2026-07-15. The macOS ingest paths, the "no nightly cron," and the "keyword-only, no embeddings" findings are confirmed from the source files. Google Drive OAuth state and MS Graph email auth were taken from persistent memory, not re-tested this session.*
