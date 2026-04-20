"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from fastapi import FastAPI, Request, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import SESSION_COOKIE_NAME, validate_session
from app.config import get_config
from app.database import db_manager
from app.exceptions import (
    DawnstarError,
    EbookParsingError,
    RateLimitError,
    ResourceNotFoundError,
)
from app.logging_config import get_logger, setup_logging
from app.middleware import LoggingMiddleware
from app.rate_limit import RateLimitMiddleware

# Import route modules
from app.routes import ai_tts, auth, library, reader, settings, stats

# Setup logging
setup_logging()
logger = get_logger(__name__)
config = get_config()


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control headers to static assets."""

    CACHE_RULES = {
        "/static/": "public, max-age=86400",       # 1 day
        "/covers/": "public, max-age=86400",        # 1 day
        "/book-images/": "public, max-age=604800",  # 7 days
    }

    async def dispatch(self, request: StarletteRequest, call_next):
        response: StarletteResponse = await call_next(request)
        path = request.url.path
        for prefix, cache_value in self.CACHE_RULES.items():
            if path.startswith(prefix):
                response.headers["Cache-Control"] = cache_value
                break
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """Session-based authentication middleware.

    Protects /api/* routes (except /api/auth/*) and page routes.
    Skips auth for static files, health check, and auth endpoints.
    """

    # Paths that never require authentication
    PUBLIC_PATHS = {
        "/login",
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/status",
    }

    # Prefixes that never require authentication
    PUBLIC_PREFIXES = (
        "/static/",
        "/covers/",
        "/book-images/",
        "/api/auth/",
    )

    async def dispatch(self, request: StarletteRequest, call_next):
        # Skip auth in testing mode
        import os
        if os.environ.get("APP_ENV") == "testing":
            return await call_next(request)

        path = request.url.path

        # Skip auth for public paths
        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth for public prefixes
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Check session cookie
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token and validate_session(token):
            return await call_next(request)

        # API routes return 401
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Authentication required"},
            )

        # Page routes redirect to login
        return RedirectResponse(url="/login", status_code=302)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events including NAS health monitoring.
    """
    # Startup
    logger.info("Starting eBook Manager")
    await db_manager.init_db()
    logger.info("Database initialized")

    # Start NAS health monitor if enabled
    if config.nas_enabled and config.nas_mount_path:
        from app.nas_health import NASHealthMonitor
        from app.storage.nas import NASStorageBackend

        nas_backend = NASStorageBackend(
            mount_path=config.nas_mount_path,
            host=config.nas_host,
        )
        nas_monitor = NASHealthMonitor(backend=nas_backend, check_interval=60)
        await nas_monitor.start()
        app.state.nas_monitor = nas_monitor
        app.state.nas_backend = nas_backend
        logger.info("NAS health monitor initialized")
    else:
        app.state.nas_monitor = None
        app.state.nas_backend = None

    yield

    # Shutdown
    if hasattr(app.state, "nas_monitor") and app.state.nas_monitor:
        await app.state.nas_monitor.stop()
    logger.info("Shutting down eBook Manager")
    await db_manager.close()


# Create FastAPI app
app = FastAPI(
    title="eLibrary Manager",
    description="Lightweight ebook manager with AI summarization",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware (order matters: outermost first)
app.add_middleware(GZipMiddleware, minimum_size=500)  # Compress responses > 500 bytes
app.add_middleware(CacheControlMiddleware)             # Cache-Control for static assets
app.add_middleware(AuthMiddleware)                     # Session-based auth
app.add_middleware(RateLimitMiddleware)                 # Per-IP rate limiting
app.add_middleware(LoggingMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount("/covers", StaticFiles(directory=config.covers_path), name="covers")
app.mount("/book-images", StaticFiles(directory=config.book_images_path), name="book-images")

# Setup templates
templates = Jinja2Templates(directory="frontend/templates")

# Include route modules
app.include_router(auth.router)
app.include_router(library.router)
app.include_router(reader.router)
app.include_router(settings.router)
app.include_router(ai_tts.router)
app.include_router(stats.router)


@app.get("/api/health")
async def health_check() -> dict:
    """Health check endpoint for Docker and monitoring."""
    return {"status": "ok"}

# Exception handlers (specific before generic)
@app.exception_handler(ResourceNotFoundError)
async def not_found_handler(
    request: Request,
    exc: ResourceNotFoundError
) -> JSONResponse:
    """Handle resource not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "Not Found",
            "message": exc.message
        }
    )


@app.exception_handler(EbookParsingError)
async def parsing_exception_handler(
    request: Request,
    exc: EbookParsingError
) -> JSONResponse:
    """Handle ebook parsing errors — file missing, corrupted, DRM, etc."""
    msg = exc.message.lower()
    if "no such file" in msg or "not found" in msg or "does not exist" in msg:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "File Not Found",
                "message": f"The book file could not be found. It may have been moved or deleted. {exc.message}"
            }
        )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": type(exc).__name__,
            "message": exc.message,
            "details": exc.details
        }
    )


@app.exception_handler(RateLimitError)
async def rate_limit_handler(
    request: Request,
    exc: RateLimitError
) -> JSONResponse:
    """Handle rate limit errors."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "Rate Limit Exceeded",
            "message": exc.message
        }
    )


@app.exception_handler(DawnstarError)
async def dawnstar_exception_handler(
    request: Request,
    exc: DawnstarError
) -> JSONResponse:
    """Handle all other Dawnstar-specific exceptions."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": type(exc).__name__,
            "message": exc.message,
            "details": exc.details
        }
    )
@app.get("/", response_class=HTMLResponse)
async def library_home(request: Request) -> HTMLResponse:
    """Render library home page."""
    return templates.TemplateResponse(
        "library.html",
        {"request": request}
    )


@app.get("/reader/{book_id}", response_class=HTMLResponse)
async def reader_page(book_id: int, request: Request) -> HTMLResponse:
    """Render reader page for a book.

    Args:
        book_id: Book primary key
        request: FastAPI request
    """
    return templates.TemplateResponse(
        "reader.html",
        {"request": request, "book_id": book_id}
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Render settings page.

    Args:
        request: FastAPI request
    """
    return templates.TemplateResponse(
        "settings.html",
        {"request": request}
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.app_host,
        port=config.app_port,
        reload=config.debug
    )
