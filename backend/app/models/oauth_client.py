"""
OAuth client and refresh token models - per-tenant database.

Supports OAuth 2.1: authorization_code+PKCE, refresh_token, client_credentials.
"""

from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class OAuthClient(Base, TimestampMixin):
    """
    OAuth 2.1 client registration (per-tenant database).
    """

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    hashed_secret: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt-hashed client secret",
    )
    client_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="'confidential' or 'public'",
    )
    redirect_uris: Mapped[list] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
    )

    def __repr__(self) -> str:
        return f"<OAuthClient(client_id={self.client_id}, type={self.client_type})>"


class RefreshToken(Base, TimestampMixin):
    """
    Refresh token storage (per-tenant database).
    
    Tokens are stored hashed; revocation is tracked via the 'revoked' flag.
    """

    __tablename__ = "refresh_tokens"

    token_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
        comment="UUID jti claim from JWT",
    )
    principal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.principal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    hashed_token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="bcrypt-hashed refresh token",
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.token_id}, revoked={self.revoked})>"
