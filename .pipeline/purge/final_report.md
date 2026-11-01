<!-- AI Code Review Pipeline -->
<!-- Stack: fastapi + ? -->
<!-- Reports: 3/3 tools succeeded -->

# Code Review: Final Synthesis Report
## Project: eLibrary-Manager — FastAPI · Python 3.12 · SQLAlchemy · SQLite · Docker
## Date: 2026-05-02
## Reviewed by: Gemini CLI · Claude Code · Qwen Code

---

## Executive Summary

- **Credentials are committed to version control.** Real API keys (Google Gemini, Groq) and the admin password exist in `.env` inside git history. These must be revoked, rotated, and purged immediately.
- **Cryptographic keys are derived from the database URL**, not from a proper `SECRET_KEY`. This weakens password hashing, session tokens, and NAS-credential encryption across the board.
- **The application is not horizontally scalable.** An in-memory session store and thread-based rate limiter prevent multi-worker/multi-replica deployments and lose all state on container restart.
- **There is no database migration framework.** Schema changes are applied via ad-hoc `ALTER TABLE` on startup — no rollback, no version tracking, no production safety.
- **Blocking I/O runs on the async event loop** in file uploads, cover extraction, and EPUB/MOBI parsing, causing latency and timeouts under concurrent load.

**Overall assessment:** The codebase demonstrates good use of Pydantic v2, clean repository separation, and well-structured exception handlers. However, it requires significant security hardening, migration tooling, and async correctness work before it is production-ready.

---

## Critical & High Severity Issues

### CRITICAL

| # | Issue | Section | Confirmed By |
|---|---|---|---|
| C1 | Committed secrets in `.env` (API keys, admin password) | Security | 2/3 |
| C2 | Crypto key derived from `database_url`, not `SECRET_KEY` | Security | 2/3 |
| C3 | EPUB/HTML content served without sanitization (XSS) | Frontend | 2/3 |
| C4 | No database migration framework — ad-hoc `ALTER TABLE` on startup | Database | 2/3 |
| C5 | No backend tests for security paths, auth, or encryption | Testing | 2/3 |
| C6 | Dockerfile non-root user may lack write permissions on mounted volumes | DevOps | 1/3 |

### HIGH

| # | Issue | Section | Confirmed By |
|---|---|---|---|
| H1 | In-memory session store — lost on restart, prevents horizontal scaling | Architecture | 2/3 |
| H2 | Rate limiter uses `threading.Lock` in async middleware | Security | 1/3 |
| H3 | Login endpoint enables username enumeration | Security | 1/3 |
| H4 | Path traversal via unsanitized upload filenames | Security/Frontend | 2/3 |
| H5 | Synchronous file I/O blocks async event loop (uploads, cover extraction) | Async | 3/3 |
| H6 | CPU-bound EPUB/MOBI parsing on event loop | Async | 2/3 |
| H7 | SQLAlchemy `commit()` on every request including reads | Architecture | 1/3 |
| H8 | Search cache key lacks user isolation — potential data leakage | Architecture | 1/3 |
| H9 | `Book.summaries` uses `lazy="noload"` → N+1 queries | Database | 1/3 |
| H10 | Exception handlers return `exc.message`/`exc.details` to client | Error Handling | 1/3 |
| H11 | Library volume mounted `:ro` in docker-compose — cover writes will fail | DevOps | 1/3 |
| H12 | CI pipeline has no vulnerability or secret scanning | DevOps | 1/3 |

---

## Section Reviews

### 1. Security & Auth

#### 1.1 Committed secrets in `.env` | CRITICAL | `.env`
**Issue**: Real API keys and the admin password are committed to the repository.
**Impact**: Google Gemini API key (`AIzaSy...`), Groq API key (`gsk_...`), and admin password (`8DVNub7Pa7mGsZyJ`) are exposed in git history. An attacker with repo access gains unrestricted use of AI services and admin panel access.
**Evidence**: `.env:9-10,24`
**Fix**: Immediately revoke and rotate all credentials. Add `.env` to `.gitignore`. Purge from git history using BFG Repo-Cleaner or `git filter-repo`. Use CI/CD secrets or a vault in production.
[Confirmed by 2/3 reviewers]

#### 1.2 Crypto key derived from `database_url` | CRITICAL | `backend/app/security.py`
**Issue**: `_derive_key()` uses `config.database_url.encode()` as the sole secret for Fernet key derivation. The HMAC fallback also uses `database_url` when `secret_key` is unset.
**Impact**: An attacker who knows or guesses the default SQLite connection string can derive the Fernet key, decrypt NAS credentials stored in the DB, and forge password hashes.
**Evidence**: `security.py:14-18` (`_derive_key()`), `security.py:40` (HMAC fallback)
**Fix**: Require `SECRET_KEY` environment variable in production. Fail startup if absent. Generate with `secrets.token_urlsafe(32)`.
[Confirmed by 2/3 reviewers] · [Severity escalated: Gemini=MEDIUM, Qwen=CRITICAL → using CRITICAL]

