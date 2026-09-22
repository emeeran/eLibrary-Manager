# SPEC-014: Default File Viewer Integration

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-09-20
- **Depends On:** SPEC-001 (Library Management), SPEC-002 (Reader Interface), SPEC-007 (Settings), SPEC-013 (Calibre Deep Link — banner conventions)

## Purpose

Let the operating system treat eLibrary Manager as the default viewer for its
supported formats (`.epub`, `.pdf`, `.mobi`): double-clicking a file in the
desktop file manager opens it in the eLM reader via the default browser.
A `GET /open?path=<abs>` bridge resolves a filesystem path to an indexed book
(or imports it), and an `elibrary-open` wrapper + `.desktop` MIME registration
turns file-manager double-clicks into that URL. PDF registration is **opt-in**
via Settings; EPUB/MOBI are registered automatically at install.

The bridge is the path-keyed sibling of `GET /calibre/launch` (spec 013) and
follows the same rule: **every branch is a 302 — a user click never dead-ends
on a 404.**

---

## Behavior

### AC-014.01: Open an Indexed File

**Given** the file at `path` is already indexed (exact match on `Book.path`)
**When** `GET /open?path=<abs>` is called with a valid session
**Then** the system redirects (HTTP `302`) to `/reader/{book.id}` without re-importing
**And** the incoming path is normalized with `os.path.abspath` — never symlink-resolved (`Path.resolve()`), so scanner-style indexed paths still match

### AC-014.02: Open an Unindexed but Existing File

**Given** `path` has a supported extension, exists on disk, and is not indexed
**When** `GET /open?path=<abs>` is called
**Then** the system imports it metadata-only (indexes the path, never copies the file — `LibraryService.import_book`)
**And** then redirects to `/reader/{book.id}`
**And** any path on a mount readable by the service user is importable (not restricted to `library_path`) — this is the admin's own authenticated click

### AC-014.03: Open a Missing, Unindexed File

**Given** `path` is not indexed and does not exist
**When** `GET /open?path=<abs>` is called
**Then** the system redirects to `/library?calibre_pending={path}` (existing banner UI)

### AC-014.04: Open an Unparseable File

**Given** `path` exists but import fails (corrupt file, DRM, parser error)
**When** `GET /open?path=<abs>` is called
**Then** the failure is logged at WARNING and the system redirects to `/library?calibre_pending={path}`

### AC-014.05: Open a Hidden Book

**Given** the resolved or imported book has `is_hidden = true`
**When** `GET /open?path=<abs>` is called
**Then** the system redirects to `/library?calibre_hidden=1` — no password bypass (same rule as spec 013)

### AC-014.06: Open an Unsupported Extension

**Given** `path` does not end in `.epub`, `.pdf`, or `.mobi` (case-insensitive)
**When** `GET /open?path=<abs>` is called
**Then** the route returns HTTP `400` with detail `"Unsupported file format: {ext}"`

### AC-014.07: Cold-Session Deep Links Survive Login

**Given** an unauthenticated session follows a deep link (e.g. `/open?path=...`)
**When** the auth middleware redirects to `/login`
**Then** the redirect carries `?next={url-encoded path + query}`
**And** after successful sign-in the login page returns to `next` when it is a same-origin relative path (starts with `/` and not `//`); otherwise `/`

### AC-014.08: EPUB + MOBI Registered at Install

**Given** the `.deb` is installed with a real run user (`ELIBRARY_RUN_USER`, not the sandboxed `elibrary` system user) with an existing home directory
**When** postinst runs
**Then** it invokes `xdg-mime default elibrary-manager.desktop <mime>` as that user for `application/epub+zip` and `application/x-mobipocket-ebook`
**And** `/usr/bin/elibrary-open` and the `.desktop` entry (with `MimeType=` for all three formats) are installed
**And** PDF is not registered at install

### AC-014.09: PDF Registration Is Opt-In

