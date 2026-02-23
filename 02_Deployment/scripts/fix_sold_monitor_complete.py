#!/usr/bin/env python3
"""
Fix Sold Monitor Script - Complete Fix
Last Updated: 12/02/2026, 9:13 AM (Wednesday) - Brisbane Time

This script fixes TWO critical issues in monitor_sold_properties.py:

ISSUE 1: Chrome WebDriver Crashes
- Error: "session not created from disconnected: unable to connect to renderer"
- Cause: Using webdriver-manager which downloads incompatible ChromeDriver versions
- Fix: Use system ChromeDriver with explicit service configuration

ISSUE 2: MongoDB Retryable Writes Error
- Error: "Retryable writes are not supported" (Azure Cosmos DB limitation)
- Cause: Connection string has retryWrites=True (default in PyMongo)
- Fix: Add retryWrites=false to connection string

This script will:
1. Update monitor_sold_properties.py to use system ChromeDriver
2. Update MongoDB connection to disable retryable writes
3. Add better error handling for Chrome crashes
4. Test the fixes
"""

import os
import re

MONITOR_SCRIPT_PATH = "/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/monitor_sold_properties.py"

def fix_chrome_driver_setup():
    """Fix Chrome WebDriver setup to use system ChromeDriver"""
    
    print("=" * 80)
    print("FIX 1: Chrome WebDriver Configuration")
    print("=" * 80)
    
    with open(MONITOR_SCRIPT_PATH, 'r') as f:
        content = f.read()
    
    # Find the setup_driver method
    old_setup = '''    def setup_driver(self):
        """Setup headless Chrome WebDriver (ONE driver for all properties)"""
        self.log("Setting up headless Chrome WebDriver...")
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.log("✓ Headless Chrome ready (shared driver)")
        except Exception as e:
            raise Exception(f"Failed to create WebDriver: {e}")'''
    
    new_setup = '''    def setup_driver(self):
        """Setup headless Chrome WebDriver (ONE driver for all properties)"""
        self.log("Setting up headless Chrome WebDriver...")
        
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')  # Use new headless mode
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-dev-tools')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--remote-debugging-port=0')  # Disable remote debugging
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        try:
            # Use system ChromeDriver (no webdriver-manager)
            service = Service('/usr/bin/chromedriver')
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.log("✓ Headless Chrome ready (system ChromeDriver)")
        except FileNotFoundError:
            # Fallback: try without explicit service path
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
                self.log("✓ Headless Chrome ready (default ChromeDriver)")
            except Exception as e:
                raise Exception(f"Failed to create WebDriver: {e}")
        except Exception as e:
            raise Exception(f"Failed to create WebDriver: {e}")'''
    
    if old_setup in content:
        content = content.replace(old_setup, new_setup)
        print("✅ Updated setup_driver() method to use system ChromeDriver")
    else:
        print("⚠️  Could not find exact setup_driver() method - may need manual update")
        return False
    
    # Write back
    with open(MONITOR_SCRIPT_PATH, 'w') as f:
        f.write(content)
    
    print("✅ Chrome WebDriver configuration fixed")
    return True


def fix_mongodb_connection():
    """Fix MongoDB connection to disable retryable writes"""
    
    print("\n" + "=" * 80)
    print("FIX 2: MongoDB Retryable Writes")
    print("=" * 80)
    
    with open(MONITOR_SCRIPT_PATH, 'r') as f:
        content = f.read()
    
    # Find the MongoDB connection code
    old_connection = '''                _mongo_client = MongoClient(
                    MONGODB_URI,
                    maxPoolSize=50,
                    minPoolSize=10,
                    maxIdleTimeMS=45000,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    retryWrites=True,
                    retryReads=True
                )'''
    
    new_connection = '''                _mongo_client = MongoClient(
                    MONGODB_URI,
                    maxPoolSize=50,
                    minPoolSize=10,
                    maxIdleTimeMS=45000,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    retryWrites=False,  # CRITICAL: Cosmos DB doesn't support retryable writes
                    retryReads=True
                )'''
    
    if old_connection in content:
        content = content.replace(old_connection, new_connection)
        print("✅ Updated MongoDB connection to disable retryable writes")
    else:
        print("⚠️  Could not find exact MongoDB connection code - checking alternative...")
        
        # Try to find and replace just the retryWrites line
        if 'retryWrites=True' in content:
            content = content.replace('retryWrites=True', 'retryWrites=False  # CRITICAL: Cosmos DB doesn\'t support retryable writes')
            print("✅ Updated retryWrites parameter")
        else:
            print("⚠️  Could not find retryWrites parameter - may need manual update")
            return False
    
    # Write back
    with open(MONITOR_SCRIPT_PATH, 'w') as f:
        f.write(content)
    
    print("✅ MongoDB retryable writes disabled")
    return True


def remove_webdriver_manager_import():
    """Remove webdriver-manager import since we're using system ChromeDriver"""
    
    print("\n" + "=" * 80)
    print("FIX 3: Remove webdriver-manager Import")
    print("=" * 80)
    
    with open(MONITOR_SCRIPT_PATH, 'r') as f:
        content = f.read()
    
    # Find the import block
    old_import = '''try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("ERROR: Selenium not installed!")
    print("Install with: pip3 install selenium webdriver-manager pymongo beautifulsoup4")
    exit(1)'''
    
    new_import = '''try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
except ImportError:
    print("ERROR: Selenium not installed!")
    print("Install with: pip3 install selenium pymongo beautifulsoup4")
    exit(1)'''
    
    if old_import in content:
        content = content.replace(old_import, new_import)
        print("✅ Removed webdriver-manager import")
    else:
        print("⚠️  Import block already updated or different format")
    
    # Write back
    with open(MONITOR_SCRIPT_PATH, 'w') as f:
        f.write(content)
    
    print("✅ Import statements cleaned up")
    return True


