"""Repository pattern for database operations."""

import os
import re
import time
from datetime import UTC, datetime

from sqlalchemy import and_, asc, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.exceptions import ResourceNotFoundError, ValidationError
from app.models import (
    Book,
    BookCategory,
    BookContent,
    BookSummary,
    Category,
    ChapterSummary,
    Setting,
)
from app.schemas import BookCreate, BookUpdate, ProgressUpdate

_COUNT_CACHE_TTL = 10.0  # seconds


def _build_fts_query(search: str) -> str | None:
    """Build a safe FTS5 prefix query for the given search string.

    Each whitespace-delimited token is double-quoted (so FTS5 operators in the
    user input are treated as literals) and given the ``*`` prefix flag for
    type-ahead matching. Returns None if the input has no usable tokens. Whether
    the FTS index exists is checked separately per-session (see
    :meth:`BookRepository._fts_available`) because tests use an in-memory DB
    where the migration (and thus ``books_fts``) is absent.
    """
    tokens = [t for t in re.split(r"\s+", search.strip()) if t]
    if not tokens:
        return None
    return " ".join(f'"{t.replace(chr(34), "")}"*' for t in tokens)


# Advanced search syntax (spec 012): ``field:term`` tokens map to a Book column
# and become an ANDed ilike predicate; the remaining bare tokens go through the
# normal ilike + FTS path. ``tag:`` is handled by the existing category facet.
_FIELD_SEARCH_RE = re.compile(r"^(author|title|series|isbn):(.+)$", re.IGNORECASE)


