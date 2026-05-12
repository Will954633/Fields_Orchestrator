#!/usr/bin/env python3
"""
URL Tracking Monitor - Entry Point
Continuously monitor properties for new URLs
"""

import asyncio
import sys
from continuous_monitor import ContinuousMonitor


async def main():
    """Main entry point"""

    print("="*80)
    print("URL TRACKING MONITOR - STARTING")
    print("="*80)
    print("✓ Direct agency website scraping")
    print("✓ Continuous URL tracking")
    print("✓ Parallel processing (10 properties at once)")
    print("✓ Local MongoDB storage (Gold_Coast) + JSON files")
    print("="*80)

    # Initialize monitor
    monitor = ContinuousMonitor(
        suburbs=['robina'],
        concurrency=10,
        json_output_dir="discovered_urls"
    )

    # Run forever
    await monitor.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
