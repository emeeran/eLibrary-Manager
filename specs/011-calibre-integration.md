# 011 — Calibre Integration

**Status:** Active  
**Version:** 1.3.0  
**Last Updated:** 2026-08-05  
**Key Files:** `app/services/calibre_sync_service.py`, `app/services/calibre_sync_monitor.py`, `app/routes/calibre.py`, `app/routes/library.py`, `app/models.py`

## Overview

Integrates Calibre libraries with the application in two complementary ways:

1. **Calibre Library Importer** — reads a Calibre library's `metadata.db`
   catalog, resolves each volume's real EPUB/PDF/MOBI file on disk, and imports
   the volumes (with full metadata, covers, ratings, tags, descriptions) into
   the application's index so they are readable in **this** reader.
2. **Calibre-Web Deep Link** — when a Calibre-Web instance is configured,
   exposes "Open in Calibre-Web" affordances on Calibre-imported books that jump
   to that book's page in the external Calibre-Web UI.

This spec also covers the (already-existing) multi-source indexing behaviour
documented in the acceptance criteria below: the index is built from both the
local `library_path` and any configured NAS mount, and the resulting database
always lives on the local filesystem.

## Acceptance Criteria

### Importer

- **AC-1:** A `CalibreImporter` reads Calibre's `metadata.db` read-only (URI
  `?mode=ro`) and resolves every volume's best-available readable format using
  the preference order **EPUB > PDF > MOBI**.
- **AC-2:** Volumes that have no EPUB/PDF/MOBI format on disk are skipped and
  counted as `no_readable_format` (never as errors).
- **AC-3:** Metadata is mapped as follows:
  - title, author(s) (comma-joined), publisher, pubdate (`YYYY-MM-DD`),
    comments → description, language, tags → subjects.
  - ISBN from `identifiers[type='isbn']`, falling back to `books.isbn`.
  - Rating: Calibre's 0–10 half-star scale is divided by 2 and clamped to 0–5.
- **AC-4:** Calibre's `cover.jpg` (next to the formats in each book folder) is
  copied into `static_covers` via the shared `optimize_cover_bytes` helper at
  the standard 600×900 / q85, so covers match the rest of the library.
- **AC-5:** Each imported `Book` records its `calibre_id` (the numeric Calibre
  book id) and `calibre_uuid` for re-sync deduplication and deep-linking.
- **AC-6:** Re-importing the same library skips volumes already present (matched
  by path *or* by `calibre_id`), counted as `skipped_existing`.
- **AC-7:** Import supports cooperative cancellation and reports progress
  (processed/total + current title) through the same `scan_progress` store and
  SSE stream (`/api/library/scan-progress/{scan_id}`) as normal scans.
- **AC-8:** The blocking SQLite read and per-volume file stat run in a
  threadpool (`asyncio.to_thread`) so the server stays responsive.

### Routes

- **AC-9:** `GET /api/library/calibre-status?path=...` validates whether a path
  is a Calibre library root (has `metadata.db` and it is readable) and returns
  the volume count. Never throws — returns `{valid: false, error}` on failure.
- **AC-10:** `POST /api/library/import-calibre` (body `{path}`) kicks off the
  background import, returns `{scan_id}` immediately, and is mutually exclusive
  with a running scan (409 if one is active). Shares the library scan lock.
- **AC-11:** `GET /api/books/{id}/calibre-web-url` returns `{url, calibre_id}`
  when the book is Calibre-imported **and** `calibre_web_url` is configured;
  otherwise `{url: null, reason}` with a human-readable reason.
- **AC-12:** `GET /api/books/{id}/open-calibre-web` 302-redirects to the
  Calibre-Web book page (404 if unavailable).

### Settings

- **AC-13:** `calibre_web_url` is a persisted setting (round-tripped through
  `GET`/`POST /api/settings`), excluded from no special handling beyond storage.
