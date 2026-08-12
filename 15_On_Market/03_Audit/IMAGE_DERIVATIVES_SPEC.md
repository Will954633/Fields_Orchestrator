# Image derivatives — build spec

**Written:** 2026-08-13 · **Status:** spec, nothing built
**Clears:** blocker 1 of 6 in `prototype/README.md` — "Photographs total ~46 MB (largest single image
10.6 MB) … Production must serve resized derivatives."

---

## 1. The problem, measured

The prototype declares `width="800" height="600"` on every gallery image
(`prototype/build.py:411-412`) and then serves the **full-resolution original**. The browser is told
the display size and handed a 3,000px file anyway. Lazy-loading past the first four is a bandage on
bytes that should never have been sent.

This is not a design fault in the prototype. It is inherited: `blobs.fieldsestate.com.au` stores
exactly one rendition per photo — whatever `mirror_full_res_photos.py` / `download_images_to_blob.py`
downloaded — and nginx (`/etc/nginx/sites-available/blobs`) serves it as a static file with no
transform layer of any kind.

**Measured 2026-08-13**, 120 photos sampled at random from the 62,873 `for_sale` files in Robina,
Varsity Lakes and Burleigh Waters:

| | |
|---|---|
| Mean original | **731 KB** (population mean 685–766 KB — the sample is representative) |
| Median / p90 / max | 298 KB / 2,304 KB / 6.1 MB |
| Median width | **1,618 px** · p90 2,998 px · max 3,240 px |
| Already ≤960 px | 15 / 120 |
| Already ≤1600 px | 57 / 120 |

Re-encoded to WebP q80, against the 86 MB the 120 originals occupy:

| Rendition | Mean | Sample total | Reduction |
|---|---|---|---|
| `480w` | 25 KB | 86 MB → 3 MB | **97%** |
| `960w` | 85 KB | 86 MB → 9 MB | **89%** |
| `1600w` | 202 KB | 86 MB → 30 MB | **65%** |

**A 14-photo gallery: 10.0 MB today → 1.8 MB as 4×1600 + 10×960 — 82% smaller.** The prototype's own
subject is heavier than average (~46 MB) because its photographs are outliers; the median listing
still ships roughly 10 MB where 1.8 MB would do.

## 2. Approach — pre-generated derivatives, not a transform proxy

Two options were considered.

**Chosen: generate at write time.** Widths are written into `/data/blobs` beside the original and
nginx serves them as plain static files. More work up front; **zero** runtime cost, no new failure
mode in the request path, and it suits a VM-local nginx with no CDN transform in front of it.

**Rejected: a resize proxy in front of nginx.** It puts a CPU-bound service on the critical path of
every image on the site, on a box whose recent history is memory-driven lockouts (e2-standard-4, see
fix-history `[BRIDGE-REGEX-CPU-BURN]`). Cheaper to write, permanently more expensive to run, and it
fails closed on the surface we most need to be fast.

### Storage

`/data/blobs` is its own disk: **738 GB, 325 GB used, 376 GB free** (`/dev/sdc`). All three tiers cost
~49% of the source bytes.

Scope derivatives to **`for_sale` in the three target suburbs** — 44 GB, so **~21 GB** of
derivatives. Do **not** blanket-generate across all 325 GB: that store is dominated by 461k cadastral
and 310k `gold_coast` files that no listing page renders.

## 3. Naming

Originals keep their current path exactly
(`{db_label}/{suburb}/{property_id}/photos/{date_prefix}/{i:02d}.jpg`, `download_images_to_blob.py:139`).
Derivatives sit beside them with the width infixed:

```
…/photos/2026-08-10/03.jpg          ← original, untouched, remains the source of truth
…/photos/2026-08-10/03.480.webp
…/photos/2026-08-10/03.960.webp
…/photos/2026-08-10/03.1600.webp
```

Derivable from the original URL by string substitution alone, so no schema change and no second
lookup. nginx already maps `webp` → `image/webp` and already sends
`Cache-Control: public, max-age=31536000, immutable`.

**Never upscale.** 15/120 photos are already ≤960 px and 57/120 ≤1600 px; where the source is
narrower than the target, write no derivative and let the consumer fall back (§5).

