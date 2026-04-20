"""Credential encryption for sensitive settings (e.g., NAS passwords)."""

import base64
import hashlib
import hmac
import os
from pathlib import Path

from cryptography.fernet import Fernet

# Cached bcrypt context (singleton)
_password_ctx = None


def _get_password_hasher():
    """Get or create the cached password hashing context."""
    global _password_ctx
    if _password_ctx is not None:
        return _password_ctx
    try:
        from passlib.context import CryptContext
        _password_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return _password_ctx
    except ImportError:
        return None


def _derive_key() -> bytes:
    """Derive a Fernet key from a stable local secret (DB path)."""
    from app.config import get_config

    config = get_config()
    secret = config.database_url.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    """Get a Fernet instance with the derived key."""
    return Fernet(_derive_key())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext string."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def _hmac_hash(password: str, secret: bytes) -> str:
    """Compute HMAC-SHA256 digest for password with given secret."""
    return "hmac:" + hmac.new(secret, password.encode("utf-8"), hashlib.sha256).hexdigest()


def _get_secret_key() -> bytes:
    """Get the app secret key bytes for HMAC operations."""
    from app.config import get_config
    config = get_config()
    return (config.secret_key or config.database_url).encode("utf-8")


def encrypt_password(password: str) -> str:
    """Hash a password using bcrypt (preferred) or HMAC fallback."""
    ctx = _get_password_hasher()
    if ctx is not None:
        return ctx.hash(password)
    return _hmac_hash(password, _get_secret_key())


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against its stored hash.

    Supports bcrypt hashes, legacy Fernet-encrypted values, and HMAC fallback.
    """
    ctx = _get_password_hasher()

    # No passlib available — legacy Fernet or HMAC only
    if ctx is None:
        if stored and not stored.startswith("hmac:"):
            try:
                return _get_fernet().decrypt(stored.encode()).decode() == password
            except Exception:
                return False
        if stored.startswith("hmac:"):
            return hmac.compare_digest(_hmac_hash(password, _get_secret_key()), stored)
        return False

    # bcrypt hash
    if stored.startswith("$2"):
        try:
            return ctx.verify(password, stored)
        except Exception:
            return False

    # Legacy Fernet migration
    try:
        if _get_fernet().decrypt(stored.encode()).decode() == password:
            return True
    except Exception:
        pass

    return False
