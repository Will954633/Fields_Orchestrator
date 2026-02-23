---
# Fields Orchestrator — Daily Incremental Processing Plan

**Purpose of this document**
This plan describes how to adapt the existing Fields Orchestrator pipeline to run **daily** while:

1. Processing **only newly-listed properties** (and any previously-failed/incomplete properties)
2. Detecting **sold transitions** and moving those properties to the **sold collection**
3. Introducing a **robust, auditable “fully processed” marking system** so we can confidently **skip** already-complete properties **as long as they remain for-sale**

It is written to reflect the current orchestrator structure (see `src/task_executor.py`, `config/process_commands.yaml`) and to acknowledge a key constraint:

> We have not yet had a clean end-to-end run, so there may be few or no properties that have been successfully processed. Therefore, we must be conservative: **only mark a property as skippable if we can verify every required artifact exists and is correct**, not merely because a process “ran”.

---

## Last Updated

**28/01/2026, 5:02 PM (Wednesday) — Brisbane (UTC+10)**

### Edit History (descending)

- **28/01/2026, 5:02 PM (Wednesday) — Brisbane**
  - Initial version: daily incremental model, sold migration, per-property completion verification + development plan.

---

## 0) Goals, Deliverables, Success Criteria

### Goal
Run the orchestrator daily in a way that is:

- Incremental (new listings + incomplete only)
- Idempotent (safe to re-run)
- Auditable (we can explain why a property was skipped)
- Conservative in marking “complete” (no false completes)

### Deliverables (design + development)

1. **Per-property processing state model** (MongoDB fields and/or a dedicated collection)
2. **Property selection logic** for daily runs (new vs. incomplete vs. sold)
3. **Verification rules** for each pipeline step before a property can be marked “fully processed”
4. **Sold transition procedure**: detect, move to sold collection, and prevent re-processing in for_sale
5. **Operational workflow**: schedule, backfill, retry strategy, and safe rollout plan

### Success Criteria

- Daily run completes with the majority of work limited to:
  - new listings since yesterday
  - properties that failed previously
  - sold transitions
- Properties that are marked “fully processed” are reliably skipped on subsequent runs **unless**:
  - the property sells
  - the pipeline definition changes (new step/version bump)
  - data corruption is detected by verification
- The system produces a clear run summary:
  - how many properties were new
  - how many were processed
  - how many were skipped (and why)
  - how many transitioned to sold
  - how many failed verification and were queued for reprocessing

---

## 1) Current Orchestrator Sequence (as implemented today)

From `config/process_commands.yaml` (execution order):

1. **Monitor For-Sale → Sold Transitions** (Selenium)
2. **Scrape For-Sale Properties** (heavy write)
3. GPT Photo Analysis
4. GPT Photo Reorder
5. Floor Plan Enrichment (For Sale)
6. Floor Plan V2 Processing (Batch) (currently guarded/no-op until fully wired)
7. Room-to-Photo Matching (Batch)
8. Property Valuation Model
9–13. Backend enrichment (dimensions, timeline, suburb medians, stats, insights)
14. Scrape Sold Properties (heavy write)
15. Floor Plan Enrichment (Sold)

Important observation:

- The orchestrator currently runs **steps**, but does not have a “per-property completion” concept. It can tell that a step succeeded, but not that **each property** was correctly updated.

This is the core gap to solve.

---

## 2) Daily Incremental Operating Model (High-Level)

Each day we want three categories of work:

### A) Sold transitions (for-sale → sold)

- Detect for-sale listings that became sold
- Move them to the sold collection and/or apply a sold marker
- Ensure they are no longer treated as for-sale candidates

### B) New listings (not previously seen)

- Identify listings that appeared since the last successful run
- Fully process them through all “for sale enrichment” steps

### C) Incomplete/failed listings (previously seen)

- Identify properties that are:
  - missing required artifacts (e.g., no photo analysis)
  - have failed verification
  - were mid-flight when a run crashed
- Re-attempt only the missing steps

### D) Existing fully processed and still for-sale listings

