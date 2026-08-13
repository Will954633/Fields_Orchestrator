# Verification scripts — /property A/B

Puppeteer harnesses used to verify the `property_page_v2` instrumentation against
**production**. Kept because every defect found on 2026-08-13 was invisible to
`vite build` and `tsc` and visible only here.

Run from the website dir (they need its `node_modules`):

```bash
cd /home/fields/Feilds_Website/01_Website
node /home/fields/Fields_Orchestrator/15_On_Market/verify/verify_final.cjs   # drive both arms
node /home/fields/Fields_Orchestrator/15_On_Market/verify/pagecheck.cjs      # does the page render at all
node /home/fields/Fields_Orchestrator/15_On_Market/verify/srcsetcheck.cjs <url>  # image bytes
```

## Two things that will waste an hour if you don't know them

1. **posthog-js drops headless traffic.** With the default UA the SDK reports
   `has_opted_out_capturing() === false` and silently sends nothing. You must spoof
   BOTH a real user agent AND `navigator.webdriver === false`
   (`page.evaluateOnNewDocument`). `verify_final.cjs` does both.
2. **PostHog ingestion runs ~2 minutes behind.** A query immediately after a run
   shows a partial event list. Twice on 2026-08-13 that produced a false "the event
   is broken" conclusion. Wait, then re-query.

⚠ Per-`distinct_id` lookups are **not** reliable — PostHog reassigned/aliased the id
mid-session on one control run, and the events were only findable in the arm-level
aggregate. Prefer aggregating by `properties.arm` over chasing a single visitor.

To force an arm without a `?variant=` parameter:
`window.posthog.featureFlags.override({property_page_v2: 'v2'})` then reload.
⚠ The override changes `getFeatureFlag()` locally but NOT the server-evaluated
`$feature/*` super-property, so those two disagree under override. That is a test
artefact, not a bug.
