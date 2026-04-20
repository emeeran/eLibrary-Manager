"""HTTP rate limiting middleware for expensive endpoints."""

import threading
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.logging_config import get_logger

logger = get_logger(__name__)

# Rate limit configuration: path prefix -> (max_requests, period_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/library/scan": (2, 60),        # 2 scans per minute
    "/api/library/import": (10, 60),      # 10 imports per minute
    "/api/library/upload": (10, 60),      # 10 uploads per minute
    "/api/library/auto-categorize": (2, 300),  # 2 categorizations per 5 min
    "/api/settings/test-ai": (5, 60),     # 5 AI tests per minute
    "/api/settings/backup": (3, 60),      # 3 backups per minute
    "/api/auth/login": (10, 60),          # 10 login attempts per minute
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting for expensive endpoints."""

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._requests: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Find matching rate limit rule
        limit_config = None
        for prefix, config in RATE_LIMITS.items():
            if path.startswith(prefix):
                limit_config = config
                break

        if not limit_config:
            return await call_next(request)

        max_requests, period = limit_config
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{path}"

        now = time.time()
        with self._lock:
            # Clean old entries
            self._requests[key][path] = [
                t for t in self._requests[key][path] if now - t < period
            ]

            if len(self._requests[key][path]) >= max_requests:
                logger.warning(f"Rate limit exceeded: {key} ({max_requests}/{period}s)")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate Limit Exceeded",
                        "message": f"Maximum {max_requests} requests per {period}s for this endpoint"
                    },
                    headers={"Retry-After": str(period)}
                )

            self._requests[key][path].append(now)

        return await call_next(request)
