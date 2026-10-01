import hashlib
from itertools import batched
from pathlib import Path
import tempfile
from threading import Event
import time

import psycopg

from researcy.config import get_settings
from researcy.db import get_conn
from researcy.errors import APIError
from researcy.documents.artifacts import put_artifact, verify_artifact
from researcy.documents.chunking import chunk_section, iter_sections
from researcy.documents.models import SandboxLimits, read_parser_records
from researcy.documents.normalize import normalize_records
from researcy.documents.parser import parse_pdf
from researcy.documents.repository import (
    seal_embedding_manifest,
    select_embedding_batch,
    write_canonical_batch,
    write_chunk_batch,
)
from researcy.papers.screening import screen_pdf
from researcy.retrieval import index
from researcy.retrieval.embedding import EmbeddingClient, validate_vectors

from .jobs import commit_stage, require_owned, seal_profile, short_transaction
from .models import (
    ArtifactRef,
    IntegrityFailure,
    Lease,
    LostLease,
    ProcessingProfile,
    StageFailure,
    StageManifest,
)


def _get_profile(conn: psycopg.Connection, lease: Lease) -> tuple[ProcessingProfile, bytes]:
    row = conn.execute(
        """SELECT profile, profile_hash FROM document_processing
           WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s""",
        (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id),
    ).fetchone()
    if (
        row is None
        or not isinstance(row[0], dict)
        or not isinstance(row[1], (bytes, memoryview))
        or len(bytes(row[1])) != 32
    ):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    try:
        profile = ProcessingProfile(**row[0])
    except (TypeError, ValueError):
        raise IntegrityFailure("PROCESSING_CONFIGURATION_INVALID") from None
    profile_hash = bytes(row[1])
    if profile.profile_hash != profile_hash:
        raise IntegrityFailure("PROCESSING_CONFIGURATION_INVALID")
    return profile, profile_hash


def _get_parsing_ref(conn: psycopg.Connection, lease: Lease, profile_hash: bytes) -> ArtifactRef:
    row = conn.execute(
        """SELECT content_hash, artifacts FROM stage_manifests
           WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s
             AND profile_hash=%s AND stage='parsing'""",
        (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, profile_hash),
    ).fetchone()
    if row is None:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    content_hash, artifacts = row
    if not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    art = artifacts[0]
    for key in ("key", "sha256", "byte_count"):
        if key not in art:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    if not isinstance(art["key"], str) or not isinstance(art["sha256"], str) or not isinstance(art["byte_count"], int):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    try:
        ref_hash = bytes.fromhex(art["sha256"])
    except ValueError:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE") from None
    if bytes(content_hash) != ref_hash:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    try:
        return ArtifactRef(art["key"], ref_hash, art["byte_count"])
    except ValueError:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE") from None


def _controlled_records(records,deadline: float,cancel: Event):
    for record in records:
        if cancel.is_set():
            raise LostLease()
        if time.monotonic()>=deadline:
            raise StageFailure('PROCESSING_RESOURCE_LIMIT','resource_limit',False)
        yield record


def _execute_validating(lease: Lease, deadline: float, cancel: Event) -> None:
    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

    with get_conn() as conn:
        with short_transaction(conn):
            row = conn.execute(
                """SELECT sha256, byte_count, object_key FROM document_versions
                   WHERE id=%s AND owner_id=%s AND paper_id=%s""",
                (lease.scope.document_version_id, lease.scope.owner_id, lease.scope.paper_id),
            ).fetchone()
            if row is None:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            expected_sha256 = bytes(row[0])
            expected_bytes = row[1]
            object_key = row[2]
            orig_ref = ArtifactRef(object_key, expected_sha256, expected_bytes)

    with tempfile.TemporaryDirectory(prefix="val-") as temp_dir:
        temp_path = Path(temp_dir) / "source.pdf"
        verify_artifact(
            orig_ref,
            temp_path,
            deadline=min(deadline, time.monotonic() + 30.0),
            cancel=cancel,
        )

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

        try:
            screen_pdf(temp_path, "application/pdf", cancel=cancel, deadline=deadline)
        except LostLease:
            raise
        except APIError as exc:
            if exc.code in ("PDF_TOO_LARGE", "PDF_TOO_MANY_PAGES"):
                raise StageFailure(exc.code, "resource_limit", False) from None
            if exc.code in ("PDF_ENCRYPTED", "PDF_INVALID", "PDF_NO_TEXT"):
                raise StageFailure(exc.code, "unsupported", False) from None
            if exc.code == "PDF_SANDBOX_UNAVAILABLE":
                raise StageFailure("PDF_SANDBOX_UNAVAILABLE", "temporary", True, retry_after_seconds=5) from None
            if exc.code in ("PDF_SCREEN_TIMEOUT", "PDF_SCREEN_RESOURCE_LIMIT"):
                raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False) from None
            raise StageFailure("PROCESSING_INTEGRITY_FAILURE", "integrity", False) from None

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

        with get_conn() as conn:
            profile = seal_profile(conn, lease, ProcessingProfile())
            manifest = StageManifest("validating", profile.profile_hash, expected_sha256, 1, (orig_ref,))
            commit_stage(conn, lease, manifest, "parsing")


