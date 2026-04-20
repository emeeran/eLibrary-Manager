"""Database connection and session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from fastapi import HTTPException

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
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
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
            logger.error(f"Database session error: {e}")
            raise DatabaseError("Database operation failed", {"error": str(e)}) from e
        finally:
            await session.close()

    async def init_db(self) -> None:
        """Initialize database schema.

        Creates all tables if they don't exist, then applies any pending
        column migrations for existing tables. Should be called on app startup.
        """
        try:
            # Ensure all models are registered with Base.metadata
            import app.models  # noqa: F401

            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

                # Apply migrations for new columns on existing tables
                await self._migrate(conn)

            logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise DatabaseError("Failed to initialize database", {"error": str(e)}) from e

    async def _migrate(self, conn) -> None:
        """Apply incremental schema migrations for existing tables."""
        from sqlalchemy import text, inspect

        def _apply_migrations(sync_conn):
            inspector = inspect(sync_conn)

            # Migration 1: Add storage_type column to books table
            if "books" in inspector.get_table_names():
                columns = {col["name"] for col in inspector.get_columns("books")}
                if "storage_type" not in columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE books ADD COLUMN storage_type "
                            "VARCHAR(10) NOT NULL DEFAULT 'local'"
                        )
                    )
                    logger.info("Migration: added storage_type column to books")

                if "rating" not in columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE books ADD COLUMN rating "
                            "INTEGER NOT NULL DEFAULT 0"
                        )
                    )
                    logger.info("Migration: added rating column to books")

        await conn.run_sync(_apply_migrations)

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

    Creates and manages a session directly without nesting async context
    managers, which avoids greenlet context tracking issues with concurrent
    requests under SQLAlchemy's async engine.

    Yields:
        AsyncSession: Database session for request handling

    Example:
        >>> @app.get("/books")
        ... async def list_books(db: AsyncSession = Depends(get_db)):
        ...     result = await db.execute(select(Book))
    """
    session = db_manager.session_factory()
    try:
        yield session
        await session.commit()
    except (DawnstarError, HTTPException):
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise DatabaseError("Database operation failed", {"error": str(e)}) from e
    finally:
        await session.close()
