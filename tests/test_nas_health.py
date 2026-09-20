"""Tests for the NAS health monitor's transition-only logging."""

import asyncio
import logging

import pytest
from app.nas_health import NASHealthMonitor


class _FakeBackend:
    """Backend whose health flips through a scripted sequence."""

    def __init__(self, sequence: list[bool]) -> None:
        self._sequence = list(sequence)
        self.mount_path = "/fake/mount"
        self.status: dict = {"healthy": self._sequence[0] if self._sequence else False}
        self.calls = 0

    async def health_check(self) -> dict:
        self.calls += 1
        healthy = self._sequence[min(self.calls - 1, len(self._sequence) - 1)]
        self.status = {"healthy": healthy, "details": f"fake-{healthy}"}
        return {"healthy": healthy, "details": f"fake-{healthy}"}


@pytest.mark.asyncio
async def test_monitor_logs_down_and_recovery_once(caplog):
    """One WARNING on going down, one INFO on recovery — no spam in between."""
    backend = _FakeBackend([False, False, False, True, True])
    monitor = NASHealthMonitor(backend, check_interval=0.01)

    with caplog.at_level(logging.INFO, logger="app.nas_health"):
        task = asyncio.create_task(monitor._run_loop())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    recoveries = [r for r in caplog.records if "recovered" in r.getMessage()]
    assert len(warnings) == 1, f"expected 1 down-warning, got {warnings}"
    assert len(recoveries) == 1


@pytest.mark.asyncio
async def test_monitor_silent_while_stably_healthy(caplog):
    """A healthy NAS produces no log output at all."""
    backend = _FakeBackend([True, True, True, True])
    monitor = NASHealthMonitor(backend, check_interval=0.01)

    with caplog.at_level(logging.INFO, logger="app.nas_health"):
        task = asyncio.create_task(monitor._run_loop())
        await asyncio.sleep(0.06)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert caplog.records == []


@pytest.mark.asyncio
async def test_monitor_survives_backend_exception(caplog):
    """A raised exception is logged and the loop keeps running."""
    class _ExplodingBackend(_FakeBackend):
        async def health_check(self) -> dict:
            self.calls += 1
            if self.calls == 1:
                raise OSError("mount vanished")
            return {"healthy": True, "details": "back"}

    backend = _ExplodingBackend([True, True])
    monitor = NASHealthMonitor(backend, check_interval=0.01)

    with caplog.at_level(logging.ERROR, logger="app.nas_health"):
        task = asyncio.create_task(monitor._run_loop())
        await asyncio.sleep(0.06)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert any("exception" in r.getMessage().lower() for r in caplog.records)
    assert backend.calls >= 2  # loop continued past the failure


@pytest.mark.asyncio
async def test_stop_cancels_cleanly():
    """stop() awaits task cancellation without raising."""
    backend = _FakeBackend([True])
    monitor = NASHealthMonitor(backend, check_interval=60)
    await monitor.start()
    await monitor.stop()
    assert monitor._task.done()
