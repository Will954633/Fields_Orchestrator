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
LOCAL_KEEP_DAYS=7
DRY_RUN="${1:-}"

log() { echo "[$(date '+%H:%M:%S')] $1"; }

# Always clean up the dump directory on exit, even if a later step fails.
# Without this trap, a failed upload (e.g. transient DNS/auth) leaves a 4-7 GB
# dump dir behind. That's what produced ~38 GB of cruft pre-2026-05-19.
cleanup_dump_dir() {
    if [ -d "$DUMP_DIR" ]; then
        log "Cleaning up dump dir (always-on trap)"
        rm -rf "$DUMP_DIR"
    fi
}
trap cleanup_dump_dir EXIT

if [ "$DRY_RUN" = "--dry-run" ]; then
    log "DRY RUN — would dump to $DUMP_DIR, compress to $ARCHIVE, upload to $GCS_BUCKET"
    exit 0
fi

mkdir -p "$BACKUP_DIR"

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

# Step 3: Drop the uncompressed dump now that we have the tarball.
# Doing this BEFORE the upload means a failed upload still leaves disk clean
# (the trap above is a belt-and-suspenders for unexpected exits).
rm -rf "$DUMP_DIR"

# Step 4: Upload to GCS
log "Uploading to GCS..."
gcloud storage cp "$ARCHIVE" "$GCS_BUCKET/$(basename $ARCHIVE)" --quiet 2>&1
log "Uploaded to $GCS_BUCKET/$(basename $ARCHIVE)"

# Step 5: Remove local archives older than 7 days
find "$BACKUP_DIR" -name "fields_mongodb_*.tar.gz" -mtime +$LOCAL_KEEP_DAYS -delete 2>/dev/null
LOCAL_COUNT=$(ls -1 "$BACKUP_DIR"/fields_mongodb_*.tar.gz 2>/dev/null | wc -l)
log "Local backups: $LOCAL_COUNT (keeping last $LOCAL_KEEP_DAYS days)"

# Step 6: List recent GCS backups
GCS_COUNT=$(gcloud storage ls "$GCS_BUCKET/" 2>/dev/null | wc -l)
log "GCS backups: $GCS_COUNT (auto-deleted after 30 days)"

log "Backup complete: $ARCHIVE_SIZE → $GCS_BUCKET"
