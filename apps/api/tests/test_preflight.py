from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os
import secrets
import sys
import time

import httpx2
import psycopg
import pymupdf
import pytest

from researcy.config import Settings, get_settings
from researcy.ingestion.models import ProcessingProfile, QUALIFIED_MODEL_DIGEST
from test_screening import _pdf, private_bucket
from test_embedding import embedding_endpoint


def _create_known_probe_pdf(path: Path) -> tuple[Path, bytes, str]:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((72, 72), "Researcy preflight probe document.")
    doc.set_metadata({"title": "Preflight Probe"})
    doc.save(path)
    doc.close()
    content = path.read_bytes()
    expected_sha256 = hashlib.sha256(content).hexdigest()
    return path, content, expected_sha256


def test_check_migrations_accepts_head_and_rejects_unmigrated(pg_conn):
    from researcy.ingestion import preflight

    # Current head migration for M2 durable processing
    preflight.check_migrations(pg_conn)

    # If database is rolled back or points to older migration, preflight fails safely
    with pg_conn.transaction():
        pg_conn.execute("UPDATE alembic_version SET version_num = '0002_m1_source_guards'")

    with pytest.raises(preflight.PreflightFailure) as exc_info:
        preflight.check_migrations(pg_conn)
    assert exc_info.value.dependency == "postgres"

    # If alembic_version table has no rows (unmigrated database)
    with pg_conn.transaction():
        pg_conn.execute("DELETE FROM alembic_version")

    with pytest.raises(preflight.PreflightFailure) as exc_info:
        preflight.check_migrations(pg_conn)
    assert exc_info.value.dependency == "postgres"


def test_check_migrations_default_connection_uses_database_url(pg_conn, monkeypatch):
    from conftest import _database_url
    from researcy.ingestion import preflight

    monkeypatch.setenv("DATABASE_URL", _database_url(pg_conn.info.dbname))
    preflight.check_migrations()

def test_check_storage_isolated_probe_verifies_and_always_cleans_up(private_bucket, monkeypatch):
    from researcy.ingestion import preflight
    from researcy.documents.artifacts import _get_minio_client

    settings = get_settings()
    preflight.check_storage(settings=settings)

    # Verify no leaked probe files remain in private bucket
    client = _get_minio_client(settings)
    objects = list(client.list_objects(settings.storage_bucket, prefix="preflight-probes/", recursive=True))
    assert len(objects) == 0

    # Test failure cleanup: verify that even when readback verification fails,
    # probe object is removed in cleanup
    original_presigned_get = client.presigned_get_object

    def bad_presigned_get(bucket, key, *args, **kwargs):
        # Point to a nonexistent key so GET returns 404
        return original_presigned_get(bucket, f"{key}-nonexistent", *args, **kwargs)

    monkeypatch.setattr(client, "presigned_get_object", bad_presigned_get)
    monkeypatch.setattr(preflight, "_get_minio_client", lambda s: client)

    with pytest.raises(preflight.PreflightFailure) as exc_info:
        preflight.check_storage(settings=settings)
    assert exc_info.value.dependency == "storage"

    # Cleanup must have executed and deleted the probe object
    objects_after = list(client.list_objects(settings.storage_bucket, prefix="preflight-probes/", recursive=True))
    assert len(objects_after) == 0

def test_check_storage_cleanup_delete_stall_times_out_and_fails(private_bucket, monkeypatch):
    import http.server
    import threading
    from researcy.ingestion import preflight
    from researcy.documents.artifacts import _get_minio_client

    settings = get_settings()
    client = _get_minio_client(settings)

    delete_received = threading.Event()

    class StallingDeleteHandler(http.server.BaseHTTPRequestHandler):
        def do_DELETE(self):
            delete_received.set()
            time.sleep(1.0)
            self.send_response(204)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), StallingDeleteHandler)
    server_port = server.server_port
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    real_presigned_url = client.get_presigned_url

    def intercept_presigned_url(method, bucket, key, *args, **kwargs):
        if method == "DELETE":
            return f"http://127.0.0.1:{server_port}/stalled-delete"
        return real_presigned_url(method, bucket, key, *args, **kwargs)

    monkeypatch.setattr(client, "get_presigned_url", intercept_presigned_url)
    monkeypatch.setattr(preflight, "_get_minio_client", lambda s: client)

    try:
        with pytest.raises(preflight.PreflightFailure) as exc_info:
            preflight.check_storage(settings=settings, timeout=0.15)
        assert exc_info.value.dependency == "storage"
        assert delete_received.is_set()
    finally:
        server.server_close()
        server_thread.join(timeout=2.0)

