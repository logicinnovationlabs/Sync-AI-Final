import logging
from typing import Optional

class Logger:
    """Application logger with structured logging."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def info(self, msg: str, **kwargs):
        """Log info message."""
        self.logger.info(msg, extra=kwargs)
    
    def error(self, msg: str, **kwargs):
        """Log error message."""
        self.logger.error(msg, extra=kwargs)
    
    def warning(self, msg: str, **kwargs):
        """Log warning message."""
        self.logger.warning(msg, extra=kwargs)
