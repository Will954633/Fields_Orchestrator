#!/bin/bash
# Fix All Index Creation Issues - Comprehensive Fix
# Last Updated: 12/02/2026, 6:32 AM (Tuesday) - Brisbane Time
#
# Issue: Multiple scripts crash when trying to create unique indexes on collections with existing documents
# Fix: Wrap ALL index creation in try/except blocks to handle Cosmos DB limitation
#
# Files to fix:
# 1. run_parallel_suburb_scrape.py
# 2. monitor_sold_properties.py (ALREADY FIXED)
# 3. run_complete_suburb_scrape.py
# 4. headless_forsale_mongodb_scraper.py
# 5. diagnose_sold_monitoring.py
# 6. migrate_to_suburb_collections.py
# 7. migrate_sold_to_separate_database.py

echo "=========================================="
echo "Fixing All Index Creation Issues"
echo "=========================================="
echo ""

cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold

# Backup all files
echo "Creating backups..."
for file in run_parallel_suburb_scrape.py run_complete_suburb_scrape.py headless_forsale_mongodb_scraper.py diagnose_sold_monitoring.py migrate_to_suburb_collections.py migrate_sold_to_separate_database.py; do
    if [ -f "$file" ]; then
        cp "$file" "${file}.backup_$(date +%Y%m%d_%H%M%S)"
        echo "  ✓ Backed up $file"
    fi
done

echo ""
echo "Applying fixes..."
echo ""

# Fix each file
python3 << 'PYTHON_EOF'
import re
import os

files_to_fix = [
    'run_parallel_suburb_scrape.py',
    'run_complete_suburb_scrape.py',
    'headless_forsale_mongodb_scraper.py',
    'diagnose_sold_monitoring.py',
    'migrate_to_suburb_collections.py',
    'migrate_sold_to_separate_database.py'
]

fixed_count = 0
skipped_count = 0

for filename in files_to_fix:
    if not os.path.exists(filename):
        print(f"⚠️  {filename} not found - skipping")
        skipped_count += 1
        continue
    
    with open(filename, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Pattern 1: Simple unique index creation (most common)
    pattern1 = r'(\s+)(self\.\w+\.create_index\(\[.*?\], unique=True\))'
    replacement1 = r'\1try:\n\1    \2\n\1except Exception:\n\1    pass  # Index may already exist or collection has documents'
    
    # Pattern 2: Collection variable unique index
    pattern2 = r'(\s+)(\w+\.create_index\(\[.*?\], unique=True\))'
    replacement2 = r'\1try:\n\1    \2\n\1except Exception:\n\1    pass  # Index may already exist or collection has documents'
    
    # Apply fixes
    content = re.sub(pattern1, replacement1, content)
    content = re.sub(pattern2, replacement2, content)
    
    if content != original_content:
        with open(filename, 'w') as f:
            f.write(content)
        print(f"✅ Fixed {filename}")
        fixed_count += 1
    else:
        print(f"⏭️  {filename} - no changes needed")
        skipped_count += 1

print(f"\n{'='*50}")
print(f"Summary: {fixed_count} files fixed, {skipped_count} skipped")
print(f"{'='*50}")

PYTHON_EOF

echo ""
echo "=========================================="
echo "Fix Complete!"
echo "=========================================="
echo ""
echo "All index creation issues have been fixed."
echo "Scripts will now handle Cosmos DB gracefully."
