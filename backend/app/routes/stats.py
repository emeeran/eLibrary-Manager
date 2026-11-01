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
        select(func.count(Book.id)).where(Book.is_hidden.is_(False))
    )
    total_books = total_result.scalar() or 0

    # Books read (progress > 0)
    read_result = await db.execute(
        select(func.count(Book.id)).where(
            Book.is_hidden.is_(False),
            Book.progress > 0,
        )
    )
    books_read = read_result.scalar() or 0

    # Books completed (progress >= 95)
    completed_result = await db.execute(
        select(func.count(Book.id)).where(
            Book.is_hidden.is_(False),
            Book.progress >= 95,
        )
    )
    books_completed = completed_result.scalar() or 0

    # Books read this week (last_read_date within 7 days)
    week_result = await db.execute(
        select(func.count(Book.id)).where(
            Book.is_hidden.is_(False),
            Book.last_read_date >= week_ago,
        )
    )
    books_this_week = week_result.scalar() or 0

    # Books read this month (last_read_date within 30 days)
    month_result = await db.execute(
        select(func.count(Book.id)).where(
            Book.is_hidden.is_(False),
            Book.last_read_date >= month_ago,
        )
    )
    books_this_month = month_result.scalar() or 0

    # Average progress across all non-hidden books
    avg_result = await db.execute(
        select(func.avg(Book.progress)).where(Book.is_hidden.is_(False))
    )
    avg_progress = round(avg_result.scalar() or 0, 1)

    # Reading time: tracked sessions are the source of truth; the
    # per-reading-day heuristic only fills in when no sessions exist yet.
    from app.models import ReadingSession, Setting

    minutes_result = await db.execute(select(func.coalesce(func.sum(ReadingSession.minutes), 0.0)))
    tracked_minutes = round(minutes_result.scalar() or 0.0, 1)
    today_minutes_result = await db.execute(
        select(func.coalesce(func.sum(ReadingSession.minutes), 0.0)).where(
            func.date(ReadingSession.started_at) == now.date()
        )
    )
    today_minutes = round(today_minutes_result.scalar() or 0.0, 1)

    goal_result = await db.execute(
        select(Setting.value).where(Setting.key == "daily_goal_minutes")
    )
    daily_goal_minutes = float(goal_result.scalar() or 30)
    goal_progress_pct = (
        round(today_minutes / daily_goal_minutes * 100)
        if daily_goal_minutes > 0
        else 0
    )

    if tracked_minutes > 0:
        reading_time_source = "tracked"
        estimated_reading_hours = round(tracked_minutes / 60, 1)
    else:
        # Heuristic fallback: each distinct reading day counts as ~30 min.
        reading_time_result = await db.execute(
            select(func.count(func.distinct(func.date(Book.last_read_date)))).where(
                Book.is_hidden.is_(False),
                Book.last_read_date.isnot(None),
            )
        )
        reading_days = reading_time_result.scalar() or 0
        reading_time_source = "estimated"
        estimated_reading_hours = round(reading_days * 0.5, 1)

    # Most read authors (top 5 by book count, limited to books with progress > 0)
    authors_result = await db.execute(
        select(Book.author, func.count(Book.id).label("count"))
        .where(
            Book.is_hidden.is_(False),
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
        .where(Book.is_hidden.is_(False))
        .group_by(Book.format)
        .order_by(func.count(Book.id).desc())
    )
    format_distribution = [
        {"format": row.format, "count": row.count} for row in format_result.all()
    ]

    # Reading streak: tracked session days when present, else book-open days.
    session_dates_result = await db.execute(
        select(func.distinct(func.date(ReadingSession.started_at)))
    )
    streak = await _calculate_reading_streak(db, now, set(session_dates_result.scalars().all()))

    return {
        "total_books": total_books,
        "books_read": books_read,
        "books_completed": books_completed,
        "books_this_week": books_this_week,
        "books_this_month": books_this_month,
        "average_progress": avg_progress,
        "estimated_reading_hours": estimated_reading_hours,
        "reading_time_source": reading_time_source,
        "tracked_minutes": tracked_minutes,
        "today_minutes": today_minutes,
        "daily_goal_minutes": daily_goal_minutes,
        "goal_progress_pct": min(goal_progress_pct, 100),
        "reading_streak": streak,
        "top_authors": top_authors,
        "format_distribution": format_distribution,
    }


async def _calculate_reading_streak(
    db: AsyncSession, now: datetime, extra_dates: set | None = None
) -> int:
    """Calculate consecutive reading streak.

    A streak is the number of consecutive days ending at today or yesterday
    where at least one book was opened or a reading session was tracked.

    Args:
        db: Database session
        now: Current datetime
        extra_dates: Additional reading dates (tracked session days) merged in.

    Returns:
        int: Number of consecutive days in the streak
    """
    # Get all distinct reading dates
    dates_result = await db.execute(
        select(func.distinct(func.date(Book.last_read_date)))
        .where(
            Book.is_hidden.is_(False),
            Book.last_read_date.isnot(None),
        )
        .order_by(func.date(Book.last_read_date).desc())
    )
    reading_dates = set(dates_result.scalars().all())
    if extra_dates:
        reading_dates |= {d for d in extra_dates if d is not None}

    if not reading_dates:
        return 0

    # Normalize to ISO strings — SQLite's date() yields text, not date objects.
    reading_dates = {str(d)[:10] for d in reading_dates}
    today = now.date().isoformat()
    yesterday = (now - timedelta(days=1)).date().isoformat()

    if today not in reading_dates and yesterday not in reading_dates:
        return 0

    # Count consecutive days backwards
    streak = 0
    check_date = today if today in reading_dates else yesterday
    check_day = datetime.fromisoformat(check_date).date()

    while check_date in reading_dates:
        streak += 1
        check_day = check_day - timedelta(days=1)
        check_date = check_day.isoformat()

    return streak
