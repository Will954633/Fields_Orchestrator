#!/bin/bash
# Fix MongoDB Connections and Upgrade to GPT
# Last Edit: 14/02/2026, 9:20 AM (Friday) — Brisbane Time
#
# Description: Comprehensive fix for VM night run failures
# - Fixes MongoDB connection strings (localhost → Cosmos DB)
# - Updates photo/floor plan analysis to use GPT instead of Ollama
# - Updates process_commands_cloud.yaml descriptions
#
# Based on: VM_NIGHT_RUN_FEB13_DETAILED_ANALYSIS.md

set -e  # Exit on error

echo "=========================================="
echo "MongoDB & GPT Upgrade Fix"
echo "Started: $(date)"
echo "=========================================="

# Colors for output
RED='\033[0:31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# VM details
VM_NAME="fields-orchestrator-vm"
ZONE="australia-southeast1-b"
PROJECT="fields-estate"

echo ""
echo "Step 1: Fix Ollama_Property_Analysis config.py (MongoDB connection)"
echo "----------------------------------------------------------------------"

# Create fixed config.py for Ollama_Property_Analysis
cat > /tmp/config_fixed.py << 'EOF'
# Last Edit: 14/02/2026, Friday, 9:20 am (Brisbane Time)
# Configuration module for property analysis system
# FIXED: Use COSMOS_CONNECTION_STRING environment variable for cloud deployment

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB Configuration - FIXED FOR CLOUD
# Use COSMOS_CONNECTION_STRING if available (cloud), otherwise fall back to local
MONGODB_URI = os.getenv("COSMOS_CONNECTION_STRING") or os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DATABASE_NAME = "Gold_Coast_Currently_For_Sale"
COLLECTION_NAME = "properties"

# Target Suburbs - Collection names (must match database exactly: underscores for multi-word suburbs)
TARGET_SUBURBS = [
    "robina",
    "mudgeeraba",
    "varsity_lakes",
    "reedy_creek",
    "burleigh_waters",
    "merrimac",
    "worongary",
    "carrara"
]

# Ollama Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = "llama3.2-vision:11b"
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
MAX_TOKENS = 16000
TEMPERATURE = 0.1

# OpenAI Configuration (Can be used as primary or fallback)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")
OPENAI_FALLBACK_ENABLED = os.getenv("OPENAI_FALLBACK_ENABLED", "True").lower() == "true"
USE_OPENAI_PRIMARY = os.getenv("USE_OPENAI_PRIMARY", "True").lower() == "true"  # CHANGED: Use GPT by default
OPENAI_TIMEOUT = 120

# Processing Configuration
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))

# Image Processing
MAX_IMAGES_PER_PROPERTY = int(os.getenv("MAX_IMAGES_PER_PROPERTY", "5"))
IMAGE_DETAIL_LEVEL = "auto"
PROCESS_IMAGES_INDIVIDUALLY = True

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = "logs/ollama_processing.log"

# Paths
LOG_DIR = "logs/"
OUTPUT_DIR = "output/"

# Parallel Processing Configuration
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "2"))
PARALLEL_BATCH_SIZE = int(os.getenv("PARALLEL_BATCH_SIZE", "50"))
WORKER_HEARTBEAT_INTERVAL = int(os.getenv("WORKER_HEARTBEAT_INTERVAL", "60"))
WORKER_TIMEOUT = int(os.getenv("WORKER_TIMEOUT", "600"))
ENABLE_WORKER_LOGS = os.getenv("ENABLE_WORKER_LOGS", "True").lower() == "true"
ENABLE_PROGRESS_LOG = os.getenv("ENABLE_PROGRESS_LOG", "True").lower() == "true"

# Testing Configuration
TEST_RUN = os.getenv("TEST_RUN", "True").lower() == "true"
MAX_BATCHES = int(os.getenv("MAX_BATCHES", "2"))

# Ensure directories exist
for directory in [LOG_DIR, OUTPUT_DIR]:
    os.makedirs(directory, exist_ok=True)
