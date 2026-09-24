import hashlib
import io
import os
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

import psycopg
import pymupdf
import pytest
from fastapi.testclient import TestClient
from minio import Minio

from conftest import _database_url
from researcy.auth.sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    issue_session,
    session_lookup,
)
from researcy.config import Settings
from researcy.errors import APIError
from researcy.main import app
from researcy.papers.arxiv import ArxivAcquisition, ArxivMetadata, ArxivUpstreamError


BASE_URL = "http://localhost:3000"
ISSUER = "https://accounts.google.com"
SESSION_LOOKUP_KEY = "intake-test-session-lookup-key-at-least-32-bytes"
MINIO_ENDPOINT = "127.0.0.1:9000"
MINIO_ACCESS_KEY = "researcy-minio"
MINIO_SECRET_KEY = "local-minio-password"


@pytest.fixture
def private_bucket(monkeypatch):
    endpoint = os.environ.get("MINIO_ENDPOINT", MINIO_ENDPOINT)
    access_key = os.environ.get("MINIO_ROOT_USER", MINIO_ACCESS_KEY)
    secret_key = os.environ.get("MINIO_ROOT_PASSWORD", MINIO_SECRET_KEY)
    bucket = f"intake-test-{uuid4().hex}"
    monkeypatch.setenv("MINIO_ENDPOINT", endpoint)
    monkeypatch.setenv("MINIO_ROOT_USER", access_key)
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", secret_key)
    monkeypatch.setenv("MINIO_BUCKET", bucket)

    secure = os.environ.get("MINIO_SECURE", "false").strip().lower() == "true"
    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    client.make_bucket(bucket)
    try:
        yield client, bucket
    finally:
        for item in client.list_objects(bucket, recursive=True):
            client.remove_object(bucket, item.object_name)
        client.remove_bucket(bucket)


@pytest.fixture
def client(monkeypatch, pg_conn, private_bucket):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_ORIGINS", BASE_URL)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("SESSION_LOOKUP_KEY", SESSION_LOOKUP_KEY)
    monkeypatch.setenv("DATABASE_URL", _database_url(pg_conn.info.dbname))

    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client


def _insert_user(conn, sub: str) -> UUID:
    return conn.execute(
        "INSERT INTO users (issuer, sub) VALUES (%s, %s) RETURNING id",
        (ISSUER, sub),
    ).fetchone()[0]


def _auth_headers(client: TestClient, conn, owner_id: UUID) -> dict[str, str]:
    session_token, csrf_token = issue_session(conn, owner_id, SESSION_LOOKUP_KEY.encode())
    conn.commit()
    client.cookies.set(SESSION_COOKIE, session_token)
    client.cookies.set(CSRF_COOKIE, csrf_token)
    return {
        "Origin": BASE_URL,
        "x-csrf-token": csrf_token,
    }


def _make_pdf(
    path: Path,
    texts=("A born-digital PDF with enough extractable text.\n" * 8,),
    *,
    title: str = "Test PDF Title",
) -> Path:
    doc = pymupdf.open()
    for text in texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.set_metadata({"title": title})
    doc.save(path)
    doc.close()
    return path


