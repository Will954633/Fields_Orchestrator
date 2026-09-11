#!/bin/bash
# MongoDB Backup Script
# Dumps all databases, compresses, uploads to GCS, cleans old local copies.
#
# Usage:
#   bash scripts/mongodb-backup.sh              # Full backup
#   bash scripts/mongodb-backup.sh --dry-run    # Show what would happen
#
# Scheduled via cron: 02:00 AEST daily (after pipeline finishes)

set -euo pipefail

BACKUP_DIR="/home/fields/backups/mongodb"
GCS_BUCKET="gs://fields-mongodb-backups"

# Load credentials from .env (COSMOS_CONNECTION_STRING). Avoids hardcoding the
# mongod password in the script (which previously was visible in git/repo).
ENV_FILE="/home/fields/Fields_Orchestrator/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi
MONGO_URI="${COSMOS_CONNECTION_STRING:-}"
if [ -z "$MONGO_URI" ]; then
    echo "ERROR: COSMOS_CONNECTION_STRING not set (looked in $ENV_FILE)" >&2
    exit 1
fi

DATE=$(date +%Y-%m-%d_%H%M)
DUMP_DIR="$BACKUP_DIR/dump_$DATE"
ARCHIVE="$BACKUP_DIR/fields_mongodb_$DATE.tar.gz"
LOCAL_KEEP_DAYS=3
DRY_RUN="${1:-}"

log() { echo "[$(date '+%H:%M:%S')] $1"; }

# Rule 7 heartbeat → system_monitor.job_runs (renders on the Systems Health
# sheet's Process Registry). Best-effort: a monitoring failure must never
# break the backup itself.
heartbeat() {  # $1=success|error  $2=detail
    /home/fields/venv/bin/python3 - "$1" "$2" <<'PY' || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from job_status import record_job_result
record_job_result("mongodb_backup", sys.argv[1], sys.argv[2],
                  cadence_hours=24, title="MongoDB Nightly Backup")
PY
}

# Always clean up the dump directory on exit, even if a later step fails.
# Without this trap, a failed upload (e.g. transient DNS/auth) leaves a 4-7 GB
# dump dir behind. That's what produced ~38 GB of cruft pre-2026-05-19.
# On any non-zero exit, also record an error heartbeat — the backup failed
# silently for 3 of 4 nights 2026-09-08→11 (disk full) before this existed.
cleanup_dump_dir() {
    if [ -d "$DUMP_DIR" ]; then
        log "Cleaning up dump dir (always-on trap)"
        rm -rf "$DUMP_DIR"
    fi
}
on_exit() {
    rc=$?
    cleanup_dump_dir
    if [ "$rc" -ne 0 ] && [ "$DRY_RUN" != "--dry-run" ]; then
        heartbeat error "backup failed rc=$rc — see logs/mongodb-backup.log"
    fi
}
trap on_exit EXIT

if [ "$DRY_RUN" = "--dry-run" ]; then
    log "DRY RUN — would dump to $DUMP_DIR, compress to $ARCHIVE, upload to $GCS_BUCKET"
    exit 0
fi

mkdir -p "$BACKUP_DIR"

# Step 0: Disk preflight. The dump is ~12G uncompressed + ~2.4G archive; with
# less than 16G free the run WILL fail mid-compress (exactly what happened
# 2026-09-08/10/11, leaving corrupt partial tarballs). Fail loudly up front.
FREE_GB=$(df --output=avail -BG / | tail -1 | tr -dc '0-9')
if [ "$FREE_GB" -lt 16 ]; then
    log "ERROR: only ${FREE_GB}G free on / — need >=16G for dump + compress"
    exit 1
fi

# Step 1: Dump all databases
log "Starting mongodump..."
mongodump --uri="$MONGO_URI" --out="$DUMP_DIR" --quiet 2>&1
DUMP_SIZE=$(du -sh "$DUMP_DIR" | cut -f1)
log "Dump complete: $DUMP_SIZE"

# Step 2: Compress
log "Compressing..."
tar -czf "$ARCHIVE" -C "$BACKUP_DIR" "dump_$DATE"
ARCHIVE_SIZE=$(du -sh "$ARCHIVE" | cut -f1)
log "Compressed: $ARCHIVE_SIZE"

# Step 2b: Outcome assertion (Rule 7b). A truncated tarball from a disk-full
# tar is indistinguishable from a good one by exit code alone once the archive
# file exists — both 2026-09-08 (2.3G) and 2026-09-10 (249M) partials sat on
# disk looking like backups. Verify integrity and a sane floor size.
if ! gzip -t "$ARCHIVE"; then
    log "ERROR: archive fails gzip integrity test — deleting corrupt partial"
    rm -f "$ARCHIVE"
    exit 1
fi
ARCHIVE_MB=$(du -m "$ARCHIVE" | cut -f1)
if [ "$ARCHIVE_MB" -lt 1000 ]; then
    log "ERROR: archive only ${ARCHIVE_MB}MB (expect ~2400MB) — treating as failed"
    rm -f "$ARCHIVE"
    exit 1
fi

# Step 3: Drop the uncompressed dump now that we have the tarball.
# Doing this BEFORE the upload means a failed upload still leaves disk clean
# (the trap above is a belt-and-suspenders for unexpected exits).
rm -rf "$DUMP_DIR"

# Step 4: Upload to GCS
log "Uploading to GCS..."
gcloud storage cp "$ARCHIVE" "$GCS_BUCKET/$(basename $ARCHIVE)" --quiet 2>&1
log "Uploaded to $GCS_BUCKET/$(basename $ARCHIVE)"

# Step 5: Remove local archives older than LOCAL_KEEP_DAYS.
#
# Uses -mmin, NOT -mtime. `-mtime +N` truncates age to whole 24h units, so it
# means "age >= N+1 days". Because this script runs from cron at the same clock
# time every day, each archive turns exactly LOCAL_KEEP_DAYS old within seconds
# of the find running — landing on the wrong side of that truncation about half
# the time. Observed 2026-08-24: 5 archives on disk (7.4 GB) where the policy
# intends 4, with the log cheerfully reporting "keeping last 3 days".
# The 60-minute shave makes the boundary unambiguous regardless of cron jitter.
find "$BACKUP_DIR" -name "fields_mongodb_*.tar.gz" \
    -mmin +$(( LOCAL_KEEP_DAYS * 1440 - 60 )) -delete 2>/dev/null
LOCAL_COUNT=$(ls -1 "$BACKUP_DIR"/fields_mongodb_*.tar.gz 2>/dev/null | wc -l)
log "Local backups: $LOCAL_COUNT (keeping last $LOCAL_KEEP_DAYS days)"

# Step 6: List recent GCS backups
GCS_COUNT=$(gcloud storage ls "$GCS_BUCKET/" 2>/dev/null | wc -l)
log "GCS backups: $GCS_COUNT (auto-deleted after 30 days)"

log "Backup complete: $ARCHIVE_SIZE → $GCS_BUCKET"
heartbeat success "$ARCHIVE_SIZE uploaded to $GCS_BUCKET ($LOCAL_COUNT local, $GCS_COUNT in GCS)"