#### 1.3 In-memory session store with no invalidation | HIGH | `backend/app/auth.py`
**Issue**: `_session_store: dict[str, dict] = {}` holds all sessions in process memory with no maximum count, no forced logout, and no session rotation on privilege changes.
**Impact**: Sessions lost on container restart. Horizontal scaling impossible — multiple workers/replicas cannot share sessions. Session fixation risk.
**Evidence**: `auth.py:20-27`
**Fix**: Migrate to Redis or database-backed sessions. Add session rotation, "logout all devices" support, and configurable max sessions per user.
[Confirmed by 2/3 reviewers]

#### 1.4 Rate limiter uses `threading.Lock` in async middleware | HIGH | `backend/app/middleware.py`
**Issue**: Rate-limit state stored in a plain `dict` with `threading.Lock()`, which blocks the async event loop.
**Impact**: Rate limiting is ineffective under `uvicorn` workers or multi-replica deployments, leaving expensive endpoints vulnerable to DoS.
**Evidence**: `middleware.py:25-27`
**Fix**: Use `asyncio.Lock` for single-worker or Redis for multi-worker. Alternatively, offload rate limiting to a reverse proxy (nginx) or API gateway.
[Unique: Qwen]

#### 1.5 Username enumeration via login endpoint | HIGH | `backend/app/routes/auth.py`
**Issue**: Different status codes or messages for invalid username vs. invalid password.
**Impact**: Attacker can enumerate valid usernames via timing differences or response variations.
**Evidence**: `auth.py:59-67`
**Fix**: Return identical response for all auth failures. Use `hmac.compare_digest()` for constant-time comparison during username lookup.
[Unique: Qwen]

#### 1.6 `SECRET_KEY` validation only warns | MEDIUM | `backend/app/config.py`
**Issue**: `validate_secret_key()` uses `warnings.warn()` instead of raising an exception.
**Impact**: Application runs in production with weak/missing secret key, compromising all crypto operations.
**Evidence**: `config.py:63-70`
**Fix**: Raise `ValueError` if `SECRET_KEY` is empty when `APP_ENV=production`.
[Unique: Qwen]

#### 1.7 NAS password encrypted with DB-derived key | MEDIUM | `backend/app/routes/settings.py`
**Issue**: `encrypt_value()` uses `_derive_key()` sourced from `database_url`.
**Impact**: DB access alone is sufficient to decrypt NAS credentials.
**Evidence**: `settings.py:104-107`
**Fix**: Derive encryption key from `SECRET_KEY`, not `database_url`. Better: use a dedicated secrets manager.
[Unique: Qwen]

#### 1.8 Session cookie missing `Secure` flag | LOW | `backend/app/routes/auth.py`
**Issue**: `response.set_cookie()` sets `httponly=True, samesite="lax"` but no `secure=True`.
**Impact**: Cookie transmitted over unencrypted HTTP if no TLS-terminating proxy.
**Evidence**: `auth.py:80`, `auth.py:89-95`
**Fix**: Add `secure=not config.debug`.
[Confirmed by 2/3 reviewers]

---

### 2. Architecture & API Design

#### 2.1 SQLAlchemy `commit()` on every request | HIGH | `backend/app/database.py`
**Issue**: `get_db()` always calls `await session.commit()` in the `try` block, even for read-only operations.
**Impact**: Unnecessary write transactions cause SQLite lock contention under concurrent load.
**Evidence**: `database.py:155-158`
**Fix**: Only commit for write operations. Use `session.begin()` context for writes, or mark read-only routes explicitly.
[Unique: Qwen]

#### 2.2 Search cache key lacks user isolation | HIGH | `backend/app/routes/library.py`
**Issue**: Cache key built from query params without session/user token hash.
**Impact**: Users may receive cached results from other users' filtered searches if filter params match.
**Evidence**: `library.py:389-393`
**Fix**: Include session token hash in cache key, or disable caching for authenticated user-specific queries.
[Unique: Qwen]

#### 2.3 Symlink escape in path validation | MEDIUM | `backend/app/routes/library.py`
**Issue**: `_validate_path_within_library()` uses `Path.relative_to()` which follows symlinks.
**Impact**: Attacker could import files from outside the library directory via symlink placement.
**Evidence**: `library.py:39-47`
**Fix**: Use `os.path.realpath()` or `Path.resolve()` before validation to resolve symlinks.
[Unique: Qwen]

