"""Application configuration management with Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Application configuration with environment variable support.

    This class centralizes all configuration management, ensuring type safety
    and providing defaults for development environments.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./dawnstar_data/dawnstar.db"

    # Library Paths
    library_path: str = "./library"
    covers_path: str = "./static_covers"
    book_images_path: str = "./static_book_images"

    # AI Configuration - Google Gemini (Primary)
    google_api_key: str = ""
    google_model: str = "gemini-1.5-flash"
    google_rate_limit_rpm: int = 15

    # AI Configuration - Groq (Secondary)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_rate_limit_rpm: int = 30

    # AI Configuration - Ollama Cloud (Tertiary)
    ollama_cloud_url: str = "https://api.ollama.ai"
    ollama_cloud_model: str = "llama3.3"

    # AI Configuration - Ollama Local (Fallback)
    ollama_local_url: str = "http://localhost:11434"
    ollama_local_model: str = "llama3.3"

    # AI Settings
    ai_default_provider: str = "auto"
    ai_enable_fallback: bool = True

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    secret_key: str = ""

    # Auth
    admin_username: str = "admin"
    admin_password_hash: str = ""
    admin_password: str = ""  # Plaintext fallback set via env ADMIN_PASSWORD

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Warn if SECRET_KEY is not set or using a default value."""
        if not v:
            import warnings
            warnings.warn(
                "SECRET_KEY is not set. Set a strong SECRET_KEY environment "
                "variable for production. Using derived fallback.",
                stacklevel=2,
            )
        return v

    # NAS Configuration
    nas_enabled: bool = False
    nas_host: str = ""
    nas_share: str = ""
    nas_mount_path: str = ""
    nas_protocol: Literal["smb", "nfs"] = "smb"
    nas_username: str = ""
    nas_auto_mount: bool = False
    nas_cache_dir: str = "./nas_cache"

    # Performance
    max_cover_size: int = 300000  # 300KB
    lazy_load_batch_size: int = 20
    db_pool_size: int = 10
    db_max_overflow: int = 20

    @field_validator(
        "library_path", "covers_path", "book_images_path",
        "nas_mount_path", "nas_cache_dir",
    )
    @classmethod
    def validate_paths(cls, v: str) -> str:
        """Ensure paths are absolute paths."""
        if not v:
            return v
        import os
        return os.path.abspath(v)

    @field_validator("google_api_key", "groq_api_key")
    @classmethod
    def validate_api_keys(cls, v: str) -> str:
        """Warn if API keys are not set (but allow for local Ollama)."""
        if not v:
            import warnings
            warnings.warn(
                "API key not set. AI features will rely on Ollama Local if available."
            )
        return v


@lru_cache
def get_config() -> AppConfig:
    """Cached configuration instance.

    Returns:
        AppConfig: Singleton configuration instance

    Example:
        >>> config = get_config()
        >>> print(config.database_url)
    """
    return AppConfig()
