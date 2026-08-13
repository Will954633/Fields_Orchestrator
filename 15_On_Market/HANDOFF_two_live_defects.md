# Handoff — two live defects found while building the On-Market V2 work

**Written:** 2026-08-13 · **For:** a separate Claude session · **Author context:** found while
building image derivatives + auditing analytics for the `/property` A/B test. Neither is fixed.

⚠ **Read this first:** I originally described these to Will as "6 corrupt originals" and "115 of
1,493 sitemap URLs broken — probably worth more traffic than the redesign". **Both descriptions were
wrong**, and I corrected them by measuring. Defect 1 is real but is not what I said it was; defect 2
is largely already fixed. The measured position is below. Do not carry the original framing forward.

---

## Defect 1 — Matterport 3D tour pages stored as `.jpg` and served as photos

### What it actually is

Six files under `/data/blobs/property-images/` have a `.jpg` extension and ~200 KB of **HTML** in
them. I first assumed they were failed-download error pages. They are not. Every one is a
**Matterport 3D Showcase page** for the correct property:

| Blob path (under `property-images/`) | Bytes | `<title>` |
|---|---|---|
| `for_sale/robina/690bd7f38b8f54659260a015/photos/2026-07-13/46.jpg` | 202,731 | 5 Chelsea Pl, Robina - Matterport 3D Showcase |
| `for_sale/robina/6a54c0e9b8e22f0011d8d08e/photos/2026-07-13/30.jpg` | 154,035 | 6 Jucara Av, Robina - Matterport 3D Showcase |
| `for_sale/robina/6a5a05bdf52d8b60206405b2/photos/2026-07-17/24.jpg` | 196,968 | 7/3 Camphor Wood Ct, Robina - Matterport 3D Showcase |
| `for_sale/burleigh_waters/690bd89a8b8f5465926486dc/photos/2026-07-27/52.jpg` | 218,208 | 42/20 Executive Dr, Burleigh Waters - Matterport 3D Showcase |
| `for_sale/varsity_lakes/690bd7ef8b8f546592608a89/photos/2026-07-10/58.jpg` | 200,627 | 8 Morea Ct, Varsity Lakes - Matterport 3D Showcase |
| `for_sale/varsity_lakes/690bd8008b8f54659260f759/photos/2026-08-07/36.jpg` | 198,013 | 13 Acklin Ct - Matterport 3D Showcase |

### Root cause — traced, not guessed

The virtual-tour URL is **in the source image list**. For `5 Chelsea Place, Robina`
(`Gold_Coast.robina`, `_id` `690bd7f38b8f54659260a015`):

```
property_images_original[46] = https://my.matterport.com/show?m=XiYGcTmZqkj&auth=Bearer%20<REDACTED>
property_images[46]          = https://blobs.fieldsestate.com.au/.../photos/2026-07-13/46.jpg
```

The downloader fetched that URL — successfully, HTTP 200 — and wrote the returned HTML to `46.jpg`.
There is **no content-type or magic-byte check on write**, so any URL in the list that isn't an image
becomes a "photo". Note `property_images_original` has 48 entries and `property_images` 47, so the
lists are already not 1:1; don't assume index alignment when fixing.

⚠ The Matterport URLs carry an `auth=Bearer …` token. Treat them as credentials: don't paste them
into logs, commits, or issue text. I redacted the one above.

### Impact

Live and user-visible: the gallery for each of these six listings renders a broken image where the
tour was. Small in count, but it is on the exact surface being redesigned and A/B tested.

### Suggested fix (not implemented)

1. **Guard the write.** In `scripts/download_images_to_blob.py` and
   `scripts/mirror_full_res_photos.py`, verify the payload is actually an image before upload —
   check the response `Content-Type` **and** sniff magic bytes (`\xff\xd8\xff` JPEG, `\x89PNG`,
   `RIFF….WEBP`, `GIF8`). Reject anything else and log it; do not store it.
