# Sold Monitor Isolated Test Setup
# Last Updated: 12/02/2026, 10:08 AM (Wednesday) - Brisbane Time
#
# Description: Documentation for the isolated sold monitor test running on VM
# This test runs the sold monitor independently from the orchestrator to identify
# and fix any errors under exact production conditions.

---

## Test Status

**Status**: ✅ RUNNING  
**Started**: 12/02/2026, 10:08 AM (Brisbane Time)  
**Process ID**: 35262  
**VM**: fields-orchestrator-vm  
**Mode**: Test mode (first 10 properties per suburb, 10 suburbs total)  
**Concurrency**: 2 suburbs at a time, 1 property at a time per suburb  

---

## What Was Done

### 1. Stopped Orchestrator Service
```bash
sudo systemctl stop fields-orchestrator
```
- Stopped the running orchestrator daemon to prevent interference
- This ensures the sold monitor runs in complete isolation

### 2. Created Isolated Test Script
Created `/home/fields/Fields_Orchestrator/scripts/test_sold_monitor_isolated.sh`:
- Runs sold monitor in test mode (10 properties per suburb)
- Captures all output to timestamped log file
- Automatically checks for errors at completion
- Conservative settings: 2 concurrent suburbs, sequential property processing

### 3. Deployed and Started Test
```bash
# Deployed script to VM
gcloud compute scp scripts/test_sold_monitor_isolated.sh fields-orchestrator-vm:/home/fields/Fields_Orchestrator/scripts/

# Made executable and started in background
chmod +x /home/fields/Fields_Orchestrator/scripts/test_sold_monitor_isolated.sh
nohup /home/fields/Fields_Orchestrator/scripts/test_sold_monitor_isolated.sh > /home/fields/sold_monitor_test.log 2>&1 &
```

---

## Monitoring Commands

### Check if process is still running
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='ps aux | grep monitor_sold_properties | grep -v grep'
```

### View live progress (last 50 lines)
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='tail -50 /home/fields/sold_monitor_test.log'
```

### Follow live output (real-time)
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='tail -f /home/fields/sold_monitor_test.log'
```

### Check for errors
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='grep -i "error\|exception\|failed\|traceback" /home/fields/sold_monitor_test.log | tail -20'
```

### View detailed log file (in scraping directory)
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='ls -lh /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/logs/sold_monitor_isolated_test_*.log'
```

### Check process status
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='ps -p 35262 -o pid,etime,cmd'
```

---

## Expected Behavior

### Test Configuration
- **Suburbs**: First 10 suburbs from gold_coast_suburbs.json
- **Properties per suburb**: First 10 properties
- **Total properties**: ~100 properties (10 suburbs × 10 properties)
- **Concurrency**: 2 suburbs running simultaneously
- **Processing**: Sequential (1 property at a time per suburb)

### Estimated Duration
- **Per property**: ~10-15 seconds (page load + analysis)
- **Per suburb**: ~2-3 minutes (10 properties)
- **Total test**: ~15-20 minutes (with 2 concurrent suburbs)

### Success Indicators
- ✅ No Python exceptions or tracebacks
- ✅ Chrome/ChromeDriver starts successfully
- ✅ MongoDB connections work
- ✅ Properties are checked and moved if sold
- ✅ Process completes without hanging

### Failure Indicators
- ❌ Python import errors
- ❌ ChromeDriver/Selenium errors
- ❌ MongoDB connection errors
- ❌ Process hangs or times out
- ❌ Zombie processes left behind

---

## Next Steps After Completion

### 1. Retrieve and Analyze Logs
```bash
# Get the main test log
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='cat /home/fields/sold_monitor_test.log'

# Get the detailed monitor log
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='cat /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/logs/sold_monitor_isolated_test_*.log'
```

### 2. Check for Errors
Look for:
- Import errors (missing Python modules)
- ChromeDriver errors (version mismatch, path issues)
- MongoDB errors (connection, authentication, retryWrites)
- Selenium errors (timeouts, element not found)
- Process errors (zombie processes, hangs)

### 3. Fix Identified Errors
For each error found:
1. Identify root cause
2. Create fix script or update code
3. Deploy fix to VM
4. Re-run test
5. Verify fix worked

### 4. Iterate Until Clean
Repeat the test → analyze → fix → re-test cycle until:
- No errors in logs
- All properties processed successfully
- No zombie processes
- Clean exit code

### 5. Document Final Configuration
Once working perfectly:
- Document all fixes applied
- Update deployment documentation
- Update orchestrator integration
- Re-enable orchestrator service

---

## Common Issues and Fixes

### Issue: ChromeDriver not found
**Fix**:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
which chromedriver
ls -l /usr/bin/chromedriver
'
```

### Issue: MongoDB connection fails
**Fix**:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
cd /home/fields/Fields_Orchestrator/02_Deployment/scripts && python3 test_cosmos_connection.py
'
```

### Issue: Missing Python modules
**Fix**:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
sudo pip3 install [module-name]
'
```

### Issue: Process hangs
**Fix**:
```bash
# Kill the process
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
kill -9 35262
pkill -f monitor_sold_properties
'
```

### Issue: Zombie ChromeDriver processes
**Fix**:
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
pkill -f chromedriver
pkill -f chrome
'
```

---

## Test Completion Checklist

When the test finishes, verify:

- [ ] Process completed (PID 35262 no longer running)
- [ ] Exit code is 0 (success)
- [ ] No errors in `/home/fields/sold_monitor_test.log`
- [ ] No errors in detailed log file
- [ ] No zombie ChromeDriver processes
- [ ] MongoDB data updated correctly
- [ ] All suburbs processed
- [ ] Summary shows properties checked/sold

---

## Restart Orchestrator After Testing

Once testing is complete and all issues are fixed:

```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='
sudo systemctl start fields-orchestrator
sudo systemctl status fields-orchestrator
'
```

---

## Notes

- The test runs in **isolation** - no other processes interfere
- Uses **exact production environment** - same VM, same MongoDB, same Chrome
- **Conservative settings** - slow and safe to catch all errors
- **Comprehensive logging** - captures everything for analysis
- **Iterative approach** - fix errors one by one until perfect

---

## Contact

When the test completes, let Cline know and provide:
1. Whether the process is still running or completed
2. Any visible errors in the output
3. The exit code (if completed)

Cline will then analyze the logs and fix any issues found.
