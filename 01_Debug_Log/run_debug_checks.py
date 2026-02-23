#!/usr/bin/env python3
"""
Debug Checks Runner for Fields Orchestrator

Last Updated: 05/02/2026, 8:19 AM (Wednesday) - Brisbane

This script runs all debug checks for the orchestrator:
1. Static record matching for new listings
2. Data integrity verification for sold properties
3. Comprehensive reporting

This should be called at the end of each orchestrator run.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logger import get_logger
from static_record_matcher import StaticRecordMatcher
from data_integrity_monitor import DataIntegrityMonitor


def run_all_checks(run_id: str, mongo_uri: str = "mongodb://127.0.0.1:27017/") -> bool:
    """
    Run all debug checks for the orchestrator run.
    
    Args:
        run_id: Orchestrator run ID
        mongo_uri: MongoDB connection URI
    
    Returns:
        True if all checks passed, False if any failures
    """
    logger = get_logger()
    
    logger.info("=" * 80)
    logger.info("STARTING DEBUG CHECKS")
    logger.info(f"Run ID: {run_id}")
    logger.info("=" * 80)
    
    all_passed = True
    
    # Step 1: Match new listings to static records
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: STATIC RECORD MATCHING")
    logger.info("=" * 80)
    
    matcher = StaticRecordMatcher(mongo_uri=mongo_uri)
    if not matcher.connect():
        logger.error("Failed to connect to MongoDB for static record matching")
        return False
    
    try:
        match_summary = matcher.match_new_listings(run_id)
        
        if match_summary['no_matches'] > 0:
            logger.warning(f"⚠️  {match_summary['no_matches']} properties could not be matched to static records")
            all_passed = False
        else:
            logger.info("✅ All new listings matched to static records")
    except Exception as e:
        logger.error(f"Error during static record matching: {e}")
        all_passed = False
    finally:
        matcher.close()
    
    # Step 2: Run data integrity checks
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: DATA INTEGRITY VERIFICATION")
    logger.info("=" * 80)
    
    monitor = DataIntegrityMonitor(mongo_uri=mongo_uri)
    if not monitor.connect():
        logger.error("Failed to connect to MongoDB for integrity monitoring")
        return False
    
    try:
        report = monitor.run_integrity_check(run_id)
        
        # Check for failures
        if report.sold_properties_failed > 0:
            logger.warning(f"⚠️  {report.sold_properties_failed} sold properties failed integrity checks")
            all_passed = False
        
        if report.new_listings_unmatched > 0:
            logger.warning(f"⚠️  {report.new_listings_unmatched} new listings are unmatched")
            all_passed = False
        
        if len(report.static_update_failures) > 0:
            logger.warning(f"⚠️  {len(report.static_update_failures)} static record updates failed")
            all_passed = False
        
        if all_passed:
            logger.info("✅ All data integrity checks passed")
        
    except Exception as e:
        logger.error(f"Error during integrity monitoring: {e}")
        all_passed = False
    finally:
        monitor.close()
    
    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("DEBUG CHECKS COMPLETE")
    logger.info("=" * 80)
    
    if all_passed:
        logger.info("✅ ALL CHECKS PASSED")
    else:
        logger.warning("❌ SOME CHECKS FAILED - Review logs for details")
    
    logger.info("=" * 80)
    
    return all_passed


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run all debug checks for Fields Orchestrator")
    parser.add_argument('--run-id', required=True, help='Orchestrator run ID')
    parser.add_argument('--mongo-uri', default='mongodb://127.0.0.1:27017/', help='MongoDB URI')
    
    args = parser.parse_args()
    
    success = run_all_checks(args.run_id, args.mongo_uri)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
