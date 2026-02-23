#!/bin/bash
# ChromeDriver Complete Fix Script
# Last Edit: 16/02/2026, 7:00 AM (Sunday) — Brisbane Time
#
# Description: Comprehensive fix for ChromeDriver issues on VM
# This script reinstalls Chrome and ChromeDriver with proper compatibility

set -e

echo "=========================================="
echo "ChromeDriver Complete Fix"
echo "=========================================="
echo ""

# Step 1: Remove existing Chrome and ChromeDriver
echo "Step 1: Removing existing Chrome and ChromeDriver..."
sudo apt-get remove -y google-chrome-stable chromium-browser chromium-chromedriver 2>/dev/null || true
sudo rm -f /usr/bin/chromedriver /usr/local/bin/chromedriver 2>/dev/null || true
echo "✓ Removed existing installations"
echo ""

# Step 2: Update package lists
echo "Step 2: Updating package lists..."
sudo apt-get update
echo "✓ Package lists updated"
echo ""

# Step 3: Install Chrome Stable
echo "Step 3: Installing Chrome Stable..."
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
sudo apt-get update
sudo apt-get install -y google-chrome-stable
echo "✓ Chrome installed"
echo ""

# Step 4: Get Chrome version
echo "Step 4: Detecting Chrome version..."
CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f 1)
echo "Chrome major version: $CHROME_VERSION"
echo ""

# Step 5: Install matching ChromeDriver
echo "Step 5: Installing matching ChromeDriver..."
# Use webdriver-manager to handle version matching
sudo pip3 install --upgrade webdriver-manager
echo "✓ webdriver-manager installed"
echo ""

# Step 6: Verify Selenium is up to date
echo "Step 6: Updating Selenium..."
sudo pip3 install --upgrade selenium
echo "✓ Selenium updated"
echo ""

# Step 7: Test Chrome in headless mode
echo "Step 7: Testing Chrome in headless mode..."
google-chrome --headless --disable-gpu --no-sandbox --dump-dom https://www.google.com > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✓ Chrome headless test passed"
else
    echo "✗ Chrome headless test failed"
    exit 1
fi
echo ""

# Step 8: Create test script
echo "Step 8: Creating ChromeDriver test script..."
cat > /tmp/test_chromedriver.py << 'EOF'
#!/usr/bin/env python3
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

try:
    print("Testing ChromeDriver setup...")
    
    # Configure Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-extensions')
    
    # Use webdriver-manager to get the right ChromeDriver
    service = Service(ChromeDriverManager().install())
    
    # Create driver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Test navigation
    driver.get('https://www.google.com')
    title = driver.title
    
    driver.quit()
    
    print(f"✓ ChromeDriver test passed! Page title: {title}")
    sys.exit(0)
    
except Exception as e:
    print(f"✗ ChromeDriver test failed: {e}")
    sys.exit(1)
EOF

chmod +x /tmp/test_chromedriver.py
python3 /tmp/test_chromedriver.py

if [ $? -eq 0 ]; then
    echo "✓ ChromeDriver test script passed"
else
    echo "✗ ChromeDriver test script failed"
    exit 1
fi
echo ""

# Step 9: Clean up test script
rm -f /tmp/test_chromedriver.py
echo "✓ Test script cleaned up"
echo ""

echo "=========================================="
echo "✅ ChromeDriver Fix Complete!"
echo "=========================================="
echo ""
echo "Chrome version: $(google-chrome --version)"
echo "Selenium version: $(python3 -c 'import selenium; print(selenium.__version__)')"
echo ""
echo "Next steps:"
echo "1. Restart the orchestrator service"
echo "2. Monitor logs for ChromeDriver errors"
echo ""
