from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
import unicodedata
from uuid import UUID, uuid4

from fastapi import UploadFile
import psycopg.errors

from ..errors import APIError
from .arxiv import fetch_official_arxiv, parse_arxiv_reference
from .models import MAX_SEARCH_LENGTH
from .objects import put_original, remove_original
from .screening import screen_pdf


logger = logging.getLogger(__name__)

_key_locks_lock = threading.Lock()
_key_locks: dict[tuple[UUID, str], threading.Lock] = {}


@contextmanager
def serialize_key(owner_id: UUID, key: str):
    """Serialize concurrent intake requests for the same owner and idempotency key."""
    with _key_locks_lock:
        lock = _key_locks.setdefault((owner_id, key), threading.Lock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _key_locks_lock:
            if not lock.locked():
                _key_locks.pop((owner_id, key), None)


def validate_idempotency_key(key: str | None) -> str:
    """Enforce a bounded, non-empty idempotency key."""
    if key is None:
        raise APIError(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key header is required.")
    cleaned = key.strip()
    if not cleaned or len(cleaned) > 255:
        raise APIError(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key header is invalid.")
    return cleaned


def sanitize_filename_title(filename: str | None) -> str | None:
    """Sanitize a client-supplied filename for display fallback only."""
    if not filename:
        return None
    name = Path(filename).name
    name = re.sub(r"(?i)\.pdf$", "", name)
    name = re.sub(r"[_\-]+", " ", name)
    name = unicodedata.normalize("NFKC", name)
    name = "".join(ch for ch in name if ch.isprintable())
    name = " ".join(name.split())
    if not name:
        return None
    return name[:MAX_SEARCH_LENGTH]


async def stream_upload_to_temp(file: UploadFile, max_bytes: int) -> tuple[Path, bytes, int]:
    """Stream an upload once to a private 0600 temp file enforcing byte limit while reading."""
    fd, temp_name = tempfile.mkstemp(prefix="researcy-upload-", suffix=".pdf")
    os.chmod(temp_name, 0o600)
    temp_path = Path(temp_name)
    hasher = hashlib.sha256()
    byte_count = 0
    try:
        with open(fd, "wb") as destination:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                byte_count += len(chunk)
                if byte_count > max_bytes:
                    raise APIError(413, "PDF_TOO_LARGE", "The PDF exceeds the configured size limit.")
                hasher.update(chunk)
                destination.write(chunk)
        if byte_count == 0:
            raise APIError(422, "PDF_INVALID", "The uploaded file is empty.")
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path, hasher.digest(), byte_count


@dataclass(frozen=True, slots=True)
class IntakeResult:
    paper_id: UUID
    document_version_id: UUID
    job_id: UUID
    stage: str
    screening_warning: str | None = None
    source_version: str | None = None
    is_replay: bool = False


@dataclass(frozen=True, slots=True)
class IntakeMetadata:
    title: str | None = None
    fallback_title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    source_version: str | None = None
    canonical_arxiv_id: str | None = None
    source_url: str | None = None
    source_media_type: str | None = None
    warning: str | None = None


def check_idempotency(
    conn, owner_id: UUID, key: str, operation: str, request_digest: bytes
) -> IntakeResult | None:
    """Check if an exact idempotency outcome exists for this owner and key."""
    row = conn.execute(
        """
        SELECT i.operation, i.request_digest, i.paper_id, i.document_version_id, i.job_id,
               j.stage, v.source_version, v.screening_warning
        FROM import_idempotency AS i
        JOIN document_versions AS v
          ON v.owner_id = i.owner_id
         AND v.id = i.document_version_id
        JOIN ingestion_jobs AS j
          ON j.owner_id = i.owner_id
         AND j.id = i.job_id
        WHERE i.owner_id = %s AND i.idempotency_key = %s
        """,
        (owner_id, key),
    ).fetchone()
    if row is None:
        return None

    stored_op, stored_digest, paper_id, version_id, job_id, stage, source_version, warning = row
    if stored_op != operation or bytes(stored_digest) != request_digest:
        raise APIError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "The idempotency key was already used with a different request.",
        )

    return IntakeResult(
        paper_id=paper_id,
        document_version_id=version_id,
        job_id=job_id,
        stage=stage,
        screening_warning=warning,
        source_version=source_version,
        is_replay=True,
    )


def check_owned_arxiv(
    conn, owner_id: UUID, canonical_id: str, explicit_version: int | None
) -> IntakeResult | None:
    """Return stored version if already owned; reject explicit different version with 409."""
    row = conn.execute(
        """
        SELECT p.id, p.active_version_id, j.id, j.stage, v.source_version, v.screening_warning
        FROM papers AS p
        JOIN document_versions AS v
          ON v.owner_id = p.owner_id
         AND v.id = p.active_version_id
        JOIN ingestion_jobs AS j
          ON j.owner_id = p.owner_id
         AND j.document_version_id = v.id
        WHERE p.owner_id = %s AND p.canonical_arxiv_id = %s
        """,
        (owner_id, canonical_id),
    ).fetchone()
    if row is None:
        return None

    paper_id, version_id, job_id, stage, source_version, warning = row
    if explicit_version is not None:
        expected = f"v{explicit_version}"
        if source_version != expected:
            raise APIError(
                409,
                "ARXIV_VERSION_CONFLICT",
                f"An explicit different version ({expected}) cannot be imported because {source_version} is already in your library.",
            )

    return IntakeResult(
        paper_id=paper_id,
        document_version_id=version_id,
        job_id=job_id,
        stage=stage,
        screening_warning=warning,
        source_version=source_version,
        is_replay=True,
    )


def accept_pdf(
    conn,
    owner_id: UUID,
    key: str,
    operation: str,
    request_digest: bytes,
    source: str,
    metadata: IntakeMetadata,
    screened_path: Path | str,
) -> IntakeResult:
    """Accept screened PDF, store immutable original, and persist paper/version/job/idempotency atomically."""
    media_type = metadata.source_media_type or "application/pdf"
    screening = screen_pdf(screened_path, media_type=media_type)

    title = metadata.title or screening.title or metadata.fallback_title or None
    warning_code = screening.warning.code if screening.warning else metadata.warning

    paper_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()

    object_key = put_original(owner_id, version_id, screened_path, screening.sha256)

    try:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO papers (
                    id, owner_id, source, canonical_arxiv_id, title, authors, year,
                    active_version_id, acceptance_state
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'accepted')
                """,
                (
                    paper_id,
                    owner_id,
                    source,
                    metadata.canonical_arxiv_id,
                    title,
                    metadata.authors,
                    metadata.year,
                    version_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO document_versions (
                    id, owner_id, paper_id, sha256, byte_count, object_key,
                    source_url, source_version, screening_warning
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    owner_id,
                    paper_id,
                    bytes.fromhex(screening.sha256),
                    screening.bytes,
                    object_key,
                    metadata.source_url,
                    metadata.source_version,
                    warning_code,
                ),
            )
            conn.execute(
                """
                INSERT INTO ingestion_jobs (id, owner_id, document_version_id, stage)
                VALUES (%s, %s, %s, 'queued')
                """,
                (job_id, owner_id, version_id),
            )
            conn.execute(
                """
                INSERT INTO import_idempotency (
                    owner_id, idempotency_key, operation, request_digest,
                    paper_id, document_version_id, job_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    owner_id,
                    key,
                    operation,
                    request_digest,
                    paper_id,
                    version_id,
                    job_id,
                ),
            )
    except psycopg.errors.UniqueViolation as exc:
        remove_original(object_key)
        constraint = getattr(getattr(exc, "diag", None), "constraint_name", "") or str(exc)
        if "uq_import_idempotency_owner_key" in constraint:
            existing = check_idempotency(conn, owner_id, key, operation, request_digest)
            if existing is not None:
                return existing
        elif "uq_papers_owner_canonical_arxiv_id" in constraint and metadata.canonical_arxiv_id:
            owned = check_owned_arxiv(conn, owner_id, metadata.canonical_arxiv_id, None)
            if owned is not None:
                return owned
        raise
    except Exception:
        remove_original(object_key)
        raise

    return IntakeResult(
        paper_id=paper_id,
        document_version_id=version_id,
        job_id=job_id,
        stage="queued",
        screening_warning=warning_code,
        source_version=metadata.source_version,
        is_replay=False,
    )
