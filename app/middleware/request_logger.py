import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.utils.logger import logger


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.time()
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        response = await call_next(request)

        duration_ms = int((time.time() - start) * 1000)
        logger.info(f"{method} {path} {response.status_code} {duration_ms}ms [{client_ip}]")

        return response
