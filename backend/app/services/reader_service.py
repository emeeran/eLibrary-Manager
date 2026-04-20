"""Reader service for reading, progress tracking, and annotations.

Coordinates between repositories, scanner, AI engine, and reader functionality.
"""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_engine import get_ai_orchestrator
from app.exceptions import ResourceNotFoundError
from app.logging_config import get_logger
from app.models import Annotation, Book, Bookmark, ChapterSummary, Note
from app.repositories import BookRepository, BookSummaryRepository, ChapterSummaryRepository
from app.scanner import LibraryScanner
from app.schemas import ProgressUpdate

logger = get_logger(__name__)


class ReaderService:
    """Service for reading and progress tracking.

    Coordinates between repositories, scanner, AI engine,
    and reader functionality.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            session: Database session
        """
        self.session = session
        self.book_repo = BookRepository(session)
        self.summary_repo = ChapterSummaryRepository(session)
        self.book_summary_repo = BookSummaryRepository(session)
        self.scanner = LibraryScanner()

    async def get_chapter_content(
        self,
        book_id: int,
        chapter_index: int
    ) -> tuple[str, str, int]:
        """Get chapter content and metadata.

        On first access of a fast-indexed book, enriches the DB record
        with full metadata and cover extracted from the file.

        Args:
            book_id: Book primary key
            chapter_index: Chapter index

        Returns:
            Tuple of (content, title, total_chapters)

        Raises:
            ResourceNotFoundError: If book or chapter not found
        """
        from app.reader_engine import ReaderEngine

        book = await self.book_repo.get_by_id_or_404(book_id)
        reader = ReaderEngine()

        # Enrich fast-indexed books on first open
        if not book.total_chapters or book.total_chapters <= 0:
            await self._enrich_book_metadata(book)

        content, title, total = await reader.get_chapter_content(
            book.path,
            chapter_index
        )

        # Update stored total_chapters if it was 0
        if book.total_chapters != total and total > 0:
            book.total_chapters = total
        book.last_read_date = datetime.utcnow()
        await self.session.flush()

        return content, title, total

    async def _enrich_book_metadata(self, book: Book) -> None:
        """Enrich a fast-indexed book with full metadata and cover.

        Args:
            book: Book ORM instance to enrich.
        """
        try:
            metadata = await self.scanner.extract_metadata(book.path)
            book.title = metadata.title or book.title
            book.author = metadata.author if metadata.author != "Unknown" else book.author
            book.total_pages = metadata.total_pages or book.total_pages
            book.publisher = metadata.publisher or book.publisher
            book.publish_date = metadata.publish_date or book.publish_date
            book.description = metadata.description or book.description
            book.language = metadata.language or book.language
            book.isbn = metadata.isbn or book.isbn
            book.file_size = metadata.file_size or book.file_size

            cover_path = await self.scanner.extract_cover(book.path)
            if cover_path:
                book.cover_path = cover_path

            await self.session.flush()
            logger.info(f"Enriched metadata for: {book.title}")
        except Exception as e:
            logger.warning(f"Failed to enrich metadata for {book.path}: {e}")

    async def update_progress(
        self,
        book_id: int,
        progress_data: ProgressUpdate
    ) -> Book:
        """Update reading progress.

        Args:
            book_id: Book primary key
            progress_data: Progress data

        Returns:
            Updated Book instance
        """
        book = await self.book_repo.update_progress(book_id, progress_data)

        if progress_data.progress > 0:
            book.is_recent = True

        await self.session.flush()
        return book

    async def get_chapter_summary(
        self,
        book_id: int,
        chapter_index: int,
        force_refresh: bool = False
    ) -> ChapterSummary:
        """Get chapter summary with AI generation if needed.

        Args:
            book_id: Book primary key
            chapter_index: Chapter index
            force_refresh: Force regeneration even if cached

        Returns:
            ChapterSummary instance

        Raises:
            ResourceNotFoundError: If book not found
        """
        book = await self.book_repo.get_by_id_or_404(book_id)

        if not force_refresh:
            cached = await self.summary_repo.get_cached_summary(
                book_id, chapter_index
            )
            if cached:
                logger.debug(
                    f"Using cached summary for book {book_id}, "
                    f"chapter {chapter_index}"
                )
                return cached

        from app.reader_engine import ReaderEngine

        reader = ReaderEngine()
        chapters = await reader.get_all_chapters(book.path)

        if chapter_index >= len(chapters):
            raise ResourceNotFoundError(
                f"Chapter {chapter_index} not found",
                {"book_id": book_id, "chapter_index": chapter_index}
            )

        _, chapter_title, chapter_text = chapters[chapter_index]

        orchestrator = await get_ai_orchestrator()
        summary_text = await orchestrator.summarize(
            chapter_text,
            context=f"Book: {book.title} by {book.author}"
        )

        summary = await self.summary_repo.create(
            book_id=book_id,
            chapter_index=chapter_index,
            chapter_title=chapter_title,
            summary_text=summary_text,
            provider=await orchestrator.get_active_provider()
        )

        logger.info(
            f"Summary generated for book {book_id}, "
            f"chapter {chapter_index} using {summary.provider}"
        )

        return summary

    async def get_book_summary(
        self,
        book_id: int,
        force_refresh: bool = False
    ) -> ChapterSummary:
        """Get comprehensive book summary.

        Args:
            book_id: Book primary key
            force_refresh: Force regeneration even if cached

        Returns:
            BookSummary instance

        Raises:
            ResourceNotFoundError: If book not found
        """
        book = await self.book_repo.get_by_id_or_404(book_id)

        if not force_refresh:
            existing = await self.book_summary_repo.get_by_book(book_id)
            if existing:
                logger.debug(f"Using cached book summary for {book_id}")
                return existing

        from app.reader_engine import ReaderEngine

        reader = ReaderEngine()
        chapters = await reader.get_all_chapters(book.path)

        chapter_summaries = []
        for i, (_, title, text) in enumerate(chapters):
            cached = await self.summary_repo.get_cached_summary(book_id, i)
            if cached:
                chapter_summaries.append(cached.summary_text)
            else:
                orchestrator = await get_ai_orchestrator()
                summary_text = await orchestrator.summarize(
                    text,
                    context=f"Chapter {i + 1}: {title}"
                )
                chapter_summaries.append(summary_text)

                await self.summary_repo.create(
                    book_id=book_id,
                    chapter_index=i,
                    chapter_title=title,
                    summary_text=summary_text,
                    provider=await orchestrator.get_active_provider()
                )

        orchestrator = await get_ai_orchestrator()
        combined_text = "\n\n".join([
            f"Chapter {i + 1}: {summary}"
            for i, summary in enumerate(chapter_summaries)
        ])

        book_summary_text = await orchestrator.summarize(
            combined_text,
            context=f"Book: {book.title} by {book.author}"
        )

        book_summary = await self.book_summary_repo.create_or_update(
            book_id=book_id,
            summary_text=book_summary_text,
            provider=await orchestrator.get_active_provider()
        )

        logger.info(f"Book summary generated for {book_id}")
        return book_summary

    async def get_ai_providers_status(self) -> dict:
        """Get status of all AI providers.

        Returns:
            Dictionary with provider status
        """
        orchestrator = await get_ai_orchestrator()
        return await orchestrator.get_provider_status()

    async def get_active_ai_provider(self) -> str:
        """Get the currently active AI provider.

        Returns:
            Name of the active provider
        """
        orchestrator = await get_ai_orchestrator()
        return await orchestrator.get_active_provider()

    async def switch_ai_provider(self, provider_name: str) -> dict:
        """Manually switch to a specific AI provider.

        Args:
            provider_name: Name of the provider to use

        Returns:
            Status dictionary

        Raises:
            ValueError: If provider is not found
        """
        orchestrator = await get_ai_orchestrator()

        target_provider = None
        for provider in orchestrator.providers:
            if provider.name == provider_name:
                target_provider = provider
                break

        if not target_provider:
            raise ValueError(
                f"Provider '{provider_name}' not found. "
                f"Available: {[p.name for p in orchestrator.providers]}"
            )

        is_healthy = await target_provider.health_check()
        if not is_healthy:
            raise ValueError(f"Provider '{provider_name}' is not available")

        orchestrator.providers.remove(target_provider)
        orchestrator.providers.insert(0, target_provider)

        logger.info(f"Switched to AI provider: {provider_name}")

        return {
            "active_provider": provider_name,
            "provider_order": [p.name for p in orchestrator.providers]
        }

    async def get_table_of_contents(self, book_id: int) -> list[dict]:
        """Get table of contents for a book.

        Args:
            book_id: Book primary key

        Returns:
            List of TOC items with index, title, level

        Raises:
            ResourceNotFoundError: If book not found
        """
        from app.reader_engine import ReaderEngine

        book = await self.book_repo.get_by_id_or_404(book_id)
        reader = ReaderEngine()

        toc = await reader.get_table_of_contents(book.path)
        return toc

    # ============================================
    # BOOKMARK METHODS
    # ============================================

    async def create_bookmark(
        self,
        book_id: int,
        chapter_index: int,
        position_in_chapter: int,
        title: str | None = None,
        notes: str | None = None
    ) -> Bookmark:
        """Create a new bookmark.

        Args:
            book_id: Book primary key
            chapter_index: Chapter index
            position_in_chapter: Character position in chapter
            title: Optional bookmark title
            notes: Optional bookmark notes

        Returns:
            Created Bookmark instance
        """
        bookmark = Bookmark(
            book_id=book_id,
            chapter_index=chapter_index,
            position_in_chapter=position_in_chapter,
            title=title,
            notes=notes
        )
        self.session.add(bookmark)
        await self.session.commit()
        await self.session.refresh(bookmark)
        logger.info(f"Bookmark created for book {book_id}, chapter {chapter_index}")
        return bookmark

    async def list_bookmarks(self, book_id: int) -> list[Bookmark]:
        """List all bookmarks for a book.

        Args:
            book_id: Book primary key

        Returns:
            List of Bookmark instances
        """
        result = await self.session.execute(
            select(Bookmark)
            .where(Bookmark.book_id == book_id)
            .order_by(Bookmark.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_bookmark(self, bookmark_id: int) -> Bookmark:
        """Get a bookmark by ID.

        Args:
            bookmark_id: Bookmark primary key

        Returns:
            Bookmark instance

        Raises:
            ResourceNotFoundError: If bookmark not found
        """
        result = await self.session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()
        if not bookmark:
            raise ResourceNotFoundError(f"Bookmark {bookmark_id} not found")
        return bookmark

    async def delete_bookmark(self, bookmark_id: int) -> None:
        """Delete a bookmark.

        Args:
            bookmark_id: Bookmark primary key
        """
        await self.session.execute(
            delete(Bookmark).where(Bookmark.id == bookmark_id)
        )
        await self.session.commit()
        logger.info(f"Bookmark {bookmark_id} deleted")

    # ============================================
    # NOTE METHODS
    # ============================================

    async def create_note(
        self,
        book_id: int,
        chapter_index: int,
        position_in_chapter: int,
        content: str,
        color: str = "yellow",
        quoted_text: str | None = None
    ) -> Note:
        """Create a new note.

        Args:
            book_id: Book primary key
            chapter_index: Chapter index
            position_in_chapter: Character position in chapter
            content: Note content
            color: Note color
            quoted_text: Optional quoted text

        Returns:
            Created Note instance
        """
        note = Note(
            book_id=book_id,
            chapter_index=chapter_index,
            position_in_chapter=position_in_chapter,
            content=content,
            color=color,
            quoted_text=quoted_text
        )
        self.session.add(note)
        await self.session.commit()
        await self.session.refresh(note)
        logger.info(f"Note created for book {book_id}, chapter {chapter_index}")
        return note

    async def list_notes(self, book_id: int) -> list[Note]:
        """List all notes for a book.

        Args:
            book_id: Book primary key

        Returns:
            List of Note instances
        """
        result = await self.session.execute(
            select(Note)
            .where(Note.book_id == book_id)
            .order_by(Note.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_note(self, note_id: int) -> None:
        """Delete a note.

        Args:
            note_id: Note primary key
        """
        await self.session.execute(
            delete(Note).where(Note.id == note_id)
        )
        await self.session.commit()
        logger.info(f"Note {note_id} deleted")

    # ============================================
    # ANNOTATION METHODS
    # ============================================

    async def create_annotation(
        self,
        book_id: int,
        chapter_index: int,
        start_position: int,
        end_position: int,
        text: str,
        color: str = "yellow",
        note: str | None = None
    ) -> Annotation:
        """Create a new annotation.

        Args:
            book_id: Book primary key
            chapter_index: Chapter index
            start_position: Start character position
            end_position: End character position
            text: Annotated text
            color: Highlight color
            note: Optional note

        Returns:
            Created Annotation instance
        """
        annotation = Annotation(
            book_id=book_id,
            chapter_index=chapter_index,
            start_position=start_position,
            end_position=end_position,
            text=text,
            color=color,
            note=note
        )
        self.session.add(annotation)
        await self.session.commit()
        await self.session.refresh(annotation)
        logger.info(f"Annotation created for book {book_id}, chapter {chapter_index}")
        return annotation

    async def list_annotations(self, book_id: int, chapter_index: int | None = None) -> list[Annotation]:
        """List annotations for a book.

        Args:
            book_id: Book primary key
            chapter_index: Optional chapter filter

        Returns:
            List of Annotation instances
        """
        query = select(Annotation).where(Annotation.book_id == book_id)
        if chapter_index is not None:
            query = query.where(Annotation.chapter_index == chapter_index)

        query = query.order_by(Annotation.start_position)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_annotation(self, annotation_id: int) -> None:
        """Delete an annotation.

        Args:
            annotation_id: Annotation primary key
        """
        await self.session.execute(
            delete(Annotation).where(Annotation.id == annotation_id)
        )
        await self.session.commit()
        logger.info(f"Annotation {annotation_id} deleted")
