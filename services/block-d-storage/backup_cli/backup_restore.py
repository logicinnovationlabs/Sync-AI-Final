"""
Backup/Restore - Per-schema backup and restore operations.
Per spec: backup_tenant(tenant_id) dumps schema tenant_<id> only.
restore_tenant(tenant_id, backup_id) restores into a schema, does not touch other tenants' schemas.
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# In-memory storage for backup metadata and data (Phase 1/2)
_backup_metadata_store: Dict[str, BackupMetadata] = {}
_backup_data_store: Dict[str, str] = {}


@dataclass
class BackupMetadata:
    """Metadata for a backup operation"""
    backup_id: str
    tenant_id: str
    schema_name: str
    timestamp: datetime
    row_count: int
    checksum: str
    size_bytes: int


def backup_tenant(db_client, tenant_id: str) -> BackupMetadata:
    """
    Backup a tenant's schema.
    
    Dumps schema `tenant_<id>` only. Does not touch other tenants' schemas.
    
    Args:
        db_client: Database client
        tenant_id: The tenant identifier
        
    Returns:
        BackupMetadata with backup details including checksum
    """
    schema_name = f"tenant_{tenant_id}"
    backup_id = f"backup_{tenant_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    
    logger.info(f"Starting backup for tenant {tenant_id} (schema: {schema_name})")
    
    # In real implementation, this would:
    # 1. Use pg_dump to dump the schema
    # 2. Store the dump in object storage with the backup_id
    # 3. Calculate checksum of the dump
    
    # For Phase 1 with mocks, we'll simulate this
    schema_data = _dump_schema(db_client, schema_name)
    
    # Calculate checksum
    checksum = _calculate_checksum(schema_data)
    
    # Count rows (simulated)
    row_count = _count_schema_rows(db_client, schema_name)
    
    # Size in bytes (simulated)
    size_bytes = len(schema_data.encode('utf-8')) if schema_data else 0
    
    metadata = BackupMetadata(
        backup_id=backup_id,
        tenant_id=tenant_id,
        schema_name=schema_name,
        timestamp=datetime.now(timezone.utc),
        row_count=row_count,
        checksum=checksum,
        size_bytes=size_bytes
    )
    
    # Store metadata and data for later retrieval (Phase 1/2)
    _backup_metadata_store[backup_id] = metadata
    _backup_data_store[backup_id] = schema_data
    
    logger.info(f"Backup complete: {backup_id}, rows: {row_count}, checksum: {checksum}")
    
    return metadata


def restore_tenant(db_client, tenant_id: str, backup_id: str) -> BackupMetadata:
    """
    Restore a tenant's schema from a backup.
    
    Restores into a schema, does not touch other tenants' schemas.
    
    Args:
        db_client: Database client
        tenant_id: The tenant identifier
        backup_id: The backup identifier to restore from
        
    Returns:
        BackupMetadata of the restored backup
    """
    schema_name = f"tenant_{tenant_id}"
    
    logger.info(f"Starting restore for tenant {tenant_id} from backup {backup_id}")
    
    # In real implementation, this would:
    # 1. Retrieve the backup dump from object storage
    # 2. Drop the existing schema (if any)
    # 3. Recreate the schema
    # 4. Restore the data from the dump
    # 5. Verify checksum
    
    # For Phase 1 with mocks, we'll simulate this
    backup_metadata = _retrieve_backup_metadata(backup_id)
    
    # Verify backup belongs to this tenant
    if backup_metadata.tenant_id != tenant_id:
        raise ValueError(f"Backup {backup_id} belongs to tenant {backup_metadata.tenant_id}, not {tenant_id}")
    
    # Restore the schema
    _restore_schema(db_client, schema_name, backup_id)
    
    logger.info(f"Restore complete: {backup_id} restored to schema {schema_name}")
    
    return backup_metadata


def _dump_schema(db_client, schema_name: str) -> str:
    """
    Dump a schema's data.
    
    In real implementation, this would use pg_dump.
    For Phase 2, dumps actual table data as JSON.
    """
    # Get all tables in the schema
    query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
    """
    tables = db_client.fetch_all(query, (schema_name,))
    
    # Dump each table's data
    dump_data = {}
    for table in tables:
        table_name = table['table_name']
        data_query = f"SELECT * FROM {schema_name}.{table_name} ORDER BY id"  # Ensure consistent ordering
        rows = db_client.fetch_all(data_query, ())
        # Convert Row objects to dictionaries
        dump_data[table_name] = [row.to_dict() for row in rows]
    
    import json
    # Use sorted keys and default=str for consistent checksums (handles datetime)
    return json.dumps(dump_data, default=str, sort_keys=True)


