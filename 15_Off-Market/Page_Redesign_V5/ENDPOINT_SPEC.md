# V5 Off-Market — Per-Address Artifact Endpoints (spec)

**Status:** Spec for developer hand-over
**Date:** 2026-08-21
**Goal:** serve the per-address **Valuation Report** (HTML + cover) and **Market Update** (HTML article + `cards.json`) for **any** off-market property — generated on demand, cached, and served same-origin — **without committing static files to the repo**. This replaces the demo's single-address static files (`public/valuation-report/…`, `public/market-update/…`) so v5 works across the whole ~15k book.

---

## 0. Why an endpoint (not static files)

The demo pre-generated 4 files for `24-bothwell-street-robina` and committed them. At 15k properties that's ~32 GB of repo/CDN weight, and any change to a generator would require re-committing 15k files. The **endpoint approach** makes both cheap:

- **Page look-and-feel changes** stay a single React edit (the page already renders live from the DB) — unaffected by this.
- **Report/article content changes** become "edit the generator → next request regenerates" — no mass re-push.

**This is exactly the pattern the Property Positioning Report already uses** (`netlify/functions/offmarket-report-request.mjs` + `scripts/offmarket_report_poller.py` + blob storage + `scripts/prewarm_offmarket_covers.py`). We mirror it for the two new artifact kinds. **Reuse that pipeline's shape; do not invent a new one.**

---

## 1. The artifacts

| Kind | Generator (Python, VM, deterministic, no AI) | Parts |
|---|---|---|
| `valuation-report` | `16_Valuation/report_page/build_report_page.py` (`--address <complete_address> --collection <suburb> --out`) | `html` (self-contained fragment → wrap as full doc), `cover` (JPEG of the rendered first page) |
| `market-update` | `17_Direct_Letterbox/Owner_Subject_Article/build_owner_article.py` (`--address "<addr>" --suburb <suburb>`) | `html` (self-contained article), `cards` (`<slug>.cards.json`, already emitted by `build_cards()`), `aerial` (the hero PNG) |

Both are **deterministic** (factbook-minted figures, human-maintained macro, precomputed suburb data). Suburb-level facts are shared across all properties in a suburb; only the per-property comps/nearby-sales differ. So generation is cheap DB-query cost per address.

> ⚠ **De-inline the market-article aerial at scale.** The demo inlined the 1.6 MB `aerial-sun.png` as a data URI → a 2.1 MB HTML file. For 15k that's the storage killer. Store the aerial as its own blob (`market-update/aerials/<slug>.png`) and reference it from the HTML. Market HTML then drops to ~16 KB. (Add a `--hero-url` / external-asset mode to `md_to_html`, or post-process to rewrite the `src` to the blob URL.)

---

## 2. Architecture (three layers, mirrors positioning report)

```
Browser (v5 modal)
   │  POST /api/v1/offmarket-artifact {slug, kind}      ← request/poll
   │  GET  /api/v1/offmarket-artifact?slug=&kind=       ← status
   ▼
Netlify function  offmarket-artifact.mjs   (Node — request/queue/serve ONLY)
   │  cache hit  → {status:'completed', url}
   │  cache miss → enqueue system_monitor.offmarket_artifact_requests → {status:'pending'}
   ▼
Azure blob  blobs.fieldsestate.com.au/…    (storage + cache)
   ▲
VM poller  scripts/offmarket_artifact_poller.py   (Python — runs the generators)
   │  claims queued rows → runs build_report_page.py / build_owner_article.py
   │  uploads html/cover/cards/aerial to blob → marks row completed
```

**Netlify functions are Node and cannot run the Python generators** — generation MUST run on the VM, exactly as `offmarket_report_poller.py` does today. The function is only the request/queue/serve layer.

### Blob layout
```
blobs.fieldsestate.com.au/
  valuation-report/<slug>.html
  valuation-report/covers/<slug>.jpg
  market-update/<slug>.html
  market-update/<slug>.cards.json
  market-update/aerials/<slug>.png
```
(Reuse the same blob-upload helper the existing pollers use — see `offmarket_report_poller.py` / `prewarm_offmarket_covers.py` for the auth + upload path.)

---

## 3. Netlify function — `offmarket-artifact.mjs`

`config.path = ["/api/v1/offmarket-artifact"]`. One function, dispatched by `kind`.

