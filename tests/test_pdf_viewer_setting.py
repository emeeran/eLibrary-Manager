"""Tests for the opt-in default PDF viewer toggle (spec 014)."""

import pytest
from app.repositories import SettingsRepository
from app.routes import settings as settings_routes


@pytest.fixture
def fake_xdg(monkeypatch):
    """Stub _run_xdg_mime with a scripted queue of (ok, output) results.

    Records issued commands so tests can assert the exact xdg-mime calls.
    """
    calls: list[tuple[str, ...]] = []
    queue: list[tuple[bool, str]] = []

    async def _fake(*args: str) -> tuple[bool, str]:
        calls.append(args)
        return queue.pop(0) if queue else (True, "")

    monkeypatch.setattr(settings_routes, "_run_xdg_mime", _fake)
    return {"calls": calls, "queue": queue}


@pytest.mark.asyncio
async def test_status_reports_enabled_state(client, fake_xdg):
    """Status reflects whatever xdg-mime query returns."""
    fake_xdg["queue"].append((True, "org.gnome.Evince.desktop"))
    resp = await client.get("/api/settings/pdf-viewer")
    body = resp.json()
    assert resp.status_code == 200
    assert body["enabled"] is False
    assert body["current"] == "org.gnome.Evince.desktop"
    assert body["desktop"] == "elibrary-manager.desktop"

    fake_xdg["queue"].append((True, "elibrary-manager.desktop"))
    resp = await client.get("/api/settings/pdf-viewer")
    assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_enable_records_previous_and_registers(client, fake_xdg, db_session):
    """Enabling saves the displaced handler and registers the desktop entry."""
    fake_xdg["queue"].append((True, "org.gnome.Evince.desktop"))  # query
    fake_xdg["queue"].append((True, ""))  # default

    resp = await client.post("/api/settings/pdf-viewer", json={"enabled": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["previous"] == "org.gnome.Evince.desktop"

    assert fake_xdg["calls"][0] == ("query", "default", settings_routes._PDF_MIME)
    assert fake_xdg["calls"][1] == (
        "default",
        "elibrary-manager.desktop",
        settings_routes._PDF_MIME,
    )
    stored = (await SettingsRepository(db_session).get_all()).get(
        settings_routes._PDF_PREVIOUS_KEY
    )
    assert stored == "org.gnome.Evince.desktop"


@pytest.mark.asyncio
async def test_enable_is_idempotent_when_already_default(client, fake_xdg):
    """Re-enabling when already registered doesn't clobber the saved handler."""
    fake_xdg["queue"].append((True, "elibrary-manager.desktop"))  # query: already ours
    resp = await client.post("/api/settings/pdf-viewer", json={"enabled": True})
    assert resp.status_code == 200
    # Only the query ran — no default call, no previous recorded
    assert len(fake_xdg["calls"]) == 1


@pytest.mark.asyncio
async def test_disable_restores_previous_handler(client, fake_xdg, db_session):
    """Disabling restores the handler recorded at enable time."""
    await SettingsRepository(db_session).set_many(
        {settings_routes._PDF_PREVIOUS_KEY: "org.gnome.Evince.desktop"}
    )

    resp = await client.post("/api/settings/pdf-viewer", json={"enabled": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["restored"] is True
    assert fake_xdg["calls"][0] == ("default", "org.gnome.Evince.desktop", "application/pdf")


@pytest.mark.asyncio
async def test_disable_without_recorded_previous_is_honest(client, fake_xdg, db_session):
    """No previous handler recorded → say so, change nothing."""
    resp = await client.post("/api/settings/pdf-viewer", json={"enabled": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["restored"] is False
    assert fake_xdg["calls"] == []
