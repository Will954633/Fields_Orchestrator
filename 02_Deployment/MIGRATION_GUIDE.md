# Migration Guide: Fix Misplaced Properties
**Date:** 2026-02-17
**Issue:** 1,318 properties stored in wrong collections (56% of database)
**Status:** Ready for migration

---

## ⚠️ Important Notes Before Starting

### Data Model Clarification

The audit found misplaced properties in two contexts:

1. **Suburb-specific collections** (e.g., `varsity_lakes`, `robina`, `burleigh_heads`)
   - These SHOULD contain only properties from that specific suburb
   - Cross-suburb properties here are genuine errors

2. **`Gold_Coast_Recently_Sold` collection**
   - This appears to be a catch-all collection for recently sold properties
   - May be intentional (different data model)
   - **Review before migrating** - you may want to exclude this collection

### Address Data Quality Issues

Some addresses have malformed suburb names:
- **Stored:** "10 Pipit Parade Burleigh, Waters, QLD 4220"
- **Should be:** "10 Pipit Parade, Burleigh Waters, QLD 4220"

This causes the suburb extraction to get "Waters" instead of "Burleigh Waters". These addresses need manual review or a more sophisticated extraction algorithm.

---

## Migration Process Overview

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Dry Run (SAFE - No Changes)                        │
│ → Preview what will be migrated                            │
│ → Verify migration plan makes sense                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Test Migration (Small Batch)                       │
│ → Migrate 10-20 properties                                 │
│ → Automatic backups created                                │
│ → Verify changes manually                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Verify Test Migration                              │
│ → Run verification script                                  │
│ → Check application still works                            │
│ → Confirm data looks correct                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Full Migration (All Properties)                    │
│ → Migrate remaining ~1,300 properties                      │
│ → Automatic backups updated                                │
│ → Detailed logging                                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: Final Verification                                 │
│ → Run verification script                                  │
│ → All checks must pass                                     │
│ → Test application thoroughly                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: Monitor & Cleanup (After 1-7 Days)                 │
│ → Monitor application in production                        │
│ → If all good, cleanup backup collections                  │
│ → Optionally export backups before deletion                │
└─────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Instructions

### Prerequisites

1. **MongoDB Running**
   ```bash
   # Verify MongoDB is accessible
   mongosh --eval "db.version()"
   ```

2. **Current Directory**
   ```bash
   cd /Users/projects/Documents/Fields_Orchestrator
   ```

3. **Scripts Executable**
   ```bash
   chmod +x scripts/migrate_misplaced_properties.py
   chmod +x scripts/verify_migration.py
   chmod +x scripts/cleanup_migration_backups.py
   ```

---

### STEP 1: Dry Run (SAFE)

Preview what will happen **without making any changes**:

```bash
# Preview full migration
python3 scripts/migrate_misplaced_properties.py --dry-run

# Preview first 10 properties only
python3 scripts/migrate_misplaced_properties.py --dry-run --limit 10
```

**Review the output:**
- Which collections will be affected?
- Do the migrations make sense?
- Are any critical collections involved?

---

### STEP 2: Test Migration (Small Batch)

Migrate a small test batch (10-20 properties):

```bash
# Migrate first 10 properties (includes automatic backups)
python3 scripts/migrate_misplaced_properties.py --limit 10
```

**This will:**
1. ✅ Create backups automatically (e.g., `varsity_lakes_backup_20260217_114954`)
2. ✅ Migrate 10 properties to correct collections
3. ✅ Add migration history to each property
4. ✅ Log all operations

**Expected output:**
```
STEP 1: Running database audit...
✓ Audit complete: Found 1318 misplaced properties
✓ Limited to first 10 properties for testing

STEP 2: Creating backups...
📦 Creating backup: varsity_lakes -> varsity_lakes_backup_20260217_114954
   ✅ Backup created: 27 documents

STEP 3: Migrating properties...
[1/10] Migrating property...
   Address: 48 Peach Drive, Robina, QLD 4226
   From: varsity_lakes
   To: robina
   ✅ Migrated successfully

...

MIGRATION SUMMARY
Backups Created: 3 collections
Properties Migrated: 10
Properties Failed: 0
```

---

### STEP 3: Verify Test Migration

Run verification checks:

```bash
python3 scripts/verify_migration.py
```

**This checks:**
1. ✅ Are there remaining misplaced properties? (Should be 1,308 now)
2. ✅ Do backup collections exist and have correct data?
3. ✅ Are there any duplicate properties?
4. ✅ Do total counts make sense?