- **AC-14:** A "Calibre" settings panel lets the user validate a library path,
  run the import (with live progress), and set the Calibre-Web base URL.

### Frontend

- **AC-15:** Book cards show an "Open in Calibre-Web" action button **only** for
  books with a `calibre_id`.
- **AC-16:** The reader toolbar shows an "Open in Calibre-Web" tab only for
  Calibre-imported books (revealed after book load via
  `maybeShowCalibreWebTab`).

### Multi-source indexing (documented — pre-existing)

- **AC-17:** `LibraryService.fast_index()` scans the local `library_path` and,
  when NAS is enabled and healthy, the NAS mount path, writing both into the
  single local index. Each book is tagged `storage_type = "local"` or `"nas"`.
- **AC-18:** The indexed database (`config.database_url`) always resides on the
  local filesystem regardless of where book files live.

### Incremental re-sync & series (v1.1)

- **AC-19:** The catalog query also reads each volume's Calibre
  `books.last_modified` and `series`/`series_index` (via
  `books_series_link` → `series`). These populate `CalibreVolume.last_modified`,
  `.series`, `.series_index`.
- **AC-20:** `import_library` accepts a `lookup_check(volume) ->
  "new" | "changed" | "unchanged"` callback (preferred over the legacy boolean
  `exists_check`, which is retained for backward compatibility → True maps to
  `"unchanged"`). On `"changed"` it calls `update_one(volume, book_data)` and
  counts it as `updated`; on `"unchanged"` it skips (`skipped_existing`); on
  `"new"` it inserts (`imported`).
- **AC-21:** The route builds a `calibre_id -> (book_id, calibre_last_modified)`
  map once and resolves each volume by comparing Calibre's `last_modified` to the
  stored value. A volume with no stored `last_modified` (e.g. first run after the
  column was added) is treated as `"changed"` so metadata is refreshed once.
- **AC-22:** `update_one` refreshes the scalar metadata (title, author,
  publisher, publish_date, description, language, isbn, rating, series,
  series_index, cover if present) and stores the new `calibre_last_modified`. It
  never duplicates a book. (Re-categorization on tag changes is deferred.)
- **AC-23:** Series is captured on `BookCreate` and surfaced in `BookResponse`
  (`series`, `series_index`).
- **AC-24:** The completion message and progress payload report
  `imported / updated / unchanged`.

### Sync completeness (v1.2)

- **AC-25:** The sync logic lives in a reusable `sync_library(session, root,
  prune_missing=False)` (`app/services/calibre_sync_service.py`) used by both the
  manual import route and the auto-scheduler. `update_one` re-categorizes from
  Calibre tags (idempotent) and clears `is_deleted` if a pruned volume reappeared.
- **AC-26:** With `prune_missing=True`, eLM books whose `calibre_id` is absent
  from the catalog are soft-deleted (`is_deleted=True`, migration
  `g4b5c6d7e8f9`), never hard-deleted.
- **AC-27:** Soft-deleted books are excluded from the normal list/count views
  (`_build_list_query` default `show_deleted=False`) and from `total_books` in
  stats; they appear in the "Deleted" view (alongside stale-file books) and are
  counted as `deleted_books`.
- **AC-28:** `POST /api/books/{id}/restore` clears `is_deleted` (404 if missing).
- **AC-29:** An auto-sync monitor (`CalibreSyncMonitor`) runs in the lifespan
  when both `calibre_library_path` and a non-zero
  `calibre_auto_sync_interval_minutes` are set, calling `sync_library` on each
  interval. It shares `_active_scans` (skips if a scan is running) and swallows
  per-run errors so the loop survives a bad run.

### Series browse (v1.3)

The series data captured at import (v1.1, AC-19/AC-23) is surfaced as a
first-class browse surface — a grid of series the reader can drill into.

