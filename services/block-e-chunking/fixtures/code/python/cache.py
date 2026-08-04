import redis.asyncio as redis
from typing import Optional, Any
import json
from datetime import timedelta

class CacheManager:
    """Manages caching with Redis."""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Connect to Redis."""
        self.client = await redis.from_url(self.redis_url, decode_responses=True)
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        value = await self.client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in cache."""
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        return await self.client.set(key, value, ex=ttl)
    
    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        return await self.client.delete(key) > 0
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return await self.client.exists(key) > 0
