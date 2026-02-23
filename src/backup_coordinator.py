#!/usr/bin/env python3
"""
Backup Coordinator Module for Fields Orchestrator
Last Updated: 31/01/2026, 7:58 AM (Friday) - Brisbane

Manages MongoDB backups with daily rotation. This module replaces the continuous
30-minute backup system with a single daily backup after the pipeline completes.

Backup Strategy:
- One backup per day after all data collection processes complete
- Maintains 4 backup slots: latest, yesterday, 3-days, 5-days
- Backs up to 2 locations for redundancy (Internal SSD, My Passport)
- T7 SSD removed from rotation (device full as of 31/01/2026)

Recent Changes (31/01/2026):
- Removed T7 SSD from backup rotation (device full)
- Increased timeout from 30 to 90 minutes (database growth)
- Added tertiary location fallback logic
- Primary: Internal SSD, Secondary: My Passport
"""

import os
import shutil
import subprocess
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

from .logger import get_logger


class BackupCoordinator:
    """
    Coordinates MongoDB backups with daily rotation.
    
    This class handles:
    - Creating compressed MongoDB backups using mongodump
    - Rotating backups through 4 time-based slots
    - Syncing backups to multiple locations for redundancy
    """
    
    # Backup slot names
    SLOT_LATEST = "backup_latest"
    SLOT_YESTERDAY = "backup_yesterday"
    SLOT_3DAYS = "backup_3days"
    SLOT_5DAYS = "backup_5days"
    
    def __init__(
        self,
        mongo_uri: str = "mongodb://127.0.0.1:27017/",
        primary_dir: str = "/Users/projects/Documents/MongdbBackups",
        secondary_dir: str = "/Volumes/My Passport for Mac/MongdbBackups",
        tertiary_dir: str = None,
        rotation_marker: str = ".last_daily_rotation"
    ):
        """
        Initialize the backup coordinator.
        
        Args:
            mongo_uri: MongoDB connection URI
            primary_dir: Primary backup location (internal SSD) - Changed from T7 (full)
            secondary_dir: Secondary backup location (My Passport external HDD)
            tertiary_dir: Tertiary backup location (disabled - T7 is full)
            rotation_marker: Filename for tracking last rotation date
        """
        self.mongo_uri = mongo_uri
        self.primary_dir = Path(primary_dir)
        self.secondary_dir = Path(secondary_dir)
        self.tertiary_dir = Path(tertiary_dir) if tertiary_dir else None
        self.rotation_marker = rotation_marker
        self.logger = get_logger()
        
        # Path to mongodump binary
        self.mongodump_bin = self._find_mongodump()
    
    def _find_mongodump(self) -> str:
        """Find the mongodump binary."""
        # Try common locations
        locations = [
            "/opt/homebrew/bin/mongodump",
            "/usr/local/bin/mongodump",
            "/usr/bin/mongodump",
        ]
        
        for loc in locations:
            if os.path.isfile(loc) and os.access(loc, os.X_OK):
                return loc
        
        # Try to find in PATH
        result = subprocess.run(
            ["which", "mongodump"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        
        self.logger.warning("mongodump not found in common locations")
        return "mongodump"  # Hope it's in PATH
    
    def _get_available_backup_dirs(self) -> List[Path]:
        """Get list of available backup directories."""
        dirs = []
        
        for backup_dir in [self.primary_dir, self.secondary_dir, self.tertiary_dir]:
            if backup_dir is None:
                continue
            
            # Check if the volume is mounted (for external drives)
            if str(backup_dir).startswith("/Volumes/"):
                volume_root = Path("/Volumes") / backup_dir.parts[2]
                if not volume_root.exists():
                    self.logger.warning(f"Volume not mounted: {volume_root}")
                    continue
            
            # Create directory if it doesn't exist
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                if backup_dir.exists() and os.access(backup_dir, os.W_OK):
                    dirs.append(backup_dir)
                else:
                    self.logger.warning(f"Backup directory not writable: {backup_dir}")
            except Exception as e:
                self.logger.warning(f"Cannot access backup directory {backup_dir}: {e}")
        
        return dirs
    
    def _get_rotation_date(self, backup_dir: Path) -> Optional[date]:
        """Get the last rotation date for a backup directory."""
        marker_file = backup_dir / self.rotation_marker
        if marker_file.exists():
            try:
                date_str = marker_file.read_text().strip()
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception as e:
                self.logger.warning(f"Failed to read rotation marker: {e}")
        return None
    
    def _set_rotation_date(self, backup_dir: Path, rotation_date: date) -> None:
        """Set the rotation date for a backup directory."""
        marker_file = backup_dir / self.rotation_marker
        try:
            marker_file.write_text(rotation_date.strftime("%Y-%m-%d"))
        except Exception as e:
            self.logger.error(f"Failed to write rotation marker: {e}")
    
    def _needs_rotation(self, backup_dir: Path) -> bool:
        """Check if backup directory needs daily rotation."""
        last_rotation = self._get_rotation_date(backup_dir)
        if last_rotation is None:
            return True
        return last_rotation < date.today()
    
    def _perform_rotation(self, backup_dir: Path) -> None:
        """
        Perform daily backup rotation for a directory.
        
        Rotation cascade:
        5days (delete) <- 3days <- yesterday <- latest
        """
        self.logger.info(f"Performing backup rotation in {backup_dir}")
        
        dir_5days = backup_dir / self.SLOT_5DAYS
        dir_3days = backup_dir / self.SLOT_3DAYS
        dir_yesterday = backup_dir / self.SLOT_YESTERDAY
        dir_latest = backup_dir / self.SLOT_LATEST
        
        # Step 1: Delete 5-day-old backup
        if dir_5days.exists():
            self.logger.debug(f"Deleting old 5-day backup")
            shutil.rmtree(dir_5days)
        
        # Step 2: Move 3-day backup to 5-day slot
        if dir_3days.exists():
            self.logger.debug(f"Moving 3-day backup → 5-day slot")
            shutil.move(str(dir_3days), str(dir_5days))
        
        # Step 3: Move yesterday backup to 3-day slot
        if dir_yesterday.exists():
            self.logger.debug(f"Moving yesterday backup → 3-day slot")
            shutil.move(str(dir_yesterday), str(dir_3days))
        
        # Step 4: Move latest backup to yesterday slot
        if dir_latest.exists():
            self.logger.debug(f"Moving latest backup → yesterday slot")
            shutil.move(str(dir_latest), str(dir_yesterday))
        
        # Update rotation marker
        self._set_rotation_date(backup_dir, date.today())
        self.logger.info(f"Rotation complete for {backup_dir}")
    
    def _create_backup(self, backup_dir: Path) -> bool:
        """
        Create a new backup using mongodump.
        
        Args:
            backup_dir: Directory to create backup in
            
        Returns:
            True if backup successful, False otherwise
        """
        backup_path = backup_dir / self.SLOT_LATEST
        
        # Remove existing latest backup if it exists
        if backup_path.exists():
            shutil.rmtree(backup_path)
        
        self.logger.info(f"Creating backup at {backup_path}")
        
        try:
            result = subprocess.run(
                [
                    self.mongodump_bin,
                    f"--uri={self.mongo_uri}",
                    f"--out={backup_path}",
                    "--gzip"
                ],
                capture_output=True,
                text=True,
                timeout=5400  # 90 minute timeout (increased from 30 min due to database growth)
            )
            
            if result.returncode == 0:
                self.logger.info(f"✅ Backup created successfully at {backup_path}")
                return True
            else:
                self.logger.error(f"Backup failed: {result.stderr}")
                # Clean up failed backup
                if backup_path.exists():
                    shutil.rmtree(backup_path)
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("Backup timed out after 90 minutes")
            return False
        except Exception as e:
            self.logger.error(f"Backup failed with exception: {e}")
            return False
    
    def _sync_backup(self, source_dir: Path, target_dir: Path) -> bool:
        """
        Sync backup from source to target directory using rsync.
        
        Args:
            source_dir: Source backup directory
            target_dir: Target backup directory
            
        Returns:
            True if sync successful, False otherwise
        """
        source_path = source_dir / self.SLOT_LATEST
        target_path = target_dir / self.SLOT_LATEST
        
        if not source_path.exists():
            self.logger.warning(f"Source backup does not exist: {source_path}")
            return False
        
        self.logger.info(f"Syncing backup to {target_dir}")
        
        try:
            # Ensure target directory exists
            target_dir.mkdir(parents=True, exist_ok=True)
            
            result = subprocess.run(
                [
                    "rsync",
                    "-a",
                    "--delete",
                    f"{source_path}/",
                    f"{target_path}/"
                ],
                capture_output=True,
                text=True,
                timeout=5400  # 90 minute timeout (increased from 30 min)
            )
            
            if result.returncode == 0:
                self.logger.info(f"✅ Sync complete to {target_dir}")
                return True
            else:
                self.logger.error(f"Sync failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("Sync timed out after 90 minutes")
            return False
        except Exception as e:
            self.logger.error(f"Sync failed with exception: {e}")
            return False
    
    def perform_daily_backup(self) -> bool:
        """
        Perform the daily backup operation.
        
        This method:
        1. Rotates existing backups in all available locations
        2. Creates a new backup in the primary location
        3. Syncs the backup to secondary and tertiary locations
        
        Returns:
            True if backup successful, False otherwise
        """
        self.logger.info("=" * 60)
        self.logger.info("STARTING DAILY MONGODB BACKUP")
        self.logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)
        
        # Get available backup directories
        available_dirs = self._get_available_backup_dirs()
        
        if not available_dirs:
            self.logger.error("No backup directories available!")
            return False
        
        self.logger.info(f"Available backup locations: {len(available_dirs)}")
        for d in available_dirs:
            self.logger.info(f"  - {d}")
        
        # Perform rotation in all directories
        for backup_dir in available_dirs:
            if self._needs_rotation(backup_dir):
                self._perform_rotation(backup_dir)
            else:
                self.logger.info(f"Rotation already done today for {backup_dir}")
        
        # Create backup in the first available directory
        source_dir = available_dirs[0]
        backup_success = self._create_backup(source_dir)
        
        if not backup_success:
            self.logger.error("Failed to create backup in primary location")
            # Try secondary location
            if len(available_dirs) > 1:
                source_dir = available_dirs[1]
                self.logger.info(f"Attempting backup in secondary location: {source_dir}")
                backup_success = self._create_backup(source_dir)
        
        if not backup_success and len(available_dirs) > 2:
            # Try tertiary location if available
            source_dir = available_dirs[2]
            self.logger.info(f"Attempting backup in tertiary location: {source_dir}")
            backup_success = self._create_backup(source_dir)
        
        if not backup_success:
            self.logger.error("❌ BACKUP FAILED - Could not create backup in any location")
            return False
        
        # Sync to other locations
        for target_dir in available_dirs:
            if target_dir != source_dir:
                self._sync_backup(source_dir, target_dir)
        
        self.logger.info("=" * 60)
        self.logger.info("✅ DAILY BACKUP COMPLETED SUCCESSFULLY")
        self.logger.info("=" * 60)
        
        return True
    
    def get_backup_status(self) -> Dict[str, Any]:
        """
        Get the current status of all backups.
        
        Returns:
            Dictionary with backup status information
        """
        status = {
            "locations": [],
            "last_backup": None,
            "total_size_mb": 0
        }
        
        for backup_dir in [self.primary_dir, self.secondary_dir, self.tertiary_dir]:
            if backup_dir is None:
                continue
            
            location_status = {
                "path": str(backup_dir),
                "available": backup_dir.exists(),
                "slots": {}
            }
            
            if backup_dir.exists():
                for slot in [self.SLOT_LATEST, self.SLOT_YESTERDAY, 
                            self.SLOT_3DAYS, self.SLOT_5DAYS]:
                    slot_path = backup_dir / slot
                    if slot_path.exists():
                        # Get size
                        size = sum(f.stat().st_size for f in slot_path.rglob('*') if f.is_file())
                        size_mb = size / 1024 / 1024
                        
                        # Get modification time
                        mtime = datetime.fromtimestamp(slot_path.stat().st_mtime)
                        
                        location_status["slots"][slot] = {
                            "exists": True,
                            "size_mb": round(size_mb, 1),
                            "modified": mtime.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        status["total_size_mb"] += size_mb
                        
                        if slot == self.SLOT_LATEST:
                            if status["last_backup"] is None or mtime > status["last_backup"]:
                                status["last_backup"] = mtime
                    else:
                        location_status["slots"][slot] = {"exists": False}
            
            status["locations"].append(location_status)
        
        status["total_size_mb"] = round(status["total_size_mb"], 1)
        if status["last_backup"]:
            status["last_backup"] = status["last_backup"].strftime("%Y-%m-%d %H:%M:%S")
        
        return status
    
    def log_backup_status(self) -> None:
        """Log the current backup status."""
        status = self.get_backup_status()
        
        self.logger.info("=" * 60)
        self.logger.info("BACKUP STATUS")
        self.logger.info("=" * 60)
        
        for location in status["locations"]:
            self.logger.info(f"\n📁 {location['path']}")
            if not location["available"]:
                self.logger.warning("   ❌ Not available")
                continue
            
            for slot, info in location["slots"].items():
                if info["exists"]:
                    self.logger.info(f"   ✅ {slot}: {info['size_mb']} MB ({info['modified']})")
                else:
                    self.logger.info(f"   ⬜ {slot}: Not present")
        
        self.logger.info(f"\nTotal backup size: {status['total_size_mb']} MB")
        self.logger.info(f"Last backup: {status['last_backup'] or 'Never'}")
        self.logger.info("=" * 60)


if __name__ == "__main__":
    # Test the backup coordinator
    from .logger import setup_logger
    
    setup_logger(level="DEBUG", console_output=True)
    
    coordinator = BackupCoordinator()
    
    print("\n--- Backup Status ---\n")
    coordinator.log_backup_status()
    
    # Uncomment to test actual backup
    # print("\n--- Performing Backup ---\n")
    # coordinator.perform_daily_backup()
