# SPEC-007: Settings

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-04-15
- **Depends On:** SPEC-003 (AI Summarization)

## Purpose

Settings is the cross-cutting configuration feature of eLibrary Manager. It provides a single API surface and full-page UI for reading and persisting all user preferences: library path and scan behavior, reading display defaults (layout, font, line height, theme), text-to-speech parameters, AI provider selection and credential management, auto-page-flip timing, and summarization preferences. Settings influence every other feature at runtime -- the reader applies theme and font defaults, the AI engine reads provider and API-key configuration, and the scanner uses the library path. The settings page also hosts a health-check endpoint for operational monitoring and an AI connection test for validating credentials before use.

---

## Behavior

### AC-007.01: Get Current Settings

**Given** the application is running with a valid `AppConfig`
**When** the user sends `GET /api/settings`
**Then** the route reads the current `AppConfig` via `get_config()`
**And** returns a `SettingsResponse` JSON body with all 17 fields populated from the config singleton or hardcoded defaults
**And** the response uses the following defaults for fields not stored persistently:

| Field | Default | Source |
|-------|---------|--------|
| `library_path` | `cfg.library_path` | `AppConfig.library_path` |
| `auto_scan` | `false` | Hardcoded |
| `watch_changes` | `false` | Hardcoded |
| `page_layout` | `"single"` | Hardcoded |
| `text_align` | `"justify"` | Hardcoded |
| `font_size` | `100` | Hardcoded |
| `font_family` | `"georgia"` | Hardcoded |
| `line_height` | `"1.8"` | Hardcoded |
| `theme` | `"day"` | Hardcoded |
| `tts_speed` | `"1.0"` | Hardcoded |
| `tts_pitch` | `1.0` | Hardcoded |
| `ai_provider` | `cfg.ai_default_provider` | `AppConfig.ai_default_provider` |
| `ollama_url` | `cfg.ollama_local_url` | `AppConfig.ollama_local_url` |
| `auto_flip` | `false` | Hardcoded |
| `flip_interval` | `30` | Hardcoded |
| `summary_length` | `"medium"` | Hardcoded |
| `auto_summary` | `false` | Hardcoded |

**And** the HTTP status code is `200`

### AC-007.02: Save Settings (Full Update)

**Given** the user has modified one or more settings fields in the UI
**When** the user sends `POST /api/settings` with a `SettingsCreate` JSON body
**Then** the route applies a partial-update strategy: each non-None field from the request replaces the current value; each None field falls back to the `AppConfig` default or hardcoded default
**And** if `ai_provider` is provided and non-None, the route sets `os.environ["AI_DEFAULT_PROVIDER"]` to that value
**And** if `ai_api_key` is provided and `ai_provider` is `"google"`, the route sets `os.environ["GOOGLE_API_KEY"]` to the key value
**And** if `ai_api_key` is provided and `ai_provider` is `"groq"`, the route sets `os.environ["GROQ_API_KEY"]` to the key value
**And** the route returns a `SettingsResponse` with the merged (provided + defaults) values
**And** the HTTP status code is `200`

### AC-007.03: Save Settings -- Partial Update (Single Field)

**Given** the user changes only the theme
**When** the user sends `POST /api/settings` with body `{ "theme": "night" }`
**Then** all other fields in the request are `None`
**And** the response preserves the default values for every unspecified field
**And** `theme` in the response is `"night"`
**And** the HTTP status code is `200`

### AC-007.04: Save Settings -- Validation Errors

**Given** the user sends `POST /api/settings` with an invalid field value
**When** a field violates its Pydantic constraint
**Then** FastAPI returns HTTP `422 Unprocessable Entity` with a standard validation error detail

The following validation rules apply per field:

