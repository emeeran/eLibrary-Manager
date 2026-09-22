"""Tests for the TTS voice catalog (spec 006 v1.1, AC-006.19)."""

import pytest
from app.edgetts_service import EdgeTTSService

EXPECTED_US_MALES = {
    "en-US-GuyNeural",
    "en-US-AndrewNeural",
    "en-US-BrianNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural",
    "en-US-RogerNeural",
    "en-US-SteffanNeural",
}


def test_us_male_voice_catalog():
    """AC-006.19: the seven US male neural voices are all offered."""
    assert EXPECTED_US_MALES <= set(EdgeTTSService.VOICES)
    for voice_id in EXPECTED_US_MALES:
        assert "Male" in EdgeTTSService.VOICES[voice_id]


@pytest.mark.asyncio
async def test_voices_endpoint_exposes_us_males(client):
    """The API serves the expanded catalog with locale metadata."""
    resp = await client.get("/api/tts/voices", params={"engine": "edgetts"})
    assert resp.status_code == 200
    data = resp.json()
    ids = {v["id"] for v in data["voices"]}
    assert EXPECTED_US_MALES <= ids
