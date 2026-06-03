"""Custom exception classes for domain-specific errors."""


class DawnstarError(Exception):
    """Base exception for all Dawnstar-specific errors.

    Attributes:
        message: Human-readable error message
        details: Additional context for debugging
        error_code: Machine-readable error code
    """

    error_code: str = "UNKNOWN_ERROR"

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
    error_code = "DATABASE_ERROR"


class LibraryScannerError(DawnstarError):
    """Raised when library scanning operations fail."""
    error_code = "LIBRARY_SCAN_ERROR"


class EbookParsingError(DawnstarError):
    """Raised when EPUB/PDF/MOBI parsing operations fail."""
    error_code = "EBOOK_PARSING_ERROR"


class AIServiceError(DawnstarError):
    """Raised when AI summarization service fails."""
    error_code = "AI_SERVICE_ERROR"


class ValidationError(DawnstarError):
    """Raised when input validation fails."""
    error_code = "VALIDATION_ERROR"


class ResourceNotFoundError(DawnstarError):
    """Raised when a requested resource doesn't exist."""
    error_code = "RESOURCE_NOT_FOUND"


class RateLimitError(DawnstarError):
    """Raised when rate limits are exceeded."""
    error_code = "RATE_LIMIT_EXCEEDED"
