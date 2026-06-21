# Fields Compliance — Digital Appraisal ("Your Home")

**Owner:** Will Simpson · Licensed Real Estate Agent (QLD), Licence No. **4832972** · Fields Real Estate
**Scope:** the `/your-home/:slug` mini-site, which is a **digital property appraisal** delivered to a prospective seller, plus the records that prove it was done lawfully.
**Status:** controls A–N implemented 2026-06-21. This is the operating manual; the full audit is referenced in §8.

> **Why this matters.** When a seller asks us what their home is likely to sell for, we are giving a *price representation* and an *appraisal* under the **Property Occupations Act 2014 (Qld)** and the **Australian Consumer Law**. Both carry a reverse onus: if a representation isn't backed by reasonable grounds, it is *taken to be misleading* and the onus is on us to prove otherwise (PO Act s 212(4)–(5), s 215). These controls and records are that proof.

---

## 1. The legal framework (plain version)

| Source | Obligation we meet |
|--------|--------------------|
| **PO Act s 215 + Sch 2** | A price request must be answered with a **Comparative Market Analysis** — ≥3 sales within the previous **6 months**, similar standard, within **5 km** — or a written explanation if one can't be prepared. |
| **PO Act s 212 / s 209** | No false/misleading representation about value, characteristics, etc. Must have **reasonable grounds** (reverse onus). |
| **PO Act ss 209 & 215** | Marketing must correctly state features + the client's price instructions and be **checked by the licensee**. |
| **PO Act Part 4 (Form 6)** | An agent can't provide services until appointed via a **Form 6**. |
| **ACL s 18 / s 29 / s 30** | No misleading/deceptive conduct; no false claims about services or land (value, future returns); no misleading competitor comparisons; no omission of material facts. |

---

## 2. Compliance controls on the appraisal (audit items A–N)

| # | Control | Where it lives |
|---|---------|----------------|
| A | **Statutory CMA** surfaced on every appraisal (≥3 sold / 6 mo / 5 km, suburb-first + 5 km ring; s 215 written-explanation fallback) | `scripts/property_reports/statutory_cma.py` → `StatutoryCMA` component |
| B | **No competitor superiority claim** (Domain comparison removed) | `ValuationTab` / `ValuationEvidence` / `homeFixture` |
| C | **"Market appraisal, not a formal valuation"** statement | `ValuationTab` + `ReportFooter` |
| D | **Report-level disclaimer** (third-party data, limitation of liability) | `ReportFooter` |
| E | **"Prepared as at / valid until 90 days"** currency stamp | statutory CMA + `ReportFooter` |
| F | **Licensee identity + Licence No. 4832972** on the report | `ReportFooter` |
| G | **Buyer shares/reach labelled "modelled, not measured"** | `BuyersTab` |
| H | **Assumptions & material-facts block** (title, flood→FloodWise, zoning) | `ValuationTab` |
| I | **Ownership/authority acknowledgement** at address entry | `AnalyseYourHomePage` |
| J | **Costs + Form 6** reference | `NextTab` |
| K | **Immutable appraisal/CMA archive** (record-keeping) | `scripts/compliance/appraisal_archive.py` |
| L | **Credential evidence register** | `scripts/compliance/credential_register.py` |
| M | **"General info, not financial/legal/tax advice"** caveat | `FaqTab` |
| N | **Licensee sign-off log** | `scripts/compliance/licensee_signoff.py` |

Website code is in `Will954633/Website_Version_Feb_2026` (`src/pages/YourHomePage/...`). Orchestrator code is in `Will954633/Fields_Orchestrator`.

---

## 3. The record-keeping system (K / L / N)

Three MongoDB collections in **`system_monitor`** are the primary store; all three are mirrored off-VM nightly.

| Collection | Item | Shape | Integrity |
|------------|------|-------|-----------|
| `appraisal_archive` | K | One **append-only** row per delivered appraisal version: address, `as_at`, `valid_until`, full `statutory_cma`, comps, range, `prepared_by` + licence. | `content_hash` (SHA-256) + `prev_hash` + `chain_index` → tamper-evident chain. Never updated. |
| `credential_register` | L | One row per public credential claim → evidence reference + verification status. | `verified` / `evidence_pending` / `retired`. |
| `licensee_signoff` | N | One row per licensee check of an artifact (appraisal / listing copy / FB post / article). | `approved` / `changes_requested` / `review_pending`; ties to the archived version's `content_hash`. |

### Storage tiers
1. **VM — MongoDB `system_monitor`** (primary, queryable).
2. **Off-VM — GCS `gs://fields-blob-backup/compliance/`** (guaranteed; dated `snapshots/<date>/` + `latest/` + `manifest.json`).
3. **Off-VM — Google Drive `Compliance/`** (human/auditor-friendly; *best-effort* — see §6, currently pending an auth fix).

> **PII rule:** these records contain addresses/owner data. They go to **Mongo + GCS + Drive only — NEVER GitHub.** Local exports (`compliance_exports/`) are gitignored.

---

## 4. Daily automation

