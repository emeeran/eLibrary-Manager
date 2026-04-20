"""Factory for creating storage backend instances."""

from app.config import get_config
from app.storage import StorageBackend
from app.storage.local import LocalStorageBackend
from app.storage.nas import NASStorageBackend


def get_storage_backend(storage_type: str = "local") -> StorageBackend:
    """Create a storage backend instance.

    Args:
        storage_type: Either "local" or "nas".

    Returns:
        StorageBackend instance appropriate for the given type.
    """
    if storage_type == "nas":
        config = get_config()
        return NASStorageBackend(
            mount_path=config.nas_mount_path,
            host=config.nas_host,
        )
    return LocalStorageBackend()
