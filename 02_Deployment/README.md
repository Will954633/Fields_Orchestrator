# Fields Orchestrator - Cloud Deployment
# Last Edit: 07/02/2026, 6:25 PM (Wednesday) - Brisbane Time
#
# This directory contains all scripts and configuration for deploying the
# Fields Orchestrator to the cloud:
# - Azure Cosmos DB (MongoDB API) for database storage
# - Google Cloud VM (e2-medium) for running the orchestrator pipeline
#
# Architecture:
#   Google Cloud VM (australia-southeast1) → Azure Cosmos DB (australiaeast)
#   - VM runs the orchestrator, scrapers, Ollama, and enrichment scripts
#   - Cosmos DB replaces local MongoDB with cloud-hosted MongoDB-compatible API
#   - Connection via pymongo using Cosmos DB connection string (drop-in replacement)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  Google Cloud VM                         │
│              (australia-southeast1-b)                     │
│                  e2-medium (2 vCPU, 4GB)                │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Orchestrator  │  │  Scrapers    │  │   Ollama     │  │
│  │   Daemon      │  │  (Selenium)  │  │  (LLaVA)     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                  │                  │          │
│         └──────────────────┼──────────────────┘          │
│                            │                             │
│                     pymongo driver                       │
│                            │                             │
└────────────────────────────┼─────────────────────────────┘
                             │
                        TLS/SSL (port 10255)
                             │
┌────────────────────────────┼─────────────────────────────┐
│              Azure Cosmos DB (MongoDB API)                │
│                   (australiaeast)                         │
│                                                          │
│  ┌──────────────────┐  ┌──────────────────┐             │
│  │  property_data    │  │ Gold_Coast_       │             │
│  │  (main DB)        │  │ Currently_For_Sale│             │
│  └──────────────────┘  └──────────────────┘             │
│  ┌──────────────────┐  ┌──────────────────┐             │
│  │  Gold_Coast       │  │ Gold_Coast_       │             │
│  │  (master DB)      │  │ Recently_Sold     │             │
│  └──────────────────┘  └──────────────────┘             │
│                                                          │
│  Free Tier: 1000 RU/s + 25 GB storage                   │
└──────────────────────────────────────────────────────────┘
```

## Directory Structure

```
02_Deployment/
├── README.md                          # This file
├── .env.template                      # Environment variables template
├── azure/
│   ├── 01_setup_cosmos_db.sh          # Create Cosmos DB account & databases
│   ├── 02_get_connection_string.sh    # Retrieve connection string
│   ├── 03_create_indexes.py           # Create indexes on Cosmos DB collections
│   └── cosmos_db_guide.md             # Step-by-step Azure portal guide
├── gcp/
│   ├── 01_create_vm.sh                # Create Google Cloud VM
│   ├── 02_setup_vm.sh                 # Install dependencies on VM
│   ├── 03_deploy_code.sh              # Deploy orchestrator code to VM
│   ├── 04_start_orchestrator.sh       # Start the orchestrator on VM
│   └── vm_setup_guide.md              # Step-by-step GCP guide
├── migration/
│   ├── 01_export_local_mongodb.sh     # Export local MongoDB data
│   ├── 02_import_to_cosmos.sh         # Import data to Cosmos DB
│   ├── 03_verify_migration.py         # Verify data integrity after migration
│   └── migration_guide.md             # Step-by-step migration guide
├── config/
│   ├── settings_cloud.yaml            # Cloud version of settings.yaml
│   └── cosmos_db_config.py            # Cosmos DB connection helper
└── scripts/
    ├── test_cosmos_connection.py       # Test Cosmos DB connectivity
    ├── test_gcp_vm.sh                  # Test GCP VM connectivity
    └── health_check.py                 # Combined health check script
```

## ⚡ Quick Status Check

**To check if the orchestrator is running on the VM:**
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash scripts/check_vm_status.sh
```

This single command will show you:
- ✅ VM status (running/stopped)
- ✅ Orchestrator service status (active/inactive)
- ✅ Recent logs (last 20 lines)
- ✅ Today's run progress
- ✅ Any errors

---

## Quick Start

### Step 1: Set Up Azure Cosmos DB
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash azure/01_setup_cosmos_db.sh
```

### Step 2: Get Connection String
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash azure/02_get_connection_string.sh
```

### Step 3: Test Connection
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 scripts/test_cosmos_connection.py
```

### Step 4: Migrate Data
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash migration/01_export_local_mongodb.sh
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash migration/02_import_to_cosmos.sh
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 migration/03_verify_migration.py
```

### Step 5: Create Google Cloud VM
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/01_create_vm.sh
```

### Step 6: Deploy & Start
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/02_setup_vm.sh
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/03_deploy_code.sh
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/04_start_orchestrator.sh
```

## Cost Estimates

| Service | Tier | Monthly Cost |
|---------|------|-------------|
| Azure Cosmos DB | Free Tier (1000 RU/s, 25 GB) | **$0** |
| Google Cloud VM | e2-medium (2 vCPU, 4GB) | **~$25/mo** |
| **Total** | | **~$25/mo** |

> Note: Cosmos DB free tier covers 1000 RU/s and 25 GB. If you exceed this,
> costs start at ~$0.008/hour per 100 RU/s. Monitor usage in Azure Portal.
