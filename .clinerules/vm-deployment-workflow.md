# VM Deployment Workflow for Fields Orchestrator
# Last Updated: 11/02/2026, 2:51 PM (Tuesday) - Brisbane Time
#
# Description: Step-by-step workflow for deploying the Fields Orchestrator to a GCP VM
# This workflow guides Cline (or any LLM) through the complete deployment process
#
# Edit History:
# - 11/02/2026 2:51 PM: Initial creation based on successful deployment experience

---

## Overview

This workflow deploys the Fields Property Data Orchestrator to a Google Cloud Platform VM. Follow these steps in order.

---

## Prerequisites

Before starting, ensure you have:
- [ ] GCP project ID: `fields-estate`
- [ ] VM name: `fields-orchestrator-vm`
- [ ] Zone: `australia-southeast1-b`
- [ ] Azure Cosmos DB connection string
- [ ] Local orchestrator code is up to date

---

## Step 1: Create or Access the VM

### 1.1 Check if VM exists
```bash
gcloud compute instances list --project=fields-estate --filter="name=fields-orchestrator-vm"
```

### 1.2 If VM doesn't exist, create it
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment/gcp
./01_create_vm.sh
```

### 1.3 Verify VM is running
```bash
gcloud compute instances describe fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --format="get(status)"
```

Expected output: `RUNNING`

---

## Step 2: Install System Dependencies

### 2.1 Update system packages
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo apt-get update && sudo apt-get upgrade -y'
```

### 2.2 Install Python 3 and pip
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo apt-get install -y python3 python3-pip python3-venv'
```

### 2.3 Install Chrome and ChromeDriver
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
sudo apt-get install -y wget unzip
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c "echo \"deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main\" >> /etc/apt/sources.list.d/google-chrome.list"
sudo apt-get update
sudo apt-get install -y google-chrome-stable
'
```

---

## Step 3: Install Python Dependencies

### 3.1 Install ALL required Python packages in system Python

**CRITICAL**: Install all packages in one command to avoid dependency conflicts:

```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo pip3 install pymongo python-dotenv pandas numpy scipy python-dateutil scikit-learn selenium beautifulsoup4 lxml webdriver-manager'
```

