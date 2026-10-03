from dataclasses import dataclass, field
from os import environ
from urllib.parse import urlsplit
import re

GENERATION_MODELS: dict[str, str] = {
    "gemini": "gemini-3.8-flash",
    "9router": "ag/gemini-3.8-flash-low",
}
GEMINI_EXACT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai"


DEFAULT_DATABASE_URL = (
    "postgresql://researcy:local-postgres-password@postgres:5432/researcy"
)


def _parse_bool(name: str, default: str) -> bool:
    value = environ.get(name, default).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def _bounded_int(name: str, default: int, maximum: int) -> int:
    value = int(environ.get(name, str(default)))
    if not 0 < value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value

def _validate_minio_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    try:
        parts = urlsplit(f"//{value}")
        valid = (bool(parts.hostname) and parts.netloc==value and parts.username is None
            and parts.password is None and not parts.path and not parts.query and not parts.fragment
            and not any(char.isspace() for char in value) and "\\" not in value)
        _ = parts.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("MINIO_ENDPOINT must be a valid host[:port] endpoint")
    return value


def _validate_minio_bucket(bucket: str) -> str:
    value = bucket.strip()
    if (not 3<=len(value)<=63 or re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]",value) is None
        or ".." in value or ".-" in value or "-." in value
        or re.fullmatch(r"\d+\.\d+\.\d+\.\d+",value) is not None):
        raise ValueError("MINIO_BUCKET must be a valid bucket name")
    return value


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

