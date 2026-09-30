from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import threading
from uuid import uuid4

import pytest

from test_screening import private_bucket
from researcy.config import get_settings
from researcy.documents.artifacts import put_artifact, verify_artifact
from researcy.ingestion.models import (
    ArtifactRef,
    DocumentScope,
    IntegrityFailure,
    StageFailure,
)


class _TransientHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if "/429" in self.path:
            self.send_response(429)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif "/501" in self.path:
            self.send_response(501)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif "/truncated" in self.path:
            self.send_response(200)
            self.send_header("Content-Length", "10000")
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(b"partial-bytes-12345")
            self.wfile.flush()
            self.connection.close()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def transient_http_server():
    server = HTTPServer(("127.0.0.1", 0), _TransientHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"127.0.0.1:{server.server_port}"
    try:
        yield endpoint
    finally:
        server.shutdown()
        server.server_close()


def test_same_content_has_one_verified_scoped_artifact(tmp_path, private_bucket):
    client, bucket = private_bucket
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "records.jsonl"
    source.write_bytes(b'{"schema_version":1}\n')
    first = put_artifact(scope, b"p" * 32, "parsing", source)
    second = put_artifact(scope, b"p" * 32, "parsing", source)
    assert first == second
    assert first.sha256 == hashlib.sha256(source.read_bytes()).digest()
    restored = tmp_path / "restored"
    verify_artifact(first, restored)
    assert restored.read_bytes() == source.read_bytes()
    objects = list(client.list_objects(bucket, recursive=True))
    assert [obj.object_name for obj in objects] == [first.key]


def test_existing_content_address_is_verified_never_overwritten(tmp_path, private_bucket):
    client, bucket = private_bucket
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "records"
    source.write_bytes(b"expected immutable bytes")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    key = f'processing/{scope.owner_id}/{scope.document_version_id}/{(b"p"*32).hex()}/parsing/{digest}'
    conflicting = b"conflicting object"
    client.put_object(bucket, key, io.BytesIO(conflicting), len(conflicting))
    with pytest.raises(IntegrityFailure):
        put_artifact(scope, b"p" * 32, "parsing", source)
    response = client.get_object(bucket, key)
    try:
        assert response.read() == conflicting
    finally:
        response.close()
        response.release_conn()


def test_readback_corruption_cannot_publish_a_partial_artifact(tmp_path, private_bucket):
    client, bucket = private_bucket
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "records"
    source.write_bytes(b"expected bytes")
    ref = put_artifact(scope, b"p" * 32, "parsing", source)
    client.put_object(bucket, ref.key, io.BytesIO(b"tampered"), 8)
    destination = tmp_path / "downloaded"
    with pytest.raises(IntegrityFailure):
        verify_artifact(ref, destination)
    assert not destination.exists()


def test_large_artifact_replay_regression(tmp_path, private_bucket):
    client, bucket = private_bucket
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "large_payload.bin"
    payload = b"M2-DURABLE-PROCESSING-PAYLOAD-CHUNK\n" * 90000  # ~3.2 MiB
    source.write_bytes(payload)

    first = put_artifact(scope, b"p" * 32, "parsing", source)
    second = put_artifact(scope, b"p" * 32, "parsing", source)
    assert first == second

    restored = tmp_path / "large_restored.bin"
    verify_artifact(second, restored)
    assert restored.stat().st_size == len(payload)
    assert restored.read_bytes() == payload

    objects = list(client.list_objects(bucket, recursive=True))
    assert [obj.object_name for obj in objects] == [first.key]


def test_large_artifact_concurrent_puts(tmp_path, private_bucket):
    client, bucket = private_bucket
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "concurrent_large.bin"
    payload = b"CONCURRENT-PAYLOAD-STREAM-TEST\n" * 90000  # ~2.8 MiB
    source.write_bytes(payload)

    def _worker():
        return put_artifact(scope, b"p" * 32, "parsing", source)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_worker) for _ in range(4)]
        results = [f.result() for f in futures]

    first = results[0]
    for r in results[1:]:
        assert r == first

    objects = list(client.list_objects(bucket, recursive=True))
    assert [obj.object_name for obj in objects] == [first.key]


