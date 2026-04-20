# SPEC-004: Bookmarks

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-04-15

## Purpose

Bookmarks allow readers to save and return to specific locations within a book. Each bookmark records a chapter index and character offset within that chapter, along with optional metadata (title, notes). The feature provides full CRUD lifecycle for bookmarks plus a jump endpoint that returns the raw navigation coordinates so the reader UI can restore the reading position. Bookmarks are scoped to a single book and cascade-deleted when the parent book is removed from the library.

## Behavior

### AC-004.01: Create Bookmark

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/bookmarks` with body `{ "chapter_index": N, "position_in_chapter": P }`
**Then** the system creates a `Bookmark` row with `book_id`, `chapter_index`, `position_in_chapter`, and server-generated `id` and `created_at`
**And** returns HTTP 200 with a `BookmarkResponse` body
**And** the response includes the generated `id` (auto-increment integer)
**And** the response includes `created_at` as a UTC datetime
**And** `title` and `notes` are `null` when omitted from the request

### AC-004.02: Create Bookmark with Title and Notes

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/bookmarks` with body `{ "chapter_index": N, "position_in_chapter": P, "title": "Important passage", "notes": "Revisit for essay" }`
**Then** the system creates a `Bookmark` row with the provided `title` and `notes`
**And** returns HTTP 200 with a `BookmarkResponse` containing the submitted `title` and `notes` values

### AC-004.03: Create Bookmark — chapter_index Validation

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/bookmarks` with `chapter_index` < 0
**Then** the system returns HTTP 422 (Unprocessable Entity)
**And** the response body contains a Pydantic validation error indicating `chapter_index` must be >= 0

### AC-004.04: Create Bookmark — position_in_chapter Validation

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/bookmarks` with `position_in_chapter` < 0
**Then** the system returns HTTP 422 (Unprocessable Entity)
**And** the response body contains a Pydantic validation error indicating `position_in_chapter` must be >= 0

### AC-004.05: Create Bookmark — title Max Length

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/bookmarks` with `title` exceeding 500 characters
**Then** the system returns HTTP 422 (Unprocessable Entity)
**And** the response body contains a Pydantic validation error indicating `title` must be at most 500 characters

### AC-004.06: Create Bookmark — Missing Required Fields

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/bookmarks` with an empty body or with `chapter_index` omitted
**Then** the system returns HTTP 422 (Unprocessable Entity)
**And** the response body contains a Pydantic validation error indicating `chapter_index` is required