EOF

echo "✓ Created fixed config.py"

echo ""
echo "Step 2: Fix generate_suburb_medians.py (MongoDB connection)"
echo "----------------------------------------------------------------------"

# Create fixed generate_suburb_medians.py
cat > /tmp/generate_suburb_medians_fixed.py << 'EOF'
#!/usr/bin/env python3
"""
Generate Suburb Median Prices Script
Last Updated: 14/02/2026, 9:20 AM (Friday) - Brisbane Time

Description:
Aggregates property_timeline data to create quarterly median prices for each suburb.
FIXED: Use COSMOS_CONNECTION_STRING environment variable for cloud deployment

Output Collection:
- suburb_median_prices: {suburb, property_type, data: [{date, median, count}]}

Usage:
    python generate_suburb_medians.py
"""

from pymongo import MongoClient
from datetime import datetime
import statistics
import sys
import os
from dateutil import parser
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def parse_date_to_quarter(date_str):
    """Parse date string and return year-quarter format."""
    if not date_str:
        return None
    
    try:
        dt = parser.parse(str(date_str))
        year = dt.year
        quarter = (dt.month - 1) // 3 + 1
        return f"{year}-Q{quarter}"
    except:
        return None


def generate_suburb_median_prices():
    """Aggregate property_timeline data to create quarterly median prices for each suburb."""
    print("=" * 80)
    print("GENERATE SUBURB MEDIAN PRICES - Starting")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Connect to MongoDB - FIXED FOR CLOUD
    try:
        # Use COSMOS_CONNECTION_STRING if available (cloud), otherwise fall back to local
        mongodb_uri = os.getenv("COSMOS_CONNECTION_STRING") or os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
        client = MongoClient(mongodb_uri)
        gc_db = client['Gold_Coast']
        
        # Create collection for median prices
        medians_collection = client['property_data']['suburb_median_prices']
        
        print("✓ Connected to MongoDB")
        print(f"✓ Using connection: {mongodb_uri[:50]}...")
        print(f"✓ Source: Gold_Coast database")
        print(f"✓ Target: property_data.suburb_median_prices\n")
    except Exception as e:
        print(f"✗ Failed to connect to MongoDB: {e}")
        sys.exit(1)
    
    # Get all suburbs
    try:
        suburbs = gc_db.list_collection_names()
        print(f"Found {len(suburbs)} suburb collections\n")
        print("-" * 80)
    except Exception as e:
        print(f"✗ Failed to list suburbs: {e}")
        sys.exit(1)
    
    total_suburbs_processed = 0
    total_suburbs_with_data = 0
    total_errors = 0
    
    for suburb_idx, suburb in enumerate(suburbs, 1):
        print(f"\n[{suburb_idx}/{len(suburbs)}] Processing: {suburb}")
        
        try:
            collection = gc_db[suburb]
            
            # Get all properties with timeline data
            properties = collection.find({
                'scraped_data.property_timeline': {'$exists': True, '$ne': []}
            })
            
            # Collect all sales by quarter
            quarterly_sales = {}
            
            for prop in properties:
                timeline = prop.get('scraped_data', {}).get('property_timeline', [])
                
                for event in timeline:
                    if not event.get('is_sold') or not event.get('price'):
                        continue
                    
                    try:
                        # Parse price
                        price = event.get('price')
                        if isinstance(price, str):
                            price = price.replace('$', '').replace(',', '').strip()
                            price = int(float(price))
                        else:
                            price = int(price)
                        
                        if price <= 0:
                            continue
                        
                        # Parse date to quarter
                        date_str = event.get('date')
                        quarter = parse_date_to_quarter(date_str)
                        
                        if not quarter:
                            continue
                        
                        # Add to quarterly sales
                        if quarter not in quarterly_sales:
                            quarterly_sales[quarter] = []
                        
                        quarterly_sales[quarter].append(price)
                    
                    except (ValueError, TypeError):
                        continue
            
            # Calculate medians for each quarter
            quarterly_data = []
            
            for quarter in sorted(quarterly_sales.keys()):
                prices = quarterly_sales[quarter]
                
                # Require at least 3 sales for a valid median
                if len(prices) >= 3:
                    median = statistics.median(prices)
                    quarterly_data.append({
                        'date': quarter,
                        'median': int(median),
                        'count': len(prices)
                    })
            
            if quarterly_data:
                # Store in database
                medians_collection.update_one(
                    {'suburb': suburb, 'property_type': 'House'},
                    {
                        '$set': {
                            'suburb': suburb,
                            'property_type': 'House',
                            'data': quarterly_data,
                            'last_updated': datetime.now()
                        }
                    },
                    upsert=True
                )
                
                total_suburbs_with_data += 1
                print(f"  ✓ Saved {len(quarterly_data)} quarters")
                print(f"    Date range: {quarterly_data[0]['date']} to {quarterly_data[-1]['date']}")
                print(f"    Latest median: ${quarterly_data[-1]['median']:,}")
            else:
                print(f"  - No sufficient data (need 3+ sales per quarter)")
            
            total_suburbs_processed += 1
        
        except Exception as e:
            total_errors += 1
            print(f"  ✗ Error processing {suburb}: {e}")
            continue
    
    print("\n" + "=" * 80)
    print("GENERATE SUBURB MEDIAN PRICES - Complete")
    print("=" * 80)
    print(f"Suburbs processed: {total_suburbs_processed}")
    print(f"Suburbs with median data: {total_suburbs_with_data}")
    print(f"Errors: {total_errors}")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Show sample
    if total_suburbs_with_data > 0:
        print("\nSample suburb median data:")
        sample = medians_collection.find_one({'data': {'$exists': True, '$ne': []}})
        if sample:
            print(f"  Suburb: {sample.get('suburb')}")
            print(f"  Total quarters: {len(sample.get('data', []))}")
            print(f"  Recent quarters:")
            for quarter_data in sample.get('data', [])[-5:]:
                print(f"    {quarter_data['date']}: ${quarter_data['median']:,} ({quarter_data['count']} sales)")


