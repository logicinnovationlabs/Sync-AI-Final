from datetime import datetime, timedelta
from typing import Optional

class DateUtils:
    """Date and time utilities."""
    
    @staticmethod
    def now_utc() -> datetime:
        """Get current UTC time."""
        return datetime.utcnow()
    
    @staticmethod
    def add_days(dt: datetime, days: int) -> datetime:
        """Add days to datetime."""
        return dt + timedelta(days=days)
    
    @staticmethod
    def diff_days(dt1: datetime, dt2: datetime) -> int:
        """Calculate difference in days between two datetimes."""
        return abs((dt1 - dt2).days)
    
    @staticmethod
    def format_iso(dt: datetime) -> str:
        """Format datetime as ISO string."""
        return dt.isoformat()
    
    @staticmethod
    def parse_iso(iso_str: str) -> Optional[datetime]:
        """Parse ISO string to datetime."""
        try:
            return datetime.fromisoformat(iso_str)
        except ValueError:
            return None
