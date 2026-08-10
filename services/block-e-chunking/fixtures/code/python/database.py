import asyncpg
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

class DatabaseManager:
    """Manages database connections and queries."""
    
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize the connection pool."""
        self.pool = await asyncpg.create_pool(self.dsn, min_size=5, max_size=20)
    
    async def close(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the pool."""
        async with self.pool.acquire() as conn:
            yield conn
    
    async def fetch_one(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Fetch a single row."""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None
    
    async def fetch_many(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetch multiple rows."""
        async with self.get_connection() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query and return the status."""
        async with self.get_connection() as conn:
            return await conn.execute(query, *args)
