"""Utility functions for the application."""
import json
from datetime import datetime, date
from typing import Any, Dict

def format_date(dt: datetime, format: str = "%Y-%m-%d") -> str:
    """Format a datetime object as a string."""
    return dt.strftime(format)

def parse_json(data: str) -> Dict[str, Any]:
    """Parse a JSON string into a dictionary."""
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return {}

def serialize_json(data: Dict[str, Any]) -> str:
    """Serialize a dictionary to JSON string."""
    return json.dumps(data, default=str)

def snake_to_camel(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def camel_to_snake(camel_str: str) -> str:
    """Convert camelCase to snake_case."""
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', camel_str).lower()

def paginate(items: list, page: int, page_size: int) -> tuple:
    """Paginate a list of items."""
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], len(items)

def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing special characters."""
    import re
    return re.sub(r'[^\w\s-]', '', filename).strip()
