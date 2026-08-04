from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import jwt

security = HTTPBearer()

class AuthMiddleware:
    """Authentication middleware for FastAPI."""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
    
    async def __call__(self, request: Request) -> Optional[str]:
        """Verify JWT token and extract user ID."""
        credentials: HTTPAuthorizationCredentials = await security(request)
        token = credentials.credentials
        
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            user_id = payload.get('user_id')
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token"
                )
            return str(user_id)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

class TenantMiddleware:
    """Tenant isolation middleware."""
    
    async def __call__(self, request: Request) -> str:
        """Extract tenant_id from request headers."""
        tenant_id = request.headers.get('X-Tenant-ID')
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant-ID header required"
            )
        return tenant_id
