import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.config.settings import settings
from app.utils.logger import logger

_request_counts: dict = defaultdict(list)

# IPs that are never rate-limited (localhost / loopback)
_EXEMPT_IPS = {"127.0.0.1", "::1", "localhost"}

# Admin panel / docs paths that should never be rate-limited
_EXEMPT_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi",
    "/admin",
)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"

        # Always exempt localhost and admin paths
        if client_ip in _EXEMPT_IPS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        # Exempt requests with a valid Bearer token (admin panel users)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        now = time.time()
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        max_req = settings.RATE_LIMIT_MAX_REQUESTS

        # Clean old timestamps outside the window
        _request_counts[client_ip] = [
            t for t in _request_counts[client_ip] if now - t < window
        ]

        if len(_request_counts[client_ip]) >= max_req:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": "Too many requests, please try again later"},
            )

        _request_counts[client_ip].append(now)
        return await call_next(request)
