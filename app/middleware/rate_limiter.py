import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.config.settings import settings
from app.utils.logger import logger

_request_counts: dict = defaultdict(list)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
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