| Field | Type | Constraint | Invalid Examples |
|-------|------|------------|------------------|
| `library_path` | `Optional[str]` | `max_length=1000` | String longer than 1000 characters |
| `page_layout` | `Optional[str]` | `pattern="^(single\|double\|continuous)$"` | `"triple"`, `"scroll"`, `""` |
| `text_align` | `Optional[str]` | `pattern="^(justify\|left\|center)$"` | `"right"`, `"bottom"` |
| `font_size` | `Optional[int]` | `ge=50, le=200` | `0`, `49`, `201`, `-10` |
| `font_family` | `Optional[str]` | `pattern="^(georgia\|times\|arial\|verdana)$"` | `"comic"`, `"monospace"` |
| `line_height` | `Optional[str]` | `pattern="^(1.4\|1.6\|1.8\|2.0)$"` | `"1.0"`, `"3.0"`, `"2"` |
| `theme` | `Optional[str]` | `pattern="^(day\|sepia\|night)$"` | `"dark"`, `"light"` |
| `tts_speed` | `Optional[str]` | `pattern="^(0.5\|0.75\|1.0\|1.25\|1.5\|2.0)$"` | `"0.25"`, `"3.0"`, `"fast"` |
| `tts_pitch` | `Optional[float]` | `ge=0.5, le=2.0` | `0.0`, `0.49`, `2.1`, `10.0` |
| `ai_provider` | `Optional[str]` | `pattern="^(auto\|google\|groq\|ollama)$"` | `"openai"`, `"azure"` |
| `ai_api_key` | `Optional[str]` | `max_length=500` | String longer than 500 characters |
| `ollama_url` | `Optional[str]` | `max_length=500` | String longer than 500 characters |
| `flip_interval` | `Optional[int]` | `ge=5, le=300` | `0`, `4`, `301`, `500` |
| `summary_length` | `Optional[str]` | `pattern="^(short\|medium\|long)$"` | `"tiny"`, `"full"` |

### AC-007.05: Save Settings -- Boolean Null Handling

**Given** boolean fields (`auto_scan`, `watch_changes`, `auto_flip`, `auto_summary`) are optional in `SettingsCreate`
**When** a boolean field is sent as `null` or omitted from the request body
**Then** the response uses `false` as the default for that field
**And** if the boolean field is explicitly sent as `false`, it is stored as `false`
**And** if the boolean field is sent as `true`, it is stored as `true`

### AC-007.06: Save Settings -- Numeric Null Handling

**Given** numeric fields (`font_size`, `flip_interval`, `tts_pitch`) are optional in `SettingsCreate`
**When** a numeric field is sent as `null` or omitted from the request body
**Then** the response uses the hardcoded default (`font_size=100`, `flip_interval=30`, `tts_pitch=1.0`)
**When** `font_size` is sent as `0`
**Then** the response uses the default `100` (because `0` is falsy in the `or` fallback)
**When** `flip_interval` is sent as `0`
**Then** the response uses the default `30` (because `0` is falsy in the `or` fallback)

### AC-007.07: Test AI Connection -- Success

**Given** a valid AI provider and API key are provided
**When** the user sends `POST /api/settings/test-ai` with body `{ "provider": "google", "api_key": "valid-key" }`
**Then** the route sets `os.environ["AI_PROVIDER"]` to the requested provider
**And** sets the appropriate API key environment variable (`GOOGLE_API_KEY` for google, `GROQ_API_KEY` for groq)
**And** calls `orchestrator.generate_summary()` with a fixed test content string: `"This is a test of the AI connection. If you can see this, the connection is working properly."`
**And** returns HTTP `200` with body:
```json
{
  "status": "success",
  "provider": "google",
  "message": "Connection successful!",
  "test_summary": "<first 100 chars of generated summary>..."
}
```
**And** `test_summary` is truncated to 100 characters with `"..."` appended if the summary exceeds 100 characters
**And** `test_summary` is returned in full if it is 100 characters or shorter

### AC-007.08: Test AI Connection -- Failure

