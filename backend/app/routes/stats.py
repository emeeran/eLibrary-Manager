"""Reading statistics routes for eLibrary Manager.

Provides aggregated reading statistics for the dashboard.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.logging_config import get_logger
from app.models import Book

logger = get_logger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/reading")
async def get_reading_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Get aggregated reading statistics.

    Returns:
        dict: Reading stats including totals, progress, authors, formats, streaks.
    """
    now = datetime.now(timezone.utc)
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
    top_authors = [
        {"author": row.author, "count": row.count}
        for row in authors_result.all()
    ]

    # Format distribution
    format_result = await db.execute(
        select(Book.format, func.count(Book.id).label("count"))
        .where(Book.is_hidden == False)  # noqa: E712
        .group_by(Book.format)
        .order_by(func.count(Book.id).desc())
    )
    format_distribution = [
        {"format": row.format, "count": row.count}
        for row in format_result.all()
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


async def _calculate_reading_streak(
    db: AsyncSession, now: datetime
) -> int:
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