- **Skip enrichment steps**
- Optionally allow lightweight refresh operations (e.g., price changes) during scrape

---

## 3) Proposed “Property Processing State” Model (MongoDB)

### 3.1 Key Design Principles

1. **Do not trust “a step ran”** → trust “required output fields exist and pass validation”.
2. Store enough metadata to answer:
   - “Why was this property skipped?”
   - “Which step failed last time and what was the error?”
   - “Has the pipeline changed since this property was marked complete?”
3. Support safe reprocessing when:
   - a bugfix is deployed
   - a new step is added
   - the data contract changes

### 3.2 Recommended Approach

Use **two layers**:

1) **Embedded status on the property document** (fast skip decisions, simple)
2) A **run/event log collection** for audit and debugging (optional but strongly recommended)

#### Embedded status (recommended fields)

In `for_sale` and `sold` property documents, add:

```js
orchestrator: {
  // lifecycle
  lifecycle: "for_sale" | "sold" | "unknown" ,
  first_seen_at: ISODate,
  last_seen_at: ISODate,

  // pipeline signature to invalidate old “complete” markers when pipeline changes
  pipeline_signature: {
    version: 1,
    // could be a hash of process_commands.yaml + key script versions
    signature: "sha256:..."
  },

  // processing state
  processing: {
    status: "new" | "incomplete" | "processing" | "complete" | "needs_review" ,
    last_run_id: "2026-01-28T20:30:00+10:00" ,
    last_attempt_at: ISODate,
    fully_processed_at: ISODate | null,

    // per-step verification results (the important part)
    steps: {
      scrape_for_sale: { ok: true, verified_at: ISODate, details: { ... } },
      gpt_photo_analysis: { ok: false, verified_at: ISODate, error: "missing field ..." },
      gpt_photo_reorder: { ... },
      floor_plan_enrichment: { ... },
      floor_plan_v2: { ... },
      room_photo_matching: { ... },
      valuation: { ... },
      backend_enrichment: { ... }
    }
  }
}
```

#### Audit log collection (recommended)

Collection: `orchestrator_runs` and `orchestrator_property_events`

- `orchestrator_runs`: one document per daily run
- `orchestrator_property_events`: append-only per property per step attempt + verification outcome

This helps when a run crashes mid-way or when scripts fail silently.

### 3.3 Identity / Keying

To make skip logic stable, we need a canonical key. Recommended:

- `domain_listing_id` (if available) OR
- normalized `listing_url` as `_id` OR
- internal `property_id` already present in your schema

If the current pipeline uses multiple identifiers, the plan should include a normalization step.

---

## 4) “Fully Processed” Definition (What must be true to skip)

### 4.1 Why this must be strict

Because we have not had a clean end-to-end run, many properties may contain:

- partial GPT results
- missing floor plan enrichments
- stale or broken “v2” outputs
- valuation missing
- backend enrichment missing

So we must define a property as **skippable** only if a verifier confirms **all** required artifacts.

### 4.2 Proposed completeness gates (For Sale)

Minimum recommended “complete” gates for `for_sale`:

1. **Scrape (for sale)**
   - Must have core listing fields present (address/suburb/beds/baths/price/agent/etc.)
   - Must have images array / image URLs present
   - Must have `orchestrator.last_seen_at` updated in the latest run

2. **GPT photo analysis**
   - Required fields exist (whatever your canonical output field is)
   - Non-empty analysis for at least N photos (define N)

3. **GPT photo reorder**
   - `photo_tour_order` exists
   - Contains at least 20 items (per your own description)
   - Order references valid image IDs/URLs

4. **Floor plan enrichment**
   - floor plan analysis exists OR explicit “no floor plan present” marker
   - extracted rooms/areas pass basic sanity checks

5. **Floor plan v2 + room matching**
   - If Step 9 is currently a guarded no-op, then:
     - either exclude it from “complete” temporarily, OR
     - keep “complete” impossible until V2 is properly wired

   Recommendation: introduce a **pipeline_signature.version** and define v1/v2 completeness:
   - v1 complete: does not require floorplan v2 artifacts
   - v2 complete: requires v2 artifacts

