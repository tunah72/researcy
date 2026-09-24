import pytest

from researcy.config import Settings


def set_production_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_ORIGINS", "https://research.example")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://api:secret@db/researcy")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p" * 32)
    monkeypatch.setenv("SESSION_LOOKUP_KEY", "s" * 64)
    monkeypatch.setenv("MINIO_ROOT_USER", "minio-api")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "m" * 32)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "production-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "production-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI", "https://research.example/auth/google/callback"
    )


def test_development_defaults_keep_pdf_limits_and_exact_local_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.delenv("MAX_UPLOAD_BYTES", raising=False)
    monkeypatch.delenv("MAX_PDF_PAGES", raising=False)

    settings = Settings.from_env()

    assert settings.max_upload_bytes == 25 * 1024 * 1024
    assert settings.max_pdf_pages == 100
    assert settings.trusted_origins == ("http://localhost:3000",)


def test_production_requires_secrets_secure_cookies_and_https_origins(monkeypatch):
    set_production_env(monkeypatch)
    monkeypatch.delenv("SESSION_LOOKUP_KEY")
    with pytest.raises(ValueError, match="SESSION_LOOKUP_KEY"):
        Settings.from_env()

    set_production_env(monkeypatch)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings.from_env()

    set_production_env(monkeypatch)
    monkeypatch.setenv("APP_ORIGINS", "http://research.example")
    with pytest.raises(ValueError, match="HTTPS"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name",
    ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"],
)
def test_production_requires_google_oauth_settings(monkeypatch, name):
    set_production_env(monkeypatch)
    monkeypatch.delenv(name)

    with pytest.raises(ValueError, match=name):
        Settings.from_env()


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://research.example/auth/google/callback",
        "https://other.example/auth/google/callback",
        "https://research.example/not-the-callback",
    ],
)
def test_production_requires_trusted_https_google_callback(monkeypatch, redirect_uri):
    set_production_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", redirect_uri)

    with pytest.raises(ValueError, match="GOOGLE_REDIRECT_URI"):
        Settings.from_env()


def test_origin_rejects_wildcards_and_non_origin_urls(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_ORIGINS", "https://*.example.test/path")
    with pytest.raises(ValueError, match="exact origin"):
        Settings.from_env()


def test_import_quota_limit_defaults_and_accepts_positive_config(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    monkeypatch.delenv("IMPORT_QUOTA_LIMIT", raising=False)

    assert Settings.from_env().import_quota_limit == 10

    monkeypatch.setenv("IMPORT_QUOTA_LIMIT", "3")
    assert Settings.from_env().import_quota_limit == 3


@pytest.mark.parametrize("value", ["0", "-1"])
def test_import_quota_limit_must_be_positive(monkeypatch, value):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("IMPORT_QUOTA_LIMIT", value)

    with pytest.raises(ValueError, match="IMPORT_QUOTA_LIMIT"):
        Settings.from_env()
