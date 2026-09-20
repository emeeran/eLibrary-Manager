"""Tests for NAS file cache and storage backend health (spec 009)."""

from types import SimpleNamespace

import pytest
from app.nas_cache import NASFileCache, get_nas_cache
from app.storage.nas import NASStorageBackend

# --- NASFileCache ----------------------------------------------------------


@pytest.fixture
def cache(tmp_path):
    """Cache with a tiny limit so eviction is easy to trigger."""
    return NASFileCache(cache_dir=str(tmp_path / "cache"), max_size_mb=1)


@pytest.fixture
def nas_file(tmp_path):
    """A fake NAS file to cache."""
    f = tmp_path / "book.epub"
    f.write_bytes(b"x" * 4096)
    return f


@pytest.mark.asyncio
async def test_cache_put_then_get(cache, nas_file):
    """A cached file resolves to the local cache path."""
    cached = await cache.put(str(nas_file))
    assert cached != str(nas_file)
    assert await cache.get(str(nas_file)) == cached


@pytest.mark.asyncio
async def test_cache_get_miss_returns_none(cache, nas_file):
    """An uncached path returns None."""
    assert await cache.get(str(nas_file)) is None


@pytest.mark.asyncio
async def test_cache_put_falls_back_to_original_on_error(cache):
    """If the source is unreadable, put returns the original path."""
    result = await cache.put("/nonexistent/source.epub")
    assert result == "/nonexistent/source.epub"


@pytest.mark.asyncio
async def test_cache_remove(cache, nas_file):
    """Remove drops both data and meta files."""
    cached = await cache.put(str(nas_file))
    assert await cache.remove(str(nas_file)) is True
    import os

    assert not os.path.exists(cached)
    assert await cache.get(str(nas_file)) is None


@pytest.mark.asyncio
async def test_cache_evicts_oldest_when_full(cache, nas_file, tmp_path):
    """Exceeding the cap evicts the oldest entry (LRU) on the next put."""
    # Cap is 1MB; write two ~0.75MB files and backdate the first's mtime.
    big1 = tmp_path / "big1.epub"
    big2 = tmp_path / "big2.epub"
    big1.write_bytes(b"a" * 768 * 1024)
    big2.write_bytes(b"b" * 768 * 1024)
    await cache.put(str(big1))
    import os

    os.utime(cache._cached_path(str(big1)), (0, 0))  # oldest
    await cache.put(str(big2))  # crosses the cap → evicts oldest

    assert cache.get_total_size() <= cache.max_size
    assert await cache.get(str(big1)) is None  # oldest was evicted
    assert await cache.get(str(big2)) is not None
    # With the cache back under the cap, explicit cleanup is a no-op
    assert await cache.cleanup() == 0


@pytest.mark.asyncio
async def test_cache_cleanup_noop_under_limit(cache, nas_file):
    """No eviction while the cache is under the cap."""
    await cache.put(str(nas_file))
    assert await cache.cleanup() == 0


@pytest.mark.asyncio
async def test_list_cached_reports_original_paths(cache, nas_file):
    """Metadata maps cache entries back to their NAS paths."""
    await cache.put(str(nas_file))
    entries = cache.list_cached()
    assert len(entries) == 1
    assert entries[0]["nas_path"] == str(nas_file)
    assert entries[0]["size_bytes"] == nas_file.stat().st_size


# --- NASStorageBackend.health_check ----------------------------------------


@pytest.mark.asyncio
async def test_backend_healthy_on_real_dir(tmp_path):
    """An existing, listable path reports healthy."""
    backend = NASStorageBackend(mount_path=str(tmp_path), host="test-host")
    result = await backend.health_check()
    assert result["healthy"] is True
    assert backend.is_healthy is True
    assert backend.status["mount_path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_backend_unhealthy_on_missing_path():
    """A nonexistent mount path reports unhealthy."""
    backend = NASStorageBackend(mount_path="/nonexistent/nas/path", host="h")
    result = await backend.health_check()
    assert result["healthy"] is False
    assert backend.is_healthy is False


@pytest.mark.asyncio
async def test_backend_unhealthy_when_unconfigured():
    """An empty mount path reports unhealthy without probing."""
    backend = NASStorageBackend(mount_path="")
    result = await backend.health_check()
    assert result["healthy"] is False


# --- get_nas_cache singleton ------------------------------------------------


def test_get_nas_cache_disabled_by_default(monkeypatch):
    """No cache is created when NAS is not enabled."""
    from app import config as config_module
    from app import nas_cache as nas_cache_module

    monkeypatch.setattr(nas_cache_module, "_instance", None)
    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda: SimpleNamespace(nas_enabled=False, nas_cache_dir=""),
    )
    assert get_nas_cache() is None