**Cron — 23:55 AEST** (after the 23:30 property-reports refresh):
```
bash /home/fields/Fields_Orchestrator/scripts/compliance/run_nightly.sh
   → appraisal_archive            (archive any new/changed delivered appraisal)
   → offsite_backup               (GCS + Drive mirror of all three collections)
   → appraisal_archive --verify   (re-walk + verify the hash chain)
```
Log: `logs/compliance-nightly.log`.

---

## 5. Runbook (manual commands)

All commands run from `/home/fields/Fields_Orchestrator` with env loaded:
`set -a && source .env && set +a` and the venv python `/home/fields/venv/bin/python`.

```bash
# K — archive: snapshot any delivered appraisal not yet archived
python3 -m scripts.compliance.appraisal_archive            # all reports
python3 -m scripts.compliance.appraisal_archive --slug <slug>
python3 -m scripts.compliance.appraisal_archive --list     # latest per slug + counts
python3 -m scripts.compliance.appraisal_archive --verify   # integrity check (chain)

# L — credentials
python3 -m scripts.compliance.credential_register --seed   # upsert known claims (idempotent)
python3 -m scripts.compliance.credential_register --list
#   after filing a proof doc in Drive Compliance/Credentials/:
python3 -m scripts.compliance.credential_register --verify <claim_id> \
        --ref "drive:Compliance/Credentials/<file>" --by "Will Simpson"

# N — licensee sign-off
python3 -m scripts.compliance.licensee_signoff --baseline-appraisals  # one-time / catch-up
python3 -m scripts.compliance.licensee_signoff --list
#   programmatic (from the approval gate / publish hooks):
#   from scripts.compliance.licensee_signoff import record_signoff
#   record_signoff("listing_copy", "<slug>", decision="approved",
#                  price_instructions_confirmed=True, notes="...")

# Backup
python3 -m scripts.compliance.offsite_backup               # GCS + Drive(best-effort)
python3 -m scripts.compliance.offsite_backup --gcs-only
```

### Restore from backup
```bash
gsutil cp gs://fields-blob-backup/compliance/latest/appraisal_archive.json .
#   then re-import to system_monitor with mongoimport, or read directly.
```

### Common tasks
- **Add a credential proof (L):** file the document in Drive `Compliance/Credentials/`, then run the `--verify` command above.
- **Record a licensee check of new public copy (N):** call `record_signoff(...)` (or wire the dashboard approval button to it — open follow-up).
- **Prove an appraisal as-at a date (K):** `--list` to find versions, then read the `appraisal_archive` row; verify the chain with `--verify`.

---

## 6. Google Drive backup — setup status & options

**Status: pending an admin action.** GCS is the authoritative off-VM backup until Drive is wired.

Why Drive isn't automated yet:
- The MCP OAuth token (`/home/fields/.gdrive-server-credentials.json`) is **testing-mode → expires ~weekly** (`invalid_grant`). Not usable for an unattended job.
- The floor-plan service account can call the Drive API but has **0 storage quota** (can't create Drive files). No Shared Drive; no domain-wide delegation.

To make Drive hands-off, Will (Workspace admin) picks **one**:
1. **Productionise the OAuth app** (Google Cloud console → OAuth consent screen → Publish), then run `python3 scripts/gdrive-reauth.py` once.
2. **Create a Shared Drive** and add `floor-plan-processor@fields-estate.iam.gserviceaccount.com` as a member (Content Manager); point `offsite_backup.py` at it.
3. **Enable domain-wide delegation** for that SA with the Drive scope.

`offsite_backup.py` already contains the Drive upload code; it skips gracefully until auth works.

---

## 7. Responsibilities & open items

| Item | Owner | Status |
|------|-------|--------|
| Nightly archive + backup | Automated (cron) | ✅ running |
| File credential evidence (finance background, negotiation training) | Will | ⏳ pending |
| Choose + enable a Drive backup path (§6) | Will | ⏳ pending |
| Hook `record_signoff()` into the ops-dashboard approval gate (so NEW reports get a real sign-off, not just the baseline) | Eng | ⏳ follow-up |
| Recalibrate the 90% CI before any public accuracy exhibit | Eng | ⏳ (see valuation backtest constraints) |
| Quarterly: re-verify the chain + spot-check a restored backup | Will | recurring |

---

## 8. References

- **Full audit:** `09_Appraisals/your-home-minisite-compliance-audit-2026-06-21.md`
- **Source legislation (PDFs):** `00_Run_Commands/Industry_Governance/` (Property Occupations Act 2014, Competition and Consumer Act 2010), `09_Appraisals/Sales and Marketing - Part 1.pdf`
- **Code:** `scripts/compliance/` (K/L/N + backup), `scripts/property_reports/statutory_cma.py` (A)
- **Fix history:** `logs/fix-history/2026-06-21.md`
- **Collections:** `system_monitor.{appraisal_archive, credential_register, licensee_signoff}`
- **Backup:** `gs://fields-blob-backup/compliance/`

## 9. Change log
- **2026-06-21** — Initial build. Audit items A–N implemented; record-keeping (K/L/N) live; 18 reports baselined; nightly cron + GCS backup in place; Drive backup pending auth.