def _parse_search(search: str | None) -> tuple[str | None, list]:
    """Split ``search`` into ``(bare_terms, field_predicates)``.

    ``author:/title:/series:/isbn:`` tokens become ``ilike('%value%')``
    predicates on the matching column (ANDed into the query). Remaining tokens
    are returned as a whitespace-joined string for the ilike + FTS path. Phrases
    aren't specially handled (consistent with ``_build_fts_query``).
    """
    if not search:
        return None, []
    field_columns = {
        "author": Book.author,
        "title": Book.title,
        "series": Book.series,
        "isbn": Book.isbn,
    }
    bare: list[str] = []
    preds: list = []
    for tok in re.split(r"\s+", search.strip()):
        if not tok:
            continue
        m = _FIELD_SEARCH_RE.match(tok)
        if m:
            col = field_columns.get(m.group(1).lower())
            value = m.group(2)
            if col is not None and value:
                preds.append(col.ilike(f"%{value}%"))
            continue
        bare.append(tok)
    return (" ".join(bare) if bare else None), preds


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
        self._count_cache: dict[str, tuple[int, float]] = {}
        self._fts_available_cache: bool | None = None

    async def _fts_available(self) -> bool:
        """Return True if the books_fts virtual table exists on this database.

        Checked against the bound session (not a hardcoded path) so it works
        in tests that use an in-memory DB. Cached per-instance.
        """
        if self._fts_available_cache is None:
            try:
                result = await self.session.execute(
                    __import__("sqlalchemy").text(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='books_fts'"
                    )
                )
                self._fts_available_cache = result.scalar() is not None
            except Exception:
                self._fts_available_cache = False
        return self._fts_available_cache

    async def _content_fts_available(self) -> bool:
        """Return True if the books_content_fts virtual table exists on this DB."""
        try:
            result = await self.session.execute(
                __import__("sqlalchemy").text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='books_content_fts'"
                )
            )
            return result.scalar() is not None
        except Exception:
            return False

    def _build_fts_predicate(self, fts_match: str, content_available: bool):
        """Build the FTS match predicate: ``(id IN meta_fts) [OR (id IN content_fts)]``.

        Two separate ``IN`` clauses joined by ``OR`` (rather than a SQL ``UNION``)
        sidesteps bind-param name collisions across a compound select. Both FTS
        tables are matched with the same term.
        """
        from sqlalchemy import column, text

        meta = Book.id.in_(
            select(column("rowid"))
            .select_from(text("books_fts"))
            .where(text("books_fts MATCH :fts_q").bindparams(fts_q=fts_match))
        )
        if not content_available:
            return meta
        content = Book.id.in_(
            select(column("book_id"))
            .select_from(text("books_content_fts"))
            .where(text("books_content_fts MATCH :fts_q").bindparams(fts_q=fts_match))
        )
        return or_(meta, content)

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
            raise ValidationError("Book already exists", {"path": book_data.path})

        book = Book(**book_data.model_dump(exclude={"subjects"}))
        self.session.add(book)
        await self.session.flush()
        await self.session.refresh(book)
        return book

    async def get_by_id(self, book_id: int) -> Book | None:
        """Retrieve book by ID.

        Args:
            book_id: Book primary key

        Returns:
            Book instance or None
        """
        result = await self.session.execute(select(Book).where(Book.id == book_id))
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
            raise ResourceNotFoundError(f"Book with ID {book_id} not found", {"book_id": book_id})
        return book

    async def get_by_path(self, path: str) -> Book | None:
        """Retrieve book by file path.

        Args:
            path: File system path

        Returns:
            Book instance or None
        """
        result = await self.session.execute(select(Book).where(Book.path == path))
        return result.scalar_one_or_none()

    def _build_list_query(
        self,
        favorite_only: bool = False,
        recent_only: bool = False,
        reading_only: bool = False,
        search: str | None = None,
        format_filter: str | None = None,
        source_filter: str | None = None,
        category_id: int | None = None,
        hidden_only: bool = False,
        show_hidden: bool = False,
        directory_filter: str | None = None,
        series_filter: list[str] | None = None,
        rating_min: int | None = None,
        show_deleted: bool = False,
    ) -> tuple:
        """Build base query conditions for book listing.

        Returns:
            Tuple of (base_select_query, conditions_list)
        """
        # Skip eager-loading of category_links for list queries —
        # categories are batch-fetched separately via get_categories_for_books.
        query = select(Book).options(noload(Book.category_links))
        conditions = []
        if favorite_only:
            conditions.append(Book.is_favorite)
        if recent_only:
            conditions.append(Book.is_recent)
        if reading_only:
            conditions.append(Book.progress > 0)
        if format_filter:
            conditions.append(Book.format == format_filter.upper())
        if series_filter:
            # Multi-select series facet (spec 012).
            conditions.append(Book.series.in_(series_filter))
        if rating_min:
            conditions.append(Book.rating >= rating_min)
        if source_filter:
            conditions.append(Book.storage_type == source_filter)
        if directory_filter:
            # Escape LIKE wildcards to prevent pattern injection
            safe_filter = directory_filter.replace("%", "\\%").replace("_", "\\_")
            conditions.append(Book.path.like(safe_filter + "/%", escape="\\"))
        if category_id is not None:
            from app.models import BookCategory

            query = query.join(BookCategory, Book.id == BookCategory.book_id).where(
                BookCategory.category_id == category_id
            )

        # Hidden book filtering
        if hidden_only:
            conditions.append(Book.is_hidden)
        elif not show_hidden:
            conditions.append(Book.is_hidden.is_(False))

        # Soft-deleted books (pruned from a linked Calibre library) are excluded
        # from normal views unless explicitly requested (spec 011 v1.2).
        if not show_deleted:
            conditions.append(Book.is_deleted.is_(False))

        if conditions:
            query = query.where(and_(*conditions))

        # The search predicate is returned separately (not ANDed in) so callers
        # can OR it with FTS5 matches — a content-only hit (body text, not
        # title/author) must still surface the book. See list_with_count.
        search_ilike: ... = None
        if search:
            search_pattern = f"%{search}%"
            search_ilike = or_(
                Book.title.ilike(search_pattern), Book.author.ilike(search_pattern)
            )
        return query, search_ilike

    async def list_with_count(
        self,
        skip: int = 0,
        limit: int = 100,
        favorite_only: bool = False,
        recent_only: bool = False,
        reading_only: bool = False,
        search: str | None = None,
        format_filter: str | None = None,
        sort_by: str = "added_date",
        sort_order: str = "desc",
        source_filter: str | None = None,
        category_id: int | None = None,
        hidden_only: bool = False,
        show_hidden: bool = False,
        directory_filter: str | None = None,
        series_filter: list[str] | None = None,
        rating_min: int | None = None,
    ) -> tuple[list[Book], int]:
        """List books with optional filters and sorting, returning total count.

        Uses a separate COUNT query followed by the data query for optimal
        performance (~100x faster than COUNT(*) OVER() window function).

        Returns:
            Tuple of (books_list, total_count)
        """
        # Parse advanced ``field:term`` syntax (spec 012): field tokens become
        # ANDed ilike predicates; bare terms drive the ilike + FTS path.
        bare_search, field_preds = _parse_search(search)
        query, search_ilike = self._build_list_query(
            favorite_only=favorite_only,
            recent_only=recent_only,
            reading_only=reading_only,
            search=bare_search,
            format_filter=format_filter,
            source_filter=source_filter,
            category_id=category_id,
            hidden_only=hidden_only,
            show_hidden=show_hidden,
            directory_filter=directory_filter,
            series_filter=series_filter,
            rating_min=rating_min,
        )
        for pred in field_preds:
            query = query.where(pred)
        # Build the search predicate: (title/author ilike) OR (metadata FTS) OR
        # (content FTS). Content-only hits (body text) must still surface the
        # book, so FTS is OR'd with — not AND'd against — the ilike clause.
        search_predicate = search_ilike
        if bare_search:
            fts_match = _build_fts_query(bare_search)
            if fts_match is not None and await self._fts_available():
                content_available = await self._content_fts_available()
                fts_pred = self._build_fts_predicate(fts_match, content_available)
                search_predicate = (
                    fts_pred if search_predicate is None else or_(search_predicate, fts_pred)
                )
        if search_predicate is not None:
            query = query.where(search_predicate)

        # Separate COUNT query — much faster than window function for large tables
        total = await self.count_filtered(
            favorite_only=favorite_only,
            recent_only=recent_only,
            reading_only=reading_only,
            search=search,
            format_filter=format_filter,
            source_filter=source_filter,
            category_id=category_id,
            hidden_only=hidden_only,
            show_hidden=show_hidden,
            directory_filter=directory_filter,
            series_filter=series_filter,
            rating_min=rating_min,
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
        reading_only: bool = False,
        search: str | None = None,
        format_filter: str | None = None,
        source_filter: str | None = None,
        category_id: int | None = None,
        hidden_only: bool = False,
        show_hidden: bool = False,
        directory_filter: str | None = None,
        series_filter: list[str] | None = None,
        rating_min: int | None = None,
    ) -> int:
        """Count books matching filters, with short-lived cache for pagination."""
        cache_key = (
            f"{favorite_only}|{recent_only}|{reading_only}|{search}|{format_filter}|"
            f"{source_filter}|{category_id}|{hidden_only}|{show_hidden}|"
            f"{directory_filter}|{series_filter}|{rating_min}"
        )

        now = time.time()
        if cache_key in self._count_cache:
            cached_count, cached_time = self._count_cache[cache_key]
            if now - cached_time < _COUNT_CACHE_TTL:
                return cached_count

        bare_search, field_preds = _parse_search(search)
        query, search_ilike = self._build_list_query(
            favorite_only=favorite_only,
            recent_only=recent_only,
            reading_only=reading_only,
            search=bare_search,
            format_filter=format_filter,
            source_filter=source_filter,
            category_id=category_id,
            hidden_only=hidden_only,
            show_hidden=show_hidden,
            directory_filter=directory_filter,
            series_filter=series_filter,
            rating_min=rating_min,
        )
        for pred in field_preds:
            query = query.where(pred)
        # Mirror list_with_count's search predicate so the count matches exactly.
        search_predicate = search_ilike
        if bare_search:
            fts_match = _build_fts_query(bare_search)
            if fts_match is not None and await self._fts_available():
                content_available = await self._content_fts_available()
                fts_pred = self._build_fts_predicate(fts_match, content_available)
                search_predicate = (
                    fts_pred if search_predicate is None else or_(search_predicate, fts_pred)
                )
        if search_predicate is not None:
            query = query.where(search_predicate)
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        count = result.scalar() or 0

        self._count_cache[cache_key] = (count, now)
        # Evict stale entries
        if len(self._count_cache) > 50:
            stale = [k for k, (_, t) in self._count_cache.items() if now - t >= _COUNT_CACHE_TTL]
            for k in stale:
                del self._count_cache[k]

        return count

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

    async def update_progress(self, book_id: int, progress_data: ProgressUpdate) -> Book:
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
        result = await self.session.execute(select(func.count(Book.id)))
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
            query = query.where(Book.is_hidden.is_(False))
        query = query.offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_all_paths(self) -> dict[str, int]:
        """Load all book paths with their IDs for stale-file detection.

        Returns:
            Dict mapping path -> book_id
        """
        result = await self.session.execute(select(Book.id, Book.path))
        return {row.path: row.id for row in result.all()}

    async def get_stale_book_ids(self) -> list[int]:
        """Find IDs of books whose files no longer exist on disk.

        Runs the filesystem checks in a thread to avoid blocking the
        event loop. More efficient than get_all_paths + manual filtering
        for the common stale-detection use case.

        Returns:
            List of book IDs with missing files.
        """
        import asyncio

        result = await self.session.execute(select(Book.id, Book.path))
        rows = result.all()

        def _check(rows: list) -> list[int]:
            return [row.id for row in rows if not os.path.exists(row.path)]

        return await asyncio.to_thread(_check, rows)

    async def find_duplicate_groups(self) -> list[dict]:
        """Find groups of books with the same lower(title)+lower(author).

        Returns rows with: norm_title, norm_author, ids (list), cnt.
        """
        result = await self.session.execute(
            select(
                func.lower(Book.title).label("norm_title"),
                func.lower(func.coalesce(Book.author, "")).label("norm_author"),
                func.group_concat(Book.id).label("ids"),
                func.count(Book.id).label("cnt"),
            )
            .group_by("norm_title", "norm_author")
            .having(func.count(Book.id) > 1)
            .order_by(func.count(Book.id).desc())
        )
        groups = []
        for row in result.all():
            ids = [int(x) for x in row.ids.split(",")]
            groups.append(
                {
                    "title": row.norm_title,
                    "author": row.norm_author,
                    "ids": ids,
                    "count": row.cnt,
                }
            )
        return groups

    async def get_categories_for_books(self, book_ids: list[int]) -> dict[int, list[str]]:
        """Batch-fetch category names for multiple books in a single query.

        Args:
            book_ids: List of book IDs.

        Returns:
            Dict mapping book_id -> list of category names.
        """
        if not book_ids:
            return {}
        result = await self.session.execute(
            select(BookCategory.book_id, Category.name)
            .join(Category, BookCategory.category_id == Category.id)
            .where(BookCategory.book_id.in_(book_ids))
        )
        categories_map: dict[int, list[str]] = {bid: [] for bid in book_ids}
        for book_id, cat_name in result.all():
            categories_map.setdefault(book_id, []).append(cat_name)
        return categories_map

    async def get_books_by_ids(self, ids: list[int]) -> list[Book]:
        """Load multiple books by ID for batch inspection."""
        if not ids:
            return []
        result = await self.session.execute(select(Book).where(Book.id.in_(ids)))
        return list(result.scalars().all())


