"""
Simple database client wrapper for psycopg2.
Used by EncryptionClient for real database connections.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from typing import Optional, Tuple, Any, List
import logging

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Simple database client for psycopg2."""
    
    def __init__(self, connection_string: str):
        """
        Initialize database client.
        
        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self._conn = None
    
    def connect(self):
        """Establish database connection."""
        if not self._conn or self._conn.closed:
            self._conn = psycopg2.connect(self.connection_string)
            self._conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return self._conn
    
    def close(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
    
    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[Any]:
        """
        Execute a query and fetch one result.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            First row as result, or None
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
            result = cursor.fetchone()
            
            if result:
                # Convert to dict-like object for attribute access
                columns = [desc[0] for desc in cursor.description]
                return Row(result, columns)
            return None
        finally:
            cursor.close()
    
    def fetch_all(self, query: str, params: Tuple = ()) -> List[Any]:
        """
        Execute a query and fetch all results.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            List of rows
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            if results:
                columns = [desc[0] for desc in cursor.description]
                return [Row(row, columns) for row in results]
            return []
        finally:
            cursor.close()
    
    def execute(self, query: str, params: Tuple = ()):
        """
        Execute a query without returning results.
        
        Args:
            query: SQL query
            params: Query parameters
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
        finally:
            cursor.close()


class Row:
    """Row object that allows both dict and attribute access."""
    
    def __init__(self, data: Tuple, columns: List[str]):
        self._data = data
        self._columns = columns
        self._dict = dict(zip(columns, data))
    
    def __getattr__(self, name: str) -> Any:
        if name in self._dict:
            return self._dict[name]
        raise AttributeError(f"'Row' object has no attribute '{name}'")
    
    def __getitem__(self, key: str) -> Any:
        return self._dict[key]
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._dict.get(key, default)
    
    def __repr__(self) -> str:
        return f"Row({self._dict})"
