# Blind Review (Phase 5)

## How this was produced

A **fresh subagent** was dispatched with a sanitized cold-review prompt —
framed as ordinary technical due diligence ("your team is about to take over
on-call; review as a senior engineer seeing it for the first time"). The prompt
deliberately did **not** mention this cleanup pipeline, its phases, "debloat,"
`AUDIT.md`, the purge pen, or that any refactor had occurred, so the reviewer
could not grade the pipeline's own work with the answer key in hand.

The review below is the subagent's final message, **saved verbatim and unedited**
by the main thread. Reconciliation against `AUDIT.md` lives in `AUDIT.md`
("Missed by pipeline, caught by blind review"), not here.

## Honest limit — read this

This subagent runs on the same underlying model as the rest of this session. A
sanitized, context-blind pass removes **self-grading bias** and **framing bias**
(both real, both fixed by the sanitized dispatch), and it demonstrably caught
two P0 issues the earlier phases missed. It does **not** remove blind spots the
model has regardless of context. For a genuinely independent signal beyond what
this phase can offer, paste a sample of the finished code into a **brand-new
session with no relation to this one** — a fresh terminal/conversation, ideally
a different reviewer's eyes — and ask the same cold-review question. Treat this
file as one data point, not a substitute for that.

---

# eLibrary Manager — Technical Due Diligence Review

Scope reviewed: `backend/app/` (FastAPI, async SQLAlchemy/SQLite, AI, parsing, NAS, Calibre), `frontend/`, `tests/`, `alembic/`, `Dockerfile`, `docker-compose.yml`. Every claim below is backed by `file:line` and verified where feasible (two bugs reproduced empirically against a real SQLite DB).

## Headline finding: logout / password-change revocation is silently broken

**`backend/app/auth.py:171-190`** — `_bump_epoch()` opens a session via `db_manager.session_factory()`, writes the new epoch, and exits the `async with`. But `AsyncSession.__aexit__` only calls `close()` — it does **not** auto-commit (confirmed by reading the SQLAlchemy source). The `get_session()` context manager is the one that commits; `session_factory()` is the raw maker. So the epoch bump is rolled back on close.

I verified this empirically:
```
epoch before bump: 0
epoch returned by bump: 1      ← in-memory cache updated
epoch from DB after bump: 0    ← but DB never got it
RESULT: BUG CONFIRMED — epoch NOT persisted
```

Consequence: **logout does not invalidate the old session token.** After logging out, the previous cookie keeps working until its 24h absolute expiry (`auth.py:42,236`). The docstring at `auth.py:246-254` explicitly promises the opposite. The fix is a one-liner: add `await db.commit()` inside `_bump_epoch` (and ideally make `_bump_epoch` use `get_session()` like everything else).

**Why the tests miss it:** `tests/test_security_session.py:34-48` stubs out both `_get_current_epoch` and `_bump_epoch` with in-memory fakes. The real DB-backed code path that actually performs logout has **zero test coverage**. This is the highest-severity item on the list.

## Bugs / logic errors

- **`backend/app/routes/settings.py:219`** — `orchestrator = get_ai_orchestrator()` calls an `async def` (`ai_engine.py:255`) without `await`. The variable is a coroutine object with no `generate_summary` attribute. **The entire "Test AI connection" feature (`POST /api/settings/test-ai`) is broken** — every call raises `AttributeError`/`TypeError`. Verified:
  ```
  type returned: <class 'coroutine'>
  has generate_summary? False
  RuntimeWarning: coroutine 'get_ai_orchestrator' was never awaited
  ```
  No test covers this endpoint (`grep test-ai tests/` → only unrelated provider-status tests).

- **`backend/app/scanner.py:206-207`** — `fast_index_directory` hardcodes `file_size = 0` (documented, for network-mount perf), then sets `total_pages=max(1, file_size // 2048)` = always `1`. Every fast-indexed book starts with `total_pages=1`. The reader service compensates by re-deriving on first open (`reader_service.py:70-77`), so it's cosmetic for the reader, but any UI showing "1 page" before first open is wrong. Low severity, but it's a real inconsistency.

- **`backend/app/main.py:147-151`** — The Alembic "stamp existing DB" branch keys off `"alembic_version" not in tables`. A DB that was created by the app's old `create_all` path but later got a partial Alembic application could match the wrong branch. Not a current bug, but fragile; worth a comment hardening.

- **`backend/app/routes/settings.py:29,43-44`** — `_reinit_nas_backend` starts the NAS health monitor with `loop.create_task(monitor.start())` and discards the reference. The task is not stored anywhere, so it can be garbage-collected mid-run (the well-known "fire-and-forget create_task" pitfall). The monitor silently stops. The `nas_health.py:35` monitor *does* keep its own `self._task`, which mitigates this for the normal startup path, but the runtime re-init path here is at risk.

- **`backend/app/auth.py:110-113`** — `_ensure_password_hash` is wrapped in `@lru_cache(maxsize=1)`. There is no admin password-change route that clears this cache, so an `ADMIN_PASSWORD` env change requires a process restart to take effect. Acceptable for a single-admin app, but undocumented and surprising if someone rotates credentials via env.

- **`backend/app/security.py:91-92`** — The HMAC password fallback uses `hmac.compare_digest(_hmac_hash(...), stored)`. Correct and constant-time, but note `_hmac_hash` prepends `"hmac:"` and the comparison is on the *full* prefixed string. Fine; just flagging that the bcrypt-truncation-at-72-bytes rule (`security.py:69`) does not apply to the HMAC path, so the two paths have different effective length limits. Minor.

## Concurrency / resource concerns

- **`backend/app/ai_providers/google_provider.py:59-67`** — `_get_client()` mutates `os.environ` (`os.environ.pop("GOOGLE_API_KEY")` then restores) to work around SDK behavior. This is a **process-global mutation** with no lock. Two concurrent summarization calls can interleave (call A pops, call B pops/gets None, call A restores) and produce a client missing the key, or restore after B already did. In practice with the GIL this is unlikely to corrupt, but it's a latent race and a code smell. The comment acknowledges the workaround is fragile.

- **`backend/app/routes/library.py:884`** and **`library.py:569-573`** — use deprecated `asyncio.get_event_loop().run_in_executor(...)` / `run_in_threadpool`. `get_event_loop()` is deprecated outside a running loop in 3.12+. Inside an async handler it works (returns the running loop), so functionally OK, but should be `asyncio.get_running_loop()` or `asyncio.to_thread()` for forward-compat.

- **`backend/app/scan_progress.py` + `backend/app/routes/library.py:35` (`_active_scans`)** — In-memory, single-process state. Fine for a single-worker SQLite app (Dockerfile pins `--workers 1`), but if anyone ever runs multiple workers these silently stop coordinating. Worth a comment, not a fix.

- **`backend/app/middleware.py:60,128-149`** — The in-memory rate limiter holds `_requests` as `defaultdict(lambda: defaultdict(list))` with cleanup only "every ~100 requests" gated on `len(self._requests) > 100`. Under sustained traffic from varied IPs/paths the dict grows without bound until the threshold, then cleans only keys whose lists are all-empty. A slow drip of new client IPs against `/hide` or `/unhide` could grow memory. Low severity for single-admin, but the cleanup condition is awkward.

## Security

- **`backend/app/routes/library.py:537-591` (`upload_book`)** — No `Content-Length` / body-size limit. `shutil.copyfileobj(file.file, buffer)` streams to disk (good), but Starlette buffers the multipart body in a temp file whose location/size is unbounded. Combined with no auth on the *size*, a malicious (or accidental) huge upload can fill the disk. The endpoint is auth-gated, so it's a self-DoS risk rather than external. Recommend an explicit `MAX_UPLOAD_SIZE` check.

- **`backend/app/routes/library.py:862-889` (`upload_cover`)** — `content = await file.read()` reads the **entire** uploaded image into memory before writing. No size limit, and only validates `content_type` (a client-controlled header). A multi-GB "image" exhausts memory. Same self-DoS class as above.

- **`backend/app/routes/library.py:424-494` (`browse_filesystem`)** — Authenticated directory traversal of the whole filesystem with a blocklist (`_BLOCKED_PATHS`). The blocklist is a deny-list approach (fragile — e.g. `/home`, `/opt`, `/srv`, `/media`, `/mnt` are all readable). For a single-admin tool this is the intended UX (pick any local dir to index), but be aware it exposes arbitrary directory listings to anyone who has the session cookie — and given the logout bug above, that includes ex-admins for up to 24h.

- **`backend/app/routes/library.py:97-122` (`_validate_path_safe`)** — Same deny-list philosophy for `index-local-dir`. `_validate_path_within_library` (`library.py:57-73`) is correctly an *allow-list* (relative_to check) — that one is solid.

- **XSS sanitization is good:** `backend/app/routes/reader.py:77-84` uses `nh3.clean` with an explicit tag/attribute allowlist. I verified `javascript:` URLs in `href` and `onerror` handlers are stripped. The reader correctly sanitizes both EPUB and PDF extracted content before sending to the browser. CSP (`security_middleware.py:50-62`) is well-formed with `frame-ancestors 'none'`, `object-src 'none'`. The `'unsafe-inline'` for script-src is documented and unavoidable given the inline-handler templates.

- **`backend/app/auth.py:74,225`** — HMAC signatures use `hmac.compare_digest` (constant-time). Correct.

- **`backend/app/routes/calibre.py:251-307` (`/calibre/launch`)** — This is on `web_router` (no `/api` prefix), correctly caught by `AuthMiddleware` as a page route → redirects unauthenticated users to `/login`. The `title` parameter feeds an `ilike(f"%{title}%")` (`calibre.py:295`) — but SQLAlchemy `ilike` binds the parameter, so no SQL injection. Note `title` has `max_length=500` but no other sanitization; a `%`/`_` in the title acts as a wildcard (minor, intentional).

## Over-engineered / inconsistent / templated

- **`backend/app/ai_engine.py:22-23` docstring** claims the fallback chain is "Google → Groq → Ollama Cloud → Ollama Local" but Groq is never instantiated (`_initialize_providers` only adds Google + two Ollamas). Stale comment from a removed provider.

- **`backend/app/ai_providers/google_provider.py:24`** sets `model = "gemini-1.5-flash"` as a class default, while `config.py:33` defaults `google_model = "gemini-2.5-flash"`. The class attr is immediately overwritten in `__init__` (`:47`), so no functional impact — just a confusing leftover.

- **`backend/app/config.py:36-38`** still references `ollama_cloud_model: str = "llama3.3"` and there's a `GROQ_API_KEY` reference in `settings.py:60-61` for a provider that doesn't exist. Dead config surface.

- **`backend/app/repositories.py:182,195`** — `__import__("sqlalchemy").text(...)` instead of a normal import. `text` is already imported at the top of the file (`from sqlalchemy import ... text`). Pure obfuscation, looks auto-generated.

- **Heavy module-level singletons + lazy `from x import y` inside functions.** Pattern is inconsistent: some modules import at top (`from app.ai_engine import get_ai_orchestrator`), others import inside the function body (`reader.py:143,158,165,197,208,240`). The latter is usually to avoid circular imports, which suggests the module graph is tangled. Not a bug, but a maintainability smell that's worth untangling.

- **`backend/app/parsers/epub_parser.py:211-215, 258`** — `warnings.filterwarnings("ignore", ...)` is called inside `get_chapters`/`get_single_chapter`, which mutates the **global** warnings filter list on every chapter fetch and never restores it. Minor leak of filter entries.

- **Two near-identical background-task runners:** `_run_background_scan` (`library.py:125-189`) and the inline `_run()` closures in `calibre.py`, `maintenance.py`, `library.py:240`. They duplicate try/except/scan_store/`_active_scans`/invalidate-cache logic four times. A single helper would cut ~150 lines.

## Under-tested / operationally risky

- **The two bugs above are both in untested paths.** The session-epoch DB path is stubbed in tests; `test-ai` has no test. The suite (130 tests, all green) gives false confidence exactly where it matters most.

- **`backend/app/parsers/pdf_parser.py`** — `fitz.open()` is called in ~8 places; most close via `doc.close()` but **not in `try/finally`**. If `_render_page_to_html` or `page.get_pixmap` raises mid-loop (e.g. corrupt PDF), the doc handle leaks until GC. On a long-running reader process against malformed PDFs this slowly leaks file descriptors. The `extract_cover` path (`pdf_parser.py:138-175`) is the worst: on the `optimize_cover_bytes` exception path the `doc.close()` at `:158` already ran, but if `pix = page.get_pixmap()` raises, `doc` is never closed. Use `with fitz.open(...) as doc:` everywhere.

- **`backend/app/scanner.py:165-225`** — `fast_index_directory` does synchronous `os.scandir` directly in the async coroutine (not via `to_thread`), only yielding every 50 dirs via `asyncio.sleep(0.01)`. On a large or slow mount this blocks the event loop for the duration of each `scandir` call — freezing every concurrent request (including SSE heartbeats). The comment acknowledges network mounts are slow but the fix (stat deferral) doesn't address the scandir blocking. This is the same class of bug the NAS health check (`storage/nas.py:42-57`) explicitly solved with `run_in_threadpool` + timeout.

- **`backend/app/storage/nas.py`** is solid: bounded timeout, threadpool, handles stale mounts. Good model for the scanner to follow.

- **Soft-delete + FTS inconsistency:** `books_fts` sync triggers (`alembic/versions/c4f1a2b3c4d5`) handle INSERT/DELETE but the soft-delete migration (`g4b5c6d7e8f9`) only adds an `is_deleted` column with an UPDATE. Soft-deleted books remain in the FTS index and stay searchable by title until hard-deleted. The list query filters `is_deleted` (`repositories.py`), but FTS-driven search will still surface them. Minor UX inconsistency at 3am.

- **`backend/app/services/calibre_sync_monitor.py` / `nas_health.py`** — background monitors started in `lifespan` (`main.py:179,217`). If `nas_monitor.start()` raises during startup, `app.state.nas_monitor` is never set and `_check_nas_available` (`reader.py:90-117`) handles `None` gracefully — good defensive coding. But there's no health alerting if the monitor task dies after start.

- **Docker:** `Dockerfile` runs minification (`jsmin`) as a build step that **mutates the copied `frontend/` in-place**. If the build cache re-runs, already-minified files get re-minified (jsmin is not always idempotent on its own output). Low risk but worth a `*.min.js` guard (which exists) + a clean-copy step.

## Genuinely well-done

- **CSRF + security headers (`security_middleware.py`)** — Same-origin enforcement layered on `SameSite=Lax`, correct host comparison, comprehensive header set. Belt-and-braces, well-reasoned docstrings.
- **XSS sanitization of reader content** — nh3 with tight allowlist, applied uniformly to EPUB and PDF paths; `javascript:`/event-handler stripping verified.
- **NAS backend (`storage/nas.py`)** — Correctly bounds kernel-blocking I/O with a threadpool + timeout, the one place that proactively defends the event loop. Excellent comments on *why*.
- **SQLite pragmas (`database.py:24-43`)** — WAL + `busy_timeout=15000` + `foreign_keys=ON`, centralized and shared with Alembic. The recent `busy_timeout` commit (`9a6c7b4`) shows the team understands the failure mode.
- **FTS5 query construction (`repositories.py:102-115`)** — User input is double-quoted and passed via bind params; FTS operators are neutralized. Correct against injection.
- **Path traversal for library-scoped operations (`library.py:57-73`)** — `resolve()` + `relative_to()` allow-list is the right pattern.
- **Keyset/cursor pagination (`repositories.py:33-99`)** — Nulls coalesced for a total order, encode/decode is opaque, sort expression mirrored on Python side. Thoughtful.
- **Single-flight summary generation (`reader_service.py:22-26`)** — Coalesces concurrent requests for the same chapter into one AI call. Good async pattern.
- **AI orchestrator retry/backoff (`ai_engine.py:130-157`)** — Bounded retries on `AIServiceError` only, exponential backoff, other exceptions propagate. Correctly scoped.
- **Soft-delete + FTS-row cleanup on hard delete** (`f4265b7`) — shows awareness of the FTS-index sync problem even if the soft-delete path misses it.

## On-call triage priorities

1. **P0 — Logout doesn't revoke sessions** (`auth.py:181-185`). One-line fix (`await db.commit()`), but until deployed, treat any logged-in session as valid for 24h regardless of logout. Add a real DB-backed test for `_bump_epoch`.
2. **P0 — "Test AI" button 500s every time** (`settings.py:219`). Add `await`. Add a test.
3. **P1 — PDF `fitz.open` not in `with`** (`pdf_parser.py` multiple). FD leak under malformed-PDF load. Switch to context managers.
4. **P1 — Synchronous `os.scandir` in async scanner** (`scanner.py:165`). Event-loop freeze on large/slow libraries. Move to `to_thread`.
5. **P2 — Upload size limits** (`library.py:537,862`). Add `MAX_UPLOAD_SIZE` and stream-check.
6. **P2 — Soft-deleted books stay FTS-searchable** (migration gap). Add an UPDATE trigger or filter in the FTS path.

The architecture is sound and the security posture on the *static* controls (CSP, CSRF, sanitization, path allow-lists) is genuinely strong for a project this size. The problems are concentrated in the *dynamic* paths that tests deliberately stub out — exactly the gap a new on-call team should close first.
