"""Hybrid auto-categorization service.

Combines rule-based metadata matching with AI-powered suggestions.
"""

from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger

logger = get_logger(__name__)

# Common subject -> category mapping
_SUBJECT_CATEGORY_MAP: dict[str, list[str]] = {
    "fiction": ["Fiction"],
    "nonfiction": ["Non-Fiction"],
    "non-fiction": ["Non-Fiction"],
    "science fiction": ["Science Fiction", "Fiction"],
    "fantasy": ["Fantasy", "Fiction"],
    "mystery": ["Mystery", "Fiction"],
    "thriller": ["Thriller", "Fiction"],
    "romance": ["Romance", "Fiction"],
    "horror": ["Horror", "Fiction"],
    "biography": ["Biography", "Non-Fiction"],
    "autobiography": ["Biography", "Non-Fiction"],
    "history": ["History", "Non-Fiction"],
    "science": ["Science", "Non-Fiction"],
    "technology": ["Technology", "Non-Fiction"],
    "programming": ["Technology", "Non-Fiction"],
    "computer science": ["Technology", "Non-Fiction"],
    "mathematics": ["Mathematics", "Non-Fiction"],
    "philosophy": ["Philosophy", "Non-Fiction"],
    "psychology": ["Psychology", "Non-Fiction"],
    "self-help": ["Self-Help", "Non-Fiction"],
    "business": ["Business", "Non-Fiction"],
    "economics": ["Business", "Non-Fiction"],
    "politics": ["Politics", "Non-Fiction"],
    "art": ["Art", "Non-Fiction"],
    "music": ["Music", "Non-Fiction"],
    "poetry": ["Poetry", "Fiction"],
    "drama": ["Drama", "Fiction"],
    "children": ["Children", "Fiction"],
    "young adult": ["Young Adult", "Fiction"],
    "travel": ["Travel", "Non-Fiction"],
    "cooking": ["Cooking", "Non-Fiction"],
    "health": ["Health", "Non-Fiction"],
    "fitness": ["Health", "Non-Fiction"],
    "religion": ["Religion", "Non-Fiction"],
    "spirituality": ["Religion", "Non-Fiction"],
    "education": ["Education", "Non-Fiction"],
    "law": ["Law", "Non-Fiction"],
    "medicine": ["Medicine", "Non-Fiction"],
    "nature": ["Nature", "Non-Fiction"],
    "sports": ["Sports", "Non-Fiction"],
    "comics": ["Comics", "Fiction"],
    "graphic novel": ["Comics", "Fiction"],
    "classic": ["Classics", "Fiction"],
    "literature": ["Literature", "Fiction"],
    "adventure": ["Adventure", "Fiction"],
    "crime": ["Crime", "Fiction"],
    "detective": ["Mystery", "Fiction"],
    "humor": ["Humor", "Non-Fiction"],
    "comedy": ["Humor", "Non-Fiction"],
    "memoir": ["Memoir", "Non-Fiction"],
    "true crime": ["True Crime", "Non-Fiction"],
    "suspense": ["Thriller", "Fiction"],
    "dystopian": ["Dystopian", "Fiction"],
    "historical fiction": ["Historical Fiction", "Fiction"],
    "literary fiction": ["Literary Fiction", "Fiction"],
}

_DEFAULT_COLORS = [
    "#8b5cf6", "#ef4444", "#f59e0b", "#10b981", "#3b82f6",
    "#ec4899", "#06b6d4", "#f97316", "#84cc16", "#6366f1",
]


