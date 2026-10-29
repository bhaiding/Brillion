from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security import SessionClaims, admin_authorized, read_token

bearer = HTTPBearer(auto_error=False)


async def session_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SessionClaims:
    claims = read_token(credentials.credentials) if credentials else None
    if claims is None:
        raise HTTPException(401, "A valid room session token is required")
    return claims


async def websocket_claims(token: Annotated[str, Query()]) -> SessionClaims:
    claims = read_token(token)
    if claims is None:
        raise HTTPException(401, "A valid room session token is required")
    return claims


async def require_admin(x_admin_secret: Annotated[str | None, Header()] = None) -> None:
    if not admin_authorized(x_admin_secret):
        raise HTTPException(401, "Administrator authentication required")
