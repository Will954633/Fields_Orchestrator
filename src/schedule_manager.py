#!/usr/bin/env python3
"""
Schedule Manager for Gold Coast Property Monitoring
Last Updated: 04/02/2026, 7:15 AM (Tuesday) - Brisbane

Determines which processes should run based on day/time and target market configuration.
Supports differentiated scheduling:
- Target Market suburbs: Run nightly (8 key suburbs)
- Other suburbs: Run weekly on Sunday (44 additional suburbs)
"""

from datetime import datetime
from typing import List, Dict, Set
from pathlib import Path
import yaml

from .logger import get_logger


class ScheduleManager:
    """
    Manages process scheduling based on target market and day of week.
    
    This class determines which processes should run on any given day:
    - Target market processes (101, 103, 105, 106): Run daily
    - Other suburbs processes (102, 104): Run weekly on Sunday
    - Valuation and backend enrichment (6, 11-16): Always run
    """
    
    def __init__(self, config_path: str = None):
        """
        Initialize the schedule manager.
        
        Args:
            config_path: Path to settings.yaml (optional)
        """
        self.logger = get_logger()
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        
        self.config = self._load_config(config_path)
        
        # Target market suburbs (8 key suburbs)
        self.target_market_suburbs = self.config.get('target_market', {}).get('suburbs', [
            "Robina:4226",
            "Mudgeeraba:4213",
            "Varsity Lakes:4227",
            "Reedy Creek:4227",
            "Burleigh Waters:4220",
            "Merrimac:4226",
            "Worongary:4213",
            "Carrara:4211"
        ])
        
        # Schedule configuration
        schedule_config = self.config.get('schedule', {})
        self.run_target_market_daily = schedule_config.get('run_target_market_daily', True)
        self.run_other_suburbs_weekly = schedule_config.get('run_other_suburbs_weekly', True)
        self.other_suburbs_day = schedule_config.get('other_suburbs_day', 'Sunday')
        
        # Process ID sets
        self.target_market_processes = {101, 103, 105, 106, 108}  # Scrape, Monitor, Photo, Floor Plan, Valuation Enrichment
        self.other_suburbs_processes = {102, 104}  # Scrape All, Monitor All
        self.always_run_processes = {6, 11, 12, 13, 14, 15, 16, 17, 18, 19, 109, 107, 110}  # Valuation + Backend Enrichment + Pre-computation + Coverage Check + Audit + Image Archival
        
        self.logger.info(f"Schedule Manager initialized")
        self.logger.info(f"Target market suburbs: {len(self.target_market_suburbs)}")
        self.logger.info(f"Target market daily: {self.run_target_market_daily}")
        self.logger.info(f"Other suburbs weekly: {self.run_other_suburbs_weekly} ({self.other_suburbs_day})")
    
    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from settings.yaml."""
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.warning(f"Failed to load config from {config_path}: {e}")
        
        return {}
    
    def should_run_target_market(self, check_date: datetime = None) -> bool:
        """
        Determine if target market processes should run.
        
        Args:
            check_date: Date to check (defaults to today)
            
        Returns:
            True if target market processes should run
        """
        if not self.run_target_market_daily:
            return False
        
        # Target market runs every day
        return True
    
    def should_run_other_suburbs(self, check_date: datetime = None) -> bool:
        """
        Determine if other suburbs processes should run.
        
        Args:
            check_date: Date to check (defaults to today)
            
        Returns:
            True if other suburbs processes should run
        """
        if not self.run_other_suburbs_weekly:
            return False
        
        if check_date is None:
            check_date = datetime.now()
        
        # Check if today matches the configured day
        today = check_date.strftime('%A')
        return today == self.other_suburbs_day
    
    def get_processes_to_run(self, check_date: datetime = None) -> List[int]:
        """
        Get list of process IDs that should run based on schedule.
        
        Args:
            check_date: Date to check (defaults to today)
            
        Returns:
            List of process IDs to execute
        """
        if check_date is None:
            check_date = datetime.now()
        
        processes = set()
        
        # Check target market
        if self.should_run_target_market(check_date):
            processes.update(self.target_market_processes)
            self.logger.info(f"✅ Target market processes scheduled: {sorted(self.target_market_processes)}")
        else:
            self.logger.info(f"⏭️  Target market processes skipped (not scheduled for today)")
        
        # Check other suburbs
        if self.should_run_other_suburbs(check_date):
            processes.update(self.other_suburbs_processes)
            self.logger.info(f"✅ Other suburbs processes scheduled: {sorted(self.other_suburbs_processes)}")
        else:
            today = check_date.strftime('%A')
            self.logger.info(f"⏭️  Other suburbs processes skipped (today is {today}, runs on {self.other_suburbs_day})")
        
        # Always run valuation and backend enrichment
        processes.update(self.always_run_processes)
        self.logger.info(f"✅ Always-run processes scheduled: {sorted(self.always_run_processes)}")
        
        # Return sorted list
        return sorted(list(processes))
    
    def get_schedule_summary(self, check_date: datetime = None) -> Dict:
        """
        Get a summary of what will run.
        
        Args:
            check_date: Date to check (defaults to today)
            
        Returns:
            Dictionary with schedule summary
        """
        if check_date is None:
            check_date = datetime.now()
        
        return {
            "date": check_date.strftime("%Y-%m-%d"),
            "day_of_week": check_date.strftime("%A"),
            "target_market_runs": self.should_run_target_market(check_date),
            "other_suburbs_runs": self.should_run_other_suburbs(check_date),
            "processes_to_run": self.get_processes_to_run(check_date),
            "target_market_suburbs": self.target_market_suburbs,
            "process_counts": {
                "target_market": len(self.target_market_processes) if self.should_run_target_market(check_date) else 0,
                "other_suburbs": len(self.other_suburbs_processes) if self.should_run_other_suburbs(check_date) else 0,
                "always_run": len(self.always_run_processes),
                "total": len(self.get_processes_to_run(check_date))
            }
        }
    
    def is_process_enabled(self, process_id: int, check_date: datetime = None) -> bool:
        """
        Check if a specific process should run.
        
        Args:
            process_id: Process ID to check
            check_date: Date to check (defaults to today)
            
        Returns:
            True if process should run
        """
        processes_to_run = self.get_processes_to_run(check_date)
        return process_id in processes_to_run


if __name__ == "__main__":
    # Test the schedule manager
    from .logger import setup_logger
    
    setup_logger(level="INFO", console_output=True)
    
    manager = ScheduleManager()
    
    print("\n" + "="*60)
    print("SCHEDULE MANAGER TEST")
    print("="*60 + "\n")
    
    # Test for different days
    from datetime import timedelta
    
    today = datetime.now()
    for i in range(7):
        test_date = today + timedelta(days=i)
        summary = manager.get_schedule_summary(test_date)
        
        print(f"\n{summary['day_of_week']} ({summary['date']}):")
        print(f"  Target Market: {'✅ YES' if summary['target_market_runs'] else '❌ NO'}")
        print(f"  Other Suburbs: {'✅ YES' if summary['other_suburbs_runs'] else '❌ NO'}")
        print(f"  Total Processes: {summary['process_counts']['total']}")
        print(f"  Process IDs: {summary['processes_to_run']}")
