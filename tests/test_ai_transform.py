"""Tests for selection transforms (translate/define).

Covers the orchestrator ``transform`` fallback path and the
``POST /api/ai/transform`` endpoint contract. Providers are faked — no network.
"""

import types

import pytest
from app.ai_engine import AIProviderOrchestrator
from app.exceptions import AIServiceError


class FakeProvider:
    """Provider stub with scripted ``complete`` outcomes (str|Exception)."""

    def __init__(self, name, side_effects=None, healthy=True):
        self.name = name
        self.model = "fake-model"
        self.priority = 1
        self.healthy = healthy
        self._effects = list(side_effects) if side_effects else []
        self.complete_calls = []
        self.complete_count = 0

    async def health_check(self):
        return self.healthy

    async def complete(self, prompt, *, max_tokens=1000, temperature=0.3):
        self.complete_count += 1
        self.complete_calls.append(prompt)
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


@pytest.mark.asyncio
async def test_translate_happy_path():
    """Translate sends the selection through the provider and returns the result."""
    provider = FakeProvider("p", ["Hola"])
    orch = _orch(provider)

    result = await orch.transform("Hello", "translate")

    assert result == "Hola"
    assert orch.current_provider == "p"
    assert len(provider.complete_calls) == 1
    assert "Hello" in provider.complete_calls[0]


@pytest.mark.asyncio
async def test_define_happy_path():
    """Define builds a dictionary-style prompt."""
    provider = FakeProvider("p", ["noun: a greeting"])
    orch = _orch(provider)

    result = await orch.transform("hello", "define")

    assert "greeting" in result
    assert "dictionary" in provider.complete_calls[0].lower()


@pytest.mark.asyncio
async def test_unknown_mode_raises_value_error():
    orch = _orch(FakeProvider("p", ["x"]))

    with pytest.raises(ValueError, match="Unknown transform mode"):
        await orch.transform("text", "summarize")


@pytest.mark.asyncio
async def test_unhealthy_provider_is_skipped():
    dead = FakeProvider("dead", ["nope"], healthy=False)
    live = FakeProvider("live", ["definition"])
    orch = _orch(dead, live)

    result = await orch.transform("word", "define")

    assert result == "definition"
    assert dead.complete_count == 0


@pytest.mark.asyncio
async def test_all_providers_fail_raises():
    orch = _orch(
        FakeProvider("p1", [AIServiceError("e1")]),
        FakeProvider("p2", [AIServiceError("e2")]),
    )

    with pytest.raises(AIServiceError):
        await orch.transform("text", "translate")


# ---------------------------------------------
# Endpoint contract
# ---------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_rejects_invalid_input(client, monkeypatch):
    """Empty text, oversized text, and unknown mode all 422."""

    async def _fail():
        raise AssertionError("orchestrator must not be called")

    monkeypatch.setattr("app.routes.ai_tts.get_ai_orchestrator", _fail)

    for payload in (
        {"text": "", "mode": "translate"},
        {"text": "x" * 2001, "mode": "translate"},
        {"text": "word", "mode": "summarize"},
        {"mode": "translate"},
    ):
        resp = await client.post("/api/ai/transform", json=payload)
        assert resp.status_code == 422, payload


@pytest.mark.asyncio
async def test_endpoint_success(client, monkeypatch):
    """Valid request returns the result and provider name."""

    class _Orch:
        current_provider = "fake"

        async def transform(self, text, mode):
            assert text == "Hello"
            assert mode == "translate"
            return "Hola"

    async def _orch():
        return _Orch()

    monkeypatch.setattr("app.routes.ai_tts.get_ai_orchestrator", _orch)

    resp = await client.post(
        "/api/ai/transform", json={"text": "Hello", "mode": "translate"}
    )

    assert resp.status_code == 200
    assert resp.json() == {"result": "Hola", "provider": "fake"}


@pytest.mark.asyncio
async def test_endpoint_503_when_no_provider_healthy(client, monkeypatch):
    """All providers failing surfaces as 503 with the error message."""

    class _Orch:
        async def transform(self, text, mode):
            raise AIServiceError("All AI providers failed")

    async def _orch():
        return _Orch()

    monkeypatch.setattr("app.routes.ai_tts.get_ai_orchestrator", _orch)

    resp = await client.post(
        "/api/ai/transform", json={"text": "Hello", "mode": "translate"}
    )

    assert resp.status_code == 503
    assert "All AI providers failed" in resp.json()["detail"]
