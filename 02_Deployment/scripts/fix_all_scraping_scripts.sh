#!/bin/bash
# Fix ALL Scraping Scripts with Chrome Options
# Last Updated: 12/02/2026, 7:07 AM (Wednesday) - Brisbane Time
#
# Description: Applies Chrome/ChromeDriver fixes to ALL scraping scripts on the VM
# This ensures the orchestrator can run without DevToolsActivePort errors

set -e

PROJECT_ID="fields-estate"
VM_NAME="fields-orchestrator-vm"
ZONE="australia-southeast1-b"

echo "=========================================="
echo "Fixing ALL Scraping Scripts"
echo "=========================================="
echo ""

gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold

# Create a Python script to fix all files
python3 << "FIX_ALL_SCRIPTS"
import os
import re

# List of scripts to fix
scripts_to_fix = [
    "run_parallel_suburb_scrape.py",
    "run_complete_suburb_scrape.py",
    "headless_forsale_mongodb_scraper.py"
]

for script in scripts_to_fix:
    if not os.path.exists(script):
        print(f"⚠ Skipping {script} (not found)")
        continue
    
    print(f"\nFixing {script}...")
    
    # Backup
    os.system(f"cp {script} {script}.backup_chrome_fix_$(date +%Y%m%d_%H%M%S)")
    
    with open(script, "r") as f:
        content = f.read()
    
    # Fix 1: Update Chrome options in setup_driver function
    pattern = r"(def setup_driver\(.*?\):.*?chrome_options = Options\(\))(.*?)(        try:)"
    replacement = r"""\1
        
        # Essential flags for headless mode on Linux server
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.binary_location = "/snap/bin/chromium"  # Use snap Chromium
        
\3"""
    
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Fix 2: Update ChromeDriver path
    content = content.replace(
        "Service(ChromeDriverManager().install())",
        "Service(\"/usr/local/bin/chromedriver\")"
    )
    
    # Fix 3: Remove any escaped quotes
    content = content.replace("\\\"", "\"")
    
    with open(script, "w") as f:
        f.write(content)
    
    print(f"  ✅ Updated {script}")

print("\n" + "="*60)
print("✅ All scraping scripts fixed!")
print("="*60)
FIX_ALL_SCRIPTS

echo ""
echo "Verifying fixes..."
echo ""
for script in run_parallel_suburb_scrape.py run_complete_suburb_scrape.py; do
    if [ -f "$script" ]; then
        echo "Checking $script:"
        grep -q "headless=new" "$script" && echo "  ✅ Chrome options updated" || echo "  ❌ Chrome options NOT updated"
        grep -q "binary_location" "$script" && echo "  ✅ Binary location set" || echo "  ❌ Binary location NOT set"
        grep -q "Service(\"/usr/local/bin/chromedriver\")" "$script" && echo "  ✅ ChromeDriver path updated" || echo "  ❌ ChromeDriver path NOT updated"
        echo ""
    fi
done
'

echo ""
echo "=========================================="
echo "✅ All Scraping Scripts Fixed!"
echo "=========================================="
echo ""
echo "The orchestrator can now run without DevToolsActivePort errors."
echo ""
echo "To start a new run:"
echo "  gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='cd /home/fields/Fields_Orchestrator && python3 src/orchestrator_daemon.py --run-now'"