### AC-004.07: Create Bookmark — position_in_chapter Default

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/bookmarks` with body `{ "chapter_index": N }` (omitting `position_in_chapter`)
**Then** the system creates the bookmark with `position_in_chapter` set to 0
**And** returns HTTP 200 with the `BookmarkResponse` showing `position_in_chapter: 0`

### AC-004.08: List Bookmarks

**Given** a book exists with id `{book_id}` and has 3 bookmarks
**When** the client sends `GET /api/books/{book_id}/bookmarks`
**Then** the system returns HTTP 200 with a `BookmarksResponse` body
**And** `bookmarks` is a list of 3 `BookmarkResponse` objects
**And** each item contains `id`, `book_id`, `chapter_index`, `position_in_chapter`, `title`, `notes`, and `created_at`

### AC-004.09: List Bookmarks — Ordering

**Given** a book has bookmarks created at times T1, T2, T3 (where T1 < T2 < T3)
**When** the client sends `GET /api/books/{book_id}/bookmarks`
**Then** the system returns bookmarks ordered by `created_at` descending
**And** the bookmark created at T3 appears first in the list
**And** the bookmark created at T1 appears last in the list

### AC-004.10: List Bookmarks — Empty

**Given** a book exists with id `{book_id}` and has no bookmarks
**When** the client sends `GET /api/books/{book_id}/bookmarks`
**Then** the system returns HTTP 200 with `{ "bookmarks": [] }`

### AC-004.11: List Bookmarks — Isolation

**Given** Book A has 2 bookmarks and Book B has 3 bookmarks
**When** the client sends `GET /api/books/{book_a_id}/bookmarks`
**Then** the system returns exactly 2 bookmarks belonging to Book A
**And** no bookmarks belonging to Book B are included

### AC-004.12: Delete Bookmark

**Given** a bookmark exists with id `{bookmark_id}`
**When** the client sends `DELETE /api/bookmarks/{bookmark_id}`
**Then** the system deletes the bookmark row from the database
**And** returns HTTP 200 with `{ "message": "Bookmark deleted successfully" }`
**And** a subsequent `GET /api/bookmarks/{bookmark_id}/jump` returns HTTP 404

### AC-004.13: Delete Bookmark — Idempotent Behavior

**Given** no bookmark exists with id `{bookmark_id}`
**When** the client sends `DELETE /api/bookmarks/{bookmark_id}`
**Then** the system returns HTTP 200 with `{ "message": "Bookmark deleted successfully" }`
**And** the delete statement matches zero rows without raising an error

### AC-004.14: Jump to Bookmark

**Given** a bookmark exists with id `{bookmark_id}`, `chapter_index` = 5, `position_in_chapter` = 1234
**When** the client sends `GET /api/bookmarks/{bookmark_id}/jump`
**Then** the system returns HTTP 200 with `{ "chapter_index": 5, "position_in_chapter": 1234 }`

### AC-004.15: Jump to Bookmark — Not Found

**Given** no bookmark exists with id `{bookmark_id}`
**When** the client sends `GET /api/bookmarks/{bookmark_id}/jump`
**Then** the system raises a `ResourceNotFoundError`
**And** the global exception handler returns HTTP 404 with `{ "error": "ResourceNotFoundError", "message": "Bookmark {bookmark_id} not found" }`

### AC-004.16: Delete Bookmark Does Not Affect Other Bookmarks

**Given** Book A has bookmarks B1 and B2
**When** the client sends `DELETE /api/bookmarks/{b1_id}`
**Then** bookmark B1 is deleted
**And** a subsequent `GET /api/books/{book_a_id}/bookmarks` returns only bookmark B2

### AC-004.17: Cascade Delete on Book Removal

**Given** Book A has 3 associated bookmarks
**When** Book A is deleted from the database (row removed from `books` table)
**Then** all 3 bookmark rows are automatically deleted by the `CASCADE` foreign key constraint on `bookmarks.book_id`
**And** no orphaned bookmark rows remain in the database

### AC-004.18: Bookmark Foreign Key Constraint

**Given** the `bookmarks` table has a `book_id` column with `ForeignKey("books.id", ondelete="CASCADE")`
**And** `book_id` is indexed for query performance
**Then** every bookmark row references a valid book or is cascade-deleted when the book is removed
**And** the index on `book_id` ensures efficient `WHERE book_id = ?` lookups

### AC-004.19: Multiple Bookmarks at Same Position

**Given** a book exists with id `{book_id}`
**When** the client creates two bookmarks with identical `chapter_index` and `position_in_chapter` values
**Then** both bookmarks are created successfully with distinct `id` values
**And** both appear in the `GET /api/books/{book_id}/bookmarks` response
**And** each can be deleted independently via `DELETE /api/bookmarks/{bookmark_id}`

### AC-004.20: Service — get_bookmark Raises ResourceNotFoundError

**Given** no bookmark exists with id `{bookmark_id}`
**When** `ReaderService.get_bookmark(bookmark_id)` is called
**Then** the method raises `ResourceNotFoundError` with message `"Bookmark {bookmark_id} not found"`

## API Contract

### Endpoints

| Method | Path | Request Body | Response Type | Status Codes |
|--------|------|-------------|---------------|--------------|
| GET | `/api/books/{book_id}/bookmarks` | — | `BookmarksResponse` | 200 |
| POST | `/api/books/{book_id}/bookmarks` | `BookmarkCreate` | `BookmarkResponse` | 200, 422 |
| DELETE | `/api/bookmarks/{bookmark_id}` | — | `{ message }` | 200 |
| GET | `/api/bookmarks/{bookmark_id}/jump` | — | `{ chapter_index, position_in_chapter }` | 200, 404 |

### Data Models

#### Bookmark (SQL Model)

```python
class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[int]                   # PK, autoincrement
    book_id: Mapped[int]              # FK("books.id", ondelete="CASCADE"), indexed
    chapter_index: Mapped[int]        # NOT NULL
    position_in_chapter: Mapped[int]  # default=0
    title: Mapped[Optional[str]]      # String(500), nullable
    notes: Mapped[Optional[str]]      # Text, nullable
    created_at: Mapped[datetime]      # NOT NULL, default=datetime.utcnow

    book: Mapped["Book"]              # relationship("Book")
