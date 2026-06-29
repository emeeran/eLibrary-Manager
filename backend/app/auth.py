"""Session-based authentication for eLibrary Manager.

Stateless signed-cookie sessions.

Design
------
Sessions are NOT held in server memory. A session token is a signed
(HMAC-SHA256), base64-encoded JSON payload::

    {"u": "<username>", "iat": <issued unix-ts>, "e": "<epoch at issue>"}

Validation is pure crypto (no DB / no shared state) so it is correct under any
number of workers and survives process restarts — previously the admin was
logged out on every deploy.

Real revocation (logout / password change) is provided by a monotonically
increasing **session epoch** persisted in the settings table. A token is only
valid while its stamped epoch equals the current epoch. Bumping the epoch
invalidates every previously issued token. For a single-admin application this
is exactly the desired behaviour.

The epoch is read through a short-lived in-process cache (``_EPOCH_CACHE_TTL``)
to keep the request hot-path cheap.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from functools import lru_cache

from app.config import get_config
from app.logging_config import get_logger
from app.security import encrypt_password, verify_password

logger = get_logger(__name__)

SESSION_COOKIE_NAME = "elib_session"
SESSION_MAX_AGE_SECONDS = 86400  # 24 hours

# Session epoch — bumped to invalidate all outstanding tokens.
_EPOCH_SETTING_KEY = "session_epoch"
_EPOCH_CACHE_TTL = 5.0  # seconds
_epoch_cache: dict[str, float | int] = {"value": 0, "fetched_at": 0.0}
_epoch_lock = asyncio.Lock()


def _signing_secret() -> bytes:
    """Return the bytes used to sign session tokens.

    Derived from the app ``SECRET_KEY`` (falling back to the DB url in dev) so
    token validity is coupled to the deployment identity.
    """
    config = get_config()
    return (config.secret_key or config.database_url).encode("utf-8")


def _b64(raw: bytes) -> str:
    """URL-safe base64 encoding without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    """URL-safe base64 decoding, padding-tolerant."""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str) -> str:
    """Return the HMAC-SHA256 signature of a base64 payload string."""
    return _b64(hmac.new(_signing_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())


def _get_password_hash() -> str:
    """Get or derive the admin password hash.

    Priority:
    1. admin_password_hash from config (bcrypt hash)
    2. admin_password from config (plaintext, auto-hashed)
    3. Generate a random default and log it

    Returns:
        str: bcrypt password hash
    """
    config = get_config()

    if config.admin_password_hash:
        return config.admin_password_hash

    if config.admin_password:
        hashed = encrypt_password(config.admin_password)
        logger.info("Admin password hashed from ADMIN_PASSWORD env variable")
        return hashed

    # Generate a random default password
    default_password = secrets.token_urlsafe(12)
    hashed = encrypt_password(default_password)
    logger.warning(
        "No admin password configured. Generated default password: %s "
        "(Set ADMIN_PASSWORD env variable to override)",
        default_password,
    )
    return hashed


# Thread-safe lazy-initialized password hash
@lru_cache(maxsize=1)
def _ensure_password_hash() -> str:
    """Ensure the admin password hash is initialized and return it."""
    return _get_password_hash()


def verify_credentials(username: str, password: str) -> bool:
    """Verify username and password against configured admin credentials.

    Args:
        username: Provided username
        password: Provided plaintext password

    Returns:
        bool: True if credentials are valid
    """
    config = get_config()
    if username != config.admin_username:
        return False

    stored_hash = _ensure_password_hash()
    return verify_password(password, stored_hash)


async def _get_current_epoch() -> int:
    """Return the current session epoch, reading the DB at most every TTL seconds.

    Falls back to ``0`` if the database is unavailable (fail-open on epoch so
    already-issued tokens keep working during a transient DB outage).
    """
    now = time.time()
    if now - _epoch_cache["fetched_at"] < _EPOCH_CACHE_TTL:
        return int(_epoch_cache["value"])  # type: ignore[arg-type]

    async with _epoch_lock:
        # Re-check inside the lock to avoid duplicate DB hits under concurrency.
        if now - _epoch_cache["fetched_at"] < _EPOCH_CACHE_TTL:
            return int(_epoch_cache["value"])  # type: ignore[arg-type]

        value = 0
        try:
            from app.database import db_manager
            from app.repositories import SettingsRepository

            async with db_manager.session_factory() as db:
                repo = SettingsRepository(db)
                raw = await repo.get(_EPOCH_SETTING_KEY)
                if raw is None:
                    await repo.set(_EPOCH_SETTING_KEY, "0")
                    value = 0
                else:
                    value = int(raw)
        except Exception:
            logger.exception("Failed to read session epoch; using cached/default")
            value = int(_epoch_cache["value"])

        _epoch_cache["value"] = value
        _epoch_cache["fetched_at"] = time.time()
        return value


async def _bump_epoch() -> int:
    """Atomically increment and persist the session epoch.

    Returns:
        int: The new epoch value.
    """
    async with _epoch_lock:
        from app.database import db_manager
        from app.repositories import SettingsRepository

        async with db_manager.session_factory() as db:
            repo = SettingsRepository(db)
            raw = await repo.get(_EPOCH_SETTING_KEY)
            new_value = (int(raw) + 1) if raw is not None else 1
            await repo.set(_EPOCH_SETTING_KEY, str(new_value))

        _epoch_cache["value"] = new_value
        _epoch_cache["fetched_at"] = time.time()
        logger.info("Session epoch bumped to %s", new_value)
        return new_value


async def create_session(username: str) -> str:
    """Create a new signed session token for the given user.

    Args:
        username: Authenticated username

    Returns:
        str: Signed session token to store in the cookie.
    """
    epoch = await _get_current_epoch()
    payload = {"u": username, "iat": time.time(), "e": epoch}
    payload_b64 = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    token = f"{payload_b64}.{_sign(payload_b64)}"
    logger.info("Session created for user: %s", username)
    return token


async def validate_session(token: str) -> bool:
    """Validate a signed session token.

    Args:
        token: Session token from cookie

    Returns:
        bool: True if the signature is valid, the token is unexpired, and its
        epoch matches the current session epoch.
    """
    if not token or "." not in token:
        return False

    payload_b64, sig = token.rsplit(".", 1)
    expected_sig = _sign(payload_b64)
    if not hmac.compare_digest(sig, expected_sig):
        return False

    try:
        payload = json.loads(_unb64(payload_b64).decode("utf-8"))
        issued_at = float(payload["iat"])
        epoch = int(payload["e"])
    except (ValueError, KeyError, TypeError):
        return False

    # Absolute expiry.
    if time.time() - issued_at > SESSION_MAX_AGE_SECONDS:
        return False

    # Revocation check.
    if epoch != await _get_current_epoch():
        return False

    return True


async def destroy_session(token: str) -> None:
    """Invalidate the current session.

    Because tokens are stateless and we run a single-admin deployment, logout
    bumps the session epoch, which invalidates every outstanding token.

    Args:
        token: Session token (unused but kept for API symmetry).
    """
    del token  # epoch-based invalidation is global
    try:
        await _bump_epoch()
    except Exception:
        logger.exception("Failed to bump session epoch on logout")


# Re-export for tests / callers that previously imported these names.
invalidate_all_sessions = _bump_epoch


# Kept for backwards compatibility with older imports — no longer needed but
# avoids breaking any out-of-tree callers.
def _cleanup_expired_sessions() -> None:  # pragma: no cover - stateless store
    """No-op retained for API compatibility (sessions are stateless now)."""
    return None