**Expected output:**
```
CHECK 1: Scanning for Remaining Misplaced Properties
✅ PASSED: Found 1308 remaining (10 were migrated)

CHECK 2: Verifying Backup Integrity
✅ PASSED: 3 backup collections verified

CHECK 3: Checking for Duplicate Properties
✅ PASSED: No duplicates found

CHECK 4: Verifying Total Property Counts
✅ PASSED: Active/backup ratio is reasonable

VERIFICATION SUMMARY
✅ ALL CHECKS PASSED - Migration verified successfully!
```

**Manual Verification:**
1. Check your application - does it still work?
2. Browse properties in the affected suburbs
3. Verify data looks correct in MongoDB:
   ```bash
   mongosh Gold_Coast_Currently_For_Sale
   > db.robina.findOne({address: /Peach Drive/})  # Should be in robina now
   > db.varsity_lakes.findOne({address: /Peach Drive/})  # Should be null now
   ```

---

### STEP 4: Full Migration (All Properties)

If test migration looks good, migrate all remaining properties:

```bash
# Full migration with automatic backups
python3 scripts/migrate_misplaced_properties.py
```

**⚠️ This will ask for confirmation:**
```
⚠️  WARNING: This will modify your database!
Backups will be created automatically before migration.

Continue? (yes/no):
```

Type `yes` and press Enter to proceed.

**Expected duration:** 5-10 minutes for ~1,300 properties

**What happens:**
1. Audits entire database (finds ~1,308 remaining misplaced properties)
2. Creates/updates backup collections for all affected collections
3. Migrates each property to correct collection
4. Logs all operations to console and optionally to file

**To save a log file:**
```bash
python3 scripts/migrate_misplaced_properties.py --log /tmp/migration_$(date +%Y%m%d).json
```

---

### STEP 5: Final Verification

After full migration, verify everything:

```bash
# Run full verification
python3 scripts/verify_migration.py --verbose
```

**All checks must pass:**
- ✅ No remaining misplaced properties (or very few with known issues)
- ✅ Backups intact and correct
- ✅ No duplicates
- ✅ Counts reasonable

**Manual verification:**
1. Test your application thoroughly
2. Check key user flows
3. Verify property searches work correctly
4. Check suburb-specific queries
5. Verify analytics/reports are accurate

**Monitor for 1-7 days:**
- Watch for any unusual behavior
- Check error logs
- Monitor user feedback
- If issues arise, you can restore from backups

---

### STEP 6: Cleanup Backups

After verifying everything works correctly (1-7 days of monitoring):

#### Option A: List Backups (No Deletion)

```bash
python3 scripts/cleanup_migration_backups.py --list
```

Shows all backup collections and their sizes.

#### Option B: Export Then Delete (Recommended)

```bash
# Export backups to JSON (for archival)
python3 scripts/cleanup_migration_backups.py --export /tmp/backups/

# This will:
# 1. Export each backup collection to JSON
# 2. Ask for confirmation
# 3. Delete backup collections
```

#### Option C: Delete Without Export

```bash
python3 scripts/cleanup_migration_backups.py

# ⚠️ Will ask for confirmation before deleting
```

**After cleanup:**
- Backup collections removed
- Database only contains active data
- Disk space freed (estimated ~5-10 MB per collection)

---

## Rollback Procedure

If something goes wrong, you can restore from backups:

### Option 1: Restore Single Collection

```bash
mongosh Gold_Coast_Currently_For_Sale

# Restore varsity_lakes from backup
db.varsity_lakes.drop()
db.varsity_lakes_backup_20260217_114954.find({_backup_metadata: {$exists: false}}).forEach(function(doc) {
  delete doc._id;  // Let MongoDB assign new ID
  db.varsity_lakes.insert(doc);
});

# Verify count
db.varsity_lakes.count()
```

### Option 2: Restore All Collections

Create a rollback script:

```bash
mongosh Gold_Coast_Currently_For_Sale

# For each backup collection:
db.getCollectionNames()
  .filter(name => name.includes('_backup_'))
  .forEach(backupName => {
    const originalName = backupName.replace(/_backup_.*$/, '');
    print(`Restoring ${originalName} from ${backupName}`);

    // Drop current collection
    db[originalName].drop();

    // Restore from backup (excluding metadata)
    db[backupName].find({_backup_metadata: {$exists: false}}).forEach(doc => {
      delete doc._id;
      db[originalName].insert(doc);
    });

    print(`  Restored ${db[originalName].count()} documents`);
  });
```

---

## Troubleshooting

### Issue: Migration fails halfway through

**Symptom:** Some properties migrated, some didn't

**Solution:**
1. Backups are already created (safe!)
2. Re-run migration script - it will skip already-migrated properties
3. Or restore from backups and investigate issue

### Issue: Properties in wrong collections after migration

**Symptom:** Verification finds misplaced properties

