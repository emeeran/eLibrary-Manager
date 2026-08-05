"""Google Gemini API provider for AI summarization."""

import os

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

        Tries GOOGLE_API_KEY from config, then GEMINI_API_KEY from env.
        """
        super().__init__()
        self.config = get_config()

        # GEMINI_API_KEY env var takes priority over GOOGLE_API_KEY from config.
        # The google-genai SDK auto-reads GOOGLE_API_KEY from env and may use
        # an expired key, so we explicitly prefer the GEMINI_API_KEY if set.
        api_key = os.environ.get("GEMINI_API_KEY", "") or self.config.google_api_key

        if not api_key:
            logger.warning("Google API key not configured")
            self._available = False
            return

        self._available = True
        self._api_key = api_key
        self.model = self.config.google_model

    def _get_client(self) -> genai.Client:
        """Get a client that uses the config API key, not env var.

        The google-genai SDK auto-reads GOOGLE_API_KEY from the environment
        and ignores the api_key parameter when the env var is present.
        We temporarily unset it so our config key takes priority.

        A request timeout is applied via ``HttpOptions`` (milliseconds) so a
        hung Gemini call can never block the caller indefinitely.
        """
        saved = os.environ.pop("GOOGLE_API_KEY", None)
        try:
            return genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(
                    timeout=int(self.config.ai_request_timeout * 1000)
                ),
            )
        finally:
            if saved is not None:
                os.environ["GOOGLE_API_KEY"] = saved

    async def summarize(self, text: str, context: str | None = None) -> str:
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

            client = self._get_client()
            # Use the async surface (``client.aio``) so this never blocks the
            # event loop while waiting on the network.
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=500,
                    temperature=0.7,
                ),
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
                {"provider": "google", "error_type": type(e).__name__},
            ) from e

    async def _perform_health_check(self) -> bool:
        """Check if Google Gemini API is accessible.

        Returns:
            True if provider is available, False otherwise
        """
        if not self._available:
            return False

        try:
            client = self._get_client()
            response = await client.aio.models.generate_content(
                model=self.model,
                contents="test",
                config=types.GenerateContentConfig(max_output_tokens=1),
            )
            return bool(response.text)
        except Exception as e:
            logger.warning(f"Google Gemini health check failed: {e}")
            return False
