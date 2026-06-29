"""Category management routes."""

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import CategoryAssignRequest, CategoryCreate, CategoryResponse

router = APIRouter(prefix="/api", tags=["categories"])


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[CategoryResponse]:
    """List all categories with book counts."""
    from sqlalchemy import func, select

    from app.models import BookCategory, Category

    result = await db.execute(
        select(
            Category.id,
            Category.name,
            Category.color,
            func.count(BookCategory.book_id).label("book_count"),
        )
        .outerjoin(BookCategory, Category.id == BookCategory.category_id)
        .group_by(Category.id, Category.name, Category.color)
        .order_by(func.count(BookCategory.book_id).desc(), Category.name)
        .limit(10)
    )

    return [
        CategoryResponse(id=row.id, name=row.name, color=row.color, book_count=row.book_count)
        for row in result.all()
    ]


@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    """Create a new category."""
    from sqlalchemy import select

    from app.models import Category

    existing = await db.execute(select(Category).where(Category.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Category already exists")

    cat = Category(name=data.name, color=data.color)
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    return CategoryResponse(id=cat.id, name=cat.name, color=cat.color, book_count=0)


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a category."""
    from sqlalchemy import select

    from app.models import Category

    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    await db.delete(cat)
    await db.flush()
    return {"message": "Category deleted"}


@router.post("/books/{book_id}/categories")
async def assign_categories(
    book_id: int,
    data: CategoryAssignRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Assign categories to a book (replaces existing assignments)."""
    from app.models import BookCategory

    await db.execute(BookCategory.__table__.delete().where(BookCategory.book_id == book_id))

    for cat_id in data.category_ids:
        db.add(BookCategory(book_id=book_id, category_id=cat_id))

    await db.flush()
    return {"message": "Categories updated", "category_ids": data.category_ids}


@router.delete("/books/{book_id}/categories/{category_id}")
async def remove_category_from_book(
    book_id: int,
    category_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a category from a book."""
    from sqlalchemy import select

    from app.models import BookCategory

    result = await db.execute(
        select(BookCategory).where(
            BookCategory.book_id == book_id,
            BookCategory.category_id == category_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await db.delete(link)
    await db.flush()
    return {"message": "Category removed from book"}


@router.post("/books/{book_id}/auto-categorize")
async def auto_categorize_book(
    book_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Auto-categorize a single book using hybrid rule-based + AI approach."""
    from app.repositories import BookRepository
    from app.services.categorization_service import CategorizationService

    repo = BookRepository(db)
    book = await repo.get_by_id_or_404(book_id)

    cat_service = CategorizationService(db)
    return await cat_service.auto_categorize(book)


@router.post("/library/auto-categorize-all")
async def auto_categorize_all(db: AsyncSession = Depends(get_db)) -> dict:
    """Auto-categorize all books in the library."""
    from app.services.categorization_service import CategorizationService

    cat_service = CategorizationService(db)
    return await cat_service.auto_categorize_all()


@router.get("/library/auto-categorize-stream")
async def auto_categorize_stream(db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """SSE stream for real-time categorization progress."""
    from sqlalchemy import select

    from app.models import Book
    from app.services.categorization_service import CategorizationService

    async def generate() -> AsyncGenerator[str, None]:
        cat_service = CategorizationService(db)
        db_result = await db.execute(select(Book))
        books = list(db_result.scalars().all())
        total = len(books)
        categorized = 0
        categories_added = 0

        yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

        for i, book in enumerate(books):
            try:
                result = await cat_service.ai_categorize(book)
                added = result.get("categories_added", 0)
                cats = result.get("categories", [])
                categorized += 1 if added > 0 else 0
                categories_added += added

                yield f"data: {
                    json.dumps(
                        {
                            'type': 'progress',
                            'current': i + 1,
                            'total': total,
                            'book': book.title,
                            'categories': cats,
                            'categories_added': added,
                            'running_categorized': categorized,
                            'running_total_added': categories_added,
                        }
                    )
                }\n\n"
            except Exception as e:
                yield f"data: {
                    json.dumps(
                        {
                            'type': 'error',
                            'current': i + 1,
                            'total': total,
                            'book': book.title,
                            'error': str(e),
                        }
                    )
                }\n\n"

            await asyncio.sleep(0)

        yield f"data: {
            json.dumps(
                {
                    'type': 'done',
                    'total': total,
                    'categorized': categorized,
                    'categories_added': categories_added,
                }
            )
        }\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
