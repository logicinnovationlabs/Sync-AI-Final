"""Database manager for connection pooling and queries."""
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from typing import List, Dict, Any

class DatabaseManager:
    """Manages database connections and queries."""
    
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
    
    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool."""
        conn = self.connection_pool.getconn()
        try:
            yield conn
        finally:
            self.connection_pool.putconn(conn)
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount
