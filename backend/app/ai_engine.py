"""Multi-provider AI orchestration with automatic fallback."""

from typing import Optional

from app.ai_providers import (
    BaseAIProvider,
    GoogleProvider,
    GroqProvider,
    OllamaCloudProvider,
    OllamaLocalProvider,
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
        self.current_provider: Optional[str] = None
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize all AI providers in priority order."""
        # Primary: Google Gemini (Fastest, highest quality)
        if self.config.google_api_key:
            self.providers.append(GoogleProvider())

        # Secondary: Groq (Very fast, good quality)
        if self.config.groq_api_key:
            self.providers.append(GroqProvider())

        # Tertiary: Ollama Cloud (Good quality, moderate speed)
        self.providers.append(OllamaCloudProvider())

        # Fallback: Ollama Local (Offline capable, no cost)
        self.providers.append(OllamaLocalProvider())

        logger.info(f"Initialized {len(self.providers)} AI providers")

    async def summarize(
        self,
        text: str,
        context: Optional[str] = None
    ) -> str:
        """Generate summary with automatic fallback.

        Args:
            text: Text to summarize
            context: Optional context (book title, chapter info, etc.)

        Returns:
            Generated summary text

        Raises:
            AIServiceError: If all providers fail
        """
        # Strip HTML tags for clean text summarization
        if '<' in text and '>' in text:
            from bs4 import BeautifulSoup
            text = BeautifulSoup(text, 'html.parser').get_text(separator='\n', strip=True)

        if len(text) < 100:
            return "(Chapter too short to summarize)"

        last_error = None

        for provider in self.providers:
            try:
                # Check provider health first
                if not await provider.health_check():
                    logger.debug(f"{provider.name} not available, skipping...")
                    continue

                # Attempt generation
                logger.info(f"Attempting summarization with {provider.name}")
                result = await provider.summarize(text, context)
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
                "last_error": str(last_error) if last_error else None
            }
        )

    async def get_provider_status(self) -> list[dict]:
        """Get status of all AI providers.

        Returns:
            List of provider status dictionaries
        """
        status_list = []

        for provider in self.providers:
            try:
                is_healthy = await provider.health_check()
                status_list.append({
                    "name": provider.name,
                    "model": provider.model,
                    "priority": provider.priority,
                    "available": is_healthy,
                    "is_current": provider.name == self.current_provider
                })
            except Exception as e:
                status_list.append({
                    "name": provider.name,
                    "model": provider.model,
                    "priority": provider.priority,
                    "available": False,
                    "is_current": False,
                    "error": str(e)
                })

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
            "providers": {}
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
_orchestrator: Optional[AIProviderOrchestrator] = None


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


class RateLimiter:
    """Simple rate limiter for API calls.

    Ensures we don't exceed rate limits for API providers.
    """

    def __init__(self, max_calls: int, period_seconds: int = 60) -> None:
        """Initialize rate limiter.

        Args:
            max_calls: Maximum calls allowed in period
            period_seconds: Time period in seconds
        """
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.calls: list[float] = []

    async def acquire(self, provider_name: str) -> None:
        """Acquire permission to make a call.

        Args:
            provider_name: Name of the provider for logging

        Raises:
            RateLimitError: If rate limit exceeded
        """
        import time

        now = time.time()

        # Remove old calls outside the period
        self.calls = [call_time for call_time in self.calls if now - call_time < self.period_seconds]

        if len(self.calls) >= self.max_calls:
            from app.exceptions import RateLimitError
            raise RateLimitError(
                f"Rate limit exceeded for {provider_name}: {self.max_calls} calls per {self.period_seconds}s",
                {"provider": provider_name, "calls": len(self.calls)}
            )

        self.calls.append(now)
        logger.debug(f"Rate limiter: {len(self.calls)}/{self.max_calls} calls for {provider_name}")