## 4. Generation

A single helper — `shared/image_derivatives.py`, `make_derivatives(container, blob_name, data) -> dict[int, str]`
— called from the two places that already write photo blobs, so a new listing is born with its
renditions:

- `scripts/download_images_to_blob.py` (nightly, new listings)
- `scripts/mirror_full_res_photos.py` (gap-fill pass)

Plus `scripts/backfill_image_derivatives.py` for existing stock: idempotent, skips any blob whose
derivatives all exist, `--suburbs` / `--limit` / `--dry-run` like its siblings.

Pillow 12.1.0 is present with WebP support confirmed. Encode `quality=80, method=4`, LANCZOS.

**Throughput — learned in the build, 2026-08-13.** The naive form (decode the full raster, three
independent LANCZOS passes, single-threaded) ran at **~10 photos/min**: about **7 hours for Robina
alone**, which is not a shippable backfill. Two changes took it to **~93 photos/min**, ~9×:

- **`Image.draft()` before `load()`** — libjpeg decodes straight to a 1/2, 1/4 or 1/8 scale, so we
  never decode a 3,000px raster in full to throw most of it away. It is guaranteed not to go below
  the requested size (verified), and it is a no-op for non-JPEG.
  ⚠ **Read the true source width before drafting.** Drafting first and measuring after would make a
  3,000px photo look "too narrow for 1600w" and silently drop its largest rendition.
- **Progressive downscale** — 1600 from the source, 960 from the 1600, 480 from the 960. The chain
  advances even at widths that need no write, so a partially-complete photo still resizes cheaply.

Then `--workers` (default 4) over a `ThreadPoolExecutor`; Pillow releases the GIL across resize and
encode, measured 2.3× on 4 threads. Kept modest — this shares a 4-vCPU box with the pipeline.

**Rule 7 + 7b.** The backfill is an ongoing process, so it wraps in
`job_run("image_derivatives", cadence_hours=24, title="Image derivatives")`, sets
`beat.metrics = {"photos_seen": n, "derivatives_written": w, "skipped_existing": s, "failures": f}`,
and **raises when `photos_seen > 0 and derivatives_written == 0 and skipped_existing == 0`** — the
zero-output path. An empty queue is success; encoding every photo and writing nothing is not. Do not
advance any watermark on a failed run.

## 5. Consumption

The website centralises the full-res rewrite in `netlify/functions/shared-utils.mjs` → `toFullResUrl()`
/ `upgradePhotoQuality()`, called by all six photo surfaces. Derivatives follow the same pattern:
one helper there, emitting a rendition set per photo, so `properties-for-sale.mjs`, `property.mjs`,
`decision-feed*.mjs`, `recently-sold.mjs` and `discover-feed.mjs` all inherit it.

Frontend renders `srcset` + `sizes` with the **original as `src`**, so a photo with no derivative
still displays. That fallback is what makes this shippable before the backfill finishes — nothing
breaks while it runs, images merely stay heavy until it reaches them.

Only derivatives that were actually written may appear in `srcset`; a 404 inside `srcset` costs a
request and silently degrades selection. The rendition set must be built from what exists on disk,
not assumed from the width list.

## 6. Sequence

1. `shared/image_derivatives.py` + unit test on a known-wide and a known-narrow photo.
2. Backfill for `robina` only, `--limit 50` — verify bytes, dimensions and `Content-Type` over HTTPS.
3. Wire the two writers so new listings self-generate.
4. `shared-utils.mjs` helper + `srcset` on the property page; verify with the Rule 4 screenshot gate.
5. Full backfill across the three target suburbs (~21 GB), under `job_run`.
6. Confirm the job on the Process Registry page of the Systems Health sheet.

## 7. Out of scope

Floor plans (`/floor_plans/`) — read at full zoom, and `floor_plan_open` is the most-used element on
the page (`04_Evidence/cta_performance_measured_2026-08-10.md`). Aerials — already 640×640. AVIF —
revisit once WebP is shipped and measured. The cadastral, `gold_coast` and `sold` containers.
