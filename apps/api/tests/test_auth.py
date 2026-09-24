import base64
import hashlib
import hmac
import time
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
from fastapi.testclient import TestClient
from joserfc import jwk, jwt


from researcy.main import app


CLIENT_ID = "local-test-client"
ISSUER = "https://accounts.google.com"
CALLBACK = "http://localhost:3000/auth/google/callback"
SESSION_LOOKUP_KEY = "test-session-lookup-key-at-least-32-bytes"


class LocalGoogle:
    def __init__(self):
        self.key = jwk.generate_key("RSA", 2048, {"kid": "local-oidc-key"}, private=True)
        self.other_key = jwk.generate_key("RSA", 2048, {"kid": "local-oidc-key"}, private=True)
        self.nonce = None
        self.challenge = None
        self.exchange = None
        self.claims = None
        self.signer = self.key
        self.transport = httpx2.MockTransport(self.handle)

    def authorize(self, response):
        query = parse_qs(urlparse(response.headers["location"]).query)
        self.nonce = query["nonce"][0]
        self.challenge = query["code_challenge"][0]
        return query

    def id_token(self, claims=None):
        payload = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "google-subject-1",
            "email": "same@example.test",
            "name": "Test User",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "nonce": self.nonce,
        }
        payload.update(claims or {})
        return jwt.encode(
            {"alg": "RS256", "kid": "local-oidc-key"}, payload, self.signer
        )

    def handle(self, request):
        if request.url == "https://accounts.google.com/.well-known/openid-configuration":
            return httpx2.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_endpoint": "https://oauth2.googleapis.com/token",
                    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if request.url == "https://www.googleapis.com/oauth2/v3/certs":
            return httpx2.Response(200, json={"keys": [self.key.as_dict(is_private=False)]})
        if request.url == "https://oauth2.googleapis.com/token":
            form = parse_qs(request.content.decode())
            self.exchange = form
            assert form["redirect_uri"] == [CALLBACK]
            assert form["code"] == ["local-authorization-code"]
            assert form["client_id"] == [CLIENT_ID]
            verifier = form["code_verifier"][0]
            challenge = base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            ).rstrip(b"=").decode()
            assert challenge == self.challenge
            return httpx2.Response(
                200,
                json={
                    "access_token": "local-access-token",
                    "token_type": "Bearer",
                    "id_token": self.id_token(self.claims),
                },
            )
        raise AssertionError("unexpected local OIDC request")


@pytest.fixture

def local_google():
    return LocalGoogle()


@pytest.fixture

def client(monkeypatch, pg_conn, local_google):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("SESSION_LOOKUP_KEY", SESSION_LOOKUP_KEY)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "local-test-client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", CALLBACK)

    from researcy.auth import oauth, routes

    @contextmanager
    def test_connection():
        with pg_conn.transaction():
            yield pg_conn

    monkeypatch.setattr(routes, "get_conn", lambda: test_connection())
    original_client_factory = oauth._google_client
    monkeypatch.setattr(
        oauth,
        "_google_client",
        lambda settings, transport=None: original_client_factory(
            settings, transport=local_google.transport
        ),
    )

    with TestClient(app, base_url="http://localhost:3000") as test_client:
        yield test_client


def start_login(client, local_google):
    response = client.get("/auth/google/start", follow_redirects=False)
    assert response.status_code == 302
    query = local_google.authorize(response)
    return response, query


def finish_login(client, query):
    return client.get(
        "/auth/google/callback",
        params={"code": "local-authorization-code", "state": query["state"][0]},
        follow_redirects=False,
    )


def test_google_oidc_pkce_creates_user_and_opaque_database_session(client, pg_conn, local_google):
    start, query = start_login(client, local_google)

    assert query["response_type"] == ["code"]
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [CALLBACK]
    assert query["scope"] == ["openid email profile"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) == 43
    assert len(query["state"][0]) >= 32
    assert len(query["nonce"][0]) >= 32
    correlation_cookie = next(
        cookie for cookie in start.headers.get_list("set-cookie") if cookie.startswith("researcy_oauth=")
    )
    assert "httponly" in correlation_cookie.lower()
    assert "domain=" not in correlation_cookie.lower()

    local_google.claims = {"sub": "google-subject-1", "email": "same@example.test"}
    callback = finish_login(client, query)

    assert callback.status_code == 303
    assert callback.headers["location"] == "/library"
    session_cookie = next(
        cookie for cookie in callback.headers.get_list("set-cookie") if cookie.startswith("researcy_session=")
    )
    csrf_cookie = next(
        cookie for cookie in callback.headers.get_list("set-cookie") if cookie.startswith("researcy_csrf=")
    )
    assert "httponly" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    assert "domain=" not in session_cookie.lower()

    raw_session = client.cookies.get("researcy_session")
    assert raw_session
    stored = pg_conn.execute(
        "SELECT token_hash, csrf_verifier, owner_id FROM sessions"
    ).fetchone()
    assert stored[0] != raw_session.encode()
    assert stored[0] == hmac.digest(
        SESSION_LOOKUP_KEY.encode(), raw_session.encode(), "sha256"
    )
    assert len(stored[0]) == 32
    assert len(stored[1]) == 32
    assert pg_conn.execute("SELECT count(*) FROM oauth_transactions WHERE consumed_at IS NOT NULL").fetchone()[0] == 1

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == "same@example.test"
    assert me.json()["request_id"]
    assert raw_session not in me.text