**Solution:**
1. Review audit output to see which properties
2. Check if addresses are malformed (e.g., "Burleigh, Waters" instead of "Burleigh Waters")
3. May need manual fixes for these edge cases
4. Consider improving address extraction logic

### Issue: Application errors after migration

**Symptom:** 404s, missing properties, broken queries

**Solution:**
1. Check if queries assume old data structure
2. Review which collections were modified
3. Restore from backups if needed
4. Update application code to handle new structure

### Issue: Duplicate properties detected

**Symptom:** Verification finds duplicates

**Solution:**
1. Review duplicate report
2. Determine which copy is correct (check timestamps, data completeness)
3. Manually remove duplicates or re-run migration with fixes

---

## Advanced Options

### Exclude Specific Collections

If you want to exclude `Gold_Coast_Recently_Sold` from migration:

**Modify the audit script:**

```python
# In database_audit.py, audit_all_collections method:
collections = [c for c in collections
               if not c.startswith('system.')
               and c != 'Gold_Coast_Recently_Sold']  # Add this line
```

### Migrate Specific Collection Only

```bash
# Modify migration script to filter errors by collection
# This requires code changes - contact developer
```

### Test on Staging First

**Best practice:**
1. Dump production database: `mongodump --db Gold_Coast_Currently_For_Sale`
2. Restore to staging: `mongorestore --db Gold_Coast_Staging`
3. Run migration on staging
4. Test thoroughly
5. Then run on production

---

## Success Criteria

Migration is successful when:

- ✅ Verification script passes all checks
- ✅ No (or very few) remaining misplaced properties
- ✅ Application works correctly
- ✅ No user complaints
- ✅ Analytics/reports accurate
- ✅ No performance degradation
- ✅ Backups created and verified
- ✅ Migration logged and documented

---

## Post-Migration

### Documentation

1. Update this guide with actual results
2. Document any issues encountered
3. Note any properties that needed manual fixes
4. Update team on changes

### Monitoring

Monitor these metrics:
- Database size (should be roughly the same)
- Query performance (should be similar or better)
- Error rates (should not increase)
- User reports (should not spike)

### Future Prevention

The scraper bug has been fixed in:
- ✅ `run_parallel_suburb_scrape.py` - uses actual address suburb
- ✅ `database_audit.py` - runs automatically after each orchestrator cycle (Process 107)

New properties will be stored in correct collections automatically.

---

## Timeline Recommendation

**Recommended schedule:**

- **Day 1:** Dry run + test migration (10-20 properties)
- **Day 2:** Verify test, if good → full migration
- **Day 3-9:** Monitor application (1 week)
- **Day 10:** If all good → cleanup backups

**Fast-track (if urgent):**

- **Hour 1:** Dry run
- **Hour 2:** Test migration (10 properties) + verify
- **Hour 3:** Full migration
- **Hour 4-24:** Monitor closely
- **Day 2-3:** Cleanup backups if stable

---

## Support

If you encounter issues:

1. Check this guide's Troubleshooting section
2. Review migration log file (if exported)
3. Run verification script with `--verbose` flag
4. Check MongoDB logs
5. Backups exist - you can always rollback

**Emergency rollback:**
- Backups are automatically created before any changes
- See "Rollback Procedure" section above

---

## Appendix: Script Reference

### migrate_misplaced_properties.py

**Purpose:** Safely migrate properties with automatic backups

**Options:**
- `--dry-run` - Preview without changes
- `--limit N` - Migrate only first N properties
- `--no-backup` - Skip backups (not recommended)
- `--log FILE` - Export migration log to JSON

**Example:**
```bash
python3 scripts/migrate_misplaced_properties.py --limit 10 --log /tmp/test.json
```

### verify_migration.py

**Purpose:** Verify migration was successful

**Options:**
- `--verbose` - Show detailed verification output

**Example:**
```bash
python3 scripts/verify_migration.py --verbose
```

### cleanup_migration_backups.py

**Purpose:** Remove backup collections after verification

**Options:**
- `--list` - List backups without deleting
- `--export DIR` - Export to JSON before deleting
- `--collection NAME` - Delete specific backup only

**Example:**
```bash
python3 scripts/cleanup_migration_backups.py --export /tmp/backups/
```

### database_audit.py

**Purpose:** Audit database for misplaced properties

**Options:**
- `--verbose` - Show detailed progress
- `--collection NAME` - Audit specific collection
- `--fix` - Auto-fix errors (use migration script instead)
- `--export FILE` - Export errors to log

**Example:**
```bash
python3 scripts/database_audit.py --collection varsity_lakes --verbose
```

---

**Last Updated:** 2026-02-17
**Version:** 1.0
**Prepared by:** Claude Sonnet 4.5
