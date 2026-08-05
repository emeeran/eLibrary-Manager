"""Multi-provider AI orchestration with automatic fallback."""

import asyncio

from app.ai_providers import (
    BaseAIProvider,
    GoogleProvider,
    OllamaProvider,
)
from app.config import get_config
from app.exceptions import AIServiceError
from app.logging_config import get_logger

logger = get_logger(__name__)


class AIProviderOrchestrator:
    """Manages multiple AI providers with automatic fallback.

    This class provides a unified interface to AI summarization,
    automatically falling back through providers in priority order:
    Google → Groq → Ollama Cloud → Ollama Local.
    """

    def __init__(self) -> None:
        """Initialize orchestrator with all providers."""
        self.config = get_config()
        self.providers: list[BaseAIProvider] = []
        self.current_provider: str | None = None
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize all AI providers in priority order."""
        # Primary: Google Gemini (Fastest, highest quality)
        if self.config.google_api_key:
            self.providers.append(GoogleProvider())

        # Secondary: Ollama Cloud (Good quality, moderate speed)
        self.providers.append(
            OllamaProvider(
                name="ollama_cloud",
                base_url=self.config.ollama_cloud_url,
                model=self.config.ollama_cloud_model,
                priority=3,
                health_timeout=5.0,
            )
        )

        # Fallback: Ollama Local (Offline capable, no cost)
        self.providers.append(
            OllamaProvider(
                name="ollama_local",
                base_url=self.config.ollama_local_url,
                model=self.config.ollama_local_model,
                priority=4,
                health_timeout=2.0,
            )
        )

        logger.info(f"Initialized {len(self.providers)} AI providers")

    async def summarize(self, text: str, context: str | None = None) -> str:
        """Generate summary with automatic fallback.

        Args:
            text: Text to summarize
            context: Optional context (book title, chapter info, etc.)

        Returns:
            Generated summary text

        Raises:
            AIServiceError: If all providers fail
        """
        # Strip HTML tags for clean text summarization. Run off the event loop —
        # BeautifulSoup parsing of a long chapter is pure CPU work.
        if "<" in text and ">" in text:
            text = await asyncio.to_thread(self._strip_html, text)

        if len(text) < 100:
            return "(Chapter too short to summarize)"

        last_error = None

        for provider in self.providers:
            try:
                # Check provider health first
                if not await provider.health_check():
                    logger.debug(f"{provider.name} not available, skipping...")
                    continue

                # Attempt generation (with bounded retry on transient failures)
                logger.info(f"Attempting summarization with {provider.name}")
                result = await self._summarize_with_retry(provider, text, context)
                self.current_provider = provider.name

                logger.info(f"Summary generated using {provider.name}")
                return result

            except AIServiceError as e:
                last_error = e
                logger.warning(f"{provider.name} failed: {e}")
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"{provider.name} failed unexpectedly: {e}")
                continue

        # All providers failed
        error_msg = "All AI providers failed"
        if last_error:
            error_msg += f" - Last error: {str(last_error)}"

        logger.error(error_msg)
        raise AIServiceError(
            error_msg,
            {
                "providers_count": len(self.providers),
                "last_error": str(last_error) if last_error else None,
            },
        )

    @staticmethod
    def _strip_html(text: str) -> str:
        """Strip HTML to plain text (run via ``asyncio.to_thread``)."""
        from bs4 import BeautifulSoup

        return BeautifulSoup(text, "html.parser").get_text(separator="\n", strip=True)

    async def _summarize_with_retry(
        self, provider: BaseAIProvider, text: str, context: str | None
    ) -> str:
        """Call ``provider.summarize`` with bounded retry + exponential backoff.

        Retries only on :class:`AIServiceError` (transient provider failures such
        as timeouts, 429s, 5xx). Other exceptions propagate immediately — they
        signal unexpected bugs and should not be retried. On exhaustion the last
        ``AIServiceError`` is re-raised so the caller's fallback loop moves on.
        """
        max_retries = max(0, self.config.ai_max_retries)
        last_exc: AIServiceError | None = None
        for attempt in range(max_retries + 1):
            try:
                return await provider.summarize(text, context)
            except AIServiceError as exc:
                last_exc = exc
                if attempt >= max_retries:
                    break
                delay = 0.5 * (3**attempt)  # 0.5s, 1.5s, 4.5s, ...
                logger.warning(
                    f"{provider.name} transient failure "
                    f"(attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {delay:.1f}s: {exc}"
                )
                await asyncio.sleep(delay)
        assert last_exc is not None  # loop runs at least once
        raise last_exc

    async def get_provider_status(self) -> list[dict]:
        """Get status of all AI providers.

        Returns:
            List of provider status dictionaries
        """
        status_list = []

        for provider in self.providers:
            try:
                is_healthy = await provider.health_check()
                status_list.append(
                    {
                        "name": provider.name,
                        "model": provider.model,
                        "priority": provider.priority,
                        "available": is_healthy,
                        "is_current": provider.name == self.current_provider,
                    }
                )
            except Exception as e:
                status_list.append(
                    {
                        "name": provider.name,
                        "model": provider.model,
                        "priority": provider.priority,
                        "available": False,
                        "is_current": False,
                        "error": str(e),
                    }
                )

        return status_list

    async def get_active_provider(self) -> str:
        """Get the currently active provider name.

        Returns:
            Name of the active provider or 'none'
        """
        return self.current_provider or "none"

    async def generate_summary(
        self,
        book_id: int,
        chapter_index: int,
        content: str,
    ) -> str:
        """Generate a summary for testing AI connection.

        Convenience method used by settings test endpoint.

        Args:
            book_id: Book ID (unused, for interface compat)
            chapter_index: Chapter index (unused, for interface compat)
            content: Text content to summarize

        Returns:
            Generated summary text
        """
        return await self.summarize(content)

    async def health_check(self) -> dict:
        """Perform health check on all providers.

        Returns:
            Dictionary with provider health status
        """
        health_status = {
            "total_providers": len(self.providers),
            "healthy_providers": 0,
            "providers": {},
        }

        for provider in self.providers:
            is_healthy = await provider.health_check()
            health_status["providers"][provider.name] = is_healthy

            if is_healthy:
                health_status["healthy_providers"] += 1

        return health_status

    async def close(self) -> None:
        """Close all provider connections."""
        for provider in self.providers:
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing {provider.name}: {e}")


# Global orchestrator instance
_orchestrator: AIProviderOrchestrator | None = None


async def get_ai_orchestrator() -> AIProviderOrchestrator:
    """Get or create the global AI orchestrator instance.

    Returns:
        AIProviderOrchestrator instance

    Example:
        >>> orchestrator = await get_ai_orchestrator()
        >>> summary = await orchestrator.summarize(chapter_text)
    """
    global _orchestrator

    if _orchestrator is None:
        _orchestrator = AIProviderOrchestrator()

    return _orchestrator


def reset_ai_orchestrator() -> None:
    """Reset the global orchestrator so it is recreated on next access.

    Called when AI credentials change (API key, provider) so the
    next request picks up new configuration.
    """
    global _orchestrator
    _orchestrator = None
