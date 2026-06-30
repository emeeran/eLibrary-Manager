# 012 — Full-Text Content Search

**Status:** Active  
**Version:** 1.1.0  
**Last Updated:** 2026-06-30  
**Depends on:** `001-library-management.md` (search/list), `008-file-parsers.md` (extraction)  
**Key Files:** `app/services/content_extractor.py`, `app/services/content_backfill_service.py`, `app/repositories.py` (`BookContentRepository`, search predicate), `app/routes/library.py`, `app/models.py` (`BookContent`)

## Overview

Makes the library search box match book **CONTENT** (body text), not just title/author. A background job extracts each book's full text and indexes it in an FTS5 table; the list/search query then surfaces any book whose body contains the term.

* EPUB → `ebooklib` spine walk + `BeautifulSoup.get_text`
* PDF → `PyMuPDF` (`fitz`) `page.get_text("text")`
* MOBI → `pymobi` (best-effort; yields "" if unavailable)

## Acceptance Criteria

### Extraction & storage

- **AC-1:** `extract_text(path, fmt)` returns normalized plain text for EPUB/PDF,
  best-effort for MOBI, and `""` for unsupported formats or extraction failures
  (never raises — the backfill must not crash on a bad file).
- **AC-2:** Extracted text is capped (`_MAX_TEXT_CHARS`) and whitespace-collapsed.
- **AC-3:** A `book_contents` table tracks per-book status
  (`pending | extracted | empty | failed`), `char_count`, `source_mtime`, and
  `extracted_at`. It stores **no text** — the text lives in the FTS table.
- **AC-4:** `books_content_fts` is a content-bearing FTS5 virtual table
  (`book_id UNINDEXED`, tokenized `content`), populated at the application layer
  (no triggers) because extraction is deferred/async.

### Backfill job

- **AC-5:** `POST /api/library/backfill-content` runs the extraction as a
  background task, returns `{scan_id}`, shares the `_active_scans` lock (409 if a
  scan/import is running), and streams progress via the shared
  `/api/library/scan-progress/{scan_id}` SSE endpoint.
- **AC-6:** The job seeds `pending` rows for any untracked book, processes books
  in batches (commit per batch), marks each `extracted`/`empty`/`failed`, and is
  **resumable** — `extract_status` is the checkpoint, so a crash/cancel resumes
  from the remaining `pending` books.
- **AC-7:** The job supports cooperative cancellation and reports
  `processed/total` + current path through the progress store.
- **AC-8:** `GET /api/library/content-index-status` returns
  `{total, indexed, pending, empty, failed}` for the search UI.

### Search behaviour

- **AC-9:** The library search predicate is
  `(title/author ilike) OR (metadata FTS match) OR (content FTS match)` — a
  body-only hit (term not in title/author) still surfaces the book.
- **AC-10:** Both FTS tables use the same MATCH term; two separate `IN` clauses
  joined by `OR` (not a SQL `UNION`) to avoid bind-param collisions.
- **AC-11:** When FTS tables are absent (e.g. in-memory test DB), search falls
  back to the portable title/author `ilike` scan unchanged.
- **AC-12:** When searching, `BookListResponse.content_snippets` carries a
  `snippet(books_content_fts, …)` context excerpt (match wrapped in `<mark>`)
  for each result book that matched by content; `None` when not searching or no
  content index. The library grid renders it on the matching card; the frontend
  escapes the whole snippet and restores only the `<mark>` delimiters so book
  content can never inject markup.

### Faceted filters & advanced syntax (v1.1)

- **AC-13:** `list_with_count` accepts `series_filter: list[str]` (multi-select,
  `Book.series.in_(…)`) and `rating_min: int` (`Book.rating >= …`), threaded
  through `LibraryService.list_books` and the `/api/books` route (`series`
  comma-separated, `rating_min`). Both are included in the response-cache key.
- **AC-14:** `GET /api/books/series` returns distinct series with book counts
  (excluding hidden), for the series facet UI.
- **AC-15:** Advanced search syntax: `author:/title:/series:/isbn:` tokens in the
  search box become ANDed `ilike` predicates (`_parse_search`); remaining bare
  tokens drive the normal ilike + FTS path.
- **AC-16:** "Jump to match" — clicking a content snippet opens
  `/reader/{id}?q=<bare_term>`; the reader seeds its in-book search from `?q=`
  after the first chapter loads.

## Data Model

```python
class BookContent:           # table: book_contents
    book_id:         PK, FK→books.id (CASCADE)
    extract_status:  str  default "pending"   # pending|extracted|empty|failed
    char_count:      int  default 0
    source_mtime:    float | None
    extracted_at:    datetime | None
```

```sql
CREATE VIRTUAL TABLE books_content_fts USING fts5(book_id UNINDEXED, content, tokenize='unicode61');
```

Migration `f3a4b5c6d7e8_add_content_search` (down_revision `e2f3a4b5c6d7`): creates
`book_contents` (with `ix_book_contents_status`), seeds existing books as
`pending`, and creates the FTS5 table (guarded — skipped if fts5 is unavailable).

## Test Coverage

`tests/test_content_search.py` — 6 tests (FTS tables created explicitly in a
fixture because the in-memory test DB runs no migrations):

| Test | AC |
|------|----|
| `test_extract_text_epub` | AC-1, AC-2 |
| `test_extract_text_pdf` | AC-1 |
| `test_extract_text_unknown_format_returns_empty` | AC-1 |
| `test_content_search_surfaces_body_match` | AC-9 |
| `test_metadata_search_still_works` | AC-9, AC-11 |
| `test_backfill_indexes_and_enables_search` | AC-5, AC-6, AC-9 |
| `test_search_returns_content_snippet` | AC-12 |

## Open Items / Future Work (M3b + later)

- **More facets** — date range (needs a normalized pubdate column),
  identifier/ISBN, tag/category multi-select beyond the single `category_id`.
- **Parallel extraction** — move `extract_text` to a `ProcessPoolExecutor` in the
  backfill for very large libraries (the function is already picklable).
- **Lazy extraction** — extract on first reader open as a gradual alternative to
  the bulk backfill.

> v1.0: content search + snippets. v1.1: series/rating facets, `field:term`
> syntax, jump-to-match. Search input already debounces at 300ms.
