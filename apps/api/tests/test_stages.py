import hashlib
from array import array
from dataclasses import replace
from itertools import batched
from pathlib import Path
from threading import Event
import time
from uuid import uuid4

import psycopg
import pytest

from test_jobs import snapshot
from test_schema import insert_job
from test_screening import _insert_owned_version, _pdf, private_bucket
from test_embedding import embedding_endpoint
from conftest import _database_url

from researcy.documents.artifacts import put_artifact
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
from researcy.ingestion.jobs import claim_due, commit_stage, seal_profile, short_transaction
from researcy.ingestion.models import (
    ArtifactRef,
    DocumentScope,
    IntegrityFailure,
    Lease,
    LostLease,
    ProcessingProfile,
    StageFailure,
    StageManifest,
)
from researcy.ingestion.stages import execute_stage
from researcy.papers.objects import get_owned_original, put_original
from researcy.papers.screening import screen_pdf
from researcy.retrieval import index
from researcy.retrieval.embedding import validate_vectors
from researcy.retrieval.repository import search_owned


_SOURCE_PARAGRAPH = "A born-digital source paragraph for durable processing testing."


@pytest.fixture
def staged_env(pg_conn, job_connections, tmp_path, monkeypatch, private_bucket):
    conn, _ = job_connections
    storage, bucket = private_bucket
    monkeypatch.setenv("DATABASE_URL", _database_url(pg_conn.info.dbname))
    monkeypatch.setenv("MINIO_BUCKET", bucket)

    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    original = _pdf(tmp_path / "stage-original.pdf", texts=(_SOURCE_PARAGRAPH,))
    source_bytes = original.read_bytes()
    source_hash = hashlib.sha256(source_bytes).digest()

    screen_pdf(original, "application/pdf")
    key = put_original(scope.owner_id, scope.document_version_id, original, source_hash.hex())
    _insert_owned_version(
        conn,
        scope.owner_id,
        scope.paper_id,
        scope.document_version_id,
        key,
        source_hash.hex(),
        len(source_bytes),
    )
    job = insert_job(conn, scope.owner_id, scope.document_version_id)
    conn.commit()

    return {
        "scope": scope,
        "job": job,
        "original": original,
        "expected_text": _SOURCE_PARAGRAPH,
        "source_bytes": source_bytes,
        "source_hash": source_hash,
        "key": key,
        "conn": conn,
        "storage": storage,
        "bucket": bucket,
        "tmp_path": tmp_path,
    }


def test_execute_stage_validating_seals_profile_and_commits_parsing(staged_env):
    conn = staged_env["conn"]
    job = staged_env["job"]
    scope = staged_env["scope"]
    source_hash = staged_env["source_hash"]
    key = staged_env["key"]
    source_bytes = staged_env["source_bytes"]

    lease = claim_due(conn, "stage-worker")
    assert lease is not None
    assert lease.stage == "validating"

    deadline = time.monotonic() + 30.0
    cancel = Event()
    execute_stage(lease, deadline, cancel)

    with short_transaction(conn):
        job_row = conn.execute(
            "SELECT stage, status, profile_hash FROM ingestion_jobs WHERE id=%s AND owner_id=%s",
            (job, scope.owner_id),
        ).fetchone()
        assert job_row[0] == "parsing"
        assert job_row[1] == "running"
        assert job_row[2] is not None

        proc_row = conn.execute(
            "SELECT original_sha256, profile_hash, index_version FROM document_processing WHERE document_version_id=%s",
            (scope.document_version_id,),
        ).fetchone()
        assert proc_row is not None
        assert bytes(proc_row[0]) == source_hash
        assert bytes(proc_row[1]) == bytes(job_row[2])

        manifest_row = conn.execute(
            "SELECT stage, content_hash, record_count, artifacts FROM stage_manifests WHERE document_version_id=%s AND stage='validating'",
            (scope.document_version_id,),
        ).fetchone()
        assert manifest_row is not None
        assert bytes(manifest_row[1]) == source_hash
        assert manifest_row[2] == 1
        artifacts = manifest_row[3]
        assert len(artifacts) == 1
        assert artifacts[0]["key"] == key
        assert artifacts[0]["sha256"] == source_hash.hex()
        assert artifacts[0]["byte_count"] == len(source_bytes)