class BookContentRepository:
    """Repository for the content-extraction index (spec 012).

    Tracks per-book extraction status in ``book_contents`` and the extracted
    text in the ``books_content_fts`` FTS5 virtual table. FTS rows are managed
    with raw SQL (virtual tables aren't first-class ORM mappings).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def seed_missing(self) -> int:
        """Insert ``pending`` rows for books not yet tracked. Returns count seeded."""
        result = await self.session.execute(
            text(
                "INSERT INTO book_contents(book_id, extract_status) "
                "SELECT b.id, 'pending' FROM books b "
                "LEFT JOIN book_contents bc ON bc.book_id = b.id "
                "WHERE bc.book_id IS NULL"
            )
        )
        await self.session.commit()
        return result.rowcount or 0

    async def pending_batch(self, limit: int = 50) -> list[tuple[int, str, str]]:
        """Return up to ``limit`` pending books as (book_id, path, format)."""
        rows = (
            await self.session.execute(
                select(Book.id, Book.path, Book.format)
                .join(BookContent, BookContent.book_id == Book.id)
                .where(BookContent.extract_status == "pending")
                .order_by(Book.id)
                .limit(limit)
            )
        ).all()
        return [(r[0], r[1], r[2]) for r in rows]

    async def mark_status(self, book_id: int, status: str) -> None:
        """Set a book's extraction status (and clear any stale FTS row on non-success)."""
        existing = await self.session.get(BookContent, book_id)
        if existing:
            existing.extract_status = status
        else:
            self.session.add(BookContent(book_id=book_id, extract_status=status))
        if status in ("empty", "failed"):
            await self.session.execute(
                text("DELETE FROM books_content_fts WHERE book_id = :bid"), {"bid": book_id}
            )

    async def upsert_extracted(
        self, book_id: int, content_text: str, char_count: int, source_mtime: float | None
    ) -> None:
        """Store extracted text in the FTS table and mark the book extracted."""
        now = datetime.now(UTC)
        # Replace any existing FTS row for this book, then insert the new content.
        await self.session.execute(
            text("DELETE FROM books_content_fts WHERE book_id = :bid"), {"bid": book_id}
        )
        await self.session.execute(
            text("INSERT INTO books_content_fts(book_id, content) VALUES (:bid, :content)"),
            {"bid": book_id, "content": content_text},
        )
        existing = await self.session.get(BookContent, book_id)
        if existing:
            existing.extract_status = "extracted"
            existing.char_count = char_count
            existing.source_mtime = source_mtime
            existing.extracted_at = now
        else:
            self.session.add(
                BookContent(
                    book_id=book_id,
                    extract_status="extracted",
                    char_count=char_count,
                    source_mtime=source_mtime,
                    extracted_at=now,
                )
            )

    async def status_counts(self) -> dict[str, int]:
        """Return {extract_status: count} for progress reporting."""
        rows = (
            await self.session.execute(
                select(BookContent.extract_status, func.count(BookContent.book_id)).group_by(
                    BookContent.extract_status
                )
            )
        ).all()
        return {r[0]: int(r[1]) for r in rows}

    async def snippets_for(self, book_ids: list[int], fts_match: str) -> dict[int, str]:
        """Return ``{book_id: context_snippet}`` for content-FTS matches.

        Uses FTS5 ``snippet()`` over the ``content`` column (index 1). Returns
        ``{}`` if there's nothing to query (no ids/term) or if the content FTS
        table isn't present (e.g. in-memory test DB) — never raises.
        """
        if not book_ids or not fts_match:
            return {}
        try:
            from sqlalchemy import bindparam

            rows = (
                await self.session.execute(
                    text(
                        "SELECT book_id, snippet(books_content_fts, 1, "
                        "'<mark>', '</mark>', ' … ', 12) "
                        "FROM books_content_fts "
                        "WHERE books_content_fts MATCH :q AND book_id IN :ids"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"q": fts_match, "ids": list(book_ids)},
                )
            ).all()
        except Exception:  # noqa: BLE001 — table missing / no fts5 → no snippets
            return {}
        return {int(r[0]): r[1] for r in rows if r[1]}