**Given** an invalid API key or unreachable provider is provided
**When** the user sends `POST /api/settings/test-ai`
**Then** `generate_summary()` raises an exception
**And** the route catches the exception and logs the error
**And** returns HTTP `400` with body:
```json
{
  "detail": {
    "error": "Connection failed",
    "message": "<exception message string>"
  }
}
```

### AC-007.09: Test AI Connection -- Validation

**Given** the user sends `POST /api/settings/test-ai` with an invalid provider
**When** the `provider` field does not match `^(auto|google|groq|ollama)$`
**Then** FastAPI returns HTTP `422` with a validation error
**When** the `provider` field is omitted
**Then** FastAPI returns HTTP `422` with a validation error (provider is required)
**When** the `api_key` field is omitted or `null`
**Then** the request passes validation (`api_key` is optional in `AIConnectionTest`)

### AC-007.10: Test AI Connection -- Provider-Specific Key Routing

**Given** the `ai_api_key` is provided alongside an `ai_provider`
**When** `provider` is `"google"`
**Then** the key is written to `os.environ["GOOGLE_API_KEY"]`
**When** `provider` is `"groq"`
**Then** the key is written to `os.environ["GROQ_API_KEY"]`
**When** `provider` is `"ollama"` or `"auto"`
**Then** no API key environment variable is set (Ollama uses URL-based auth; auto does not route to a single key)

### AC-007.11: Health Check

