"""EdgeTTS service for neural text-to-speech.

Uses Microsoft Edge's free TTS API via the edge-tts package.
"""

from typing import AsyncGenerator

import edge_tts

from app.logging_config import get_logger

logger = get_logger(__name__)


class EdgeTTSError(Exception):
    """Base exception for EdgeTTS errors."""

    def __init__(self, message: str, details: str | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class EdgeTTSService:
    """Service for EdgeTTS neural text-to-speech."""

    # Common voices with descriptions
    VOICES = {
        # English US
        "en-US-AriaNeural": "Aria (US, Female)",
        "en-US-GuyNeural": "Guy (US, Male)",
        "en-US-JennyNeural": "Jenny (US, Female)",
        "en-US-MichelleNeural": "Michelle (US, Female)",
        # English UK
        "en-GB-SoniaNeural": "Sonia (UK, Female)",
        "en-GB-RyanNeural": "Ryan (UK, Male)",
        "en-GB-LibbyNeural": "Libby (UK, Female)",
        "en-GB-MiaNeural": "Mia (UK, Female)",
        # English India
        "en-IN-NeerjaNeural": "Neerja (India, Female)",
        "en-IN-PrabhatNeural": "Prabhat (India, Male)",
        # English Australia
        "en-AU-NatashaNeural": "Natasha (Australia, Female)",
        "en-AU-WilliamNeural": "William (Australia, Male)",
        # English Canada
        "en-CA-ClaraNeural": "Clara (Canada, Female)",
        "en-CA-LiamNeural": "Liam (Canada, Male)",
        # Spanish
        "es-ES-ElviraNeural": "Elvira (Spain, Female)",
        "es-MX-DaliaNeural": "Dalia (Mexico, Female)",
        # French
        "fr-FR-DeniseNeural": "Denise (France, Female)",
        "fr-FR-HenriNeural": "Henri (France, Male)",
        # German
        "de-DE-KatjaNeural": "Katja (Germany, Female)",
        "de-DE-ConradNeural": "Conrad (Germany, Male)",
        # Italian
        "it-IT-ElsaNeural": "Elsa (Italy, Female)",
        "it-IT-DiegoNeural": "Diego (Italy, Male)",
        # Portuguese
        "pt-BR-FranciscaNeural": "Francisca (Brazil, Female)",
        "pt-PT-AmeliaNeural": "Amelia (Portugal, Female)",
        # Japanese
        "ja-JP-NanamiNeural": "Nanami (Japan, Female)",
        "ja-JP-KeitaNeural": "Keita (Japan, Male)",
        # Korean
        "ko-KR-SunHiNeural": "SunHi (Korea, Female)",
        "ko-KR-InJoonNeural": "InJoon (Korea, Male)",
        # Chinese
        "zh-CN-XiaoxiaoNeural": "Xiaoxiao (China, Female)",
        "zh-CN-YunyangNeural": "Yunyang (China, Male)",
    }

    DEFAULT_VOICE = "en-US-JennyNeural"

    # Rate ranges (EdgeTTS uses percentage)
    MIN_RATE = -50  # 0.5x
    MAX_RATE = 100  # 2.0x
    DEFAULT_RATE = 0  # 1.0x

    @classmethod
    async def get_voices(cls) -> list[dict]:
        """Get available voices.

        Returns:
            List of voice dictionaries with id, name, and locale
        """
        voices = []
        for voice_id, name in cls.VOICES.items():
            parts = voice_id.split("-")
            lang = parts[0]
            locale = f"{parts[0]}-{parts[1]}" if len(parts) > 1 else lang
            voices.append({
                "id": voice_id,
                "name": name,
                "locale": locale,
                "language": lang
            })
        return voices

    @classmethod
    def normalize_rate(cls, rate: float) -> str:
        """Convert rate (0.5-2.0) to EdgeTTS percentage (-50 to 100).

        Args:
            rate: Playback rate from 0.5 to 2.0

        Returns:
            Rate as string percentage with sign (e.g., "+0%", "-10%", "+20%")
        """
        # Convert 0.5-2.0 range to -50 to 100 percentage
        percentage = int((rate - 1.0) * 100)
        percentage = max(cls.MIN_RATE, min(cls.MAX_RATE, percentage))
        # EdgeTTS requires a sign (+ or -)
        return f"{percentage:+d}%"

    @classmethod
    def get_default_voice(cls) -> str:
        """Get the default voice."""
        return cls.DEFAULT_VOICE

    @classmethod
    async def generate_audio(
        cls,
        text: str,
        voice: str | None = None,
        rate: float = 1.0,
        pitch: str = "+0Hz"
    ) -> bytes:
        """Generate audio from text using EdgeTTS.

        Args:
            text: Text to synthesize
            voice: Voice ID (defaults to en-US-JennyNeural)
            rate: Playback rate (0.5 to 2.0)
            pitch: Pitch adjustment (e.g., "+0Hz", "-10Hz", "+20Hz")

        Returns:
            MP3 audio bytes

        Raises:
            EdgeTTSError: If synthesis fails
        """
        voice = voice or cls.DEFAULT_VOICE
        rate_str = cls.normalize_rate(rate)

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate_str,
                pitch=pitch
            )

            # Collect audio chunks
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            if not audio_chunks:
                raise EdgeTTSError("No audio data generated")

            logger.info(f"Generated {len(b''.join(audio_chunks))} bytes using EdgeTTS (voice={voice})")
            return b"".join(audio_chunks)

        except Exception as e:
            logger.error(f"EdgeTTS error: {e}")
            raise EdgeTTSError(
                "Failed to generate audio",
                details=str(e)
            ) from e

    @classmethod
    async def stream_audio(
        cls,
        text: str,
        voice: str | None = None,
        rate: float = 1.0,
        pitch: str = "+0Hz"
    ) -> AsyncGenerator[bytes, None]:
        """Stream audio from text using EdgeTTS.

        Args:
            text: Text to synthesize
            voice: Voice ID (defaults to en-US-JennyNeural)
            rate: Playback rate (0.5 to 2.0)
            pitch: Pitch adjustment

        Yields:
            MP3 audio chunks

        Raises:
            EdgeTTSError: If synthesis fails
        """
        voice = voice or cls.DEFAULT_VOICE
        rate_str = cls.normalize_rate(rate)

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate_str,
                pitch=pitch
            )

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        except Exception as e:
            logger.error(f"EdgeTTS streaming error: {e}")
            raise EdgeTTSError(
                "Failed to stream audio",
                details=str(e)
            ) from e


# Singleton instance
_edgetts_service: EdgeTTSService | None = None


def get_edgetts_service() -> EdgeTTSService:
    """Get the EdgeTTS service singleton."""
    global _edgetts_service
    if _edgetts_service is None:
        _edgetts_service = EdgeTTSService()
    return _edgetts_service
