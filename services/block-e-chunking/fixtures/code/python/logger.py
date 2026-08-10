import logging
from typing import Optional
from datetime import datetime
import sys

class StructuredLogger:
    """Structured logging with context support."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
    
    def info(self, message: str, **context):
        """Log an info message with context."""
        self.logger.info(f"{message} {context or ''}")
    
    def error(self, message: str, **context):
        """Log an error message with context."""
        self.logger.error(f"{message} {context or ''}")
    
    def warning(self, message: str, **context):
        """Log a warning message with context."""
        self.logger.warning(f"{message} {context or ''}")
    
    def debug(self, message: str, **context):
        """Log a debug message with context."""
        self.logger.debug(f"{message} {context or ''}")