def test_check_storage_total_deadline_timeout_fails_safely(private_bucket):
    from researcy.ingestion import preflight

    settings = get_settings()
    with pytest.raises(preflight.PreflightFailure) as exc_info:
        preflight.check_storage(settings=settings, timeout=0.0001)
    assert exc_info.value.dependency == "storage"

def test_check_storage_unreachable_fails_with_safe_dependency(monkeypatch):
    from researcy.ingestion import preflight

    monkeypatch.setenv("MINIO_ENDPOINT", "127.0.0.1:59999")
    bad_settings = Settings.from_env()

    with pytest.raises(preflight.PreflightFailure) as exc_info:
        preflight.check_storage(settings=bad_settings)
    assert exc_info.value.dependency == "storage"


def test_check_qdrant_verifies_real_collection_schema_and_payload_indexes(monkeypatch):
    from researcy.ingestion import preflight
    from researcy.retrieval import index

    profile = ProcessingProfile()
    test_collection = f"test_preflight_schema_{uuid4().hex}"
    monkeypatch.setattr(index, "collection_name", lambda p: test_collection)

    # Use actual Qdrant client to test ensure_collection and schema verification
    endpoint = get_settings().qdrant_endpoint
    client = index.QdrantClient(endpoint, deadline=time.monotonic() + 30)

    try:
        preflight.check_qdrant(profile=profile, settings=get_settings())

        # Read back actual collection from Qdrant and assert exact schema
        info = client.request("GET", f"/collections/{test_collection}")
        assert info["status"] == "ok"
        params = info["result"]["config"]["params"]["vectors"]
        assert params["size"] == 1024
        assert params["distance"].lower() == "cosine"
        payload_schema = info["result"].get("payload_schema", {})
        for field in ("owner_id", "paper_id", "document_version_id", "section_type"):
            assert field in payload_schema
            assert payload_schema[field]["data_type"] == "keyword"
    finally:
        client.deadline = time.monotonic() + 10
        client.request("DELETE", f"/collections/{test_collection}")
        client.close()


def test_check_qdrant_wrong_existing_schema_fails_without_mutating_or_deleting(monkeypatch):
    from researcy.ingestion import preflight
    from researcy.retrieval import index

    profile = ProcessingProfile()
    test_collection = f"test_preflight_bad_schema_{uuid4().hex}"
    monkeypatch.setattr(index, "collection_name", lambda p: test_collection)

    endpoint = get_settings().qdrant_endpoint
    client = index.QdrantClient(endpoint, deadline=time.monotonic() + 30)

    try:
        # Create collection with incompatible vector dimension (768 != 1024)
        create_res = client.request("PUT", f"/collections/{test_collection}", {
            "vectors": {"size": 768, "distance": "Cosine"}
        })
        assert create_res.get("status") == "ok"

        # Preflight must fail safely with safe dependency "qdrant"
        with pytest.raises(preflight.PreflightFailure) as exc_info:
            preflight.check_qdrant(profile=profile, settings=get_settings())
        assert exc_info.value.dependency == "qdrant"

        # Invariant: Preflight must NOT delete or mutate the existing collection
        existing = client.request("GET", f"/collections/{test_collection}")
        assert existing.get("status") == "ok"
        assert existing["result"]["config"]["params"]["vectors"]["size"] == 768
    finally:
        client.deadline = time.monotonic() + 10
        client.request("DELETE", f"/collections/{test_collection}")
        client.close()


def test_check_embedding_malformed_vector_is_a_safe_dependency_failure(embedding_endpoint,monkeypatch):
    from researcy.ingestion import preflight

    endpoint,state=embedding_endpoint
    state['mode']='dimension'
    monkeypatch.setenv('OLLAMA_BASE_URL',endpoint)
    with pytest.raises(preflight.PreflightFailure) as error:
        preflight.check_embedding()
    assert error.value.dependency=='embedding'



