"""Settings and configuration routes."""

import asyncio
import os
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_engine import get_ai_orchestrator, reset_ai_orchestrator
from app.config import get_config
from app.database import get_db
from app.logging_config import get_logger
from app.repositories import SettingsRepository
from app.schemas import (
    AIConnectionTest,
    NASHealthResponse,
    PDFViewerStatus,
    PDFViewerToggle,
    SettingsCreate,
    SettingsResponse,
)


def _reinit_nas_backend(app: object, nas_enabled: bool, mount_path: str, host: str) -> None:
    """Reinitialize NAS backend and health monitor at runtime.

    Called when NAS settings are saved so changes take effect without restart.
    """
    from app.storage.nas import NASStorageBackend

    # Stop existing monitor
    old_monitor = getattr(app.state, "nas_monitor", None)
    if old_monitor:
        import asyncio

        try:
            asyncio.get_event_loop().create_task(old_monitor.stop())
        except RuntimeError:
            pass

    if nas_enabled and mount_path:
        backend = NASStorageBackend(mount_path=mount_path, host=host)
        app.state.nas_backend = backend

        from app.nas_health import NASHealthMonitor

        monitor = NASHealthMonitor(backend=backend, check_interval=60)
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            loop.create_task(monitor.start())
        except RuntimeError:
            pass
        app.state.nas_monitor = monitor
        logger.info(f"NAS backend reinitialized: {host}:{mount_path}")
    else:
        app.state.nas_backend = None
        app.state.nas_monitor = None
        logger.info("NAS backend disabled")


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
    calibre_web_url="",
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
        watch_changes=_bool("watch_changes")
        if _str("watch_changes") is not None
        else defaults["watch_changes"],
        page_layout=_str("page_layout") or defaults["page_layout"],
        text_align=_str("text_align") or defaults["text_align"],
        font_size=_int("font_size") or defaults["font_size"],
        font_family=_str("font_family") or defaults["font_family"],
        line_height=_str("line_height") or defaults["line_height"],
        theme=_str("theme") or defaults["theme"],
        tts_speed=_str("tts_speed") or defaults["tts_speed"],
        tts_pitch=_float("tts_pitch") if _str("tts_pitch") is not None else defaults["tts_pitch"],
        tts_engine=_str("tts_engine") or "edgetts",
        tts_voice=_str("tts_voice") or "",
        ai_provider=_str("ai_provider") or cfg.ai_default_provider,
        ollama_url=_str("ollama_url") or cfg.ollama_local_url,
        auto_flip=_bool("auto_flip") if _str("auto_flip") is not None else defaults["auto_flip"],
        flip_interval=_int("flip_interval") or defaults["flip_interval"],
        summary_length=_str("summary_length") or defaults["summary_length"],
        auto_summary=_bool("auto_summary")
        if _str("auto_summary") is not None
        else defaults["auto_summary"],
        nas_enabled=_bool("nas_enabled")
        if _str("nas_enabled") is not None
        else defaults["nas_enabled"],
        nas_host=_str("nas_host") or defaults["nas_host"],
        nas_share=_str("nas_share") or defaults["nas_share"],
        nas_mount_path=_str("nas_mount_path") or defaults["nas_mount_path"],
        nas_protocol=_str("nas_protocol") or defaults["nas_protocol"],
        nas_username=_str("nas_username") or defaults["nas_username"],
        nas_auto_mount=_bool("nas_auto_mount")
        if _str("nas_auto_mount") is not None
        else defaults["nas_auto_mount"],
        calibre_web_url=_str("calibre_web_url") or defaults["calibre_web_url"],
    )


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)) -> SettingsResponse:
    """Get current application settings from database."""
    repo = SettingsRepository(db)
    stored = await repo.get_all()
    return _build_response(stored)


