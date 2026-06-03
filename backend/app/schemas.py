"""Pydantic schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, Field


class BookBase(BaseModel):
    """Base schema for Book data."""

    title: str = Field(..., min_length=1, max_length=500, description="Book title")
    author: str | None = Field(None, max_length=300, description="Book author")
    format: str = Field(default="EPUB", pattern="^(EPUB|PDF|MOBI)$")


class BookCreate(BookBase):
    """Schema for creating a new book."""

    path: str = Field(..., min_length=1, max_length=1000)
    file_size: int = Field(..., ge=0)
    cover_path: str | None = Field(None, max_length=1000)
    publisher: str | None = Field(None, max_length=300)
    publish_date: str | None = Field(None, max_length=50)
    description: str | None = Field(None)
    language: str | None = Field(None, max_length=20)
    isbn: str | None = Field(None, max_length=30)
    total_pages: int = Field(default=0, ge=0)
    storage_type: str = Field(default="local", pattern="^(local|nas)$")
    subjects: list[str] = Field(default_factory=list, max_length=20, description="Subjects/tags from metadata")


class BookUpdate(BaseModel):
    """Schema for updating book metadata."""

    title: str | None = Field(None, min_length=1, max_length=500)
    author: str | None = Field(None, max_length=300)
    is_favorite: bool | None = None
    is_hidden: bool | None = None
    progress: float | None = Field(None, ge=0, le=100)
    current_chapter: int | None = Field(None, ge=0)
    rating: int | None = Field(None, ge=0, le=5)


class BookResponse(BookBase):
    """Schema for book response."""

    id: int
    path: str
    cover_path: str | None
    total_chapters: int
    current_chapter: int
    progress: float
    is_favorite: bool
    is_hidden: bool = False
    is_recent: bool
    file_size: int
    added_date: datetime
    last_read_date: datetime | None
    publisher: str | None = None
    publish_date: str | None = None
    description: str | None = None
    language: str | None = None
    isbn: str | None = None
    total_pages: int = 0
    storage_type: str = "local"
    rating: int = 0
    categories: list[str] = Field(default_factory=list, description="Category names")

    model_config = {"from_attributes": True}

    @staticmethod
    def from_book(book) -> "BookResponse":
        """Convert a Book ORM object to BookResponse, including categories."""
        from app.models import Book as BookModel

        resp = BookResponse.model_validate(book)
        if isinstance(book, BookModel) and hasattr(book, "category_links"):
            resp.categories = [
                link.category.name for link in book.category_links
                if link.category is not None
            ]
        return resp


# Backward-compatible alias
def book_to_response(book):
    """Convert a Book ORM object to BookResponse, including categories."""
    return BookResponse.from_book(book)


class BookListResponse(BaseModel):
    """Schema for paginated book list."""

    books: list[BookResponse]
    total: int
    page: int
    page_size: int
    counts: dict[str, int] | None = None  # Sidebar counts (all, recent, favorites, etc.)


class ProgressUpdate(BaseModel):
    """Schema for updating reading progress."""

    chapter_index: int = Field(..., ge=0)
    progress: float = Field(..., ge=0, le=100)



class DirectoryImportRequest(BaseModel):
    """Schema for directory import request."""

    path: str = Field(..., min_length=1, description="Absolute path to directory")


# ============================================
# BOOKMARK SCHEMAS
# ============================================

class BookmarkBase(BaseModel):
    """Base schema for Bookmark data."""

    title: str | None = Field(None, max_length=500, description="Bookmark title")
    notes: str | None = Field(None, description="Bookmark notes")


class BookmarkCreate(BookmarkBase):
    """Schema for creating a bookmark."""

    chapter_index: int = Field(..., ge=0, description="Chapter index")
    position_in_chapter: int = Field(0, ge=0, description="Character position in chapter")


class BookmarkResponse(BookmarkBase):
    """Schema for bookmark response."""

    id: int
    book_id: int
    chapter_index: int
    position_in_chapter: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BookmarksResponse(BaseModel):
    """Schema for bookmarks list response."""

    bookmarks: list[BookmarkResponse]


# ============================================
# NOTE SCHEMAS
# ============================================

class NoteBase(BaseModel):
    """Base schema for Note data."""

    content: str = Field(..., min_length=1, description="Note content")
    color: str = Field("yellow", pattern="^(yellow|green|blue|pink|orange)$")
    quoted_text: str | None = Field(None, description="Text being noted")


class NoteCreate(NoteBase):
    """Schema for creating a note."""

    chapter_index: int = Field(..., ge=0, description="Chapter index")
    position_in_chapter: int = Field(0, ge=0, description="Character position in chapter")


class NoteResponse(NoteBase):
    """Schema for note response."""

    id: int
    book_id: int
    chapter_index: int
    position_in_chapter: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotesResponse(BaseModel):
    """Schema for notes list response."""

    notes: list[NoteResponse]


# ============================================
# ANNOTATION SCHEMAS
# ============================================

class AnnotationBase(BaseModel):
    """Base schema for Annotation data."""

    text: str = Field(..., min_length=1, description="Annotated text")
    color: str = Field("yellow", pattern="^(yellow|green|blue|pink|orange)$")
    note: str | None = Field(None, description="Optional note attached to annotation")


class AnnotationCreate(AnnotationBase):
    """Schema for creating an annotation."""

    chapter_index: int = Field(..., ge=0, description="Chapter index")
    start_position: int = Field(..., ge=0, description="Start character position")
    end_position: int = Field(..., ge=0, description="End character position")


class AnnotationResponse(AnnotationBase):
    """Schema for annotation response."""

    id: int
    book_id: int
    chapter_index: int
    start_position: int
    end_position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AnnotationsResponse(BaseModel):
    """Schema for annotations list response."""

    annotations: list[AnnotationResponse]


# ============================================
# TABLE OF CONTENTS SCHEMAS
# ============================================

class TOCItem(BaseModel):
    """Schema for a table of contents item."""

    index: int = Field(..., description="Chapter index")
    title: str = Field(..., description="Chapter title")
    level: int = Field(1, ge=1, description="Nesting level (1 for top-level)")
    children: list["TOCItem"] = Field(default_factory=list, description="Child chapters")

    model_config = {"from_attributes": True}


class TOCResponse(BaseModel):
    """Schema for table of contents response."""

    items: list[TOCItem]
    total_chapters: int


# Update forward references for recursive TOCItem
TOCItem.model_rebuild()


# ============================================
# SETTINGS SCHEMAS
# ============================================

class SettingsCreate(BaseModel):
    """Schema for creating/updating settings."""

    library_path: str | None = Field(None, max_length=1000)
    auto_scan: bool | None = None
    watch_changes: bool | None = None
    page_layout: str | None = Field(None, pattern="^(single|double|continuous)$")
    text_align: str | None = Field(None, pattern="^(justify|left|center)$")
    font_size: int | None = Field(None, ge=8, le=200)
    font_family: str | None = Field(None, max_length=50)
    line_height: str | None = Field(None, max_length=10)
    theme: str | None = Field(None, max_length=30)
    tts_speed: str | None = Field(None, max_length=10)
    tts_pitch: float | None = Field(None, ge=0.5, le=2.0)
    ai_provider: str | None = Field(None, pattern="^(auto|google|groq|ollama)$")
    ai_api_key: str | None = Field(None, max_length=500)
    ollama_url: str | None = Field(None, max_length=500)
    auto_flip: bool | None = None
    flip_interval: int | None = Field(None, ge=5, le=300)
    summary_length: str | None = Field(None, pattern="^(short|medium|long)$")
    auto_summary: bool | None = None

    # NAS Settings
    nas_enabled: bool | None = None
    nas_host: str | None = Field(None, max_length=100)
    nas_share: str | None = Field(None, max_length=200)
    nas_mount_path: str | None = Field(None, max_length=500)
    nas_protocol: str | None = Field(None, pattern="^(smb|nfs)$")
    nas_username: str | None = Field(None, max_length=100)
    nas_password: str | None = Field(None, max_length=200)
    nas_auto_mount: bool | None = None


class SettingsResponse(BaseModel):
    """Schema for settings response."""

    library_path: str
    auto_scan: bool
    watch_changes: bool
    page_layout: str
    text_align: str
    font_size: int
    font_family: str
    line_height: str
    theme: str
    tts_speed: str
    tts_pitch: float
    ai_provider: str
    ollama_url: str | None = None
    auto_flip: bool
    flip_interval: int
    summary_length: str
    auto_summary: bool

    # NAS Settings (password excluded for security)
    nas_enabled: bool = False
    nas_host: str = ""
    nas_share: str = ""
    nas_mount_path: str = ""
    nas_protocol: str = "smb"
    nas_username: str = ""
    nas_auto_mount: bool = False


class AIConnectionTest(BaseModel):
    """Schema for AI connection test request."""

    provider: str = Field(..., pattern="^(auto|google|groq|ollama)$")
    api_key: str | None = None


# ============================================
# NAS SCHEMAS
# ============================================

class NASHealthResponse(BaseModel):
    """Schema for NAS health check response."""

    healthy: bool
    last_check: datetime | None = None
    mount_path: str
    details: str | None = None


# ============================================
# CATEGORY SCHEMAS
# ============================================

class CategoryCreate(BaseModel):
    """Schema for creating a category."""

    name: str = Field(..., min_length=1, max_length=100, description="Category name")
    color: str = Field("#8b5cf6", max_length=7, description="Hex color code")


class CategoryResponse(BaseModel):
    """Schema for category response."""

    id: int
    name: str
    color: str
    book_count: int = 0

    model_config = {"from_attributes": True}


class CategoryAssignRequest(BaseModel):
    """Schema for assigning categories to a book."""

    category_ids: list[int] = Field(..., description="List of category IDs to assign")


# ============================================
# MAINTENANCE SCHEMAS
# ============================================

class StaleBookItem(BaseModel):
    """A single stale book whose file is missing from disk."""

    id: int
    title: str
    author: str | None = None
    path: str
    format: str
    file_size: int


class StaleBooksResponse(BaseModel):
    """Paginated response for stale books detection."""

    stale_books: list[StaleBookItem]
    total_stale: int
    page: int
    page_size: int


class DuplicateBookItem(BaseModel):
    """One copy within a duplicate group."""

    id: int
    path: str
    format: str
    file_size: int
    file_exists: bool


class DuplicateGroup(BaseModel):
    """A group of books sharing the same title+author."""

    title: str
    author: str | None = None
    copies: list[DuplicateBookItem]
    recommended_keep_id: int
    recommended_keep_reason: str


class DuplicatesResponse(BaseModel):
    """Paginated response for duplicate detection."""

    duplicate_groups: list[DuplicateGroup]
    total_groups: int
    total_extra_copies: int
    page: int
    page_size: int


class OrphansReport(BaseModel):
    """Report of orphaned child records."""

    orphaned_bookmarks: int
    orphaned_notes: int
    orphaned_annotations: int
    orphaned_chapter_summaries: int
    orphaned_book_summaries: int
    orphaned_book_categories: int


class FKStatusResponse(BaseModel):
    """Foreign key enforcement status."""

    foreign_keys_enabled: bool
    message: str


class BulkDeleteResult(BaseModel):
    """Result of a bulk deletion operation."""

    dry_run: bool
    books_deleted: int
    chapter_summaries_deleted: int = 0
    book_summaries_deleted: int = 0
    bookmarks_deleted: int = 0
    notes_deleted: int = 0
    annotations_deleted: int = 0
    book_categories_deleted: int = 0
    errors: int = 0
    message: str = ""


class DuplicateDedupResult(BulkDeleteResult):
    """Result of dedup operation."""

    duplicate_groups_processed: int = 0
    books_kept: int = 0
    books_removed: int = 0


class OrphanDeleteResult(BaseModel):
    """Result of orphan cleanup."""

    dry_run: bool
    bookmarks_deleted: int = 0
    notes_deleted: int = 0
    annotations_deleted: int = 0
    chapter_summaries_deleted: int = 0
    book_summaries_deleted: int = 0
    book_categories_deleted: int = 0


class VacuumResult(BaseModel):
    """Result of VACUUM operation."""

    size_before_bytes: int
    size_after_bytes: int
    freed_bytes: int
    message: str


class MaintenanceSummary(BaseModel):
    """Dashboard summary of all maintenance metrics."""

    total_books: int
    stale_books_count: int
    duplicate_groups_count: int
    extra_copies_count: int
    orphaned_bookmarks: int
    orphaned_notes: int
    orphaned_annotations: int
    foreign_keys_enabled: bool
    db_size_bytes: int
