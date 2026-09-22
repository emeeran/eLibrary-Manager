"""Tests for settings routes."""

import pytest


@pytest.mark.asyncio
async def test_test_ai_connection_awaits_orchestrator(client, monkeypatch):
    """POST /api/settings/test-ai must await get_ai_orchestrator (regression).

    Previously ``orchestrator = get_ai_orchestrator()`` (no ``await``) left a
    coroutine object, so ``orchestrator.generate_summary`` raised AttributeError
    and the endpoint returned an error on every call.
    """

    class _FakeOrch:
        async def generate_summary(self, **kwargs):
            return "connection ok"

    async def _fake_get():
        return _FakeOrch()

    monkeypatch.setattr("app.routes.settings.get_ai_orchestrator", _fake_get)

    resp = await client.post("/api/settings/test-ai", json={"provider": "google"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["test_summary"] == "connection ok"