def test_execute_stage_parsing_writes_immutable_artifact_and_commits_normalizing(staged_env):
    conn = staged_env["conn"]
    job = staged_env["job"]
    scope = staged_env["scope"]
    storage = staged_env["storage"]
    bucket = staged_env["bucket"]
    expected_text = staged_env["expected_text"]

    lease = claim_due(conn, "stage-worker")
    cancel = Event()
    execute_stage(lease, time.monotonic() + 30.0, cancel)
    lease = replace(lease, stage="parsing")

    execute_stage(lease, time.monotonic() + 30.0, cancel)

    with short_transaction(conn):
        job_row = conn.execute(
            "SELECT stage, status, profile_hash FROM ingestion_jobs WHERE id=%s AND owner_id=%s",
            (job, scope.owner_id),
        ).fetchone()
        assert job_row[0] == "normalizing"
        assert job_row[1] == "running"

        manifest_row = conn.execute(
            "SELECT stage, content_hash, record_count, artifacts FROM stage_manifests WHERE document_version_id=%s AND stage='parsing'",
            (scope.document_version_id,),
        ).fetchone()
        assert manifest_row is not None
        artifacts = manifest_row[3]
        assert len(artifacts) == 1
        artifact_key = artifacts[0]["key"]

    obj = storage.get_object(bucket, artifact_key)
    artifact_bytes = obj.read()
    obj.close()
    assert len(artifact_bytes) > 0
    assert hashlib.sha256(artifact_bytes).digest() == bytes(manifest_row[1])

    # Concrete assertions on parsed geometry and text from the immutable artifact
    temp_jsonl = staged_env["tmp_path"] / "verified_parser.jsonl"
    temp_jsonl.write_bytes(artifact_bytes)
    records = list(read_parser_records(temp_jsonl, SandboxLimits.full_parser()))
    page_record = next(r for r in records if r.kind == "page")
    assert page_record.page_index == 0
    assert page_record.media_box[2] > 0 and page_record.media_box[3] > 0

    span_record = next(r for r in records if r.kind == "span")
    assert span_record.raw_text == expected_text
    assert len(span_record.character_boxes) == len(expected_text)
    for box in span_record.character_boxes:
        assert len(box) == 4
        assert box[0] <= box[2] and box[1] <= box[3]


def test_execute_stage_normalizing_writes_canonical_rows_and_commits_chunking(staged_env):
    conn = staged_env["conn"]
    job = staged_env["job"]
    scope = staged_env["scope"]
    expected_text = staged_env["expected_text"]

    lease = claim_due(conn, "stage-worker")
    cancel = Event()
    execute_stage(lease, time.monotonic() + 30.0, cancel)
    lease = replace(lease, stage="parsing")
    execute_stage(lease, time.monotonic() + 30.0, cancel)
    lease = replace(lease, stage="normalizing")

    execute_stage(lease, time.monotonic() + 60.0, cancel)

    with short_transaction(conn):
        job_row = conn.execute(
            "SELECT stage, status FROM ingestion_jobs WHERE id=%s AND owner_id=%s",
            (job, scope.owner_id),
        ).fetchone()
        assert job_row == ("chunking", "running")

        pages = conn.execute(
            "SELECT page_index, media_box, width, height FROM document_pages WHERE document_version_id=%s",
            (scope.document_version_id,),
        ).fetchall()
        assert len(pages) == 1
        assert pages[0][0] == 0
        assert pages[0][2] > 0 and pages[0][3] > 0

        sections = conn.execute(
            "SELECT ordinal FROM document_sections WHERE document_version_id=%s ORDER BY ordinal",
            (scope.document_version_id,),
        ).fetchall()
        assert len(sections) >= 1
        assert sections[0][0] == 0

        spans = conn.execute(
            "SELECT raw_text, boxes FROM document_spans WHERE document_version_id=%s ORDER BY ordinal",
            (scope.document_version_id,),
        ).fetchall()
        assert len(spans) >= 1
        assert spans[0][0] == expected_text
        assert len(spans[0][1]) == len(expected_text)


def test_execute_stage_chunking_writes_chunks_and_commits_embedding(staged_env):
    conn = staged_env["conn"]
    job = staged_env["job"]
    scope = staged_env["scope"]
    expected_text = staged_env["expected_text"]

    lease = claim_due(conn, "stage-worker")
    cancel = Event()
    execute_stage(lease, time.monotonic() + 30.0, cancel)
    lease = replace(lease, stage="parsing")
    execute_stage(lease, time.monotonic() + 30.0, cancel)
    lease = replace(lease, stage="normalizing")
    execute_stage(lease, time.monotonic() + 60.0, cancel)
    lease = replace(lease, stage="chunking")

    execute_stage(lease, time.monotonic() + 60.0, cancel)

    with short_transaction(conn):
        job_row = conn.execute(
            "SELECT stage, status FROM ingestion_jobs WHERE id=%s AND owner_id=%s",
            (job, scope.owner_id),
        ).fetchone()
        assert job_row == ("embedding", "running")

        chunks = conn.execute(
            "SELECT ordinal, text, checksum FROM document_chunks WHERE document_version_id=%s ORDER BY ordinal",
            (scope.document_version_id,),
        ).fetchall()
        assert len(chunks) >= 1
        assert chunks[0][0] == 0
        assert expected_text in chunks[0][1]
        assert len(bytes(chunks[0][2])) == 32

        mappings = conn.execute(
            "SELECT chunk_id, ordinal, chunk_start, chunk_end, transformation FROM chunk_span_mappings WHERE document_version_id=%s ORDER BY ordinal",
            (scope.document_version_id,),
        ).fetchall()
        assert len(mappings) >= 1
        assert mappings[0][1] == 0
        assert mappings[0][2] == 0
        assert mappings[0][3] > 0
        assert mappings[0][4] in ("identity", "separator", "whitespace", "ligature", "dehyphenation")


