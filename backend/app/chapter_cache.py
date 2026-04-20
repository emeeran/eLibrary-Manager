"""In-memory chapter cache for fast page loading.

Caches parsed chapter content to avoid re-parsing ebook files on every request.
Uses LRU eviction with configurable size limits.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CachedChapter:
    """Cached chapter data."""
    content: str
    title: str
    total_chapters: int
    cached_at: datetime
    file_mtime: float  # File modification time for invalidation


class ChapterCache:
    """LRU cache for parsed chapter content.
    
    Provides O(1) lookup for cached chapters and automatic eviction
    when the cache size limit is reached.
    """
    
    def __init__(self, max_size: int = 200) -> None:
        """Initialize cache with size limit.
        
        Args:
            max_size: Maximum number of chapters to cache (increased for PDFs)
        """
        self._cache: OrderedDict[str, CachedChapter] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
    
    # Bump when content extraction logic changes to invalidate all caches
    CONTENT_VERSION = 2

    def _make_key(self, book_path: str, chapter_index: int) -> str:
        """Generate cache key from book path and chapter index."""
        return f"v{self.CONTENT_VERSION}:{book_path}:{chapter_index}"

    async def get(
        self,
        book_path: str,
        chapter_index: int,
        file_mtime: float | None = None
    ) -> CachedChapter | None:
        """Get cached chapter if available and valid.

        Args:
            book_path: Path to ebook file
            chapter_index: Zero-based chapter index
            file_mtime: Current file modification time (for invalidation)

        Returns:
            Cached chapter data or None if not cached/stale
        """
        key = self._make_key(book_path, chapter_index)
        
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            cached = self._cache[key]
            
            # Invalidate if file was modified
            if file_mtime is not None and cached.file_mtime != file_mtime:
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Cache invalidated for {book_path} ch{chapter_index}")
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            
            return cached
    
    async def put(
        self,
        book_path: str,
        chapter_index: int,
        content: str,
        title: str,
        total_chapters: int,
        file_mtime: float
    ) -> None:
        """Store chapter in cache.
        
        Args:
            book_path: Path to ebook file
            chapter_index: Zero-based chapter index
            content: Chapter HTML content
            title: Chapter title
            total_chapters: Total chapters in book
            file_mtime: File modification time
        """
        key = self._make_key(book_path, chapter_index)
        
        async with self._lock:
            # Remove oldest if at capacity
            while len(self._cache) >= self._max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.debug(f"Evicted {oldest_key} from cache")
            
            self._cache[key] = CachedChapter(
                content=content,
                title=title,
                total_chapters=total_chapters,
                cached_at=datetime.utcnow(),
                file_mtime=file_mtime
            )
    
    async def invalidate_book(self, book_path: str) -> int:
        """Remove all cached chapters for a book.
        
        Args:
            book_path: Path to ebook file
            
        Returns:
            Number of entries removed
        """
        prefix = f"{book_path}:"
        
        async with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]
            
            if keys_to_remove:
                logger.debug(f"Invalidated {len(keys_to_remove)} chapters for {book_path}")
            
            return len(keys_to_remove)
    
    async def clear(self) -> None:
        """Clear all cached chapters."""
        async with self._lock:
            self._cache.clear()
            logger.info("Chapter cache cleared")
    
    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%"
        }


# Global cache instance
_chapter_cache: ChapterCache | None = None


def get_chapter_cache() -> ChapterCache:
    """Get the global chapter cache instance."""
    global _chapter_cache
    if _chapter_cache is None:
        _chapter_cache = ChapterCache(max_size=200)  # Cache up to 200 chapters
    return _chapter_cache