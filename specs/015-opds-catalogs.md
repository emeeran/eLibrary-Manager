# 015 — OPDS Network Catalogs

**Status:** Active  
**Version:** 1.1.0  
**Last Updated:** 2026-11-01  
**Depends on:** `001-library-management.md` (downloaded items become Books), `007-settings.md` (Fernet secret handling)  
**Origin:** Moon+ Reader Pro parity — "Net Library" (see `docs/moonreader-feature-inventory.md`, cluster 6)

## Overview

Adds OPDS (Open Publication Distribution System) catalog support: the user
registers catalogs (name + root URL + optional basic-auth credentials), browses
their navigation/acquisition feeds through the eLM backend, and downloads
publication files directly into the library. The backend proxies all catalog
fetches so browser CORS rules and catalog credentials never reach the client,
mirroring Moon+ Reader's "Add new catalog / Net Library" feature.

## API Contract

All routes live under `/api/opds` (session-gated by `AuthMiddleware` like the
other `/api` routers; CSRF applies to mutating methods).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/opds/catalogs` | List registered catalogs |
| `POST` | `/api/opds/catalogs` | Register a catalog `{name, url, username?, password?}` |
| `PUT` | `/api/opds/catalogs/{catalog_id}` | Update a catalog |
| `DELETE` | `/api/opds/catalogs/{catalog_id}` | Remove a catalog |
| `GET` | `/api/opds/catalogs/{catalog_id}/browse?url=<feed-url>` | Fetch + normalize an OPDS feed (defaults to the catalog root) |
| `POST` | `/api/opds/catalogs/{catalog_id}/download` `{url, filename}` | Download an acquisition entry into `LIBRARY_PATH` and import it |

### Normalized feed schema (`browse` response)

```json
{
  "title": "…feed title…",
  "url": "…fetched url…",
  "entries": [
    {
      "id": "…opds entry id…",
      "title": "…",
      "summary": "…",
      "authors": ["…"],
      "thumbnail_url": "…or null…",
      "is_navigation": true,
      "download": {"url": "…", "media_type": "application/epub+zip"} | null
    }
  ]
}
```

An entry is a **navigation** entry when its selected link has an
`opds-catalog` profile type or a `subsection`-style rel; an **acquisition**
entry when a link rel contains `acquisition` (OPDS 1.x/2.x both covered).

## Data Model

New table `opds_catalogs` (migration `m0n1o2p3q4r5_add_opds_catalogs`):

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `name` | String(200) | display name |
| `url` | String(1000) | root feed URL |
| `username` | String(200), nullable | basic-auth user |
| `password_encrypted` | String(1000), nullable | Fernet via `security.encrypt_value` |
| `added_date` | DateTime | |
| `last_browsed` | DateTime, nullable | |

## Acceptance Criteria

### Catalog CRUD

- **AC-1:** `POST /api/opds/catalogs` creates a catalog; `GET /api/opds/catalogs`
  returns it with `has_password` (bool) — **never** the plaintext or encrypted
  password.
- **AC-2:** The stored password is Fernet-encrypted at rest
  (`security.encrypt_value`), consistent with NAS credentials (spec 007/009).
- **AC-3:** `PUT` updates name/url/credentials; `DELETE` removes the catalog;
  both respond 404 for an unknown id.
- **AC-4:** `POST` with a non-`http(s)` scheme URL (`ftp://`, `file://`, …)
  responds **400** (`ValidationError` → generic Dawnstar handler) and stores
  nothing.

### Browse (feed proxy)

- **AC-5:** `browse` fetches the catalog root (or the supplied `url`) and
  returns the normalized schema above; navigation and acquisition entries are
  classified per the rel/type rules.
- **AC-6:** Basic-auth credentials, when stored, are sent on catalog requests
  only — the response never echoes them.
- **AC-7:** Non-XML or malformed feed responses respond **502** with a JSON
  error (never a traceback/500).
- **AC-8:** Fetch timeout / connection failure responds **502** with a JSON
  error.
- **AC-9:** Fetch responses are capped (default 10 MB); an oversized feed
  responds **502**.
- **AC-10:** `browse` on an unknown catalog id responds **404**.
- **AC-11:** `browse?url=` targeting a different host than the catalog root is
  **allowed** (OPDS feeds legitimately link across hosts), but the scheme
  whitelist of AC-4 still applies to the target URL.