**Given** the operator wants eLM as the system PDF handler
**When** `POST /api/settings/pdf-viewer` is called with `{"enabled": true}`
**Then** the current default handler (from `xdg-mime query default application/pdf`) is stored under settings key `pdf_viewer_previous_default` (unless eLM is already registered)
**And** `xdg-mime default elibrary-manager.desktop application/pdf` is executed off the event loop
**And** calling enable again when already registered is a no-op that does not clobber the stored previous handler
**When** `POST /api/settings/pdf-viewer` is called with `{"enabled": false}`
**Then** the stored previous handler is restored via `xdg-mime default`; if none was recorded the response says so and changes nothing

### AC-014.10: Wrapper Script

**Given** `elibrary-open <path | file://URI>` is invoked by the desktop entry
**When** the script runs
**Then** it reads `ELIBRARY_PORT` from `/etc/elibrary-manager/config.env` (fallback `8000`), converts a `file://` URI to a plain path, percent-encodes it, and `exec`s `xdg-open http://localhost:{PORT}/open?path={encoded}`

---

## API Contract

```
GET /open?path=<abs, 1..1000 chars>
  302 → /reader/{id} | /library?calibre_pending={path} | /library?calibre_hidden=1
  400 → {"detail": "Unsupported file format: {ext}"}   (unsupported extension)
  (unauthenticated → 302 /login?next=... by the auth middleware)

GET /api/settings/pdf-viewer →
  PDFViewerStatus {available: bool, enabled: bool, current: str, desktop: str}

POST /api/settings/pdf-viewer {enabled: bool} →
  {"enabled": bool, "previous": str, "restored": bool, "detail"?: str, "already"?: bool}
  500 on xdg-mime failure
```

## Implementation Map

| Component | File | Key Elements |
|-----------|------|--------------|
| Bridge route | `app/main.py` | `GET /open` (`open_by_path`) |
| Login return path | `app/main.py`, `frontend/templates/login.html` | AuthMiddleware `?next=`, login JS same-origin guard |
| PDF toggle | `app/routes/settings.py` | `_run_xdg_mime`, `GET/POST /api/settings/pdf-viewer` |
| Wrapper | `packaging/deb/elibrary-open` | `/usr/bin/elibrary-open` |
| Desktop entry | `packaging/deb/elibrary-manager.desktop` | `Exec=elibrary-open %u`, `MimeType=` |
| Install registration | `packaging/deb/postinst` | per-user `xdg-mime default` (EPUB+MOBI only) |

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|------------------|-----------|---------------|--------|
| AC-014.01 Indexed → reader | `tests/test_open_route.py` | `test_open_indexed_book_redirects_to_reader` | Covered |
| AC-014.06 Unsupported ext | `tests/test_open_route.py` | `test_open_rejects_unsupported_extension` | Covered |
| AC-014.03 Missing file banner | `tests/test_open_route.py` | `test_open_missing_unindexed_file_redirects_to_pending_banner` | Covered |
| AC-014.04 Unparseable banner | `tests/test_open_route.py` | `test_open_unindexed_existing_file_falls_back_to_banner_on_import_failure` | Covered |
| AC-014.05 Hidden no-bypass | `tests/test_open_route.py` | `test_open_hidden_book_never_bypasses_password` | Covered |
| AC-014.07 Login next | `tests/test_open_route.py` | `test_unauthenticated_page_request_preserves_target` | Covered (middleware; JS guard verified manually) |
| AC-014.09 PDF toggle | `tests/test_pdf_viewer_setting.py` | `test_status_*`, `test_enable_*`, `test_disable_*` | Covered |
| AC-014.08 postinst registration | — | — | GAP (packaging script; verified at install time) |
| AC-014.10 wrapper | — | — | GAP (shell script; `sh -n` + manual) |

## Dependencies

- SPEC-001 (import-by-path), SPEC-002 (reader), SPEC-007 (settings storage),
  SPEC-013 (banner query-param conventions `calibre_pending` / `calibre_hidden`)
- System: `xdg-utils` (already a package dependency), `python3` (wrapper encoding)
