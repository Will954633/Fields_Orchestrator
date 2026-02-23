#!/usr/bin/env python3
"""
Update monitor_sold_properties.py Chrome Options for VM
Last Updated: 12/02/2026, 6:37 AM (Wednesday) - Brisbane Time

Description: Updates the setup_driver() method in monitor_sold_properties.py
to use proper Chrome options for headless mode on Linux server
"""

import re
import sys

def update_chrome_options(filepath):
    """Update Chrome options in monitor_sold_properties.py"""
    
    # Read the file
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Find the setup_driver method and replace the Chrome options section
    # Pattern: Find from "chrome_options = Options()" to just before "try:"
    pattern = r"(def setup_driver\(self\):.*?self\.log\(\"Setting up headless Chrome WebDriver\.\.\.\"\)\s+)(chrome_options = Options\(\).*?)(try:)"
    
    replacement = r'''\1chrome_options = Options()
        
        # Essential flags for headless mode on Linux server
        chrome_options.add_argument('--headless=new')  # Use new headless mode
        chrome_options.add_argument('--no-sandbox')  # Required for running as root or in containers
        chrome_options.add_argument('--disable-dev-shm-usage')  # Overcome limited resource problems
        chrome_options.add_argument('--disable-gpu')  # Disable GPU hardware acceleration
        chrome_options.add_argument('--disable-software-rasterizer')
        
        # Additional stability flags
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--remote-debugging-port=9222')  # Explicitly set debugging port
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--start-maximized')
        
        # User agent to avoid detection
        chrome_options.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Disable logging
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        \3'''
    
    # Replace
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    if new_content == content:
        print("❌ Pattern not found - no changes made")
        return False
    
    # Write back
    with open(filepath, 'w') as f:
        f.write(new_content)
    
    print("✅ Updated monitor_sold_properties.py with fixed Chrome options")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 update_monitor_chrome_options.py <filepath>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    success = update_chrome_options(filepath)
    sys.exit(0 if success else 1)
