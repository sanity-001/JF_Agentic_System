"""Logging module providing unified console and file logging."""

import logging
import sys
from pathlib import Path
from typing import Optional
from .config import Config


class Logger:
    """Singleton logger factory."""

    _loggers = {}

    @classmethod
    def get_logger(cls, name: str = 'ImageSensorProcessor',
                   log_file: Optional[str] = None,
                   level: str = None,
                   auto_log_file: bool = False) -> logging.Logger:
        """Get or create a named logger.

        Args:
            name: Logger name.
            log_file: Optional log file path.
            level: Log level (defaults to Config.LOG_LEVEL).
            auto_log_file: If True, auto-generate a timestamped log file
                           in output/logs/.

        Returns:
            Configured logging.Logger instance.
        """
        if name in cls._loggers:
            return cls._loggers[name]

        if auto_log_file and log_file is None:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = f'output/logs/process_{timestamp}.log'

        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level or Config.LOG_LEVEL))

        if not logger.handlers:
            # Console handler (INFO level)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                Config.LOG_FORMAT, datefmt=Config.LOG_DATE_FORMAT
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

            # File handler (DEBUG level), if specified
            if log_file:
                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setLevel(logging.DEBUG)
                file_formatter = logging.Formatter(
                    Config.LOG_FORMAT, datefmt=Config.LOG_DATE_FORMAT
                )
                file_handler.setFormatter(file_formatter)
                logger.addHandler(file_handler)

        cls._loggers[name] = logger
        return logger


class ProgressTracker:
    """Tracks iterative progress with configurable update intervals."""

    def __init__(self, total: int, description: str = "Processing",
                 update_interval: int = None):
        """Initialize progress tracker.

        Args:
            total: Total number of tasks.
            description: Task description.
            update_interval: Log every N updates.
        """
        self.total = total
        self.description = description
        self.update_interval = update_interval or Config.PROGRESS_UPDATE_INTERVAL
        self.current = 0
        self.logger = Logger.get_logger()

    def update(self, n: int = 1):
        """Increment progress by n steps."""
        self.current += n

        if self.current % self.update_interval == 0 or self.current == self.total:
            percentage = (self.current / self.total) * 100
            self.logger.info(f"{self.description}: {self.current}/{self.total} "
                           f"({percentage:.1f}%)")

    def finish(self):
        """Log completion."""
        self.logger.info(f"{self.description} completed: {self.current}/{self.total}")


# Convenience function
def get_logger(name: str = 'ImageSensorProcessor',
               log_file: Optional[str] = None,
               auto_log_file: bool = False) -> logging.Logger:
    """Convenience wrapper for Logger.get_logger."""
    return Logger.get_logger(name, log_file, auto_log_file=auto_log_file)
