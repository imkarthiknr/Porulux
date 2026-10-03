from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .supabase import get_supabase_client

security = HTTPBearer()


@dataclass(frozen=True)
class AuthUser:
    id: str
    created_at: datetime | None


async def get_auth_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthUser:
    token = credentials.credentials
    client = get_supabase_client()
    try:
        response = client.auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if response.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthUser(id=response.user.id, created_at=getattr(response.user, "created_at", None))


async def get_current_user(user: AuthUser = Depends(get_auth_user)) -> str:
    return user.id
