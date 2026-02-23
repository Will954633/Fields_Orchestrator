#!/bin/bash
# ChromeDriver Zombie Process Cleanup Script
# Last Updated: 06/02/2026, 9:22 am (Thursday) - Brisbane
#
# Purpose: Kill all zombie ChromeDriver processes that are preventing new instances from starting
# Usage: ./cleanup_zombie_chromedrivers.sh

echo "=========================================="
echo "ChromeDriver Zombie Process Cleanup"
echo "=========================================="
echo ""

# Count zombie processes
ZOMBIE_COUNT=$(ps aux | grep -i chromedriver | grep -v grep | wc -l | tr -d ' ')

if [ "$ZOMBIE_COUNT" -eq 0 ]; then
    echo "✅ No ChromeDriver processes found. System is clean."
    exit 0
fi

echo "⚠️  Found $ZOMBIE_COUNT ChromeDriver processes"
echo ""

# Show processes
echo "Current ChromeDriver processes:"
echo "----------------------------------------"
ps aux | grep -i chromedriver | grep -v grep | head -10
if [ "$ZOMBIE_COUNT" -gt 10 ]; then
    echo "... and $((ZOMBIE_COUNT - 10)) more"
fi
echo ""

# Ask for confirmation
read -p "Kill all ChromeDriver processes? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cleanup cancelled"
    exit 1
fi

echo ""
echo "🔪 Killing all ChromeDriver processes..."

# Kill all chromedriver processes
pkill -9 chromedriver

# Wait for cleanup
sleep 2

# Verify cleanup
REMAINING=$(ps aux | grep -i chromedriver | grep -v grep | wc -l | tr -d ' ')

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ Successfully killed $ZOMBIE_COUNT ChromeDriver processes"
    echo "✅ System is now clean"
else
    echo "⚠️  Warning: $REMAINING processes still running"
    echo ""
    echo "Remaining processes:"
    ps aux | grep -i chromedriver | grep -v grep
    echo ""
    echo "You may need to manually kill these processes or restart your system"
fi

echo ""
echo "=========================================="
echo "Cleanup Complete"
echo "=========================================="