def test_execute_stage_embedding_embeds_and_replays_selected_batches(staged_env, embedding_endpoint, monkeypatch):
    endpoint, state = embedding_endpoint
    monkeypatch.setenv("OLLAMA_BASE_URL", endpoint)

    conn = staged_env["conn"]
    job = staged_env["job"]
    scope = staged_env["scope"]
    storage = staged_env["storage"]
    bucket = staged_env["bucket"]

    lease = claim_due(conn, "stage-worker")
    cancel = Event()
    execute_stage(lease, time.monotonic() + 30.0, cancel)
    lease = replace(lease, stage="parsing")
    execute_stage(lease, time.monotonic() + 30.0, cancel)
    lease = replace(lease, stage="normalizing")
    execute_stage(lease, time.monotonic() + 60.0, cancel)
    lease = replace(lease, stage="chunking")
    execute_stage(lease, time.monotonic() + 60.0, cancel)
    lease = replace(lease, stage="embedding")

    embed_requests_before = len([r for r in state["requests"] if r[0] == "/api/embed"])
    execute_stage(lease, time.monotonic() + 60.0, cancel)
    embed_requests_after = len([r for r in state["requests"] if r[0] == "/api/embed"])
    assert embed_requests_after > embed_requests_before

    with short_transaction(conn):
        job_row = conn.execute(
            "SELECT stage, status FROM ingestion_jobs WHERE id=%s AND owner_id=%s",
            (job, scope.owner_id),
        ).fetchone()
        assert job_row == ("indexing", "running")

        batch_rows = conn.execute(
            "SELECT batch_ordinal, chunk_ids, selected_bytes, content_hash, artifact FROM embedding_batches WHERE document_version_id=%s ORDER BY batch_ordinal",
            (scope.document_version_id,),
        ).fetchall()
        assert len(batch_rows) >= 1
        batch_ord, chunk_ids, selected_bytes, content_hash, artifact_json = batch_rows[0]
        assert batch_ord == 0
        assert len(chunk_ids) >= 1
        raw_vecs = bytes(selected_bytes)
        assert len(raw_vecs) == len(chunk_ids) * 1024 * 4
        validate_vectors(raw_vecs, len(chunk_ids))
        assert hashlib.sha256(raw_vecs).digest() == bytes(content_hash)

    # Verify vector artifact stored in MinIO matches exact bytes
    obj = storage.get_object(bucket, artifact_json["key"])
    obj_bytes = obj.read()
    obj.close()
    assert obj_bytes == raw_vecs

    # Replay simulation: reset stage to 'embedding' to simulate restart with existing batches
    with short_transaction(conn):
        conn.execute("UPDATE ingestion_jobs SET stage='embedding' WHERE id=%s", (job,))
    lease = replace(lease, stage="embedding")

    req_count = len([r for r in state["requests"] if r[0] == "/api/embed"])
    execute_stage(lease, time.monotonic() + 60.0, cancel)
    # Concrete assertion: No new /api/embed calls made because batches were already selected
    assert len([r for r in state["requests"] if r[0] == "/api/embed"]) == req_count

    with short_transaction(conn):
        job_row = conn.execute("SELECT stage, status FROM ingestion_jobs WHERE id=%s", (job,)).fetchone()
        assert job_row == ("indexing", "running")