def _execute_parsing(lease: Lease, deadline: float, cancel: Event) -> None:
    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("PDF_PARSE_TIMEOUT", "resource_limit", False)

    with get_conn() as conn:
        with short_transaction(conn):
            profile, profile_hash = _get_profile(conn, lease)
            val_row = conn.execute(
                """SELECT content_hash, artifacts FROM stage_manifests
                   WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s
                     AND profile_hash=%s AND stage='validating'""",
                (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, profile_hash),
            ).fetchone()
            if val_row is None:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            expected_sha256 = bytes(val_row[0])
            val_artifacts = val_row[1]
            if not val_artifacts or len(val_artifacts) != 1:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            art = val_artifacts[0]
            orig_ref = ArtifactRef(art["key"], expected_sha256, art["byte_count"])

    with tempfile.TemporaryDirectory(prefix="parse-") as temp_dir:
        temp_source = Path(temp_dir) / "source.pdf"
        temp_output = Path(temp_dir) / "parsed.jsonl"

        verify_artifact(
            orig_ref,
            temp_source,
            deadline=min(deadline, time.monotonic() + 30.0),
            cancel=cancel,
        )

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PDF_PARSE_TIMEOUT", "resource_limit", False)

        limits = SandboxLimits.full_parser()
        parse_pdf(temp_source, temp_output, limits, cancel=cancel, deadline=deadline)

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PDF_PARSE_TIMEOUT", "resource_limit", False)

        # Count parser records with bounded stream counter rather than loading full list in memory
        record_count = 0
        for _ in read_parser_records(temp_output, limits):
            if cancel.is_set():
                raise LostLease()
            record_count += 1

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PDF_PARSE_TIMEOUT", "resource_limit", False)

        ref = put_artifact(lease.scope, profile_hash, "parsing", temp_output, deadline=deadline, cancel=cancel)

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PDF_PARSE_TIMEOUT", "resource_limit", False)

        with get_conn() as conn:
            manifest = StageManifest("parsing", profile_hash, ref.sha256, record_count, (ref,))
            commit_stage(conn, lease, manifest, "normalizing")


def _execute_normalizing(lease: Lease, deadline: float, cancel: Event) -> None:
    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

    with get_conn() as conn:
        with short_transaction(conn):
            profile, profile_hash = _get_profile(conn, lease)
            parsing_ref = _get_parsing_ref(conn, lease, profile_hash)

    with tempfile.TemporaryDirectory(prefix="norm-") as temp_dir:
        temp_parsed = Path(temp_dir) / "parsed.jsonl"
        verify_artifact(parsing_ref, temp_parsed, deadline=deadline, cancel=cancel)

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

        limits = SandboxLimits.full_parser()
        parser_records = _controlled_records(read_parser_records(temp_parsed, limits),deadline,cancel)
        canonical_records = normalize_records(parser_records, profile, scope=lease.scope)

        id_hasher = hashlib.sha256()
        record_count = 0
        batch = []
        for record in canonical_records:
            if cancel.is_set():
                raise LostLease()
            batch.append(record)
            id_hasher.update(record.id.bytes)
            record_count += 1
            if len(batch) >= 500:
                if cancel.is_set():
                    raise LostLease()
                if time.monotonic() >= deadline:
                    raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)
                with get_conn() as conn:
                    write_canonical_batch(conn, lease, batch)
                if cancel.is_set():
                    raise LostLease()
                batch.clear()

        if batch:
            if cancel.is_set():
                raise LostLease()
            if time.monotonic() >= deadline:
                raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)
            with get_conn() as conn:
                write_canonical_batch(conn, lease, batch)
            if cancel.is_set():
                raise LostLease()
            batch.clear()

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

        content_hash = id_hasher.digest()
        manifest = StageManifest("normalizing", profile_hash, content_hash, record_count, (parsing_ref,))
        with get_conn() as conn:
            commit_stage(conn, lease, manifest, "chunking")