#### 2.4 Middleware order incorrect | MEDIUM | `backend/app/main.py`
**Issue**: `AuthMiddleware` runs before `ProductionMiddleware` (rate limiting). Unauthenticated requests trigger rate-limited operations before auth check.
**Impact**: Wasted resources processing requests that will be rejected.
**Evidence**: `main.py:119-121`
**Fix**: Reorder: `ProductionMiddleware` (outermost), then `AuthMiddleware`, then `GZipMiddleware`.
[Unique: Qwen]

#### 2.5 `BookCreate` subjects list has no length limit | LOW | `backend/app/schemas.py`
**Issue**: `subjects: list[str] = Field(default_factory=list)` with no `max_length`.
**Impact**: Potential abuse storing large amounts of data in metadata.
**Evidence**: `schemas.py:24-25`
**Fix**: Add `Field(default_factory=list, max_length=20)` and validate item lengths.
[Unique: Qwen]

#### 2.6 Repository pattern well-implemented | INFO | `backend/app/repositories.py`
**Impact**: Clean separation of DB operations, easy to test and swap data sources.
[Unique: Qwen]

---

### 3. Database & ORM

#### 3.1 No migration framework | CRITICAL | `backend/app/database.py`
**Issue**: Schema changes applied via ad-hoc `ALTER TABLE` in `_migrate()`, with no version tracking or rollback.
**Impact**: Schema drift between environments, no rollback capability, production deployments are risky. Race conditions if multiple instances initialize simultaneously.
**Evidence**: `database.py:105-127`
**Fix**: Introduce Alembic. Generate migration scripts. Execute during init container or CI/CD pipeline, not during FastAPI lifespan.
[Confirmed by 2/3 reviewers] · [Severity escalated: Gemini=HIGH, Qwen=CRITICAL → using CRITICAL]

#### 3.2 `Book.summaries` uses `lazy="noload"` → N+1 queries | HIGH | `backend/app/models.py`
**Issue**: Accessing `summaries` after loading triggers one query per book.
**Evidence**: `models.py:75-78`
**Fix**: Use `lazy="selectin"` or explicitly load with `selectinload()` in queries needing summaries.
[Unique: Qwen]

#### 3.3 `list_with_count()` runs separate COUNT without transaction isolation | HIGH | `backend/app/repositories.py`
**Issue**: Separate `count_filtered()` call followed by data query outside a consistent transaction.
**Impact**: Count and results may be inconsistent under concurrent writes (phantom reads).
**Evidence**: `repositories.py:175-205`
**Fix**: Wrap both queries in a serializable transaction, or accept eventual consistency for UI display.
[Unique: Qwen]

#### 3.4 SQLite `mmap_size=256MB` exceeds Docker memory reservation | MEDIUM | `backend/app/database.py`
**Issue**: `PRAGMA mmap_size=268435456` (256MB) per connection exceeds Docker Compose `reservations: memory: 128M`. Ten pool connections × 256MB = 2.5GB potential.
**Impact**: OOM kills under load.
**Evidence**: `database.py:49`, `docker-compose.yml:25`
**Fix**: Reduce to 32MB or make configurable via environment variable.
[Confirmed by 2/3 reviewers]

#### 3.5 `BookCategory` missing individual FK indexes | MEDIUM | `backend/app/models.py`
**Issue**: Only composite index exists; individual FK columns lack indexes.
**Impact**: JOINs on `book_categories` may be slow.
**Evidence**: `models.py:354-368`
**Fix**: Add individual indexes on `book_id` and `category_id`.
[Unique: Qwen]

#### 3.6 `autoflush=False` with `expire_on_commit=False` may serve stale data | MEDIUM | `backend/app/database.py`
**Issue**: Session may return outdated data after commits.
**Evidence**: `database.py:76-81`
**Fix**: Enable `autoflush=True` or document that callers must call `session.refresh()` after commits.
[Unique: Qwen]

#### 3.7 `get_by_id_or_404()` leaks repository abstraction | LOW | `backend/app/repositories.py`
**Issue**: Repository raises `ResourceNotFoundError` — domain exceptions belong in the service layer.
**Evidence**: `repositories.py:78-91`
**Fix**: Return `None`; let service layer raise domain exceptions.
[Unique: Qwen]

#### 3.8 Good use of SQLAlchemy relationships and indexes | INFO
**Impact**: `lazy="selectin"` on `category_links` prevents N+1. Indexes on `is_hidden`, `is_favorite`, `progress` optimize common UI queries.
[Confirmed by 2/3 reviewers]

---

### 4. Async / Performance

