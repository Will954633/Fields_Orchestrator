# Market Research — current index

| Topic dossier | As at | Latest brief | Status |
|---|---|---|---|
| [national-market-turn-2026](topics/national-market-turn-2026.md) | 2026-08-24 | [2026-08-24](briefs/current/2026-08-24_national-market-turn.md) | current |
| [cgt-negative-gearing-2026](topics/cgt-negative-gearing-2026.md) | 2026-08-24 | — | current |
| migration | — | — | active · dossier on first run |
| leading-indicators | — | — | active · dossier on first run |
| interest-rates | — | — | active · dossier on first run |
| supply-and-approvals | — | — | active · dossier on first run |
| sentiment | — | — | active · dossier on first run |
| affordability | — | — | active · dossier on first run |

Evergreen dossiers in `topics/`; dated briefs in `briefs/current/` (→ `briefs/archive/<cycle>/`).

## Automated cycle
- `scripts/run_research_cycle.py` — fortnightly (Sunday noon AEST). Refreshes each of the
  **8 active** topics via headless `claude -p` (Max); topics without a dossier are researched
  from scratch on the first run. Archives + indexes into `system_monitor.market_research_briefs`;
  self-reports (job `market_research_cycle`).
- **Not yet activated** — run `scripts/install_cron.sh` from the main checkout (post-merge).
  `--dry-run` validated. ⚠ First real cycle creates 6 new dossiers (≈8 research passes, run
  sequentially) — budget ~$12-16 and up to ~1-2 hours for that first run; steady-state cheaper.
