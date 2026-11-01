"""Tests for reader-mode settings keys (spec 002 v1.1, AC-002.55).

Auto-scroll speed and page-turn animation round-trip through the settings
API; invalid values are rejected by pydantic validation before persistence.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_reader_mode_settings_roundtrip(client) -> None:
    """AC-002.55: new keys persist and are returned by GET /api/settings."""
    resp = await client.post(
        "/api/settings",
        json={"auto_scroll_speed": 120, "page_turn_animation": "fade"},
    )
    assert resp.status_code == 200

    fetched = await client.get("/api/settings")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["auto_scroll_speed"] == 120
    assert body["page_turn_animation"] == "fade"


async def test_reader_mode_settings_defaults(client) -> None:
    """Unset keys surface the documented defaults (off / no animation)."""
    fetched = await client.get("/api/settings")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["auto_scroll_speed"] == 0
    assert body["page_turn_animation"] == "none"


async def test_reader_mode_settings_validation(client) -> None:
    """AC-002.55: out-of-range / wrong-pattern values are rejected (422)."""
    bad_animation = await client.post(
        "/api/settings",
        json={"page_turn_animation": "curl3d"},
    )
    assert bad_animation.status_code == 422

    negative_speed = await client.post(
        "/api/settings",
        json={"auto_scroll_speed": -5},
    )
    assert negative_speed.status_code == 422

    huge_speed = await client.post(
        "/api/settings",
        json={"auto_scroll_speed": 5000},
    )
    assert huge_speed.status_code == 422

    # Nothing was stored by the rejected requests.
    fetched = await client.get("/api/settings")
    body = fetched.json()
    assert body["page_turn_animation"] == "none"
    assert body["auto_scroll_speed"] == 0
