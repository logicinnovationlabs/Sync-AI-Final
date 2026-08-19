"""
Custom exceptions for the platform.
"""


class SnyQException(Exception):
    """Base exception for all SnyQ errors."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class TenantNotFoundError(SnyQException):
    """Raised when a tenant cannot be resolved."""

    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant not found: {tenant_id}", status_code=404)
        self.tenant_id = tenant_id


class UnauthorizedError(SnyQException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status_code=401)


class ForbiddenError(SnyQException):
    """Raised when authorization fails (e.g., missing scopes)."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status_code=403)


class RevokedTokenError(SnyQException):
    """Raised when a token has been revoked."""

    def __init__(self, jti: str):
        super().__init__(f"Token has been revoked: {jti}", status_code=401)
        self.jti = jti


class InvalidTokenError(SnyQException):
    """Raised when a token is malformed or invalid."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message, status_code=401)


# Back-compat aliases for legacy signoff tests
TokenInvalidError = InvalidTokenError


class TokenExpiredError(SnyQException):
    """Raised when a token has expired."""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message, status_code=401)


class CrossTenantAccessError(SnyQException):
    """Raised when cross-tenant access is attempted."""

    def __init__(self, source_tenant: str, target_tenant: str):
        super().__init__(
            f"Cross-tenant access denied: {source_tenant} -> {target_tenant}",
            status_code=403,
        )
        self.source_tenant = source_tenant
        self.target_tenant = target_tenant


class VaultError(SnyQException):
    """Raised when vault operations fail."""

    def __init__(self, message: str):
        super().__init__(f"Vault error: {message}", status_code=500)


class SCIMSyncError(SnyQException):
    """Raised when SCIM sync fails."""

    def __init__(self, message: str):
        super().__init__(f"SCIM sync error: {message}", status_code=500)
