"""Unified production middleware — logging, caching, and rate limiting."""

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
    "/api/library/scan": (2, 60),
    "/api/library/import": (10, 60),
    "/api/library/upload": (10, 60),
    "/api/library/auto-categorize": (2, 300),
    "/api/settings/test-ai": (5, 60),
    "/api/settings/backup": (3, 60),
    "/api/auth/login": (10, 60),
}

# Cache-Control rules for static assets
CACHE_RULES: dict[str, str] = {
    "/static/": "public, max-age=86400",
    "/covers/": "public, max-age=86400",
    "/book-images/": "public, max-age=604800",
}


class ProductionMiddleware(BaseHTTPMiddleware):
    """Combined logging, cache-control, and rate-limiting middleware."""

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._requests: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        start_time = time.time()

        # 1. Rate limiting (before processing)
        response = self._check_rate_limit(request)
        if response:
            return response

        # 2. Process request
        response = await call_next(request)
        duration = time.time() - start_time

        # 3. Add Cache-Control headers
        for prefix, cache_value in CACHE_RULES.items():
            if path.startswith(prefix):
                response.headers["Cache-Control"] = cache_value
                break

        # 4. Log — warn on slow requests, debug otherwise
        if duration > 2.0:
            logger.warning(
                f"Slow request: {request.method} {path} — {response.status_code} ({duration:.3f}s)"
            )
        else:
            logger.debug(f"{request.method} {path} — {response.status_code} ({duration:.3f}s)")

        return response

    def _check_rate_limit(self, request: Request) -> Response | None:
        """Check rate limit for the request. Returns 429 response if exceeded."""
        path = request.url.path

        limit_config = None
        for prefix, config in RATE_LIMITS.items():
            if path.startswith(prefix):
                limit_config = config
                break

        if not limit_config:
            return None

        max_requests, period = limit_config
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{path}"

        now = time.time()
        with self._lock:
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

        return None
