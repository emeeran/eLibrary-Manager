"""Security middleware: HTTP security headers and same-origin CSRF defense.

Two concerns are addressed here:

1. **Security response headers** — CSP, X-Frame-Options, X-Content-Type-Options,
   Referrer-Policy and Permissions-Policy are attached to every response. The
   reader renders extracted ebook HTML, so a Content-Security-Policy is the
   single most valuable hardening control.

2. **CSRF defense-in-depth** — for state-changing requests (POST/PUT/PATCH/
   DELETE) we require that the request is same-origin. Session cookies already
   carry ``SameSite=Lax``, which blocks cross-site POSTs in modern browsers;
   the origin check here is a belt-and-braces fallback for legacy clients and
   direct header spoofing attempts.

Both checks are intentionally cheap (string compares, no I/O) so they are safe
to run on every request ahead of route dispatch.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.logging_config import get_logger

logger = get_logger(__name__)

# Methods that may mutate server state and therefore require a same-origin check.
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Paths exempt from the origin check (e.g. third-party webhooks, if any).
# Auth login is NOT exempt — it is the highest-value CSRF target.
CSRF_EXEMPT_PATHS: frozenset[str] = frozenset()

DEFAULT_SECURITY_HEADERS: dict[str, str] = {
    # Restrict everything by default; the reader needs inline styles (extracted
    # EPUB HTML + our own CSS) and images/data URIs for covers and renders.
    # 'self' covers same-origin static + covers + book-images mounts.
    #
    # NOTE: ``script-src`` includes ``'unsafe-inline'`` because the existing
    # Jinja templates embed inline ``<script>`` blocks and inline ``on*``
    # handlers (see docs/frontend-modernization.md). Migrating those to
    # external files + nonces is a follow-up; until then 'unsafe-inline' keeps
    # the app functional while the remaining CSP directives (default-src,
    # frame-ancestors, object-src, connect-src, etc.) still harden the surface.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": ("camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
    "X-Content-Security-Policy": "default-src 'self'",  # legacy IE fallback
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach browser security headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for header, value in DEFAULT_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin state-changing requests.

    Validates the ``Origin`` (preferred) or ``Referer`` header against the
    request's own host for mutating methods. SameSite cookies handle the
    common case in modern browsers; this guards the rest.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if (
            request.method in _MUTATING_METHODS
            and request.url.path not in CSRF_EXEMPT_PATHS
            and not self._is_same_origin(request)
        ):
            client = request.client.host if request.client else "?"
            logger.warning(
                "CSRF check failed: %s %s origin mismatch (client=%s)",
                request.method,
                request.url.path,
                client,
            )
            return JSONResponse(
                status_code=403,
                content={"error": "Cross-site request blocked", "message": "Invalid origin"},
            )
        return await call_next(request)

    @staticmethod
    def _is_same_origin(request: Request) -> bool:
        """Return True if the request is same-origin.

        Policy (OWASP Origin/Referer based CSRF, layered on SameSite cookies):
        - If ``Origin`` is present it MUST match the request host.
        - Else if ``Referer`` is present it MUST match.
        - If neither is present, allow: a cross-origin browser POST always
          sends ``Origin``, so absence means a non-browser client which is
          outside the CSRF threat model. SameSite cookies still protect us.
        """
        request_host = (
            request.url.hostname or (request.client.host if request.client else "")
        ).lower()
        if not request_host:
            return True  # cannot determine host; do not block blindly

        origin = request.headers.get("origin")
        if origin:
            return CSRFMiddleware._host_matches(origin, request_host)

        referer = request.headers.get("referer")
        if referer:
            return CSRFMiddleware._host_matches(referer, request_host)

        return True

    @staticmethod
    def _host_matches(url: str, request_host: str) -> bool:
        """Return True if the hostname component of *url* equals *request_host*."""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        host = (parsed.hostname or "").lower()
        return bool(host) and host == request_host
