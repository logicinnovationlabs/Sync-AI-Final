"""
Cursor Store - persists resume cursors for incremental sync.

Stores per-tenant, per-source:
- Resume cursor (Drive pageToken, Gmail historyId)
- Watch channel info (channel IDs, resource IDs, expiration)
- Last sync timestamp

Implemented as PostgreSQL table for durability (survives Redis flushes).
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, JSON, Index
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_

from app.models.base import Base, TimestampMixin
from app.storage.control_plane_db import ControlPlaneSessionLocal


class SyncCursor(Base, TimestampMixin):
    """
    Sync cursor model - stores resume cursors and watch info.
    
    Unique per (tenant_id, source_type).
    """
    __tablename__ = "sync_cursors"
    
    tenant_id: str = Column(String(255), primary_key=True, index=True)
    source_type: str = Column(String(100), primary_key=True, index=True)
    
    # Resume cursor (Drive pageToken or Gmail historyId)
    cursor: str = Column(String(500), nullable=True)
    
    # Watch/subscription info (JSON)
    watch_data: Dict[str, Any] = Column(JSON, nullable=True)
    
    # Watch expiration (milliseconds since epoch)
    watch_expiration: int = Column(BigInteger, nullable=True)
    
    # Last successful sync timestamp
    last_sync_at: datetime = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("ix_sync_cursors_expiration", "watch_expiration"),
    )


class CursorStore:
    """
    Cursor store service - manages sync cursors and watch info.
    """
    
    async def get_cursor(
        self,
        tenant_id: str,
        source_type: str,
    ) -> Optional[str]:
        """
        Get the stored resume cursor for a tenant/source.
        
        Args:
            tenant_id: Tenant identifier
            source_type: Source type (e.g., 'google_drive', 'google_gmail')
            
        Returns:
            Cursor string or None
        """
        async with ControlPlaneSessionLocal() as session:
            result = await session.execute(
                select(SyncCursor).where(
                    and_(
                        SyncCursor.tenant_id == tenant_id,
                        SyncCursor.source_type == source_type,
                    )
                )
            )
            record = result.scalar_one_or_none()
            return record.cursor if record else None
    
    async def update_cursor(
        self,
        tenant_id: str,
        source_type: str,
        cursor: str,
    ) -> None:
        """
        Update the resume cursor for a tenant/source.
        
        Args:
            tenant_id: Tenant identifier
            source_type: Source type
            cursor: New cursor value
        """
        async with ControlPlaneSessionLocal() as session:
            result = await session.execute(
                select(SyncCursor).where(
                    and_(
                        SyncCursor.tenant_id == tenant_id,
                        SyncCursor.source_type == source_type,
                    )
                )
            )
            record = result.scalar_one_or_none()
            
            if record:
                record.cursor = cursor
                record.last_sync_at = datetime.utcnow()
            else:
                record = SyncCursor(
                    tenant_id=tenant_id,
                    source_type=source_type,
                    cursor=cursor,
                    last_sync_at=datetime.utcnow(),
                )
                session.add(record)
            
            await session.commit()
    
    async def set_watch_info(
        self,
        tenant_id: str,
        source_type: str,
        watch_data: Dict[str, Any],
    ) -> None:
        """
        Store watch/subscription info for a tenant/source.
        
        Args:
            tenant_id: Tenant identifier
            source_type: Source type
            watch_data: Watch metadata (channel IDs, expiration, etc.)
        """
        expiration_ms = watch_data.get("expiration", 0)
        
        async with ControlPlaneSessionLocal() as session:
            result = await session.execute(
                select(SyncCursor).where(
                    and_(
                        SyncCursor.tenant_id == tenant_id,
                        SyncCursor.source_type == source_type,
                    )
                )
            )
            record = result.scalar_one_or_none()
            
            if record:
                record.watch_data = watch_data
                record.watch_expiration = expiration_ms
            else:
                record = SyncCursor(
                    tenant_id=tenant_id,
                    source_type=source_type,
                    watch_data=watch_data,
                    watch_expiration=expiration_ms,
                )
                session.add(record)
            
            await session.commit()
    
    async def get_watch_info(
        self,
        tenant_id: str,
        source_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get watch info for a tenant/source.
        
        Args:
            tenant_id: Tenant identifier
            source_type: Source type
            
        Returns:
            Watch data dict or None
        """
        async with ControlPlaneSessionLocal() as session:
            result = await session.execute(
                select(SyncCursor).where(
                    and_(
                        SyncCursor.tenant_id == tenant_id,
                        SyncCursor.source_type == source_type,
                    )
                )
            )
            record = result.scalar_one_or_none()
            return record.watch_data if record else None
    
    async def get_watch_by_channel(
        self,
        channel_id: str,
        resource_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Look up watch info by Drive channel ID and resource ID.
        
        Args:
            channel_id: Drive channel identifier
            resource_id: Drive resource identifier
            
        Returns:
            Dict with tenant_id, source_type, watch_data, or None
        """
        async with ControlPlaneSessionLocal() as session:
            result = await session.execute(select(SyncCursor))
            records = result.scalars().all()
            
            for record in records:
                if not record.watch_data:
                    continue
                
                if (
                    record.watch_data.get("channel_id") == channel_id
                    and record.watch_data.get("resource_id") == resource_id
                ):
                    return {
                        "tenant_id": record.tenant_id,
                        "source_type": record.source_type,
                        "watch_data": record.watch_data,
                    }
            
            return None
    
    async def get_watch_by_email(
        self,
        email_address: str,
        source_type: str = "google_gmail",
    ) -> Optional[Dict[str, Any]]:
        """
        Look up watch info by email address (for Gmail).
        
        Note: This is a simplified implementation. In production, you'd store
        a mapping of email -> tenant_id in the config dict or a separate table.
        
        Args:
            email_address: Gmail email address
            source_type: Source type (default: google_gmail)
            
        Returns:
            Dict with tenant_id, source_type, watch_data, or None
        """
        # For now, just return the first Gmail watch
        # In production, resolve email -> tenant_id via config
        async with ControlPlaneSessionLocal() as session:
            result = await session.execute(
                select(SyncCursor).where(SyncCursor.source_type == source_type)
            )
            record = result.scalar_one_or_none()
            
            if record:
                return {
                    "tenant_id": record.tenant_id,
                    "source_type": record.source_type,
                    "watch_data": record.watch_data,
                }
            
            return None
    
    async def get_expiring_watches(
        self,
        hours: int = 48,
    ) -> List[Dict[str, Any]]:
        """
        Get all watches expiring within N hours.
        
        Args:
            hours: Hours until expiration threshold
            
        Returns:
            List of dicts with tenant_id, source_type, watch_data
        """
        threshold_ms = int((datetime.utcnow() + timedelta(hours=hours)).timestamp() * 1000)
        
        async with ControlPlaneSessionLocal() as session:
            result = await session.execute(
                select(SyncCursor).where(
                    and_(
                        SyncCursor.watch_expiration.isnot(None),
                        SyncCursor.watch_expiration <= threshold_ms,
                    )
                )
            )
            records = result.scalars().all()
            
            return [
                {
                    "tenant_id": record.tenant_id,
                    "source_type": record.source_type,
                    "watch_data": record.watch_data,
                }
                for record in records
            ]


# Global cursor store instance
cursor_store = CursorStore()