**Given** the application is running
**When** the user sends `GET /api/health`
**Then** the route returns HTTP `200` with body:
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```
**And** no database or external service calls are made

### AC-007.12: Settings UI -- Page Rendering

**Given** the application is running
**When** the user navigates to `GET /settings`
**Then** the server renders the `settings.html` template
**And** the page contains a sidebar with navigation tabs: General, Reading, Appearance, Text-to-Speech, Hotkeys, AI Provider, About
**And** the page contains a "Back to Library" button that navigates to `/`
**And** a bottom save bar with "Reset to Defaults" and "Save Settings" buttons

### AC-007.13: Settings UI -- Tab Navigation

**Given** the settings page is loaded
**When** the user clicks a tab in the sidebar (e.g., "Reading")
**Then** the `switchTab()` JavaScript function hides all panels and shows the matching panel (`panel-reading`)
**And** the active tab receives the CSS class `active`
**And** no server request is made (tab switching is client-side only)

### AC-007.14: Settings UI -- Load Settings on Page Init

**Given** the settings page is loaded
**When** the `DOMContentLoaded` event fires
**Then** the `loadSettings()` function first reads from `localStorage` key `"dawnstar-settings"`
**And** applies those values to all form elements
**And** then fetches `GET /api/settings` from the server
**And** server settings override localStorage values via `Object.assign()`
**And** the `applySettingsToUI()` function maps the merged settings object to form elements by ID

### AC-007.15: Settings UI -- Save Settings (Client-Side)

**Given** the user has modified settings fields
**When** the user clicks "Save Settings" or presses `Ctrl+S` / `Cmd+S`
**Then** the `saveSettings()` function collects all form values into a settings object
**And** writes the full settings object to `localStorage` key `"dawnstar-settings"`
**And** also writes `reader-theme`, `reader-zoom`, and `reader-speed` as individual localStorage keys for use by the reader page
**And** sends `POST /api/settings` with the settings as JSON
**And** on success, shows a success notification
**And** on failure, shows a warning notification that settings were saved locally but could not sync with the server
**And** the save button enters a loading state (disabled, original text hidden) during the request and exits it on completion

### AC-007.16: Settings UI -- Reset to Defaults

**Given** the user clicks "Reset to Defaults"
**When** the user confirms the browser `confirm()` dialog
**Then** the `resetSettings()` function removes `"dawnstar-settings"` from localStorage
**And** resets all form elements to hardcoded default values:
  - `library_path`: `"/home/user/ebooks"`
  - `auto_scan`: `false`
  - `watch_changes`: `false`
  - `page_layout`: `"single"`
  - `text_align`: `"justify"`
  - `font_size`: `100`
  - `font_family`: `"georgia"`
  - `line_height`: `"1.8"`
  - `tts_speed`: `"1.0"`
  - `tts_pitch`: `1`
  - `auto_flip`: `false`
  - `flip_interval`: `30`
  - `theme`: `"day"`
**And** shows an info notification: "Settings reset to defaults"
**And** does NOT send a POST to the server (reset is client-side only)

### AC-007.17: Settings UI -- Theme Selection

**Given** the Appearance tab is active
**When** the user clicks one of the three theme preview cards (Day, Sepia, Night)
**Then** the `selectTheme()` function adds the CSS class `selected` to the clicked theme option
**And** removes `selected` from all other theme options
**And** the `data-theme` attribute value is stored for inclusion in the next save request

### AC-007.18: Settings UI -- AI Provider Toggle

**Given** the AI Provider tab is active
**When** the user selects `"ollama"` from the AI Provider dropdown
**Then** the Ollama URL input row becomes visible
**When** the user selects any other provider (`google`, `groq`)
**Then** the Ollama URL input row is hidden

### AC-007.19: Settings UI -- Test AI Connection (Client-Side)

**Given** the AI Provider tab is active
**When** the user clicks "Test Connection"
**Then** the `testAIConnection()` function reads the `ai-provider` and `ai-api-key` values
**And** if the API key is empty and the provider is not `"ollama"`, shows a warning notification: "Please enter an API key first"
**And** otherwise sends `POST /api/settings/test-ai` with `{ "provider": "<value>", "api_key": "<value>" }`
**And** on success, shows a success notification with the provider name
**And** on failure, shows an error notification with the error detail
**And** the test button enters a loading state during the request

### AC-007.20: Settings UI -- Font Size Slider

**Given** the Reading tab is active
**When** the user drags the font size range slider
**Then** the `oninput` handler calls `updateFontSizeDisplay(value)`
**And** the display text updates to show `"{value}%"` (e.g., `"150%"`)
**And** the slider range is `min=50, max=200`, matching the schema constraint

### AC-007.21: Settings UI -- TTS Pitch Slider

**Given** the TTS tab is active
**When** the user drags the pitch range slider
**Then** the `oninput` handler calls `updatePitchDisplay(value)`
**And** the display text updates to show the value formatted to one decimal place (e.g., `"1.5"`)
**And** the slider range is `min=0.5, max=2.0, step=0.1`, matching the schema constraint

### AC-007.22: Settings UI -- Keyboard Shortcuts

**Given** the settings page is loaded
**When** the user presses `Escape` (and is not focused on an input, textarea, or select)
**Then** the browser navigates to `/` (library page)
**When** the user presses `Ctrl+S` or `Cmd+S`
**Then** the default browser save is prevented (`e.preventDefault()`)
**And** `saveSettings()` is called

### AC-007.23: Settings UI -- Notification System

**Given** any settings operation completes
**When** a notification is triggered via `showNotification(message, type)`
**Then** a notification element is appended to `document.body`
**And** the notification has one of four CSS classes: `notification-success`, `notification-warning`, `notification-error`, `notification-info`
**And** the notification contains a close button
**And** the notification auto-dismisses after 5 seconds with a CSS fade-out animation
**And** HTML in the message is escaped via `escapeHtml()` to prevent XSS

### AC-007.24: Settings UI -- Hotkeys Tab (Read-Only)

**Given** the Hotkeys tab is active
**Then** the page displays a table of keyboard shortcuts with action names and key bindings:
  - Show hotkeys: `F1`
  - Go to previous page/chapter: `Left`, `Up`, `PgUp`, `Backspace`
  - Go to next page/chapter: `Right`, `Down`, `PgDn`, `Space`
  - Zoom in / Increase font: `+`, `=`
  - Zoom out / Decrease font: `-`
  - Toggle fullscreen: `F11`
  - Close current panel: `Escape`
  - Search: `Ctrl+F`
  - Add new book: `Ctrl+N`
  - Open library: `Ctrl+L`
  - Toggle favorite: `Ctrl+D`
**And** a "Reset to Defaults" button calls `resetHotkeys()` which shows a confirm dialog and then an info notification

### AC-007.25: Settings UI -- About Panel

**Given** the About tab is active
**Then** the page displays application info:
  - Name: "eLibrary Manager"
  - Badge: "PRO"
  - Version: "1.0.0"
  - Build: "2025.02.08"
  - A description paragraph
  - A feature list (EPUB/PDF/MOBI support, AI summaries, TTS, themes, progress, search)
  - Links: Documentation, GitHub Repository, Report Issue, License
  - Copyright notice

---

## API Contract

### Endpoints

| Method | Path | Request Body | Response Body | Status Codes |
|--------|------|-------------|---------------|--------------|
| `GET` | `/api/settings` | None | `SettingsResponse` | `200` |
| `POST` | `/api/settings` | `SettingsCreate` | `SettingsResponse` | `200`, `422` |
| `POST` | `/api/settings/test-ai` | `AIConnectionTest` | `{ status, provider, message, test_summary }` | `200`, `400`, `422` |
| `GET` | `/api/health` | None | `{ status, version }` | `200` |
| `GET` | `/settings` | None | HTML (`settings.html`) | `200` |

### Data Models

#### SettingsCreate

All fields are optional. Omitted fields fall back to defaults.

| Field | Type | Constraint | Default | Description |
|-------|------|-----------|---------|-------------|
| `library_path` | `Optional[str]` | `max_length=1000` | `cfg.library_path` | Filesystem path to ebook collection |
| `auto_scan` | `Optional[bool]` | None | `false` | Automatically scan library on startup |
| `watch_changes` | `Optional[bool]` | None | `false` | Watch for filesystem changes |
| `page_layout` | `Optional[str]` | `^(single\|double\|continuous)$` | `"single"` | Default page display mode |
| `text_align` | `Optional[str]` | `^(justify\|left\|center)$` | `"justify"` | Default text alignment |
| `font_size` | `Optional[int]` | `ge=50, le=200` | `100` | Base font size as percentage |
| `font_family` | `Optional[str]` | `^(georgia\|times\|arial\|verdana)$` | `"georgia"` | Reader font family |
| `line_height` | `Optional[str]` | `^(1.4\|1.6\|1.8\|2.0)$` | `"1.8"` | Line spacing multiplier |
| `theme` | `Optional[str]` | `^(day\|sepia\|night)$` | `"day"` | Reader color theme |
| `tts_speed` | `Optional[str]` | `^(0.5\|0.75\|1.0\|1.25\|1.5\|2.0)$` | `"1.0"` | Speech playback rate |
| `tts_pitch` | `Optional[float]` | `ge=0.5, le=2.0` | `1.0` | Voice pitch (Web Speech only) |
| `ai_provider` | `Optional[str]` | `^(auto\|google\|groq\|ollama)$` | `cfg.ai_default_provider` | AI service for summaries |
| `ai_api_key` | `Optional[str]` | `max_length=500` | None | API key for selected provider |
| `ollama_url` | `Optional[str]` | `max_length=500` | `cfg.ollama_local_url` | Local Ollama server URL |
| `auto_flip` | `Optional[bool]` | None | `false` | Enable automatic page advancement |
| `flip_interval` | `Optional[int]` | `ge=5, le=300` | `30` | Seconds between auto-flip |
| `summary_length` | `Optional[str]` | `^(short\|medium\|long)$` | `"medium"` | Target summary word count |
| `auto_summary` | `Optional[bool]` | None | `false` | Auto-generate chapter summaries |

#### SettingsResponse

All fields are required in the response.

| Field | Type | Description |
|-------|------|-------------|
| `library_path` | `str` | Current library path |
| `auto_scan` | `bool` | Auto-scan on startup |
| `watch_changes` | `bool` | Filesystem watcher enabled |
| `page_layout` | `str` | Page display mode |
| `text_align` | `str` | Text alignment |
| `font_size` | `int` | Font size percentage |
| `font_family` | `str` | Font family name |
| `line_height` | `str` | Line height multiplier |
| `theme` | `str` | Active reader theme |
| `tts_speed` | `str` | TTS playback rate |
| `tts_pitch` | `float` | Voice pitch value |
| `ai_provider` | `str` | Active AI provider |
| `ollama_url` | `Optional[str]` | Ollama server URL |
| `auto_flip` | `bool` | Auto-flip enabled |
| `flip_interval` | `int` | Flip interval in seconds |
| `summary_length` | `str` | Summary target length |
| `auto_summary` | `bool` | Auto-summary enabled |

#### AIConnectionTest

| Field | Type | Constraint | Required | Description |
|-------|------|-----------|----------|-------------|
| `provider` | `str` | `^(auto\|google\|groq\|ollama)$` | Yes | AI provider to test |
| `api_key` | `Optional[str]` | None | No | API key for the provider |

#### AppConfig (Environment-Sourced Defaults)

Managed by `pydantic-settings`. Loaded from `.env` file and environment variables.

| Field | Type | Default | Env Var | Description |
|-------|------|---------|---------|-------------|
| `database_url` | `str` | `sqlite+aiosqlite:///./dawnstar_data/dawnstar.db` | `DATABASE_URL` | Database connection string |
| `library_path` | `str` | `./library` | `LIBRARY_PATH` | Default ebook directory |
| `covers_path` | `str` | `./static_covers` | `COVERS_PATH` | Extracted cover storage |
| `google_api_key` | `str` | `""` | `GOOGLE_API_KEY` | Google Gemini API key |
| `google_model` | `str` | `"gemini-1.5-flash"` | `GOOGLE_MODEL` | Gemini model identifier |
| `google_rate_limit_rpm` | `int` | `15` | `GOOGLE_RATE_LIMIT_RPM` | Rate limit (requests/min) |
| `groq_api_key` | `str` | `""` | `GROQ_API_KEY` | Groq API key |
| `groq_model` | `str` | `"llama-3.3-70b-versatile"` | `GROQ_MODEL` | Groq model identifier |
| `groq_rate_limit_rpm` | `int` | `30` | `GROQ_RATE_LIMIT_RPM` | Rate limit (requests/min) |
| `ollama_cloud_url` | `str` | `"https://api.ollama.ai"` | `OLLAMA_CLOUD_URL` | Ollama cloud endpoint |
| `ollama_cloud_model` | `str` | `"llama3.3"` | `OLLAMA_CLOUD_MODEL` | Cloud model identifier |
| `ollama_local_url` | `str` | `"http://localhost:11434"` | `OLLAMA_LOCAL_URL` | Local Ollama endpoint |
| `ollama_local_model` | `str` | `"llama3.3"` | `OLLAMA_LOCAL_MODEL` | Local model identifier |
| `ai_default_provider` | `str` | `"auto"` | `AI_DEFAULT_PROVIDER` | Default AI provider |
| `ai_enable_fallback` | `bool` | `true` | `AI_ENABLE_FALLBACK` | Enable provider fallback chain |
| `app_host` | `str` | `"0.0.0.0"` | `APP_HOST` | Server bind address |
| `app_port` | `int` | `8000` | `APP_PORT` | Server bind port |
| `debug` | `bool` | `false` | `DEBUG` | Enable debug mode |
| `log_level` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `"INFO"` | `LOG_LEVEL` | Logging verbosity |
| `max_cover_size` | `int` | `300000` | `MAX_COVER_SIZE` | Max cover image bytes |
| `lazy_load_batch_size` | `int` | `20` | `LAZY_LOAD_BATCH_SIZE` | Cover lazy-load batch |
| `db_pool_size` | `int` | `10` | `DB_POOL_SIZE` | Connection pool size |
| `db_max_overflow` | `int` | `20` | `DB_MAX_OVERFLOW` | Max overflow connections |