def test_oidc_rejects_nonce_issuer_audience_signature_and_expiry(client, pg_conn, local_google):
    failures = [
        {"nonce": "wrong-nonce"},
        {"iss": "https://attacker.example"},
        {"aud": "another-client"},
        {"exp": 1},
    ]
    for claims in failures:
        _, query = start_login(client, local_google)
        local_google.claims = claims
        callback = finish_login(client, query)
        assert callback.status_code == 303
        assert callback.headers["location"] == "/sign-in?error=oauth"
        assert pg_conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
        assert pg_conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0

    _, query = start_login(client, local_google)
    local_google.claims = None
    local_google.signer = local_google.other_key
    callback = finish_login(client, query)
    assert callback.status_code == 303
    assert callback.headers["location"] == "/sign-in?error=oauth"
    assert pg_conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
    assert pg_conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_oauth_correlation_cookie_is_bound_to_state(client, pg_conn, local_google):
    _, query = start_login(client, local_google)
    client.cookies.clear()
    client.cookies.set(
        "researcy_oauth",
        "wrong-correlation",
        domain="localhost",
        path="/auth/google/callback",
    )

    rejected = finish_login(client, query)

    assert rejected.headers["location"] == "/sign-in?error=oauth"
    assert pg_conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
    assert pg_conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0

def test_expired_and_replayed_oauth_transactions_never_issue_another_session(client, pg_conn, local_google):
    _, query = start_login(client, local_google)
    state_hash = hashlib.sha256(query["state"][0].encode()).digest()
    pg_conn.execute(
        """
        UPDATE oauth_transactions
        SET created_at = CURRENT_TIMESTAMP - interval '2 minutes',
            expires_at = CURRENT_TIMESTAMP - interval '1 second'
        WHERE state_hash = %s
        """,
        (state_hash,),
    )
    expired = finish_login(client, query)
    assert expired.headers["location"] == "/sign-in?error=oauth"
    assert pg_conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
    assert pg_conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0

    _, query = start_login(client, local_google)
    local_google.claims = None
    accepted = finish_login(client, query)
    assert accepted.headers["location"] == "/library"
    replay = finish_login(client, query)
    assert replay.headers["location"] == "/sign-in?error=oauth"
    assert pg_conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    assert pg_conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1


def test_google_issuer_aliases_share_the_same_subject_identity(client, pg_conn, local_google):
    _, first = start_login(client, local_google)
    local_google.claims = {"iss": "accounts.google.com"}
    assert finish_login(client, first).headers["location"] == "/library"

    _, second = start_login(client, local_google)
    local_google.claims = {"iss": ISSUER}
    assert finish_login(client, second).headers["location"] == "/library"

    assert (
        pg_conn.execute(
            "SELECT count(*) FROM users WHERE sub = %s", ("google-subject-1",)
        ).fetchone()[0]
        == 1
    )


def test_google_subject_not_email_is_the_user_identity(client, pg_conn, local_google):
    _, first = start_login(client, local_google)
    local_google.claims = {"sub": "google-subject-a", "email": "same@example.test"}
    assert finish_login(client, first).headers["location"] == "/library"

    _, second = start_login(client, local_google)
    local_google.claims = {"sub": "google-subject-b", "email": "same@example.test"}
    assert finish_login(client, second).headers["location"] == "/library"

    assert pg_conn.execute("SELECT count(*) FROM users WHERE email = %s", ("same@example.test",)).fetchone()[0] == 2


@pytest.mark.parametrize(
    "csrf_header,origin",
    [
        ("wrong", "http://localhost:3000"),
        (None, "http://localhost:3000"),
        ("cookie", "https://hostile.example"),
    ],
)
def test_invalid_csrf_or_origin_returns_403_without_revoke(client, local_google, csrf_header, origin):
    _, query = start_login(client, local_google)
    local_google.claims = None
    assert finish_login(client, query).headers["location"] == "/library"
    csrf = client.cookies.get("researcy_csrf")
    header = "wrong" if csrf_header == "wrong" else csrf
    if csrf_header is None:
        header = None
    response = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": header, "Origin": origin} if header else {"Origin": origin},
    )
    assert response.status_code == 403
    assert client.get("/api/me").status_code == 200


def test_logout_revokes_old_cookie_before_clearing_it(client, local_google):
    _, query = start_login(client, local_google)
    local_google.claims = None
    assert finish_login(client, query).headers["location"] == "/library"
    raw_session = client.cookies.get("researcy_session")
    csrf = client.cookies.get("researcy_csrf")

    response = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": csrf, "Origin": "http://localhost:3000"},
    )

    assert response.status_code == 204
    client.cookies.set("researcy_session", raw_session, domain="localhost", path="/")
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("expiry", ["idle", "absolute"])
def test_expired_idle_or_absolute_session_returns_401(client, pg_conn, local_google, expiry):
    _, query = start_login(client, local_google)
    local_google.claims = None
    assert finish_login(client, query).headers["location"] == "/library"
    raw_session = client.cookies.get("researcy_session")
    token_hash = hmac.digest(
        SESSION_LOOKUP_KEY.encode(), raw_session.encode(), "sha256"
    )
    if expiry == "idle":
        pg_conn.execute(
            """
            UPDATE sessions
            SET issued_at = CURRENT_TIMESTAMP - interval '2 hours',
                idle_expires_at = CURRENT_TIMESTAMP - interval '1 second',
                absolute_expires_at = CURRENT_TIMESTAMP + interval '10 hours'
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
    else:
        pg_conn.execute(
            """
            UPDATE sessions
            SET issued_at = CURRENT_TIMESTAMP - interval '13 hours',
                idle_expires_at = CURRENT_TIMESTAMP - interval '2 seconds',
                absolute_expires_at = CURRENT_TIMESTAMP - interval '1 second'
            WHERE token_hash = %s
            """,
            (token_hash,),
        )

    assert client.get("/api/me").status_code == 401

def test_me_requires_authenticated_session():
    with TestClient(app) as unauthenticated:
        response = unauthenticated.get("/api/me")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
