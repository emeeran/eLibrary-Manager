"""SQLAlchemy models for eBook Manager."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Book(Base):
    """Represents an ebook in the library.

    Attributes:
        id: Primary key
        title: Book title
        author: Book author (optional)
        path: Filesystem path to ebook file
        cover_path: Path to extracted cover image
        format: File format (EPUB, PDF, etc.)
        total_chapters: Number of chapters in the book
        current_chapter: Reading progress (chapter index)
        progress: Reading progress percentage (0-100)
        is_favorite: User's favorite status
        is_recent: Recently read flag
        file_size: Size in bytes
        added_date: When the book was added to library
        last_read_date: Last time book was opened
        publisher: Book publisher
        publish_date: Publication date/year
        description: Book description/synopsis
        language: Book language
        isbn: ISBN identifier
        total_pages: Total pages (for PDFs) or estimated pages
        summaries: Related chapter summaries
    """

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    author: Mapped[Optional[str]] = mapped_column(String(300), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    cover_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="EPUB")

    # Reading Progress
    total_chapters: Mapped[int] = mapped_column(Integer, default=0)
    current_chapter: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    # User Flags
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_recent: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Metadata
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    added_date: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    last_read_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # Enhanced Metadata
    publisher: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    publish_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    isbn: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    storage_type: Mapped[str] = mapped_column(String(10), default="local")
    rating: Mapped[int] = mapped_column(Integer, default=0)  # 0=unrated, 1-5 stars

    # Relationships
    summaries: Mapped[list["ChapterSummary"]] = relationship(
        "ChapterSummary",
        back_populates="book",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    category_links: Mapped[list["BookCategory"]] = relationship(
        "BookCategory",
        back_populates="book",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index('ix_books_hidden_favorite', 'is_hidden', 'is_favorite'),
        Index('ix_books_format_hidden', 'format', 'is_hidden'),
        Index('ix_books_recent_hidden', 'is_recent', 'is_hidden'),
    )

    def __repr__(self) -> str:
        """String representation of Book."""
        return f"<Book(id={self.id}, title='{self.title}', author='{self.author}')>"


class ChapterSummary(Base):
    """AI-generated summary for a book chapter.

    Attributes:
        id: Primary key
        book_id: Foreign key to Book
        chapter_index: Zero-based chapter index
        chapter_title: Optional chapter title
        summary_text: Generated summary content
        provider: AI provider used (google/groq/ollama_cloud/ollama_local)
        created_at: When summary was generated
        book: Related Book object
    """

    __tablename__ = "chapter_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="google",
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="summaries")

    def __repr__(self) -> str:
        """String representation of ChapterSummary."""
        return (
            f"<ChapterSummary(id={self.id}, book_id={self.book_id}, "
            f"chapter_index={self.chapter_index}, provider='{self.provider}')>"
        )


class BookSummary(Base):
    """AI-generated comprehensive book summary.

    Attributes:
        id: Primary key
        book_id: Foreign key to Book
        summary_text: Generated summary content
        provider: AI provider used
        created_at: When summary was generated
    """

    __tablename__ = "book_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    def __repr__(self) -> str:
        """String representation of BookSummary."""
        return f"<BookSummary(id={self.id}, book_id={self.book_id}, provider='{self.provider}')>"


class Bookmark(Base):
    """User bookmark for a specific location in a book.

    Attributes:
        id: Primary key
        book_id: Foreign key to Book
        chapter_index: Chapter index
        position_in_chapter: Character position in chapter
        title: User-provided bookmark title (optional)
        notes: User notes for this bookmark (optional)
        created_at: When bookmark was created
        book: Related Book object
    """

    __tablename__ = "bookmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    position_in_chapter: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book")

    def __repr__(self) -> str:
        """String representation of Bookmark."""
        return f"<Bookmark(id={self.id}, book_id={self.book_id}, chapter={self.chapter_index})>"


class Note(Base):
    """User note attached to a specific location in a book.

    Attributes:
        id: Primary key
        book_id: Foreign key to Book
        chapter_index: Chapter index
        position_in_chapter: Character position in chapter
        content: Note content
        color: Note highlight color (optional)
        created_at: When note was created
        updated_at: When note was last updated
        book: Related Book object
    """

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    position_in_chapter: Mapped[int] = mapped_column(Integer, default=0)
    quoted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="yellow")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        onupdate=datetime.utcnow
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book")

    def __repr__(self) -> str:
        """String representation of Note."""
        return f"<Note(id={self.id}, book_id={self.book_id}, chapter={self.chapter_index})>"


class Annotation(Base):
    """Text highlight/annotation in a book.

    Attributes:
        id: Primary key
        book_id: Foreign key to Book
        chapter_index: Chapter index
        start_position: Character start position
        end_position: Character end position
        text: Annotated text content
        color: Highlight color
        note: Optional note attached to annotation
        created_at: When annotation was created
        book: Related Book object
    """

    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_position: Mapped[int] = mapped_column(Integer, nullable=False)
    end_position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="yellow")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book")

    def __repr__(self) -> str:
        """String representation of Annotation."""
        return f"<Annotation(id={self.id}, book_id={self.book_id}, chapter={self.chapter_index})>"


class Setting(Base):
    """Application setting stored as key-value pair.

    Attributes:
        id: Primary key
        key: Unique setting key
        value: Setting value as string
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<Setting(key='{self.key}', value='{self.value[:50]}')>"


class Category(Base):
    """User-defined category/tag for organizing books.

    Attributes:
        id: Primary key
        name: Unique category name
        color: Hex color code for display
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#8b5cf6")

    # Relationships
    book_links: Mapped[list["BookCategory"]] = relationship(
        "BookCategory",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name='{self.name}')>"


class BookCategory(Base):
    """Many-to-many relationship between books and categories.

    Attributes:
        book_id: Foreign key to Book
        category_id: Foreign key to Category
    """

    __tablename__ = "book_categories"

    book_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="category_links")
    category: Mapped["Category"] = relationship("Category", back_populates="book_links", lazy="selectin")

    __table_args__ = (
        Index("ix_book_categories_composite", "category_id", "book_id"),
    )

    def __repr__(self) -> str:
        return f"<BookCategory(book_id={self.book_id}, category_id={self.category_id})>"
