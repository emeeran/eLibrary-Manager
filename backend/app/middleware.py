"""Custom middleware."""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging_config import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses.

    Logs all incoming requests and their responses with timing information.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """Log request and response.

        Args:
            request: Incoming request
            call_next: Next middleware/ route handler

        Returns:
            Response from route handler
        """
        start_time = time.time()

        # Log request
        logger.info(
            f"Request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "client": request.client.host if request.client else None
            }
        )

        # Process request
        response = await call_next(request)

        # Log response
        duration = time.time() - start_time
        logger.info(
            f"Response: {response.status_code} ({duration:.3f}s)",
            extra={
                "status_code": response.status_code,
                "duration": duration,
                "method": request.method,
                "path": request.url.path
            }
        )

        return response
