import json
from typing import Any, Dict, List
from datetime import datetime

class JSONSerializer:
    """JSON serialization utilities."""
    
    @staticmethod
    def serialize(obj: Any) -> str:
        """Serialize object to JSON string."""
        def default(o):
            if isinstance(o, datetime):
                return o.isoformat()
            raise TypeError(f"Object of type {type(o)} is not JSON serializable")
        return json.dumps(obj, default=default)
    
    @staticmethod
    def deserialize(json_str: str) -> Any:
        """Deserialize JSON string to object."""
        return json.loads(json_str)
