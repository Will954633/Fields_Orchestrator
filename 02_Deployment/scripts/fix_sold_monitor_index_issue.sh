#!/bin/bash
# Fix Sold Property Monitor - Index Creation Issue
# Last Updated: 12/02/2026, 6:26 AM (Tuesday) - Brisbane Time
#
# Issue: Monitor crashes when trying to create unique index on collection with existing documents
# Fix: Wrap index creation in try/except to handle Cosmos DB limitation
#
# This script fixes the monitor_sold_properties.py file on the VM

echo "=================================="
echo "Fixing Sold Property Monitor"
echo "=================================="
echo ""

# Navigate to the scraping directory
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold

# Backup the original file
cp monitor_sold_properties.py monitor_sold_properties.py.backup_$(date +%Y%m%d_%H%M%S)

# Fix the index creation code (lines 145-151)
# Replace the index creation block with try/except wrapped version
python3 << 'EOF'
import re

with open('monitor_sold_properties.py', 'r') as f:
    content = f.read()

# Find and replace the index creation block
old_code = '''        # Create indexes for sold collection
        self.sold_collection.create_index([("listing_url", ASCENDING)], unique=True)
        self.sold_collection.create_index([("address", ASCENDING)])
        self.sold_collection.create_index([("sold_detection_date", ASCENDING)])
        self.sold_collection.create_index([("sold_date", ASCENDING)])'''

new_code = '''        # Create indexes for sold collection (wrapped in try/except for Cosmos DB)
        try:
            self.sold_collection.create_index([("listing_url", ASCENDING)], unique=True)
        except Exception as e:
            # Cosmos DB doesn't allow unique indexes on collections with existing documents
            self.log(f"Note: Could not create unique index (collection may have existing documents)")
        
        try:
            self.sold_collection.create_index([("address", ASCENDING)])
            self.sold_collection.create_index([("sold_detection_date", ASCENDING)])
            self.sold_collection.create_index([("sold_date", ASCENDING)])
        except Exception as e:
            self.log(f"Note: Could not create indexes: {e}")'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('monitor_sold_properties.py', 'w') as f:
        f.write(content)
    print("✅ Fixed index creation code")
else:
    print("⚠️  Could not find exact match - index creation may have already been fixed")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Sold property monitor fixed successfully!"
    echo ""
    echo "Testing the fix..."
    echo ""
    
    # Test with Robina
    python3 monitor_sold_properties.py --suburbs "Robina:4226" --max-concurrent 1 --test 2>&1 | head -60
    
    echo ""
    echo "=================================="
    echo "Fix Complete!"
    echo "=================================="
else
    echo ""
    echo "❌ Fix failed - restoring backup"
    mv monitor_sold_properties.py.backup_* monitor_sold_properties.py
    exit 1
fi