@router.post("/settings")
async def save_settings(
    request: Request, settings: SettingsCreate, db: AsyncSession = Depends(get_db)
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

    # Reinitialize NAS backend if NAS settings changed
    if settings.nas_enabled is not None:
        nas_enabled = settings.nas_enabled
        nas_mount = settings.nas_mount_path or ""
        nas_host = settings.nas_host or ""
        _reinit_nas_backend(request.app, nas_enabled, nas_mount, nas_host)

    stored = await repo.get_all()
    return _build_response(stored)


@router.post("/settings/test-ai")
async def test_ai_connection(request: AIConnectionTest) -> dict:
    """Test AI provider connection."""
    try:
        if request.api_key:
            _apply_ai_credentials(request.provider, request.api_key)

        orchestrator = await get_ai_orchestrator()

        test_result = await orchestrator.generate_summary(
            book_id=1,
            chapter_index=0,
            content="This is a test of the AI connection. If you can see this, the connection is working properly.",
        )

        return {
            "status": "success",
            "provider": request.provider,
            "message": "Connection successful",
            "test_summary": test_result[:100] + "..." if len(test_result) > 100 else test_result,
        }

    except Exception as e:
        logger.error(f"AI connection test failed: {e}")
        raise HTTPException(
            status_code=400, detail={"error": "Connection failed", "message": str(e)}
        ) from e


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
    # Use the runtime NAS backend (initialized from DB settings on save)
    nas_backend = getattr(request.app.state, "nas_backend", None)
    if not nas_backend:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "NAS not configured",
                "message": "Enable NAS and set mount path first",
            },
        )

    result = await nas_backend.health_check()

    if result["healthy"]:
        return {"status": "success", "message": result["details"]}
    else:
        raise HTTPException(
            status_code=503,
            detail={"error": "NAS Unreachable", "message": result["details"]},
        )


# ---------------------------------------------------------------------- #
# Default PDF viewer (spec 014) — opt-in system registration
# ---------------------------------------------------------------------- #

_PDF_MIME = "application/pdf"
_DESKTOP_ID = "elibrary-manager.desktop"
_PDF_PREVIOUS_KEY = "pdf_viewer_previous_default"


async def _run_xdg_mime(*args: str) -> tuple[bool, str]:
    """Run ``xdg-mime`` off the event loop, as the service user.

    The service process already runs as the desktop user on personal
    installs (``ELIBRARY_RUN_USER``), so no privilege juggling here.

    Returns:
        (success, combined stdout/stderr output)
    """

    def _run() -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                ["xdg-mime", *args], capture_output=True, text=True, timeout=10
            )
            return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)

    return await asyncio.to_thread(_run)


@router.get("/settings/pdf-viewer", response_model=PDFViewerStatus)
async def get_pdf_viewer_status() -> PDFViewerStatus:
    """Report whether eLM is currently the registered PDF handler."""
    ok, current = await _run_xdg_mime("query", "default", _PDF_MIME)
    return PDFViewerStatus(
        available=ok,
        enabled=ok and current == _DESKTOP_ID,
        current=current,
        desktop=_DESKTOP_ID,
    )


@router.post("/settings/pdf-viewer")
async def set_pdf_viewer(
    payload: PDFViewerToggle, db: AsyncSession = Depends(get_db)
) -> dict:
    """Register (or restore) eLM as the system default PDF viewer.

    PDF registration is opt-in because it changes the handler for every PDF
    on the desktop. The previous handler is recorded on enable and restored
    on disable.

    Args:
        payload: ``{"enabled": bool}``
        db: Database session

    Returns:
        The resulting state, including which handler was displaced/restored.
    """
    if payload.enabled:
        ok, current = await _run_xdg_mime("query", "default", _PDF_MIME)
        if not ok:
            raise HTTPException(status_code=500, detail=f"xdg-mime query failed: {current}")
        if current == _DESKTOP_ID:
            # Already registered — don't clobber any saved previous handler
            return {"enabled": True, "previous": "", "restored": False, "already": True}
        await SettingsRepository(db).set_many({_PDF_PREVIOUS_KEY: current})
        ok, out = await _run_xdg_mime("default", _DESKTOP_ID, _PDF_MIME)
        if not ok:
            raise HTTPException(status_code=500, detail=f"xdg-mime default failed: {out}")
        return {"enabled": True, "previous": current, "restored": False}

    stored = await SettingsRepository(db).get_all()
    previous = stored.get(_PDF_PREVIOUS_KEY, "")
    if not previous:
        return {
            "enabled": False,
            "previous": "",
            "restored": False,
            "detail": "No previous PDF handler recorded — association left unchanged",
        }
    ok, out = await _run_xdg_mime("default", previous, _PDF_MIME)
    if not ok:
        raise HTTPException(status_code=500, detail=f"xdg-mime default failed: {out}")
    return {"enabled": False, "previous": previous, "restored": True}
