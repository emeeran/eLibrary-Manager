"""Database connection and session management."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_config
from app.exceptions import DatabaseError, DawnstarError
from app.logging_config import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class DatabaseManager:
    """Manages database connections and sessions.

    This class provides a singleton interface to the database, ensuring
    connection pooling and proper resource management.
    """

    def __init__(self) -> None:
        """Initialize database manager with configuration."""
        self.config = get_config()
        self._engine = None
        self._session_factory = None

    @property
    def engine(self):
        """Lazy-initialize database engine."""
        if self._engine is None:
            from sqlalchemy import event

            self._engine = create_async_engine(
                self.config.database_url,
                echo=self.config.debug,
                pool_size=self.config.db_pool_size,
                max_overflow=self.config.db_max_overflow,
                connect_args={"check_same_thread": False}  # SQLite specific
            )

            # SQLite performance pragmas
            @event.listens_for(self._engine.sync_engine, "connect")
            def _set_sqlite_pragmas(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
                cursor.execute("PRAGMA temp_store=MEMORY")
                mmap_size = int(os.environ.get("DB_MMAP_SIZE", 33554432))  # 32MB default
                cursor.execute(f"PRAGMA mmap_size={mmap_size}")
                cursor.close()

            logger.info(f"Database engine created: {self.config.database_url}")
        return self._engine

    @property
    def session_factory(self):
        """Lazy-initialize session factory."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False
            )
        return self._session_factory

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional scope for database operations.

        Yields:
            AsyncSession: Database session with automatic cleanup

        Example:
            >>> async with db_manager.get_session() as session:
            ...     result = await session.execute(query)
        """
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except DawnstarError:
            await session.rollback()
            raise
        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            logger.exception("Database session error: %s", e)
            raise DatabaseError("Database operation failed", {"error": str(e)}) from e
        finally:
            await session.close()

    async def init_db(self) -> None:
        """Prepare the database for migrations.

        Ensures the database file's parent directory exists and imports all
        models so ``Base.metadata`` is fully populated. Schema creation itself
        is owned by Alembic (see the lifespan in ``app.main``) so that model and
        migration definitions can never silently drift apart.
        """
        try:
            # Ensure all models are registered with Base.metadata
            import app.models  # noqa: F401

            # Ensure the SQLite database file's directory exists.
            db_path = self.config.database_url.split("///")[-1]
            db_dir = os.path.dirname(os.path.abspath(db_path))
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            logger.info("Database prepared for migrations")
        except Exception as e:
            logger.error(f"Database preparation failed: {e}")
            raise DatabaseError("Failed to prepare database", {"error": str(e)}) from e

    async def close(self) -> None:
        """Close database connections.

        Should be called on app shutdown.
        """
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.

    Thin wrapper around :meth:`DatabaseManager.get_session` so all transaction
    semantics (commit / rollback / exception mapping) live in exactly one place.

    Yields:
        AsyncSession: Database session for request handling

    Example:
        >>> @app.get("/books")
        ... async def list_books(db: AsyncSession = Depends(get_db)):
        ...     result = await db.execute(select(Book))
    """
    async with db_manager.get_session() as session:
        yield session
