"""Reading statistics routes for eLibrary Manager.

Provides aggregated reading statistics for the dashboard.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.logging_config import get_logger
from app.models import Book

logger = get_logger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/sidebar")
async def get_sidebar_counts(db: AsyncSession = Depends(get_db)) -> dict:
    """Get sidebar navigation counts.

    Returns cached counts for all, recent, favorites, reading, deleted, hidden.
    Decoupled from the book list endpoint for better performance.
    """
    from app.services import LibraryService

    service = LibraryService(db)
    return await service.get_sidebar_counts()


@router.get("/reading")
async def get_reading_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Get aggregated reading statistics.

    Returns:
        dict: Reading stats including totals, progress, authors, formats, streaks.
    """
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Total books (non-hidden, non-deleted)
    total_result = await db.execute(
        select(func.count(Book.id)).where(Book.is_hidden == False)  # noqa: E712
    )
    total_books = total_result.scalar() or 0

    # Books read (progress > 0)
    read_result = await db.execute(
        select(func.count(Book.id)).where(
            Book.is_hidden == False,  # noqa: E712
            Book.progress > 0,
        )
    )
    books_read = read_result.scalar() or 0

    # Books completed (progress >= 95)
    completed_result = await db.execute(
        select(func.count(Book.id)).where(
            Book.is_hidden == False,  # noqa: E712
            Book.progress >= 95,
        )
    )
    books_completed = completed_result.scalar() or 0

    # Books read this week (last_read_date within 7 days)
    week_result = await db.execute(
        select(func.count(Book.id)).where(
            Book.is_hidden == False,  # noqa: E712
            Book.last_read_date >= week_ago,
        )
    )
    books_this_week = week_result.scalar() or 0

    # Books read this month (last_read_date within 30 days)
    month_result = await db.execute(
        select(func.count(Book.id)).where(
            Book.is_hidden == False,  # noqa: E712
            Book.last_read_date >= month_ago,
        )
    )
    books_this_month = month_result.scalar() or 0

    # Average progress across all non-hidden books
    avg_result = await db.execute(
        select(func.avg(Book.progress)).where(Book.is_hidden == False)  # noqa: E712
    )
    avg_progress = round(avg_result.scalar() or 0, 1)

    # Total estimated reading time (based on last_read_date deltas)
    # Each day with a last_read_date counts as ~30 min reading
    reading_time_result = await db.execute(
        select(func.count(func.distinct(func.date(Book.last_read_date)))).where(
            Book.is_hidden == False,  # noqa: E712
            Book.last_read_date.isnot(None),
        )
    )
    reading_days = reading_time_result.scalar() or 0
    estimated_reading_hours = round(reading_days * 0.5, 1)  # 30 min per day estimate

    # Most read authors (top 5 by book count, limited to books with progress > 0)
    authors_result = await db.execute(
        select(Book.author, func.count(Book.id).label("count"))
        .where(
            Book.is_hidden == False,  # noqa: E712
            Book.author.isnot(None),
            Book.author != "",
            Book.progress > 0,
        )
        .group_by(Book.author)
        .order_by(func.count(Book.id).desc())
        .limit(5)
    )
    top_authors = [{"author": row.author, "count": row.count} for row in authors_result.all()]

    # Format distribution
    format_result = await db.execute(
        select(Book.format, func.count(Book.id).label("count"))
        .where(Book.is_hidden == False)  # noqa: E712
        .group_by(Book.format)
        .order_by(func.count(Book.id).desc())
    )
    format_distribution = [
        {"format": row.format, "count": row.count} for row in format_result.all()
    ]

    # Reading streak (consecutive days with last_read_date ending at today or yesterday)
    streak = await _calculate_reading_streak(db, now)

    return {
        "total_books": total_books,
        "books_read": books_read,
        "books_completed": books_completed,
        "books_this_week": books_this_week,
        "books_this_month": books_this_month,
        "average_progress": avg_progress,
        "estimated_reading_hours": estimated_reading_hours,
        "reading_streak": streak,
        "top_authors": top_authors,
        "format_distribution": format_distribution,
    }


async def _calculate_reading_streak(db: AsyncSession, now: datetime) -> int:
    """Calculate consecutive reading streak.

    A streak is the number of consecutive days ending at today or yesterday
    where at least one book was opened.

    Args:
        db: Database session
        now: Current datetime

    Returns:
        int: Number of consecutive days in the streak
    """
    # Get all distinct reading dates
    dates_result = await db.execute(
        select(func.distinct(func.date(Book.last_read_date)))
        .where(
            Book.is_hidden == False,  # noqa: E712
            Book.last_read_date.isnot(None),
        )
        .order_by(func.date(Book.last_read_date).desc())
    )
    reading_dates = set(dates_result.scalars().all())

    if not reading_dates:
        return 0

    # Check if today or yesterday is in the set
    today = now.date()
    yesterday = (now - timedelta(days=1)).date()

    if today not in reading_dates and yesterday not in reading_dates:
        return 0

    # Count consecutive days backwards
    streak = 0
    check_date = today if today in reading_dates else yesterday

    while check_date in reading_dates:
        streak += 1
        check_date = check_date - timedelta(days=1)

    return streak


