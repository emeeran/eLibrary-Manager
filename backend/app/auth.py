"""Session-based authentication for eLibrary Manager.

Provides minimal single-admin-user auth with cookie-based sessions.
Uses in-memory session store with configurable expiry.
"""

import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from app.config import get_config
from app.logging_config import get_logger
from app.security import encrypt_password, verify_password

logger = get_logger(__name__)

# In-memory session store: {token: {"username": str, "created_at": float}}
_session_store: dict[str, dict] = {}

SESSION_COOKIE_NAME = "elib_session"
SESSION_MAX_AGE_SECONDS = 86400  # 24 hours


def _get_password_hash() -> str:
    """Get or derive the admin password hash.

    Priority:
    1. admin_password_hash from config (bcrypt hash)
    2. admin_password from config (plaintext, auto-hashed)
    3. Generate default and log it

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


# Lazy-initialized password hash
_admin_password_hash: Optional[str] = None


def _ensure_password_hash() -> str:
    """Ensure the admin password hash is initialized and return it."""
    global _admin_password_hash
    if _admin_password_hash is None:
        _admin_password_hash = _get_password_hash()
    return _admin_password_hash


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


def create_session(username: str) -> str:
    """Create a new session for the given user.

    Args:
        username: Authenticated username

    Returns:
        str: Session token
    """
    _cleanup_expired_sessions()

    token = secrets.token_urlsafe(32)
    _session_store[token] = {
        "username": username,
        "created_at": time.time(),
    }
    logger.info("Session created for user: %s", username)
    return token


def validate_session(token: str) -> bool:
    """Validate a session token.

    Args:
        token: Session token from cookie

    Returns:
        bool: True if session is valid and not expired
    """
    if not token:
        return False

    session = _session_store.get(token)
    if not session:
        return False

    # Check expiry
    age = time.time() - session["created_at"]
    if age > SESSION_MAX_AGE_SECONDS:
        del _session_store[token]
        return False

    return True


def destroy_session(token: str) -> None:
    """Destroy a session.

    Args:
        token: Session token to destroy
    """
    _session_store.pop(token, None)


def _cleanup_expired_sessions() -> None:
    """Remove expired sessions from the store."""
    now = time.time()
    expired = [
        token
        for token, session in _session_store.items()
        if now - session["created_at"] > SESSION_MAX_AGE_SECONDS
    ]
    for token in expired:
        del _session_store[token]
