"""AI provider and Text-to-Speech routes.

TTS Fallback Strategy:
1. EdgeTTS (server-side) - Default, high quality neural voices
2. Browser Web Speech API - Client-side fallback
3. gTTS (server-side) - Final fallback
"""

from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

MAX_TTS_TEXT_LENGTH = 50000  # characters
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.database import get_db
from app.edgetts_service import EdgeTTSError, get_edgetts_service
from app.gtts_service import GTTSError, get_gtts_service
from app.logging_config import get_logger
from app.services import ReaderService

router = APIRouter(prefix="/api", tags=["ai", "tts"])
logger = get_logger(__name__)
config = get_config()

# TTS Engine Constants
ENGINE_EDGETTS = "edgetts"
ENGINE_BROWSER = "browser"
ENGINE_GTTS = "gtts"


# ============================================
# AI PROVIDER ENDPOINTS
# ============================================

@router.get("/ai/providers")
async def list_ai_providers(db: AsyncSession = Depends(get_db)) -> dict:
    """List AI providers and their status.

    Returns:
        Providers status dictionary
    """
    service = ReaderService(db)
    providers = await service.get_ai_providers_status()
    active = await service.get_active_ai_provider()

    return {
        "providers": providers,
        "active_provider": active,
        "default_provider": config.ai_default_provider
    }


@router.get("/ai/providers/active")
async def get_active_provider(db: AsyncSession = Depends(get_db)) -> dict:
    """Get currently active AI provider.

    Returns:
        Active provider name
    """
    service = ReaderService(db)
    active = await service.get_active_ai_provider()

    return {
        "active_provider": active
    }