class CategorizationService:
    """Hybrid categorization: rule-based from metadata + optional AI."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._color_index = 0

    def _next_color(self) -> str:
        """Get next color from the default palette."""
        color = _DEFAULT_COLORS[self._color_index % len(_DEFAULT_COLORS)]
        self._color_index += 1
        return color

    async def _get_or_create_category(self, name: str) -> int:
        """Get existing category ID or create a new one."""
        from app.models import Category

        result = await self.session.execute(
            select(Category).where(Category.name == name)
        )
        cat = result.scalar_one_or_none()
        if cat:
            return cat.id

        cat = Category(name=name, color=self._next_color())
        self.session.add(cat)
        await self.session.flush()
        await self.session.refresh(cat)
        logger.info(f"Created category: {name}")
        return cat.id

    async def _get_book_category_ids(self, book_id: int) -> set[int]:
        """Get current category IDs for a book."""
        from app.models import BookCategory

        result = await self.session.execute(
            select(BookCategory.category_id).where(BookCategory.book_id == book_id)
        )
        return {row[0] for row in result.all()}

    async def _assign_category(
        self, book_id: int, category_id: int, existing_ids: set[int] | None = None
    ) -> bool:
        """Assign a category to a book. Returns True if new assignment."""
        from app.models import BookCategory

        if existing_ids is None:
            existing_ids = await self._get_book_category_ids(book_id)
        if category_id in existing_ids:
            return False

        self.session.add(BookCategory(book_id=book_id, category_id=category_id))
        await self.session.flush()
        existing_ids.add(category_id)
        return True

    def _fuzzy_match(self, subject: str) -> list[str]:
        """Find matching categories for a subject using fuzzy matching."""
        subject_lower = subject.lower().strip()

        # Direct lookup first
        if subject_lower in _SUBJECT_CATEGORY_MAP:
            return _SUBJECT_CATEGORY_MAP[subject_lower]

        # Fuzzy match
        best_matches: list[str] = []
        best_score = 0.0
        for key, categories in _SUBJECT_CATEGORY_MAP.items():
            score = SequenceMatcher(None, subject_lower, key).ratio()
            if score > best_score and score >= 0.8:
                best_score = score
                best_matches = categories

        return best_matches

    async def rule_based_categorize(
        self, book, subjects: list[str]
    ) -> dict:
        """Categorize a book based on extracted metadata subjects.

        Args:
            book: Book ORM instance
            subjects: List of subject strings from metadata

        Returns:
            Dict with categorization results
        """
        if not subjects:
            return {"categories_added": 0, "categories": []}

        all_category_names: set[str] = set()
        for subject in subjects:
            matched = self._fuzzy_match(subject)
            all_category_names.update(matched)
            # Also try the subject itself as a category if no match
            if not matched and len(subject) < 50:
                all_category_names.add(subject.title())

        if not all_category_names:
            return {"categories_added": 0, "categories": []}

        added = 0
        category_names: list[str] = []
        existing_ids = await self._get_book_category_ids(book.id)
        for name in all_category_names:
            cat_id = await self._get_or_create_category(name)
            is_new = await self._assign_category(book.id, cat_id, existing_ids)
            if is_new:
                added += 1
            category_names.append(name)

        await self.session.commit()
        logger.info(f"Rule-based categorized '{book.title}': {category_names}")
        return {"categories_added": added, "categories": category_names}

    async def ai_categorize(self, book) -> dict:
        """Use AI to suggest categories for a book."""
        try:
            from app.ai_engine import get_ai_orchestrator

            orchestrator = await get_ai_orchestrator()
            prompt = (
                f"Categorize this book into 2-5 genres/categories.\n"
                f"Title: {book.title}\n"
                f"Author: {book.author or 'Unknown'}\n"
                f"Description: {book.description or 'N/A'}\n\n"
                f"Return ONLY a JSON array of category names, nothing else.\n"
                f"Example: [\"Fiction\", \"Science Fiction\"]"
            )

            response = await orchestrator.summarize(prompt)
            import json
            # Try to extract JSON array from response
            text = response.strip()
            if text.startswith("["):
                categories = json.loads(text)
            else:
                # Try to find array in response
                import re
                match = re.search(r'\[.*?\]', text, re.DOTALL)
                if match:
                    categories = json.loads(match.group())
                else:
                    return {"categories_added": 0, "categories": []}

            return await self.rule_based_categorize(book, categories)

        except Exception as e:
            logger.warning(f"AI categorization failed for '{book.title}': {e}")
            return {"categories_added": 0, "categories": []}

    async def auto_categorize(self, book) -> dict:
        """Auto-categorize a book using AI."""
        return await self.ai_categorize(book)

    async def auto_categorize_all(self) -> dict:
        """Auto-categorize all books in the library."""
        from app.models import Book

        db_result = await self.session.execute(select(Book))
        books = list(db_result.scalars().all())

        total_categorized = 0
        total_categories_added = 0

        for book in books:
            try:
                result = await self.ai_categorize(book)
                if result["categories_added"] > 0:
                    total_categorized += 1
                    total_categories_added += result["categories_added"]
            except Exception as e:
                logger.warning(f"Failed to categorize '{book.title}': {e}")

        return {
            "total_books": len(books),
            "categorized": total_categorized,
            "categories_added": total_categories_added,
        }
