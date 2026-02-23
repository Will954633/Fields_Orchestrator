#!/usr/bin/env python3
"""
Orchestrator Remediation Runner
Last Updated: 29/01/2026, 2:20 PM (Wednesday) - Brisbane

Runs remediation steps to fix failed pipeline steps and mark properties complete.

Steps:
1. Rerun Step 10 (room-photo matching) for the 1 failing property
2. Rerun Step 6 (valuation) for all 147 properties  
3. Run verifier with mark_complete=true
4. Report completion counts

Usage:
    python scripts/run_remediation.py
    python scripts/run_remediation.py --skip-step10  # Skip room matching
    python scripts/run_remediation.py --skip-step6   # Skip valuation
    python scripts/run_remediation.py --dry-run      # Test without marking complete
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.property_processing_verifier import PropertyProcessingVerifier
from src.pipeline_signature import compute_pipeline_signature
from pymongo import MongoClient


def run_command(cmd: str, cwd: str) -> tuple[bool, str]:
    """Run a shell command and return success status + output."""
    print(f"\n{'='*80}")
    print(f"Running: {cmd}")
    print(f"Working directory: {cwd}")
    print(f"{'='*80}\n")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        success = result.returncode == 0
        if success:
            print(f"\n✓ Command completed successfully")
        else:
            print(f"\n✗ Command failed with return code {result.returncode}")
        
        return success, result.stdout + result.stderr
        
    except subprocess.TimeoutExpired:
        print(f"\n✗ Command timed out after 1 hour")
        return False, "Timeout"
    except Exception as e:
        print(f"\n✗ Command failed with exception: {e}")
        return False, str(e)


def check_mongodb_status() -> dict:
    """Check current MongoDB status."""
    print("\n" + "="*80)
    print("Checking MongoDB Status")
    print("="*80 + "\n")
    
    client = MongoClient("mongodb://127.0.0.1:27017/", serverSelectionTimeoutMS=5000)
    db = client["property_data"]
    col = db["properties_for_sale"]
    
    total = col.count_documents({})
    
    # Count by status
    pipeline = [
        {"$group": {"_id": "$orchestrator.processing.status", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}
    ]
    by_status = list(col.aggregate(pipeline))
    
    # Count with iteration_08_valuation
    has_valuation = col.count_documents({"iteration_08_valuation.predicted_value": {"$exists": True}})
    
    # Count with room_photo_matching_completed_at
    has_room_matching = col.count_documents({"room_photo_matching_completed_at": {"$exists": True}})
    
    client.close()
    
    stats = {
        "total": total,
        "by_status": by_status,
        "has_valuation": has_valuation,
        "has_room_matching": has_room_matching,
    }
    
    print(f"Total properties: {total}")
    print(f"\nStatus breakdown:")
    for item in by_status:
        print(f"  {item['_id']}: {item['n']}")
    print(f"\nHas iteration_08_valuation: {has_valuation}/{total}")
    print(f"Has room_photo_matching_completed_at: {has_room_matching}/{total}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Run orchestrator remediation")
    parser.add_argument("--skip-step10", action="store_true", help="Skip Step 10 (room-photo matching)")
    parser.add_argument("--skip-step6", action="store_true", help="Skip Step 6 (valuation)")
    parser.add_argument("--dry-run", action="store_true", help="Run verifier in dry-run mode (don't mark complete)")
    parser.add_argument("--limit-valuation", type=int, help="Limit valuation to N properties (for testing)")
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("ORCHESTRATOR REMEDIATION RUNNER")
    print("="*80)
    print(f"Skip Step 10: {args.skip_step10}")
    print(f"Skip Step 6: {args.skip_step6}")
    print(f"Dry Run: {args.dry_run}")
    print("="*80 + "\n")
    
    base_dir = Path(__file__).parent.parent
    
    # Check initial status
    print("\n### INITIAL STATUS ###")
    initial_stats = check_mongodb_status()
    
    # Step 1: Rerun Step 10 (room-photo matching) for failing property
    if not args.skip_step10:
        print("\n### STEP 1: Rerun Room-Photo Matching for Failing Property ###")
        success, output = run_command(
            "python3 match_floor_plan_rooms_to_photos.py --property-id 697a03122dd05817453a97d8",
            cwd="/Users/projects/Documents/Feilds_Website"
        )
        if not success:
            print("⚠️ Step 10 remediation failed, but continuing...")
    
    # Step 2: Rerun Step 6 (valuation) for all properties
    if not args.skip_step6:
        print("\n### STEP 2: Rerun Valuation for All Properties ###")
        cmd = "python batch_valuate_with_tracking.py"
        if args.limit_valuation:
            cmd += f" --limit {args.limit_valuation}"
        
        success, output = run_command(
            cmd,
            cwd="/Users/projects/Documents/Property_Valuation/04_Production_Valuation"
        )
        if not success:
            print("⚠️ Step 6 remediation failed, but continuing...")
    
    # Step 3: Run verifier with mark_complete=true
    print("\n### STEP 3: Run Verifier with mark_complete=true ###")
    print("="*80 + "\n")
    
    sig = compute_pipeline_signature(base_dir=base_dir, version=2)
    
    verifier = PropertyProcessingVerifier(
        mongo_uri="mongodb://127.0.0.1:27017/",
        database="property_data",
        pipeline_version=2,
        pipeline_signature=sig.signature,
        dry_run=args.dry_run,
        write_verification_results=True,
        mark_complete=not args.dry_run,  # Only mark complete if not dry-run
    )
    
    if not verifier.connect():
        print("✗ Failed to connect to MongoDB")
        sys.exit(1)
    
    print(f"Pipeline signature: {sig.signature}")
    print(f"Dry run: {args.dry_run}")
    print(f"Mark complete: {not args.dry_run}\n")
    
    result = verifier.verify_and_update(run_id="manual-remediation-2026-01-29")
    verifier.close()
    
    print("\nVerifier Results:")
    print(f"  Examined: {result['examined']}")
    print(f"  Verified Complete: {result['verified_complete']}")
    print(f"  Verified Incomplete: {result['verified_incomplete']}")
    print(f"  Dry Run: {result['dry_run']}")
    print(f"  Mark Complete: {result['mark_complete']}")
    
    # Step 4: Check final status
    print("\n### FINAL STATUS ###")
    final_stats = check_mongodb_status()
    
    # Summary
    print("\n" + "="*80)
    print("REMEDIATION SUMMARY")
    print("="*80)
    
    print(f"\nBefore:")
    print(f"  Total: {initial_stats['total']}")
    print(f"  Has valuation: {initial_stats['has_valuation']}")
    print(f"  Has room matching: {initial_stats['has_room_matching']}")
    
    print(f"\nAfter:")
    print(f"  Total: {final_stats['total']}")
    print(f"  Has valuation: {final_stats['has_valuation']}")
    print(f"  Has room matching: {final_stats['has_room_matching']}")
    
    print(f"\nVerifier:")
    print(f"  Complete: {result['verified_complete']}")
    print(f"  Incomplete: {result['verified_incomplete']}")
    
    # Calculate how many will be skipped tomorrow
    client = MongoClient("mongodb://127.0.0.1:27017/", serverSelectionTimeoutMS=5000)
    db = client["property_data"]
    col = db["properties_for_sale"]
    
    skippable = col.count_documents({
        "orchestrator.processing.status": "complete",
        "orchestrator.pipeline_signature.signature": sig.signature
    })
    
    client.close()
    
    print(f"\nTomorrow's Run:")
    print(f"  Properties that will be skipped: {skippable}/{final_stats['total']}")
    print(f"  Properties that will be processed: {final_stats['total'] - skippable}/{final_stats['total']}")
    
    if skippable > 0:
        speedup_pct = (skippable / final_stats['total']) * 100
        print(f"  Expected speedup: ~{speedup_pct:.0f}% (skipping {skippable} already-complete properties)")
    
    print("\n" + "="*80)
    print("✓ Remediation complete!")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
