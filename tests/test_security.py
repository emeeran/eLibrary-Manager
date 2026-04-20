"""Tests for configuration and security."""

import os
import pytest
from unittest.mock import patch, MagicMock

from app.config import AppConfig, validate_library_path, _DEFAULT_SECRET_KEY


def _make_config(**env_overrides):
    """Create an AppConfig with controlled env vars (no .env file interference)."""
    saved = {}
    # Save and override env vars
    for key, val in env_overrides.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = val
    try:
        return AppConfig(_env_file="/dev/null")
    finally:
        # Restore
        for key, old_val in saved.items():
            if old_val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_val


class TestConfig:
    """Test configuration management."""

    def test_production_rejects_default_secret_key(self):
        with pytest.raises(ValueError, match="SECRET_KEY"):
            _make_config(
                APP_ENV="production",
                ADMIN_PASSWORD="test",
                SECRET_KEY=_DEFAULT_SECRET_KEY,
            )

    def test_production_requires_admin_password(self):
        with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
            _make_config(
                APP_ENV="production",
                SECRET_KEY="a-real-secret-key-that-is-long-enough",
            )

    def test_production_accepts_valid_config(self):
        config = _make_config(
            APP_ENV="production",
            SECRET_KEY="a-real-secret-key-that-is-long-enough",
            ADMIN_PASSWORD="secure-password",
        )
        assert config.is_production is True

    def test_development_allows_defaults(self):
        config = _make_config(APP_ENV="development")
        assert config.is_development is True

    def test_cors_origin_list_parsing(self):
        config = _make_config(
            APP_ENV="testing",
            CORS_ORIGINS="http://localhost:3000, https://example.com"
        )
        assert config.cors_origin_list == [
            "http://localhost:3000",
            "https://example.com"
        ]

    def test_upload_size_default(self):
        config = _make_config(APP_ENV="testing")
        assert config.max_upload_size == 104_857_600

    def test_backup_config_defaults(self):
        config = _make_config(APP_ENV="testing")
        assert config.backup_max_count == 10


class TestPathValidation:
    """Test file path validation for security."""

    def test_rejects_path_outside_library(self, tmp_path):
        lib_dir = tmp_path / "library"
        lib_dir.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        book_file = outside_dir / "file.epub"
        book_file.write_text("test")

        mock_cfg = MagicMock()
        mock_cfg.library_path = str(lib_dir)
        with patch("app.config.get_config", return_value=mock_cfg):
            with pytest.raises(ValueError, match="outside"):
                validate_library_path(str(book_file))

    def test_allows_path_inside_library(self, tmp_path):
        lib_dir = tmp_path / "library"
        lib_dir.mkdir()
        book_path = lib_dir / "book.epub"
        book_path.write_text("test")

        mock_cfg = MagicMock()
        mock_cfg.library_path = str(lib_dir)
        with patch("app.config.get_config", return_value=mock_cfg):
            result = validate_library_path(str(book_path))
            assert result == str(book_path.resolve())

    def test_rejects_path_traversal(self, tmp_path):
        lib_dir = tmp_path / "library"
        lib_dir.mkdir()

        mock_cfg = MagicMock()
        mock_cfg.library_path = str(lib_dir)
        with patch("app.config.get_config", return_value=mock_cfg):
            with pytest.raises(ValueError, match="outside"):
                validate_library_path(str(lib_dir / ".." / "etc" / "passwd"))


class TestSecurity:
    """Test security functions."""

    def test_password_encrypt_decrypt(self):
        from app.security import encrypt_password, verify_password
        encrypted = encrypt_password("test-password")
        assert verify_password("test-password", encrypted)
        assert not verify_password("wrong-password", encrypted)

    def test_value_encrypt_decrypt(self):
        from app.security import encrypt_value, decrypt_value
        encrypted = encrypt_value("sensitive-data")
        assert decrypt_value(encrypted) == "sensitive-data"

    def test_admin_password_verification(self):
        from app import security
        mock_cfg = MagicMock()
        mock_cfg.admin_password = "correct-password"
        with patch("app.config.get_config", return_value=mock_cfg):
            assert security.verify_admin_password("correct-password")
            assert not security.verify_admin_password("wrong-password")

    def test_admin_password_not_set(self):
        from app import security
        mock_cfg = MagicMock()
        mock_cfg.admin_password = ""
        with patch("app.config.get_config", return_value=mock_cfg):
            assert not security.verify_admin_password("any-password")


class TestMiddleware:
    """Test middleware functionality."""

    def test_session_creation_and_validation(self):
        from app.middleware import create_session, _validate_session, revoke_session
        token = create_session()
        assert _validate_session(token)
        revoke_session(token)
        assert not _validate_session(token)

    def test_invalid_session_rejected(self):
        from app.middleware import _validate_session
        assert not _validate_session("invalid-token")