def test_check_sandbox_containment_verifies_actual_document_screening(tmp_path):
    from researcy.ingestion import preflight

    probe_path, expected_bytes, expected_sha256 = _create_known_probe_pdf(tmp_path / "probe.pdf")

    if sys.platform == "linux":
        # On Linux deployed runtime, sandbox runs screening and extracts actual properties
        result = preflight.check_sandbox(probe_pdf=probe_path)
        assert result.pages == 1
        assert result.sha256 == expected_sha256
        assert result.bytes == len(expected_bytes)
    else:
        # On Darwin / non-Linux, sandbox containment fails closed
        with pytest.raises(preflight.PreflightFailure) as exc_info:
            preflight.check_sandbox(probe_pdf=probe_path)
        assert exc_info.value.dependency == "sandbox"

@pytest.mark.skipif(sys.platform!='linux',reason='Requires the deployed Linux containment boundary')
def test_default_preflight_generates_and_screens_its_private_probe(tmp_path):
    from researcy.ingestion import preflight

    result=preflight.check_sandbox(tmp_dir=tmp_path)
    assert result.pages==1
    assert not list(tmp_path.iterdir())



def test_preflight_never_claims_or_mutates_jobs(pg_conn, queued_job, monkeypatch):
    from researcy.ingestion import preflight

    scope, job_id = queued_job

    # Snapshot job before preflight
    before = pg_conn.execute(
        "SELECT status, stage, attempts, cycle_attempts, locked_by, lease_expires_at, heartbeat_at FROM ingestion_jobs WHERE id = %s",
        (job_id,)
    ).fetchone()
    assert before[0] == "pending"
    assert before[1] == "queued"
    assert before[4] is None

    # Stub the individual sub-checks to test the preflight pipeline itself
    monkeypatch.setattr(preflight, "check_migrations", lambda *args, **kwargs: None)
    monkeypatch.setattr(preflight, "check_storage", lambda *args, **kwargs: None)
    monkeypatch.setattr(preflight, "check_qdrant", lambda *args, **kwargs: None)
    monkeypatch.setattr(preflight, "check_embedding", lambda *args, **kwargs: {})
    monkeypatch.setattr(preflight, "check_sandbox", lambda *args, **kwargs: None)

    preflight.run_preflight(conn=pg_conn)

    # Invariant: job row was completely untouched
    after = pg_conn.execute(
        "SELECT status, stage, attempts, cycle_attempts, locked_by, lease_expires_at, heartbeat_at FROM ingestion_jobs WHERE id = %s",
        (job_id,)
    ).fetchone()
    assert after == before


def test_preflight_cli_check_returns_zero_on_healthy_system(monkeypatch):
    from researcy.ingestion import preflight

    monkeypatch.setattr(preflight, "check_migrations", lambda *args, **kwargs: None)
    monkeypatch.setattr(preflight, "check_storage", lambda *args, **kwargs: None)
    monkeypatch.setattr(preflight, "check_qdrant", lambda *args, **kwargs: None)
    monkeypatch.setattr(preflight, "check_embedding", lambda *args, **kwargs: {})
    monkeypatch.setattr(preflight, "check_sandbox", lambda *args, **kwargs: None)

    code = preflight.main(["--check"])
    assert code == 0


def test_preflight_cli_failure_reports_safe_dependency_name_and_never_leaks_secrets(monkeypatch, capsys):
    from researcy.ingestion import preflight

    secret_postgres = "secret-postgres-pw-abc123"
    secret_minio = "secret-minio-pw-xyz789"
    secret_session = "secret-session-lookup-key-456"
    monkeypatch.setenv("POSTGRES_PASSWORD", secret_postgres)
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", secret_minio)
    monkeypatch.setenv("SESSION_LOOKUP_KEY", secret_session)

    # Simulate storage failure
    def failing_storage(*args, **kwargs):
        raise preflight.PreflightFailure("storage")

    monkeypatch.setattr(preflight, "check_migrations", lambda *args, **kwargs: None)
    monkeypatch.setattr(preflight, "check_storage", failing_storage)

    code = preflight.main(["--check"])
    assert code != 0

    captured = capsys.readouterr()
    output = captured.out + captured.err
    # Must report safe dependency name only
    assert "storage" in output.lower()
    # Must NEVER leak passwords or secret keys
    assert secret_postgres not in output
    assert secret_minio not in output
    assert secret_session not in output


def test_preflight_cli_rejects_unknown_flags(capsys):
    from researcy.ingestion import preflight

    code = preflight.main(["--unknown-flag"])
    assert code != 0