#### 4.1 Synchronous file I/O blocks the async event loop | HIGH | Multiple files
**Issue**: `open()` + `shutil.copyfileobj()` in upload handler, cover upload, and cover extraction all run synchronously on the event loop.
**Impact**: Large file uploads and batch cover extraction stall all concurrent requests, causing timeouts.
**Evidence**: `library.py:269` (upload), `library.py:481-485` (cover upload), `library_service.py:352-362` (cover extraction)
**Fix**: Use `aiofiles`, `asyncio.to_thread()`, or `run_in_threadpool()` for all file operations:
```python
from fastapi.concurrency import run_in_threadpool
await run_in_threadpool(save_file_sync, file.file, file_path)
```
[Confirmed by 3/3 reviewers]

#### 4.2 CPU-bound EPUB/MOBI parsing on event loop | HIGH | `backend/app/parsers/epub_parser.py`
**Issue**: `epub.read_epub()` and `BeautifulSoup` parsing execute synchronously (unlike `pdf_parser.py` which correctly uses `asyncio.to_thread`).
**Impact**: Importing books severely bottlenecks the application under concurrent load.
**Evidence**: `epub_parser.py:55`
**Fix**: Wrap all blocking calls in `asyncio.to_thread()`, mirroring the pattern in `pdf_parser.py`.
[Confirmed by 2/3 reviewers]

#### 4.3 Chapter cache relies solely on `mtime` | MEDIUM | `backend/app/reader_engine.py`
**Issue**: No fallback for unreliable filesystem modification times.
**Impact**: May serve stale content.
**Evidence**: `reader_engine.py:28-30`
**Fix**: Add content hash (e.g., first 1KB) as secondary cache invalidation check.
[Unique: Qwen]

#### 4.4 Search cache has no eviction policy beyond count limit | MEDIUM | `backend/app/routes/library.py`
**Issue**: Simple dict-based cache with `max=50` entries, no TTL.
**Impact**: Memory leak potential; entries never expire.
**Evidence**: `library.py:34-36`
**Fix**: Use `functools.lru_cache` or implement TTL-based eviction.
[Unique: Qwen]

#### 4.5 `fast_index()` batch commits don't handle individual failures | MEDIUM | `backend/app/services/library_service.py`
**Issue**: Single bad book in a batch of 100 causes entire batch rollback with no partial success tracking.
**Evidence**: `library_service.py:117-123`
**Fix**: Wrap each `book_repo.create()` in try/except; track failed items; continue with remaining batch.
[Unique: Qwen]

#### 4.6 Rate limit cleanup has no background task | LOW | `backend/app/middleware.py`
**Issue**: Cleanup only during request processing; memory grows for low-traffic endpoints.
**Evidence**: `middleware.py:67-70`
**Fix**: Add background task to periodically purge expired entries.
[Unique: Qwen]

#### 4.7 Good lazy engine initialization | INFO | `backend/app/database.py`
**Impact**: Database only connected when first request needs it.
[Unique: Qwen]

---

### 5. Frontend & API Integration

#### 5.1 EPUB/HTML content served without sanitization (XSS) | CRITICAL | `backend/app/routes/reader.py`
**Issue**: Chapter endpoint returns full HTML content from parser without defense-in-depth sanitization. EPUB files can embed malicious scripts.
**Impact**: Stored XSS — malicious ebook content executes in user browsers.
**Evidence**: `reader.py:63-85`
**Fix**: Add HTML sanitization with `bleach.clean()` or equivalent before returning content, even if the parser strips scripts.
[Confirmed by 2/3 reviewers] · [Severity escalated: Qwen=MEDIUM, Claude=CRITICAL → using CRITICAL]

#### 5.2 Path traversal via unsanitized upload filename | HIGH | `backend/app/routes/library.py`
**Issue**: `filename = file.filename or "unknown"` used directly in `os.path.join()`.
**Impact**: Attacker can overwrite files outside the uploads directory (e.g., `../../../root/test.epub`).
**Evidence**: `library.py:253-275`
**Fix**: Use `secure_filename()` from Werkzeug or `os.path.basename()` to extract only the base name.
[Confirmed by 2/3 reviewers] · [Severity escalated: Qwen=MEDIUM, Gemini=HIGH → using HIGH]

#### 5.3 Cache-Control via custom middleware | LOW | `backend/app/middleware.py`
**Issue**: Cache headers manually injected via string-prefix checks instead of using `StaticFiles` mount headers.
**Evidence**: `middleware.py:46`
**Fix**: Pass `headers={"Cache-Control": "public, max-age=86400"}` to `StaticFiles()` mounts.
[Unique: Gemini]

#### 5.4 `TOCItem.model_rebuild()` placement | LOW | `backend/app/schemas.py`
**Issue**: Called at end of file after all imports; may cause import-order issues.
**Evidence**: `schemas.py:175-183`
**Fix**: Move immediately after `TOCItem` class definition.
[Unique: Qwen]

