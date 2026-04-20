# SPEC-005: Notes & Annotations

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-04-15

## Purpose

Provides users with the ability to attach notes and text-highlight annotations to specific locations within a book's chapters. Notes are freeform text entries pinned to a chapter and character position, optionally quoting a passage from the text. Annotations represent highlighted text ranges with an optional attached note. Both entities support a fixed palette of five highlight colors and cascade-delete with their parent book. This spec covers full CRUD for notes and annotations, color validation, chapter-scoped filtering for annotations, timestamp management, and cascade deletion semantics.

---

## Behavior

### Notes

#### AC-005.01: Create Note

**Given** a book exists with `id={book_id}`
**When** the client sends `POST /api/books/{book_id}/notes` with a valid `NoteCreate` body
**Then** the system creates a `Note` record in the database
**And** returns HTTP 200 with a `NoteResponse` including the server-generated `id`, `book_id`, `created_at`, and `updated_at`
**And** `created_at` is set to the current UTC datetime
**And** `updated_at` is set to the same value as `created_at` on creation

#### AC-005.02: Create Note — Required Fields

**Given** a valid `NoteCreate` request
**When** the request body is validated
**Then** `content` is required and must have `min_length=1`
**And** `chapter_index` is required and must be `>= 0`
**And** `position_in_chapter` defaults to `0` and must be `>= 0`
**And** `color` defaults to `"yellow"`
**And** `quoted_text` is optional and defaults to `None`

#### AC-005.03: Create Note — Color Validation

**Given** a `NoteCreate` request with a `color` field
**When** `color` is not one of `yellow`, `green`, `blue`, `pink`, or `orange`
**Then** the system returns HTTP 422 with a Pydantic validation error
**And** no `Note` record is created

#### AC-005.04: Create Note — Empty Content Rejected

**Given** a `NoteCreate` request with `content` set to an empty string `""`
**When** the request body is validated
**Then** the system returns HTTP 422 with a Pydantic validation error
**And** no `Note` record is created

#### AC-005.05: List Notes

**Given** a book exists with `id={book_id}`
**And** the book has one or more notes in the database
**When** the client sends `GET /api/books/{book_id}/notes`
**Then** the system returns HTTP 200 with a `NotesResponse` body
**And** `notes` is a list of `NoteResponse` objects
**And** notes are ordered by `created_at` descending (most recent first)

#### AC-005.06: List Notes — Empty Result

**Given** a book exists with `id={book_id}`
**And** the book has zero notes
**When** the client sends `GET /api/books/{book_id}/notes`
**Then** the system returns HTTP 200 with `NotesResponse` containing an empty `notes` list

#### AC-005.07: Delete Note

**Given** a note exists with `id={note_id}`
**When** the client sends `DELETE /api/notes/{note_id}`
**Then** the system deletes the note row from the `notes` table
**And** returns HTTP 200 with body `{ "message": "Note deleted successfully" }`

#### AC-005.08: Delete Note — Idempotent

**Given** no note exists with `id={note_id}` (already deleted or never existed)
**When** the client sends `DELETE /api/notes/{note_id}`
**Then** the system returns HTTP 200 with `{ "message": "Note deleted successfully" }`
**And** the DELETE operation is idempotent — no error is raised for missing targets

#### AC-005.09: Note — Update Timestamp

**Given** a `Note` record exists in the database
**And** the `updated_at` column has `onupdate=datetime.utcnow`
**When** the note row is updated via SQLAlchemy
**Then** `updated_at` is automatically set to the current UTC datetime
**And** `created_at` remains unchanged from its original value

**Note:** As of the current implementation, there is no `PUT /api/notes/{note_id}` endpoint. The `NoteUpdate` schema exists in `app/schemas.py` but is not wired to a route. The `updated_at` column is ready for future note-editing functionality.

#### AC-005.10: Note — Quoted Text

**Given** a `NoteCreate` request includes `quoted_text`
**When** the note is created
**Then** the `quoted_text` value is stored in the `Note.quoted_text` column (nullable Text)
**And** the `NoteResponse` includes the `quoted_text` field

**Given** a `NoteCreate` request omits `quoted_text`
**When** the note is created
**Then** `Note.quoted_text` is stored as `None`
**And** the `NoteResponse` includes `quoted_text` as `None`

### Annotations

#### AC-005.11: Create Annotation

