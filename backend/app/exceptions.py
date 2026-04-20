"""Custom exception classes for domain-specific errors."""


class DawnstarError(Exception):
    """Base exception for all Dawnstar-specific errors.

    Attributes:
        message: Human-readable error message
        details: Additional context for debugging
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        """Initialize exception with message and optional details.

        Args:
            message: Human-readable error message
            details: Additional context for debugging
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation."""
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message


class DatabaseError(DawnstarError):
    """Raised when database operations fail."""
    pass


class LibraryScannerError(DawnstarError):
    """Raised when library scanning operations fail."""
    pass


class EbookParsingError(DawnstarError):
    """Raised when EPUB/PDF/MOBI parsing operations fail."""
    pass


class AIServiceError(DawnstarError):
    """Raised when AI summarization service fails."""
    pass


class ValidationError(DawnstarError):
    """Raised when input validation fails."""
    pass


class ResourceNotFoundError(DawnstarError):
    """Raised when a requested resource doesn't exist."""
    pass


class RateLimitError(DawnstarError):
    """Raised when rate limits are exceeded."""
    pass
