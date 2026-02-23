#!/usr/bin/env python3
"""
Test Script for Unknown Status Detection
Last Updated: 27/01/2026, 10:48 AM (Monday) - Brisbane

This script tests the unknown status detection functionality.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.logger import setup_logger, get_logger
from src.unknown_status_detector import UnknownStatusDetector


def test_snapshot():
    """Test taking a snapshot."""
    logger = get_logger()
    logger.info("\n" + "="*80)
    logger.info("TEST 1: Taking Pre-Phase 2 Snapshot")
    logger.info("="*80 + "\n")
    
    detector = UnknownStatusDetector()
    
    if not detector.connect_mongodb():
        logger.error("❌ Failed to connect to MongoDB")
        return False
    
    success = detector.take_pre_phase2_snapshot()
    detector.disconnect_mongodb()
    
    if success:
        logger.info("✅ Snapshot test PASSED")
    else:
        logger.error("❌ Snapshot test FAILED")
    
    return success


def test_load_snapshot():
    """Test loading a snapshot."""
    logger = get_logger()
    logger.info("\n" + "="*80)
    logger.info("TEST 2: Loading Snapshot")
    logger.info("="*80 + "\n")
    
    detector = UnknownStatusDetector()
    success = detector.load_snapshot()
    
    if success:
        logger.info(f"✅ Load snapshot test PASSED - {len(detector.pre_phase2_snapshot)} properties loaded")
    else:
        logger.warning("⚠️ Load snapshot test - No snapshot found (expected on first run)")
    
    return True  # Not a failure if no snapshot exists


def test_detection():
    """Test the full detection process."""
    logger = get_logger()
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Full Detection Process")
    logger.info("="*80 + "\n")
    
    detector = UnknownStatusDetector()
    success = detector.run_detection()
    
    if success:
        logger.info("✅ Detection test PASSED")
        if detector.unknown_properties:
            logger.info(f"   Found {len(detector.unknown_properties)} unknown status properties")
        else:
            logger.info("   No unknown status properties detected")
    else:
        logger.error("❌ Detection test FAILED")
    
    return success


def test_mongodb_connection():
    """Test MongoDB connection."""
    logger = get_logger()
    logger.info("\n" + "="*80)
    logger.info("TEST 0: MongoDB Connection")
    logger.info("="*80 + "\n")
    
    detector = UnknownStatusDetector()
    success = detector.connect_mongodb()
    
    if success:
        logger.info("✅ MongoDB connection test PASSED")
        
        # Check collections exist
        if detector.db is not None:
            collections = detector.db.list_collection_names()
            logger.info(f"   Available collections: {', '.join(collections)}")
            
            if 'properties_for_sale' in collections:
                count = detector.db['properties_for_sale'].count_documents({})
                logger.info(f"   properties_for_sale: {count} documents")
            
            if 'properties_sold' in collections:
                count = detector.db['properties_sold'].count_documents({})
                logger.info(f"   properties_sold: {count} documents")
        
        detector.disconnect_mongodb()
    else:
        logger.error("❌ MongoDB connection test FAILED")
    
    return success


def main():
    """Run all tests."""
    setup_logger(level="INFO", console_output=True)
    logger = get_logger()
    
    logger.info("\n" + "="*80)
    logger.info("🧪 UNKNOWN STATUS DETECTION - TEST SUITE")
    logger.info("="*80 + "\n")
    
    tests = [
        ("MongoDB Connection", test_mongodb_connection),
        ("Take Snapshot", test_snapshot),
        ("Load Snapshot", test_load_snapshot),
        ("Full Detection", test_detection),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ Test '{test_name}' raised exception: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("📊 TEST SUMMARY")
    logger.info("="*80 + "\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"  {status} - {test_name}")
    
    logger.info(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 All tests PASSED!")
        return 0
    else:
        logger.warning(f"\n⚠️ {total - passed} test(s) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