### Download

- **AC-12:** `download` fetches the acquisition URL, writes the file into
  `LIBRARY_PATH` under the supplied filename, and imports it as a `Book` via
  the normal scan pipeline — the response contains the new `book_id`.
- **AC-13:** A `filename` whose extension is not a supported format (per spec
  008 parsers: currently `.epub`/`.pdf`/`.mobi`) responds **400** and fetches
  nothing.
- **AC-14:** A failed/partial download (network error, non-200 status) leaves
  no partial file in `LIBRARY_PATH` and responds **502**.

## Frontend — Net Library panel (v1.1)

### AC-15: Net Library Entry Point
**Given** the library page
**When** the user clicks the "Net Library" sidebar item
**Then** the Net Library modal opens showing the catalog-management view

### AC-16: Catalog Management UI
**Given** the catalog-management view
**Then** registered catalogs are listed with name, URL, and auth indicator, each with Browse and Delete buttons
**And** the add-catalog form (name, root URL, optional username/password) creates a catalog via `POST /api/opds/catalogs` and refreshes the list
**And** Delete confirms first, then removes via `DELETE /api/opds/catalogs/{id}`
**And** failures surface as error toasts (never silent)

### AC-17: Browse UI
**Given** the user clicks Browse on a catalog
**Then** the modal switches to the feed view showing entries from the normalized browse schema
**And** navigation entries render an "Open" button that drills into the linked feed
**And** acquisition entries render a "Download" button deriving a supported filename (title + acquisition-URL extension, defaulting to `.epub`)
**And** feed-load failures (404/502) render an inline error message from the response body

### AC-18: Download Feedback
**Given** the user clicks Download on an acquisition entry
**Then** the button shows in-progress state and disables until the request resolves
**And** success shows a success toast with the imported book title and refreshes the library grid (`loadBooks`)
**And** failure restores the button and shows an error toast

## Security

- **SSRF posture:** the server fetches admin-supplied URLs. eLM is a
  self-hosted, single-admin app and catalogs legitimately live on the LAN
  (e.g., Calibre-Web's OPDS endpoint), so private-range hosts are **not**
  blanket-blocked. Mitigations: `http`/`https` scheme whitelist (AC-4/AC-11),
  response size cap (AC-9), request timeout (AC-8), and credentials are only
  ever attached to the registered catalog's requests.
- Credentials are Fernet-encrypted at rest and never returned by any route
  (AC-1).
- XML parsing uses `xml.etree.ElementTree` (external entities are not
  resolved by Python's default parser); no `lxml` DTD fetch.

## Test Coverage

`tests/test_opds.py` (new; catalog feeds served from in-process fixtures via a
monkeypatched fetch function — no network in tests):

| Test | AC |
|------|----|
| `test_create_and_list_catalog` | AC-1 |
| `test_password_encrypted_and_hidden` | AC-1, AC-2 |
| `test_update_and_delete_catalog` | AC-3 |
| `test_reject_non_http_scheme` | AC-4 |
| `test_browse_normalizes_navigation_feed` | AC-5 |
| `test_browse_classifies_acquisition_entries` | AC-5 |
| `test_browse_sends_basic_auth` | AC-6 |
| `test_browse_malformed_feed_502` | AC-7 |
| `test_browse_fetch_failure_502` | AC-8 |
| `test_browse_oversized_feed_502` | AC-9 |
| `test_browse_unknown_catalog_404` | AC-10 |
| `test_browse_cross_host_url_allowed` | AC-11 |
| `test_download_imports_book` | AC-12 |
| `test_download_rejects_unsupported_extension` | AC-13 |
| `test_download_failure_leaves_no_file` | AC-14 |
| Frontend Net Library panel (v1.1) | — | — | GAP (AC-15–AC-18; requires Playwright/E2E) |

## Open Items / Future Work

- Thumbnail proxying for relative OPDS cover URLs (currently absolute URLs
  only render).
- OPDS 2.x (JSON feed) support alongside Atom.
- Auto-detected OPDS URLs when the user opens an `atom+xml;profile=opds-catalog`
  link (Moon+ parity behavior).