def _execute_chunking(lease: Lease, deadline: float, cancel: Event) -> None:
    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

    with get_conn() as conn:
        with short_transaction(conn):
            profile, profile_hash = _get_profile(conn, lease)
            parsing_ref = _get_parsing_ref(conn, lease, profile_hash)

    max_chunks = getattr(get_settings(), "parser_max_chunks", profile.max_chunks)

    with tempfile.TemporaryDirectory(prefix="chunk-") as temp_dir:
        temp_parsed = Path(temp_dir) / "parsed.jsonl"
        verify_artifact(parsing_ref, temp_parsed, deadline=deadline, cancel=cancel)

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

        limits = SandboxLimits.full_parser()
        parser_records = _controlled_records(read_parser_records(temp_parsed, limits),deadline,cancel)
        canonical_records = normalize_records(parser_records, profile, scope=lease.scope)

        chunk_hasher = hashlib.sha256()
        total_chunks = 0
        batch = []

        for section in iter_sections(canonical_records):
            if cancel.is_set():
                raise LostLease()
            if time.monotonic() >= deadline:
                raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

            for chunk in chunk_section(section, profile, start_ordinal=total_chunks):
                if cancel.is_set():
                    raise LostLease()
                if total_chunks >= max_chunks:
                    raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

                batch.append(chunk)
                chunk_hasher.update(chunk.checksum)
                total_chunks += 1

                if len(batch) >= 500:
                    if cancel.is_set():
                        raise LostLease()
                    if time.monotonic() >= deadline:
                        raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)
                    with get_conn() as conn:
                        write_chunk_batch(conn, lease, batch)
                    if cancel.is_set():
                        raise LostLease()
                    batch.clear()

        if batch:
            if cancel.is_set():
                raise LostLease()
            if time.monotonic() >= deadline:
                raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)
            with get_conn() as conn:
                write_chunk_batch(conn, lease, batch)
            if cancel.is_set():
                raise LostLease()
            batch.clear()

        if cancel.is_set():
            raise LostLease()
        if time.monotonic() >= deadline:
            raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

        content_hash = chunk_hasher.digest()
        manifest = StageManifest("chunking", profile_hash, content_hash, total_chunks, ())
        with get_conn() as conn:
            commit_stage(conn, lease, manifest, "embedding")


