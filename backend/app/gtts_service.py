"""gTTS (Google Text-to-Speech) service for eBook Manager.

Uses gTTS library to generate speech from text.
"""

import asyncio
from typing import Optional

from app.logging_config import get_logger

logger = get_logger(__name__)


class GTTSError(Exception):
    """gTTS service error."""

    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(message)


class GTTSService:
    """Google Text-to-Speech service using gTTS library."""

    # Available language codes for gTTS
    LANGUAGES = {
        'en': 'English',
        'en-US': 'English (US)',
        'en-GB': 'English (UK)',
        'en-AU': 'English (Australia)',
        'en-CA': 'English (Canada)',
        'en-IN': 'English (India)',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'it': 'Italian',
        'pt': 'Portuguese',
        'pt-BR': 'Portuguese (Brazil)',
        'ru': 'Russian',
        'ja': 'Japanese',
        'ko': 'Korean',
        'zh-CN': 'Chinese (Simplified)',
        'zh-TW': 'Chinese (Traditional)',
        'ar': 'Arabic',
        'hi': 'Hindi',
        'nl': 'Dutch',
        'pl': 'Polish',
        'sv': 'Swedish',
        'da': 'Danish',
        'no': 'Norwegian',
        'fi': 'Finnish',
        'tr': 'Turkish',
        'cs': 'Czech',
        'el': 'Greek',
        'he': 'Hebrew',
        'th': 'Thai',
        'vi': 'Vietnamese',
        'id': 'Indonesian',
        'ms': 'Malay',
        'ro': 'Romanian',
        'uk': 'Ukrainian',
    }

    # Slow speech rate flag
    SLOW = False

    # Default language
    DEFAULT_LANG = 'en'

    # Default TLD (top-level domain for Google Translate)
    DEFAULT_TLD = 'com'

    @classmethod
    async def get_voices(cls) -> list[dict]:
        """Get list of available voices/languages.

        Returns:
            List of voice dictionaries with ShortName and FriendlyName
        """
        voices = []
        for code, name in cls.LANGUAGES.items():
            # Handle dialect codes properly
            if '-' in code:
                main_lang, dialect = code.split('-', 1)
                friendly_name = f"{name} ({dialect.upper()})"
            else:
                friendly_name = name

            voices.append({
                'ShortName': code,
                'FriendlyName': friendly_name,
                'Locale': code,
                'Gender': 'Unknown'  # gTTS doesn't provide gender info
            })

        return voices

    @classmethod
    def _get_slow_flag(cls) -> str:
        """Get the slow flag parameter for gTTS."""
        return 'slow' if cls.SLOW else 'normal'

    @classmethod
    def _generate_audio_sync(
        cls,
        text: str,
        lang: str = 'en',
        slow: bool = False,
        tld: str = 'com'
    ) -> bytes:
        """Generate audio from text using gTTS (synchronous).

        Args:
            text: Text to convert to speech
            lang: Language code (default: 'en')
            slow: Whether to use slow speech (default: False)
            tld: Top-level domain for Google Translate (default: 'com')

        Returns:
            MP3 audio data as bytes

        Raises:
            GTTSError: If TTS generation fails
        """
        import io
        import traceback

        try:
            from gtts import gTTS
            from gtts.tts import gTTSError

            # Validate input
            if not text or not text.strip():
                raise ValueError("Text cannot be empty")

            text = text.strip()

            # Log parameters for debugging
            logger.info(f"gTTS request: text_length={len(text)}, lang={lang}, slow={slow}, tld={tld}")

            # Create gTTS object
            tts = gTTS(
                text=text,
                lang=lang,
                slow=slow,
                tld=tld
            )

            # Generate audio to bytes
            audio_fp = io.BytesIO()
            tts.write_to_fp(audio_fp)
            audio_data = audio_fp.getvalue()

            logger.info(f"Generated {len(audio_data)} bytes of audio using gTTS (lang={lang})")
            return audio_data

        except ImportError as e:
            logger.error(f"gTTS library not installed: {e}")
            raise GTTSError(
                "gTTS library not installed",
                "Install it with: uv add gtts"
            )
        except ValueError as e:
            logger.error(f"Invalid input for gTTS: {e}")
            raise GTTSError(
                "Invalid input",
                str(e)
            )
        except Exception as e:
            logger.error(f"gTTS generation failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            raise GTTSError(
                "Failed to generate speech",
                f"{type(e).__name__}: {str(e)}"
            )

    @classmethod
    async def generate_audio(
        cls,
        text: str,
        lang: str = 'en',
        slow: bool = False,
        tld: str = 'com'
    ) -> bytes:
        """Generate audio from text using gTTS (async wrapper).

        Args:
            text: Text to convert to speech
            lang: Language code (default: 'en')
            slow: Whether to use slow speech (default: False)
            tld: Top-level domain for Google Translate (default: 'com')

        Returns:
            MP3 audio data as bytes

        Raises:
            GTTSError: If TTS generation fails
        """
        # Run the synchronous gTTS generation in a thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,  # Use default executor
            cls._generate_audio_sync,
            text, lang, slow, tld
        )

    @classmethod
    def get_default_voice(cls) -> str:
        """Get the default voice/language."""
        return cls.DEFAULT_LANG

    @classmethod
    async def text_to_speech(
        cls,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> bytes:
        """Convert text to speech with gTTS.

        Args:
            text: Text to speak
            voice: Language code (default: 'en')
            rate: Playback rate (not fully supported by gTTS)
            pitch: Pitch adjustment (not supported by gTTS)

        Returns:
            MP3 audio bytes
        """
        # Use default language if not specified
        lang = voice or cls.DEFAULT_LANG

        # Extract TLD from voice if needed (e.g., 'en-IN.co.in')
        slow = False
        tld = cls.DEFAULT_TLD

        # gTTS doesn't support rate/pitch, but we can use slow flag
        # for lower rate
        if rate:
            rate_val = float(rate)
            if rate_val < 0.75:
                slow = True

        try:
            return await cls.generate_audio(text, lang=lang, slow=slow, tld=tld)
        except Exception as e:
            raise GTTSError(f"Text-to-speech failed: {str(e)}")


# Global instance
_gtts_service = None


def get_gtts_service() -> GTTSService:
    """Get or create the global gTTS service instance."""
    global _gtts_service
    if _gtts_service is None:
        _gtts_service = GTTSService()
    return _gtts_service
