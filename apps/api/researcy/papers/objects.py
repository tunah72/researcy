import hashlib
import logging
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from minio import Minio

from ..config import get_settings
from ..errors import APIError


logger = logging.getLogger(__name__)
_READ_SIZE = 64 * 1024


class PrivateResourceNotFound(APIError):
    def __init__(self):
        super().__init__(404, "RESOURCE_NOT_FOUND", "The requested resource was not found.")


class OriginalStorageError(APIError):
    def __init__(self):
        super().__init__(503, "ORIGINAL_STORAGE_UNAVAILABLE", "The original PDF is unavailable.")


def _bucket() -> str:
    return os.environ.get("MINIO_BUCKET", "researcy-originals").strip()


def _client() -> Minio:
    endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000").strip()
    access_key = os.environ.get("MINIO_ACCESS_KEY") or os.environ.get("MINIO_ROOT_USER", "")
    secret_key = os.environ.get("MINIO_SECRET_KEY") or os.environ.get("MINIO_ROOT_PASSWORD", "")
    secure = os.environ.get("MINIO_SECURE", "false").strip().lower()
    if not endpoint or not access_key or not secret_key or secure not in {"true", "false"}:
        raise OriginalStorageError()
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure == "true")


def _close_response(response) -> None:
    try:
        response.close()
    except Exception:
        pass
    try:
        response.release_conn()
    except Exception:
        pass


def _readback_matches(client: Minio, bucket: str, key: str, expected_bytes: int, expected_sha256: str) -> bool:
    response = None
    digest = hashlib.sha256()
    byte_count = 0
    try:
        response = client.get_object(bucket, key)
        while True:
            chunk = response.read(_READ_SIZE)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > expected_bytes:
                return False
            digest.update(chunk)
    finally:
        if response is not None:
            _close_response(response)
    return byte_count == expected_bytes and digest.hexdigest() == expected_sha256


def _remove_or_log(client: Minio, bucket: str, key: str) -> None:
    try:
        client.remove_object(bucket, key)
    except Exception:
        logger.error("private_original_orphan_cleanup_failed")

def remove_original(key: str) -> None:
    """Best-effort cleanup of an orphaned original object."""
    try:
        _client().remove_object(_bucket(), key)
    except Exception:
        logger.error("private_original_orphan_cleanup_failed")


def _stream_original(key: str) -> Iterator[bytes]:
    response = None
    try:
        response = _client().get_object(_bucket(), key)
    except Exception:
        raise OriginalStorageError() from None
    try:
        while True:
            try:
                chunk = response.read(_READ_SIZE)
            except Exception:
                raise OriginalStorageError() from None
            if not chunk:
                break
            yield chunk
    finally:
        _close_response(response)


def put_original(owner_id, version_id, path: str | os.PathLike[str], sha256: str) -> str:
    """Write an immutable original to private object storage and verify its read-back."""
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in sha256)
    ):
        raise APIError(422, "INVALID_PDF_HASH", "The PDF hash is invalid.")
    expected_sha256 = sha256.lower()
    try:
        source = open(Path(path), "rb")
    except (OSError, TypeError, ValueError):
        raise APIError(422, "PDF_INVALID", "The PDF could not be read.") from None

    with source:
        try:
            expected_bytes = os.fstat(source.fileno()).st_size
        except OSError:
            raise APIError(422, "PDF_INVALID", "The PDF could not be read.") from None
        if expected_bytes <= 0:
            raise APIError(422, "PDF_INVALID", "The PDF could not be read.")
        if expected_bytes > get_settings().max_upload_bytes:
            raise APIError(413, "PDF_TOO_LARGE", "The PDF exceeds the configured size limit.")
        try:
            owner_segment = UUID(str(owner_id)).hex
            version_segment = UUID(str(version_id)).hex
        except (TypeError, ValueError, AttributeError):
            raise APIError(422, "INVALID_RESOURCE_ID", "The resource identifier is invalid.") from None
        key = f"originals/{owner_segment}/{version_segment}/{secrets.token_hex(32)}"
        bucket = _bucket()
        try:
            client = _client()
        except Exception:
            raise OriginalStorageError() from None
        try:
            client.put_object(
                bucket,
                key,
                source,
                expected_bytes,
                content_type="application/pdf",
            )
            if not _readback_matches(client, bucket, key, expected_bytes, expected_sha256):
                raise OriginalStorageError()
        except Exception:
            _remove_or_log(client, bucket, key)
            raise OriginalStorageError() from None
    return key


def get_owned_original(conn, owner_id, paper_id, version_id) -> Iterator[bytes]:
    """Return a private object stream only after owner, paper, and version all match."""
    row = conn.execute(
        """
        SELECT object_key
        FROM document_versions
        WHERE owner_id = %s AND paper_id = %s AND id = %s
        """,
        (owner_id, paper_id, version_id),
    ).fetchone()
    if row is None:
        raise PrivateResourceNotFound()
    return _stream_original(row[0])