**Given** a book exists with `id={book_id}`
**When** the client sends `POST /api/books/{book_id}/annotations` with a valid `AnnotationCreate` body
**Then** the system creates an `Annotation` record in the database
**And** returns HTTP 200 with an `AnnotationResponse` including the server-generated `id`, `book_id`, and `created_at`
**And** `created_at` is set to the current UTC datetime

#### AC-005.12: Create Annotation — Required Fields

**Given** a valid `AnnotationCreate` request
**When** the request body is validated
**Then** `chapter_index` is required and must be `>= 0`
**And** `start_position` is required and must be `>= 0`
**And** `end_position` is required and must be `>= 0`
**And** `text` is required and must have `min_length=1`
**And** `color` defaults to `"yellow"`
**And** `note` is optional and defaults to `None`

#### AC-005.13: Create Annotation — Color Validation

**Given** an `AnnotationCreate` request with a `color` field
**When** `color` is not one of `yellow`, `green`, `blue`, `pink`, or `orange`
**Then** the system returns HTTP 422 with a Pydantic validation error
**And** no `Annotation` record is created

#### AC-005.14: Create Annotation — Empty Text Rejected

**Given** an `AnnotationCreate` request with `text` set to an empty string `""`
**When** the request body is validated
**Then** the system returns HTTP 422 with a Pydantic validation error
**And** no `Annotation` record is created

#### AC-005.15: List Annotations — All

**Given** a book exists with `id={book_id}`
**And** the book has annotations across multiple chapters
**When** the client sends `GET /api/books/{book_id}/annotations` (no `chapter_index` query parameter)
**Then** the system returns HTTP 200 with an `AnnotationsResponse` body
**And** `annotations` is a list of all `AnnotationResponse` objects for the book
**And** annotations are ordered by `start_position` ascending

#### AC-005.16: List Annotations — Filtered by Chapter

**Given** a book exists with `id={book_id}`
**And** the book has annotations in chapters 0, 1, and 2
**When** the client sends `GET /api/books/{book_id}/annotations?chapter_index=1`
**Then** the system returns HTTP 200 with an `AnnotationsResponse` body
**And** only annotations where `chapter_index == 1` are included
**And** the filtered annotations are ordered by `start_position` ascending

#### AC-005.17: List Annotations — Empty Result

**Given** a book exists with `id={book_id}`
**And** the book has zero annotations
**When** the client sends `GET /api/books/{book_id}/annotations`
**Then** the system returns HTTP 200 with `AnnotationsResponse` containing an empty `annotations` list

#### AC-005.18: List Annotations — Chapter Filter with No Matches

**Given** a book exists with `id={book_id}`
**And** the book has annotations only in chapters 0 and 1
**When** the client sends `GET /api/books/{book_id}/annotations?chapter_index=5`
**Then** the system returns HTTP 200 with `AnnotationsResponse` containing an empty `annotations` list

#### AC-005.19: Delete Annotation

**Given** an annotation exists with `id={annotation_id}`
**When** the client sends `DELETE /api/annotations/{annotation_id}`
**Then** the system deletes the annotation row from the `annotations` table
**And** returns HTTP 200 with body `{ "message": "Annotation deleted successfully" }`

#### AC-005.20: Delete Annotation — Idempotent

**Given** no annotation exists with `id={annotation_id}` (already deleted or never existed)
**When** the client sends `DELETE /api/annotations/{annotation_id}`
**Then** the system returns HTTP 200 with `{ "message": "Annotation deleted successfully" }`
**And** the DELETE operation is idempotent — no error is raised for missing targets

#### AC-005.21: Annotation — Attached Note

**Given** an `AnnotationCreate` request includes `note`
**When** the annotation is created
**Then** the `note` value is stored in the `Annotation.note` column (nullable Text)
**And** the `AnnotationResponse` includes the `note` field

**Given** an `AnnotationCreate` request omits `note`
**When** the annotation is created
**Then** `Annotation.note` is stored as `None`
**And** the `AnnotationResponse` includes `note` as `None`

### Cross-Cutting

#### AC-005.22: Cascade Delete on Book Removal

**Given** a book with `id={book_id}` has associated `Note` and `Annotation` records
**When** the book row is deleted from the `books` table
**Then** all `Note` rows with `book_id={book_id}` are automatically deleted (CASCADE)
**And** all `Annotation` rows with `book_id={book_id}` are automatically deleted (CASCADE)
**And** this is enforced by the `ForeignKey("books.id", ondelete="CASCADE")` constraint on both `Note.book_id` and `Annotation.book_id`

