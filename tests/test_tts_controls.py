"""Tests for TTS playback-control settings keys (spec 006 v1.2, AC-006.28).

Sentence interval and character filter round-trip through the settings API;
invalid values are rejected by pydantic validation before persistence.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_tts_control_settings_roundtrip(client) -> None:
    """AC-006.28: new keys persist and are returned by GET /api/settings."""
    resp = await client.post(
        "/api/settings",
        json={"tts_sentence_interval": 350, "tts_char_filter": "*#_"},
    )
    assert resp.status_code == 200

    fetched = await client.get("/api/settings")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["tts_sentence_interval"] == 350
    assert body["tts_char_filter"] == "*#_"


async def test_tts_control_settings_defaults(client) -> None:
    """Unset keys surface the documented defaults (no gap, no filter)."""
    fetched = await client.get("/api/settings")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["tts_sentence_interval"] == 0
    assert body["tts_char_filter"] == ""


async def test_tts_control_settings_validation(client) -> None:
    """AC-006.28: out-of-range / over-length values are rejected (422)."""
    too_big = await client.post(
        "/api/settings",
        json={"tts_sentence_interval": 5000},
    )
    assert too_big.status_code == 422

    negative = await client.post(
        "/api/settings",
        json={"tts_sentence_interval": -100},
    )
    assert negative.status_code == 422

    too_long = await client.post(
        "/api/settings",
        json={"tts_char_filter": "x" * 101},
    )
    assert too_long.status_code == 422

    # Nothing was stored by the rejected requests.
    fetched = await client.get("/api/settings")
    body = fetched.json()
    assert body["tts_sentence_interval"] == 0
    assert body["tts_char_filter"] == ""