#### 5.5 Good auth endpoint separation | INFO | `backend/app/routes/auth.py`
**Impact**: Supports both browser (HTML) and API clients cleanly.
[Unique: Qwen]

---

### 6. Error Handling & Logging

#### 6.1 Exception handlers leak internal state to clients | HIGH | `backend/app/main.py`
**Issue**: Handlers return `exc.message` and `exc.details` directly, potentially exposing file paths, DB structure, etc.
**Impact**: Information disclosure in production.
**Evidence**: `main.py:165-177`
**Fix**: Return generic error messages in production. Log details server-side only.
[Unique: Qwen]

#### 6.2 Generic `Exception` catch loses traceback context | HIGH | `backend/app/database.py`
**Issue**: `raise DatabaseError(...) from e` preserves chain but original context may be lost in production logs.
**Evidence**: `database.py:97-101`
**Fix**: Call `logger.exception()` before re-raising. Include exception type in error details.
[Unique: Qwen]

#### 6.3 Metadata enrichment failures are silently swallowed | MEDIUM | `backend/app/services/reader_service.py`
**Issue**: `_enrich_book_metadata()` catches all exceptions, logs warning, and continues.
**Impact**: Books may have incomplete data with no visibility to operators.
**Evidence**: `reader_service.py:63-78`
**Fix**: Track enrichment failures in DB (`metadata_enrichment_failed` flag) and expose via API.
[Unique: Qwen]

#### 6.4 `logging.basicConfig(force=True)` overrides dependency logging | MEDIUM | `backend/app/logging_config.py`
**Issue**: Force-sets root logger, potentially breaking logging for libraries that initialized before app startup.
**Evidence**: `logging_config.py:42-47`
**Fix**: Only use `force=True` in development mode; check for existing handlers in production.
[Unique: Qwen]

#### 6.5 Custom exceptions lack machine-readable error codes | LOW | `backend/app/exceptions.py`
**Issue**: Only `message` and `details` attributes; no `error_code`.
**Evidence**: `exceptions.py:4-50`
**Fix**: Add `error_code: str` attribute (e.g., `BOOK_NOT_FOUND`, `DATABASE_ERROR`).
[Unique: Qwen]

#### 6.6 Good exception handler separation | INFO | `backend/app/main.py`
**Impact**: Specific handlers for each exception type with appropriate HTTP status codes; sanitizes responses.
[Confirmed by 2/3 reviewers]

---

### 7. Code Quality & Typing

#### 7.1 Circular import deferred inside function | HIGH | `backend/app/routes/library.py`
**Issue**: `from app.database import db_manager` inside `_run_background_scan()` indicates module coupling.
**Impact**: Code smell; harder to test and maintain.
**Evidence**: `library.py:66-68`
**Fix**: Move to module level or inject `db_manager` as a dependency.
[Unique: Qwen]

#### 7.2 `book_to_response()` standalone function breaks encapsulation | MEDIUM | `backend/app/schemas.py`
**Issue**: ORM-to-schema conversion logic lives outside the schema class.
**Evidence**: `schemas.py:74-82`
**Fix**: Make it a `@staticmethod` on `BookResponse` or use Pydantic v2 `model_validate()` with `from_attributes=True`.
[Unique: Qwen]

#### 7.3 Inline `import warnings` suggests circular dependency | MEDIUM | `backend/app/config.py`
**Issue**: `import warnings` inside `validate_secret_key()`.
**Evidence**: `config.py:66-68`
**Fix**: Move import to module level.
[Unique: Qwen]

#### 7.4 Global mutable `_admin_password_hash` is thread-unsafe | MEDIUM | `backend/app/auth.py`
**Issue**: Lazy initialization of global `_admin_password_hash` may race on first auth.
**Evidence**: `auth.py:50-55`
**Fix**: Use `functools.cache` or initialize at module load with a thread lock.
[Unique: Qwen]

#### 7.5 `list_with_count()` has 11 parameters — God method | LOW | `backend/app/repositories.py`
**Issue**: Too many parameters; hard to test and extend.
**Evidence**: `repositories.py:151-166`
**Fix**: Use parameter object pattern: `BookListFilter` dataclass.
[Unique: Qwen]

#### 7.6 Model docstrings out of sync with actual attributes | LOW | `backend/app/models.py`
**Issue**: Docstrings describe attributes that are relationships.
**Evidence**: `models.py:18-38`
**Fix**: Update docstrings to reflect actual model structure.
[Unique: Qwen]

#### 7.7 Good use of Pydantic v2 features | INFO | `backend/app/schemas.py`
**Impact**: `model_config`, `Field`, `from_attributes` ensure robust validation and accurate OpenAPI schemas.
[Confirmed by 2/3 reviewers]

