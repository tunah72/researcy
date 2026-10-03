import pytest

from researcy.config import Settings

def test_google_primary_accepts_its_exact_endpoint_and_model(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_PROVIDER", "gemini")
    monkeypatch.setenv("GENERATION_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/openai")
    monkeypatch.setenv("GENERATION_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("GENERATION_API_KEY", "isolated-test-only")
    settings = Settings.from_env()
    assert settings.generation_provider == "gemini"
    assert settings.generation_endpoint == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert settings.generation_model == "gemini-3.8-flash"
    assert "isolated-test-only" not in repr(settings)


def test_9router_route_accepts_its_exact_endpoint_and_model(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_PROVIDER", "9router")
    monkeypatch.setenv("GENERATION_ENDPOINT", "https://gateway.internal/v1")
    monkeypatch.setenv("GENERATION_MODEL", "ag/gemini-3.8-flash-low")
    monkeypatch.setenv("GENERATION_API_KEY", "isolated-9router-key")
    settings = Settings.from_env()
    assert settings.generation_provider == "9router"
    assert settings.generation_endpoint == "https://gateway.internal/v1"
    assert settings.generation_model == "ag/gemini-3.8-flash-low"
    assert "isolated-9router-key" not in repr(settings)





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


@pytest.mark.parametrize(
    "provider,invalid_model",
    [
        ("gemini", "openai/gpt-4o"),
        ("gemini", "ag/gemini-3.8-flash-low"),
        ("9router", "gemini-3.8-flash"),
        ("9router", "openai/gpt-4o"),
    ],
)
def test_generation_model_rejects_any_other_route(monkeypatch, provider, invalid_model):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_PROVIDER", provider)
    monkeypatch.setenv("GENERATION_ENDPOINT",
        "https://gateway.internal/v1" if provider == "9router"
        else "https://generativelanguage.googleapis.com/v1beta/openai")
    monkeypatch.setenv("GENERATION_MODEL", invalid_model)

    with pytest.raises(ValueError):
        Settings.from_env()


def test_generation_provider_rejects_unknown(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_PROVIDER", "anthropic")

    with pytest.raises(ValueError):
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
def test_9router_generation_endpoint_rejects_invalid_urls(monkeypatch, invalid_endpoint):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_PROVIDER", "9router")
    monkeypatch.setenv("GENERATION_MODEL", "ag/gemini-3.8-flash-low")
    monkeypatch.setenv("GENERATION_ENDPOINT", invalid_endpoint)

    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize(
    "invalid_gemini_endpoint",
    [
        "http://generativelanguage.googleapis.com/v1beta/openai",  # http
        "https://generativelanguage.googleapis.com/v1",            # old /v1
        "https://generativelanguage.googleapis.com/v1beta/openai?key=1",  # query
        "https://attacker.com/v1beta/openai",                      # attacker host
        "https://user:pass@generativelanguage.googleapis.com/v1beta/openai",  # userinfo
        "https://generativelanguage.googleapis.com/v1beta/openai#frag",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ],
)
def test_gemini_generation_endpoint_rejects_non_exact_endpoint(monkeypatch, invalid_gemini_endpoint):
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_PROVIDER", "gemini")
    monkeypatch.setenv("GENERATION_ENDPOINT", invalid_gemini_endpoint)

    with pytest.raises(ValueError):
        Settings.from_env()

def test_generation_endpoint_production_requires_tls_on_9router(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_ROLE", "api")
    monkeypatch.setenv("GENERATION_PROVIDER", "9router")
    monkeypatch.setenv("GENERATION_MODEL", "ag/gemini-3.8-flash-low")
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
    with pytest.raises(ValueError):
        Settings.from_env()

    monkeypatch.setenv("GENERATION_ENDPOINT", "https://gateway.internal/v1")
    settings = Settings.from_env()
    assert settings.generation_endpoint == "https://gateway.internal/v1"
