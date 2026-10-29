import hashlib
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.realtime import hub


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed fixed-window limiting shared by every API instance."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in {"POST", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
            client = request.client.host if request.client else "unknown"
            identity = hashlib.sha256(client.encode()).hexdigest()[:20]
            sensitive = request.url.path.endswith("/join") or request.url.path == "/api/rooms"
            limit = 12 if sensitive else 90
            bucket = int(time.time() // 60)
            key = f"rate:{identity}:{bucket}:{'sensitive' if sensitive else 'mutate'}"
            try:
                count = await hub.redis.incr(key)
                if count == 1:
                    await hub.redis.expire(key, 70)
                if count > limit:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests; please wait a moment"},
                        headers={"Retry-After": "60"},
                    )
            except Exception:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Realtime coordination is temporarily unavailable"},
                )
        return await call_next(request)
