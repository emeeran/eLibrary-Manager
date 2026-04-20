"""Persistent disk cache for NAS-sourced ebook files.

Enables offline reading by caching recently-accessed books locally.
Uses LRU eviction when the cache exceeds a configurable size limit.
"""

import hashlib
import os
import shutil
from pathlib import Path
from typing import Optional

from app.logging_config import get_logger

logger = get_logger(__name__)

# Module-level singleton
_instance: Optional["NASFileCache"] = None


class NASFileCache:
    """Disk-based cache for NAS ebook files.

    Copies ebook files from the NAS mount to a local cache directory
    so they remain accessible when the NAS is offline.
    """

    def __init__(self, cache_dir: str, max_size_mb: int = 2000) -> None:
        """Initialize the cache.

        Args:
            cache_dir: Local directory for cached files.
            max_size_mb: Maximum total cache size in megabytes.
        """
        self.cache_dir = Path(cache_dir)
        self.max_size = max_size_mb * 1024 * 1024
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _path_hash(nas_path: str) -> str:
        """Generate a deterministic hash for a NAS path."""
        return hashlib.sha256(nas_path.encode("utf-8")).hexdigest()[:32]

    def _cached_path(self, nas_path: str) -> Path:
        """Return the local cache path for a NAS file."""
        ext = Path(nas_path).suffix
        return self.cache_dir / f"{self._path_hash(nas_path)}{ext}"

    def _meta_path(self, nas_path: str) -> Path:
        """Return the metadata file path for tracking original paths."""
        return self.cache_dir / f"{self._path_hash(nas_path)}.meta"

    async def get(self, nas_path: str) -> Optional[str]:
        """Check if a file is cached and return the cached path.

        Args:
            nas_path: Original NAS file path.

        Returns:
            Local cached path if available, None otherwise.
        """
        cached = self._cached_path(nas_path)
        if cached.exists() and cached.stat().st_size > 0:
            return str(cached)
        return None

    async def put(self, nas_path: str) -> str:
        """Copy a file from NAS to cache.

        Args:
            nas_path: Original NAS file path.

        Returns:
            Local cached path.
        """
        cached = self._cached_path(nas_path)

        if cached.exists() and cached.stat().st_size > 0:
            # Already cached, update metadata
            self._write_meta(nas_path)
            return str(cached)

        try:
            shutil.copy2(nas_path, str(cached))
            self._write_meta(nas_path)
            logger.info(f"Cached NAS file: {Path(nas_path).name}")
        except OSError as e:
            logger.error(f"Failed to cache {nas_path}: {e}")
            return nas_path  # Return original path as fallback

        await self.cleanup()
        return str(cached)

    async def ensure_cached(self, nas_path: str) -> str:
        """Ensure a file is cached, copying it if necessary.

        Args:
            nas_path: Original NAS file path.

        Returns:
            Path to use (cached if available, original as fallback).
        """
        cached = await self.get(nas_path)
        if cached:
            return cached

        # Try to cache it
        try:
            return await self.put(nas_path)
        except Exception:
            return nas_path

    async def remove(self, nas_path: str) -> bool:
        """Remove a file from cache.

        Args:
            nas_path: Original NAS file path.

        Returns:
            True if the file was removed.
        """
        cached = self._cached_path(nas_path)
        meta = self._meta_path(nas_path)
        removed = False

        if cached.exists():
            cached.unlink()
            removed = True
        if meta.exists():
            meta.unlink()

        return removed

    async def cleanup(self) -> int:
        """Evict oldest files when cache exceeds max size.

        Returns:
            Number of files evicted.
        """
        total_size = 0
        files = []

        for f in self.cache_dir.iterdir():
            if f.is_file() and not f.suffix == ".meta":
                stat = f.stat()
                total_size += stat.st_size
                files.append((f, stat.st_mtime, stat.st_size))

        if total_size <= self.max_size:
            return 0

        # Sort by mtime (oldest first) for LRU eviction
        files.sort(key=lambda x: x[1])

        evicted = 0
        for f, _, size in files:
            if total_size <= self.max_size:
                break
            f.unlink()
            # Remove associated meta file
            meta = f.with_suffix(".meta")
            if meta.exists():
                meta.unlink()
            total_size -= size
            evicted += 1

        if evicted:
            logger.info(f"Cache cleanup: evicted {evicted} files")
        return evicted

    def _write_meta(self, nas_path: str) -> None:
        """Write metadata file linking cache entry to original path."""
        meta = self._meta_path(nas_path)
        meta.write_text(nas_path)

    def get_total_size(self) -> int:
        """Return total cache size in bytes."""
        total = 0
        for f in self.cache_dir.iterdir():
            if f.is_file() and not f.suffix == ".meta":
                total += f.stat().st_size
        return total

    def list_cached(self) -> list[dict]:
        """List all cached files with metadata.

        Returns:
            List of dicts with path_hash, nas_path, size_bytes.
        """
        result = []
        for f in self.cache_dir.iterdir():
            if f.is_file() and not f.suffix == ".meta":
                meta_path = f.with_suffix(".meta")
                nas_path = meta_path.read_text() if meta_path.exists() else "unknown"
                result.append({
                    "path_hash": f.stem,
                    "nas_path": nas_path,
                    "cached_path": str(f),
                    "size_bytes": f.stat().st_size,
                })
        return result


def get_nas_cache() -> Optional[NASFileCache]:
    """Get or create the NAS file cache singleton.

    Returns:
        NASFileCache instance if NAS is configured, None otherwise.
    """
    global _instance
    if _instance is not None:
        return _instance

    from app.config import get_config
    config = get_config()

    if not config.nas_enabled or not config.nas_cache_dir:
        return None

    _instance = NASFileCache(
        cache_dir=config.nas_cache_dir,
        max_size_mb=2000,
    )
    return _instance
