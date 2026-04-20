# SPEC-003: AI Summarization

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-04-15

## Purpose

Provides AI-generated summaries for individual book chapters and complete books. Uses a multi-provider orchestrator with automatic fallback across four AI backends (Google Gemini, Groq, Ollama Cloud, Ollama Local) to maximize availability. Summaries are cached in the database and served from cache on subsequent requests unless the client explicitly forces a refresh. A rate limiter prevents exceeding per-provider API quotas.

---

## Behavior

### AC-003.01: Generate Chapter Summary

**Given** a book with `id={book_id}` exists in the database
**And** the chapter at `{chapter_index}` has text content of at least 100 characters
**When** the client sends `GET /api/books/{book_id}/summary/{chapter_index}`
**Then** the system extracts the full chapter text (truncated to 15,000 characters)
**And** sends the text to the active AI provider with context `Book: {title} by {author}`
**And** persists the result as a `ChapterSummary` row (book_id, chapter_index, chapter_title, summary_text, provider)
**And** returns HTTP 200 with body `{ summary, provider, created_at }`

### AC-003.02: Reject Short Text

**Given** a chapter's extracted text content is fewer than 100 characters
**When** the orchestrator's `summarize()` method is called with that text
**Then** the system raises `AIServiceError` with message "Text too short to summarize" and detail `{ length: <actual_length> }`
**And** no AI provider is invoked

### AC-003.03: Serve Cached Chapter Summary

**Given** a `ChapterSummary` row already exists for `(book_id, chapter_index)` in the `chapter_summaries` table
**When** the client sends `GET /api/books/{book_id}/summary/{chapter_index}` without `?refresh=true`
**Then** the system returns the cached summary immediately without calling any AI provider
**And** returns HTTP 200 with the cached `{ summary, provider, created_at }`

### AC-003.04: Force Chapter Summary Refresh

**Given** a cached `ChapterSummary` exists for `(book_id, chapter_index)`
**When** the client sends `GET /api/books/{book_id}/summary/{chapter_index}?refresh=true`
**Then** the system ignores the cached entry
**And** re-extracts chapter text and generates a new summary via the active AI provider
**And** creates a new `ChapterSummary` row in the database
**And** returns HTTP 200 with the new `{ summary, provider, created_at }`

### AC-003.05: Generate Full Book Summary

**Given** a book with `id={book_id}` exists in the database
**When** the client sends `GET /api/books/{book_id}/summary`
**Then** the system iterates over all chapters in the book
**And** for each chapter: retrieves the cached chapter summary if present, otherwise generates one via AI and persists it as a `ChapterSummary`
**And** concatenates all chapter summaries with headers (`Chapter {n}: {summary}`)
**And** sends the combined text to the AI orchestrator with context `Book: {title} by {author}`
**And** persists the result as a `BookSummary` row (book_id UNIQUE, summary_text, provider)
**And** returns HTTP 200 with `{ summary, provider, created_at }`

### AC-003.06: Serve Cached Book Summary

**Given** a `BookSummary` row already exists for `book_id` in the `book_summaries` table
**When** the client sends `GET /api/books/{book_id}/summary` without `?refresh=true`
**Then** the system returns the cached book summary immediately without calling any AI provider
**And** returns HTTP 200 with the cached `{ summary, provider, created_at }`

### AC-003.07: Force Book Summary Refresh

**Given** a cached `BookSummary` exists for `book_id`
**When** the client sends `GET /api/books/{book_id}/summary?refresh=true`
**Then** the system ignores the cached book summary
**And** re-generates all chapter summaries (using cached chapter summaries where available)
**And** generates a new combined book summary via AI
**And** upserts the `BookSummary` row (via `create_or_update`)
**And** returns HTTP 200 with the new `{ summary, provider, created_at }`

### AC-003.08: Provider Fallback Chain

**Given** the orchestrator is initialized with the provider priority order: Google (1) -> Groq (2) -> Ollama Cloud (3) -> Ollama Local (4)
**When** the orchestrator's `summarize()` method is called
**Then** the system iterates providers in priority order
**And** for each provider: performs a health check first; if unhealthy, skips to the next provider
**And** if the provider is healthy, sends the summarization request
**And** on success: updates `current_provider` to the provider name and returns the summary
**And** on failure: logs the error and continues to the next provider
**And** if all providers fail: raises `AIServiceError` with message "All AI providers failed - Last error: {last_error}" and details `{ providers_count, last_error }`

