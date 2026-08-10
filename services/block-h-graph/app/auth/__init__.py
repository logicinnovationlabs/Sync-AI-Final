"""Auth dependencies for Block H."""

from app.auth.jwt_auth import assert_tenant_binding, get_current_user, get_tenant, require_scopes

__all__ = [
    "assert_tenant_binding",
    "get_current_user",
    "get_tenant",
    "require_scopes",
]
