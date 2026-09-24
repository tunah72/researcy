from fastapi import APIRouter, Request, Response
from starlette.responses import RedirectResponse

from ..db import get_conn
from ..errors import APIError
from .oauth import consume_transaction, create_authorization, exchange_and_validate
from .sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    cookie_secure,
    get_current_user,
    issue_session,
    require_csrf,
    session_lookup,
)

router = APIRouter()
OAUTH_COOKIE = "researcy_oauth"
OAUTH_COOKIE_PATH = "/auth/google/callback"
OAUTH_ERROR_REDIRECT = "/sign-in?error=oauth"


def _redirect(request: Request, location: str) -> RedirectResponse:
    response = RedirectResponse(location, status_code=303)
    response.delete_cookie(
        OAUTH_COOKIE,
        path=OAUTH_COOKIE_PATH,
        secure=cookie_secure(request, request.app.state.settings),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/auth/google/start")
def google_start(request: Request):
    settings = request.app.state.settings
    try:
        with get_conn() as conn:
            authorization_url, correlation = create_authorization(conn, settings)
    except Exception:
        return _redirect(request, OAUTH_ERROR_REDIRECT)

    response = RedirectResponse(authorization_url, status_code=302)
    response.set_cookie(
        OAUTH_COOKIE,
        correlation,
        max_age=10 * 60,
        path=OAUTH_COOKIE_PATH,
        secure=cookie_secure(request, settings),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/auth/google/callback")
def google_callback(request: Request, code: str | None = None, state: str | None = None):
    try:
        with get_conn() as conn:
            transaction = consume_transaction(
                conn, state, request.cookies.get(OAUTH_COOKIE)
            )
    except Exception:
        return _redirect(request, OAUTH_ERROR_REDIRECT)

    if transaction is None or not code or request.query_params.get("error"):
        return _redirect(request, OAUTH_ERROR_REDIRECT)

    nonce, verifier = transaction
    settings = request.app.state.settings
    try:
        identity = exchange_and_validate(settings, code, nonce, verifier)
        if identity is None:
            return _redirect(request, OAUTH_ERROR_REDIRECT)
        with get_conn() as conn:
            user_id = conn.execute(
                """
                INSERT INTO users (issuer, sub, email, display_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (issuer, sub) DO UPDATE
                SET email = EXCLUDED.email, display_name = EXCLUDED.display_name
                RETURNING id
                """,
                (
                    identity["issuer"],
                    identity["sub"],
                    identity["email"],
                    identity["display_name"],
                ),
            ).fetchone()[0]
            raw_session, raw_csrf = issue_session(
                conn, user_id, settings.session_lookup_key
            )
    except Exception:
        return _redirect(request, OAUTH_ERROR_REDIRECT)

    response = _redirect(request, "/library")
    secure = cookie_secure(request, settings)
    response.set_cookie(
        SESSION_COOKIE,
        raw_session,
        max_age=12 * 60 * 60,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        raw_csrf,
        max_age=12 * 60 * 60,
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )
    return response


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    if not request.cookies.get(SESSION_COOKIE):
        raise APIError(401, "UNAUTHENTICATED", "Authentication is required.")
    settings = request.app.state.settings
    with get_conn() as conn:
        user_id = get_current_user(request, conn)
        require_csrf(request, conn, user_id)
        raw_session = request.cookies[SESSION_COOKIE]
        conn.execute(
            "UPDATE sessions SET revoked = TRUE WHERE token_hash = %s AND owner_id = %s",
            (session_lookup(raw_session, settings.session_lookup_key), user_id),
        )

    response = Response(status_code=204)
    secure = cookie_secure(request, settings)
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", secure=secure, httponly=False, samesite="lax"
    )
    return response


@router.get("/api/me")
def me(request: Request):
    if not request.cookies.get(SESSION_COOKIE):
        raise APIError(401, "UNAUTHENTICATED", "Authentication is required.")
    with get_conn() as conn:
        user_id = get_current_user(request, conn)
        row = conn.execute(
            "SELECT email, display_name FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if row is None:
        raise APIError(401, "UNAUTHENTICATED", "Authentication is required.")
    return {
        "id": str(user_id),
        "email": row[0],
        "name": row[1],
        "request_id": request.state.request_id,
    }