### AC-003.09: Provider Initialization with API Keys

**Given** the application configuration (`AppConfig`) is loaded
**When** the `AIProviderOrchestrator` is instantiated
**Then** Google provider is included only if `google_api_key` is non-empty
**And** Groq provider is included only if `groq_api_key` is non-empty
**And** Ollama Cloud provider is always included (no API key required)
**And** Ollama Local provider is always included (no API key required)
**And** providers are ordered by priority: Google (1), Groq (2), Ollama Cloud (3), Ollama Local (4)

### AC-003.10: Google Gemini Provider

**Given** `google_api_key` is configured
**When** `GoogleProvider.summarize()` is called
**Then** the system builds a prompt via `_build_prompt()` and sends it to the Google Gemini API
**And** uses model from config (default: `gemini-1.5-flash`)
**And** uses `max_output_tokens=500` and `temperature=0.7`
**And** returns the stripped response text
**And** if the response text is empty, raises `AIServiceError("Empty summary received from Google Gemini")`

### AC-003.11: Groq Provider

**Given** `groq_api_key` is configured
**When** `GroqProvider.summarize()` is called
**Then** the system builds a prompt via `_build_prompt()` and sends it to the Groq chat completions API
**And** uses model `llama-3.3-70b-versatile`
**And** uses `max_tokens=500` and `temperature=0.7`
**And** returns `response.choices[0].message.content.strip()`
**And** if the response text is empty, raises `AIServiceError("Empty summary received from Groq")`

### AC-003.12: Ollama Cloud Provider

**Given** the Ollama Cloud URL is configured (default: `https://api.ollama.ai`)
**When** `OllamaCloudProvider.summarize()` is called
**Then** the system creates an `AsyncOpenAI` client with `base_url={cloud_url}/v1` and `api_key="ollama"`
**And** sends the prompt via chat completions with model `llama3.3`, `max_tokens=500`, `temperature=0.7`
**And** returns the stripped response text
**And** if the response text is empty, raises `AIServiceError("Empty summary received from Ollama Cloud")`

### AC-003.13: Ollama Local Provider

**Given** Ollama is running locally at the configured URL (default: `http://localhost:11434`)
**When** `OllamaLocalProvider.summarize()` is called
**Then** the system creates an `AsyncOpenAI` client with `base_url={local_url}/v1` and `api_key="ollama"`
**And** sends the prompt via chat completions with model `llama3.3`, `max_tokens=500`, `temperature=0.7`
**And** returns the stripped response text
**And** if the response text is empty, raises `AIServiceError("Empty summary received from local Ollama")`

### AC-003.14: Provider Health Check

**Given** a provider is initialized
**When** `health_check()` is called on a provider:
- **Google:** sends a minimal generate_content request (`max_output_tokens=1`); returns `True` if response has text, `False` on exception
- **Groq:** sends a minimal chat completion request (`max_tokens=1`); returns `True` if response has content, `False` on exception
- **Ollama Cloud:** sends HTTP GET to `{base_url}/api/tags` with 5s timeout; returns `True` if status 200
- **Ollama Local:** sends HTTP GET to `{base_url}/api/tags` with 2s timeout; returns `True` if status 200

**And** if a provider's `_available` flag is `False` (e.g., missing API key), health check returns `False` immediately without network calls

### AC-003.15: List All Providers with Status

**Given** the orchestrator is initialized
**When** the client sends `GET /api/ai/providers`
**Then** the system returns HTTP 200 with:
```json
{
  "providers": [
    {
      "name": "google",
      "model": "gemini-1.5-flash",
      "priority": 1,
      "available": true,
      "is_current": true
    }
  ],
  "active_provider": "google",
  "default_provider": "auto"
}
```
**And** each provider entry includes `name`, `model`, `priority`, `available` (health check result), and `is_current`
**And** `default_provider` comes from `config.ai_default_provider`

### AC-003.16: Get Active Provider

**Given** the orchestrator has or has not been used yet
**When** the client sends `GET /api/ai/providers/active`
**Then** the system returns HTTP 200 with `{ "active_provider": "<provider_name>" }`
**And** if no summarization has been performed yet, `active_provider` is `"none"`

### AC-003.17: Switch Active Provider

