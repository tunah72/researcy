import asyncio
import hashlib
from pathlib import Path
import secrets
from uuid import UUID

import httpx2
from minio import Minio

from researcy.config import Settings, get_settings
from researcy.ingestion.models import (
    STAGES,
    ArtifactRef,
    DocumentScope,
    IntegrityFailure,
    StageFailure,
)

CHUNK_SIZE = 64 * 1024


def _storage_unavailable() -> StageFailure:
    return StageFailure(
        "DEPENDENCY_UNAVAILABLE",
        "temporary",
        True,
        retry_after_seconds=5,
    )


def _get_minio_client(settings: Settings) -> Minio:
    if (
        not settings.storage_access_key
        or not settings.storage_secret_key
        or not settings.storage_bucket
        or not settings.storage_minio_endpoint
    ):
        raise _storage_unavailable()
    try:
        return Minio(
            settings.storage_minio_endpoint,
            access_key=settings.storage_access_key,
            secret_key=settings.storage_secret_key,
            secure=settings.storage_secure,
            region="us-east-1",
        )
    except Exception:
        raise _storage_unavailable() from None


async def _check_existing(
    http_client: httpx2.AsyncClient,
    get_url: str,
    expected_sha256: bytes,
    expected_byte_count: int,
    max_bytes: int,
) -> str:
    """Check existing object state via raw streaming.

    Returns:
        "match": object exists (200) with matching SHA-256 and byte count.
        "conflict": object exists (200) but bytes/size mismatch or exceed max.
        "absent": object does not exist (404).

    Raises:
        StageFailure: on 5xx server errors or connection/timeout faults.
    """
    try:
        async with http_client.stream("GET", get_url) as stream_resp:
            if stream_resp.status_code == 429 or stream_resp.status_code >= 500:
                raise _storage_unavailable()
            if stream_resp.status_code == 404:
                return "absent"
            if stream_resp.status_code != 200:
                raise _storage_unavailable()

            hasher = hashlib.sha256()
            total_bytes = 0
            async for chunk in stream_resp.aiter_raw(chunk_size=CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > max_bytes or total_bytes > expected_byte_count:
                    return "conflict"
                hasher.update(chunk)

            if total_bytes != expected_byte_count:
                return "conflict"
            if hasher.digest() != expected_sha256:
                return "conflict"
            return "match"
    except (TimeoutError, asyncio.TimeoutError, httpx2.TimeoutException):
        raise _storage_unavailable() from None
    except httpx2.TransportError:
        raise _storage_unavailable() from None


async def _put_artifact_async(
    scope: DocumentScope,
    profile_hash: bytes,
    stage: str,
    source: Path,
    settings: Settings,
) -> ArtifactRef:
    if (
        not isinstance(scope, DocumentScope)
        or not isinstance(scope.owner_id, UUID)
        or not isinstance(scope.paper_id, UUID)
        or not isinstance(scope.document_version_id, UUID)
    ):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    if type(profile_hash) is not bytes or len(profile_hash) != 32:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    if stage not in STAGES:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    source_path = Path(source)
    if not source_path.is_file():
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")

    hasher = hashlib.sha256()
    byte_count = 0
    max_bytes = settings.parser_output_bytes

    try:
        with open(source_path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                byte_count += len(chunk)
                if byte_count > max_bytes:
                    raise IntegrityFailure("PARSER_OUTPUT_INVALID")
                hasher.update(chunk)
    except OSError:
        raise IntegrityFailure("PARSER_OUTPUT_INVALID") from None

    if byte_count <= 0:
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")

    sha256_digest = hasher.digest()
    content_hex = hasher.hexdigest()
    profile_hex = profile_hash.hex()
    key = (
        f"processing/{scope.owner_id}/{scope.document_version_id}/"
        f"{profile_hex}/{stage}/{content_hex}"
    )

    client = _get_minio_client(settings)
    bucket = settings.storage_bucket
    try:
        put_url = client.presigned_put_object(bucket, key)
        get_url = client.presigned_get_object(bucket, key)
    except Exception:
        raise _storage_unavailable() from None

    async def file_chunks():
        with open(source_path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    deadline = float(settings.worker_io_deadline_seconds)
    headers = {
        "If-None-Match": "*",
        "Content-Length": str(byte_count),
        "Content-Type": "application/octet-stream",
    }

    try:
        async with httpx2.AsyncClient(timeout=deadline, trust_env=False) as http_client:
            async with asyncio.timeout(deadline):
                # 1. GET verify existing key first under total deadline
                existing_status = await _check_existing(
                    http_client=http_client,
                    get_url=get_url,
                    expected_sha256=sha256_digest,
                    expected_byte_count=byte_count,
                    max_bytes=max_bytes,
                )
                if existing_status == "match":
                    return ArtifactRef(
                        key=key,
                        sha256=sha256_digest,
                        byte_count=byte_count,
                    )
                if existing_status == "conflict":
                    raise IntegrityFailure("PARSER_OUTPUT_CONFLICT")

                # Only 404 absent permits conditional PUT
                put_succeeded = False
                try:
                    async with http_client.stream(
                        "PUT",
                        put_url,
                        content=file_chunks(),
                        headers=headers,
                    ) as put_resp:
                        status = put_resp.status_code

                    if 200 <= status < 300:
                        put_succeeded = True
                    elif status == 412:
                        put_succeeded = False
                    else:
                        raise _storage_unavailable()
                except StageFailure:
                    raise
                except Exception:
                    # Uncertain PUT ack or broken pipe during upload in race
                    put_succeeded = False

                # 2. Exactly one GET verification under remaining deadline
                verify_status = await _check_existing(
                    http_client=http_client,
                    get_url=get_url,
                    expected_sha256=sha256_digest,
                    expected_byte_count=byte_count,
                    max_bytes=max_bytes,
                )
                if verify_status == "match":
                    return ArtifactRef(
                        key=key,
                        sha256=sha256_digest,
                        byte_count=byte_count,
                    )
                if verify_status == "conflict":
                    code = (
                        "PROCESSING_INTEGRITY_FAILURE"
                        if put_succeeded
                        else "PARSER_OUTPUT_CONFLICT"
                    )
                    raise IntegrityFailure(code)

                raise _storage_unavailable()

    except (TimeoutError, asyncio.TimeoutError, httpx2.TimeoutException):
        raise _storage_unavailable() from None
    except httpx2.TransportError:
        raise _storage_unavailable() from None
    except StageFailure:
        raise
    except Exception:
        raise _storage_unavailable() from None


async def _verify_artifact_async(
    ref: ArtifactRef,
    destination: Path,
    settings: Settings,
) -> None:
    if not isinstance(ref, ArtifactRef):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    dest_path = Path(destination)
    if dest_path.exists():
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    if ref.byte_count > settings.parser_output_bytes or ref.byte_count <= 0:
        raise IntegrityFailure("PARSER_OUTPUT_INVALID")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    client = _get_minio_client(settings)
    bucket = settings.storage_bucket
    try:
        get_url = client.presigned_get_object(bucket, ref.key)
    except Exception:
        raise _storage_unavailable() from None

    temp_file = dest_path.with_name(f".tmp.{dest_path.name}.{secrets.token_hex(16)}")
    deadline = float(settings.worker_io_deadline_seconds)
    max_bytes = settings.parser_output_bytes
    expected_bytes = ref.byte_count
    expected_sha256 = ref.sha256

    try:
        async with httpx2.AsyncClient(timeout=deadline, trust_env=False) as http_client:
            async with asyncio.timeout(deadline):
                async with http_client.stream("GET", get_url) as stream_resp:
                    if stream_resp.status_code == 429 or stream_resp.status_code >= 500:
                        raise _storage_unavailable()
                    if stream_resp.status_code != 200:
                        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

                    hasher = hashlib.sha256()
                    total_bytes = 0
                    with open(temp_file, "wb") as out_f:
                        async for chunk in stream_resp.aiter_raw(
                            chunk_size=CHUNK_SIZE
                        ):
                            total_bytes += len(chunk)
                            if (
                                total_bytes > max_bytes
                                or total_bytes > expected_bytes
                            ):
                                break
                            out_f.write(chunk)
                            hasher.update(chunk)

                    if (
                        total_bytes != expected_bytes
                        or hasher.digest() != expected_sha256
                    ):
                        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        temp_file.replace(dest_path)
    except (TimeoutError, asyncio.TimeoutError, httpx2.TimeoutException):
        temp_file.unlink(missing_ok=True)
        raise _storage_unavailable() from None
    except httpx2.TransportError:
        temp_file.unlink(missing_ok=True)
        raise _storage_unavailable() from None
    except Exception:
        temp_file.unlink(missing_ok=True)
        raise


def put_artifact(
    scope: DocumentScope,
    profile_hash: bytes,
    stage: str,
    source: Path | str,
    *,
    settings: Settings | None = None,
) -> ArtifactRef:
    resolved_settings = settings if settings is not None else get_settings()
    return asyncio.run(
        _put_artifact_async(
            scope,
            profile_hash,
            stage,
            Path(source),
            resolved_settings,
        )
    )


def verify_artifact(
    ref: ArtifactRef,
    destination: Path | str,
    *,
    settings: Settings | None = None,
) -> None:
    resolved_settings = settings if settings is not None else get_settings()
    asyncio.run(
        _verify_artifact_async(
            ref,
            Path(destination),
            resolved_settings,
        )
    )
