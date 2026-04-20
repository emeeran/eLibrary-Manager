"""Settings and configuration routes."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_engine import get_ai_orchestrator, reset_ai_orchestrator
from app.config import get_config
from app.database import get_db
from app.logging_config import get_logger
from app.repositories import SettingsRepository
from app.schemas import AIConnectionTest, NASHealthResponse, SettingsCreate, SettingsResponse


def _apply_ai_credentials(provider: str, api_key: str | None = None) -> None:
    """Set AI provider env var and reset orchestrator so changes take effect."""
    if api_key:
        if provider == "google":
            os.environ["GOOGLE_API_KEY"] = api_key
        elif provider == "groq":
            os.environ["GROQ_API_KEY"] = api_key

    reset_ai_orchestrator()


router = APIRouter(prefix="/api", tags=["settings"])
logger = get_logger(__name__)

# Default settings
DEFAULTS: SettingsResponse = SettingsResponse(
    library_path="./library",
    auto_scan=False,
    watch_changes=False,
    page_layout="single",
    text_align="justify",
    font_size=100,
    font_family="georgia",
    line_height="1.8",
    theme="day",
    tts_speed="1.0",
    tts_pitch=1.0,
    ai_provider="auto",
    ollama_url="http://localhost:11434",
    auto_flip=False,
    flip_interval=30,
    summary_length="medium",
    auto_summary=False,
    nas_enabled=False,
    nas_host="",
    nas_share="",
    nas_mount_path="",
    nas_protocol="smb",
    nas_username="",
    nas_auto_mount=False,
)


def _build_response(stored: dict[str, str]) -> SettingsResponse:
    """Build SettingsResponse from stored key-value pairs merged with defaults."""
    cfg = get_config()
    defaults = DEFAULTS.model_dump()

    def _str(key: str) -> str | None:
        return stored.get(key)

    def _bool(key: str) -> bool | None:
        v = stored.get(key)
        if v is None:
            return None
        return v.lower() in ("true", "1", "yes")

    def _int(key: str) -> int | None:
        v = stored.get(key)
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    def _float(key: str) -> float | None:
        v = stored.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    return SettingsResponse(
        library_path=_str("library_path") or cfg.library_path,
        auto_scan=_bool("auto_scan") if _str("auto_scan") is not None else defaults["auto_scan"],
        watch_changes=_bool("watch_changes") if _str("watch_changes") is not None else defaults["watch_changes"],
        page_layout=_str("page_layout") or defaults["page_layout"],
        text_align=_str("text_align") or defaults["text_align"],
        font_size=_int("font_size") or defaults["font_size"],
        font_family=_str("font_family") or defaults["font_family"],
        line_height=_str("line_height") or defaults["line_height"],
        theme=_str("theme") or defaults["theme"],
        tts_speed=_str("tts_speed") or defaults["tts_speed"],
        tts_pitch=_float("tts_pitch") if _str("tts_pitch") is not None else defaults["tts_pitch"],
        ai_provider=_str("ai_provider") or cfg.ai_default_provider,
        ollama_url=_str("ollama_url") or cfg.ollama_local_url,
        auto_flip=_bool("auto_flip") if _str("auto_flip") is not None else defaults["auto_flip"],
        flip_interval=_int("flip_interval") or defaults["flip_interval"],
        summary_length=_str("summary_length") or defaults["summary_length"],
        auto_summary=_bool("auto_summary") if _str("auto_summary") is not None else defaults["auto_summary"],
        nas_enabled=_bool("nas_enabled") if _str("nas_enabled") is not None else defaults["nas_enabled"],
        nas_host=_str("nas_host") or defaults["nas_host"],
        nas_share=_str("nas_share") or defaults["nas_share"],
        nas_mount_path=_str("nas_mount_path") or defaults["nas_mount_path"],
        nas_protocol=_str("nas_protocol") or defaults["nas_protocol"],
        nas_username=_str("nas_username") or defaults["nas_username"],
        nas_auto_mount=_bool("nas_auto_mount") if _str("nas_auto_mount") is not None else defaults["nas_auto_mount"],
    )


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)) -> SettingsResponse:
    """Get current application settings from database."""
    repo = SettingsRepository(db)
    stored = await repo.get_all()
    return _build_response(stored)


@router.post("/settings")
async def save_settings(
    settings: SettingsCreate,
    db: AsyncSession = Depends(get_db)
) -> SettingsResponse:
    """Save application settings to database."""
    repo = SettingsRepository(db)

    data = settings.model_dump(exclude_none=True)

    # Handle AI API key separately — store in env for runtime, but don't persist to DB
    if settings.ai_api_key:
        _apply_ai_credentials(settings.ai_provider, settings.ai_api_key)

    # Remove sensitive fields from plain persistence
    data.pop("ai_api_key", None)

    # Handle NAS password encryption
    nas_password = data.pop("nas_password", None)
    if nas_password:
        from app.security import encrypt_value
        data["nas_password_encrypted"] = encrypt_value(nas_password)

    await repo.set_many(data)

    stored = await repo.get_all()
    return _build_response(stored)


@router.post("/settings/test-ai")
async def test_ai_connection(request: AIConnectionTest) -> dict:
    """Test AI provider connection."""
    try:
        if request.api_key:
            _apply_ai_credentials(request.provider, request.api_key)

        orchestrator = get_ai_orchestrator()

        test_result = await orchestrator.generate_summary(
            book_id=1,
            chapter_index=0,
            content="This is a test of the AI connection. If you can see this, the connection is working properly.",
        )

        return {
            "status": "success",
            "provider": request.provider,
            "message": "Connection successful!",
            "test_summary": test_result[:100] + "..." if len(test_result) > 100 else test_result,
        }

    except Exception as e:
        logger.error(f"AI connection test failed: {e}")
        raise HTTPException(
            status_code=400,
            detail={"error": "Connection failed", "message": str(e)}
        )


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0"
    }


@router.get("/settings/nas-health", response_model=NASHealthResponse)
async def get_nas_health(request: Request) -> NASHealthResponse:
    """Get current NAS mount health status."""
    nas_backend = getattr(request.app.state, "nas_backend", None)
    if not nas_backend:
        return NASHealthResponse(
            healthy=False,
            mount_path="",
            details="NAS not configured",
        )
    health = await nas_backend.health_check()
    return NASHealthResponse(
        healthy=health["healthy"],
        last_check=nas_backend.status.get("last_check"),
        mount_path=nas_backend.mount_path,
        details=health.get("details"),
    )


@router.post("/settings/test-nas")
async def test_nas_connection(request: Request) -> dict:
    """Test NAS mount connectivity on demand."""
    config = get_config()
    if not config.nas_mount_path:
        raise HTTPException(
            status_code=400,
            detail={"error": "NAS not configured", "message": "Set NAS mount path first"},
        )

    from app.storage.nas import NASStorageBackend
    backend = NASStorageBackend(
        mount_path=config.nas_mount_path,
        host=config.nas_host,
    )
    result = await backend.health_check()

    if result["healthy"]:
        return {"status": "success", "message": result["details"]}
    else:
        raise HTTPException(
            status_code=503,
            detail={"error": "NAS Unreachable", "message": result["details"]},
        )