---

### 8. Testing Coverage

#### 8.1 No backend tests for critical security paths | CRITICAL | `tests/`
**Issue**: Complete absence of security tests for auth, password hashing, encryption, and rate limiting.
**Impact**: Security regressions undetected; credential-handling bugs ship to production.
**Fix**: Implement `pytest` with `pytest-asyncio`. Create mock tests for `ReaderService`, database operations (in-memory SQLite fixture), API integration via `httpx.AsyncClient`, and all security functions.
[Confirmed by 2/3 reviewers] · [Severity escalated: Gemini=HIGH, Qwen=CRITICAL → using CRITICAL]

#### 8.2 No integration tests for database migrations | HIGH | `tests/`
**Issue**: Tests use fresh in-memory DB schema; no migration testing.
**Evidence**: `conftest.py:36-41`
**Fix**: Add tests that apply migrations and verify schema matches expected state.
[Unique: Qwen]

#### 8.3 No tests for NAS storage backend | HIGH | `tests/`
**Issue**: No test files for `backend/app/storage/` or `backend/app/nas_health.py`.
**Fix**: Add tests with mocked filesystem for file access, health checks, and operations.
[Unique: Qwen]

#### 8.4 Test fixtures don't override all dependencies | MEDIUM | `tests/conftest.py`
**Issue**: Only `get_db` is overridden; `get_ai_orchestrator`, NAS backend, and filesystem operations are not.
**Evidence**: `conftest.py:65-83`
**Fix**: Add dependency overrides for all external services.
[Unique: Qwen]

#### 8.5 No performance or load tests | MEDIUM
**Issue**: No `pytest-benchmark` or locust tests.
**Fix**: Add load tests for key endpoints (search, chapter load, scan).
[Unique: Qwen]

#### 8.6 Test file organization unclear | LOW
**Issue**: Both `test_api.py` and `test_api_extended.py` with no clear separation criteria.
**Fix**: Consolidate or organize by feature (auth, library, reader, settings).
[Unique: Qwen]

---

### 9. DevOps & Configuration

#### 9.1 Dockerfile permission issues on mounted volumes | CRITICAL | `Dockerfile`
**Issue**: `chown` runs before `USER dawnstar`, but runtime bind-mounted volumes may have different ownership.
**Impact**: Container may fail to write to data directories.
**Evidence**: `Dockerfile:31-33`
**Fix**: Document host directory ownership requirements, or use Docker volumes instead of bind mounts.
[Unique: Qwen]

#### 9.2 Library volume mounted read-only — cover writes will fail | HIGH | `docker-compose.yml`
**Issue**: `./library:/app/library:ro` but app needs write access for covers/metadata.
**Impact**: Cover extraction and metadata enrichment fail for NAS books.
**Evidence**: `docker-compose.yml:10`
**Fix**: Remove `:ro` or document that covers are stored separately in `static_covers`.
[Unique: Qwen]

#### 9.3 CI pipeline lacks vulnerability and secret scanning | HIGH | `.github/workflows/ci.yml`
**Issue**: CI only builds and runs health check — no trivy, snyk, or git-secrets scan.
**Impact**: Vulnerable images or leaked secrets deploy to production undetected.
**Fix**: Add security scanning step: `trivy image`, `gitleaks`, or `docker scan`.
[Unique: Qwen]

#### 9.4 SQLite pragmas exceed Docker memory reservation | MEDIUM | `backend/app/database.py`, `docker-compose.yml`
**Issue**: `mmap_size=256MB` + `cache_size=-64000` per connection exceed `reservations: memory: 128M`.
**Impact**: OOM kills under load.
**Evidence**: `database.py:49`, `docker-compose.yml:25`
**Fix**: Reduce pragmas to fit within constraints, or increase Docker memory to ≥1GB. Make pragmas configurable via env vars.
[Confirmed by 2/3 reviewers]

#### 9.5 Docker memory limits (512M) may be insufficient | MEDIUM | `docker-compose.yml`
**Issue**: Large library scans or AI operations may exceed 512MB.
**Impact**: OOM kills during memory-intensive operations.
**Evidence**: `docker-compose.yml:24-25`
**Fix**: Increase to 1GB minimum, add memory monitoring.
[Unique: Qwen]

#### 9.6 Multi-stage Docker build doesn't verify Python version match | MEDIUM | `Dockerfile`
**Issue**: Builder and runtime both use `python:3.12-slim` but no validation step.
**Fix**: Add `RUN python --version` check in both stages.
[Unique: Qwen]

#### 9.7 Pre-commit config excludes `tests/` from linting | MEDIUM | `.pre-commit-config.yaml`
**Issue**: `exclude: | ^tests/` means test code quality is not enforced.
**Evidence**: `.pre-commit-config.yaml:31-32`
**Fix**: Remove tests from exclude list or add separate test-specific rules.
[Unique: Qwen]

