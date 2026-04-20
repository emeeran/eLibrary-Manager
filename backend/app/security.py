"""Credential encryption for sensitive settings (e.g., NAS passwords)."""

import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet


def _derive_key() -> bytes:
    """Derive a Fernet key from a stable local secret (DB path)."""
    from app.config import get_config

    config = get_config()
    # Use the database path as a stable local secret
    secret = config.database_url.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    """Get a Fernet instance with the derived key."""
    return Fernet(_derive_key())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return base64-encoded ciphertext.

    Args:
        plaintext: The string to encrypt.

    Returns:
        Base64-encoded encrypted string.
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext string.

    Args:
        ciphertext: The base64-encoded encrypted string.

    Returns:
        Decrypted plaintext string.
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def _get_password_hasher():
    """Get a password hashing context using bcrypt."""
    import hashlib
    try:
        from passlib.context import CryptContext
        return CryptContext(schemes=["bcrypt"], deprecated="auto")
    except ImportError:
        # Fallback: use HMAC-based hashing if passlib is unavailable
        return None


def encrypt_password(password: str) -> str:
    """Hash a password using bcrypt (preferred) or HMAC fallback."""
    ctx = _get_password_hasher()
    if ctx is not None:
        return ctx.hash(password)

    # Fallback: HMAC-SHA256 with the app secret key
    from app.config import get_config
    config = get_config()
    secret = (config.secret_key or config.database_url).encode("utf-8")
    import hmac
    return "hmac:" + hmac.new(secret, password.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against its stored hash.

    Supports both bcrypt hashes and legacy Fernet-encrypted values.
    """
    ctx = _get_password_hasher()

    # Legacy Fernet-encrypted passwords (backward compatible)
    if stored and not stored.startswith(("hmac:", "$2")) and ctx is None:
        try:
            return _get_fernet().decrypt(stored.encode()).decode() == password
        except Exception:
            return False

    if ctx is not None:
        # Try bcrypt first
        if stored.startswith("$2"):
            try:
                return ctx.verify(password, stored)
            except Exception:
                return False
        # Legacy Fernet migration: verify old format, return True to allow re-save
        try:
            legacy_fernet = _get_fernet()
            if legacy_fernet.decrypt(stored.encode()).decode() == password:
                return True
        except Exception:
            pass
        return False

    # HMAC fallback verification
    if stored.startswith("hmac:"):
        from app.config import get_config
        config = get_config()
        secret = (config.secret_key or config.database_url).encode("utf-8")
        import hmac
        expected = "hmac:" + hmac.new(secret, password.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, stored)

    return False
