"""Abstract base class for all AI providers."""

import time
from abc import ABC, abstractmethod


class BaseAIProvider(ABC):
    """Abstract base class for all AI providers.

    All AI providers must implement these methods to ensure
    consistent integration with the orchestrator.
    """

    # Provider identifiers
    name: str
    model: str
    priority: int

    # Health check cache — avoid hammering providers on every summarize call
    _HEALTH_TTL: float = 30.0  # seconds

    def __init__(self) -> None:
        """Initialize the AI provider."""
        self._client = None
        self._health_cached: bool | None = None
        self._health_ts: float = 0.0

    @abstractmethod
    async def summarize(self, text: str, context: str | None = None) -> str:
        """Generate a summary for the given text.

        Args:
            text: Text to summarize
            context: Optional context (book title, chapter info, etc.)

        Returns:
            Generated summary text

        Raises:
            AIServiceError: If summarization fails
        """
        pass

    @abstractmethod
    async def _perform_health_check(self) -> bool:
        """Perform the actual health check against the provider.

        Subclasses implement this — the public ``health_check`` method
        handles caching.

        Returns:
            True if provider is available, False otherwise
        """
        pass

    async def health_check(self) -> bool:
        """Check if the AI provider is available and healthy.

        Results are cached for ``_HEALTH_TTL`` seconds to avoid
        making a network request on every summarization attempt.

        Returns:
            True if provider is available, False otherwise
        """
        now = time.time()
        if self._health_cached is not None and (now - self._health_ts) < self._HEALTH_TTL:
            return self._health_cached
        result = await self._perform_health_check()
        self._health_cached = result
        self._health_ts = now
        return result

    def _build_prompt(self, text: str, context: str | None = None) -> str:
        """Build the prompt for AI summarization.

        Args:
            text: Text to summarize
            context: Optional context

        Returns:
            Formatted prompt string
        """
        context_section = ""
        if context:
            context_section = f"\n\nContext: {context}"

        prompt = f"""You are an expert literary analyst. Summarize the following book chapter into 3-5 concise bullet points that capture the key plot developments, character actions, and important themes.{context_section}

Chapter Text:
{text[:15000]}

Provide a clear, well-structured summary that helps readers understand the chapter's main points without reading the full text."""
        return prompt

    async def close(self) -> None:  # noqa: B027 - optional override hook
        """Close any open connections or resources.

        This method should be called when shutting down the provider.
        Providers without persistent resources may leave this as a no-op.
        """
        pass