**`POST { slug, kind }`** and **`GET ?slug=&kind=&part=`**:
1. Validate `kind ∈ {valuation-report, market-update}`, resolve `slug` → doc via the existing `findPropertyById` shape (must exist, be an off-market subject in a measured suburb).
2. **Cache check:** HEAD the blob(s) for `<slug>`; if present and `computed_at` within the freshness window (**30 days**, or newer than `valuation_data.computed_at` / the monthly market refresh) → return `{ status:'completed', html_url, cover_url, cards_url }` (same-origin paths — see §4).
3. **Miss/stale:** upsert a row into **`system_monitor.offmarket_artifact_requests`** (dedup key `slug+kind`, fields: `slug, kind, complete_address, suburb, state:'queued', source:'offmarket_v5', requested_at`), return `{ status:'pending'|'processing' }`.
4. **Bot/headless UA guard** (copy from `offmarket-report-request.mjs`): answer but never enqueue, to protect the serial render queue.
5. **No auth / no contact capture** — same design stance as the positioning report.

> Consider just **extending `offmarket-report-request.mjs`** with a `kind` param and one shared queue rather than a new function — one request path, one poller, one queue collection. Cleaner ops. (The positioning report becomes `kind:'positioning'`.)

---

## 4. Serving the HTML same-origin (iframe requirement)

The modals iframe the report/article, so the content must be **same-origin** to `fieldsestate.com.au` (the current demo relies on the `/valuation-report/* → SAMEORIGIN` header in `netlify.toml`). Two ways to keep it same-origin from blob:

- **(A, recommended) 200-proxy rewrite.** `netlify.toml` `[[redirects]]` with `status = 200`:
  ```toml
  [[redirects]]
    from = "/valuation-report/*"
    to   = "https://blobs.fieldsestate.com.au/valuation-report/:splat"
    status = 200            # proxy, stays same-origin
  [[redirects]]
    from = "/market-update/*"
    to   = "https://blobs.fieldsestate.com.au/market-update/:splat"
    status = 200
  ```
  The existing `X-Frame-Options: SAMEORIGIN` header rules for those paths still apply (headers run on the proxied response). The iframe `src` stays the clean path `/valuation-report/<slug>.html`. On a cache miss the proxy 404s → the modal's request/poll flow (below) shows a "preparing" state until the blob exists, then loads the iframe.
- **(B) Function streams it.** `offmarket-artifact.mjs` fetches the blob and returns `text/html` with SAMEORIGIN. Simpler config, but the function runs on every view. Prefer (A).

⚠ **Do not** point the iframe directly at `https://blobs.fieldsestate.com.au/…` — cross-origin, and Azure blob will not frame under our origin's SAMEORIGIN expectation.

---

## 5. VM poller — `scripts/offmarket_artifact_poller.py` (systemd)

Mirror `offmarket_report_poller.py`. Loop:
1. Claim `state:'queued'` rows from `offmarket_artifact_requests` (atomic find-and-set `state:'processing'`).
2. Dispatch by `kind`:
   - **valuation-report:** `build_report_page.py --address <complete_address> --collection <suburb> --out <tmp>` → wrap fragment as full HTML → render cover (headless first-page screenshot, the exact method used for the demo cover) → upload `html` + `covers/<slug>.jpg`.
   - **market-update:** `build_owner_article.py --address "<addr>" --suburb <suburb> --out-dir <tmp>` → upload `html` (aerial de-inlined, §1) + `cards.json` + `aerials/<slug>.png`.
3. Honor the generator gates: valuation report **refuses** on `directional_only` / null `reconciled_valuation` (mark row `state:'declined'`, `error:'unavailable'` — the modal then hides the card, like `hasReport()` does); market-update needs suburb data (mark `declined` if absent).
4. Mark row `completed`, stamp `computed_at`.
5. **Rule 7 self-monitoring (mandatory):** wrap the run in `job_run("offmarket_artifact_poller", cadence_hours=…, title=…)`; assert an outcome (Rule 7b) — raise if it claimed rows but produced 0 outputs (upstream broken ≠ empty queue). Never advance a watermark on a failed run.
6. Serial + rate-limited like the positioning poller (~35s/render); one row at a time protects Cosmos RU and the render queue.

---

## 6. Pre-warm batch — `scripts/prewarm_offmarket_artifacts.py`