def _count_schema_rows(db_client, schema_name: str) -> int:
    """
    Count total rows in a schema.
    
    In real implementation, this would query all tables in the schema.
    For Phase 1 with mocks, returns a simulated count.
    For Phase 2 with real DB, counts actual rows.
    """
    try:
        # Query all tables in the schema
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
        """
        tables = db_client.fetch_all(query, (schema_name,))
        
        total_rows = 0
        for table in tables:
            table_name = table['table_name']
            count_query = f"SELECT COUNT(*) as count FROM {schema_name}.{table_name}"
            result = db_client.fetch_one(count_query, ())
            if result:
                total_rows += result['count']
        
        return total_rows
    except Exception as e:
        logger.warning(f"Failed to count schema rows: {e}")
        return 0


def _calculate_checksum(data: str) -> str:
    """Calculate SHA256 checksum of data"""
    import json
    # Normalize JSON to ensure consistent checksums
    if data.startswith('{'):
        parsed = json.loads(data)
        normalized = json.dumps(parsed, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def _retrieve_backup_metadata(backup_id: str) -> BackupMetadata:
    """
    Retrieve backup metadata from storage.
    
    In real implementation, this would query object storage.
    For Phase 1, retrieves from in-memory store.
    """
    if backup_id in _backup_metadata_store:
        return _backup_metadata_store[backup_id]
    
    # Fallback to parsing if not in store (shouldn't happen in normal flow)
    parts = backup_id.split('_')
    if len(parts) >= 3:
        tenant_id = '_'.join(parts[1:-3])
    else:
        tenant_id = "unknown"
    
    return BackupMetadata(
        backup_id=backup_id,
        tenant_id=tenant_id,
        schema_name=f"tenant_{tenant_id}",
        timestamp=datetime.now(timezone.utc),
        row_count=0,
        checksum="simulated_checksum",
        size_bytes=0
    )


def _restore_schema(db_client, schema_name: str, backup_id: str):
    """
    Restore a schema from a backup.
    
    For Phase 2:
    1. Drop existing schema
    2. Recreate schema
    3. Restore data from backup dump (JSON)
    """
    # Drop existing schema
    drop_query = f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"
    db_client.execute(drop_query, ())
    
    # Recreate schema
    create_query = f"CREATE SCHEMA {schema_name}"
    db_client.execute(create_query, ())
    
    # Restore data from backup data store
    import json
    if backup_id in _backup_data_store:
        schema_data = _backup_data_store[backup_id]
        dump_data = json.loads(schema_data)
        
        # Recreate tables and insert data
        for table_name, rows in dump_data.items():
            if not rows:
                continue
                
            # Get column names and types from first row
            first_row = rows[0]
            columns = []
            for col, val in first_row.items():
                if col == 'id':
                    columns.append(f"{col} INTEGER PRIMARY KEY")  # Use INTEGER instead of SERIAL to preserve IDs
                elif isinstance(val, int):
                    columns.append(f"{col} INTEGER")
                elif isinstance(val, str):
                    columns.append(f"{col} TEXT")
                else:
                    columns.append(f"{col} TEXT")
            
            # Create table
            col_defs = ", ".join(columns)
            create_table_query = f"CREATE TABLE {schema_name}.{table_name} ({col_defs})"
            try:
                db_client.execute(create_table_query, ())
            except Exception as e:
                logger.warning(f"Failed to create table {table_name}: {e}")
                continue
            
            # Insert data (include all columns including id to preserve exact data)
            # Sort by id to ensure consistent ordering
            rows_sorted = sorted(rows, key=lambda x: x.get('id', 0))
            for row in rows_sorted:
                insert_cols = list(row.keys())
                values = [row.get(col) for col in insert_cols]
                if insert_cols:
                    placeholders = ", ".join(["%s"] * len(insert_cols))
                    insert_query = f"INSERT INTO {schema_name}.{table_name} ({', '.join(insert_cols)}) VALUES ({placeholders})"
                    try:
                        db_client.execute(insert_query, tuple(values))
                    except Exception as e:
                        logger.warning(f"Failed to insert row into {table_name}: {e}")
                        # Try with ISO format for datetime
                        try:
                            values_iso = [col if not isinstance(col, str) or not col.endswith('+00:00') else col.replace('+00:00', 'Z') for col in values]
                            db_client.execute(insert_query, tuple(values_iso))
                        except Exception as e2:
                            logger.warning(f"Failed to insert row with ISO format: {e2}")
        
        logger.info(f"Restored {len(dump_data)} tables to schema {schema_name}")
    else:
        logger.warning(f"No backup data found for {backup_id}")
    
    logger.debug(f"Schema {schema_name} recreated for restore from {backup_id}")
