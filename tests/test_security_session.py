"""Tests for the stateless session system and security middleware.

Covers:
- Signed-token creation / validation / tamper detection / expiry.
- Session-epoch revocation (logout / password change).
- Security response headers (CSP, X-Frame-Options, etc.).
- CSRF same-origin enforcement on mutating methods.
"""

from __future__ import annotations

import time

import pytest
from app.auth import (
    SESSION_MAX_AGE_SECONDS,
    _b64,
    _sign,
    _unb64,
    create_session,
    destroy_session,
    validate_session,
)
from app.security_middleware import (
    DEFAULT_SECURITY_HEADERS,
    CSRFMiddleware,
)

# ---------------------------------------------------------------------------
# Epoch helpers: keep these tests hermetic by stubbing the DB-backed epoch.
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_epoch(monkeypatch):
    """Pin the session epoch to a constant so no DB access is needed."""
    state = {"value": 7}

    async def _get():
        return state["value"]

    async def _bump():
        state["value"] += 1
        return state["value"]

    monkeypatch.setattr("app.auth._get_current_epoch", _get)
    monkeypatch.setattr("app.auth._bump_epoch", _bump)
    return state


# ---------------------------------------------------------------------------
# Signed-token primitives
# ---------------------------------------------------------------------------


def test_b64_roundtrip():
    """Base64 helpers round-trip arbitrary bytes including unicode."""
    raw = "héllo🔐\x00\x01".encode()
    assert _unb64(_b64(raw)) == raw


def test_sign_is_deterministic_and_secret_bound(monkeypatch):
    """Signature depends on the signing secret (deployment identity)."""
    monkeypatch.setattr("app.auth._signing_secret", lambda: b"secret-a")
    sig_a = _sign("payload")
    monkeypatch.setattr("app.auth._signing_secret", lambda: b"secret-b")
    sig_b = _sign("payload")
    assert sig_a != sig_b
    # Same secret reproduces the same signature.
    monkeypatch.setattr("app.auth._signing_secret", lambda: b"secret-a")
    assert _sign("payload") == sig_a


# ---------------------------------------------------------------------------
# create / validate / revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_validate_session(fixed_epoch):
    """A freshly created token validates successfully."""
    token = await create_session("admin")
    assert "." in token
    assert await validate_session(token) is True


@pytest.mark.asyncio
async def test_validate_rejects_garbage(fixed_epoch):
    """Malformed tokens are rejected without raising."""
    assert await validate_session("") is False
    assert await validate_session("not-a-token") is False
    assert await validate_session("aaa.bbb") is False  # bad signature


@pytest.mark.asyncio
async def test_validate_rejects_tampered_payload(fixed_epoch):
    """Changing the payload without re-signing invalidates the token."""
    token = await create_session("admin")
    payload_b64, _sig = token.rsplit(".", 1)
    # Flip a character in the payload but keep the (now stale) signature.
    tampered = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B")
    assert await validate_session(f"{tampered}.{_sign(tampered)}") in (False,)
    assert await validate_session(f"{tampered}.{_sig}") is False


@pytest.mark.asyncio
async def test_session_expires(fixed_epoch, monkeypatch):
    """Tokens past the max age are rejected."""
    token = await create_session("admin")

    real_time = time.time
    monkeypatch.setattr("app.auth.time.time", lambda: real_time() + SESSION_MAX_AGE_SECONDS + 1)
    assert await validate_session(token) is False


@pytest.mark.asyncio
async def test_logout_revokes_via_epoch(fixed_epoch):
    """Bumping the epoch (logout) invalidates previously issued tokens."""
    token = await create_session("admin")
    assert await validate_session(token) is True
    await destroy_session(token)
    assert await validate_session(token) is False


@pytest.mark.asyncio
async def test_new_session_works_after_revocation(fixed_epoch):
    """After revocation a fresh login still produces a valid token."""
    old = await create_session("admin")
    await destroy_session(old)
    new = await create_session("admin")
    assert new != old
    assert await validate_session(new) is True


# ---------------------------------------------------------------------------
# Security headers + CSRF (integration via the ASGI client)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_present(client):
    """Every default security header is attached to responses."""
    resp = await client.get("/api/health")
    for header in DEFAULT_SECURITY_HEADERS:
        assert header in resp.headers, f"missing security header: {header}"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in resp.headers["content-security-policy"]
    assert "script-src 'self' 'unsafe-inline'" in resp.headers["content-security-policy"]


def test_csrf_host_match_logic():
    """The hostname comparison helper matches hosts and rejects cross-origin."""
    assert CSRFMiddleware._host_matches("http://test/api", "test") is True
    assert CSRFMiddleware._host_matches("https://evil.example/x", "test") is False
    assert CSRFMiddleware._host_matches("not-a-url", "test") is False


@pytest.mark.asyncio
async def test_csrf_blocks_cross_origin_post(client):
    """A cross-origin POST is rejected with 403."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_csrf_allows_same_origin_post(client):
    """A same-origin POST is not blocked by the CSRF guard (reaches auth)."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "test-password"},
        headers={"Origin": "http://test"},
    )
    # CSRF must NOT block same-origin traffic. A non-403 code proves the request
    # was forwarded to the auth layer (200 on success or 401 on bad creds are
    # both acceptable; only 403 would indicate a CSRF false-positive).
    assert resp.status_code != 403