6. **Valuation**
   - `iteration_08_valuation.predicted_value` exists and is numeric
   - optionally: store model version used

7. **Backend enrichment (capital gain + insights)**
   - room dimensions parsed (if floor plan exists)
   - property timeline enriched
   - suburb medians exist for that suburb
   - suburb stats exist
   - property insights / rarity fields exist

### 4.3 Completeness gates (Sold)

Sold completeness is separate and can be lighter or heavier depending on your needs.
At minimum:

- sold scrape has sold date / sold price
- sold floor plan enrichment if available

---

## 5) How to Verify Per-Property Completion (Verifier/Auditor)

### 5.1 Add an explicit verification step

Add a new orchestrator “meta step” that:

- Queries MongoDB for candidate properties
- Applies the completeness gates above
- Writes verification results into `orchestrator.processing.steps.*`
- Sets:
  - `processing.status = complete` only if all gates pass
  - otherwise `processing.status = incomplete` or `needs_review`

This is the safest way to avoid needing every external script to perfectly report status.

### 5.2 Candidate sets for verification

Verifier should check:

- New properties discovered this run
- Properties touched/updated this run
- Properties previously marked incomplete

### 5.3 Conservative marking rules

Only mark `complete` if:

- All required gates pass
- No “unknown status” flags exist (if relevant)
- The property is still `lifecycle=for_sale`
- The `pipeline_signature.signature` matches current pipeline

If any required artifact is missing → mark `incomplete` and record exactly what is missing.

---

## 6) Daily “Only New + Incomplete” Selection Logic

### 6.1 Tracking new properties

There are two viable ways (can do both):

**Option A — Snapshot diff (recommended quick win)**

- Persist the list of for-sale listing URLs each day (`state/for_sale_snapshot.json` already exists)
- Compute:
  - `new_urls = todays_urls - yesterdays_urls`
  - `removed_urls = yesterdays_urls - todays_urls` (these may be sold/expired)

**Option B — first_seen_at / last_seen_at fields**

- During scrape, set `first_seen_at` when inserting a new document
- Update `last_seen_at` for each listing seen today

### 6.2 Selecting work each day

Define:

- `RUN_ID`: timestamp-based unique id
- `pipeline_signature`: hash of current pipeline

Candidate “for sale enrichment” list is:

1) `new` properties (first_seen_at >= run_start OR in new_urls)
2) `incomplete` properties (processing.status in [incomplete, needs_review])
3) `stale` properties (pipeline_signature mismatched)

Properties to skip:

- processing.status == complete AND lifecycle == for_sale AND pipeline_signature matches

### 6.3 How to enforce selection across existing scripts

Today many steps likely iterate “all docs missing field X”. That is already partially incremental.

For stronger control, add a shared mechanism:

- orchestrator writes a file: `state/current_run_candidates.json` (list of ids/urls)
- each downstream script supports one of:
  - `--only-ids-file path.json`
  - `--run-id RUN_ID` and filters `orchestrator.processing.last_run_id == RUN_ID`
  - `--query '{...}'`

Then `config/process_commands.yaml` can pass the filter into each command.

---

## 7) Sold Transition Procedure (Move to Sold Collection)

### 7.1 Requirements

When a property sells:

- It must stop being treated as for-sale
- Its document should be moved to (or mirrored into) `sold` collection
- The move must be idempotent (safe to re-run)
- We should preserve lineage:
  - original for-sale `_id`
  - sold record `_id`
  - move timestamp and reason

### 7.2 Recommended flow

1. Step 1 (Monitor for-sale → sold) detects sold
2. It writes a marker on the for-sale doc:
   - `orchestrator.lifecycle = "sold"`
   - `orchestrator.sold_detected_at = now`
   - and ideally `sold_details` (sold date/price/source)
3. A “sold mover” job runs immediately after monitor:
   - `copy -> sold` (upsert)
   - `delete from for_sale` OR `mark archived` (choose one)

Recommendation: **copy + mark archived**, at least initially, until you trust the pipeline.