class ChapterSummaryRepository:
    """Repository for ChapterSummary operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_cached_summary(self, book_id: int, chapter_index: int) -> ChapterSummary | None:
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
                    ChapterSummary.book_id == book_id, ChapterSummary.chapter_index == chapter_index
                )
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        book_id: int,
        chapter_index: int,
        chapter_title: str | None,
        summary_text: str,
        provider: str = "google",
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
            provider=provider,
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

    async def get_by_book(self, book_id: int) -> BookSummary | None:
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
        self, book_id: int, summary_text: str, provider: str = "google"
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

        summary = BookSummary(book_id=book_id, summary_text=summary_text, provider=provider)
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
        result = await self.session.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        return setting.value if setting else default

    async def get_all(self) -> dict[str, str]:
        """Get all settings as a dictionary."""
        result = await self.session.execute(select(Setting))
        return {s.key: s.value for s in result.scalars().all()}

    async def set(self, key: str, value: str) -> None:
        """Set a setting value (upsert)."""
        result = await self.session.execute(select(Setting).where(Setting.key == key))
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
        """Delete a setting by key.

        Uses a bulk ``DELETE`` statement (Core) rather than ``session.delete()``
        (ORM unit-of-work). The ORM path requires a flush to schedule the row
        deletion and was observed not to persist through some request
        lifecycles; the Core path issues the ``DELETE`` immediately on the
        current transaction so the subsequent commit reliably lands it.
        """
        from sqlalchemy import delete as sa_delete

        await self.session.execute(sa_delete(Setting).where(Setting.key == key))