**Given** the target provider exists in the orchestrator's provider list
**And** the target provider passes its health check
**When** the client sends `POST /api/ai/providers/switch` with body `provider_name` (string)
**Then** the system removes the target provider from its current position in the list
**And** inserts it at position 0 (highest priority)
**And** returns HTTP 200 with `{ "active_provider": "<provider_name>", "provider_order": ["<name>", ...] }`

### AC-003.18: Switch to Invalid Provider

**Given** the target provider name does not match any provider in the orchestrator's list
**When** the client sends `POST /api/ai/providers/switch` with an unknown `provider_name`
**Then** the system raises `ValueError` with message `"Provider '{name}' not found. Available: [...]"`
**And** returns HTTP 500 (unhandled ValueError) or the application error handler converts it

### AC-003.19: Switch to Unhealthy Provider

**Given** the target provider exists but fails its health check
**When** the client sends `POST /api/ai/providers/switch` with that provider's name
**Then** the system raises `ValueError` with message `"Provider '{name}' is not available"`
**And** the provider order is not modified

### AC-003.20: Rate Limiting

**Given** a `RateLimiter` is configured with `max_calls` and `period_seconds`
**When** `acquire()` is called
**Then** the system removes all call timestamps older than `period_seconds` from the internal list
**And** if the remaining count is at or above `max_calls`, raises `RateLimitError` with details `{ provider, calls }`
**And** if under the limit, appends the current timestamp and allows the call

### AC-003.21: Input Text Truncation

**Given** chapter text exceeds 15,000 characters
**When** the prompt is built via `BaseAIProvider._build_prompt()`
**Then** the text is truncated to the first 15,000 characters before being included in the prompt
**And** the prompt instructs the AI: "You are an expert literary analyst. Summarize the following book chapter into 3-5 concise bullet points..."

### AC-003.22: Prompt Template with Context

**Given** the `context` parameter is provided (e.g., `"Book: The Great Gatsby by F. Scott Fitzgerald"`)
**When** `_build_prompt()` is called
**Then** the prompt includes a "Context:" section with the provided context string
**And** the full prompt structure is:
```
You are an expert literary analyst. Summarize the following book chapter into 3-5 concise bullet points that capture the key plot developments, character actions, and important themes.

Context: {context}

Chapter Text:
{text[:15000]}

Provide a clear, well-structured summary that helps readers understand the chapter's main points without reading the full text.
```

### AC-003.23: Prompt Template Without Context

**Given** the `context` parameter is `None`
**When** `_build_prompt()` is called
**Then** the prompt omits the "Context:" section entirely
**And** the prompt contains only the system instruction, chapter text, and closing instruction

### AC-003.24: Summary for Non-existent Book

**Given** no book with `id={book_id}` exists in the database
**When** the client sends `GET /api/books/{book_id}/summary/{chapter_index}`
**Then** the system raises `ResourceNotFoundError`
**And** returns HTTP 404

### AC-003.25: Summary for Non-existent Chapter

**Given** a book exists but `{chapter_index}` is greater than or equal to the total number of chapters
**When** the system attempts to generate a summary
**Then** the system raises `ResourceNotFoundError` with message `"Chapter {chapter_index} not found"` and details `{ book_id, chapter_index }`
**And** returns HTTP 404

### AC-003.26: Provider Cleanup on Shutdown

**Given** the orchestrator has one or more initialized providers
**When** `close()` is called on the orchestrator
**Then** the system calls `close()` on each provider in sequence
**And** each provider cleans up its client resources (Google sets `_client = None`; Groq, Ollama Cloud, Ollama Local are no-ops)
**And** errors during close are logged as warnings but do not halt the shutdown of remaining providers

### AC-003.27: Book Summary Uses Cached Chapter Summaries

**Given** individual chapter summaries already exist in the `chapter_summaries` table for a book
**When** the system generates a full book summary (AC-003.05)
**Then** for each chapter that has a cached summary, the system uses the cached `summary_text` instead of calling the AI provider
**And** for each chapter without a cached summary, the system generates a new summary via AI and persists it
**And** the book summary is generated from the concatenation of all chapter summaries

### AC-003.28: Global Orchestrator Singleton

