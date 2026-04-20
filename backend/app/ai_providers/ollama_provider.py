"""Ollama API provider for AI summarization (Cloud and Local)."""

from typing import Optional

from openai import AsyncOpenAI

from app.ai_providers.base import BaseAIProvider
from app.config import get_config
from app.exceptions import AIServiceError
from app.logging_config import get_logger

logger = get_logger(__name__)


class OllamaCloudProvider(BaseAIProvider):
    """Ollama Cloud API provider.

    Tertiary AI provider using Ollama's cloud service.
    Good quality with moderate speed.
    """

    name = "ollama_cloud"
    model = "llama3.3"
    priority = 3

    def __init__(self) -> None:
        """Initialize Ollama Cloud provider."""
        super().__init__()
        self.config = get_config()

        self._base_url = self.config.ollama_cloud_url
        self._available = True  # Ollama doesn't require auth

    async def summarize(self, text: str, context: Optional[str] = None) -> str:
        """Generate a summary using Ollama Cloud.

        Args:
            text: Text to summarize
            context: Optional context (book title, chapter info, etc.)

        Returns:
            Generated summary text

        Raises:
            AIServiceError: If summarization fails
        """
        try:
            client = AsyncOpenAI(
                base_url=f"{self._base_url}/v1",
                api_key="ollama"  # Ollama doesn't require real key
            )

            prompt = self._build_prompt(text, context)

            logger.debug(f"Sending request to Ollama Cloud: {len(text)} chars")

            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )

            summary = response.choices[0].message.content.strip()

            if not summary:
                raise AIServiceError("Empty summary received from Ollama Cloud")

            logger.info(f"Ollama Cloud summary generated: {len(summary)} chars")
            return summary

        except AIServiceError:
            raise
        except Exception as e:
            logger.error(f"Ollama Cloud API error: {e}")
            raise AIServiceError(
                f"Ollama Cloud API error: {str(e)}",
                {"provider": "ollama_cloud", "error_type": type(e).__name__}
            ) from e

    async def health_check(self) -> bool:
        """Check if Ollama Cloud is accessible.

        Returns:
            True if provider is available, False otherwise
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama Cloud health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Ollama Cloud client."""
        pass


class OllamaLocalProvider(BaseAIProvider):
    """Local Ollama instance provider.

    Fallback AI provider for offline capability.
    Requires Ollama to be running locally on port 11434.
    """

    name = "ollama_local"
    model = "llama3.2:3b"
    priority = 4

    def __init__(self) -> None:
        """Initialize Ollama Local provider."""
        super().__init__()
        self.config = get_config()

        self._base_url = self.config.ollama_local_url
        self._available = True  # Will verify on health check

    async def summarize(self, text: str, context: Optional[str] = None) -> str:
        """Generate a summary using local Ollama.

        Args:
            text: Text to summarize
            context: Optional context (book title, chapter info, etc.)

        Returns:
            Generated summary text

        Raises:
            AIServiceError: If summarization fails or Ollama not running
        """
        try:
            client = AsyncOpenAI(
                base_url=f"{self._base_url}/v1",
                api_key="ollama"
            )

            prompt = self._build_prompt(text, context)

            logger.debug(f"Sending request to local Ollama: {len(text)} chars")

            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )

            summary = response.choices[0].message.content.strip()

            if not summary:
                raise AIServiceError("Empty summary received from local Ollama")

            logger.info(f"Local Ollama summary generated: {len(summary)} chars")
            return summary

        except AIServiceError:
            raise
        except Exception as e:
            logger.error(f"Local Ollama API error: {e}")
            raise AIServiceError(
                f"Local Ollama error: {str(e)}",
                {"provider": "ollama_local", "error_type": type(e).__name__}
            ) from e

    async def health_check(self) -> bool:
        """Check if local Ollama is running.

        Returns:
            True if Ollama is available, False otherwise
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                is_running = response.status_code == 200

            if is_running:
                self._available = True
            else:
                self._available = False

            return is_running
        except Exception as e:
            logger.debug(f"Local Ollama health check failed: {e}")
            self._available = False
            return False

    async def close(self) -> None:
        """Close the local Ollama client."""
        pass