def test_execute_stage_indexing_and_publish_ready(selected_index, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _database_url(selected_index["conn"].info.dbname))
    lease = selected_index["lease"]
    conn = selected_index["conn"]
    job = selected_index["job"]
    scope = selected_index["scope"]

    cancel = Event()
    execute_stage(lease, time.monotonic() + 60.0, cancel)

    with short_transaction(conn):
        row = conn.execute(
            "SELECT stage, status FROM ingestion_jobs WHERE id=%s AND owner_id=%s",
            (job, scope.owner_id),
        ).fetchone()
        assert row == ("ready", "succeeded")

        pub = conn.execute(
            "SELECT point_count, embedding_manifest_hash FROM index_publications WHERE owner_id=%s AND document_version_id=%s",
            (scope.owner_id, scope.document_version_id),
        ).fetchone()
        assert pub is not None
        assert pub[0] == len(selected_index["chunks"])
        assert bytes(pub[1]) == selected_index["manifest"].content_hash

    # Concrete retrieval assertion: published index serves search query
    hits = search_owned(scope.owner_id, scope.paper_id, "evidence", 5)
    assert len(hits) >= 1
    assert any(hit.chunk_id in {c.id for c in selected_index["chunks"]} for hit in hits)


def test_execute_stage_cancellation_raises_lost_lease(staged_env):
    conn = staged_env["conn"]
    job = staged_env["job"]
    lease = claim_due(conn, "stage-worker")
    cancel = Event()
    cancel.set()

    with pytest.raises(LostLease):
        execute_stage(lease, time.monotonic() + 30.0, cancel)

    with short_transaction(conn):
        row = conn.execute("SELECT stage, status FROM ingestion_jobs WHERE id=%s", (job,)).fetchone()
        assert row == ("validating", "running")


def test_execute_stage_deadline_exceeded_raises_stage_failure(staged_env):
    conn = staged_env["conn"]
    job = staged_env["job"]
    lease = claim_due(conn, "stage-worker")
    cancel = Event()
    past_deadline = time.monotonic() - 1.0

    with pytest.raises(StageFailure) as exc:
        execute_stage(lease, past_deadline, cancel)
    assert exc.value.code in ("PROCESSING_RESOURCE_LIMIT", "PDF_PARSE_TIMEOUT", "DEPENDENCY_UNAVAILABLE")

    with short_transaction(conn):
        row = conn.execute("SELECT stage, status FROM ingestion_jobs WHERE id=%s", (job,)).fetchone()
        assert row == ("validating", "running")

def test_shutdown_during_embedding_sealing_does_not_advance_checkpoint(selected_index,monkeypatch):
    from researcy.ingestion import stages

    fixture=selected_index;conn=fixture['conn'];lease=replace(fixture['lease'],stage='embedding');cancel=Event()
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    with short_transaction(conn):
        conn.execute("UPDATE ingestion_jobs SET stage='embedding' WHERE id=%s",(lease.job_id,))
    original=stages.seal_embedding_manifest
    def shutdown_during_seal(*args,**kwargs):
        manifest=original(*args,**kwargs)
        cancel.set()
        return manifest
    monkeypatch.setattr(stages,'seal_embedding_manifest',shutdown_during_seal)
    with pytest.raises(LostLease):
        execute_stage(lease,time.monotonic()+30,cancel)
    assert snapshot(conn,lease.job_id)[:2]==('embedding','running')


def test_embedding_replay_requires_recoverable_private_selected_artifact(selected_index,private_bucket,monkeypatch):
    fixture=selected_index;conn=fixture['conn'];lease=replace(fixture['lease'],stage='embedding')
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    with short_transaction(conn):
        conn.execute("UPDATE ingestion_jobs SET stage='embedding' WHERE id=%s",(lease.job_id,))
    storage,bucket=private_bucket
    storage.remove_object(bucket,fixture['manifest'].artifacts[0].key)
    with pytest.raises(IntegrityFailure):
        execute_stage(lease,time.monotonic()+30,Event())
    assert snapshot(conn,lease.job_id)[:2]==('embedding','running')


@pytest.mark.parametrize('stage',['normalizing','chunking'])
def test_input_normalization_stops_consuming_after_lease_cancellation(staged_env,monkeypatch,stage):
    from researcy.ingestion import stages

    conn=staged_env['conn'];lease=claim_due(conn,'input-cancellation');cancel=Event()
    execute_stage(lease,time.monotonic()+30,cancel);lease=replace(lease,stage='parsing')
    execute_stage(lease,time.monotonic()+30,cancel);lease=replace(lease,stage='normalizing')
    if stage=='chunking':
        execute_stage(lease,time.monotonic()+30,cancel);lease=replace(lease,stage='chunking')
    original=stages.read_parser_records
    def interrupted_input(*args,**kwargs):
        for record in original(*args,**kwargs):
            cancel.set()
            yield record
            raise AssertionError('Cancelled normalization must not consume another input record')
    monkeypatch.setattr(stages,'read_parser_records',interrupted_input)
    with pytest.raises(LostLease):
        execute_stage(lease,time.monotonic()+30,cancel)
    assert snapshot(conn,lease.job_id)[:2]==(stage,'running')
