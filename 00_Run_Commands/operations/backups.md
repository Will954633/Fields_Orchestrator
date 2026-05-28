# Backups & Disaster Recovery

**Read this file first when something is lost.** STATE.md shows last-backup freshness; this file explains recovery.

## What's Backed Up

| Asset | Source | Backup target | Schedule | Verified? |
|-------|--------|---------------|----------|-----------|
| Property images | `/data/blobs/` (249GB, ~994k files) | `gs://fields-blob-backup` (GCS Nearline) | Daily 03:00 AEST | Initial sync in progress as of 2026-05-28 |
| MongoDB databases | Local `mongod` (`Gold_Coast`, `property_data`, `system_monitor`) | **NONE** ⚠️ | — | — |
| Orchestrator code | `/home/fields/Fields_Orchestrator/` | `Will954633/Fields_Orchestrator` GitHub | On every push | Yes |
| Website code | `/home/fields/Feilds_Website/01_Website/` | `Will954633/Website_Version_Feb_2026` GitHub | On every push | Yes |
| Automation code | `/home/fields/Fields_Automation/` | `Will954633/fields-automation` GitHub | On every push | Yes |
| `.env` files | VM only | **NONE** ⚠️ | — | — |
| nginx configs / certs | VM only | **NONE** ⚠️ | — | — |

## Gaps to close (priority order)

1. **MongoDB backup** — no off-VM copy. If `/var/lib/mongodb` dies, every property record, ad metric, article, agent proposal is gone. **Action:** nightly `mongodump` → GCS.
2. **`.env` files** — Cosmos URI, OpenAI key, FB token, Anthropic key, etc. Today only on VM. **Action:** encrypted snapshot to GCS (or 1Password export).
3. **nginx / certbot state** — re-recoverable but tedious. **Action:** tar `/etc/nginx/` + `/etc/letsencrypt/` → GCS weekly.

## Restore Procedures

### Restore property images from GCS
```bash
# Full restore (to fresh VM)
sudo mkdir -p /data/blobs
gsutil -m rsync -r gs://fields-blob-backup/ /data/blobs/

# Selective: one suburb's photos
gsutil -m rsync -r gs://fields-blob-backup/property-images/for_sale/robina/ /data/blobs/property-images/for_sale/robina/
```

### Restore code from GitHub
```bash
gh repo clone Will954633/Fields_Orchestrator /home/fields/Fields_Orchestrator
gh repo clone Will954633/Website_Version_Feb_2026 /home/fields/Feilds_Website/01_Website
gh repo clone Will954633/fields-automation /home/fields/Fields_Automation
```

### Restore MongoDB (once backup exists)
TBD — define when mongodump backup is in place.

## GCS Backup Auth Gotcha

`gsutil` writes to `gs://fields-blob-backup` MUST run as the regular shell user (`will.simpson@blueoceans.com.au` gcloud creds). **Never use `sudo gsutil` for this bucket** — the VM's default service account has `devstorage.read_only` scope and writes fail silently-ish with `403 Provided scope(s) are not authorized`.

`/data/blobs/` is owned by `projects:projects` 755, so sudo is unnecessary for reads anyway.

The cron entry lives in user `projects`'s crontab (`crontab -e` as that user), NOT root's:
```
0 3 * * * /snap/bin/gsutil -m rsync -r -d /data/blobs/ gs://fields-blob-backup/ >> /var/log/blob-backup/daily-sync.log 2>&1
```

## Verifying Backup Freshness

```bash
# Source size vs target size
sudo du -sh /data/blobs/
gsutil du -sh gs://fields-blob-backup/

# File count match
sudo find /data/blobs -type f | wc -l
gsutil ls -r gs://fields-blob-backup/ | grep -v '/$' | wc -l

# Last successful daily sync
tail -20 /var/log/blob-backup/daily-sync.log
```

STATE.md surfaces these numbers nightly.

## History

- **2026-05-28** Azure Blob (`fieldspropertyimages`) disabled, subscription cancelled. GCS bucket `fields-blob-backup` created as replacement. First sync attempt failed silently due to sudo/scope issue (see "auth gotcha" above). Retried as user, succeeded.