**Given** no `AIProviderOrchestrator` instance has been created in the current process
**When** `get_ai_orchestrator()` is called
**Then** a new `AIProviderOrchestrator` instance is created and stored in the module-level `_orchestrator` variable
**And** subsequent calls to `get_ai_orchestrator()` return the same instance

---

## API Contract

### Endpoints

| Method | Path | Query Params | Request Body | Success Response | Error Responses | Purpose |
|--------|------|-------------|--------------|-----------------|----------------|---------|
| GET | `/api/books/{book_id}/summary/{chapter_index}` | `refresh` (bool, default false) | - | `200 { summary, provider, created_at }` | `404` book/chapter not found, `500` AI service error | Get or generate chapter summary |
| GET | `/api/books/{book_id}/summary` | `refresh` (bool, default false) | - | `200 { summary, provider, created_at }` | `404` book not found, `500` AI service error | Get or generate full book summary |
| GET | `/api/ai/providers` | - | - | `200 { providers[], active_provider, default_provider }` | - | List all providers with health status |
| GET | `/api/ai/providers/active` | - | - | `200 { active_provider }` | - | Get currently active provider name |
| POST | `/api/ai/providers/switch` | - | `provider_name` (string) | `200 { active_provider, provider_order[] }` | `500` provider not found or unhealthy | Switch active provider |

### Data Models

#### ChapterSummary (database table: `chapter_summaries`)

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | INTEGER | PK, AUTO | Primary key |
| book_id | INTEGER | FK(books.id) CASCADE, NOT NULL, INDEX | Parent book |
| chapter_index | INTEGER | NOT NULL | Zero-based chapter index |
| chapter_title | VARCHAR(500) | NULLABLE | Chapter title from TOC |
| summary_text | TEXT | NOT NULL | Generated summary content |
| provider | VARCHAR(50) | NOT NULL, DEFAULT "google", INDEX | AI provider that generated this summary |
| created_at | DATETIME | NOT NULL, DEFAULT utcnow | Generation timestamp |

#### BookSummary (database table: `book_summaries`)

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| id | INTEGER | PK, AUTO | Primary key |
| book_id | INTEGER | FK(books.id) CASCADE, NOT NULL, UNIQUE | Parent book (one summary per book) |
| summary_text | TEXT | NOT NULL | Generated book summary |
| provider | VARCHAR(50) | NOT NULL, DEFAULT "google" | AI provider used |
| created_at | DATETIME | NOT NULL, DEFAULT utcnow | Generation timestamp |

### Pydantic Schemas

```python
class ChapterSummaryResponse(BaseModel):
    id: int
    book_id: int
    chapter_index: int              # ge=0
    chapter_title: Optional[str]    # max_length=500
    summary_text: str               # min_length=1
    provider: str
    created_at: datetime

class BookSummaryResponse(BaseModel):
    id: int
    book_id: int
    summary_text: str
    provider: str
    created_at: datetime

class AIProviderStatus(BaseModel):
    name: str
    available: bool
    model: str
    priority: int

class AIProvidersResponse(BaseModel):
    providers: list[AIProviderStatus]
    active_provider: str
    default_provider: str

class AISummaryRequest(BaseModel):  # Internal, not exposed via API
    text: str
    context: Optional[str] = None
    max_length: int = 500
```

### Provider Configuration

| Provider | Config Key | Default | Priority | Model |
|----------|-----------|---------|----------|-------|
| Google Gemini | `google_api_key`, `google_model` | `gemini-1.5-flash` | 1 | From `google_model` config |
| Groq | `groq_api_key`, `groq_model` | `llama-3.3-70b-versatile` | 2 | From `groq_model` config |
| Ollama Cloud | `ollama_cloud_url`, `ollama_cloud_model` | `https://api.ollama.ai`, `llama3.3` | 3 | From `ollama_cloud_model` config |
| Ollama Local | `ollama_local_url`, `ollama_local_model` | `http://localhost:11434`, `llama3.3` | 4 | From `ollama_local_model` config |

---

## Implementation Map

