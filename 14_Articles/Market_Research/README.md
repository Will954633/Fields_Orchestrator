# 14_Articles/Market_Research — the Market Research Engine

**Single central home for recurring research on the Australian and local property
markets.** One place, many consumers: subject-property letters (17_Direct_Letterbox),
Market Intelligence articles, monthly/quarterly market updates (10_Market_Report),
the seller book (08_Seller-Book), Facebook/organic content. Research is written and
verified **once**, here, and every downstream generator reads from it — so the same
fact is never re-derived, never cited three different ways, and never quietly stale.

> **Why this exists.** Before this folder, market research lived in at least six
> scattered places (`10_Market_Report/research`, `10_Market_Report/editorial_migration_research`,
> `12_Marketing/01_Research_Articles`, `08_Seller-Book/Research`, `17_Direct_Letterbox/02_Research`,
> and the 1,600-file `knowledge-base/`). Nothing was the canonical source, so each
> article re-researched the same ground. This is the one place that supersedes them.

---

## What lives here

```
14_Articles/Market_Research/
├── README.md              ← this file
├── topics/                ← EVERGREEN dossiers, continuously updated. The current
│                            state of knowledge on one theme (one file per theme):
│                            e.g. national-market-turn-2026.md, migration.md,
│                            leading-indicators.md, cgt-negative-gearing.md,
│                            interest-rates.md, supply-and-approvals.md, sentiment.md
├── briefs/
│   ├── current/           ← the latest cycle's briefs — what consumers read NOW
│   └── archive/           ← dated snapshots, one folder per cycle (e.g. 2026-W35/)
│                            so we can always show "as at" and diff cycle to cycle
├── sources/               ← source_registry.md: the reputable sources + data
│                            endpoints we pull from, with reliability notes
├── data/                  ← cached data pulls the briefs cite (ABS series, etc.)
├── scripts/               ← the deep-dive workflow: research runner, data pullers,
│                            brief writer, indexer (to be built)
└── INDEX.md               ← human-readable index of what is current
```

**Two document types, deliberately separate:**
- **Topic dossiers** (`topics/`) are *evergreen* — the living, best-current answer to
  "what do we know about X", rewritten in place as evidence changes. A generator that
  wants "the migration story" reads the dossier.
- **Briefs** (`briefs/`) are *point-in-time* — one cycle's findings, dated and
  archived, so we keep a provenance trail and can say exactly what we knew when.

---

## The rules (inherited from the article-generation discipline)

1. **Every claim carries a source + date.** Reputable sources only (RBA, ABS,
   Treasury, Cotality/CoreLogic, PropTrack, quality press, academic). Fact is
   separated from commentary. No fabricated figures, papers, quotes, or policy
   changes — an unverifiable claim is reported as unverifiable, never filled in.
2. **Test hypotheses, don't confirm them.** When a brief starts from a premise
   ("the market turned because of X"), it verifies X and reports honestly if the
   evidence does not support it.
3. **Evergreen dossiers get an "as at" date** and a short changelog at the bottom.
4. **Nothing here is a forecast.** Research surfaces evidence and its limits;
   downstream editorial decides framing under its own no-advice / no-prediction
   rules. (The subject-property letter, for one, will never turn any of this into a
   prediction — see `17_Direct_Letterbox/Owner_Subject_Article`.)

---

## How downstream generators consume it (the contract)

The markdown here is the **human-reviewable source of truth**. For *programmatic*
consumers (article generators), each brief/dossier is indexed into a queryable store
so code can pull "the latest research on topic X" without parsing markdown:

- **DB collection `system_monitor.market_research_briefs`** (supersedes the existing
  `policy_research_briefs`, which today holds monthly AU/QLD housing policy briefs):
  `{topic, cycle, as_at, summary, findings:[{claim, source, date, url, confidence}],
  supersedes, source_files:[…]}`.
- Generators like the owner-subject article's `fundamentals_context.json` /
  `update_labour_context.py` can then read structured, cited findings instead of each
  re-researching. (Migration, jobs, leading-indicator and arbitrage facts that piece
  currently carries are the first candidates to source from here.)

---

## The automated cycle (to be built — `scripts/`)

Target: a **weekly-to-fortnightly deep-dive** that runs unattended and, for each
active topic:
1. pulls fresh data (ABS Data API, Cotality/PropTrack releases, RBA) into `data/`,
2. runs multi-source research (web + our knowledge-base + academic library) to update
   the topic dossier and write a dated brief into `briefs/current/`,
3. archives the previous cycle into `briefs/archive/<cycle>/`,
4. re-indexes into `market_research_briefs`,
5. self-reports via `job_status.job_run` (CLAUDE.md Rule 7) and asserts a non-empty
   outcome (Rule 7b) — a cycle that researched nothing is a failure, not a success.

Coverage mirrors what the subject-property letter already touches — national macro,
the local market, leading/lagging indicators, migration, supply, sentiment, policy —
plus whatever is topical that cycle.

---

## Relationship to existing folders

- **`10_Market_Report/`** stays the *quarterly Market Report product/engine*; it
  becomes a *consumer* of this research, not a store of it.
- **`12_Marketing/01_Research_Articles/`** (academic housing papers — Abelson et al.,
  etc.) is the *reference library*; link to it from dossiers rather than duplicate.
- **`knowledge-base/`** remains the ingested-document brain; this folder is the
  curated, cited, article-ready layer on top.
