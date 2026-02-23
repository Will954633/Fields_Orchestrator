#!/usr/bin/env python3
"""
MongoDB Monitor Module for Fields Orchestrator
Last Updated: 26/01/2026, 7:52 PM (Brisbane Time)

Monitors MongoDB health and provides cooldown functionality to prevent
database instability from too many concurrent read/write operations.
"""

import os
import time
from datetime import datetime
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from .logger import get_logger


class MongoDBMonitor:
    """
    Monitors MongoDB connection health and manages cooldown periods.
    
    This class ensures MongoDB stability by:
    - Checking connection health before operations
    - Implementing cooldown periods between heavy operations
    - Retrying connections with exponential backoff
    """
    
    def __init__(
        self,
        uri: str = None,
        database: str = "property_data",
        health_check_timeout: int = 10,
        max_retries: int = 5,
        retry_delay: int = 30
    ):
        """
        Initialize the MongoDB monitor.
        
        Args:
            uri: MongoDB connection URI (defaults to MONGODB_URI env var or localhost)
            database: Database name to monitor
            health_check_timeout: Timeout for health checks in seconds
            max_retries: Maximum number of connection retries
            retry_delay: Delay between retries in seconds
        """
        # Use provided URI, or fall back to environment variable, or localhost
        if uri is None:
            uri = os.getenv('MONGODB_URI', 'mongodb://REDACTED:REDACTED@REDACTED.mongo.cosmos.azure.com:10255/')
        self.uri = uri
        self.database_name = database
        self.health_check_timeout = health_check_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = get_logger()
        self._client: Optional[MongoClient] = None
        self._last_operation_time: Optional[datetime] = None
        self._cooldown_end_time: Optional[datetime] = None
    
    def _get_client(self) -> MongoClient:
        """Get or create MongoDB client."""
        if self._client is None:
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.health_check_timeout * 1000
            )
        return self._client
    
    def check_connection(self) -> bool:
        """
        Check if MongoDB is reachable and responsive.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            client = self._get_client()
            # Ping the server
            client.admin.command('ping')
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            self.logger.warning(f"MongoDB connection check failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error checking MongoDB connection: {e}")
            return False
    
    def wait_for_connection(self) -> bool:
        """
        Wait for MongoDB to become available, with retries.
        
        Returns:
            True if connection established, False if all retries exhausted
        """
        for attempt in range(1, self.max_retries + 1):
            self.logger.info(f"Checking MongoDB connection (attempt {attempt}/{self.max_retries})...")
            
            if self.check_connection():
                self.logger.info("✅ MongoDB connection established")
                return True
            
            if attempt < self.max_retries:
                self.logger.warning(f"MongoDB not available. Retrying in {self.retry_delay} seconds...")
                time.sleep(self.retry_delay)
        
        self.logger.error("❌ Failed to connect to MongoDB after all retries")
        return False
    
    def get_server_status(self) -> Optional[Dict[str, Any]]:
        """
        Get MongoDB server status information.
        
        Returns:
            Server status dict or None if unavailable
        """
        try:
            client = self._get_client()
            status = client.admin.command('serverStatus')
            return {
                'uptime': status.get('uptime', 0),
                'connections': status.get('connections', {}),
                'opcounters': status.get('opcounters', {}),
                'mem': status.get('mem', {}),
            }
        except Exception as e:
            self.logger.error(f"Failed to get server status: {e}")
            return None
    
    def get_database_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get statistics for the property_data database.
        
        Returns:
            Database stats dict or None if unavailable
        """
        try:
            client = self._get_client()
            db = client[self.database_name]
            stats = db.command('dbStats')
            return {
                'collections': stats.get('collections', 0),
                'objects': stats.get('objects', 0),
                'dataSize': stats.get('dataSize', 0),
                'storageSize': stats.get('storageSize', 0),
                'indexes': stats.get('indexes', 0),
            }
        except Exception as e:
            self.logger.error(f"Failed to get database stats: {e}")
            return None
    
    def start_cooldown(self, duration_seconds: int, reason: str = "") -> None:
        """
        Start a cooldown period where no heavy operations should occur.
        
        Args:
            duration_seconds: Duration of cooldown in seconds
            reason: Reason for the cooldown (for logging)
        """
        self._cooldown_end_time = datetime.now()
        self._last_operation_time = datetime.now()
        
        reason_str = f" ({reason})" if reason else ""
        self.logger.info(f"🕐 Starting {duration_seconds}s cooldown{reason_str}...")
        
        # Actually wait for the cooldown
        time.sleep(duration_seconds)
        
        self._cooldown_end_time = None
        self.logger.info("✅ Cooldown complete")
    
    def is_in_cooldown(self) -> bool:
        """
        Check if currently in a cooldown period.
        
        Returns:
            True if in cooldown, False otherwise
        """
        if self._cooldown_end_time is None:
            return False
        return datetime.now() < self._cooldown_end_time
    
    def wait_for_cooldown(self) -> None:
        """Wait for any active cooldown to complete."""
        if self._cooldown_end_time is not None:
            remaining = (self._cooldown_end_time - datetime.now()).total_seconds()
            if remaining > 0:
                self.logger.info(f"Waiting {remaining:.0f}s for cooldown to complete...")
                time.sleep(remaining)
    
    def log_status(self) -> None:
        """Log current MongoDB status."""
        if not self.check_connection():
            self.logger.warning("MongoDB is not connected")
            return
        
        status = self.get_server_status()
        db_stats = self.get_database_stats()
        
        if status:
            self.logger.info(f"MongoDB Status:")
            self.logger.info(f"  Uptime: {status['uptime']/3600:.1f} hours")
            self.logger.info(f"  Current connections: {status['connections'].get('current', 'N/A')}")
            self.logger.info(f"  Operations - Insert: {status['opcounters'].get('insert', 0)}, "
                           f"Query: {status['opcounters'].get('query', 0)}, "
                           f"Update: {status['opcounters'].get('update', 0)}")
        
        if db_stats:
            self.logger.info(f"Database '{self.database_name}':")
            self.logger.info(f"  Collections: {db_stats['collections']}")
            self.logger.info(f"  Documents: {db_stats['objects']}")
            self.logger.info(f"  Data size: {db_stats['dataSize']/1024/1024:.1f} MB")
    
    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self.logger.debug("MongoDB connection closed")


if __name__ == "__main__":
    # Test the MongoDB monitor
    from .logger import setup_logger
    
    setup_logger(level="DEBUG", console_output=True)
    
    monitor = MongoDBMonitor()
    
    print("\n--- Testing MongoDB Monitor ---\n")
    
    # Test connection
    if monitor.wait_for_connection():
        monitor.log_status()
        
        # Test cooldown
        print("\n--- Testing Cooldown ---\n")
        monitor.start_cooldown(5, "Test cooldown")
        
    monitor.close()