#### AC-005.23: Color Palette

**Given** the system accepts a `color` field on both `NoteCreate` and `AnnotationCreate`
**Then** the valid color values are exactly: `yellow`, `green`, `blue`, `pink`, `orange`
**And** the validation is enforced by the Pydantic `pattern="^(yellow|green|blue|pink|orange)$"` constraint
**And** both `Note.color` and `Annotation.color` default to `"yellow"`
**And** the database column is `String(20), nullable=False, default="yellow"`

#### AC-005.24: Book ID Indexing

**Given** the `notes` and `annotations` tables each have an indexed `book_id` column
**When** queries filter by `book_id` (list notes, list annotations)
**Then** the database uses the index on `book_id` for efficient lookup
**And** the index is defined by `index=True` on the `MappedColumn`

#### AC-005.25: Service-Level Logging

**Given** the `ReaderService` creates or deletes a note or annotation
**When** `create_note` succeeds
**Then** the system logs at INFO level: `"Note created for book {book_id}, chapter {chapter_index}"`
**When** `delete_note` succeeds
**Then** the system logs at INFO level: `"Note {note_id} deleted"`
**When** `create_annotation` succeeds
**Then** the system logs at INFO level: `"Annotation created for book {book_id}, chapter {chapter_index}"`
**When** `delete_annotation` succeeds
**Then** the system logs at INFO level: `"Annotation {annotation_id} deleted"`

---

## API Contract

### Endpoints

| Method | Path | Request Body | Query Params | Response Type | Status Codes |
|--------|------|-------------|-------------|---------------|--------------|
| GET | `/api/books/{book_id}/notes` | — | — | `NotesResponse` | 200 |
| POST | `/api/books/{book_id}/notes` | `NoteCreate` | — | `NoteResponse` | 200, 422 |
| DELETE | `/api/notes/{note_id}` | — | — | `{ message: str }` | 200 |
| GET | `/api/books/{book_id}/annotations` | — | `chapter_index: int (optional)` | `AnnotationsResponse` | 200 |
| POST | `/api/books/{book_id}/annotations` | `AnnotationCreate` | — | `AnnotationResponse` | 200, 422 |
| DELETE | `/api/annotations/{annotation_id}` | — | — | `{ message: str }` | 200 |

### Data Models

#### SQL: `notes` table

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | `Integer` | PK, autoincrement |
| `book_id` | `Integer` | FK(`books.id`, CASCADE), NOT NULL, indexed |
| `chapter_index` | `Integer` | NOT NULL |
| `position_in_chapter` | `Integer` | default=0 |
| `quoted_text` | `Text` | nullable |
| `content` | `Text` | NOT NULL |
| `color` | `String(20)` | NOT NULL, default="yellow" |
| `created_at` | `DateTime` | NOT NULL, default=utcnow |
| `updated_at` | `DateTime` | NOT NULL, default=utcnow, onupdate=utcnow |

Relationship: `Note.book` -> `Book` (many-to-one)

#### SQL: `annotations` table

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | `Integer` | PK, autoincrement |
| `book_id` | `Integer` | FK(`books.id`, CASCADE), NOT NULL, indexed |
| `chapter_index` | `Integer` | NOT NULL |
| `start_position` | `Integer` | NOT NULL |
| `end_position` | `Integer` | NOT NULL |
| `text` | `Text` | NOT NULL |
| `color` | `String(20)` | NOT NULL, default="yellow" |
| `note` | `Text` | nullable |
| `created_at` | `DateTime` | NOT NULL, default=utcnow |

Relationship: `Annotation.book` -> `Book` (many-to-one)

#### Schema: `NoteCreate`

```python
class NoteCreate(NoteBase):
    chapter_index: int = Field(..., ge=0)
    position_in_chapter: int = Field(0, ge=0)
```

Where `NoteBase` defines:

```python
class NoteBase(BaseModel):
    content: str = Field(..., min_length=1)
    color: str = Field("yellow", pattern="^(yellow|green|blue|pink|orange)$")
    quoted_text: Optional[str] = Field(None)
```

#### Schema: `NoteResponse`

```python
class NoteResponse(NoteBase):
    id: int
    book_id: int
    chapter_index: int
    position_in_chapter: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

#### Schema: `NotesResponse`

```python
class NotesResponse(BaseModel):
    notes: list[NoteResponse]
```

#### Schema: `NoteUpdate` (defined but not wired to a route)

```python
class NoteUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1)
    color: Optional[str] = Field(None, pattern="^(yellow|green|blue|pink|orange)$")
