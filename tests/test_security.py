"""Tests for security functions."""

import pytest
from unittest.mock import patch, MagicMock


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_bcrypt_hash_and_verify(self):
        """Test bcrypt password hashing and verification."""
        from app.security import encrypt_password, verify_password
        hashed = encrypt_password("my-secret-password")
        assert verify_password("my-secret-password", hashed)
        assert not verify_password("wrong-password", hashed)

    def test_hash_is_different_each_time(self):
        """Test that hashing the same password produces different hashes."""
        from app.security import encrypt_password
        hash1 = encrypt_password("same-password")
        hash2 = encrypt_password("same-password")
        assert hash1 != hash2  # bcrypt uses random salt

    def test_special_characters_password(self):
        """Test handling of special characters in passwords."""
        from app.security import encrypt_password, verify_password
        pw = "p@$$w0rd!#%^&*()"
        hashed = encrypt_password(pw)
        assert verify_password(pw, hashed)

    def test_max_length_password(self):
        """Test handling of 72-byte bcrypt max password."""
        from app.security import encrypt_password, verify_password
        # bcrypt truncates at 72 bytes, test with exactly 72
        pw = "a" * 72
        hashed = encrypt_password(pw)
        assert verify_password(pw, hashed)


class TestValueEncryption:
    """Test symmetric value encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test encrypting and decrypting a value."""
        from app.security import encrypt_value, decrypt_value
        plaintext = "sensitive-password-123"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext
        assert decrypt_value(encrypted) == plaintext

    def test_different_values_produce_different_ciphertexts(self):
        """Test that different values produce different ciphertexts."""
        from app.security import encrypt_value
        enc1 = encrypt_value("value1")
        enc2 = encrypt_value("value2")
        assert enc1 != enc2

    def test_empty_string_encryption(self):
        """Test encrypting empty string."""
        from app.security import encrypt_value, decrypt_value
        encrypted = encrypt_value("")
        assert decrypt_value(encrypted) == ""

    def test_unicode_encryption(self):
        """Test encrypting unicode characters."""
        from app.security import encrypt_value, decrypt_value
        plaintext = "パスワード 🔐"
        encrypted = encrypt_value(plaintext)
        assert decrypt_value(encrypted) == plaintext