def _execute_embedding(lease: Lease, deadline: float, cancel: Event) -> None:
    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

    with get_conn() as conn:
        with short_transaction(conn):
            profile, profile_hash = _get_profile(conn, lease)

    embedding = None
    identity = None

    cursor = 0
    with tempfile.TemporaryDirectory(prefix="embed-") as temp_dir:
        while True:
            if cancel.is_set():
                raise LostLease()
            if time.monotonic() >= deadline:
                raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

            with get_conn() as conn:
                with short_transaction(conn):
                    batch = conn.execute(
                        """SELECT id, ordinal, text FROM document_chunks
                           WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s
                             AND ordinal >= %s
                           ORDER BY ordinal LIMIT 4""",
                        (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, profile_hash, cursor),
                    ).fetchall()

            if not batch:
                if cursor == 0:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                break

            batch_ordinal = cursor // 4
            chunk_ids = tuple(row[0] for row in batch)

            with get_conn() as conn:
                with short_transaction(conn):
                    existing = conn.execute(
                        """SELECT chunk_ids, selected_bytes, content_hash, artifact FROM embedding_batches
                           WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s
                             AND profile_hash=%s AND batch_ordinal=%s""",
                        (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, profile_hash, batch_ordinal),
                    ).fetchone()

            if existing is not None:
                # Replay verification: verify existing batch integrity without re-embedding
                if tuple(existing[0]) != chunk_ids:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                existing_bytes = bytes(existing[1])
                validate_vectors(existing_bytes, len(chunk_ids))
                if hashlib.sha256(existing_bytes).digest() != bytes(existing[2]):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                value=existing[3]
                try:
                    ref=ArtifactRef(value['key'],bytes.fromhex(value['sha256']),value['byte_count'])
                except (KeyError,TypeError,ValueError):
                    raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE') from None
                if ref.sha256!=bytes(existing[2]) or ref.byte_count!=len(existing_bytes):
                    raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
                replay_path=Path(temp_dir)/f'replay-{batch_ordinal}.bin'
                verify_artifact(ref,replay_path,deadline=deadline,cancel=cancel)
                if replay_path.read_bytes()!=existing_bytes:
                    raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
                replay_path.unlink()
                cursor += len(batch)
                continue

            if embedding is None:
                embedding = EmbeddingClient(profile, cancel=cancel)
                remaining = max(0.001, deadline - time.monotonic())
                embedding.timeout = min(embedding.timeout, remaining)

                if cancel.is_set():
                    raise LostLease()
                identity = embedding.preflight()
                if cancel.is_set():
                    raise LostLease()

            remaining = max(0.001, deadline - time.monotonic())
            embedding.timeout = min(embedding.timeout, remaining)

            texts = tuple(row[2] for row in batch)
            encoded = embedding.embed(texts)

            if cancel.is_set():
                raise LostLease()
            if time.monotonic() >= deadline:
                raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

            vec_path = Path(temp_dir) / f"embed-{batch_ordinal}.bin"
            vec_path.write_bytes(encoded)
            artifact = put_artifact(lease.scope, profile_hash, "embedding", vec_path, deadline=deadline, cancel=cancel)

            if cancel.is_set():
                raise LostLease()
            if time.monotonic() >= deadline:
                raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

            with get_conn() as conn:
                select_embedding_batch(
                    conn,
                    lease,
                    batch_ordinal,
                    artifact,
                    chunk_ids,
                    selected_bytes=encoded,
                    runtime_identity=identity,
                )

            if cancel.is_set():
                raise LostLease()

            cursor += len(batch)

    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

    with get_conn() as conn:
        manifest = seal_embedding_manifest(conn, lease,deadline=deadline,cancel=cancel)
        if cancel.is_set():
            raise LostLease()
        if time.monotonic()>=deadline:
            raise StageFailure('DEPENDENCY_UNAVAILABLE','temporary',True,retry_after_seconds=5)
        commit_stage(conn, lease, manifest, "indexing")


def _execute_indexing(lease: Lease, deadline: float, cancel: Event) -> None:
    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

    with get_conn() as conn:
        with short_transaction(conn):
            profile, _ = _get_profile(conn, lease)

    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

    qdrant_client = index.QdrantClient(deadline=deadline, cancel=cancel)
    index.ensure_collection(profile, client=qdrant_client)

    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

    receipt = index.index_selected(lease, deadline, cancel=cancel)

    if cancel.is_set():
        raise LostLease()

    with get_conn() as conn:
        index.publish_ready(conn, lease, receipt)


def execute_stage(lease: Lease, deadline: float, cancel: Event) -> None:
    """Execute the exact current stage according to lease and commit to next stage."""
    if cancel.is_set():
        raise LostLease()
    if time.monotonic() >= deadline:
        if lease.stage == "parsing":
            raise StageFailure("PDF_PARSE_TIMEOUT", "resource_limit", False)
        if lease.stage in ("embedding", "indexing"):
            raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)
        raise StageFailure("PROCESSING_RESOURCE_LIMIT", "resource_limit", False)

    if lease.stage == "validating":
        _execute_validating(lease, deadline, cancel)
    elif lease.stage == "parsing":
        _execute_parsing(lease, deadline, cancel)
    elif lease.stage == "normalizing":
        _execute_normalizing(lease, deadline, cancel)
    elif lease.stage == "chunking":
        _execute_chunking(lease, deadline, cancel)
    elif lease.stage == "embedding":
        _execute_embedding(lease, deadline, cancel)
    elif lease.stage == "indexing":
        _execute_indexing(lease, deadline, cancel)
    else:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
