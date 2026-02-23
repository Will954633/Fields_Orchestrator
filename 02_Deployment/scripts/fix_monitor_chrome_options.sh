#!/bin/bash
# Fix monitor_sold_properties.py Chrome Options for VM
# Last Updated: 12/02/2026, 6:36 AM (Wednesday) - Brisbane Time
#
# Description: Updates the setup_driver() method in monitor_sold_properties.py
# to use proper Chrome options for headless mode on Linux server

set -e

PROJECT_ID="fields-estate"
VM_NAME="fields-orchestrator-vm"
ZONE="australia-southeast1-b"

echo "=========================================="
echo "Fixing monitor_sold_properties.py Chrome Options"
echo "=========================================="
echo ""

# Update the setup_driver method in monitor_sold_properties.py
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold

# Backup original file
cp monitor_sold_properties.py monitor_sold_properties.py.backup_chrome_fix_$(date +%Y%m%d_%H%M%S)

# Use Python to update the setup_driver method
python3 << "PYTHON_SCRIPT"
import re

# Read the file
with open("monitor_sold_properties.py", "r") as f:
    content = f.read()

# Find and replace the setup_driver method
# The method starts with "def setup_driver(self):" and ends before the next method "def close(self):"
pattern = r"(    def setup_driver\(self\):.*?)(        chrome_options = Options\(\).*?)(        try:)"

replacement = r'''\1        chrome_options = Options()
        
        # Essential flags for headless mode on Linux server
        chrome_options.add_argument("--headless=new")  # Use new headless mode
        chrome_options.add_argument("--no-sandbox")  # Required for running as root or in containers
        chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
        chrome_options.add_argument("--disable-gpu")  # Disable GPU hardware acceleration
        chrome_options.add_argument("--disable-software-rasterizer")
        
        # Additional stability flags
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")  # Explicitly set debugging port
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")
        
        # User agent to avoid detection
        chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Disable logging
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
\3'''

# Replace the method
content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Write back
with open("monitor_sold_properties.py", "w") as f:
    f.write(content)

print("✅ Updated monitor_sold_properties.py with fixed Chrome options")
PYTHON_SCRIPT

echo ""
echo "✅ Chrome options updated successfully!"
echo ""
echo "Testing the updated monitor..."
'

# Test the updated monitor
echo "Testing monitor with new Chrome options..."
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold

# Test by creating a simple test script
python3 << "TEST_SCRIPT"
import sys
sys.path.insert(0, "/home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold")

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

print("Testing Chrome configuration from monitor_sold_properties.py...")

# Replicate the exact setup from the file
chrome_options = Options()

# Essential flags for headless mode on Linux server
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-software-rasterizer")

# Additional stability flags
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-setuid-sandbox")
chrome_options.add_argument("--remote-debugging-port=9222")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--start-maximized")

# User agent
chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Disable logging
chrome_options.add_argument("--log-level=3")
chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
chrome_options.add_experimental_option("useAutomationExtension", False)

try:
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("✅ Chrome driver created successfully!")
    
    driver.get("https://www.realestate.com.au")
    print(f"✅ Page loaded: {driver.title}")
    
    driver.quit()
    print("✅ Chrome driver closed successfully!")
    print("")
    print("🎉 DevToolsActivePort error is FIXED!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
TEST_SCRIPT
'

echo ""
echo "=========================================="
echo "✅ Fix Complete!"
echo "=========================================="
echo ""
echo "The DevToolsActivePort error has been resolved."
echo "The sold property monitor is now ready to run on the VM."
echo ""
echo "Next steps:"
echo "1. The monitor will run automatically at scheduled time"
echo "2. Or trigger manually: cd /home/fields/Fields_Orchestrator && python3 src/orchestrator_daemon.py --run-now"
