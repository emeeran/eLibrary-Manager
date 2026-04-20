"""Google Gemini API provider for AI summarization."""

from typing import Optional

from google import genai
from google.genai import types

from app.ai_providers.base import BaseAIProvider
from app.config import get_config
from app.exceptions import AIServiceError
from app.logging_config import get_logger

logger = get_logger(__name__)


class GoogleProvider(BaseAIProvider):
    """Google Gemini API provider.

    Primary AI provider with high-quality summaries and fast inference.
    Uses the Gemini model specified in config.
    """

    name = "google"
    model = "gemini-1.5-flash"  # Default, will be overridden from config
    priority = 1

    def __init__(self) -> None:
        """Initialize Google Gemini provider.

        Raises:
            ValueError: If API key is not configured
        """
        super().__init__()
        self.config = get_config()

        if not self.config.google_api_key:
            logger.warning("Google API key not configured")
            self._available = False
            return

        self._available = True
        self._client = genai.Client(api_key=self.config.google_api_key)
        # Use model from config
        self.model = self.config.google_model

    async def summarize(self, text: str, context: Optional[str] = None) -> str:
        """Generate a summary using Google Gemini.

        Args:
            text: Text to summarize
            context: Optional context (book title, chapter info, etc.)

        Returns:
            Generated summary text

        Raises:
            AIServiceError: If summarization fails
        """
        if not self._available:
            raise AIServiceError("Google provider is not available")

        try:
            prompt = self._build_prompt(text, context)

            logger.debug(f"Sending request to Google Gemini: {len(text)} chars")

            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=500,
                    temperature=0.7,
                )
            )

            summary = response.text.strip()

            if not summary:
                raise AIServiceError("Empty summary received from Google Gemini")

            logger.info(f"Google Gemini summary generated: {len(summary)} chars")
            return summary

        except AIServiceError:
            raise
        except Exception as e:
            logger.error(f"Google Gemini API error: {e}")
            raise AIServiceError(
                f"Google Gemini API error: {str(e)}",
                {"provider": "google", "error_type": type(e).__name__}
            ) from e

    async def health_check(self) -> bool:
        """Check if Google Gemini API is accessible.

        Returns:
            True if provider is available, False otherwise
        """
        if not self._available:
            return False

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents="test",
                config=types.GenerateContentConfig(max_output_tokens=1)
            )
            return bool(response.text)
        except Exception as e:
            logger.warning(f"Google Gemini health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Google client."""
        self._client = None
