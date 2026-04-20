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


def _get_password_fernet() -> Fernet:
    """Get a Fernet instance keyed from the app secret_key."""
    from app.config import get_config

    config = get_config()
    secret = config.secret_key.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_password(password: str) -> str:
    """Encrypt a password using Fernet."""
    return _get_password_fernet().encrypt(password.encode()).decode()


def verify_password(password: str, encrypted: str) -> bool:
    """Verify a password against encrypted value."""
    try:
        return _get_password_fernet().decrypt(encrypted.encode()).decode() == password
    except Exception:
        return False
