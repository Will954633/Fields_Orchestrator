# E1 — Where is this business wasting money?

Find the largest avoidable spend in this system. The business is pre-revenue with a finite runway, so
recurring waste matters more than one-off cost.

Places worth looking, though do not limit yourself to these:

- **Cosmos DB (Azure, serverless, ~5000 RU/s burst).** RU is billed per operation. Look for queries
  that scan when they could seek, missing filters (`Gold_Coast` collections hold ~40k cadastral records
  and a query without `listing_status` hits all of them), unbounded `find()` in loops, repeated
  identical reads that could be cached, nightly jobs re-reading what did not change, and full-document
  `replace_one` where a `$set` would do.
- **LLM API spend.** Multiple providers are in use (Anthropic metered vs Claude Max subscription,
  OpenAI, OpenRouter, Gemini via Vertex). `scripts/cost-collector.py` exists — see what it records.
  Look for work running on a metered API that could run on the Max subscription, oversized context
  being resent, retries without backoff, and vision calls on images larger than the model needs.
- **Netlify.** Build minutes and function invocations. Deploys triggered more often than necessary,
  functions that re-open a database connection per invocation instead of pooling, missing cache headers
  causing repeat cold work.
- **GCP.** This VM (e2-standard-2) plus any other instance. Idle or oversized resources, orphaned
  disks, snapshots, static IPs, storage buckets holding data nothing reads.
- **Duplicated work.** Two scripts computing the same thing. A cron running more often than its data
  changes. A job whose output nothing consumes — check whether anything actually reads it.

Check the crontab (`crontab -l` is not available to you, but `logs/crontab-backups/` holds recent
copies) for frequency-vs-need mismatches: a job running hourly against data that updates monthly is
pure waste.

For each finding, estimate the monthly saving and say what the estimate rests on. A finding of
"$4/month" ranked above a real "$200/month" is a failure of prioritisation — but so is inventing a
large number you cannot support.
