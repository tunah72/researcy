import pytest

from researcy.config import Settings



def test_generation_credentials_are_absent_from_diagnostic_repr(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_API_KEY", "private-product-credential")
    assert "private-product-credential" not in repr(Settings.from_env())




def test_worker_role_excludes_generation_credentials(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "worker")
    monkeypatch.setenv("GENERATION_ENDPOINT", "http://127.0.0.1:20128/v1")
    monkeypatch.setenv("GENERATION_API_KEY", "secret-worker-key")

    settings = Settings.from_env()
    assert settings.generation_endpoint == ""
    assert settings.generation_api_key == ""


def test_generation_model_rejects_any_other_route(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_MODEL", "openai/gpt-4o")

    with pytest.raises(ValueError, match="GENERATION_MODEL must be ag/gemini-3.8-flash-low"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name,val",
    [
        ("GENERATION_MAX_OUTPUT_TOKENS", "8193"),
        ("GENERATION_MAX_OUTPUT_TOKENS", "0"),
        ("GENERATION_MAX_OUTPUT_BYTES", "262145"),
        ("GENERATION_MAX_OUTPUT_BYTES", "0"),
        ("GENERATION_CONNECT_SECONDS", "6"),
        ("GENERATION_CONNECT_SECONDS", "0"),
        ("GENERATION_PASS_SECONDS", "61"),
        ("GENERATION_PASS_SECONDS", "0"),
    ],
)
def test_generation_limits_cannot_exceed_approved_maxima_or_be_non_positive(monkeypatch, name, val):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv(name, val)

    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize(
    "invalid_endpoint",
    [
        "not-a-url",
        "ftp://localhost:8000/v1",
        "http://user:pass@localhost:8000/v1",
        "http://localhost:8000/v1?query=1",
        "http://localhost:8000/v1#fragment",
        "http://localhost:8000/v1/extra",
        "http://localhost:8000/v1\\bad",
        "http://localhost:8000/ v1",
        "http://",
    ],
)
def test_generation_endpoint_rejects_invalid_urls(monkeypatch, invalid_endpoint):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_ENDPOINT", invalid_endpoint)

    with pytest.raises(ValueError, match="GENERATION_ENDPOINT"):
        Settings.from_env()


def test_generation_endpoint_production_requires_tls(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db:5432/db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a" * 32)
    monkeypatch.setenv("MINIO_ROOT_USER", "minio")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "b" * 32)
    monkeypatch.setenv("SESSION_LOOKUP_KEY", "c" * 32)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client_id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://localhost:3000/auth/google/callback")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("APP_ORIGINS", "https://localhost:3000")

    monkeypatch.setenv("GENERATION_ENDPOINT", "http://gateway.internal/v1")
    with pytest.raises(ValueError, match="production GENERATION_ENDPOINT must use HTTPS"):
        Settings.from_env()

    monkeypatch.setenv("GENERATION_ENDPOINT", "https://gateway.internal/v1")
    settings = Settings.from_env()
    assert settings.generation_endpoint == "https://gateway.internal/v1"