```

#### Schema: `AnnotationCreate`

```python
class AnnotationCreate(AnnotationBase):
    chapter_index: int = Field(..., ge=0)
    start_position: int = Field(..., ge=0)
    end_position: int = Field(..., ge=0)
```

Where `AnnotationBase` defines:

```python
class AnnotationBase(BaseModel):
    text: str = Field(..., min_length=1)
    color: str = Field("yellow", pattern="^(yellow|green|blue|pink|orange)$")
    note: Optional[str] = Field(None)
```

#### Schema: `AnnotationResponse`

```python
class AnnotationResponse(AnnotationBase):
    id: int
    book_id: int
    chapter_index: int
    start_position: int
    end_position: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

#### Schema: `AnnotationsResponse`

```python
class AnnotationsResponse(BaseModel):
    annotations: list[AnnotationResponse]
```

#### Schema: `AnnotationUpdate` (defined but not wired to a route)

```python
class AnnotationUpdate(BaseModel):
    color: Optional[str] = Field(None, pattern="^(yellow|green|blue|pink|orange)$")
    note: Optional[str] = None
```

---

## Implementation Map

| Component | File | Key Functions |
|-----------|------|---------------|
| Routes | `app/routes/reader.py` | `list_notes`, `create_note`, `delete_note`, `list_annotations`, `create_annotation`, `delete_annotation` |
| Service | `app/services/reader_service.py` | `ReaderService.create_note`, `ReaderService.list_notes`, `ReaderService.delete_note`, `ReaderService.create_annotation`, `ReaderService.list_annotations`, `ReaderService.delete_annotation` |
| Models | `app/models.py` | `Note`, `Annotation` |
| Schemas | `app/schemas.py` | `NoteBase`, `NoteCreate`, `NoteUpdate`, `NoteResponse`, `NotesResponse`, `AnnotationBase`, `AnnotationCreate`, `AnnotationUpdate`, `AnnotationResponse`, `AnnotationsResponse` |
| Database | `app/database.py` | `Base`, `get_db` (AsyncSession provider) |
| Exceptions | `app/exceptions.py` | `ResourceNotFoundError` (available for future 404 handling on delete) |

---

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|-----------------|-----------|---------------|--------|
| AC-005.01 Create Note | — | — | GAP |
| AC-005.02 Create Note — Required Fields | — | — | GAP |
| AC-005.03 Create Note — Color Validation | — | — | GAP |
| AC-005.04 Create Note — Empty Content Rejected | — | — | GAP |
| AC-005.05 List Notes | — | — | GAP |
| AC-005.06 List Notes — Empty Result | — | — | GAP |
| AC-005.07 Delete Note | — | — | GAP |
| AC-005.08 Delete Note — Idempotent | — | — | GAP |
| AC-005.09 Note — Update Timestamp | — | — | GAP |
| AC-005.10 Note — Quoted Text | — | — | GAP |
| AC-005.11 Create Annotation | — | — | GAP |
| AC-005.12 Create Annotation — Required Fields | — | — | GAP |
| AC-005.13 Create Annotation — Color Validation | — | — | GAP |
| AC-005.14 Create Annotation — Empty Text Rejected | — | — | GAP |
| AC-005.15 List Annotations — All | — | — | GAP |
| AC-005.16 List Annotations — Filtered by Chapter | — | — | GAP |
| AC-005.17 List Annotations — Empty Result | — | — | GAP |
| AC-005.18 List Annotations — Chapter Filter No Matches | — | — | GAP |
| AC-005.19 Delete Annotation | — | — | GAP |
| AC-005.20 Delete Annotation — Idempotent | — | — | GAP |
| AC-005.21 Annotation — Attached Note | — | — | GAP |
| AC-005.22 Cascade Delete on Book Removal | — | — | GAP |
| AC-005.23 Color Palette | — | — | GAP |
| AC-005.24 Book ID Indexing | — | — | GAP |
| AC-005.25 Service-Level Logging | — | — | GAP |

---

## Dependencies

- **SPEC-002: Reader Interface** — Notes and annotations exist within the book and chapter context provided by the reader. The reader routes host the note/annotation endpoints alongside chapter content, TOC, and bookmark endpoints. Annotation highlight rendering in the reader UI is covered by AC-002.40 (Annotation Highlight Colors) and AC-002.41 (Selection Context Menu).

---

## Open Questions

- None