- **AC-30:** `GET /api/series` returns each distinct, non-hidden, non-deleted
  series with its book `count` and a representative `cover_path`/`author`
  (the volume with the smallest `series_index`, tie-broken by `id`), ordered by
  count descending then name. Books with a null series are excluded.
- **AC-31:** `GET /api/series/{name}` returns the books in that series
  (non-hidden, non-deleted) ordered by `series_index` ascending (nulls last),
  serialized as `BookResponse` items.
- **AC-32:** An unknown or empty series name returns `200` with an empty list —
  never a 404 — so the UI can render an empty state.
- **AC-33:** The library offers a "Series" view mode that renders series cards
  (name, count, representative cover); selecting a series switches the grid to
  that series (ordered by `series_index`).

## Data Model

```python
class Book:
    calibre_id:             Mapped[int | None]      # indexed, nullable
    calibre_uuid:           Mapped[str | None]      # nullable, len ≤ 64
    calibre_last_modified:  Mapped[str | None]      # raw Calibre timestamp, equality-compared
    series:                 Mapped[str | None]      # indexed, nullable
    series_index:           Mapped[float | None]    # nullable
```

Migrations:

* `d1e2f3a4b5c6_add_calibre_columns` — `calibre_id` (indexed) + `calibre_uuid`.
* `e2f3a4b5c6d7_add_calibre_sync_and_series` (down_revision `d1e2f3a4b5c6`) —
  `calibre_last_modified`, `series` (indexed), `series_index`. Idempotent via
  `batch_alter_table`.

## Calibre Schema Notes

The importer queries these tables (LEFT JOINs throughout so a book missing
publishers/comments/tags still imports):

`books`, `authors`/`books_authors_link`, `publishers`/`books_publishers_link`,
`comments`, `tags`/`books_tags_link`, `ratings`/`books_ratings_link`,
`languages`/`books_languages_link`, `identifiers`, `data`.

Many-to-many tables are collapsed with `GROUP_CONCAT`. Each `books.path` is
relative to the library root; the file is
`<library>/<books.path>/<data.name>.<format.lower()>` and the cover is
`<library>/<books.path>/cover.jpg`.

## Test Coverage

`tests/test_calibre.py` — 16 tests:

| Test | AC |
|------|----|
| `test_importer_validates_library_root` | AC-1 |
| `test_importer_reads_catalog` | AC-2, AC-3 |
| `test_importer_resolves_best_format` | AC-1 |
| `test_import_library_full_pipeline` | AC-1, AC-2, AC-4, AC-5, AC-6 |
| `test_import_library_skips_existing` | AC-6 |
| `test_calibre_status_route` | AC-9 |
| `test_calibre_status_rejects_bad_path` | AC-9 |
| `test_calibre_web_url_route` | AC-11, AC-13 |
| `test_calibre_web_url_for_non_calibre_book` | AC-11 |
| `test_importer_reads_series_and_last_modified` | AC-19 |
| `test_import_library_incremental_update` | AC-20, AC-21, AC-24 |

Tests build a real on-disk Calibre library (genuine schema + EPUB + cover.jpg)
so the importer exercises actual file resolution and cover copying.

## Open Items / Future Work

- **Series import** — done in v1.1.
- **Incremental re-sync** — done in v1.1.
- **Pruning deleted volumes** — done in v1.2 (soft-delete + Deleted view + restore).
- **Auto-scheduling** — done in v1.2 (`CalibreSyncMonitor`).
- **Re-categorize on tag change** — done in v1.2 (`update_one` re-categorizes).
- **Series browse view** — done in v1.3 (`GET /api/series`,
  `GET /api/series/{name}`, library "Series" view mode).
- **Custom columns** — generic Calibre `custom_columns` import (series shipped
  first as the 80/20).
- OPDS feed consumption as an alternative to a local `metadata.db`.
- **Restore UI** — a button on the Deleted view to restore pruned books (the
  `POST /api/books/{id}/restore` endpoint exists; the UI is a follow-up).
