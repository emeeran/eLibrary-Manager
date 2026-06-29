"""Per-book hidden-password routes.

Approach A: each hidden book is protected by its own password (stored as a
one-way bcrypt hash on the book). There is no global hidden-books password.

Routes
------
- ``POST /books/{book_id}/hide``    — set a new password for *this* book and
  mark it hidden. Body: ``{"password": "..."}``.
- ``POST /books/{book_id}/unhide``  — verify the book's password and unhide it.
  Body: ``{"password": "..."}``. Per-book rate-limited (attempt cap).
- ``GET  /hidden/status``           — whether any hidden books exist (drives the
  sidebar nav visibility).
- ``POST /hidden/unhide-all``       — admin-only bulk reset: clears every book's
  hidden state + password AND deletes the legacy global ``hidden_password``
  setting. This is the "remove existing password and unhide all" action.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.logging_config import get_logger
from app.models import Book, Setting
from app.routes.library import invalidate_book_list_cache
from app.security import encrypt_password
from app.security import verify_password as check_password

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["hidden-books"])

# Minimum length for a per-book password.
_MIN_PASSWORD_LEN = 1
# Lockout after too many failed unhide attempts on a single book. bcrypt is
# expensive, but we still cap attempts to make brute force impractical.
_MAX_FAILED_ATTEMPTS = 5
# Track failed unhide attempts per (book_id, client) to enforce lockout.
# In-memory (single-process); cleared on restart — adequate for a personal app.
_failed_attempts: dict[tuple[int, str], int] = {}


async def _get_book_or_404(db: AsyncSession, book_id: int) -> Book:
    """Load a book by id or raise 404."""
    from sqlalchemy import select

    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.post("/books/{book_id}/hide")
async def hide_book(
    book_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hide a book behind a new per-book password.

    Sets ``is_hidden = True`` and stores a one-way bcrypt *hash* of ``password``
    on the book (never the reversible password). If the book is already hidden
    with a password, this requires the *current* password to re-hide/re-key it
    (prevents silently overwriting a forgotten password). To unhide instead,
    use ``/unhide``.
    """
    payload = (await request.json()) if request else {}
    password = payload.get("password", "")
    if not password or len(password) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail="A password is required to hide this book")
    if len(password) > 72:
        # bcrypt truncates at 72 bytes; reject longer to avoid silent-truncation ambiguity.
        raise HTTPException(status_code=400, detail="Password must be 72 characters or fewer")

    book = await _get_book_or_404(db, book_id)

    # If the book already has a password, require it before re-keying.
    if book.hidden_password:
        current = payload.get("current_password", "")
        if not current or not check_password(current, book.hidden_password):
            raise HTTPException(
                status_code=401,
                detail="This book is already hidden. Provide the current password to re-key it, "
                       "or use Unhide instead.",
            )

    book.hidden_password = encrypt_password(password)
    book.is_hidden = True
    await db.commit()
    invalidate_book_list_cache()
    logger.info("Book %s hidden with a per-book password", book_id)
    return {"is_hidden": True, "message": "Book hidden"}


@router.post("/books/{book_id}/unhide")
async def unhide_book(
    book_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Unhide a book by verifying its per-book password.

    Clears ``is_hidden`` and the stored password hash on success. 401 if the
    password is wrong or the book isn't actually hidden. Enforces a per-book
    attempt cap to throttle brute force.
    """
    payload = (await request.json()) if request else {}
    password = payload.get("password", "")
    book = await _get_book_or_404(db, book_id)

    if not book.is_hidden or not book.hidden_password:
        raise HTTPException(status_code=400, detail="This book is not hidden")

    client = request.client.host if request.client else "unknown"
    key = (book_id, client)
    if _failed_attempts.get(key, 0) >= _MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Use “Remove all & unhide everything”, or restart the service.",
        )

    if not password or not check_password(password, book.hidden_password):
        _failed_attempts[key] = _failed_attempts.get(key, 0) + 1
        raise HTTPException(status_code=401, detail="Incorrect password for this book")

    # Success — clear any failed-attempt counter for this client/book.
    _failed_attempts.pop(key, None)
    book.is_hidden = False
    book.hidden_password = None
    await db.commit()
    invalidate_book_list_cache()
    logger.info("Book %s unhidden", book_id)
    return {"is_hidden": False, "message": "Book unhidden"}


@router.get("/hidden/status")
async def get_hidden_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Report whether any hidden books exist.

    Replaces the old "global password set?" semantics: the sidebar Hidden nav
    item is shown when at least one book is hidden.
    """
    from sqlalchemy import func, select

    count = (
        await db.execute(select(func.count(Book.id)).where(Book.is_hidden))
    ).scalar_one()
    return {"password_set": count > 0, "hidden_count": int(count)}


@router.post("/hidden/unhide-all")
async def unhide_all_books(db: AsyncSession = Depends(get_db)) -> dict:
    """Remove every hidden-book password and unhide all books.

    Bulk admin reset (the request is already authenticated as the admin via
    :class:`AuthMiddleware`). Clears ``is_hidden`` and ``hidden_password`` on
    every book and deletes the legacy global ``hidden_password`` setting if it
    exists. This is the one-time "remove existing password and unhide all"
    migration action.
    """
    from sqlalchemy import delete as sa_delete

    # 1. Clear per-book hidden state + passwords in one statement.
    result = await db.execute(
        update(Book)
        .where((Book.is_hidden == True) | (Book.hidden_password.isnot(None)))  # noqa: E712
        .values(is_hidden=False, hidden_password=None)
    )
    cleared_books = result.rowcount or 0

    # 2. Remove the legacy global hidden_password setting (if present).
    legacy = await db.execute(sa_delete(Setting).where(Setting.key == "hidden_password"))
    cleared_legacy = legacy.rowcount or 0

    await db.commit()
    invalidate_book_list_cache()
    logger.info(
        "Bulk hidden reset: cleared %s book(s), removed legacy setting: %s",
        cleared_books, bool(cleared_legacy),
    )
    return {
        "message": f"Cleared {cleared_books} hidden book(s).",
        "cleared_books": cleared_books,
        "legacy_setting_removed": bool(cleared_legacy),
    }