2. **Filter the source list.** Drop non-image URLs (`my.matterport.com`, any `/show?`, anything
   whose response isn't an image) before they reach the download queue.
3. **Repair the six.** Remove the bad blob and the corresponding `property_images` entry, or re-point
   it. Consider surfacing the Matterport link as a *virtual tour* feature rather than discarding it —
   it is genuinely useful content that is currently being thrown away as a broken photo.
4. **Sweep wider.** I only checked `for_sale` in the three target suburbs. Scope beyond that is
   **unmeasured**. Sweep with `file` for `HTML document` under other containers (`sold/`,
   `gold_coast/`, `cadastral/`).

### How to detect / verify

```bash
# find them
find /data/blobs/property-images/for_sale -name '*.jpg' -size +1k -print0 \
  | xargs -0 -P4 -n50 file | grep -F 'HTML document'

# the derivative job already counts them — it raises above 2% of photos seen
python3 scripts/backfill_image_derivatives.py --suburbs robina --workers 4
# -> metrics.originals_corrupt in system_monitor.job_runs, job='image_derivatives'
```

`shared/image_derivatives.py` raises `DecodeError` on these (it deliberately does **not** treat them
as "nothing to do"), and `scripts/backfill_image_derivatives.py` counts them as `corrupt` and raises
if they exceed 2% of photos seen. So this defect is now *visible*, just not fixed.

---

## Defect 2 — `/property` sitemap URLs rendering "Property Not Found"

### Status: LARGELY ALREADY FIXED — verify before spending time on it

`logs/fix-history/2026-08-08.md:176,204,215` recorded a sitemap↔robots invariant monitor finding
**115 of 1,493 `/property` sitemap URLs (7.7%)** returning HTTP 200 while rendering "Property Not
Found" with `noindex`. I repeated that measurement against the live site on **2026-08-13**:

- Live `sitemap.xml`: **17,338 URLs**, of which **1,508** are `/property/`.
- Random sample of **250** `/property` sitemap URLs fetched live: **0 rendered "Property Not Found".**
- Wilson 95% upper bound: **≤1.5%**, i.e. **at most ~22 of 1,508** — down from 115.

So the remediation between 8 and 13 August appears to have worked. **I did not find a fix-history
entry confirming closure**, which is why it still looked open.

### What is left to do

1. Re-run the invariant monitor itself (the one behind `2026-08-08.md:176`) rather than my sample —
   it presumably checks all 1,508, and can confirm the true residual instead of an upper bound.
2. If a residual exists, it is ~22 URLs at most; fix and **write the closing fix-history entry**, the
   absence of which caused this to be re-reported as open.
3. Related and **not** measured by me: `2026-08-08.md:27` recorded **11 `/property` pages earning
   Google impressions but absent from the sitemap** (e.g. 17 Pitta Place, 33 impressions/2 clicks;
   180 Christine Avenue, 38 impressions). That is the inverse problem and may still be live.

### Correction to carry forward

I told Will this was "probably worth more traffic than the redesign". On the measurement above that
is **not supported** — the defect is mostly gone. The sitemap-absence issue (item 3) is the part that
might still matter, and it is a different, smaller problem.

---

## Useful context for whoever picks this up

- **Blob store:** `/data/blobs` is its own disk, `/dev/sdc`, 738 GB, ~329 GB used. ⚠ `df -h /data`
  reports the 97 GB root and is misleading.
- **Rule 8 applies here.** Both defects were mis-described on first pass because a plausible
  explanation ("error page", "still broken") was carried forward instead of tested. Check the file
  and re-run the measurement before reporting either.
- **Related fix-history:** `logs/fix-history/2026-08-13.md` →
  `[LISTING-IMAGE-DERIVATIVES]`, `[DERIVATIVE-CORRUPT-AS-SKIPPED]` (where the corrupt files were
  first surfaced), `[PROPERTY-ANALYTICS-CENSORED]`.
- **Do not disturb:** an A/A period is running on PostHog flag `property_page_v2` (id 817007,
  control/v2 50/50) and `page_engagement` is newly deployed on the property page. Changing the
  property page's photo list or render path during that window adds a confound — coordinate first.
