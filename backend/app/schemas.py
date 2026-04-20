"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BookBase(BaseModel):
    """Base schema for Book data."""

    title: str = Field(..., min_length=1, max_length=500, description="Book title")
    author: Optional[str] = Field(None, max_length=300, description="Book author")
    format: str = Field(default="EPUB", pattern="^(EPUB|PDF|MOBI)$")


class BookCreate(BookBase):
    """Schema for creating a new book."""

    path: str = Field(..., min_length=1, max_length=1000)
    file_size: int = Field(..., ge=0)
    cover_path: Optional[str] = Field(None, max_length=1000)
    publisher: Optional[str] = Field(None, max_length=300)
    publish_date: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None)
    language: Optional[str] = Field(None, max_length=20)
    isbn: Optional[str] = Field(None, max_length=30)
    total_pages: int = Field(default=0, ge=0)
    storage_type: str = Field(default="local", pattern="^(local|nas)$")
    subjects: list[str] = Field(default_factory=list, description="Subjects/tags from metadata")


class BookUpdate(BaseModel):
    """Schema for updating book metadata."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    author: Optional[str] = Field(None, max_length=300)
    is_favorite: Optional[bool] = None
    is_hidden: Optional[bool] = None
    progress: Optional[float] = Field(None, ge=0, le=100)
    current_chapter: Optional[int] = Field(None, ge=0)
    rating: Optional[int] = Field(None, ge=0, le=5)


class BookResponse(BookBase):
    """Schema for book response."""

    id: int
    path: str
    cover_path: Optional[str]
    total_chapters: int
    current_chapter: int
    progress: float
    is_favorite: bool
    is_hidden: bool = False
    is_recent: bool
    file_size: int
    added_date: datetime
    last_read_date: Optional[datetime]
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    isbn: Optional[str] = None
    total_pages: int = 0
    storage_type: str = "local"
    rating: int = 0
    categories: list[str] = Field(default_factory=list, description="Category names")

    model_config = {"from_attributes": True}


def book_to_response(book):
    """Convert a Book ORM object to BookResponse, including categories."""
    from app.models import Book as BookModel

    resp = BookResponse.model_validate(book)
    if isinstance(book, BookModel) and hasattr(book, "category_links"):
        resp.categories = [
            link.category.name for link in book.category_links
            if link.category is not None
        ]
    return resp


class BookListResponse(BaseModel):
    """Schema for paginated book list."""

    books: list[BookResponse]
    total: int
    page: int
    page_size: int
    counts: Optional[dict[str, int]] = None  # Sidebar counts (all, recent, favorites, etc.)


class ChapterSummaryBase(BaseModel):
    """Base schema for chapter summary."""

    chapter_index: int = Field(..., ge=0, description="Zero-based chapter index")
    chapter_title: Optional[str] = Field(None, max_length=500)
    summary_text: str = Field(..., min_length=1, description="Generated summary")


class ChapterSummaryCreate(ChapterSummaryBase):
    """Schema for creating a chapter summary."""

    book_id: int


class ChapterSummaryResponse(ChapterSummaryBase):
    """Schema for chapter summary response."""

    id: int
    book_id: int
    provider: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BookSummaryResponse(BaseModel):
    """Schema for book summary response."""

    id: int
    book_id: int
    summary_text: str
    provider: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProgressUpdate(BaseModel):
    """Schema for updating reading progress."""

    chapter_index: int = Field(..., ge=0)
    progress: float = Field(..., ge=0, le=100)


class LibraryStats(BaseModel):
    """Schema for library statistics."""

    total_books: int
    favorite_books: int
    recent_books: int
    total_size_bytes: int


class ErrorResponse(BaseModel):
    """Schema for error responses."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error context")


class AIProviderStatus(BaseModel):
    """Schema for AI provider status."""

    name: str
    available: bool
    model: str
    priority: int


class AIProvidersResponse(BaseModel):
    """Schema for AI providers list response."""

    providers: list[AIProviderStatus]
    active_provider: str
    default_provider: str


class DirectoryImportRequest(BaseModel):
    """Schema for directory import request."""

    path: str = Field(..., min_length=1, description="Absolute path to directory")


