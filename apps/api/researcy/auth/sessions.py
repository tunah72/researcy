import hmac
import secrets
from uuid import UUID

from fastapi import Request

from ..config import Settings
from ..errors import APIError

SESSION_COOKIE = "researcy_session"
CSRF_COOKIE = "researcy_csrf"
SESSION_IDLE_SECONDS = 30 * 60
SESSION_ABSOLUTE_SECONDS = 12 * 60 * 60


def session_lookup(raw_token: str, key: bytes) -> bytes:
    return hmac.digest(key, raw_token.encode(), "sha256")


def _csrf_verifier(raw_csrf: str, key: bytes) -> bytes:
    return hmac.digest(key, b"csrf:" + raw_csrf.encode(), "sha256")


def _key(request: Request) -> bytes:
    key = request.app.state.settings.session_lookup_key
    if len(key) < 32:
        raise APIError(401, "UNAUTHENTICATED", "Authentication is required.")
    return key


def _forbidden() -> APIError:
    return APIError(403, "CSRF_REJECTED", "The request could not be verified.")


def get_current_user(request: Request, conn) -> UUID:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise APIError(401, "UNAUTHENTICATED", "Authentication is required.")

    token_hash = session_lookup(raw_token, _key(request))
    row = conn.execute(
        """
        UPDATE sessions
        SET idle_expires_at = LEAST(
            absolute_expires_at, CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
        )
        WHERE token_hash = %s
          AND revoked = FALSE
          AND idle_expires_at > CURRENT_TIMESTAMP
          AND absolute_expires_at > CURRENT_TIMESTAMP
        RETURNING owner_id
        """,
        (SESSION_IDLE_SECONDS, token_hash),
    ).fetchone()
    if row is None:
        raise APIError(401, "UNAUTHENTICATED", "Authentication is required.")
    return row[0]


def require_csrf(request: Request, conn, user_id: UUID) -> None:
    origin = request.headers.get("origin")
    if origin not in request.app.state.settings.trusted_origins:
        raise _forbidden()

    raw_token = request.cookies.get(SESSION_COOKIE)
    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    csrf_header = request.headers.get("x-csrf-token")
    if not raw_token or not csrf_cookie or not csrf_header:
        raise _forbidden()

    if not hmac.compare_digest(csrf_cookie.encode(), csrf_header.encode()):
        raise _forbidden()

    key = _key(request)
    row = conn.execute(
        """
        SELECT csrf_verifier
        FROM sessions
        WHERE token_hash = %s
          AND owner_id = %s
          AND revoked = FALSE
          AND idle_expires_at > CURRENT_TIMESTAMP
          AND absolute_expires_at > CURRENT_TIMESTAMP
        """,
        (session_lookup(raw_token, key), user_id),
    ).fetchone()
    if row is None or not hmac.compare_digest(
        _csrf_verifier(csrf_cookie, key), bytes(row[0]) if row else b""
    ):
        raise _forbidden()


def issue_session(conn, user_id, key: bytes) -> tuple[str, str]:
    if len(key) < 32:
        raise APIError(503, "AUTH_NOT_CONFIGURED", "Sign-in is temporarily unavailable.")

    raw_token = secrets.token_urlsafe(32)
    raw_csrf = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO sessions (
            token_hash, owner_id, csrf_verifier, idle_expires_at, absolute_expires_at
        ) VALUES (
            %s, %s, %s,
            CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
            CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
        )
        """,
        (
            session_lookup(raw_token, key),
            user_id,
            _csrf_verifier(raw_csrf, key),
            SESSION_IDLE_SECONDS,
            SESSION_ABSOLUTE_SECONDS,
        ),
    )
    return raw_token, raw_csrf


def cookie_secure(request: Request, settings: Settings) -> bool:
    if settings.cookie_secure or request.url.scheme == "https":
        return True
    host = request.url.hostname or ""
    if settings.app_env == "test":
        return False
    return not (settings.app_env == "development" and host in {"localhost", "127.0.0.1", "::1"})


