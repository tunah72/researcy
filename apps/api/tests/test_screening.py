import hashlib
import importlib
import os
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from minio import Minio

from researcy.errors import APIError


MAX_PDF_BYTES = 25 * 1024 * 1024
MINIO_ENDPOINT = "127.0.0.1:9000"
MINIO_ACCESS_KEY = "researcy-minio"
MINIO_SECRET_KEY = "local-minio-password"


def _module(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name == name:
            pytest.fail(f"expected {name} boundary is not implemented")
        raise


def _pdf(
    path: Path,
    texts=("A born-digital PDF with enough extractable text.\n" * 8,),
    *,
    title="Test PDF",
    encrypted=False,
):
    document = pymupdf.open()
    for text in texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.set_metadata({"title": title})
    options = {}
    if encrypted:
        options = {
            "encryption": pymupdf.PDF_ENCRYPT_AES_256,
            "owner_pw": "screening-test-owner",
            "user_pw": "screening-test-user",
        }
    document.save(path, **options)
    document.close()
    return path


def _assert_api_error(action, *, status, code):
    with pytest.raises(APIError) as raised:
        action()
    assert raised.value.status_code == status
    assert raised.value.code == code


def test_screen_pdf_accepts_born_digital_document_and_hashes_original(tmp_path):
    path = _pdf(tmp_path / "valid.pdf", title="A useful title")

    result = _module("researcy.papers.screening").screen_pdf(path, "application/pdf")

    assert result.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.bytes == path.stat().st_size
    assert result.pages == 1
    assert result.title == "A useful title"
    assert result.warning is None


def test_screen_pdf_rejects_zero_extractable_text(tmp_path):
    path = _pdf(tmp_path / "blank.pdf", texts=("",))

    _assert_api_error(
        lambda: _module("researcy.papers.screening").screen_pdf(path, "application/pdf"),
        status=422,
        code="PDF_NO_TEXT",
    )


def test_screen_pdf_warns_for_nonzero_low_text(tmp_path):
    path = _pdf(tmp_path / "low-text.pdf", texts=("One short line",))

    result = _module("researcy.papers.screening").screen_pdf(path, "application/pdf")

    assert result.warning.code == "LOW_TEXT"
    assert result.warning.message


def test_screen_pdf_warns_when_fewer_than_half_pages_have_enough_text(tmp_path):
    path = _pdf(
        tmp_path / "sparse-pages.pdf",
        texts=(("A" * 40 + "\n") * 8, "", ""),
    )

    result = _module("researcy.papers.screening").screen_pdf(path, "application/pdf")

    assert result.warning.code == "LOW_TEXT"


def test_screen_pdf_rejects_non_pdf_mime(tmp_path):
    path = _pdf(tmp_path / "valid.pdf")

    _assert_api_error(
        lambda: _module("researcy.papers.screening").screen_pdf(path, "text/plain"),
        status=415,
        code="PDF_UNSUPPORTED",
    )


def test_screen_pdf_rejects_wrong_signature(tmp_path):
    path = tmp_path / "not-pdf.pdf"
    path.write_bytes(b"not a PDF")

    _assert_api_error(
        lambda: _module("researcy.papers.screening").screen_pdf(path, "application/pdf"),
        status=415,
        code="PDF_UNSUPPORTED",
    )


@pytest.mark.parametrize(
    ("encrypted", "code"),
    [(False, "PDF_INVALID"), (True, "PDF_ENCRYPTED")],
    ids=["corrupt", "encrypted"],
)
def test_screen_pdf_rejects_corrupt_or_encrypted_document(tmp_path, encrypted, code):
    path = tmp_path / ("encrypted.pdf" if encrypted else "corrupt.pdf")
    if encrypted:
        _pdf(path, encrypted=True)
    else:
        path.write_bytes(b"%PDF-1.7\nthis is not a valid PDF")

    _assert_api_error(
        lambda: _module("researcy.papers.screening").screen_pdf(path, "application/pdf"),
        status=422,
        code=code,
    )


def test_screen_pdf_rejects_more_than_configured_page_limit(tmp_path, monkeypatch):
    path = _pdf(tmp_path / "too-many-pages.pdf", texts=("x",) * 101)
    monkeypatch.setenv("MAX_PDF_PAGES", "100")

    _assert_api_error(
        lambda: _module("researcy.papers.screening").screen_pdf(path, "application/pdf"),
        status=422,
        code="PDF_TOO_MANY_PAGES",
    )


def test_screen_pdf_rejects_more_than_configured_byte_limit(tmp_path):
    path = tmp_path / "too-large.pdf"
    with path.open("wb") as file:
        file.write(b"%PDF-1.7\n")
        file.truncate(MAX_PDF_BYTES + 1)

    _assert_api_error(
        lambda: _module("researcy.papers.screening").screen_pdf(path, "application/pdf"),
        status=413,
        code="PDF_TOO_LARGE",
    )


def test_screen_pdf_worker_does_not_inherit_service_secrets(tmp_path, monkeypatch):
    path = _pdf(tmp_path / "isolated-worker.pdf")
    screening = _module("researcy.papers.screening")
    secret_names = {"GOOGLE_CLIENT_SECRET", "SESSION_LOOKUP_KEY", "MINIO_ROOT_PASSWORD"}
    for name in secret_names:
        monkeypatch.setenv(name, "test-only-secret")

    captured = {}
    real_run = screening.subprocess.run

    def capture_worker_environment(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(screening.subprocess, "run", capture_worker_environment)

    assert screening.screen_pdf(path, "application/pdf").pages == 1
    worker_env = captured["env"]
    assert worker_env is not None
    assert secret_names.isdisjoint(worker_env)

def test_screen_pdf_converts_inspection_timeout_to_safe_rejection(tmp_path, monkeypatch):
    path = _pdf(tmp_path / "timeout.pdf")
    screening = _module("researcy.papers.screening")

    def timeout(*_args, **_kwargs):
        raise screening.subprocess.TimeoutExpired("pdf-worker", 1)

    monkeypatch.setattr(screening.subprocess, "run", timeout)

    _assert_api_error(
        lambda: screening.screen_pdf(path, "application/pdf"),
        status=422,
        code="PDF_SCREEN_TIMEOUT",
    )


def test_screen_pdf_converts_child_resource_exhaustion_to_safe_rejection(tmp_path, monkeypatch):
    path = _pdf(tmp_path / "resource-limit.pdf")
    screening = _module("researcy.papers.screening")

    monkeypatch.setattr(
        screening.subprocess,
        "run",
        lambda *_args, **_kwargs: screening.subprocess.CompletedProcess(
            args="pdf-worker", returncode=-9, stdout=b"", stderr=b"private PDF text"
        ),
    )

    with pytest.raises(APIError) as raised:
        screening.screen_pdf(path, "application/pdf")

    assert raised.value.status_code == 422
    assert raised.value.code == "PDF_SCREEN_RESOURCE_LIMIT"
    assert "private PDF text" not in str(raised.value)


@pytest.fixture
def private_bucket(monkeypatch):
    endpoint = os.environ.get("MINIO_ENDPOINT", MINIO_ENDPOINT)
    access_key = os.environ.get("MINIO_ROOT_USER", MINIO_ACCESS_KEY)
    secret_key = os.environ.get("MINIO_ROOT_PASSWORD", MINIO_SECRET_KEY)
    bucket = f"screening-test-{uuid4().hex}"
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


def _insert_owned_version(conn, owner_id, paper_id, version_id, object_key, digest, size):
    conn.execute(
        "INSERT INTO users (id, issuer, sub) VALUES (%s, %s, %s)",
        (owner_id, "https://accounts.google.com", f"pdf-test-{owner_id}"),
    )
    conn.execute(
        """
        INSERT INTO papers (id, owner_id, source, canonical_arxiv_id, active_version_id)
        VALUES (%s, %s, 'upload', NULL, %s)
        """,
        (paper_id, owner_id, version_id),
    )
    conn.execute(
        """
        INSERT INTO document_versions (
            id, owner_id, paper_id, sha256, byte_count, object_key
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (version_id, owner_id, paper_id, bytes.fromhex(digest), size, object_key),
    )


def test_private_minio_round_trip_and_anonymous_read_denial(
    tmp_path, private_bucket, pg_conn
):
    path = _pdf(tmp_path / "private-original.pdf", title="Private source")
    contents = path.read_bytes()
    digest = hashlib.sha256(contents).hexdigest()
    owner_id, paper_id, version_id = uuid4(), uuid4(), uuid4()
    objects = _module("researcy.papers.objects")

    key = objects.put_original(owner_id, version_id, path, digest)
    _insert_owned_version(pg_conn, owner_id, paper_id, version_id, key, digest, len(contents))
    pg_conn.commit()

    streamed = b"".join(objects.get_owned_original(pg_conn, owner_id, paper_id, version_id))

    assert streamed == contents
    assert hashlib.sha256(streamed).hexdigest() == digest
    assert not key.endswith(".pdf")
    assert str(path.name) not in key
    endpoint = os.environ["MINIO_ENDPOINT"]
    secure = os.environ.get("MINIO_SECURE", "false").strip().lower() == "true"
    scheme = "https" if secure else "http"
    url = f"{scheme}://{endpoint}/{private_bucket[1]}/{key}"
    try:
        response = urllib.request.urlopen(url, timeout=3)
    except urllib.error.HTTPError as error:
        try:
            assert error.code in {401, 403}
        finally:
            error.close()
    else:
        response.close()
        pytest.fail("private original object was readable without credentials")


def test_put_original_never_overwrites_an_existing_version_object(
    tmp_path, private_bucket
):
    first_path = _pdf(tmp_path / "first.pdf", title="First upload")
    second_path = _pdf(tmp_path / "second.pdf", title="Second upload")
    first_bytes = first_path.read_bytes()
    second_bytes = second_path.read_bytes()
    owner_id, version_id = uuid4(), uuid4()
    objects = _module("researcy.papers.objects")
    client, bucket = private_bucket

    first_key = objects.put_original(
        owner_id, version_id, first_path, hashlib.sha256(first_bytes).hexdigest()
    )
    second_key = objects.put_original(
        owner_id, version_id, second_path, hashlib.sha256(second_bytes).hexdigest()
    )

    assert first_key != second_key
    for key, expected in ((first_key, first_bytes), (second_key, second_bytes)):
        response = client.get_object(bucket, key)
        try:
            streamed = response.read()
            assert len(streamed) == len(expected)
            assert hashlib.sha256(streamed).digest() == hashlib.sha256(expected).digest()
        finally:
            response.close()
            response.release_conn()


def test_owner_and_paper_guard_runs_before_any_object_read(pg_conn, monkeypatch):
    owner_id, paper_id, version_id = uuid4(), uuid4(), uuid4()
    _insert_owned_version(
        pg_conn,
        owner_id,
        paper_id,
        version_id,
        "missing-object-is-never-read",
        hashlib.sha256(b"x").hexdigest(),
        1,
    )
    pg_conn.commit()
    objects = _module("researcy.papers.objects")

    def forbidden_object_read():
        pytest.fail("storage must not be accessed before owner, paper, and version match")

    monkeypatch.setattr(objects, "_client", forbidden_object_read)

    with pytest.raises(objects.PrivateResourceNotFound) as foreign_owner:
        objects.get_owned_original(pg_conn, uuid4(), paper_id, version_id)
    with pytest.raises(objects.PrivateResourceNotFound) as wrong_paper:
        objects.get_owned_original(pg_conn, owner_id, uuid4(), version_id)
    assert foreign_owner.value.status_code == wrong_paper.value.status_code == 404
    assert foreign_owner.value.code == wrong_paper.value.code == "RESOURCE_NOT_FOUND"


def test_put_original_removes_object_when_readback_hash_mismatches(tmp_path, private_bucket):
    path = _pdf(tmp_path / "mismatch.pdf")
    client, bucket = private_bucket
    objects = _module("researcy.papers.objects")

    with pytest.raises(objects.OriginalStorageError) as raised:
        objects.put_original(
            uuid4(),
            uuid4(),
            path,
            hashlib.sha256(b"different bytes").hexdigest(),
        )
    assert raised.value.status_code == 503
    assert raised.value.code == "ORIGINAL_STORAGE_UNAVAILABLE"
    assert list(client.list_objects(bucket, recursive=True)) == []


def test_failed_orphan_cleanup_emits_only_safe_marker(
    tmp_path, private_bucket, monkeypatch, caplog
):
    path = _pdf(tmp_path / "orphan.pdf")
    client, bucket = private_bucket
    objects = _module("researcy.papers.objects")

    class CleanupFailureClient:
        def put_object(self, *args, **kwargs):
            return client.put_object(*args, **kwargs)

        def get_object(self, *args, **kwargs):
            return client.get_object(*args, **kwargs)

        def remove_object(self, *_args, **_kwargs):
            raise RuntimeError("sensitive storage detail")

    monkeypatch.setattr(objects, "_client", CleanupFailureClient)

    with pytest.raises(objects.OriginalStorageError) as raised:
        objects.put_original(uuid4(), uuid4(), path, hashlib.sha256(b"wrong").hexdigest())
    assert raised.value.status_code == 503
    assert raised.value.code == "ORIGINAL_STORAGE_UNAVAILABLE"

    assert "private_original_orphan_cleanup_failed" in caplog.text
    assert "sensitive storage detail" not in caplog.text
    assert len(list(client.list_objects(bucket, recursive=True))) == 1