| Component | File | Key Functions/Classes |
|-----------|------|----------------------|
| Orchestrator | `app/ai_engine.py` | `AIProviderOrchestrator`, `get_ai_orchestrator()`, `RateLimiter` |
| Base Provider | `app/ai_providers/base.py` | `BaseAIProvider`, `AISummaryRequest`, `_build_prompt()` |
| Google Provider | `app/ai_providers/google_provider.py` | `GoogleProvider` |
| Groq Provider | `app/ai_providers/groq_provider.py` | `GroqProvider` |
| Ollama Providers | `app/ai_providers/ollama_provider.py` | `OllamaCloudProvider`, `OllamaLocalProvider` |
| Provider Exports | `app/ai_providers/__init__.py` | Re-exports all provider classes |
| Summary Routes | `app/routes/reader.py` | `get_summary()`, `get_book_summary()` |
| Provider Management Routes | `app/routes/ai_tts.py` | `list_ai_providers()`, `get_active_provider()`, `switch_ai_provider()` |
| Reader Service | `app/services/reader_service.py` | `get_chapter_summary()`, `get_book_summary()`, `get_ai_providers_status()`, `get_active_ai_provider()`, `switch_ai_provider()` |
| Chapter Summary Repo | `app/repositories.py` | `ChapterSummaryRepository.get_cached_summary()`, `ChapterSummaryRepository.create()` |
| Book Summary Repo | `app/repositories.py` | `BookSummaryRepository.get_by_book()`, `BookSummaryRepository.create_or_update()` |
| DB Models | `app/models.py` | `ChapterSummary`, `BookSummary` |
| Pydantic Schemas | `app/schemas.py` | `ChapterSummaryResponse`, `BookSummaryResponse`, `AIProviderStatus`, `AIProvidersResponse` |
| Configuration | `app/config.py` | `AppConfig` (AI-related fields) |
| Exceptions | `app/exceptions.py` | `AIServiceError`, `RateLimitError`, `ResourceNotFoundError` |

---

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|------------------|-----------|---------------|--------|
| AC-003.15: List providers endpoint | `tests/test_api.py` | `test_ai_providers_endpoint` | Covered |
| AC-003.16: Get active provider endpoint | `tests/test_api.py` | `test_ai_provider_active_endpoint` | Covered |
| AC-003.01: Generate chapter summary | - | - | GAP |
| AC-003.02: Reject short text | - | - | GAP |
| AC-003.03: Serve cached chapter summary | - | - | GAP |
| AC-003.04: Force chapter summary refresh | - | - | GAP |
| AC-003.05: Generate full book summary | - | - | GAP |
| AC-003.06: Serve cached book summary | - | - | GAP |
| AC-003.07: Force book summary refresh | - | - | GAP |
| AC-003.08: Provider fallback chain | - | - | GAP |
| AC-003.09: Provider initialization with API keys | - | - | GAP |
| AC-003.10: Google Gemini provider | - | - | GAP |
| AC-003.11: Groq provider | - | - | GAP |
| AC-003.12: Ollama Cloud provider | - | - | GAP |
| AC-003.13: Ollama Local provider | - | - | GAP |
| AC-003.14: Provider health check | - | - | GAP |
| AC-003.17: Switch active provider | - | - | GAP |
| AC-003.18: Switch to invalid provider | - | - | GAP |
| AC-003.19: Switch to unhealthy provider | - | - | GAP |
| AC-003.20: Rate limiting | - | - | GAP |
| AC-003.21: Input text truncation | - | - | GAP |
| AC-003.22: Prompt with context | - | - | GAP |
| AC-003.23: Prompt without context | - | - | GAP |
| AC-003.24: Summary for non-existent book | - | - | GAP |
| AC-003.25: Summary for non-existent chapter | - | - | GAP |
| AC-003.26: Provider cleanup on shutdown | - | - | GAP |
| AC-003.27: Book summary uses cached chapter summaries | - | - | GAP |
| AC-003.28: Global orchestrator singleton | - | - | GAP |

---

## Dependencies

- **SPEC-002: Reader Interface** -- chapter content extraction (`get_chapter_content`, `get_all_chapters`) and table of contents (`get_table_of_contents`) are required to supply text to the AI engine
- **SPEC-007: Settings** -- AI provider configuration (`ai_provider`, `ai_api_key`, `ollama_url`) is managed through settings
- **External: `google-genai`** -- Google Gemini Python SDK for primary AI provider
- **External: `groq`** -- Groq Python SDK for secondary AI provider
- **External: `openai`** -- OpenAI-compatible client used by Ollama Cloud and Ollama Local providers
- **External: `httpx`** -- Async HTTP client used for Ollama health checks

---

## Open Questions

- None
