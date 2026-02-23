#!/usr/bin/env python3
"""
Scraping Failures Logger
Last Updated: 05/02/2026, 9:30 AM (Wednesday) - Brisbane

PURPOSE:
Logs failed property scraping attempts for debugging and monitoring.
Tracks timeout failures, network errors, and other scraping issues.

USAGE:
    from scraping_failures_logger import log_scraping_failure
    
    log_scraping_failure(
        url="https://domain.com.au/property-123456",
        suburb="Robina",
        error_type="timeout",
        error_message="Page load timeout after 90 seconds",
        retry_count=2
    )
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class ScrapingFailuresLogger:
    """Logger for tracking scraping failures"""
    
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
        self.log_file = self.log_dir / f"scraping_failures_{timestamp}.jsonl"
    
    def log_failure(
        self,
        url: str,
        suburb: str,
        error_type: str,
        error_message: str,
        retry_count: int = 0,
        additional_info: Optional[dict] = None
    ):
        """
        Log a scraping failure
        
        Args:
            url: Property URL that failed
            suburb: Suburb name
            error_type: Type of error (timeout, network, parse_error, etc.)
            error_message: Detailed error message
            retry_count: Number of retries attempted
            additional_info: Additional context (optional)
        """
        failure_record = {
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "suburb": suburb,
            "error_type": error_type,
            "error_message": error_message,
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
        
        log_file = self.log_dir / f"scraping_failures_{date}.jsonl"
        
        if not log_file.exists():
            return {
                "date": date,
                "total_failures": 0,
                "by_error_type": {},
                "by_suburb": {},
                "failed_urls": []
            }
        
        failures = []
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    failures.append(json.loads(line))
        
        # Aggregate statistics
        by_error_type = {}
        by_suburb = {}
        failed_urls = []
        
        for failure in failures:
            error_type = failure.get("error_type", "unknown")
            suburb = failure.get("suburb", "unknown")
            url = failure.get("url", "")
            
            by_error_type[error_type] = by_error_type.get(error_type, 0) + 1
            by_suburb[suburb] = by_suburb.get(suburb, 0) + 1
            failed_urls.append(url)
        
        return {
            "date": date,
            "total_failures": len(failures),
            "by_error_type": by_error_type,
            "by_suburb": by_suburb,
            "failed_urls": failed_urls
        }
    
    def print_summary(self, date: Optional[str] = None):
        """Print a human-readable summary of failures"""
        summary = self.get_failures_summary(date)
        
        print("\n" + "=" * 60)
        print(f"SCRAPING FAILURES SUMMARY - {summary['date']}")
        print("=" * 60)
        print(f"\nTotal Failures: {summary['total_failures']}")
        
        if summary['total_failures'] > 0:
            print("\nBy Error Type:")
            for error_type, count in sorted(summary['by_error_type'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {error_type}: {count}")
            
            print("\nBy Suburb:")
            for suburb, count in sorted(summary['by_suburb'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {suburb}: {count}")
            
            print(f"\nFailed URLs: {len(summary['failed_urls'])}")
            if len(summary['failed_urls']) <= 10:
                for url in summary['failed_urls']:
                    print(f"  - {url}")
            else:
                print(f"  (Too many to display - see log file)")
        
        print("=" * 60 + "\n")


# Global logger instance
_logger = None


def get_logger() -> ScrapingFailuresLogger:
    """Get or create global logger instance"""
    global _logger
    if _logger is None:
        _logger = ScrapingFailuresLogger()
    return _logger


def log_scraping_failure(
    url: str,
    suburb: str,
    error_type: str,
    error_message: str,
    retry_count: int = 0,
    additional_info: Optional[dict] = None
):
    """
    Convenience function to log a scraping failure
    
    Args:
        url: Property URL that failed
        suburb: Suburb name
        error_type: Type of error (timeout, network, parse_error, etc.)
        error_message: Detailed error message
        retry_count: Number of retries attempted
        additional_info: Additional context (optional)
    """
    logger = get_logger()
    logger.log_failure(url, suburb, error_type, error_message, retry_count, additional_info)


def print_failures_summary(date: Optional[str] = None):
    """Print summary of scraping failures"""
    logger = get_logger()
    logger.print_summary(date)


if __name__ == "__main__":
    # Test the logger
    import argparse
    
    parser = argparse.ArgumentParser(description="View scraping failures summary")
    parser.add_argument('--date', help='Date in YYYYMMDD format (default: today)')
    args = parser.parse_args()
    
    print_failures_summary(args.date)
