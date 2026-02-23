#!/usr/bin/env python3
"""
Update monitor_sold_properties.py to use system ChromeDriver
Last Updated: 12/02/2026, 6:39 AM (Wednesday) - Brisbane Time

Description: Updates setup_driver() to use /usr/local/bin/chromedriver
instead of webdriver-manager
"""

import re
import sys

def update_to_system_chromedriver(filepath):
    """Update to use system ChromeDriver"""
    
    # Read the file
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Find and replace the Service creation line
    # Change from: service = Service(ChromeDriverManager().install())
    # To: service = Service('/usr/local/bin/chromedriver')
    
    pattern = r"service = Service\(ChromeDriverManager\(\)\.install\(\)\)"
    replacement = "service = Service('/usr/local/bin/chromedriver')"
    
    new_content = content.replace(pattern, replacement)
    
    if new_content == content:
        print("❌ Pattern not found - no changes made")
        return False
    
    # Write back
    with open(filepath, 'w') as f:
        f.write(new_content)
    
    print("✅ Updated monitor_sold_properties.py to use system ChromeDriver")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 fix_monitor_use_system_chromedriver.py <filepath>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    success = update_to_system_chromedriver(filepath)
    sys.exit(0 if success else 1)