#### 9.8 No test command in `pyproject.toml` scripts | LOW | `pyproject.toml`
**Issue**: `pytest` in dev deps but no `[tool.uv.scripts]` section.
**Fix**: Add `test = "pytest -v"`, `lint = "ruff check backend/ tests/"`.
[Unique: Qwen]

#### 9.9 Good `.dockerignore` configuration | INFO
**Impact**: Excludes `.venv`, `__pycache__`, test files for smaller images.
[Unique: Qwen]

---

## Tool-Exclusive Findings

### Only Gemini flagged
- **Cache-Control via middleware instead of StaticFiles headers** (Frontend, LOW) — valid optimization but low priority.

### Only Claude flagged
- Claude's review was brief and focused on the three highest-impact items (committed secrets, EPUB XSS, blocking I/O). All three were also flagged by other tools and are merged into the main findings above.

### Only Qwen flagged
- **Rate limiter async-unsafe** (Security, HIGH)
- **Username enumeration** (Security, HIGH)
- **Middleware ordering** (Architecture, MEDIUM)
- **Symlink escape** (Architecture, MEDIUM)
- **`Book.summaries` N+1** (Database, HIGH)
- **`list_with_count` phantom reads** (Database, HIGH)
- **Missing FK indexes on `BookCategory`** (Database, MEDIUM)
- **Session `autoflush=False` staleness** (Database, MEDIUM)
- **`get_by_id_or_404` abstraction leak** (Database, LOW)
- **Chapter cache mtime reliability** (Async, MEDIUM)
- **Search cache no TTL** (Async, MEDIUM)
- **Batch import partial failures** (Async, MEDIUM)
- **Rate limit cleanup background task** (Async, LOW)
- **Exception handler information disclosure** (Error Handling, HIGH)
- **Generic exception traceback loss** (Error Handling, HIGH)
- **Silent metadata enrichment failures** (Error Handling, MEDIUM)
- **Logging `force=True` overrides** (Error Handling, MEDIUM)
- **No machine-readable error codes** (Error Handling, LOW)
- **Circular import** (Code Quality, HIGH)
- **`book_to_response` encapsulation** (Code Quality, MEDIUM)
- **Inline import warnings** (Code Quality, MEDIUM)
- **Thread-unsafe password hash init** (Code Quality, MEDIUM)
- **God method `list_with_count`** (Code Quality, LOW)
- **Docstring drift** (Code Quality, LOW)
- **No migration integration tests** (Testing, HIGH)
- **No NAS storage tests** (Testing, HIGH)
- **Incomplete test fixtures** (Testing, MEDIUM)
- **No load tests** (Testing, MEDIUM)
- **Test file organization** (Testing, LOW)
- **Dockerfile volume permissions** (DevOps, CRITICAL)
- **Library volume `:ro`** (DevOps, HIGH)
- **No CI security scanning** (DevOps, HIGH)
- **Docker memory limits insufficient** (DevOps, MEDIUM)
- **Python version validation in Docker** (DevOps, MEDIUM)
- **Pre-commit excludes tests** (DevOps, MEDIUM)
- **No test script in pyproject.toml** (DevOps, LOW)

---

## Quick Wins

Low-effort, high-impact fixes to ship first:

| # | Fix | Effort | Impact |
|---|---|---|---|
| QW1 | Sanitize upload filenames with `os.path.basename()` or `secure_filename()` | 2 lines | Blocks path traversal |
| QW2 | Add `secure=not config.debug` to session cookie | 1 line | Prevents cookie theft over HTTP |
| QW3 | Wrap EPUB parser blocking calls in `asyncio.to_thread()` | ~10 lines | Fixes event loop blocking |
| QW4 | Fail startup if `SECRET_KEY` is empty in production | 3 lines | Enforces crypto key strength |
| QW5 | Add `bleach.clean()` to chapter HTML response | ~5 lines | Mitigates XSS |
| QW6 | Add `.env` to `.gitignore` and rotate credentials | 1 line + ops | Stops credential exposure |
| QW7 | Remove `:ro` from library volume in `docker-compose.yml` | 1 character | Fixes cover extraction failures |
| QW8 | Use `asyncio.Lock` instead of `threading.Lock` in rate limiter | 2 lines | Makes rate limiting actually work |

---

## Recommended Action Plan

### P0 — This Sprint (Production Blockers)