def test_put_artifact_storage_unavailable_raises_temporary_failure(tmp_path, private_bucket):
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "unavailable_source"
    source.write_bytes(b"test storage unavailable")
    offline_settings = replace(
        get_settings(),
        storage_minio_endpoint="127.0.0.1:59999",
        worker_io_deadline_seconds=1,
    )

    with pytest.raises(StageFailure) as exc_info:
        put_artifact(scope, b"p" * 32, "parsing", source, settings=offline_settings)

    failure = exc_info.value
    assert failure.code == "DEPENDENCY_UNAVAILABLE"
    assert failure.failure_kind == "temporary"
    assert failure.retryable is True


def test_put_artifact_rejects_oversized_content(tmp_path, private_bucket):
    client, bucket = private_bucket
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "oversize"
    source.write_bytes(b"x" * 1024)

    tiny_settings = replace(get_settings(), parser_output_bytes=512)
    with pytest.raises(IntegrityFailure):
        put_artifact(scope, b"p" * 32, "parsing", source, settings=tiny_settings)

    objects = list(client.list_objects(bucket, recursive=True))
    assert objects == []


def test_put_artifact_rejects_empty_file(tmp_path, private_bucket):
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "empty_file"
    source.write_bytes(b"")

    with pytest.raises(IntegrityFailure):
        put_artifact(scope, b"p" * 32, "parsing", source)


def test_verify_artifact_missing_key_raises_integrity_failure(tmp_path, private_bucket):
    fake_ref = ArtifactRef(
        key="processing/nonexistent/missing_key",
        sha256=b"m" * 32,
        byte_count=50,
    )
    destination = tmp_path / "downloaded_missing"
    with pytest.raises(IntegrityFailure):
        verify_artifact(fake_ref, destination)
    assert not destination.exists()


def test_verify_artifact_rejects_preexisting_destination(tmp_path, private_bucket):
    scope = DocumentScope(uuid4(), uuid4(), uuid4())
    source = tmp_path / "records_preexist"
    source.write_bytes(b"content to verify")
    ref = put_artifact(scope, b"p" * 32, "parsing", source)

    destination = tmp_path / "destination_preexist"
    destination.write_bytes(b"caller existing data")

    with pytest.raises(IntegrityFailure):
        verify_artifact(ref, destination)

    assert destination.read_bytes() == b"caller existing data"


def test_verify_artifact_transient_429_raises_temporary_failure(tmp_path, transient_http_server):
    ref = ArtifactRef(key="processing/test/429", sha256=b"h" * 32, byte_count=100)
    destination = tmp_path / "dest_429"
    test_settings = replace(
        get_settings(),
        storage_minio_endpoint=transient_http_server,
        worker_io_deadline_seconds=2,
    )

    with pytest.raises(StageFailure) as exc_info:
        verify_artifact(ref, destination, settings=test_settings)

    failure = exc_info.value
    assert failure.code == "DEPENDENCY_UNAVAILABLE"
    assert failure.failure_kind == "temporary"
    assert failure.retryable is True
    assert not destination.exists()


def test_verify_artifact_unlisted_5xx_raises_temporary_failure(tmp_path, transient_http_server):
    ref = ArtifactRef(key="processing/test/501", sha256=b"h" * 32, byte_count=100)
    destination = tmp_path / "dest_501"
    test_settings = replace(
        get_settings(),
        storage_minio_endpoint=transient_http_server,
        worker_io_deadline_seconds=2,
    )

    with pytest.raises(StageFailure) as exc_info:
        verify_artifact(ref, destination, settings=test_settings)

    failure = exc_info.value
    assert failure.code == "DEPENDENCY_UNAVAILABLE"
    assert failure.failure_kind == "temporary"
    assert failure.retryable is True
    assert not destination.exists()


def test_verify_artifact_truncated_response_raises_temporary_failure(tmp_path, transient_http_server):
    ref = ArtifactRef(key="processing/test/truncated", sha256=b"h" * 32, byte_count=10000)
    destination = tmp_path / "dest_truncated"
    test_settings = replace(
        get_settings(),
        storage_minio_endpoint=transient_http_server,
        worker_io_deadline_seconds=2,
    )

    with pytest.raises(StageFailure) as exc_info:
        verify_artifact(ref, destination, settings=test_settings)

    failure = exc_info.value
    assert failure.code == "DEPENDENCY_UNAVAILABLE"
    assert failure.failure_kind == "temporary"
    assert failure.retryable is True
    assert not destination.exists()