Example fields:

```js
orchestrator: {
  lifecycle: "sold",
  migrated_to_sold: {
    at: ISODate,
    run_id: "...",
    method: "monitor_sold_properties",
    sold_collection_id: "..."
  }
}
```

### 7.3 Handling ambiguity

Some listings will be “unknown” (auction, withdrawn, temporarily blocked).
Those should become:

- `lifecycle = "unknown"`
- excluded from “complete”
- placed into a daily review queue with reason

---

## 8) Pipeline Signature + Versioning (Avoid stale “complete” markers)

If we mark properties complete today, and tomorrow we add a new step (or fix Step 9), then old properties are no longer complete.

Solution:

1. Create a `pipeline_signature.signature` string computed from:
   - `config/process_commands.yaml`
   - and optionally key versions of downstream scripts
2. Store it on each property when verified
3. On each run, if signatures mismatch, mark property as `stale` and reprocess

This avoids manual wiping of flags.

---

## 9) Development Plan (Phased Implementation)

### Phase 0 — Observability + Safety (1–2 days)

- Add `RUN_ID` concept to orchestrator logs and run summaries
- Create `orchestrator_runs` collection (optional) to record:
  - run start/end
  - step success/failure
  - counts (new, processed, skipped, moved-to-sold)

### Phase 1 — Data Model + Verifier (2–4 days)

- Implement `src/property_processing_verifier.py` (new module)
  - defines gates per step
  - writes `orchestrator.processing.*` and per-step verification results
- Add a new orchestrator step: “Verify & Mark Properties”
- Run verifier in **dry-run mode** initially:
  - compute results
  - do NOT mark complete until confidence is high

### Phase 2 — Candidate Selection (2–5 days)

- Implement snapshot diff and/or first_seen_at/last_seen_at tracking
- Produce `state/current_run_candidates.json`
- Modify downstream processes to accept candidate filtering
  - start with the most expensive steps first (Room-to-Photo matching, GPT steps)

### Phase 3 — Sold Migration Hardening (1–3 days)

- Ensure monitor step writes explicit sold markers
- Implement sold mover:
  - idempotent copy/upsert
  - optional archival removal from for_sale
- Add a report:
  - which ids moved
  - which failed to move

### Phase 4 — Backfill Strategy (ongoing)

Because there may be 0 “complete” properties today:

- Introduce “backfill nights” where you deliberately process a limited batch of old properties
- Use a cap (e.g., process max 20 properties per night)
- Keep daily run focused on new properties + failed ones

### Phase 5 — Operational Rollout (1–2 days)

- Turn on marking `complete` only after verifier passes on a representative sample
- Add alerts/notifications if:
  - completion rate drops
  - sold transitions spike
  - unknown status rate spikes

---

## 10) Testing Plan

### Unit-level

- Verifier rules tested against mocked property documents
- Pipeline signature generation tested for stability

### Integration-level

- Run orchestrator against a small controlled subset:
  - 5 new
  - 5 incomplete
  - 5 complete (once you have them)

Verify:

- only candidates are processed
- complete properties are skipped
- sold properties are moved
- failures re-queue correctly

### Dry-run marking

- For several nights, run verifier with:
  - `write_verification_results = true`
  - `mark_complete = false`

Then compare:

- what verifier says is complete
- with manual spot checks

---

## 11) Open Questions / Decisions Needed

1. **Canonical property identifier**: what is the stable unique key across all pipelines?
2. **Sold mover policy**: delete-from-for_sale vs archive flag?
3. **Completeness definition for Step 9** (Floor Plan V2):
   - do we treat V2 as required for “complete” right now, or introduce pipeline versions?
4. **Minimal daily refresh for “complete” for-sale properties**:
   - do we still update price/inspection times daily, or treat those as optional?

---

## 12) Suggested Next Actions (Practical)

1. Implement verifier in dry-run mode (fastest path to safe marking)
2. Decide pipeline versioning around Floor Plan V2
3. Add candidate filtering to the most expensive steps first
4. After 3–7 stable dry-run nights, enable `mark_complete=true`