---

## Implementation Map

| Component | File | Key Functions / Classes |
|-----------|------|------------------------|
| Routes | `app/routes/settings.py` | `get_settings()`, `save_settings()`, `test_ai_connection()`, `health_check()` |
| Schemas | `app/schemas.py` | `SettingsCreate`, `SettingsResponse`, `AIConnectionTest` |
| Config | `app/config.py` | `AppConfig`, `get_config()` |
| AI Engine | `app/ai_engine.py` | `AIProviderOrchestrator.generate_summary()` (used by test-ai) |
| Template | `app/templates/settings.html` | Full-page settings UI with 7 tab panels |
| JavaScript | `app/static/js/settings.js` | `loadSettings()`, `saveSettings()`, `resetSettings()`, `testAIConnection()`, `switchTab()`, `selectTheme()`, `showNotification()` |
| Router Registration | `app/main.py` | `app.include_router(settings.router)` at line 69; `settings_page()` at line 143 |

---

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|------------------|-----------|---------------|--------|
| AC-007.11: Health check returns 200 with healthy status | `tests/test_api.py` | `test_health_check` | Covered |
| AC-007.01: Get settings returns all fields | - | - | GAP |
| AC-007.02: Save settings with full body | - | - | GAP |
| AC-007.03: Save settings partial update | - | - | GAP |
| AC-007.04: Save settings validation rejects invalid fields | - | - | GAP |
| AC-007.05: Boolean null defaults to false | - | - | GAP |
| AC-007.06: Numeric null handling (zero vs omitted) | - | - | GAP |
| AC-007.07: AI connection test success | - | - | GAP |
| AC-007.08: AI connection test failure returns 400 | - | - | GAP |
| AC-007.09: AI connection test validation | - | - | GAP |
| AC-007.10: Provider-specific key routing | - | - | GAP |