def test_upload_accepted_creates_paper_version_job_and_object(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "upload-owner-1")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "key-upload-1"

    pdf_path = _make_pdf(tmp_path / "valid.pdf", title="Deep Residual Learning")
    pdf_bytes = pdf_path.read_bytes()

    res = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("valid.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["stage"] == "queued"
    assert data["screening_warning"] is None
    paper_id = UUID(data["paper_id"])
    version_id = UUID(data["document_version"])
    job_id = UUID(data["job_id"])

    # Verify single owned DB rows
    paper_row = pg_conn.execute(
        "SELECT id, owner_id, source, title, active_version_id FROM papers WHERE id = %s",
        (paper_id,),
    ).fetchone()
    assert paper_row is not None
    assert paper_row[1] == owner
    assert paper_row[2] == "upload"
    assert paper_row[3] == "Deep Residual Learning"
    assert paper_row[4] == version_id

    version_row = pg_conn.execute(
        "SELECT id, owner_id, paper_id, byte_count, object_key FROM document_versions WHERE id = %s",
        (version_id,),
    ).fetchone()
    assert version_row is not None
    assert version_row[1] == owner
    assert version_row[2] == paper_id
    assert version_row[3] == len(pdf_bytes)
    object_key = version_row[4]

    job_row = pg_conn.execute(
        "SELECT id, owner_id, document_version_id, stage FROM ingestion_jobs WHERE id = %s",
        (job_id,),
    ).fetchone()
    assert job_row is not None
    assert job_row[1] == owner
    assert job_row[2] == version_id
    assert job_row[3] == "queued"

    # Verify object storage
    minio_client, bucket = private_bucket
    obj = minio_client.get_object(bucket, object_key)
    stored_bytes = obj.read()
    obj.close()
    obj.release_conn()
    assert stored_bytes == pdf_bytes


def test_upload_exact_replay_returns_200_without_quota_or_new_records(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "upload-replay-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "replay-key-1"

    pdf_path = _make_pdf(tmp_path / "replay.pdf")
    pdf_bytes = pdf_path.read_bytes()

    first = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("replay.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert first.status_code == 202
    first_data = first.json()

    # Replay with same key and identical bytes
    replay = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("replay.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert replay.status_code == 200
    replay_data = replay.json()

    assert replay_data["paper_id"] == first_data["paper_id"]
    assert replay_data["document_version"] == first_data["document_version"]
    assert replay_data["job_id"] == first_data["job_id"]
    assert replay_data["stage"] == first_data["stage"]

    # Verify no second job or version created
    job_count = pg_conn.execute(
        "SELECT count(*) FROM ingestion_jobs WHERE owner_id = %s", (owner,)
    ).fetchone()[0]
    assert job_count == 1

    # Verify rate limit request count is only 1
    quota_count = pg_conn.execute(
        "SELECT request_count FROM import_rate_limits WHERE owner_id = %s", (owner,)
    ).fetchone()[0]
    assert quota_count == 1


def test_upload_same_key_changed_bytes_returns_409(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "upload-conflict-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "conflict-key-1"

    pdf1 = _make_pdf(tmp_path / "pdf1.pdf", title="PDF One")
    pdf2 = _make_pdf(tmp_path / "pdf2.pdf", title="PDF Two")

    res1 = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("p1.pdf", io.BytesIO(pdf1.read_bytes()), "application/pdf")},
    )
    assert res1.status_code == 202

    res2 = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("p2.pdf", io.BytesIO(pdf2.read_bytes()), "application/pdf")},
    )
    assert res2.status_code == 409
    assert res2.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_same_key_changed_operation_returns_409(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "op-conflict-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "op-conflict-key"

    pdf = _make_pdf(tmp_path / "op.pdf")
    res1 = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("op.pdf", io.BytesIO(pdf.read_bytes()), "application/pdf")},
    )
    assert res1.status_code == 202

    # Now call arxiv with the same key
    res2 = client.post(
        "/api/papers/arxiv",
        headers=headers,
        json={"arxiv_id_or_url": "1706.03762"},
    )
    assert res2.status_code == 409
    assert res2.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_arxiv_accepted_creates_paper_version_job_and_object(client, pg_conn, private_bucket, tmp_path, monkeypatch):
    owner = _insert_user(pg_conn, "arxiv-owner-1")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "arxiv-key-1"

    pdf_path = _make_pdf(tmp_path / "arxiv.pdf", title="Attention Is All You Need")
    pdf_bytes = pdf_path.read_bytes()

    fake_acquisition = ArxivAcquisition(
        metadata=ArxivMetadata(title="Attention Is All You Need", authors=["Ashish Vaswani"], year=2017),
        resolved_version=1,
        pdf_path=pdf_path,
        source_url="https://arxiv.org/pdf/1706.03762v1",
    )
    import researcy.papers.intake as intake_mod
    monkeypatch.setattr(
        intake_mod,
        "fetch_official_arxiv",
        lambda *args, **kwargs: fake_acquisition,
    )

    res = client.post(
        "/api/papers/arxiv",
        headers=headers,
        json={"arxiv_id_or_url": "1706.03762"},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["stage"] == "queued"
    assert data["source_version"] == "v1"

    paper_row = pg_conn.execute(
        "SELECT canonical_arxiv_id, source FROM papers WHERE id = %s",
        (UUID(data["paper_id"]),),
    ).fetchone()
    assert paper_row[0] == "1706.03762"
    assert paper_row[1] == "arxiv"


def test_arxiv_unversioned_new_key_returns_stored_version_without_fetch(client, pg_conn, private_bucket, tmp_path, monkeypatch):
    owner = _insert_user(pg_conn, "arxiv-owner-unversioned")
    headers = _auth_headers(client, pg_conn, owner)

    pdf_path = _make_pdf(tmp_path / "arxiv_v1.pdf")
    pdf_bytes = pdf_path.read_bytes()

    fetch_called = False

    def mock_fetch(*args, **kwargs):
        nonlocal fetch_called
        fetch_called = True
        return ArxivAcquisition(
            metadata=ArxivMetadata(title="Attention", authors=["Vaswani"], year=2017),
            resolved_version=1,
            pdf_path=pdf_path,
            source_url="https://arxiv.org/pdf/1706.03762v1",
        )
    import researcy.papers.intake as intake_mod
    monkeypatch.setattr(intake_mod, "fetch_official_arxiv", mock_fetch)

    # First import
    headers["Idempotency-Key"] = "key-arxiv-first"
    first = client.post(
        "/api/papers/arxiv",
        headers=headers,
        json={"arxiv_id_or_url": "1706.03762"},
    )
    assert first.status_code == 202
    assert fetch_called is True

    # Reset flag and call with NEW key and unversioned reference
    fetch_called = False
    headers["Idempotency-Key"] = "key-arxiv-new-unversioned"
    second = client.post(
        "/api/papers/arxiv",
        headers=headers,
        json={"arxiv_id_or_url": "1706.03762"},
    )
    assert second.status_code == 200
    assert fetch_called is False  # Zero fetch!
    assert second.json()["paper_id"] == first.json()["paper_id"]
    assert second.json()["source_version"] == "v1"


def test_arxiv_explicit_different_version_returns_409_without_fetch(client, pg_conn, private_bucket, tmp_path, monkeypatch):
    owner = _insert_user(pg_conn, "arxiv-owner-diff-v")
    headers = _auth_headers(client, pg_conn, owner)
    pdf_path = _make_pdf(tmp_path / "arxiv_v1.pdf")
    pdf_bytes = pdf_path.read_bytes()
    fetch_called = False
    def mock_fetch(*args, **kwargs):
        nonlocal fetch_called
        fetch_called = True
        return ArxivAcquisition(
            metadata=ArxivMetadata(title="Attention", authors=["Vaswani"], year=2017),
            resolved_version=1,
            pdf_path=pdf_path,
            source_url="https://arxiv.org/pdf/1706.03762v1",
        )
    import researcy.papers.intake as intake_mod
    monkeypatch.setattr(intake_mod, "fetch_official_arxiv", mock_fetch)

    headers["Idempotency-Key"] = "key-arxiv-v1"
    client.post("/api/papers/arxiv", headers=headers, json={"arxiv_id_or_url": "1706.03762v1"})

    fetch_called = False
    headers["Idempotency-Key"] = "key-arxiv-v2"
    res = client.post("/api/papers/arxiv", headers=headers, json={"arxiv_id_or_url": "1706.03762v2"})
    assert res.status_code == 409
    assert res.json()["code"] == "ARXIV_VERSION_CONFLICT"
    assert fetch_called is False  # Zero fetch!


def test_concurrent_same_key_upload_yields_one_job_and_object(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "concurrent-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "concurrent-key-1"

    pdf_path = _make_pdf(tmp_path / "concurrent.pdf")
    pdf_bytes = pdf_path.read_bytes()

    def do_upload():
        with TestClient(app, base_url=BASE_URL) as thread_client:
            thread_client.cookies.set(SESSION_COOKIE, client.cookies.get(SESSION_COOKIE))
            thread_client.cookies.set(CSRF_COOKIE, client.cookies.get(CSRF_COOKIE))
            return thread_client.post(
                "/api/papers/upload",
                headers=headers,
                files={"file": ("concurrent.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(do_upload)
        f2 = pool.submit(do_upload)
        res1 = f1.result()
        res2 = f2.result()

    statuses = {res1.status_code, res2.status_code}
    assert statuses in ({202, 200}, {202}, {200})

    job_count = pg_conn.execute(
        "SELECT count(*) FROM ingestion_jobs WHERE owner_id = %s", (owner,)
    ).fetchone()[0]
    assert job_count == 1

    # Exactly 1 object in minio bucket
    minio_client, bucket = private_bucket
    objects = list(minio_client.list_objects(bucket, recursive=True))
    assert len(objects) == 1


def test_upload_exceeds_cap_rejected_while_streaming(client, pg_conn, private_bucket, monkeypatch):
    owner = _insert_user(pg_conn, "overflow-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "overflow-key"
    headers["Content-Length"] = "50"  # False length!

    # Cap to 500 bytes for this test
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "500")

    big_payload = b"%PDF-" + (b"A" * 1000)
    res = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("overflow.pdf", io.BytesIO(big_payload), "application/pdf")},
    )
    assert res.status_code == 413
    assert res.json()["code"] == "PDF_TOO_LARGE"

    # Verify no job, no paper, no object
    assert pg_conn.execute("SELECT count(*) FROM papers WHERE owner_id = %s", (owner,)).fetchone()[0] == 0
    minio_client, bucket = private_bucket
    assert len(list(minio_client.list_objects(bucket, recursive=True))) == 0


def test_csrf_rejection_leaves_no_side_effects(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "csrf-victim")
    headers = _auth_headers(client, pg_conn, owner)
    headers["x-csrf-token"] = "invalid-token"
    headers["Idempotency-Key"] = "csrf-key"

    pdf_path = _make_pdf(tmp_path / "csrf.pdf")
    res = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("csrf.pdf", io.BytesIO(pdf_path.read_bytes()), "application/pdf")},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "CSRF_REJECTED"

    assert pg_conn.execute("SELECT count(*) FROM papers WHERE owner_id = %s", (owner,)).fetchone()[0] == 0
    minio_client, bucket = private_bucket
    assert len(list(minio_client.list_objects(bucket, recursive=True))) == 0


def test_db_commit_failure_triggers_minio_compensation(client, pg_conn, private_bucket, tmp_path, monkeypatch):
    owner = _insert_user(pg_conn, "compensation-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "compensation-key"

    pdf_path = _make_pdf(tmp_path / "compensate.pdf")

    from contextlib import contextmanager
    import researcy.db as db_mod
    import researcy.papers.routes as routes_mod

    orig_get_conn = db_mod.get_conn
    @contextmanager
    def failing_conn():
        with orig_get_conn() as conn:
            orig_execute = conn.execute
            def intercept_execute(query, *args, **kwargs):
                if "INSERT INTO papers" in str(query):
                    raise psycopg.OperationalError("Simulated DB crash")
                return orig_execute(query, *args, **kwargs)
            conn.execute = intercept_execute
            yield conn

    monkeypatch.setattr(db_mod, "get_conn", failing_conn)
    monkeypatch.setattr(routes_mod, "get_conn", failing_conn)
    res = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("compensate.pdf", io.BytesIO(pdf_path.read_bytes()), "application/pdf")},
    )
    assert res.status_code in {500, 503}

    # Verify no rows in DB and no objects in MinIO
    assert pg_conn.execute("SELECT count(*) FROM papers WHERE owner_id = %s", (owner,)).fetchone()[0] == 0
    minio_client, bucket = private_bucket
    assert len(list(minio_client.list_objects(bucket, recursive=True))) == 0


def test_controlled_upstream_outage_returns_safe_503(client, pg_conn, private_bucket, monkeypatch):
    owner = _insert_user(pg_conn, "outage-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "outage-key"

    import researcy.papers.intake as intake_mod
    def mock_failing_fetch(*args, **kwargs):
        raise ArxivUpstreamError("The upstream service is unavailable.", retry_after=30)
    monkeypatch.setattr(intake_mod, "fetch_official_arxiv", mock_failing_fetch)

    res = client.post(
        "/api/papers/arxiv",
        headers=headers,
        json={"arxiv_id_or_url": "1706.03762"},
    )
    assert res.status_code == 503
    assert res.json()["code"] == "ARXIV_UPSTREAM_ERROR"
    assert res.headers.get("retry-after") == "30"
def test_low_text_pdf_accepted_with_persisted_warning(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "low-text-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "low-text-key"

    pdf_path = _make_pdf(tmp_path / "low.pdf", texts=("One short line",))
    res = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("low.pdf", io.BytesIO(pdf_path.read_bytes()), "application/pdf")},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["screening_warning"] == "LOW_TEXT"

    detail = client.get(f"/api/papers/{data['paper_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["screening_warning"] == "LOW_TEXT"


def test_zero_text_pdf_rejected_before_queuing(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "zero-text-owner")
    headers = _auth_headers(client, pg_conn, owner)
    headers["Idempotency-Key"] = "zero-text-key"

    pdf_path = _make_pdf(tmp_path / "zero.pdf", texts=("",))
    res = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("zero.pdf", io.BytesIO(pdf_path.read_bytes()), "application/pdf")},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "PDF_NO_TEXT"
    assert pg_conn.execute("SELECT count(*) FROM papers WHERE owner_id = %s", (owner,)).fetchone()[0] == 0


def test_missing_or_invalid_idempotency_key_rejected(client, pg_conn, private_bucket, tmp_path):
    owner = _insert_user(pg_conn, "idempotency-key-owner")
    headers = _auth_headers(client, pg_conn, owner)

    pdf_path = _make_pdf(tmp_path / "valid.pdf")

    # Missing
    res1 = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("valid.pdf", io.BytesIO(pdf_path.read_bytes()), "application/pdf")},
    )
    assert res1.status_code == 400
    assert res1.json()["code"] == "INVALID_IDEMPOTENCY_KEY"

    # Whitespace only
    headers["Idempotency-Key"] = "   "
    res2 = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("valid.pdf", io.BytesIO(pdf_path.read_bytes()), "application/pdf")},
    )
    assert res2.status_code == 400
    assert res2.json()["code"] == "INVALID_IDEMPOTENCY_KEY"

    # Exceeding 255 chars
    headers["Idempotency-Key"] = "x" * 256
    res3 = client.post(
        "/api/papers/upload",
        headers=headers,
        files={"file": ("valid.pdf", io.BytesIO(pdf_path.read_bytes()), "application/pdf")},
    )
    assert res3.status_code == 400
    assert res3.json()["code"] == "INVALID_IDEMPOTENCY_KEY"


def test_unauthenticated_request_rejected(client, tmp_path):
    pdf_path = _make_pdf(tmp_path / "unauth.pdf")
    res = client.post(
        "/api/papers/upload",
        headers={"Idempotency-Key": "unauth-key"},
        files={"file": ("unauth.pdf", io.BytesIO(pdf_path.read_bytes()), "application/pdf")},
    )
    assert res.status_code == 401

