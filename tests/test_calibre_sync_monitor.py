"""Tests for the Calibre auto-sync monitor loop (spec 011 v1.2)."""

import contextlib
import types

import pytest
from app.services.calibre_sync_monitor import CalibreSyncMonitor


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _FakeDbManager:
    """Stands in for app.database.db_manager with an in-memory session."""

    def __init__(self, settings: dict[str, str]) -> None:
        self._settings = settings
        self.session = _FakeSession()

    @contextlib.asynccontextmanager
    async def get_session(self):
        yield self.session


@pytest.fixture
def monitor_env(monkeypatch):
    """Patch out the real DB, settings repo, scan lock, and sync service."""
    import app.repositories as repositories_module
    import app.routes.library as library_module
    import app.services.calibre_sync_service as sync_module

    state: dict = {"settings": {"calibre_library_path": "/calibre/lib"}}

    class _FakeSettingsRepo:
        def __init__(self, session) -> None:
            pass

        async def get_all(self) -> dict[str, str]:
            return state["settings"]

    calls: list[tuple[str, bool]] = []

    async def _fake_sync(session, path, prune_missing):
        calls.append((path, prune_missing))
        return types.SimpleNamespace(imported=1, updated=2, skipped_existing=3)

    monkeypatch.setattr(repositories_module, "SettingsRepository", _FakeSettingsRepo)
    monkeypatch.setattr(sync_module, "sync_library", _fake_sync)
    monkeypatch.setattr(library_module, "_active_scans", set())
    state["db"] = _FakeDbManager(state["settings"])
    state["calls"] = calls
    return state


def _patch_db(monkeypatch, state):
    import app.database as database_module

    monkeypatch.setattr(database_module, "db_manager", state["db"])


@pytest.mark.asyncio
async def test_run_sync_happy_path(monitor_env, monkeypatch):
    """Sync runs with the saved path, commits, and releases the scan lock."""
    from app.routes.library import _active_scans

    _patch_db(monkeypatch, monitor_env)

    monitor = CalibreSyncMonitor(interval_minutes=0)
    await monitor._run_sync()

    assert monitor_env["calls"] == [("/calibre/lib", True)]
    assert monitor_env["db"].session.commits == 1
    assert "calibre-autosync" not in _active_scans


@pytest.mark.asyncio
async def test_run_sync_skips_without_path(monitor_env, monkeypatch):
    """No configured library path → no sync attempt."""
    monitor_env["settings"]["calibre_library_path"] = ""
    _patch_db(monkeypatch, monitor_env)

    monitor = CalibreSyncMonitor(interval_minutes=0)
    await monitor._run_sync()

    assert monitor_env["calls"] == []


@pytest.mark.asyncio
async def test_run_sync_skips_while_scan_active(monitor_env, monkeypatch):
    """A manual scan holding the lock defers the auto-sync."""
    import app.routes.library as library_module

    library_module._active_scans.add("manual-scan")
    _patch_db(monkeypatch, monitor_env)

    monitor = CalibreSyncMonitor(interval_minutes=0)
    await monitor._run_sync()

    assert monitor_env["calls"] == []
    # The auto-sync must not have left its own lock behind
    assert "calibre-autosync" not in library_module._active_scans


@pytest.mark.asyncio
async def test_interval_floor_is_one_minute():
    """A zero/negative configured interval is clamped to 1 minute."""
    assert CalibreSyncMonitor(interval_minutes=0).interval_minutes == 1
    assert CalibreSyncMonitor(interval_minutes=-5).interval_minutes == 1
    assert CalibreSyncMonitor(interval_minutes=30).interval_minutes == 30


@pytest.mark.asyncio
async def test_loop_survives_sync_failure(monitor_env, monkeypatch):
    """A raising sync is swallowed so the monitor loop keeps its cadence."""
    import asyncio

    import app.services.calibre_sync_service as sync_module
    from app.routes.library import _active_scans

    _patch_db(monkeypatch, monitor_env)

    async def _boom(session, path, prune_missing):
        raise RuntimeError("calibre metadata.db locked")

    monkeypatch.setattr(sync_module, "sync_library", _boom)

    monitor = CalibreSyncMonitor(interval_minutes=1)
    monitor.interval_minutes = 0.001  # ~0.06s between runs, for the test
    await monitor.start()
    await asyncio.sleep(0.2)  # at least one failing run
    await monitor.stop()

    assert monitor._task.done()
    assert "calibre-autosync" not in _active_scans  # finally-discarded despite failure
