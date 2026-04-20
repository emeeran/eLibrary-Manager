"""Groq API provider for AI summarization."""

from typing import Optional

from app.ai_providers.base import BaseAIProvider
from app.config import get_config
from app.exceptions import AIServiceError
from app.logging_config import get_logger

logger = get_logger(__name__)


class GroqProvider(BaseAIProvider):
    """Groq API provider.

    Secondary AI provider with extremely fast inference using Llama models.
    Great for quick summaries with good quality.
    """

    name = "groq"
    model = "llama-3.3-70b-versatile"
    priority = 2

    def __init__(self) -> None:
        """Initialize Groq provider.

        Raises:
            ValueError: If API key is not configured
        """
        super().__init__()
        self.config = get_config()

        if not self.config.groq_api_key:
            logger.warning("Groq API key not configured")
            self._available = False
            return

        self._available = True

    async def summarize(self, text: str, context: Optional[str] = None) -> str:
        """Generate a summary using Groq.

        Args:
            text: Text to summarize
            context: Optional context (book title, chapter info, etc.)

        Returns:
            Generated summary text

        Raises:
            AIServiceError: If summarization fails
        """
        if not self._available:
            raise AIServiceError("Groq provider is not available")

        try:
            from groq import Groq

            client = Groq(api_key=self.config.groq_api_key)
            prompt = self._build_prompt(text, context)

            logger.debug(f"Sending request to Groq: {len(text)} chars")

            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )

            summary = response.choices[0].message.content.strip()

            if not summary:
                raise AIServiceError("Empty summary received from Groq")

            logger.info(f"Groq summary generated: {len(summary)} chars")
            return summary

        except AIServiceError:
            raise
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise AIServiceError(
                f"Groq API error: {str(e)}",
                {"provider": "groq", "error_type": type(e).__name__}
            ) from e

    async def health_check(self) -> bool:
        """Check if Groq API is accessible.

        Returns:
            True if provider is available, False otherwise
        """
        if not self._available:
            return False

        try:
            from groq import Groq

            client = Groq(api_key=self.config.groq_api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1
            )
            return bool(response.choices[0].message.content)
        except Exception as e:
            logger.warning(f"Groq health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Groq client."""
        pass
