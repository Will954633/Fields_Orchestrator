#!/bin/bash
# Date: 11/02/2026, 11:10 AM (Tuesday) - Brisbane Time
# Description: Install remaining Python dependencies discovered during test runs
# 
# Edit History:
# - 11/02/2026 11:10 AM: Initial creation after discovering bs4 missing

set -e

echo "============================================================"
echo "Installing Remaining Python Dependencies"
echo "============================================================"

echo "📦 Installing web scraping packages..."
sudo pip3 install beautifulsoup4 lxml html5lib

echo ""
echo "📦 Installing additional common packages..."
sudo pip3 install requests urllib3 certifi

echo ""
echo "============================================================"
echo "Verification"
echo "============================================================"
python3 << 'PYEOF'
import sys
modules = [
    "bs4",
    "lxml", 
    "requests",
    "dotenv",
    "pandas",
    "dateutil",
    "numpy",
    "sklearn",
    "pymongo",
    "selenium"
]
print("Checking all required modules:")
missing = []
for mod in modules:
    try:
        __import__(mod)
        print(f"  ✅ {mod}")
    except ImportError:
        print(f"  ❌ {mod} - NOT FOUND")
        missing.append(mod)

if missing:
    print(f"\n❌ Missing modules: {', '.join(missing)}")
    sys.exit(1)
else:
    print("\n✅ All required modules installed!")
PYEOF

echo ""
echo "✅ All dependencies installed successfully!"
