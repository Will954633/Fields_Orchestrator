#!/usr/bin/env python3
"""
Logger Module for Fields Orchestrator
Last Updated: 26/01/2026, 7:52 PM (Brisbane Time)

Provides centralized logging functionality with file rotation and console output.
Supports colored console output for better readability.
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# ANSI color codes for console output
class Colors:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels."""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.BLUE,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.MAGENTA + Colors.BOLD,
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors."""
        # Add color to the level name
        color = self.LEVEL_COLORS.get(record.levelno, Colors.WHITE)
        record.levelname = f"{color}{record.levelname}{Colors.RESET}"
        
        # Add timestamp in Brisbane timezone
        record.brisbane_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return super().format(record)


class PlainFormatter(logging.Formatter):
    """Plain formatter for file output (no colors)."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record without colors."""
        record.brisbane_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return super().format(record)


# Global logger instance
_logger: Optional[logging.Logger] = None


def setup_logger(
    name: str = "orchestrator",
    log_file: Optional[str] = None,
    level: str = "INFO",
    max_size_mb: int = 10,
    backup_count: int = 5,
    console_output: bool = True
) -> logging.Logger:
    """
    Set up and configure the logger.
    
    Args:
        name: Logger name
        log_file: Path to log file (relative to base_dir or absolute)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        max_size_mb: Maximum log file size in MB before rotation
        backup_count: Number of backup log files to keep
        console_output: Whether to output to console
        
    Returns:
        Configured logger instance
    """
    global _logger
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console format with colors
    console_format = "%(brisbane_time)s | %(levelname)s | %(message)s"
    
    # File format without colors
    file_format = "%(brisbane_time)s | %(levelname)s | %(name)s | %(message)s"
    
    # Add console handler if requested
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredFormatter(console_format))
        logger.addHandler(console_handler)
    
    # Add file handler if log file specified
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        if not log_path.is_absolute():
            base_dir = Path(__file__).parent.parent
            log_path = base_dir / log_file
        
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create rotating file handler
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(PlainFormatter(file_format))
        logger.addHandler(file_handler)
    
    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """
    Get the global logger instance.
    
    Returns:
        Logger instance (creates default if not set up)
    """
    global _logger
    
    if _logger is None:
        _logger = setup_logger()
    
    return _logger


def log_step_start(step_id: int, step_name: str) -> None:
    """Log the start of a pipeline step."""
    logger = get_logger()
    logger.info(f"{'='*60}")
    logger.info(f"STEP {step_id}: {step_name}")
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"{'='*60}")


def log_step_complete(step_id: int, step_name: str, duration_seconds: float, success: bool) -> None:
    """Log the completion of a pipeline step."""
    logger = get_logger()
    status = "✅ COMPLETED" if success else "❌ FAILED"
    duration_str = f"{duration_seconds/60:.1f} minutes" if duration_seconds >= 60 else f"{duration_seconds:.0f} seconds"
    
    logger.info(f"STEP {step_id}: {step_name} - {status}")
    logger.info(f"Duration: {duration_str}")
    logger.info(f"{'-'*60}")


def log_pipeline_start() -> None:
    """Log the start of the entire pipeline."""
    logger = get_logger()
    logger.info(f"{'#'*60}")
    logger.info(f"FIELDS PROPERTY DATA PIPELINE STARTED")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Brisbane)")
    logger.info(f"{'#'*60}")


def log_pipeline_complete(total_duration_seconds: float, steps_completed: int, steps_failed: int) -> None:
    """Log the completion of the entire pipeline."""
    logger = get_logger()
    duration_str = f"{total_duration_seconds/3600:.1f} hours" if total_duration_seconds >= 3600 else f"{total_duration_seconds/60:.1f} minutes"
    
    logger.info(f"{'#'*60}")
    logger.info(f"FIELDS PROPERTY DATA PIPELINE COMPLETED")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Brisbane)")
    logger.info(f"Total Duration: {duration_str}")
    logger.info(f"Steps Completed: {steps_completed}")
    logger.info(f"Steps Failed: {steps_failed}")
    logger.info(f"{'#'*60}")


if __name__ == "__main__":
    # Test the logger
    logger = setup_logger(
        log_file="logs/test.log",
        level="DEBUG",
        console_output=True
    )
    
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
    
    log_pipeline_start()
    log_step_start(1, "Test Step")
    log_step_complete(1, "Test Step", 125.5, True)
    log_pipeline_complete(3600, 7, 0)