@router.post("/ai/providers/switch")
async def switch_ai_provider(
    provider_name: str,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Manually switch AI provider.

    Args:
        provider_name: Provider name to switch to
        db: Database session

    Returns:
        New provider configuration
    """
    service = ReaderService(db)
    result = await service.switch_ai_provider(provider_name)

    return result


# ============================================
# TEXT-TO-SPEECH ENDPOINTS
# ============================================

@router.get("/tts/engines")
async def get_tts_engines() -> dict:
    """Get available TTS engines with their status.

    Returns:
        Dictionary with available engines and default
    """
    return {
        "engines": [
            {
                "id": ENGINE_EDGETTS,
                "name": "EdgeTTS (Neural)",
                "description": "High-quality neural voices from Microsoft Edge",
                "is_server": True
            },
            {
                "id": ENGINE_BROWSER,
                "name": "Browser Speech",
                "description": "Built-in browser text-to-speech",
                "is_server": False
            },
            {
                "id": ENGINE_GTTS,
                "name": "Google TTS",
                "description": "Basic text-to-speech from Google",
                "is_server": True
            }
        ],
        "default_engine": ENGINE_EDGETTS,
        "fallback_order": [ENGINE_EDGETTS, ENGINE_BROWSER, ENGINE_GTTS]
    }


@router.get("/tts/voices")
async def get_tts_voices(engine: str = ENGINE_EDGETTS) -> dict:
    """Get available voices for the specified TTS engine.

    Args:
        engine: TTS engine (edgetts, browser, gtts)

    Returns:
        Dictionary with list of voices and default
    """
    if engine == ENGINE_EDGETTS:
        edgetts_service = get_edgetts_service()
        voices = await edgetts_service.get_voices()
        return {
            "engine": ENGINE_EDGETTS,
            "voices": voices,
            "default_voice": edgetts_service.get_default_voice()
        }
    elif engine == ENGINE_GTTS:
        gtts_service = get_gtts_service()
        voices = await gtts_service.get_voices()
        return {
            "engine": ENGINE_GTTS,
            "voices": voices,
            "default_voice": gtts_service.get_default_voice()
        }
    else:
        # Browser voices are loaded client-side
        return {
            "engine": ENGINE_BROWSER,
            "voices": [],
            "default_voice": None,
            "note": "Browser voices are loaded client-side"
        }


@router.post("/tts/stream")
async def stream_speech(request: Request) -> StreamingResponse:
    """Stream speech audio in real-time using EdgeTTS.

    Returns MP3 audio chunks as they're generated, enabling instant playback.
    Falls back to buffering the full audio via gTTS if EdgeTTS fails.

    Expects JSON body:
        text: Text to synthesize
        voice: Voice ID (optional)
        rate: Playback rate 0.5-2.0 (optional)
        pitch: Pitch adjustment (optional)
    """
    try:
        body = await request.json()
        text = body.get("text", "")
        voice = body.get("voice", "en-US-JennyNeural")
        rate = body.get("rate", 1.0)
        pitch = body.get("pitch", "+0Hz")

        if not text:
            raise HTTPException(status_code=400, detail="text field is required")

        if len(text) > MAX_TTS_TEXT_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Text too long ({len(text)} chars). Max is {MAX_TTS_TEXT_LENGTH}.",
            )

        try:
            rate = float(rate)
        except (TypeError, ValueError):
            rate = 1.0

        edgetts_service = get_edgetts_service()

        async def _generate() -> AsyncGenerator[bytes, None]:
            try:
                async for chunk in edgetts_service.stream_audio(
                    text=text, voice=voice, rate=rate, pitch=pitch
                ):
                    yield chunk
            except Exception as e:
                logger.warning(f"EdgeTTS stream failed: {e}")
                try:
                    gtts_service = get_gtts_service()
                    audio_data = await gtts_service.text_to_speech(
                        text=text, voice=voice, rate=str(rate), pitch=pitch
                    )
                    yield audio_data
                except Exception as fallback_err:
                    logger.error(f"TTS fallback also failed: {fallback_err}")

        return StreamingResponse(
            _generate(),
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-cache",
                "X-TTS-Engine": ENGINE_EDGETTS,
                "Accept-Ranges": "none",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS stream error: {e}")
        raise HTTPException(status_code=500, detail=f"Stream failed: {e}")


@router.post("/tts/synthesize")
async def synthesize_speech(
    request: Request
) -> Response:
    """Synthesize speech from text using the specified engine with fallback.

    Expects JSON body:
        text: Text to synthesize
        voice: Voice ID or language code
        rate: Playback rate 0.5-2.0 (optional, defaults to 1.0)
        pitch: Pitch adjustment (optional, defaults to "+0Hz")
        engine: TTS engine to use (optional, defaults to edgetts with fallback)

    Returns:
        MP3 audio response

    Fallback order:
        1. EdgeTTS (if engine is edgetts or not specified)
        2. gTTS (if EdgeTTS fails)
    """
    try:
        body = await request.json()
        text = body.get("text", "")
        voice = body.get("voice", "en")
        rate = body.get("rate", 1.0)
        pitch = body.get("pitch", "+0Hz")
        engine = body.get("engine", ENGINE_EDGETTS)

        if not text:
            raise HTTPException(
                status_code=400,
                detail="text field is required"
            )

        if len(text) > MAX_TTS_TEXT_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Text too long ({len(text)} chars). Maximum is {MAX_TTS_TEXT_LENGTH} characters."
            )

        # Normalize rate to float
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            rate = 1.0

        # Try the requested engine first
        if engine == ENGINE_EDGETTS or engine == ENGINE_GTTS:
            if engine == ENGINE_EDGETTS:
                # Try EdgeTTS first
                try:
                    edgetts_service = get_edgetts_service()
                    audio_data = await edgetts_service.generate_audio(
                        text=text,
                        voice=voice,
                        rate=rate,
                        pitch=pitch
                    )
                    return _audio_response(audio_data, ENGINE_EDGETTS)
                except EdgeTTSError as e:
                    logger.warning(f"EdgeTTS failed, falling back to gTTS: {e}")
                    # Fall through to gTTS
                except Exception as e:
                    logger.warning(f"EdgeTTS failed with unexpected error, falling back to gTTS: {e}")

            # Try gTTS (either requested or as fallback)
            try:
                gtts_service = get_gtts_service()
                audio_data = await gtts_service.text_to_speech(
                    text=text,
                    voice=voice,
                    rate=str(rate),
                    pitch=pitch
                )
                return _audio_response(audio_data, ENGINE_GTTS)
            except GTTSError as e:
                logger.error(f"gTTS synthesis failed: {e}")
                raise
            except Exception as e:
                logger.error(f"gTTS unexpected error: {e}")
                raise

        elif engine == ENGINE_BROWSER:
            # Browser TTS is handled client-side, return error
            raise HTTPException(
                status_code=400,
                detail="Browser TTS is handled client-side. Use Web Speech API directly."
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown engine: {engine}"
            )

    except (EdgeTTSError, GTTSError) as e:
        logger.error(f"TTS synthesis error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Synthesis failed",
                "message": e.message,
                "details": e.details
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Synthesis failed: {str(e)}"
        )


def _audio_response(audio_data: bytes, engine: str) -> Response:
    """Create an audio response with appropriate headers."""
    return Response(
        content=audio_data,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"attachment; filename=speech_{engine}.mp3",
            "Cache-Control": "no-cache",
            "X-TTS-Engine": engine
        }
    )
