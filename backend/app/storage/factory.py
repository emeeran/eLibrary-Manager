"""Factory for creating storage backend instances."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.storage import StorageBackend
from app.storage.local import LocalStorageBackend
from app.storage.nas import NASStorageBackend


async def get_nas_config_from_db(session: AsyncSession) -> dict[str, str | None]:
    """Read NAS settings from DB, falling back to env config.

    Args:
        session: Database session for reading settings.

    Returns:
        Dict with nas_enabled, nas_mount_path, nas_host.
    """
    from app.repositories import SettingsRepository

    repo = SettingsRepository(session)
    stored = await repo.get_all()

    def _str(key: str) -> str | None:
        return stored.get(key)

    def _bool(key: str) -> bool:
        v = stored.get(key)
        return v.lower() in ("true", "1", "yes") if v else False

    config = get_config()

    return {
        "nas_enabled": _bool("nas_enabled")
        if _str("nas_enabled") is not None
        else config.nas_enabled,
        "nas_mount_path": _str("nas_mount_path") or config.nas_mount_path,
        "nas_host": _str("nas_host") or config.nas_host,
    }


def get_storage_backend(
    storage_type: str = "local",
    mount_path: str | None = None,
    host: str | None = None,
) -> StorageBackend:
    """Create a storage backend instance.

    Args:
        storage_type: Either "local" or "nas".
        mount_path: NAS mount path (overrides env config).
        host: NAS host (overrides env config).

    Returns:
        StorageBackend instance appropriate for the given type.
    """
    if storage_type == "nas":
        config = get_config()
        return NASStorageBackend(
            mount_path=mount_path or config.nas_mount_path,
            host=host or config.nas_host,
        )
    return LocalStorageBackend()
