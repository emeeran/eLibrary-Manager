"""Abstract base class for all AI providers."""

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class AISummaryRequest(BaseModel):
    """Request model for AI summarization."""

    text: str
    context: Optional[str] = None
    max_length: int = 500


class BaseAIProvider(ABC):
    """Abstract base class for all AI providers.

    All AI providers must implement these methods to ensure
    consistent integration with the orchestrator.
    """

    # Provider identifiers
    name: str
    model: str
    priority: int

    def __init__(self) -> None:
        """Initialize the AI provider."""
        self._client = None

    @abstractmethod
    async def summarize(self, text: str, context: Optional[str] = None) -> str:
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
    async def health_check(self) -> bool:
        """Check if the AI provider is available and healthy.

        Returns:
            True if provider is available, False otherwise
        """
        pass

    def _build_prompt(self, text: str, context: Optional[str] = None) -> str:
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

    async def close(self) -> None:
        """Close any open connections or resources.

        This method should be called when shutting down the provider.
        """
        pass