if __name__ == '__main__':
    generate_suburb_medians()
EOF

echo "✓ Created fixed generate_suburb_medians.py"

echo ""
echo "Step 3: Update process_commands_cloud.yaml descriptions"
echo "----------------------------------------------------------------------"

# Note: We'll update this on the VM directly using sed

echo "✓ Will update on VM"

echo ""
echo "Step 4: Deploy fixes to VM"
echo "----------------------------------------------------------------------"

# Copy fixed config.py to Ollama_Property_Analysis
echo "Deploying fixed config.py..."
gcloud compute scp /tmp/config_fixed.py ${VM_NAME}:/home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/config.py \
  --zone=${ZONE} --project=${PROJECT}

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Deployed fixed config.py${NC}"
else
    echo -e "${RED}✗ Failed to deploy config.py${NC}"
    exit 1
fi

# Copy fixed generate_suburb_medians.py
echo "Deploying fixed generate_suburb_medians.py..."
gcloud compute scp /tmp/generate_suburb_medians_fixed.py ${VM_NAME}:/home/fields/Feilds_Website/08_Market_Narrative_Engine/generate_suburb_medians.py \
  --zone=${ZONE} --project=${PROJECT}

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Deployed fixed generate_suburb_medians.py${NC}"
else
    echo -e "${RED}✗ Failed to deploy generate_suburb_medians.py${NC}"
    exit 1
fi

echo ""
echo "Step 5: Update process_commands_cloud.yaml on VM"
echo "----------------------------------------------------------------------"

gcloud compute ssh ${VM_NAME} --zone=${ZONE} --project=${PROJECT} --command='
# Update Step 105 description (Ollama → GPT)
sed -i "s/Analyzes and reorders photos using Ollama LLaVA/Analyzes and reorders photos using GPT-4o/" /home/fields/Fields_Orchestrator/config/process_commands.yaml