@router.get("/recommendations")
async def get_recommendations(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Suggest books based on shared categories and authors with books you've read.

    Returns up to 10 unread books ranked by overlap count.
    """
    # Find book IDs the user has already started reading
    read_result = await db.execute(
        select(Book.id).where(Book.progress > 0, Book.is_hidden.is_(False))
    )
    read_ids = [row[0] for row in read_result.all()]

    if not read_ids:
        return []

    from app.models import BookCategory

    # Find authors the user reads
    author_result = await db.execute(
        select(Book.author).where(
            Book.id.in_(read_ids),
            Book.author.isnot(None),
            Book.author != "",
        )
    )
    read_authors = {row[0] for row in author_result.all()}

    # Find categories the user reads
    cat_result = await db.execute(
        select(BookCategory.category_id).where(BookCategory.book_id.in_(read_ids))
    )
    read_cat_ids = {row[0] for row in cat_result.all()}

    # Find unread books sharing those authors or categories
    unread_query = select(Book).where(
        Book.is_hidden.is_(False),
        Book.progress == 0,
        ~Book.id.in_(read_ids),
    )

    # Add OR conditions for author/category matches
    author_conditions = [Book.author == a for a in read_authors] if read_authors else []
    category_condition = (
        Book.id.in_(select(BookCategory.book_id).where(BookCategory.category_id.in_(read_cat_ids)))
        if read_cat_ids
        else None
    )

    if author_conditions or category_condition:
        from sqlalchemy import or_

        or_parts = list(author_conditions)
        if category_condition is not None:
            or_parts.append(category_condition)
        unread_query = unread_query.where(or_(*or_parts))

    result = await db.execute(unread_query.limit(20))
    candidates = list(result.scalars().all())

    # Score by overlap: +2 for same author, +1 for each shared category
    scored: list[tuple[int, dict]] = []
    for book in candidates:
        score = 0
        if book.author in read_authors:
            score += 2

        if read_cat_ids:
            book_cats = await db.execute(
                select(BookCategory.category_id).where(BookCategory.book_id == book.id)
            )
            book_cat_ids = {row[0] for row in book_cats.all()}
            score += len(book_cat_ids & read_cat_ids)

        if score > 0:
            scored.append(
                (
                    score,
                    {
                        "id": book.id,
                        "title": book.title,
                        "author": book.author,
                        "format": book.format,
                        "cover_path": book.cover_path,
                        "score": score,
                    },
                )
            )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:10]]


# ============================================
# READING GOALS
# ============================================

from pydantic import BaseModel


class ReadingGoalRequest(BaseModel):
    """Request body for creating or updating a reading goal."""

    goal_type: str = "daily"  # "daily" or "weekly"
    target_minutes: int = 30


@router.get("/goals")
async def get_reading_goal(db: AsyncSession = Depends(get_db)) -> dict:
    """Get the current reading goal."""
    from app.models import ReadingGoal

    result = await db.execute(select(ReadingGoal).order_by(ReadingGoal.updated_at.desc()).limit(1))
    goal = result.scalar_one_or_none()
    if not goal:
        return {"goal_type": "daily", "target_minutes": 30}
    return {
        "id": goal.id,
        "goal_type": goal.goal_type,
        "target_minutes": goal.target_minutes,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
    }


@router.put("/goals")
async def set_reading_goal(
    request: ReadingGoalRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set or update the reading goal."""
    from app.models import ReadingGoal

    if request.goal_type not in ("daily", "weekly"):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="goal_type must be 'daily' or 'weekly'")

    result = await db.execute(select(ReadingGoal).order_by(ReadingGoal.updated_at.desc()).limit(1))
    goal = result.scalar_one_or_none()

    if goal:
        goal.goal_type = request.goal_type
        goal.target_minutes = request.target_minutes
    else:
        goal = ReadingGoal(
            goal_type=request.goal_type,
            target_minutes=request.target_minutes,
        )
        db.add(goal)

    await db.flush()
    return {"goal_type": goal.goal_type, "target_minutes": goal.target_minutes}


@router.get("/goals/progress")
async def get_reading_goal_progress(db: AsyncSession = Depends(get_db)) -> dict:
    """Get progress toward the current reading goal.

    Reading time is estimated at 30 minutes per distinct reading day.
    """
    from app.models import ReadingGoal

    now = datetime.now(UTC)

    # Get goal
    result = await db.execute(select(ReadingGoal).order_by(ReadingGoal.updated_at.desc()).limit(1))
    goal = result.scalar_one_or_none()
    goal_type = goal.goal_type if goal else "daily"
    target_minutes = goal.target_minutes if goal else 30

    # Calculate period start
    if goal_type == "weekly":
        period_start = now - timedelta(days=7)
    else:
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Count distinct reading dates in the period
    reading_result = await db.execute(
        select(func.count(func.distinct(func.date(Book.last_read_date)))).where(
            Book.is_hidden.is_(False),
            Book.last_read_date.isnot(None),
            Book.last_read_date >= period_start,
        )
    )
    reading_days = reading_result.scalar() or 0
    estimated_minutes = reading_days * 30

    return {
        "goal_type": goal_type,
        "target_minutes": target_minutes,
        "estimated_minutes": estimated_minutes,
        "progress_percent": min(100, round(estimated_minutes / target_minutes * 100, 1))
        if target_minutes > 0
        else 0,
    }
