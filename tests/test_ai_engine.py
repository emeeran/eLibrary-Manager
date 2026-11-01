"""Tests for AI orchestration (spec 003): fallback, retry/backoff, single-flight.

Providers are faked — no network. Covers the audit-batch changes in
``ai_engine.py`` (per-provider retry) and ``reader_service.py`` (single-flight
coalescing of concurrent summary requests).
"""

import asyncio
import types

import pytest
from app.ai_engine import AIProviderOrchestrator
from app.exceptions import AIServiceError


class FakeProvider:
    """Minimal provider stub. ``side_effects`` is a queue of str|Exception."""

    def __init__(self, name, side_effects=None, healthy=True):
        self.name = name
        self.model = "fake-model"
        self.priority = 1
        self.healthy = healthy
        self._effects = list(side_effects) if side_effects else []
        self.summarize_calls = 0

    async def health_check(self):
        return self.healthy

    async def summarize(self, text, context=None):
        self.summarize_calls += 1
        if not self._effects:
            raise AIServiceError(f"{self.name} side effects exhausted")
        outcome = self._effects.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _orch(*providers, max_retries=0):
    """Build an orchestrator without running ``_initialize_providers``."""
    orch = AIProviderOrchestrator.__new__(AIProviderOrchestrator)
    orch.providers = list(providers)
    orch.current_provider = None
    orch.config = types.SimpleNamespace(ai_max_retries=max_retries, ai_request_timeout=1.0)
    return orch


LONG_TEXT = "word " * 40  # > 100 chars, no HTML -> reaches the provider


@pytest.mark.asyncio
async def test_fallback_to_secondary_on_primary_failure():
    """Primary raises AIServiceError -> orchestrator falls back to secondary."""
    primary = FakeProvider("primary", [AIServiceError("boom")])
    secondary = FakeProvider("secondary", ["secondary summary"])
    orch = _orch(primary, secondary)

    result = await orch.summarize(LONG_TEXT)

    assert result == "secondary summary"
    assert orch.current_provider == "secondary"
    assert primary.summarize_calls == 1


@pytest.mark.asyncio
async def test_all_providers_fail_raises(monkeypatch):
    """Every provider failing surfaces a single AIServiceError."""

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("app.ai_engine.asyncio.sleep", _no_sleep)
    orch = _orch(
        FakeProvider("p1", [AIServiceError("e1")]),
        FakeProvider("p2", [AIServiceError("e2")]),
        max_retries=1,
    )

    with pytest.raises(AIServiceError):
        await orch.summarize(LONG_TEXT)


@pytest.mark.asyncio
async def test_unhealthy_provider_is_skipped():
    """A provider whose health_check is False is never called."""
    dead = FakeProvider("dead", ["should-not-happen"], healthy=False)
    live = FakeProvider("live", ["live summary"])
    orch = _orch(dead, live)

    result = await orch.summarize(LONG_TEXT)

    assert result == "live summary"
    assert dead.summarize_calls == 0


@pytest.mark.asyncio
async def test_retry_then_success(monkeypatch):
    """Transient failures are retried; success on the 3rd attempt."""
    sleeps = []

    async def _track_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr("app.ai_engine.asyncio.sleep", _track_sleep)
    provider = FakeProvider("p", [AIServiceError("e"), AIServiceError("e"), "ok"])
    orch = _orch(provider, max_retries=2)

    result = await orch.summarize(LONG_TEXT)

    assert result == "ok"
    assert provider.summarize_calls == 3  # 1 initial + 2 retries
    assert len(sleeps) == 2  # backoff between attempts
    assert orch.current_provider == "p"


@pytest.mark.asyncio
async def test_retry_exhausted_falls_through_to_next_provider(monkeypatch):
    """After exhausting retries on the primary, the next provider is tried."""

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("app.ai_engine.asyncio.sleep", _no_sleep)
    primary = FakeProvider("p1", [AIServiceError("e")] * 3)  # 1 + 2 retries all fail
    secondary = FakeProvider("p2", ["p2 summary"])
    orch = _orch(primary, secondary, max_retries=2)

    result = await orch.summarize(LONG_TEXT)

    assert result == "p2 summary"
    assert primary.summarize_calls == 3
    assert secondary.summarize_calls == 1


@pytest.mark.asyncio
async def test_short_text_returns_placeholder_without_calling_providers():
    """Text under the min length short-circuits — no provider is contacted."""
    provider = FakeProvider("p", ["x"])
    orch = _orch(provider)

    result = await orch.summarize("too short")

    assert "too short to summarize" in result.lower()
    assert provider.summarize_calls == 0


@pytest.mark.asyncio
async def test_chapter_summary_single_flight(db_session, monkeypatch):
    """Two concurrent requests for the same chapter share one AI call."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate
    from app.services.reader_service import ReaderService

    book = await BookRepository(db_session).create(
        BookCreate(title="T", author="A", path="/x.epub", format="EPUB", file_size=1)
    )
    await db_session.flush()

    chapter_text = "sentence " * 30  # > 100 chars

    async def slow_chapter(_path, _idx):
        await asyncio.sleep(0.02)  # force the two requests to overlap
        return chapter_text, "Ch1", 1

    monkeypatch.setattr(
        "app.reader_engine.get_reader_engine",
        lambda: types.SimpleNamespace(get_chapter_content=slow_chapter),
    )

    call_count = 0

    class CountingOrchestrator:
        async def summarize(self, _text, context=None):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.02)
            return "coalesced summary"

        async def get_active_provider(self):
            return "fake"

    counter = CountingOrchestrator()

    async def _get_orch():
        return counter

    monkeypatch.setattr("app.services.reader_service.get_ai_orchestrator", _get_orch)

    svc = ReaderService(db_session)
    r1, r2 = await asyncio.gather(
        svc.get_chapter_summary(book.id, 0),
        svc.get_chapter_summary(book.id, 0),
    )

    assert call_count == 1  # single-flight: exactly one provider call
    assert r1.summary_text == r2.summary_text == "coalesced summary"


@pytest.mark.asyncio
async def test_get_provider_status_reports_health():
    dead = FakeProvider("dead", healthy=False)
    live = FakeProvider("live", healthy=True)
    orch = _orch(dead, live)

    status = await orch.get_provider_status()

    by_name = {s["name"]: s for s in status}
    assert by_name["dead"]["available"] is False
    assert by_name["live"]["available"] is True


@pytest.mark.asyncio
async def test_health_check_counts_healthy_providers():
    orch = _orch(FakeProvider("a", healthy=True), FakeProvider("b", healthy=False))

    health = await orch.health_check()

    assert health["total_providers"] == 2
    assert health["healthy_providers"] == 1


@pytest.mark.asyncio
async def test_get_active_provider_defaults_to_none():
    assert await _orch().get_active_provider() == "none"


@pytest.mark.asyncio
async def test_generate_summary_delegates_to_summarize():
    orch = _orch(FakeProvider("p", ["generated"]))
    assert await orch.generate_summary(1, 0, LONG_TEXT) == "generated"
