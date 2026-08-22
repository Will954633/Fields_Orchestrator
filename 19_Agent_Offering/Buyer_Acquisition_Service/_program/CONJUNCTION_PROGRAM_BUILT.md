# Fields Conjunction Program — built inventory

Everything from `CONJUNCTION_PROGRAM_BUILD_PLAN.md`, built 2026-08-20. All pushed to
`Will954633/Fields_Orchestrator`. Website-backend edits noted where they live on the VM only.

## Tier 0 — data-integrity foundations
| Item | Artifact | Commit | Verified |
|---|---|---|---|
| 0.1 Floor-area resolver | `shared/floor_area.py`; wired into enrich (step 16), suburb_statistics (step 14), editorial prompt; `calculate_property_insights` None-guard | pushed (shared+editorial+insights); ⚠ enrich + stats are **VM-only, untracked** | 214 docs repopulated; BW median 170→187; 93 fixed 331→220 |
| 0.2 Waterfront geometric fallback | `shared/waterfront.py` (`WATERFRONT_GEOMETRIC_FALLBACK_M=35`) | `7af77e01` | 365 canal-side docs reclassified |
| 0.3 Cadastral polygon backfill | `scripts/backfill_cadastral_polygons.py` (heartbeat, 7b outcome) | `352542e8` | 1,020 fillable; 50 run; area-matched 0.4% |

## Tier 1 — conjunction as a first-class object
| Item | Artifact | Commit |
|---|---|---|
| 1.1 Register | `scripts/conjunction_register.py`, `system_monitor.conjunction_properties` (93 seeded) | `f7adf9fc` |
| 1.2 Guard A (no seller-prospecting) | `samantha/seller_intent.py` + `live_leads_to_sheet.py` | `f7adf9fc` |
| 1.2 Guard B (no positioning verdict) | `generate_property_ai_analysis.py` `_conjunction_editorial_gate()` → `skipped_conjunction` | `f7adf9fc` |

## Tier 2 — intelligence & comparables
| Item | Artifact | Commit |
|---|---|---|
| 2.1 Dossier + contradiction report | `scripts/property_dossier.py` (7 checks) | `6a4844ed` |
| 2.2 Comparable-set builder + claim-tester | `scripts/comparable_set.py` | `aabe8370` |
| 2.3 Block-geometry library | `shared/block_geometry.py` | `fd9ac898` |
| 2.4 Reverse-prospect agent map | `scripts/reverse_prospect_map.py` | `874b1363` |

## Tier 3 — planning
| Item | Artifact | Commit |
|---|---|---|
| 3.1 Derived planning signals | `shared/planning_signals.py` | `a81f068e` |
| 3.1 City Plan report ingest | `scripts/ingest_cityplan_report.py` (→ `zoning_data.cityplan`) | `9b6051c2` |
| 3.2 Dual-occ precedent finder | `scripts/dual_occ_precedents.py` | `b9a5e986` |

## Tier 4 — campaign assembly
| Item | Artifact | Commit |
|---|---|---|
| 4.1 Landing-page generator | `scripts/generate_conjunction_landing.py` + `conjunction_landing_configs/93-*.json` | `a0732b78` |
| 4.2 Campaign-lead reporting | `scripts/campaign_lead_report.py` (interest breakdown) | `73be9322` |
| 4.3 Claim / fact-check gate | `scripts/claim_gate.py` (5 batteries, exit-non-zero on FAIL) | `1480162d` |

## Run the whole workflow for the next property
```
python3 scripts/conjunction_register.py --add property_slug=... listing_agent=... ...
python3 scripts/property_dossier.py --slug <slug>          # facts + contradictions
python3 scripts/comparable_set.py --slug <slug> --claim "..."   # comps + claim test
python3 scripts/reverse_prospect_map.py --slug <slug>      # who to call first
python3 scripts/ingest_cityplan_report.py --pdf <report.pdf> --slug <slug> --store
python3 scripts/dual_occ_precedents.py --slug <slug>
python3 scripts/claim_gate.py --slug <slug> --file claims.txt   # gate every claim
python3 scripts/generate_conjunction_landing.py --slug <slug> [--write-tree]
# ... after launch:
python3 scripts/campaign_lead_report.py --slug <slug>      # which thesis converts
```

## ⚠ Open items for Will
1. **Valuations shift tonight** on ~45 properties whose floor area was corrected (watch 5 Camberwell 331→190, 7 Winton 367→275, 21 Olympus 236→389). Strictly more correct (internal, not carport-inclusive totals) but published $ moves.
2. **Backup gap:** `enrich_properties_for_sale.py` and `generate_suburb_statistics.py` (Feilds_Website) are not git-tracked — edits are VM-only. Need a repo home.
3. **Landing-page price-floor is threshold-sensitive:** "within 1.7km, none sold below $2,196,785" is true, but 148 Burleigh Street (same street, $2,050,000, 850m²) sits at 1.86km — a buyer's agent could raise it. Consider softening the floor language or widening the comp window before the page goes live. The scarcity claim (only 800m²+ non-waterfront *for sale* within 1.5km) is not threshold-sensitive and stands.
