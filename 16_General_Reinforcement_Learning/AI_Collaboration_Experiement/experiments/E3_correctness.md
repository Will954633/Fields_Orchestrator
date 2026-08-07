# E3 — What in this system is silently wrong right now?

Find defects that are live, are producing wrong output, and nobody has noticed. Wrongness that reaches
a reader or a homeowner ranks far above internal untidiness.

The failure modes this codebase actually has, drawn from its own fix-history — treat these as hunting
patterns rather than an inventory of solved problems:

- **A second code path recomputing a metric the guarded pipeline already owns.** A guard that checks a
  document cannot protect a consumer that never reads that document. One instance of this was just
  found in the owner-article generator; assume there are more. Any place a median, count, rate or
  valuation is computed inline rather than read from the canonical field is a candidate.
- **Silent truncation and silent empty results.** A script that exits 0 having written 2KB where 40KB
  was expected. A helper that returns `[]` on an HTTP 504 and lets the caller treat it as "no data".
  Both have cost us days here.
- **Partial `$set` writes leaving stale sibling fields.** A document with several independent content
  layers where updating one leaves the others contradicting it.
- **A process that stopped firing and nobody noticed.** Check `system_monitor.job_runs` heartbeats
  against each job's declared cadence. Anything stale is a live finding. Distinguish deliberately
  paused from dead.
- **Unreliable metrics carrying a narrative.** Our sold-transaction capture from Domain misses 40-50%
  of real sales, so volume and months-of-supply must not drive any claim. Look for places they still do.
- **Two series that disagree.** Where the same quantity is computed two ways and a consumer picks one
  arbitrarily.
- **Guards that no longer cover the case they were written for** — an allowlist that stopped matching,
  a branch that no longer executes.
- **Numbers rendered to the public that no longer match their source**, including hardcoded figures in
  React components that were true when written.

Priority order: anything a homeowner or reader sees > anything that corrupts stored data > anything
that wastes compute > anything merely untidy.

Do not re-report the owner-article median bypass in
`scripts/owner_article/build_owner_article.py` — it is already fixed. Finding a *sibling* of it
elsewhere is exactly what is wanted.
