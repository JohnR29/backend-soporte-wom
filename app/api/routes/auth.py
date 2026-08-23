from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.backend_auth import get_user


bearer_scheme = HTTPBearer(auto_error=False)


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Bearer token required")
    user_id = get_user(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user_id