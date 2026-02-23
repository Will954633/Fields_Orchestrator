# Azure Cosmos DB Setup Guide (MongoDB API)
# Last Edit: 07/02/2026, 6:28 PM (Wednesday) - Brisbane Time
#
# Step-by-step guide for setting up Azure Cosmos DB with MongoDB API
# for the Fields Property Data Orchestrator.

## Prerequisites

### 1. Install Azure CLI
```bash
brew install azure-cli
```

### 2. Login to Azure
```bash
az login
```
This opens a browser window. Sign in with your Azure account.

### 3. Set your subscription
```bash
az account set --subscription "bd82ca68-9e1e-4ad8-b617-11f087ae9ef2"
```

### 4. Verify
```bash
az account show --query "{name:name, id:id}" --output table
```

## Option A: Automated Setup (Recommended)

```bash
# 1. Copy .env template
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && cp .env.template .env

# 2. Run setup script (creates resource group, Cosmos DB account, databases)
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash azure/01_setup_cosmos_db.sh

# 3. Save connection string to .env
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash azure/02_get_connection_string.sh

# 4. Test connection
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 scripts/test_cosmos_connection.py

# 5. Create indexes
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 azure/03_create_indexes.py
```

## Option B: Manual Setup via Azure Portal

### Step 1: Create Resource Group
1. Go to https://portal.azure.com
2. Search for "Resource groups" → Click "+ Create"
3. Fill in:
   - **Subscription:** fieldsestate.com.au
   - **Resource group:** `fields-property-rg`
   - **Region:** `Australia East`
4. Click "Review + create" → "Create"

### Step 2: Create Cosmos DB Account
1. Search for "Azure Cosmos DB" → Click "+ Create"
2. Select **"Azure Cosmos DB for MongoDB"**
3. Fill in:
   - **Subscription:** fieldsestate.com.au
   - **Resource group:** `fields-property-rg`
   - **Account name:** `fields-property-cosmos`
   - **Location:** `Australia East`
   - **Capacity mode:** Provisioned throughput
   - **Apply Free Tier Discount:** ✅ **Yes** (IMPORTANT!)
   - **Version:** 4.2
4. Click "Review + create" → "Create"
5. ⏳ Wait 5-10 minutes for deployment

### Step 3: Get Connection String
1. Go to your Cosmos DB account
2. Left menu → "Connection strings"
3. Copy the **"PRIMARY CONNECTION STRING"**
4. Save it to your `.env` file as `COSMOS_CONNECTION_STRING`

### Step 4: Create Databases
1. In Cosmos DB account → "Data Explorer"
2. Click "New Database" for each:
   - `property_data`
   - `Gold_Coast_Currently_For_Sale`
   - `Gold_Coast`
   - `Gold_Coast_Recently_Sold`
3. For each, set throughput to **Shared (400 RU/s)** to stay within free tier

## Cosmos DB MongoDB API - Key Differences

### What Works (Same as MongoDB)
- ✅ `pymongo` driver (same connection code)
- ✅ CRUD operations (insert, find, update, delete)
- ✅ Most aggregation pipeline stages
- ✅ Indexes (single field, compound)
- ✅ `$match`, `$group`, `$sort`, `$project`, `$unwind`, `$lookup`
- ✅ `$set`, `$unset`, `$push`, `$pull`, `$addToSet`
- ✅ Bulk operations

### What's Different
- ⚠️ `retryWrites` must be `false` in connection string
- ⚠️ No `$graphLookup` support
- ⚠️ No text indexes (use `$regex` instead)
- ⚠️ Unique indexes must be created on empty collections
- ⚠️ `serverStatus` command has limited fields
- ⚠️ No `dbStats` command (use Azure metrics instead)
- ⚠️ Connection string uses port 10255 (not 27017)
- ⚠️ TLS/SSL required (always encrypted)

### Code Changes Required
The main change is the connection string. In your Python code:

```python
# OLD (local MongoDB)
client = MongoClient("mongodb://127.0.0.1:27017/")

# NEW (Cosmos DB) - just change the URI!
client = MongoClient(
    "mongodb://REDACTED:REDACTED@REDACTED.mongo.cosmos.azure.com:10255/",
    retryWrites=False,
    serverSelectionTimeoutMS=30000,
)
```

### RU/s (Request Units) Explained
- Every operation costs RU/s (like database "credits")
- Free tier: 1000 RU/s shared across all databases
- Simple read: ~1 RU
- Simple write: ~5 RU
- Aggregation: 10-100+ RU depending on complexity
- If you exceed 1000 RU/s, requests get throttled (HTTP 429)
- Monitor in Azure Portal → Metrics → "Total Request Units"

## Monitoring & Troubleshooting

### Check RU Usage
```bash
az monitor metrics list \
    --resource "/subscriptions/bd82ca68-9e1e-4ad8-b617-11f087ae9ef2/resourceGroups/fields-property-rg/providers/Microsoft.DocumentDB/databaseAccounts/fields-property-cosmos" \
    --metric "TotalRequestUnits" \
    --interval PT1H \
    --output table
```

### Common Issues

1. **429 Too Many Requests**
   - You're exceeding 1000 RU/s
   - Solution: Add retry logic with exponential backoff
   - Or increase throughput (costs money beyond free tier)

2. **Connection Timeout**
   - Ensure firewall allows your IP
   - Check: Cosmos DB → Networking → "Allow access from all networks"

3. **SSL/TLS Errors**
   - Ensure `ssl=true` in connection string
   - Use `pymongo>=4.0` which handles TLS automatically

4. **retryWrites Error**
   - Add `retryWrites=False` to MongoClient constructor
   - Or ensure `retrywrites=false` in connection string

brew install azure-cli && az login
