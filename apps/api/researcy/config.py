from dataclasses import dataclass
from os import environ
from urllib.parse import urlsplit


DEFAULT_DATABASE_URL = (
    "postgresql://researcy:local-postgres-password@postgres:5432/researcy"
)


def _parse_bool(name: str, default: str) -> bool:
    value = environ.get(name, default).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def _parse_origins(value: str, production: bool) -> tuple[str, ...]:
    origins = tuple(
        dict.fromkeys(part.strip() for part in value.split(",") if part.strip())
    )
    if not origins:
        raise ValueError("APP_ORIGINS must contain at least one exact origin")

    for origin in origins:
        try:
            parts = urlsplit(origin)
            valid = (
                parts.scheme in {"http", "https"}
                and bool(parts.hostname)
                and "*" not in parts.netloc
                and parts.username is None
                and parts.password is None
                and parts.path == ""
                and not parts.query
                and not parts.fragment
            )
            _ = parts.port  # Access validates the port syntax and range.
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(
                "APP_ORIGINS must contain exact origins without paths or wildcards"
            )
        if production and parts.scheme != "https":
            raise ValueError("production APP_ORIGINS must use HTTPS")
    return origins


def _validate_production_google_redirect(
    redirect_uri: str, trusted_origins: tuple[str, ...]
) -> None:
    try:
        parts = urlsplit(redirect_uri)
        origin = f"{parts.scheme}://{parts.netloc}"
        valid = (
            parts.scheme == "https"
            and bool(parts.hostname)
            and parts.username is None
            and parts.password is None
            and parts.path == "/auth/google/callback"
            and not parts.query
            and not parts.fragment
            and origin in trusted_origins
        )
        _ = parts.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "production GOOGLE_REDIRECT_URI must be the trusted HTTPS /auth/google/callback"
        )


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_env: str
    trusted_origins: tuple[str, ...]
    cookie_secure: bool
    max_upload_bytes: int
    max_pdf_pages: int
    import_quota_limit: int
    session_lookup_key: bytes
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    @property
    def max_upload_request_bytes(self) -> int:
        return self.max_upload_bytes + 64 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        app_env = environ.get("APP_ENV", "development").strip().lower()
        if app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")

        production = app_env == "production"
        cookie_secure = _parse_bool("COOKIE_SECURE", "false")
        origins = _parse_origins(
            environ.get("APP_ORIGINS", "http://localhost:3000"), production
        )
        max_upload_bytes = int(environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
        max_pdf_pages = int(environ.get("MAX_PDF_PAGES", "100"))
        import_quota_limit = int(environ.get("IMPORT_QUOTA_LIMIT", "10"))
        if import_quota_limit <= 0:
            raise ValueError("IMPORT_QUOTA_LIMIT must be a positive integer")
        if max_upload_bytes <= 0 or max_pdf_pages <= 0:
            raise ValueError(
                "MAX_UPLOAD_BYTES and MAX_PDF_PAGES must be positive integers"
            )

        database_url = environ.get("DATABASE_URL", "").strip()
        session_lookup_key = environ.get("SESSION_LOOKUP_KEY", "").encode()
        if production:
            required = (
                "DATABASE_URL",
                "POSTGRES_PASSWORD",
                "SESSION_LOOKUP_KEY",
                "MINIO_ROOT_USER",
                "MINIO_ROOT_PASSWORD",
                "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET",
                "GOOGLE_REDIRECT_URI",
            )
            missing = [name for name in required if not environ.get(name, "").strip()]
            if missing:
                raise ValueError(f"missing production settings: {', '.join(missing)}")
            for name in (
                "POSTGRES_PASSWORD",
                "SESSION_LOOKUP_KEY",
                "MINIO_ROOT_PASSWORD",
            ):
                if len(environ[name].encode()) < 32:
                    raise ValueError(f"production {name} must be at least 32 bytes")
            if not cookie_secure:
                raise ValueError("production COOKIE_SECURE must be true")
            _validate_production_google_redirect(
                environ["GOOGLE_REDIRECT_URI"].strip(), origins
            )
        elif not database_url:
            database_url = DEFAULT_DATABASE_URL

        return cls(
            database_url=database_url,
            app_env=app_env,
            trusted_origins=origins,
            cookie_secure=cookie_secure,
            max_upload_bytes=max_upload_bytes,
            max_pdf_pages=max_pdf_pages,
            import_quota_limit=import_quota_limit,
            session_lookup_key=session_lookup_key,
            google_client_id=environ.get("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=environ.get("GOOGLE_REDIRECT_URI", "").strip(),
        )


def get_settings() -> Settings:
    return Settings.from_env()
