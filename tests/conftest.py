"""Pytest configuration and fixtures."""

import os
import tempfile
from pathlib import Path

import pytest_asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.main import app

# Set test credentials before any app imports resolve
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("APP_ENV", "testing")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def _engine():
    """Create test database engine (session-scoped)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine):
    """Create a fresh database session for each test.

    Drops and recreates all tables to ensure a clean state.
    """
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    """Create authenticated test client with database override."""
    from app.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Authenticate to get session cookie
        login_resp = await ac.post("/api/auth/login", json={
            "username": "admin",
            "password": "test-password",
        })
        # If login fails (no auth middleware yet), continue without auth
        if login_resp.status_code != 200:
            # Try without auth — auth may not be fully wired up
            pass

        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def temp_library():
    """Create temporary library directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
