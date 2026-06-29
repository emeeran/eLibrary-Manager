"""Storage backend abstraction for local and NAS file access."""

import asyncio
import os
from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    Provides a uniform interface for file system operations regardless
    of whether the underlying storage is local or a network mount.
    """

    @abstractmethod
    async def health_check(self) -> dict:
        """Check storage availability.

        Returns:
            Dict with "healthy" (bool) and "details" (str) keys.
        """

    async def walk_directory(self, root: str) -> list[tuple[str, list[str]]]:
        """Recursively walk a directory tree (non-blocking).

        Args:
            root: Root directory path to walk.

        Returns:
            List of (dirpath, filenames) tuples.
        """

        def _walk() -> list[tuple[str, list[str]]]:
            result: list[tuple[str, list[str]]] = []
            try:
                for dirpath, _, filenames in os.walk(root):
                    result.append((dirpath, filenames))
            except OSError:
                pass
            return result

        return await asyncio.to_thread(_walk)

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists (non-blocking)."""
        return await asyncio.to_thread(os.path.exists, path)

    async def get_file_size(self, path: str) -> int:
        """Get file size in bytes (non-blocking)."""
        try:
            return await asyncio.to_thread(os.path.getsize, path)
        except OSError:
            return 0

    def resolve_path(self, path: str) -> str:
        """Return path as-is (locally accessible via mount)."""
        return path