### 3.2 Verify all packages are installed
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='python3 -c "
modules = [\"pymongo\", \"dotenv\", \"pandas\", \"numpy\", \"scipy\", \"dateutil\", \"sklearn\", \"selenium\", \"bs4\", \"lxml\", \"webdriver_manager\"]
missing = []
for mod in modules:
    try:
        __import__(mod)
        print(f\"✅ {mod}\")
    except ImportError:
        print(f\"❌ {mod} - NOT FOUND\")
        missing.append(mod)
if missing:
    print(f\"\nMissing: {missing}\")
    exit(1)
else:
    print(\"\n✅ All dependencies installed!\")
"'
```

Expected: All modules show ✅

---

## Step 4: Deploy Orchestrator Code

### 4.1 Create directory structure
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
mkdir -p /home/fields/Fields_Orchestrator
mkdir -p /home/fields/Property_Data_Scraping
'
```

### 4.2 Copy orchestrator code
```bash
cd /Users/projects/Documents/Fields_Orchestrator
gcloud compute scp --recurse src config scripts state 02_Deployment fields-orchestrator-vm:/home/fields/Fields_Orchestrator/ --zone=australia-southeast1-b --project=fields-estate
```

### 4.3 Copy scraping scripts
```bash
cd /Users/projects/Documents/Property_Data_Scraping
gcloud compute scp --recurse 03_Gold_Coast fields-orchestrator-vm:/home/fields/Property_Data_Scraping/ --zone=australia-southeast1-b --project=fields-estate
```

---

## Step 5: Configure MongoDB Connection

### 5.1 Update settings.yaml with Cosmos DB connection string

**Option A: Edit directly on VM**
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate
# Then edit: nano /home/fields/Fields_Orchestrator/config/settings.yaml
```

**Option B: Use sed to replace**
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
cd /home/fields/Fields_Orchestrator/config
sed -i "s|uri: \"\${COSMOS_CONNECTION_STRING}\"|uri: \"mongodb://REDACTED:REDACTED@REDACTED.mongo.cosmos.azure.com:10255/"|" settings.yaml
'
```

### 5.2 Verify MongoDB connection
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='cd /home/fields/Fields_Orchestrator/02_Deployment/scripts && python3 test_cosmos_connection.py'
```

Expected: `✅ Successfully connected to MongoDB!`

---

## Step 6: Set Up Systemd Service

### 6.1 Create systemd service file
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
sudo tee /etc/systemd/system/fields-orchestrator.service > /dev/null <<EOF
[Unit]
Description=Fields Property Data Orchestrator
After=network.target

[Service]
Type=simple
User=fields
WorkingDirectory=/home/fields/Fields_Orchestrator
ExecStart=/usr/bin/python3 -u src/orchestrator_daemon.py
Restart=always
RestartSec=10
StandardOutput=append:/home/fields/Fields_Orchestrator/logs/orchestrator.log
StandardError=append:/home/fields/Fields_Orchestrator/logs/orchestrator.log

[Install]
WantedBy=multi-user.target
EOF
'
```

### 6.2 Enable and start service
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
sudo systemctl daemon-reload
sudo systemctl enable fields-orchestrator
sudo systemctl start fields-orchestrator
'
```

### 6.3 Verify service is running
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo systemctl status fields-orchestrator --no-pager'
```

Expected: `Active: active (running)`

---

## Step 7: Configure Trigger Time

### 7.1 Set trigger time in settings.yaml
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
cd /home/fields/Fields_Orchestrator/config
sed -i "s/trigger_time: \".*\"/trigger_time: \"20:30\"/" settings.yaml
grep "trigger_time:" settings.yaml
'
```

### 7.2 Restart service to apply changes
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo systemctl restart fields-orchestrator'
```

---

## Step 8: Test the Deployment

### 8.1 Trigger a manual run
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='cd /home/fields/Fields_Orchestrator && python3 src/orchestrator_daemon.py --run-now'
```

### 8.2 Monitor logs
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'
```

### 8.3 Check for errors
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='grep -E "(ERROR|FAILED)" /home/fields/Fields_Orchestrator/logs/orchestrator.log | tail -20'
```

---

## Step 9: Verify Scheduled Runs

### 9.1 Check next scheduled run time
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='tail -20 /home/fields/Fields_Orchestrator/logs/orchestrator.log | grep "Trigger Time"'
```

### 9.2 Verify service will restart on reboot
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='systemctl is-enabled fields-orchestrator'
```

Expected: `enabled`

---

## Troubleshooting

### If Python module is missing:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo pip3 install <module-name>'
```

### If MongoDB connection fails:
1. Check connection string in `config/settings.yaml`
2. Verify Cosmos DB is accessible from VM
3. Check firewall rules

### If service won't start:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
sudo journalctl -u fields-orchestrator -n 50 --no-pager
'
```

### If scraping fails:
1. Verify Chrome and ChromeDriver are installed
2. Check selenium and webdriver-manager are installed
3. Verify beautifulsoup4 and lxml are installed

---

## Complete Python Dependencies List

For reference, here are ALL required Python packages:

```
pymongo==4.16.0
python-dotenv==1.2.1
pandas==2.3.3
numpy==2.2.6
scipy==1.15.3
python-dateutil==2.9.0.post0
scikit-learn==1.7.2
selenium==4.40.0
beautifulsoup4==4.14.3
lxml==6.0.2
webdriver-manager==4.0.2
```

---

## Post-Deployment Checklist

- [ ] VM is running
- [ ] All Python dependencies installed
- [ ] MongoDB connection working
- [ ] Systemd service enabled and running
- [ ] Trigger time configured
- [ ] Manual test run successful
- [ ] Logs are being written
- [ ] No critical errors in logs
- [ ] Service will restart on reboot

---

## Maintenance Commands

### View logs:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'
```

### Restart service:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo systemctl restart fields-orchestrator'
```

### Check service status:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo systemctl status fields-orchestrator --no-pager'
```

### Update code:
```bash
cd /Users/projects/Documents/Fields_Orchestrator
gcloud compute scp --recurse src fields-orchestrator-vm:/home/fields/Fields_Orchestrator/ --zone=australia-southeast1-b --project=fields-estate
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo systemctl restart fields-orchestrator'
```

---

## Notes

- Always install Python packages in system Python (not venv) since scripts use `python3` directly
- The orchestrator runs as a systemd service and will auto-restart on failure
- Logs rotate automatically (configured in orchestrator code)
- The VM should be in the same region as Cosmos DB for best performance
- Chrome and ChromeDriver versions must be compatible
