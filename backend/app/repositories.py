"""Repository pattern for database operations."""

from typing import Optional

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ResourceNotFoundError, ValidationError
from app.models import Book, BookSummary, ChapterSummary, Setting
from app.schemas import BookCreate, BookUpdate, ProgressUpdate


class BookRepository:
    """Repository for Book database operations.

    Provides a clean abstraction layer between business logic and database,
    following the Repository pattern for better testability and separation of concerns.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create(self, book_data: BookCreate) -> Book:
        """Create a new book record.

        Args:
            book_data: Book creation data

        Returns:
            Created Book instance

        Raises:
            ValidationError: If book with same path exists
        """
        # Check for duplicates
        existing = await self.get_by_path(book_data.path)
        if existing:
            raise ValidationError(
                "Book already exists",
                {"path": book_data.path}
            )

        book = Book(**book_data.model_dump(exclude={"subjects"}))
        self.session.add(book)
        await self.session.flush()
        await self.session.refresh(book)
        return book

    async def get_by_id(self, book_id: int) -> Optional[Book]:
        """Retrieve book by ID.

        Args:
            book_id: Book primary key

        Returns:
            Book instance or None
        """
        result = await self.session.execute(
            select(Book).where(Book.id == book_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_or_404(self, book_id: int) -> Book:
        """Retrieve book by ID or raise exception.

        Args:
            book_id: Book primary key

        Returns:
            Book instance

        Raises:
            ResourceNotFoundError: If book doesn't exist
        """
        book = await self.get_by_id(book_id)
        if not book:
            raise ResourceNotFoundError(
                f"Book with ID {book_id} not found",
                {"book_id": book_id}
            )
        return book

    async def get_by_path(self, path: str) -> Optional[Book]:
        """Retrieve book by file path.

        Args:
            path: File system path

        Returns:
            Book instance or None
        """
        result = await self.session.execute(
            select(Book).where(Book.path == path)
        )
        return result.scalar_one_or_none()

    def _build_list_query(
        self,
        favorite_only: bool = False,
        recent_only: bool = False,
        search: Optional[str] = None,
        format_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        category_id: Optional[int] = None,
        hidden_only: bool = False,
        show_hidden: bool = False,
        directory_filter: Optional[str] = None,
    ) -> tuple:
        """Build base query conditions for book listing.

        Returns:
            Tuple of (base_select_query, conditions_list)
        """
        query = select(Book)
        conditions = []
        if favorite_only:
            conditions.append(Book.is_favorite == True)
        if recent_only:
            conditions.append(Book.is_recent == True)
        if search:
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Book.title.ilike(search_pattern),
                    Book.author.ilike(search_pattern)
                )
            )
        if format_filter:
            conditions.append(Book.format == format_filter.upper())
        if source_filter:
            conditions.append(Book.storage_type == source_filter)
        if directory_filter:
            # Escape LIKE wildcards to prevent pattern injection
            safe_filter = directory_filter.replace("%", "\\%").replace("_", "\\_")
            conditions.append(Book.path.like(safe_filter + "/%"))
        if category_id is not None:
            from app.models import BookCategory
            query = query.join(
                BookCategory, Book.id == BookCategory.book_id
            ).where(BookCategory.category_id == category_id)

        # Hidden book filtering
        if hidden_only:
            conditions.append(Book.is_hidden == True)
        elif not show_hidden:
            conditions.append(Book.is_hidden == False)

        if conditions:
            query = query.where(and_(*conditions))
        return query

    async def list_with_count(
        self,
        skip: int = 0,
        limit: int = 100,
        favorite_only: bool = False,
        recent_only: bool = False,
        search: Optional[str] = None,
        format_filter: Optional[str] = None,
        sort_by: str = "added_date",
        sort_order: str = "desc",
        source_filter: Optional[str] = None,
        category_id: Optional[int] = None,
        hidden_only: bool = False,
        show_hidden: bool = False,
        directory_filter: Optional[str] = None,
    ) -> tuple[list[Book], int]:
        """List books with optional filters and sorting, returning total count.

        Uses a separate COUNT query followed by the data query for optimal
        performance (~100x faster than COUNT(*) OVER() window function).

        Returns:
            Tuple of (books_list, total_count)
        """
        query = self._build_list_query(
            favorite_only=favorite_only,
            recent_only=recent_only,
            search=search,
            format_filter=format_filter,
            source_filter=source_filter,
            category_id=category_id,
            hidden_only=hidden_only,
            show_hidden=show_hidden,
            directory_filter=directory_filter,
        )

        # Separate COUNT query — much faster than window function for large tables
        total = await self.count_filtered(
            favorite_only=favorite_only,
            recent_only=recent_only,
            search=search,
            format_filter=format_filter,
            source_filter=source_filter,
            category_id=category_id,
            hidden_only=hidden_only,
            show_hidden=show_hidden,
            directory_filter=directory_filter,
        )

        # Apply sorting and pagination (case-insensitive for text columns)
        sort_map = {
            "title": Book.title,
            "author": Book.author,
            "added_date": Book.added_date,
            "last_read": Book.last_read_date,
            "progress": Book.progress,
        }
        sort_col = sort_map.get(sort_by, Book.added_date)
        if sort_by in ("title", "author"):
            order_expr = func.lower(sort_col)
        else:
            order_expr = sort_col
        order_func = desc if sort_order == "desc" else asc
        query = query.order_by(order_func(order_expr)).offset(skip).limit(limit)

        result = await self.session.execute(query)
        books = list(result.scalars().all())
        return books, total

    async def count_filtered(
        self,
        favorite_only: bool = False,
        recent_only: bool = False,
        search: Optional[str] = None,
        format_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        category_id: Optional[int] = None,
        hidden_only: bool = False,
        show_hidden: bool = False,
        directory_filter: Optional[str] = None,
    ) -> int:
        """Count books matching filters."""
        query = self._build_list_query(
            favorite_only=favorite_only,
            recent_only=recent_only,
            search=search,
            format_filter=format_filter,
            source_filter=source_filter,
            category_id=category_id,
            hidden_only=hidden_only,
            show_hidden=show_hidden,
            directory_filter=directory_filter,
        )
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        return result.scalar() or 0

    async def update(self, book_id: int, update_data: BookUpdate) -> Book:
        """Update book metadata.

        Args:
            book_id: Book primary key
            update_data: Fields to update

        Returns:
            Updated Book instance

        Raises:
            ResourceNotFoundError: If book doesn't exist
        """
        book = await self.get_by_id_or_404(book_id)

        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(book, field, value)

        await self.session.flush()
        await self.session.refresh(book)
        return book

    async def update_progress(
        self,
        book_id: int,
        progress_data: ProgressUpdate
    ) -> Book:
        """Update reading progress.

        Args:
            book_id: Book primary key
            progress_data: Progress update data

        Returns:
            Updated Book instance
        """
        book = await self.get_by_id_or_404(book_id)
        book.current_chapter = progress_data.chapter_index
        book.progress = progress_data.progress
        await self.session.flush()
        return book

    async def delete(self, book_id: int) -> None:
        """Delete a book.

        Args:
            book_id: Book primary key

        Raises:
            ResourceNotFoundError: If book doesn't exist
        """
        book = await self.get_by_id_or_404(book_id)
        await self.session.delete(book)

    async def count(self) -> int:
        """Count total books.

        Returns:
            Total number of books
        """
        result = await self.session.execute(
            select(func.count(Book.id))
        )
        return result.scalar() or 0

    async def list_all(
        self,
        limit: int = 1000,
        offset: int = 0,
        show_hidden: bool = True,
    ) -> list[Book]:
        """Retrieve all books with pagination.

        Args:
            limit: Maximum number of books to return
            offset: Number of books to skip
            show_hidden: Whether to include hidden books

        Returns:
            List of Book instances
        """
        query = select(Book).order_by(Book.id)
        if not show_hidden:
            query = query.where(Book.is_hidden == False)
        query = query.offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class ChapterSummaryRepository:
    """Repository for ChapterSummary operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_cached_summary(
        self,
        book_id: int,
        chapter_index: int
    ) -> Optional[ChapterSummary]:
        """Retrieve cached summary for a chapter.

        Args:
            book_id: Book primary key
            chapter_index: Chapter index

        Returns:
            ChapterSummary instance or None
        """
        result = await self.session.execute(
            select(ChapterSummary).where(
                and_(
                    ChapterSummary.book_id == book_id,
                    ChapterSummary.chapter_index == chapter_index
                )
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        book_id: int,
        chapter_index: int,
        chapter_title: Optional[str],
        summary_text: str,
        provider: str = "google"
    ) -> ChapterSummary:
        """Create a new chapter summary.

        Args:
            book_id: Book primary key
            chapter_index: Chapter index
            chapter_title: Optional chapter title
            summary_text: Generated summary
            provider: AI provider used

        Returns:
            Created ChapterSummary instance
        """
        summary = ChapterSummary(
            book_id=book_id,
            chapter_index=chapter_index,
            chapter_title=chapter_title,
            summary_text=summary_text,
            provider=provider
        )
        self.session.add(summary)
        await self.session.flush()
        await self.session.refresh(summary)
        return summary

    async def get_by_book(self, book_id: int) -> list[ChapterSummary]:
        """Get all summaries for a book.

        Args:
            book_id: Book primary key

        Returns:
            List of ChapterSummary instances ordered by chapter
        """
        result = await self.session.execute(
            select(ChapterSummary)
            .where(ChapterSummary.book_id == book_id)
            .order_by(ChapterSummary.chapter_index)
        )
        return list(result.scalars().all())


class BookSummaryRepository:
    """Repository for BookSummary operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_by_book(self, book_id: int) -> Optional[BookSummary]:
        """Get book summary for a book.

        Args:
            book_id: Book primary key

        Returns:
            BookSummary instance or None
        """
        result = await self.session.execute(
            select(BookSummary).where(BookSummary.book_id == book_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        book_id: int,
        summary_text: str,
        provider: str = "google"
    ) -> BookSummary:
        """Create or update a book summary.

        Args:
            book_id: Book primary key
            summary_text: Generated summary
            provider: AI provider used

        Returns:
            Created or updated BookSummary instance
        """
        existing = await self.get_by_book(book_id)

        if existing:
            existing.summary_text = summary_text
            existing.provider = provider
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        summary = BookSummary(
            book_id=book_id,
            summary_text=summary_text,
            provider=provider
        )
        self.session.add(summary)
        await self.session.flush()
        await self.session.refresh(summary)
        return summary


class SettingsRepository:
    """Repository for application settings (key-value store)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str, default: str | None = None) -> str | None:
        """Get a setting value by key."""
        result = await self.session.execute(
            select(Setting).where(Setting.key == key)
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else default

    async def get_all(self) -> dict[str, str]:
        """Get all settings as a dictionary."""
        result = await self.session.execute(select(Setting))
        return {s.key: s.value for s in result.scalars().all()}

    async def set(self, key: str, value: str) -> None:
        """Set a setting value (upsert)."""
        result = await self.session.execute(
            select(Setting).where(Setting.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            self.session.add(Setting(key=key, value=value))
        await self.session.flush()

    async def set_many(self, settings: dict[str, str]) -> None:
        """Set multiple settings at once."""
        for key, value in settings.items():
            if value is not None:
                await self.set(key, str(value))

    async def delete(self, key: str) -> None:
        """Delete a setting by key."""
        result = await self.session.execute(
            select(Setting).where(Setting.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            await self.session.delete(setting)