Mirror `prewarm_offmarket_covers.py`. Nightly (or on data-refresh):
- Iterate indexed off-market subjects in the measured suburbs (start with the 3; the generators already gate elsewhere on data availability).
- For each, if the artifact is missing or older than the source data (`valuation_data.computed_at`, monthly market refresh), enqueue/generate + upload.
- This makes **most user requests return `completed` on the POST** (the fast path), exactly like the 8,291 pre-warmed positioning covers. The poller handles only the long tail + freshness.
- **Watermark on the source-data timestamp**, not "last run", so a failed night re-does its work (Rule 7b).

---

## 7. v5 page changes (small)

- **Valuation & Market modals:** replace the static-file assumption with the **request/poll flow already implemented in `PositioningReportCard`** (`POST → poll GET → open`). On miss show "Preparing your report…"; on `completed` set the iframe `src` to the same-origin path. Reuse that component's logic — it already does exactly this for the positioning report.
- **`cards.json` fetch:** `GET /api/v1/offmarket-artifact?slug=&kind=market-update&part=cards` **or** just fetch `/market-update/<slug>.cards.json` (proxied, §4); on 404 kick a POST to enqueue and render the CTA-only ladder until it's ready.
- **Valuation cover:** `/valuation-report/covers/<slug>.jpg` (proxied) with the existing `onError` fallback to the icon.
- No layout change — this is purely swapping the data source from static files to the proxied blob + request/poll.

---

## 8. Freshness, gates, cost

- **Freshness:** artifacts stamped `computed_at`; regenerate when `valuation_data` recomputes or the monthly market data refreshes. 30-day cache ceiling as a backstop.
- **Methodology gate (blocking for valuation-report):** per `16_Valuation/report_page/README.md` the report is a **mockup with an open honesty review** (the "four in five" band claim). **Do not pre-warm or serve the valuation report to real users until signed off.** Keep it behind `?v5=1` / a feature flag until then. The market-update article is already Rule-5-compliant and fact-verified (safe), but was authored as a **direct-mail** asset — confirm on-page use with Will.
- **Storage (with aerial de-inlined):** ~15k × (valuation html 60 KB + cover 90 KB + market html 16 KB + cards 4 KB + aerial ~200 KB resized) ≈ **~5–6 GB** on blob (vs ~32 GB if the aerial stays inlined). Resize/compress the aerial for the web.

---

## 9. Effort estimate

| Task | Est. |
|---|---|
| `offmarket-artifact.mjs` (or extend `offmarket-report-request.mjs`) | 0.5 d |
| `netlify.toml` 200-proxy rewrites + confirm SAMEORIGIN | 0.25 d |
| `offmarket_artifact_poller.py` (reuse both generators + blob upload) | 1 d |
| De-inline market-article aerial (`--hero-url` mode) | 0.25 d |
| `prewarm_offmarket_artifacts.py` + systemd/cron + Rule-7 heartbeat | 0.5 d |
| v5 modal wiring (reuse `PositioningReportCard` request/poll) | 0.5 d |
| **Total** | **~3 days** |

---

## 10. Cutover checklist

1. Ship the endpoint + poller + pre-warm; verify a **cold** address (not 24 Bothwell) produces all artifacts on request.
2. Pre-warm the measured suburbs; confirm most requests hit the fast path.
3. Delete the demo static files (`public/valuation-report/…`, `public/market-update/…`) and the demo-only `netlify.toml` SAMEORIGIN header can be kept (the proxy still needs it).
4. Methodology sign-off on the valuation report before it's exposed beyond `?v5=1`.
5. Flip v5 to default (mirror the v4 `wantsV4` default-in-measured-suburbs pattern) — a one-line loader change, reversible via `?v5=0`.

---

### Key existing files to mirror/reuse
- `netlify/functions/offmarket-report-request.mjs` — the request/poll/serve function to copy (or extend with `kind`).
- `scripts/offmarket_report_poller.py` — the VM poller pattern (claim → generate → upload → mark).
- `scripts/prewarm_offmarket_covers.py` — the pre-warm batch pattern.
- `scripts/job_status.py` (`job_run`) — Rule-7 self-monitoring (mandatory for the poller + pre-warm).
- `16_Valuation/report_page/build_report_page.py`, `17_Direct_Letterbox/Owner_Subject_Article/build_owner_article.py` — the two generators (unchanged except the aerial de-inline).
- `src/pages/OffMarketPage/v5/OffMarketV5.tsx` `PositioningReportCard` — the request/poll UI to reuse for the two modals.
