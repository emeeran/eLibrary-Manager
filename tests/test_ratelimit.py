"""Hermetic tests for the ProductionMiddleware rate limiter.

The global ASGI test client disables rate limiting under ``APP_ENV=testing`` so
the rest of the suite is not polluted by the in-memory counter. These tests
exercise the limiter directly against a throwaway ASGI app so the behaviour is
still covered.
"""

from __future__ import annotations

import os

import pytest
from app.middleware import ProductionMiddleware
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


def _ok(_request):
    return JSONResponse({"ok": True})


def _build_app():
    app = Starlette(routes=[Route("/api/library/scan", _ok, methods=["POST"])])
    app.add_middleware(ProductionMiddleware)
    return app


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_threshold(monkeypatch):
    """Requests beyond the configured threshold are rejected with 429."""
    # Force the limiter on even though pytest sets APP_ENV=testing.
    monkeypatch.delenv("APP_ENV", raising=False)

    from httpx import ASGITransport, AsyncClient

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        codes = []
        # /api/library/scan is capped at 2 per 60s.
        for _ in range(4):
            r = await ac.post("/api/library/scan")
            codes.append(r.status_code)
    # First two pass, subsequent ones are limited.
    assert codes[:2] == [200, 200]
    assert codes[2:] == [429, 429]


@pytest.mark.asyncio
async def test_rate_limit_skip_in_testing():
    """Under APP_ENV=testing the limiter is a no-op (no cross-test pollution)."""
    prior = os.environ.get("APP_ENV")
    os.environ["APP_ENV"] = "testing"
    try:
        from httpx import ASGITransport, AsyncClient

        app = _build_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            codes = [await ac.post("/api/library/scan") for _ in range(5)]
            assert all(c.status_code == 200 for c in codes)
    finally:
        # Restore prior state rather than unconditionally popping — the rest of
        # the suite relies on APP_ENV=testing (AuthMiddleware skips auth under
        # it), and popping it here leaked into later tests.
        if prior is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = prior
