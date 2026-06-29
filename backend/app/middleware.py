"""Unified production middleware — logging, caching, and rate limiting."""

import asyncio
import os
import time
from collections import defaultdict
from collections.abc import Callable

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
    # Per-book hide/unhide run bcrypt verification — cap hard to throttle brute
    # force. Matched by exact-path suffix below so they don't affect reads.
    "/hide": (20, 60),
    "/unhide": (20, 60),
}

# Maximum period across all rate limits (for stale entry cleanup)
_MAX_PERIOD = max(period for _, period in RATE_LIMITS.values()) if RATE_LIMITS else 300

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
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        start_time = time.time()

        # 1. Rate limiting (before processing)
        response = await self._check_rate_limit(request)
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

    async def _check_rate_limit(self, request: Request) -> Response | None:
        """Check rate limit for the request. Returns 429 response if exceeded."""
        # Tests run many requests against the same process; the in-memory limiter
        # would otherwise trip across test boundaries. Auth middleware already
        # short-circuits under APP_ENV=testing for the same reason.
        if os.environ.get("APP_ENV") == "testing":
            return None
        path = request.url.path

        limit_config = None
        # Prefer exact matches over prefix matches so a broad prefix never
        # accidentally throttles unrelated sub-paths (e.g. "/hide" must not
        # limit "/api/books/{id}/chapter/...").
        if path in RATE_LIMITS:
            limit_config = RATE_LIMITS[path]
        else:
            for prefix, config in RATE_LIMITS.items():
                # Suffix-style keys (e.g. "/hide") match any path ending with them
                # but only when the prefix itself isn't a path-like key.
                if prefix.startswith("/") and not prefix.startswith("/api") and path.endswith(prefix):
                    limit_config = config
                    break

        if not limit_config:
            return None

        max_requests, period = limit_config
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{path}"

        now = time.time()
        async with self._lock:
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

        # Periodic cleanup of stale entries (every ~100 requests)
        if len(self._requests) > 100:
            stale_keys = [
                k for k, paths in self._requests.items()
                if all(not ts for ts in paths.values())
            ]
            for k in stale_keys:
                del self._requests[k]

        return None
