import hmac
import secrets
import time
from hashlib import sha256
from urllib.parse import urlsplit

from authlib.integrations.base_client.sync_app import OAuth2Mixin
from authlib.integrations.base_client.sync_openid import OpenIDMixin
from authlib.integrations.httpx_client import OAuth2Client

from ..config import Settings

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_ISSUER = "https://accounts.google.com"
GOOGLE_ISSUERS = (GOOGLE_ISSUER, "accounts.google.com")
OAUTH_TRANSACTION_SECONDS = 10 * 60


def _valid_callback_uri(settings: Settings) -> bool:
    try:
        parts = urlsplit(settings.google_redirect_uri)
        host = parts.hostname or ""
        origin = f"{parts.scheme}://{parts.netloc}"
        parts.port
    except ValueError:
        return False
    return (
        parts.path == "/auth/google/callback"
        and parts.scheme in {"http", "https"}
        and bool(host)
        and parts.username is None
        and parts.password is None
        and not parts.query
        and not parts.fragment
        and origin in settings.trusted_origins
        and (settings.app_env != "production" or parts.scheme == "https")
        and (
            parts.scheme != "http"
            or settings.app_env == "test"
            or (settings.app_env == "development" and host in {"localhost", "127.0.0.1", "::1"})
        )
    )


class _GoogleOIDCClient(OAuth2Mixin, OpenIDMixin):
    client_cls = OAuth2Client


def _google_client(settings: Settings, transport=None) -> _GoogleOIDCClient:
    if not (
        settings.google_client_id
        and settings.google_client_secret
        and _valid_callback_uri(settings)
    ):
        raise ValueError("Google sign-in is not configured")

    client_kwargs = {
        "timeout": 5,
        "code_challenge_method": "S256",
        "token_endpoint_auth_method": "client_secret_post",
    }
    if transport is not None:
        client_kwargs["transport"] = transport
    return _GoogleOIDCClient(
        framework=None,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs=client_kwargs,
    )


def _validated_metadata(client: _GoogleOIDCClient) -> dict:
    metadata = client.load_server_metadata()
    if metadata.get("issuer") != GOOGLE_ISSUER:
        raise ValueError("Unexpected OIDC issuer")
    if "RS256" not in metadata.get("id_token_signing_alg_values_supported", []):
        raise ValueError("Unsupported Google signing algorithm")

    endpoints = {
        "authorization_endpoint": {"accounts.google.com"},
        "token_endpoint": {"oauth2.googleapis.com"},
        "jwks_uri": {"www.googleapis.com"},
    }
    for name, hosts in endpoints.items():
        parts = urlsplit(metadata.get(name, ""))
        if (
            parts.scheme != "https"
            or parts.hostname not in hosts
            or parts.port not in {None, 443}
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Invalid Google OIDC endpoint")
    metadata["id_token_signing_alg_values_supported"] = ["RS256"]
    return metadata


def create_authorization(conn, settings: Settings) -> tuple[str, str]:
    client = _google_client(settings)
    _validated_metadata(client)

    state = secrets.token_urlsafe(32)
    correlation = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(32)
    authorization = client.create_authorization_url(
        redirect_uri=settings.google_redirect_uri,
        response_type="code",
        scope="openid email profile",
        state=state,
        nonce=nonce,
        code_verifier=verifier,
    )
    if authorization.get("state") != state:
        raise ValueError("OAuth state was not preserved")

    conn.execute(
        """
        INSERT INTO oauth_transactions (
            state_hash, nonce, pkce_verifier, correlation_hash, expires_at
        ) VALUES (
            %s, %s, %s, %s,
            CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
        )
        """,
        (
            sha256(state.encode()).digest(),
            nonce,
            authorization["code_verifier"],
            sha256(correlation.encode()).digest(),
            OAUTH_TRANSACTION_SECONDS,
        ),
    )
    return authorization["url"], correlation


def consume_transaction(conn, state: str | None, correlation: str | None) -> tuple[str, str] | None:
    if not state or not correlation:
        return None

    state_hash = sha256(state.encode()).digest()
    correlation_hash = sha256(correlation.encode()).digest()
    with conn.transaction():
        row = conn.execute(
            """
            SELECT nonce, pkce_verifier, correlation_hash
            FROM oauth_transactions
            WHERE state_hash = %s
              AND consumed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            FOR UPDATE
            """,
            (state_hash,),
        ).fetchone()
        if row is None or not hmac.compare_digest(bytes(row[2]), correlation_hash):
            return None
        consumed = conn.execute(
            """
            UPDATE oauth_transactions
            SET consumed_at = CURRENT_TIMESTAMP
            WHERE state_hash = %s AND consumed_at IS NULL
            RETURNING nonce, pkce_verifier
            """,
            (state_hash,),
        ).fetchone()
    return (consumed[0], consumed[1]) if consumed else None


def exchange_and_validate(
    settings: Settings, code: str, nonce: str, verifier: str, transport=None
) -> dict | None:
    client = _google_client(settings, transport=transport)
    metadata = _validated_metadata(client)
    token = client.fetch_access_token(
        redirect_uri=settings.google_redirect_uri,
        code=code,
        code_verifier=verifier,
        grant_type="authorization_code",
    )
    user = client.parse_id_token(
        token,
        nonce,
        claims_options={
            "iss": {"essential": True, "values": list(GOOGLE_ISSUERS)},
            "aud": {"essential": True},
            "exp": {"essential": True},
            "nonce": {"essential": True},
        },
        leeway=0,
    )
    if user is None:
        return None

    issuer = user.get("iss")
    audiences = user.get("aud")
    if isinstance(audiences, str):
        audiences = [audiences]
    if (
        issuer not in GOOGLE_ISSUERS
        or not isinstance(audiences, list)
        or settings.google_client_id not in audiences
        or (len(audiences) > 1 and user.get("azp") != settings.google_client_id)
        or not isinstance(user.get("exp"), (int, float))
        or isinstance(user.get("exp"), bool)
        or user["exp"] <= time.time()
        or not isinstance(user.get("sub"), str)
        or not user["sub"]
        or not isinstance(user.get("nonce"), str)
        or not hmac.compare_digest(user["nonce"].encode(), nonce.encode())
    ):
        return None

    return {
        "issuer": GOOGLE_ISSUER,
        "sub": user["sub"],
        "email": user.get("email") if isinstance(user.get("email"), str) else None,
        "display_name": user.get("name") if isinstance(user.get("name"), str) else None,
    }
