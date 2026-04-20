"""Authentication routes for eLibrary Manager.

Provides login, logout, and auth status endpoints.
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session,
    destroy_session,
    validate_session,
    verify_credentials,
)
from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Serve the login page.

    If already authenticated, redirect to home.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token and validate_session(token):
        return RedirectResponse(url="/", status_code=302)

    from fastapi.templating import Jinja2Templates

    config = get_config()
    templates = Jinja2Templates(directory="frontend/templates")
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/api/auth/login")
async def login(request: Request, response: Response) -> JSONResponse:
    """Validate credentials and set session cookie.

    Expects JSON body: {"username": "...", "password": "..."}
    or just {"password": "..."} for backwards compatibility.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid request body"},
        )

    username = body.get("username", "admin")
    password = body.get("password", "")

    if not password:
        return JSONResponse(
            status_code=401,
            content={"error": "Password required"},
        )

    if not verify_credentials(username, password):
        logger.warning("Failed login attempt for user: %s", username)
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid credentials"},
        )

    token = create_session(username)

    response = JSONResponse(
        status_code=200,
        content={"message": "Login successful"},
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    logger.info("User %s logged in successfully", username)
    return response


@router.post("/api/auth/logout")
async def logout(request: Request) -> JSONResponse:
    """Clear session and remove cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        destroy_session(token)

    response = JSONResponse(
        status_code=200,
        content={"message": "Logged out"},
    )
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/api/auth/status")
async def auth_status(request: Request) -> JSONResponse:
    """Return current authentication status."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    authenticated = bool(token and validate_session(token))
    return JSONResponse(
        status_code=200,
        content={"authenticated": authenticated},
    )
