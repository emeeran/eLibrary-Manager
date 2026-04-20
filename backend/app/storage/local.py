"""Local filesystem storage backend."""

import os
from typing import Any

from app.storage import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Storage backend for local filesystem access."""

    async def health_check(self) -> dict:
        """Local storage is always healthy."""
        return {"healthy": True, "details": "Local filesystem"}

    async def walk_directory(self, root: str) -> list[tuple[str, list[str]]]:
        """Walk local directory tree."""
        result: list[tuple[str, list[str]]] = []
        for dirpath, _, filenames in os.walk(root):
            result.append((dirpath, filenames))
        return result

    async def file_exists(self, path: str) -> bool:
        """Check if file exists on local filesystem."""
        return os.path.exists(path)

    async def get_file_size(self, path: str) -> int:
        """Get local file size."""
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def resolve_path(self, path: str) -> str:
        """Return path as-is for local storage."""
        return path
