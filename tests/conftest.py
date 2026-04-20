"""Pytest configuration and fixtures."""

import tempfile
from pathlib import Path

import pytest_asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from typer.testing import CliRunner

from app.database import Base, db_manager
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_session():
    """Create test database session.

    Returns:
        AsyncSession: Database session with automatic cleanup
    """
    # Use in-memory SQLite for testing
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )

    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Provide session
    async with async_session() as session:
        yield session

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """Create test client with database override.

    Returns:
        AsyncClient: Test client for API testing
    """
    from app.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def temp_library():
    """Create temporary library directory.

    Returns:
        Path: Temporary directory for ebook files
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_epub_path(temp_library):
    """Create a sample EPUB file for testing.

    Returns:
        Path: Path to sample EPUB file
    """
    # For now, just create a placeholder
    epub_path = temp_library / "test_book.epub"
    epub_path.write_text("Sample EPUB content")
    return epub_path
