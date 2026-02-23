# VM MongoDB Connection Fix Summary
# Last Edit: 11/02/2026, 3:04 PM (Tuesday) - Brisbane Time
#
# Description: Complete summary of MongoDB connection issue and fix for deployed orchestrator

---

## Problem

The orchestrator on the GCP VM was unable to connect to Azure Cosmos DB. Scraping scripts were trying to connect to `localhost:27017` instead of the Azure Cosmos DB connection string.

### Root Cause

The scraping scripts use `os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')` which falls back to localhost if the `MONGODB_URI` environment variable is not set. The environment variable was not configured on the VM.

---

## Solution Implemented

### 1. Set MONGODB_URI Environment Variable

Added to `/etc/environment`:
```bash
export MONGODB_URI="mongodb://fields-property-cosmos:REDACTED
```

### 2. Updated Systemd Service

Created `/etc/systemd/system/fields-orchestrator.service` with:
- **User**: `projects` (the actual user on the VM)
- **WorkingDirectory**: `/home/fields/Fields_Orchestrator`
- **Environment**: MONGODB_URI set inline
- **ExecStart**: `/usr/bin/python3 -u src/orchestrator_daemon.py`
- **Logs**: `/home/fields/Fields_Orchestrator/logs/orchestrator.log`

### 3. Key Discoveries

- **User**: The VM user is `projects` (UID 1001), not `fields`
- **Directory**: Files are at `/home/fields/Fields_Orchestrator/` (owned by `projects`)
- **Connection Test**: Manual test with MONGODB_URI set successfully connected to Cosmos DB

---

## Test Results

### MongoDB Connection Test (Successful)
```bash
export MONGODB_URI="mongodb://fields-property-cosmos:..."
python3 /home/fields/test_mongodb_env.py
```

**Output:**
```
✅ Successfully connected to MongoDB!
Database: property_data
Collections: 13
Collection names: properties_for_sale, suburb_statistics, processing_status, image_descriptions, property_floorplan_interactive...
```

---

## Next Steps to Complete Fix

### 1. Ensure logs directory exists and has correct permissions
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
mkdir -p /home/fields/Fields_Orchestrator/logs
chmod 775 /home/fields/Fields_Orchestrator/logs
'
```

### 2. Reload systemd and restart service
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
sudo systemctl daemon-reload
sudo systemctl restart fields-orchestrator
sudo systemctl status fields-orchestrator --no-pager
'
```

### 3. Test manual run with environment variable
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
export MONGODB_URI="mongodb://fields-property-cosmos:REDACTED
cd /home/fields/Fields_Orchestrator
python3 src/orchestrator_daemon.py --run-now 2>&1 | head -50
'
```

---

## Files Modified

1. `/Users/projects/Documents/Fields_Orchestrator/02_Deployment/scripts/update_systemd_service.sh`
   - Updated to use correct user (`projects`) and path (`/home/fields/Fields_Orchestrator`)

2. `/Users/projects/Documents/Fields_Orchestrator/02_Deployment/scripts/test_mongodb_env.py`
   - Created test script to verify MongoDB connection with environment variable

---

## VM Configuration Details

- **VM Name**: fields-orchestrator-vm
- **Zone**: australia-southeast1-b
- **Project**: fields-estate
- **User**: projects (UID 1001, GID 1002)
- **Home Directory**: /home/projects
- **Orchestrator Path**: /home/fields/Fields_Orchestrator
- **Scraping Scripts**: /home/fields/Property_Data_Scraping

---

## Connection String Details

- **Service**: Azure Cosmos DB (MongoDB API)
- **Account**: fields-property-cosmos
- **Endpoint**: fields-property-cosmos.mongo.cosmos.azure.com:10255
- **SSL**: Required
- **Replica Set**: globaldb
- **Retry Writes**: false (Cosmos DB limitation)

---

## Status

- ✅ MongoDB connection string identified
- ✅ Environment variable solution implemented
- ✅ Systemd service file updated
- ✅ Connection test successful
- ⏳ Awaiting final service restart and orchestrator test
