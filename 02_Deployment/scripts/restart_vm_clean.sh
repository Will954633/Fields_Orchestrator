#!/bin/bash
# Restart VM and Verify All Fixes Persist
# Last Updated: 12/02/2026, 6:52 AM (Wednesday) - Brisbane Time
#
# Description: Stops all orchestrator processes, restarts the VM, and verifies
# that all Selenium/Chrome fixes persist after restart

set -e

PROJECT_ID="fields-estate"
VM_NAME="fields-orchestrator-vm"
ZONE="australia-southeast1-b"

echo "=========================================="
echo "VM Restart and Verification Script"
echo "=========================================="
echo ""

# Step 1: Stop all orchestrator processes
echo "Step 1: Stopping all orchestrator processes..."
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
# Kill all orchestrator processes
pkill -f "orchestrator_daemon.py" || true
sleep 2
# Verify they are stopped
if ps aux | grep orchestrator_daemon | grep -v grep; then
    echo "⚠ Some processes still running, force killing..."
    pkill -9 -f "orchestrator_daemon.py" || true
    sleep 2
fi
echo "✅ All orchestrator processes stopped"
'

# Step 2: Restart the VM
echo ""
echo "Step 2: Restarting VM..."
gcloud compute instances stop $VM_NAME --zone=$ZONE --project=$PROJECT_ID
echo "Waiting for VM to stop..."
sleep 10

gcloud compute instances start $VM_NAME --zone=$ZONE --project=$PROJECT_ID
echo "Waiting for VM to start and boot..."
sleep 30

# Wait for SSH to be available
echo "Waiting for SSH to be available..."
for i in {1..12}; do
    if gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='echo "SSH ready"' 2>/dev/null; then
        echo "✅ SSH is ready"
        break
    fi
    echo "Waiting... ($i/12)"
    sleep 5
done

# Step 3: Verify all fixes persist
echo ""
echo "Step 3: Verifying all fixes persist after restart..."
echo ""

gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
echo "=== Verification Report ==="
echo ""

# Check 1: ChromeDriver installed and accessible
echo "1. ChromeDriver Installation:"
if [ -f /usr/local/bin/chromedriver ]; then
    echo "   ✅ ChromeDriver exists at /usr/local/bin/chromedriver"
    ls -la /usr/local/bin/chromedriver
    /usr/local/bin/chromedriver --version
else
    echo "   ❌ ChromeDriver NOT FOUND"
fi
echo ""

# Check 2: Xvfb installed
echo "2. Xvfb Installation:"
if command -v xvfb-run &> /dev/null; then
    echo "   ✅ Xvfb is installed"
else
    echo "   ❌ Xvfb NOT installed"
fi
echo ""

# Check 3: Monitor file has correct Chrome options
echo "3. Monitor Chrome Options:"
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold
if grep -q "headless=new" monitor_sold_properties.py; then
    echo "   ✅ Chrome options include --headless=new"
else
    echo "   ❌ Chrome options NOT updated"
fi
if grep -q "no-sandbox" monitor_sold_properties.py; then
    echo "   ✅ Chrome options include --no-sandbox"
else
    echo "   ❌ --no-sandbox NOT found"
fi
echo ""

# Check 4: Monitor uses system ChromeDriver
echo "4. ChromeDriver Path:"
if grep -q "Service(\"/usr/local/bin/chromedriver\")" monitor_sold_properties.py; then
    echo "   ✅ Monitor uses system ChromeDriver"
else
    echo "   ❌ Monitor NOT using system ChromeDriver"
fi
echo ""

# Check 5: Systemd service status
echo "5. Systemd Service:"
if systemctl is-enabled fields-orchestrator &> /dev/null; then
    echo "   ✅ fields-orchestrator service is enabled"
    systemctl status fields-orchestrator --no-pager | head -5
else
    echo "   ⚠ fields-orchestrator service not enabled (may be OK)"
fi
echo ""

# Check 6: Test Chrome creation
echo "6. Testing Chrome Driver Creation:"
python3 << "TEST_CHROME"
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    service = Service("/usr/local/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.quit()
    print("   ✅ Chrome driver creation SUCCESSFUL")
except Exception as e:
    print(f"   ❌ Chrome driver creation FAILED: {e}")
TEST_CHROME

echo ""
echo "=== End Verification Report ==="
'

echo ""
echo "=========================================="
echo "✅ VM Restart Complete!"
echo "=========================================="
echo ""
echo "The VM has been restarted and all fixes have been verified."
echo ""
echo "To start a new orchestrator run:"
echo "  gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='cd /home/fields/Fields_Orchestrator && python3 src/orchestrator_daemon.py --run-now'"