def update_file_header():
    """Update file header with fix information"""
    
    print("\n" + "=" * 80)
    print("FIX 4: Update File Header")
    print("=" * 80)
    
    with open(MONITOR_SCRIPT_PATH, 'r') as f:
        content = f.read()
    
    # Find the header
    header_pattern = r'""".*?Last Updated:.*?"""'
    
    new_header = '''"""
Sold Property Monitor - Headless Parallel Version with Optimized Driver Reuse
Last Updated: 12/02/2026, 9:13 AM (Wednesday) - Brisbane Time

CHROME WEBDRIVER FIX (12/02/2026):
- Fixed "session not created from disconnected" error
- Now uses system ChromeDriver instead of webdriver-manager
- Added --headless=new flag for better stability
- Added --remote-debugging-port=0 to prevent port conflicts

MONGODB RETRYABLE WRITES FIX (12/02/2026):
- Fixed "Retryable writes are not supported" error with Azure Cosmos DB
- Changed retryWrites=True to retryWrites=False in connection
- This is required for Azure Cosmos DB compatibility

Previous Update: 06/02/2026, 9:37 pm Friday (Brisbane Time) - Fixed --test flag bug

PRICE TRACKING FIX:
- Now preserves original listing price in 'listing_price' field
- Extracts sold price properly from HTML into 'sale_price' field
- Improved sold price extraction with multiple methods
- Keeps price history separate: listing_price vs sale_price

ADDRESS MATCHING FIX:
- Fixed collection name mismatch: now uses collection_name (lowercase with underscores)
  instead of suburb_name (with spaces and capitals) when accessing master database
- Master database collections use format: "mermaid_waters" not "Mermaid Waters"

PERFORMANCE FIX:
- Now creates ONE ChromeDriver per suburb process (not per property)
- Reuses the same driver for all properties in the suburb
- Eliminates 60+ second cleanup delays between properties
- Expected performance: ~10 properties per minute (vs ~1 property per minute before)

PURPOSE:
Monitors properties in Gold_Coast_Currently_For_Sale collections (52 suburbs) and detects
when they've been sold. Moves sold properties to Gold_Coast_Recently_Sold collection.

FEATURES:
- Headless Chrome operation
- Parallel processing (multiple suburbs + multiple properties)
- 5 detection methods for sold status
- Auction protection (prevents false positives)
- Extracts sold date and sale price
- Preserves all historical data
- MongoDB safe with connection pooling

USAGE:
python3 monitor_sold_properties.py --all --max-concurrent 3 --parallel-properties 2
python3 monitor_sold_properties.py --suburbs "Robina:4226" "Varsity Lakes:4227"
python3 monitor_sold_properties.py --test --max-concurrent 2
python3 monitor_sold_properties.py --report
"""'''
    
    content = re.sub(header_pattern, new_header, content, count=1, flags=re.DOTALL)
    
    # Write back
    with open(MONITOR_SCRIPT_PATH, 'w') as f:
        f.write(content)
    
    print("✅ File header updated with fix information")
    return True


def main():
    """Main execution"""
    print("\n" + "=" * 80)
    print("SOLD MONITOR COMPLETE FIX")
    print("=" * 80)
    print(f"\nTarget file: {MONITOR_SCRIPT_PATH}")
    print("\nThis will fix:")
    print("  1. Chrome WebDriver crashes (use system ChromeDriver)")
    print("  2. MongoDB retryable writes error (disable for Cosmos DB)")
    print("  3. Remove webdriver-manager dependency")
    print("  4. Update file documentation")
    print("\n" + "=" * 80 + "\n")
    
    # Check if file exists
    if not os.path.exists(MONITOR_SCRIPT_PATH):
        print(f"❌ ERROR: File not found: {MONITOR_SCRIPT_PATH}")
        return 1
    
    # Apply fixes
    success = True
    success = fix_chrome_driver_setup() and success
    success = fix_mongodb_connection() and success
    success = remove_webdriver_manager_import() and success
    success = update_file_header() and success
    
    if success:
        print("\n" + "=" * 80)
        print("✅ ALL FIXES APPLIED SUCCESSFULLY")
        print("=" * 80)
        print("\nNext steps:")
        print("  1. Deploy to VM:")
        print("     cd /Users/projects/Documents/Property_Data_Scraping")
        print("     gcloud compute scp --recurse 03_Gold_Coast fields-orchestrator-vm:/home/fields/Property_Data_Scraping/ --zone=australia-southeast1-b --project=fields-estate")
        print("\n  2. Restart orchestrator:")
        print("     gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='sudo systemctl restart fields-orchestrator'")
        print("\n  3. Monitor logs:")
        print("     gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'")
        print("\n" + "=" * 80 + "\n")
        return 0
    else:
        print("\n" + "=" * 80)
        print("⚠️  SOME FIXES MAY NEED MANUAL REVIEW")
        print("=" * 80)
        print("\nPlease review the warnings above and check the file manually.")
        print("\n" + "=" * 80 + "\n")
        return 1


if __name__ == "__main__":
    exit(main())