def _validate_generation_endpoint(endpoint: str, production: bool, provider: str) -> str:
    value = endpoint.strip()
    if not value:
        return ""
    if provider == "gemini":
        if value != GEMINI_EXACT_ENDPOINT:
            raise ValueError(f"gemini endpoint must be exactly {GEMINI_EXACT_ENDPOINT}")
        return value
    if provider == "9router":
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in ("http", "https")
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and parsed.path == "/v1"
                and not parsed.query
                and not parsed.fragment
                and not any(char.isspace() for char in value)
                and "\\" not in value
            )
            _ = parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(
                "GENERATION_ENDPOINT must be a valid base URL ending in /v1 with no userinfo, query, or fragment"
            )
        if production and parsed.scheme != "https":
            raise ValueError("production GENERATION_ENDPOINT must use HTTPS")
        return value
    raise ValueError(f"invalid generation_provider: {provider}")


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_env: str
    app_role: str
    trusted_origins: tuple[str, ...]
    cookie_secure: bool
    max_upload_bytes: int
    max_pdf_pages: int
    import_quota_limit: int
    session_lookup_key: bytes
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    job_lease_seconds: int = 90
    job_heartbeat_seconds: int = 15
    job_statement_timeout_ms: int = 5000
    job_lock_timeout_ms: int = 1000
    worker_idle_min_seconds: int = 1
    worker_idle_max_seconds: int = 5
    worker_claim_deadline_seconds: int = 1800
    worker_stage_deadlines: tuple[tuple[str, int], ...] = (
        ("validating",60), ("parsing",60), ("normalizing",120),
        ("chunking",120), ("embedding",900), ("indexing",300),
    )
    worker_io_deadline_seconds: int = 30
    worker_embedding_request_seconds: int = 60
    worker_batch_rows: int = 500
    parser_cpu_seconds: int = 45
    parser_wall_seconds: int = 60
    parser_memory_bytes: int = 768 * 1024 * 1024
    parser_output_bytes: int = 128 * 1024 * 1024
    parser_max_characters: int = 2_000_000
    parser_max_chunks: int = 10_000
    storage_minio_endpoint: str = "minio:9000"
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_secure: bool = False
    storage_bucket: str = "researcy-originals"
    embedding_endpoint: str = "http://host.docker.internal:11434"
    qdrant_endpoint: str = "http://qdrant:6333"
    generation_provider: str = "gemini"
    generation_endpoint: str = ""
    generation_api_key: str = field(default="", repr=False)
    generation_model: str = "gemini-3.8-flash"
    generation_max_output_tokens: int = 8192
    generation_max_output_bytes: int = 262144
    generation_connect_seconds: int = 5
    generation_pass_seconds: int = 60


    def __post_init__(self) -> None:
        if self.generation_provider not in GENERATION_MODELS:
            raise ValueError(f"invalid generation_provider: {self.generation_provider}")
        expected_model = GENERATION_MODELS[self.generation_provider]
        if self.generation_model != expected_model:
            raise ValueError(f"GENERATION_MODEL for {self.generation_provider} must be {expected_model}")
        if self.generation_endpoint:
            _validate_generation_endpoint(
                self.generation_endpoint,
                self.app_env == "production",
                self.generation_provider,
            )
    @property
    def max_upload_request_bytes(self) -> int:
        return self.max_upload_bytes + 64 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        app_env = environ.get("APP_ENV", "development").strip().lower()
        if app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")

        app_role = environ.get("APP_ROLE", "api").strip().lower()
        if app_role not in {"api", "worker"}:
            raise ValueError("APP_ROLE must be api or worker")

        production = app_env == "production"
        cookie_secure = _parse_bool("COOKIE_SECURE", "false")
        origins = _parse_origins(
            environ.get("APP_ORIGINS", "http://localhost:3000"),
            production if app_role == "api" else False,
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

        queue = {
            "job_lease_seconds": _bounded_int("JOB_LEASE_SECONDS",90,90),
            "job_heartbeat_seconds": _bounded_int("JOB_HEARTBEAT_SECONDS",15,15),
            "job_statement_timeout_ms": _bounded_int("JOB_STATEMENT_TIMEOUT_MS",5000,5000),
            "job_lock_timeout_ms": _bounded_int("JOB_LOCK_TIMEOUT_MS",1000,1000),
            "worker_idle_min_seconds": _bounded_int("WORKER_IDLE_MIN_SECONDS",1,5),
            "worker_idle_max_seconds": _bounded_int("WORKER_IDLE_MAX_SECONDS",5,5),
            "worker_claim_deadline_seconds": _bounded_int("WORKER_CLAIM_DEADLINE_SECONDS",1800,1800),
            "worker_io_deadline_seconds": _bounded_int("WORKER_IO_DEADLINE_SECONDS",30,30),
            "worker_embedding_request_seconds": _bounded_int("WORKER_EMBEDDING_REQUEST_SECONDS",60,60),
            "worker_batch_rows": _bounded_int("WORKER_BATCH_ROWS",500,500),
            "parser_cpu_seconds": _bounded_int("PARSER_CPU_SECONDS", 45, 45),
            "parser_wall_seconds": _bounded_int("PARSER_WALL_SECONDS", 60, 60),
            "parser_memory_bytes": _bounded_int("PARSER_MEMORY_BYTES", 768 * 1024 * 1024, 768 * 1024 * 1024),
            "parser_output_bytes": _bounded_int("PARSER_OUTPUT_BYTES", 128 * 1024 * 1024, 128 * 1024 * 1024),
            "parser_max_characters": _bounded_int("PARSER_MAX_CHARACTERS", 2_000_000, 2_000_000),
            "parser_max_chunks": _bounded_int("PARSER_MAX_CHUNKS", 10_000, 10_000),
        }
        if queue["parser_cpu_seconds"] > queue["parser_wall_seconds"]:
            raise ValueError("PARSER_CPU_SECONDS cannot exceed PARSER_WALL_SECONDS")
        storage_endpoint = _validate_minio_endpoint(environ.get("MINIO_ENDPOINT", "minio:9000"))
        storage_access_key = environ.get("MINIO_ACCESS_KEY") or environ.get("MINIO_ROOT_USER", "")
        storage_secret_key = environ.get("MINIO_SECRET_KEY") or environ.get("MINIO_ROOT_PASSWORD", "")
        storage_secure = _parse_bool("MINIO_SECURE", "false")
        storage_bucket = _validate_minio_bucket(environ.get("MINIO_BUCKET", "researcy-originals"))
        endpoints={}
        for name,default in (("OLLAMA_BASE_URL","http://host.docker.internal:11434"),("QDRANT_URL","http://qdrant:6333")):
            endpoint=environ.get(name,default).strip()
            try:
                parsed=urlsplit(endpoint)
                valid=(parsed.scheme in ("http","https") and bool(parsed.hostname) and parsed.username is None
                    and parsed.password is None and parsed.path in ("","/") and not parsed.query and not parsed.fragment
                    and not any(char.isspace() for char in endpoint) and "\\" not in endpoint)
                _=parsed.port
            except ValueError:
                valid=False
            if not valid:
                raise ValueError(f"{name} must be a plain HTTP origin")
            endpoints[name]=endpoint.rstrip("/")
        deadlines = tuple((stage,_bounded_int(f"PROCESSING_{stage.upper()}_DEADLINE_SECONDS",cap,cap))
            for stage,cap in (("validating",60),("parsing",60),("normalizing",120),
                ("chunking",120),("embedding",900),("indexing",300)))
        if (queue["job_heartbeat_seconds"] >= queue["job_lease_seconds"]
            or queue["job_lock_timeout_ms"] > queue["job_statement_timeout_ms"]
            or queue["worker_idle_min_seconds"] > queue["worker_idle_max_seconds"]
            or max(limit for _,limit in deadlines) > queue["worker_claim_deadline_seconds"]):
            raise ValueError("inconsistent worker deadlines")
        generation_provider = "gemini"
        generation_endpoint = ""
        generation_api_key = ""
        generation_model = "gemini-3.8-flash"
        generation_max_output_tokens = 8192
        generation_max_output_bytes = 262144
        generation_connect_seconds = 5
        generation_pass_seconds = 60

        if app_role == "api":
            generation_provider = environ.get("GENERATION_PROVIDER", "gemini").strip().lower()
            if generation_provider not in GENERATION_MODELS:
                raise ValueError(f"GENERATION_PROVIDER must be 'gemini' or '9router', got {generation_provider!r}")

            raw_endpoint = environ.get("GENERATION_ENDPOINT", "").strip()
            generation_endpoint = _validate_generation_endpoint(raw_endpoint, production, generation_provider)
            generation_api_key = environ.get("GENERATION_API_KEY", "").strip()

            expected_model = GENERATION_MODELS[generation_provider]
            configured_model = environ.get("GENERATION_MODEL", expected_model).strip()
            if configured_model != expected_model:
                raise ValueError(f"GENERATION_MODEL for {generation_provider} must be {expected_model}")
            generation_model = configured_model

            generation_max_output_tokens = _bounded_int("GENERATION_MAX_OUTPUT_TOKENS", 8192, 8192)
            generation_max_output_bytes = _bounded_int("GENERATION_MAX_OUTPUT_BYTES", 262144, 262144)
            generation_connect_seconds = _bounded_int("GENERATION_CONNECT_SECONDS", 5, 5)
            generation_pass_seconds = _bounded_int("GENERATION_PASS_SECONDS", 60, 60)
        database_url = environ.get("DATABASE_URL", "").strip()
        session_lookup_key = environ.get("SESSION_LOOKUP_KEY", "").encode()
        if production:
            required = ["DATABASE_URL", "POSTGRES_PASSWORD", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"]
            if app_role == "api":
                required.extend([
                    "SESSION_LOOKUP_KEY",
                    "GOOGLE_CLIENT_ID",
                    "GOOGLE_CLIENT_SECRET",
                    "GOOGLE_REDIRECT_URI",
                ])
            missing = [name for name in required if not environ.get(name, "").strip()]
            if missing:
                raise ValueError(f"missing production settings: {', '.join(missing)}")

            secret_checks = ["POSTGRES_PASSWORD", "MINIO_ROOT_PASSWORD"]
            if app_role == "api":
                secret_checks.append("SESSION_LOOKUP_KEY")
            for name in secret_checks:
                if len(environ[name].encode()) < 32:
                    raise ValueError(f"production {name} must be at least 32 bytes")
            if app_role == "api":
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
            app_role=app_role,
            trusted_origins=origins,
            cookie_secure=cookie_secure,
            max_upload_bytes=max_upload_bytes,
            max_pdf_pages=max_pdf_pages,
            import_quota_limit=import_quota_limit,
            session_lookup_key=session_lookup_key,
            google_client_id=environ.get("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=environ.get("GOOGLE_REDIRECT_URI", "").strip(),
            worker_stage_deadlines=deadlines,
            storage_minio_endpoint=storage_endpoint,
            storage_access_key=storage_access_key,
            storage_secret_key=storage_secret_key,
            storage_secure=storage_secure,
            storage_bucket=storage_bucket,
            embedding_endpoint=endpoints["OLLAMA_BASE_URL"],
            qdrant_endpoint=endpoints["QDRANT_URL"],
            generation_provider=generation_provider,
            generation_endpoint=generation_endpoint,
            generation_api_key=generation_api_key,
            generation_model=generation_model,
            generation_max_output_tokens=generation_max_output_tokens,
            generation_max_output_bytes=generation_max_output_bytes,
            generation_connect_seconds=generation_connect_seconds,
            generation_pass_seconds=generation_pass_seconds,
            **queue,
        )


def get_settings() -> Settings:
    return Settings.from_env()
