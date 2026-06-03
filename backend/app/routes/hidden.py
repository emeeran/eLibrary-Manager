"""Hidden books password management routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/api", tags=["hidden-books"])


@router.post("/books/{book_id}/hide")
async def toggle_book_hidden(
    book_id: int,
    request: dict = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Toggle book hidden status. Requires password verification."""
    from app.repositories import BookRepository, SettingsRepository
    from app.security import verify_password as check_password

    settings = SettingsRepository(db)
    stored = await settings.get("hidden_password")

    if not stored:
        raise HTTPException(status_code=400, detail="No password set. Set a password first.")

    password = (request or {}).get("password", "")
    if not password:
        raise HTTPException(status_code=400, detail="Password required")

    if not check_password(password, stored):
        raise HTTPException(status_code=401, detail="Incorrect password")

    repo = BookRepository(db)
    book = await repo.get_by_id_or_404(book_id)

    book.is_hidden = not book.is_hidden
    await db.flush()
    return {"is_hidden": book.is_hidden, "message": "Book hidden" if book.is_hidden else "Book unhidden"}


@router.get("/hidden/status")
async def get_hidden_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Check if hidden books password is set."""
    from app.repositories import SettingsRepository

    settings = SettingsRepository(db)
    stored = await settings.get("hidden_password")
    return {"password_set": stored is not None and bool(stored)}


@router.post("/hidden/set-password")
async def set_hidden_password(
    request: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set or update the hidden books password."""
    from app.repositories import SettingsRepository
    from app.security import encrypt_password

    password = request.get("password")
    if not password or len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    encrypted = encrypt_password(password)
    settings = SettingsRepository(db)
    await settings.set("hidden_password", encrypted)
    await db.flush()
    return {"message": "Password set successfully"}


@router.post("/hidden/verify-password")
async def verify_hidden_password(
    request: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify the hidden books password."""
    from app.repositories import SettingsRepository
    from app.security import verify_password as check_password

    password = request.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="Password required")

    settings = SettingsRepository(db)
    stored = await settings.get("hidden_password")
    if not stored:
        raise HTTPException(status_code=400, detail="No password set")

    if not check_password(password, stored):
        raise HTTPException(status_code=401, detail="Incorrect password")

    return {"verified": True}


@router.post("/hidden/reset-password")
async def reset_hidden_password(
    request: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset hidden books password. Requires current password."""
    from app.repositories import SettingsRepository
    from app.security import verify_password as check_password

    password = request.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="Current password required")

    settings = SettingsRepository(db)
    stored = await settings.get("hidden_password")
    if not stored:
        raise HTTPException(status_code=400, detail="No password set")

    if not check_password(password, stored):
        raise HTTPException(status_code=401, detail="Incorrect password")

    await settings.delete("hidden_password")
    await db.flush()
    return {"message": "Password reset successfully"}