# ============================================
# BOOKMARK SCHEMAS
# ============================================

class BookmarkBase(BaseModel):
    """Base schema for Bookmark data."""

    title: Optional[str] = Field(None, max_length=500, description="Bookmark title")
    notes: Optional[str] = Field(None, description="Bookmark notes")


class BookmarkCreate(BookmarkBase):
    """Schema for creating a bookmark."""

    chapter_index: int = Field(..., ge=0, description="Chapter index")
    position_in_chapter: int = Field(0, ge=0, description="Character position in chapter")


class BookmarkUpdate(BaseModel):
    """Schema for updating a bookmark."""

    title: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


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
    quoted_text: Optional[str] = Field(None, description="Text being noted")


class NoteCreate(NoteBase):
    """Schema for creating a note."""

    chapter_index: int = Field(..., ge=0, description="Chapter index")
    position_in_chapter: int = Field(0, ge=0, description="Character position in chapter")


class NoteUpdate(BaseModel):
    """Schema for updating a note."""

    content: Optional[str] = Field(None, min_length=1)
    color: Optional[str] = Field(None, pattern="^(yellow|green|blue|pink|orange)$")


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
    note: Optional[str] = Field(None, description="Optional note attached to annotation")


class AnnotationCreate(AnnotationBase):
    """Schema for creating an annotation."""

    chapter_index: int = Field(..., ge=0, description="Chapter index")
    start_position: int = Field(..., ge=0, description="Start character position")
    end_position: int = Field(..., ge=0, description="End character position")


class AnnotationUpdate(BaseModel):
    """Schema for updating an annotation."""

    color: Optional[str] = Field(None, pattern="^(yellow|green|blue|pink|orange)$")
    note: Optional[str] = None


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

    library_path: Optional[str] = Field(None, max_length=1000)
    auto_scan: Optional[bool] = None
    watch_changes: Optional[bool] = None
    page_layout: Optional[str] = Field(None, pattern="^(single|double|continuous)$")
    text_align: Optional[str] = Field(None, pattern="^(justify|left|center)$")
    font_size: Optional[int] = Field(None, ge=8, le=200)
    font_family: Optional[str] = Field(None, max_length=50)
    line_height: Optional[str] = Field(None, max_length=10)
    theme: Optional[str] = Field(None, max_length=30)
    tts_speed: Optional[str] = Field(None, max_length=10)
    tts_pitch: Optional[float] = Field(None, ge=0.5, le=2.0)
    ai_provider: Optional[str] = Field(None, pattern="^(auto|google|groq|ollama)$")
    ai_api_key: Optional[str] = Field(None, max_length=500)
    ollama_url: Optional[str] = Field(None, max_length=500)
    auto_flip: Optional[bool] = None
    flip_interval: Optional[int] = Field(None, ge=5, le=300)
    summary_length: Optional[str] = Field(None, pattern="^(short|medium|long)$")
    auto_summary: Optional[bool] = None

    # NAS Settings
    nas_enabled: Optional[bool] = None
    nas_host: Optional[str] = Field(None, max_length=100)
    nas_share: Optional[str] = Field(None, max_length=200)
    nas_mount_path: Optional[str] = Field(None, max_length=500)
    nas_protocol: Optional[str] = Field(None, pattern="^(smb|nfs)$")
    nas_username: Optional[str] = Field(None, max_length=100)
    nas_password: Optional[str] = Field(None, max_length=200)
    nas_auto_mount: Optional[bool] = None


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
    ollama_url: Optional[str] = None
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
    api_key: Optional[str] = None


# ============================================
# NAS SCHEMAS
# ============================================

class NASHealthResponse(BaseModel):
    """Schema for NAS health check response."""

    healthy: bool
    last_check: Optional[datetime] = None
    mount_path: str
    details: Optional[str] = None


class NASCacheStatusResponse(BaseModel):
    """Schema for NAS cache status response."""

    cached_books: int
    total_cache_size_bytes: int
    max_cache_size_bytes: int
    books: list[dict]  # [{"book_id": int, "title": str, "size_bytes": int}]


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
