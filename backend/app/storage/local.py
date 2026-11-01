"""Local filesystem storage backend."""

from app.storage import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Storage backend for local filesystem access."""

    async def health_check(self) -> dict:
        """Local storage is always healthy."""
        return {"healthy": True, "details": "Local filesystem"}