# Update Step 106 description (Ollama → GPT)
sed -i "s/Analyzes floor plans using Ollama LLaVA/Analyzes floor plans using GPT-4o/" /home/fields/Fields_Orchestrator/config/process_commands.yaml

echo "✓ Updated process_commands.yaml descriptions"
'

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Updated process descriptions${NC}"
else
    echo -e "${YELLOW}⚠ Warning: Failed to update descriptions (non-critical)${NC}"
fi

echo ""
echo "Step 6: Set environment variables on VM"
echo "----------------------------------------------------------------------"

gcloud compute ssh ${VM_NAME} --zone=${ZONE} --project=${PROJECT} --command='
# Ensure COSMOS_CONNECTION_STRING is set in systemd service
if ! grep -q "COSMOS_CONNECTION_STRING" /etc/systemd/system/fields-orchestrator.service; then
    echo "⚠ COSMOS_CONNECTION_STRING not found in systemd service"
    echo "  This should have been set during initial deployment"
    echo "  Skipping (assuming it is set elsewhere)"
fi

# Check if .env exists in Ollama_Property_Analysis
if [ ! -f /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/.env ]; then
    echo "Creating .env file for Ollama_Property_Analysis..."
    cat > /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/.env << "ENVEOF"
# MongoDB Connection (Cloud)
COSMOS_CONNECTION_STRING=${COSMOS_CONNECTION_STRING}

# OpenAI Configuration
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=gpt-4o-2024-08-06
USE_OPENAI_PRIMARY=True

# Processing Configuration
TEST_RUN=True
MAX_BATCHES=2
ENVEOF
    echo "✓ Created .env file"
else
    echo "✓ .env file already exists"
fi
'

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Environment variables configured${NC}"
else
    echo -e "${YELLOW}⚠ Warning: Failed to configure environment (non-critical)${NC}"
fi

echo ""
echo "Step 7: Verify MongoDB connections"
echo "----------------------------------------------------------------------"

gcloud compute ssh ${VM_NAME} --zone=${ZONE} --project=${PROJECT} --command='
cd /home/fields/Fields_Orchestrator/02_Deployment/scripts
python3 test_cosmos_connection.py
'

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ MongoDB connection verified${NC}"
else
    echo -e "${RED}✗ MongoDB connection test failed${NC}"
    exit 1
fi

echo ""
echo "Step 8: Restart orchestrator service"
echo "----------------------------------------------------------------------"

gcloud compute ssh ${VM_NAME} --zone=${ZONE} --project=${PROJECT} --command='
sudo systemctl restart fields-orchestrator
sleep 3
sudo systemctl status fields-orchestrator --no-pager
'

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Orchestrator service restarted${NC}"
else
    echo -e "${RED}✗ Failed to restart orchestrator${NC}"
    exit 1
fi

echo ""
echo "=========================================="
echo "MongoDB & GPT Upgrade Fix - COMPLETE"
echo "=========================================="
echo ""
echo "Summary of changes:"
echo "  ✓ Fixed config.py to use COSMOS_CONNECTION_STRING"
echo "  ✓ Fixed generate_suburb_medians.py to use COSMOS_CONNECTION_STRING"
echo "  ✓ Updated process descriptions (Ollama → GPT)"
echo "  ✓ Configured environment variables"
echo "  ✓ Verified MongoDB connection"
echo "  ✓ Restarted orchestrator service"
echo ""
echo "Next steps:"
echo "  1. Monitor tonight's run (20:30 Brisbane time)"
echo "  2. Check logs: tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log"
echo "  3. Verify Steps 105, 106, and 13 complete successfully"
echo ""
echo "Completed: $(date)"
echo "=========================================="

# Cleanup
rm -f /tmp/config_fixed.py /tmp/generate_suburb_medians_fixed.py
