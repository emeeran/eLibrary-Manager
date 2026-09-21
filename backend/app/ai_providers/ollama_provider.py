"""Unified Ollama API provider for AI summarization (Cloud and Local)."""

import httpx
from openai import AsyncOpenAI

from app.ai_providers.base import BaseAIProvider
from app.exceptions import AIServiceError
from app.logging_config import get_logger

logger = get_logger(__name__)


class OllamaProvider(BaseAIProvider):
    """Ollama provider supporting both cloud and local instances.

    Uses the OpenAI-compatible API that Ollama exposes.
    Maintains a shared httpx.AsyncClient for connection pooling.
    """

    def __init__(
        self,
        name: str = "ollama",
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        priority: int = 4,
        health_timeout: float = 2.0,
    ) -> None:
        """Initialize Ollama provider.

        Args:
            name: Provider display name (e.g. 'ollama_cloud', 'ollama_local')
            base_url: Ollama server URL
            model: Model name to use
            priority: Fallback priority (lower = higher priority)
            health_timeout: Timeout for health check requests
        """
        super().__init__()
        self.name = name
        self.model = model
        self.priority = priority
        self._base_url = base_url
        self._health_timeout = health_timeout
        self._available = True
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create a shared httpx client for connection pooling."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self._health_timeout)
        return self._http_client

    async def summarize(self, text: str, context: str | None = None) -> str:
        """Generate a summary using Ollama.

        Args:
            text: Text to summarize
            context: Optional context (book title, chapter info, etc.)

        Returns:
            Generated summary text

        Raises:
            AIServiceError: If summarization fails
        """
        logger.debug(f"Sending request to {self.name}: {len(text)} chars")
        return await self.complete(
            self._build_prompt(text, context), max_tokens=500, temperature=0.7
        )

    async def complete(
        self, prompt: str, *, max_tokens: int = 1000, temperature: float = 0.3
    ) -> str:
        """Send an arbitrary prompt to Ollama.

        Args:
            prompt: Full prompt text.
            max_tokens: Response token cap.
            temperature: Sampling temperature.

        Returns:
            Model response text.

        Raises:
            AIServiceError: If the request fails or returns empty text.
        """
        try:
            client = AsyncOpenAI(
                base_url=f"{self._base_url}/v1",
                api_key="ollama",  # Ollama doesn't require real key
            )

            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            result = (response.choices[0].message.content or "").strip()

            if not result:
                raise AIServiceError(f"Empty response received from {self.name}")

            logger.info(f"{self.name} response generated: {len(result)} chars")
            return result

        except AIServiceError:
            raise
        except Exception as e:
            logger.error(f"{self.name} API error: {e}")
            raise AIServiceError(
                f"{self.name} error: {str(e)}",
                {"provider": self.name, "error_type": type(e).__name__},
            ) from e

    async def _perform_health_check(self) -> bool:
        """Check if Ollama instance is accessible.

        Returns:
            True if provider is available, False otherwise
        """
        try:
            client = self._get_http_client()
            response = await client.get(f"{self._base_url}/api/tags")
            self._available = response.status_code == 200
        except Exception as e:
            logger.debug(f"{self.name} health check failed: {e}")
            self._available = False
        return self._available

    async def close(self) -> None:
        """Close the shared httpx client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
