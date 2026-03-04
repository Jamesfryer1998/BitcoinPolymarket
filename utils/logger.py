"""
Centralized Logging Configuration
"""
import logging
import os
from datetime import datetime
from config import LOGS_DIR, LOG_LEVEL


class HourlyRotatingFileHandler(logging.Handler):
    """Custom handler that creates a new log file every hour"""

    def __init__(self):
        super().__init__()
        self.current_hour = None
        self.current_file = None

    def emit(self, record):
        """Emit a record to the appropriate hourly log file"""
        try:
            # Get current hour timestamp
            now = datetime.now()
            hour_stamp = now.strftime('%Y%m%d-%H')

            # Check if we need a new file
            if hour_stamp != self.current_hour:
                if self.current_file:
                    self.current_file.close()

                # Create new log file
                log_filename = f"all-{hour_stamp}.log"
                log_path = os.path.join(LOGS_DIR, log_filename)

                self.current_file = open(log_path, 'a', encoding='utf-8')
                self.current_hour = hour_stamp

            # Write log entry
            msg = self.format(record)
            self.current_file.write(msg + '\n')
            self.current_file.flush()

        except Exception:
            self.handleError(record)

    def close(self):
        """Close the current log file"""
        if self.current_file:
            self.current_file.close()
        super().close()


# Global logger instance
_logger = None


def setup_logger():
    """Configure and return the global logger"""
    global _logger

    if _logger is not None:
        return _logger

    # Create logger
    _logger = logging.getLogger('btc_trading')
    _logger.setLevel(getattr(logging, LOG_LEVEL))

    # Remove any existing handlers
    _logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)8s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Add hourly rotating file handler
    file_handler = HourlyRotatingFileHandler()
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)

    # Also add console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)

    return _logger


def get_logger(name=None):
    """
    Get a logger instance.

    Args:
        name (str, optional): Logger name (e.g., module name)

    Returns:
        logging.Logger: Logger instance
    """
    if _logger is None:
        setup_logger()

    if name:
        return _logger.getChild(name)
    return _logger
