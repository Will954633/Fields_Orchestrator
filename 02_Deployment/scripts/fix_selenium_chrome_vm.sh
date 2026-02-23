#!/bin/bash
# Fix Selenium Chrome DevToolsActivePort Error on VM
# Last Updated: 12/02/2026, 6:34 AM (Wednesday) - Brisbane Time
#
# Description: Fixes the DevToolsActivePort error that occurs when running Chrome/Selenium on GCP VM
# This error happens because Chrome can't create its DevTools port file in headless mode without proper configuration
#
# Root Cause: Chrome needs specific flags and environment setup to run in headless mode on Linux servers
# Solution: Configure Chrome options with proper flags and ensure display/sandbox settings are correct

set -e

PROJECT_ID="fields-estate"
VM_NAME="fields-orchestrator-vm"
ZONE="australia-southeast1-b"

echo "=========================================="
echo "Fixing Selenium Chrome DevToolsActivePort Error"
echo "=========================================="
echo ""

# Step 1: Install Xvfb (virtual display) if not already installed
echo "Step 1: Installing Xvfb (virtual display)..."
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
sudo apt-get update
sudo apt-get install -y xvfb
'

# Step 2: Create Chrome options configuration file
echo ""
echo "Step 2: Creating Chrome options configuration..."
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
cat > /tmp/chrome_options.py << "EOF"
"""
Chrome Options Configuration for Headless Mode on Linux Server
This configuration fixes the DevToolsActivePort error
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import os

def get_chrome_options():
    """
    Returns Chrome options configured for headless mode on Linux server
    """
    chrome_options = Options()
    
    # Essential flags for headless mode on Linux
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
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Disable logging
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    # Set download directory
    prefs = {
        "download.default_directory": "/tmp",
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    return chrome_options

def create_chrome_driver():
    """
    Creates and returns a Chrome WebDriver instance with proper configuration
    """
    chrome_options = get_chrome_options()
    
    # Create service with explicit path (optional)
    service = Service()
    
    # Create driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Set timeouts
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(10)
    
    return driver

# Example usage
if __name__ == "__main__":
    print("Testing Chrome configuration...")
    driver = create_chrome_driver()
    print("✅ Chrome driver created successfully!")
    driver.get("https://www.google.com")
    print(f"✅ Page loaded: {driver.title}")
    driver.quit()
    print("✅ Chrome driver closed successfully!")
EOF
'

# Step 3: Update monitor_sold_properties.py to use new Chrome options
echo ""
echo "Step 3: Updating monitor_sold_properties.py with fixed Chrome options..."
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold

# Backup original file
cp monitor_sold_properties.py monitor_sold_properties.py.backup_$(date +%Y%m%d_%H%M%S)

# Update the Chrome options in the file
python3 << "PYTHON_SCRIPT"
import re

# Read the file
with open("monitor_sold_properties.py", "r") as f:
    content = f.read()

# Find and replace the Chrome options section
# Look for the setup_driver function
pattern = r"def setup_driver\(\):.*?return driver"
replacement = """def setup_driver():
    \"\"\"Set up Chrome driver with options for headless mode on Linux server\"\"\"
    chrome_options = Options()
    
    # Essential flags for headless mode on Linux
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
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Disable logging
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    # Create service
    service = Service()
    
    # Create driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(10)
    
    return driver"""

# Replace the function
content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Write back
with open("monitor_sold_properties.py", "w") as f:
    f.write(content)

print("✅ Updated monitor_sold_properties.py with fixed Chrome options")
PYTHON_SCRIPT
'

# Step 4: Test the Chrome configuration
echo ""
echo "Step 4: Testing Chrome configuration..."
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
cd /tmp
python3 chrome_options.py
'

# Step 5: Test the sold property monitor
echo ""
echo "Step 5: Testing sold property monitor with new Chrome options..."
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold
python3 -c "
from monitor_sold_properties import setup_driver
print(\"Testing monitor_sold_properties Chrome setup...\")
driver = setup_driver()
print(\"✅ Chrome driver created successfully!\")
driver.get(\"https://www.realestate.com.au\")
print(f\"✅ Page loaded: {driver.title}\")
driver.quit()
print(\"✅ Chrome driver closed successfully!\")
"
'

echo ""
echo "=========================================="
echo "✅ Selenium Chrome Fix Complete!"
echo "=========================================="
echo ""
echo "The DevToolsActivePort error should now be resolved."
echo "The sold property monitor should now be able to run successfully."
echo ""
echo "Next steps:"
echo "1. Monitor will run automatically at scheduled time"
echo "2. Check logs: tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log"
echo "3. Or trigger manually: cd /home/fields/Fields_Orchestrator && python3 src/orchestrator_daemon.py --run-now"