```

#### BookmarkCreate (Request Schema)

```python
class BookmarkCreate(BaseModel):
    chapter_index: int          # Field(..., ge=0)
    position_in_chapter: int    # Field(0, ge=0)
    title: Optional[str]        # Field(None, max_length=500)
    notes: Optional[str]        # Field(None)
```

#### BookmarkResponse (Response Schema)

```python
class BookmarkResponse(BaseModel):
    id: int
    book_id: int
    chapter_index: int
    position_in_chapter: int
    title: Optional[str]
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
```

#### BookmarksResponse (List Response Schema)

```python
class BookmarksResponse(BaseModel):
    bookmarks: list[BookmarkResponse]
```

#### Jump Response (Inline)

```python
# Returned as plain dict, not a Pydantic model
{
    "chapter_index": int,
    "position_in_chapter": int
}
```

#### Delete Response (Inline)

```python
{
    "message": "Bookmark deleted successfully"
}
```

## Implementation Map

| Component | File | Key Functions |
|-----------|------|---------------|
| Routes | `app/routes/reader.py` | `list_bookmarks`, `create_bookmark`, `delete_bookmark`, `jump_to_bookmark` |
| Service | `app/services/reader_service.py` | `ReaderService.create_bookmark`, `ReaderService.list_bookmarks`, `ReaderService.get_bookmark`, `ReaderService.delete_bookmark` |
| Model | `app/models.py` | `Bookmark` |
| Schemas | `app/schemas.py` | `BookmarkBase`, `BookmarkCreate`, `BookmarkUpdate`, `BookmarkResponse`, `BookmarksResponse` |
| Exceptions | `app/exceptions.py` | `ResourceNotFoundError` |
| Exception Handler | `app/main.py` | `not_found_handler` (maps `ResourceNotFoundError` to HTTP 404) |

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|-----------------|-----------|---------------|--------|
| AC-004.01 Create Bookmark | — | — | GAP |
| AC-004.02 Create Bookmark with Title/Notes | — | — | GAP |
| AC-004.03 chapter_index Validation | — | — | GAP |
| AC-004.04 position_in_chapter Validation | — | — | GAP |
| AC-004.05 title Max Length | — | — | GAP |
| AC-004.06 Missing Required Fields | — | — | GAP |
| AC-004.07 position_in_chapter Default | — | — | GAP |
| AC-004.08 List Bookmarks | — | — | GAP |
| AC-004.09 List Bookmarks Ordering | — | — | GAP |
| AC-004.10 List Bookmarks Empty | — | — | GAP |
| AC-004.11 List Bookmarks Isolation | — | — | GAP |
| AC-004.12 Delete Bookmark | — | — | GAP |
| AC-004.13 Delete Bookmark Idempotent | — | — | GAP |
| AC-004.14 Jump to Bookmark | — | — | GAP |
| AC-004.15 Jump to Bookmark Not Found | — | — | GAP |
| AC-004.16 Delete Does Not Affect Others | — | — | GAP |
| AC-004.17 Cascade Delete on Book Removal | — | — | GAP |
| AC-004.18 Foreign Key Constraint | — | — | GAP |
| AC-004.19 Multiple Bookmarks Same Position | — | — | GAP |
| AC-004.20 Service get_bookmark Raises Error | — | — | GAP |

## Dependencies

- **SPEC-002: Reader Interface** — Book records must exist (via `BookRepository.get_by_id_or_404`) before bookmarks can be listed or created. The reader UI renders the bookmarks sidebar and calls the jump endpoint to navigate.
- **SPEC-001: Library Management** — Book deletion triggers cascade removal of all associated bookmarks via the `ondelete="CASCADE"` foreign key constraint.

## Open Questions

- None