---

## Dependencies

### External

| Package | Version | Purpose |
|---------|---------|---------|
| `pydantic` | >=2.0 | Schema validation for `SettingsCreate`, `SettingsResponse`, `AIConnectionTest` |
| `pydantic-settings` | >=2.0 | `AppConfig` with `.env` file support and `SettingsConfigDict` |
| `fastapi` | >=0.100 | Route handlers, HTTPException, APIRouter |
| `httpx` | >=0.24 | Test client for async API tests |

### Internal

| Component | Spec | Usage |
|-----------|------|-------|
| AI Engine | SPEC-003 | `get_ai_orchestrator().generate_summary()` called by `test_ai_connection()` |
| Config | This spec | `AppConfig` provides defaults; `get_config()` is a cached singleton |

---

## Open Questions

- Settings persistence is currently in-memory (environment variables) and localStorage. There is no database-backed settings table. A page reload on the server side resets non-environment defaults. A future spec may introduce a `settings` DB table for durable persistence.
- The `ai_api_key` field is sent over plaintext HTTP. In production, the application should be behind a TLS reverse proxy to protect credentials in transit.
- The `font_family` schema allows `"custom"` in the HTML `<select>` but the `SettingsCreate` pattern only allows `^(georgia|times|arial|verdana)$`. Submitting `"custom"` will result in a `422` validation error. This UI/schema mismatch should be resolved.
- The `page_margins`, `sidebar_width`, `card_size`, and `tts_engine` fields exist in the HTML template but are not included in the `SettingsCreate` schema, meaning they are saved only to localStorage and never sent to the server.
