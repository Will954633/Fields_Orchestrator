#!/usr/bin/env python3
"""
Process Failures Logger
Last Updated: 05/02/2026, 7:03 PM (Wednesday) - Brisbane

PURPOSE:
Logs orchestrator process/step failures for debugging and monitoring.
Tracks timeouts, errors, and retry attempts across all pipeline steps.

USAGE:
    from process_failures_logger import log_process_failure
    
    log_process_failure(
        step_id=106,
        step_name="Floor Plan Analysis",
        error_type="timeout",
        error_message="Process timed out after 180 minutes",
        property_address="32 Coronata Place Reedy Creek",
        retry_count=1
    )
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class ProcessFailuresLogger:
    """Logger for tracking orchestrator process failures"""
    
    def __init__(self, log_dir: Optional[str] = None):
        """Initialize logger with log directory"""
        if log_dir is None:
            # Default to 01_Debug_Log directory
            script_dir = Path(__file__).parent
            log_dir = script_dir / "logs"
        else:
            log_dir = Path(log_dir)
        
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d")
        self.log_file = self.log_dir / f"process_failures_{timestamp}.jsonl"
    
    def log_failure(
        self,
        step_id: int,
        step_name: str,
        error_type: str,
        error_message: str,
        property_address: Optional[str] = None,
        retry_count: int = 0,
        additional_info: Optional[dict] = None
    ):
        """
        Log a process failure
        
        Args:
            step_id: Process/step ID (e.g., 101, 106)
            step_name: Process name (e.g., "Floor Plan Analysis")
            error_type: Type of error (timeout, ollama_timeout, network, exception, etc.)
            error_message: Detailed error message
            property_address: Property address if applicable
            retry_count: Number of retries attempted
            additional_info: Additional context (optional)
        """
        failure_record = {
            "timestamp": datetime.now().isoformat(),
            "step_id": step_id,
            "step_name": step_name,
            "error_type": error_type,
            "error_message": error_message,
            "property_address": property_address,
            "retry_count": retry_count,
            "additional_info": additional_info or {}
        }
        
        # Append to JSONL file (one JSON object per line)
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(failure_record) + '\n')
    
    def get_failures_summary(self, date: Optional[str] = None) -> dict:
        """
        Get summary of failures for a specific date
        
        Args:
            date: Date in YYYYMMDD format (default: today)
        
        Returns:
            Dictionary with failure statistics
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        
        log_file = self.log_dir / f"process_failures_{date}.jsonl"
        
        if not log_file.exists():
            return {
                "date": date,
                "total_failures": 0,
                "by_error_type": {},
                "by_step": {},
                "failed_properties": []
            }
        
        failures = []
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    failures.append(json.loads(line))
        
        # Aggregate statistics
        by_error_type = {}
        by_step = {}
        failed_properties = []
        
        for failure in failures:
            error_type = failure.get("error_type", "unknown")
            step_name = failure.get("step_name", "unknown")
            property_addr = failure.get("property_address")
            
            by_error_type[error_type] = by_error_type.get(error_type, 0) + 1
            by_step[step_name] = by_step.get(step_name, 0) + 1
            
            if property_addr:
                failed_properties.append({
                    "address": property_addr,
                    "step": step_name,
                    "error": error_type
                })
        
        return {
            "date": date,
            "total_failures": len(failures),
            "by_error_type": by_error_type,
            "by_step": by_step,
            "failed_properties": failed_properties
        }
    
    def print_summary(self, date: Optional[str] = None):
        """Print a human-readable summary of failures"""
        summary = self.get_failures_summary(date)
        
        print("\n" + "=" * 60)
        print(f"PROCESS FAILURES SUMMARY - {summary['date']}")
        print("=" * 60)
        print(f"\nTotal Failures: {summary['total_failures']}")
        
        if summary['total_failures'] > 0:
            print("\nBy Error Type:")
            for error_type, count in sorted(summary['by_error_type'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {error_type}: {count}")
            
            print("\nBy Step:")
            for step, count in sorted(summary['by_step'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {step}: {count}")
            
            if summary['failed_properties']:
                print(f"\nFailed Properties: {len(summary['failed_properties'])}")
                if len(summary['failed_properties']) <= 20:
                    for prop in summary['failed_properties']:
                        print(f"  - {prop['address']} ({prop['step']}: {prop['error']})")
                else:
                    print(f"  (Too many to display - see log file)")
        
        print("=" * 60 + "\n")


# Global logger instance
_logger = None


def get_logger() -> ProcessFailuresLogger:
    """Get or create global logger instance"""
    global _logger
    if _logger is None:
        _logger = ProcessFailuresLogger()
    return _logger


def log_process_failure(
    step_id: int,
    step_name: str,
    error_type: str,
    error_message: str,
    property_address: Optional[str] = None,
    retry_count: int = 0,
    additional_info: Optional[dict] = None
):
    """
    Convenience function to log a process failure
    
    Args:
        step_id: Process/step ID
        step_name: Process name
        error_type: Type of error (timeout, ollama_timeout, network, exception, etc.)
        error_message: Detailed error message
        property_address: Property address if applicable
        retry_count: Number of retries attempted
        additional_info: Additional context (optional)
    """
    logger = get_logger()
    logger.log_failure(step_id, step_name, error_type, error_message, property_address, retry_count, additional_info)


def print_failures_summary(date: Optional[str] = None):
    """Print summary of process failures"""
    logger = get_logger()
    logger.print_summary(date)


if __name__ == "__main__":
    # Test the logger
    import argparse
    
    parser = argparse.ArgumentParser(description="View process failures summary")
    parser.add_argument('--date', help='Date in YYYYMMDD format (default: today)')
    args = parser.parse_args()
    
    print_failures_summary(args.date)