1. **Revoke and rotate all committed credentials** — Google API key, Groq API key, admin password. Purge `.env` from git history.
2. **Enforce `SECRET_KEY` at startup** — fail if empty in production. Update `_derive_key()` to use it exclusively.
3. **Sanitize upload filenames** — `secure_filename()` or `os.path.basename()`.
4. **Add HTML sanitization to chapter content** — `bleach.clean()` before returning.
5. **Wrap all blocking I/O in `asyncio.to_thread()`** — file uploads, cover extraction, EPUB/MOBI parsing.
6. **Fix Docker Compose volume mounts** — remove `:ro` from library, increase memory to ≥1GB.

### P1 — Next Sprint (Scalability & Safety)

7. **Introduce Alembic migrations** — replace ad-hoc `_migrate()`, version-track all schema changes.
8. **Move session storage to Redis or database** — enable horizontal scaling and container restart resilience.
9. **Fix rate limiter for async** — use `asyncio.Lock` or Redis-backed store.
10. **Add comprehensive test suite** — security tests (auth, hashing, encryption), API integration tests, NAS storage tests.
11. **Reduce SQLite pragma memory** — `mmap_size` to 32MB, make configurable.
12. **Fix error response information leakage** — generic messages in production, detailed logs server-side.
13. **Add CI security scanning** — trivy/gitleaks step in GitHub Actions.

### P2 — Backlog (Hardening & Quality)

14. **Fix username enumeration** — constant-time comparison, uniform error responses.
15. **Add user isolation to search cache** — include session hash in cache key.
16. **Add TTL eviction to search cache** — `lru_cache` or `OrderedDict` with expiry.
17. **Fix `Book.summaries` lazy loading** — switch to `lazy="selectin"`.
18. **Add individual FK indexes on `BookCategory`**.
19. **Fix `autoflush=False` staleness** — enable autoflush or document refresh requirements.
20. **Reduce `list_with_count()` parameters** — parameter object pattern.
21. **Add machine-readable error codes** to custom exceptions.
22. **Resolve circular import** in library routes.
23. **Add pre-commit linting for tests/**.

---

## Appendix: Severity Matrix

| Section | CRITICAL | HIGH | MEDIUM | LOW | INFO |
|---|---|---|---|---|---|
| 1. Security & Auth | 2 | 3 | 2 | 1 | 0 |
| 2. Architecture & API Design | 0 | 2 | 2 | 1 | 1 |
| 3. Database & ORM | 1 | 2 | 3 | 1 | 1 |
| 4. Async / Performance | 0 | 2 | 3 | 1 | 1 |
| 5. Frontend & API Integration | 1 | 1 | 0 | 2 | 1 |
| 6. Error Handling & Logging | 0 | 2 | 2 | 1 | 1 |
| 7. Code Quality & Typing | 0 | 1 | 3 | 2 | 1 |
| 8. Testing Coverage | 1 | 2 | 2 | 1 | 0 |
| 9. DevOps & Configuration | 1 | 2 | 4 | 1 | 1 |
| **Total** | **6** | **17** | **23** | **11** | **7** |

---

## Appendix: Agreement Matrix

| Finding | Gemini | Claude | Qwen |
|---|---|---|---|
| Committed secrets in `.env` | — | ✅ CRITICAL | ✅ CRITICAL |
| Crypto key from `database_url` | ✅ MEDIUM | — | ✅ CRITICAL |
| In-memory session store | ✅ HIGH | — | ✅ HIGH |
| No database migrations | ✅ HIGH | — | ✅ CRITICAL |
| Blocking file I/O on event loop | ✅ HIGH | ✅ HIGH | ✅ HIGH |
| CPU-bound EPUB parsing | ✅ HIGH | ✅ HIGH | — |
| No backend tests | ✅ HIGH | — | ✅ CRITICAL |
| XSS in chapter content | — | ✅ CRITICAL | ✅ MEDIUM |
| Path traversal in upload | ✅ HIGH | — | ✅ MEDIUM |
| Cookie missing `Secure` flag | ✅ LOW | — | ✅ LOW |
| SQLite pragma memory vs Docker | ✅ MEDIUM | — | ✅ MEDIUM |
| Good Pydantic v2 usage | ✅ INFO | — | ✅ INFO |
| Good exception handler separation | ✅ INFO | — | ✅ INFO |
| Good SQLAlchemy relationships | ✅ INFO | — | — |
| Good repository pattern | — | — | ✅ INFO |
| Rate limiter async-unsafe | — | — | ✅ HIGH |
| Username enumeration | — | — | ✅ HIGH |
| Middleware ordering | — | — | ✅ MEDIUM |
| Symlink escape in path validation | — | — | ✅ MEDIUM |
| `Book.summaries` N+1 | — | — | ✅ HIGH |
| Dockerfile volume permissions | — | — | ✅ CRITICAL |
| Library volume `:ro` | — | — | ✅ HIGH |
| CI no security scanning | — | — | ✅ HIGH |