import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx2
import pytest

from researcy.documents.artifacts import verify_artifact
from researcy.ingestion.models import (
    ArtifactRef,
    DocumentScope,
    IntegrityFailure,
    ProcessingProfile,
    StageFailure,
)
from researcy.retrieval.index import (
    QdrantClient,
    ensure_collection,
    point_id,
    validate_point_set,
    validate_search_hits,
)


def test_point_id_tail_difference_avoids_membership_poison():
    chunk_id = uuid4()
    v1 = b"\x00" * 31 + b"\x01"
    v2 = b"\x00" * 31 + b"\x02"
    p1 = point_id(v1, chunk_id)
    p2 = point_id(v2, chunk_id)
    assert p1 != p2
    assert isinstance(p1, UUID)
    assert isinstance(p2, UUID)


def test_qdrant_client_oversize_response_raises_integrity_failure():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"x" * (13 * 1024 * 1024))

    client = QdrantClient("http://qdrant:6333")
    async def mock_request(method, path, payload=None):
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as cl:
            return await client._request(cl, method, path, payload)
    client._async_request = mock_request

    with pytest.raises(IntegrityFailure):
        client.request("GET", "/collections/test")


def test_qdrant_client_malformed_json_raises_integrity_failure():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b'{"result": {"status": "ok", truncated')

    client = QdrantClient("http://qdrant:6333")
    async def mock_request(method, path, payload=None):
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as cl:
            return await client._request(cl, method, path, payload)
    client._async_request = mock_request

    with pytest.raises(IntegrityFailure):
        client.request("GET", "/collections/test")


def test_qdrant_client_timeout_and_deadline_exceeded():
    client = QdrantClient("http://qdrant:6333", deadline=time.monotonic() - 1.0)
    with pytest.raises(StageFailure) as sf:
        client.request("GET", "/test")
    assert sf.value.code == "DEPENDENCY_UNAVAILABLE"
    assert sf.value.retryable is True


def test_qdrant_client_status_code_mappings():
    def handler(request: httpx2.Request) -> httpx2.Response:
        url_str = str(request.url)
        if "404" in url_str:
            return httpx2.Response(404, json={"status": {"error": "not found"}})
        if "429" in url_str:
            return httpx2.Response(429, json={"status": "rate limited"})
        if "500" in url_str:
            return httpx2.Response(500, json={"status": "server error"})
        if "400" in url_str:
            return httpx2.Response(400, json={"status": "bad request"})
        return httpx2.Response(200, json={"result": {"status": "ok"}, "status": "ok"})

    client = QdrantClient("http://qdrant:6333")
    async def mock_request(method, path, payload=None):
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as cl:
            return await client._request(cl, method, path, payload)
    client._async_request = mock_request

    not_found = client.request("GET", "/404")
    assert "error" in not_found.get("status", {})

    with pytest.raises(StageFailure) as sf_rate:
        client.request("GET", "/429")
    assert sf_rate.value.code == "DEPENDENCY_RATE_LIMITED"
    assert sf_rate.value.retryable is True

    with pytest.raises(StageFailure) as sf_srv:
        client.request("GET", "/500")
    assert sf_srv.value.code == "DEPENDENCY_UNAVAILABLE"
    assert sf_srv.value.retryable is True

    with pytest.raises(IntegrityFailure):
        client.request("GET", "/400")

    ok_res = client.request("GET", "/200")
    assert ok_res["status"] == "ok"


@pytest.mark.parametrize(
    "corrupt_element",
    [
        True,
        False,
        "scalar_str",
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_validate_point_set_malformed_vector_elements(corrupt_element):
    u = str(uuid4())
    expected = [{"id": u, "payload": {"k": "v"}, "vector": [1.0] + [0.0] * 1023}]
    observed = [{"id": u, "payload": {"k": "v"}, "vector": [corrupt_element] + [0.0] * 1023}]
    with pytest.raises(IntegrityFailure):
        validate_point_set(expected, observed)


def test_validate_point_set_non_unit_norm_vector():
    u = str(uuid4())
    expected = [{"id": u, "payload": {"k": "v"}, "vector": [1.0] + [0.0] * 1023}]
    observed = [{"id": u, "payload": {"k": "v"}, "vector": [0.5] + [0.0] * 1023}]
    with pytest.raises(IntegrityFailure):
        validate_point_set(expected, observed)


@pytest.mark.parametrize(
    "bad_input",
    [
        "not_a_list",
        [{"id": "not_a_uuid", "payload": {}, "vector": [1.0] + [0.0] * 1023}],
        [{"id": str(uuid4()), "payload": "not_a_dict", "vector": [1.0] + [0.0] * 1023}],
        [{"id": str(uuid4()), "payload": {}, "vector": "not_a_list"}],
        [{"id": str(uuid4()), "payload": {}, "vector": [1.0] * 10}],
    ],
)
def test_validate_point_set_bad_input_structures(bad_input):
    u = str(uuid4())
    expected = [{"id": u, "payload": {}, "vector": [1.0] + [0.0] * 1023}]
    with pytest.raises(IntegrityFailure):
        validate_point_set(expected, bad_input if isinstance(bad_input, list) else [bad_input])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "malformed_get_result",
    [
        [],  # result is a list instead of a dict
        "not_a_dict",
        {"config": "not_a_dict"},
        {"config": {"params": {"vectors": "not_a_dict"}}},
        {"config": {"params": {"vectors": {"size": "not_an_int", "distance": "Cosine"}}}},
        {"config": {"params": {"vectors": {"size": 1024, "distance": "Cosine"}}}, "payload_schema": "not_a_dict"},
        {"config": {"params": {"vectors": {"size": 1024, "distance": "Cosine"}}}, "payload_schema": {"owner_id": "not_a_dict"}},
    ],
)
def test_ensure_collection_malformed_nested_result_raises_integrity_failure(malformed_get_result):
    profile = ProcessingProfile()
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"status": "ok", "result": malformed_get_result})

    client = QdrantClient("http://qdrant:6333")
    async def mock_request(method, path, payload=None):
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as cl:
            return await client._request(cl, method, path, payload)
    client._async_request = mock_request

    with pytest.raises(IntegrityFailure):
        ensure_collection(profile, client=client)


def test_ensure_collection_replay_safe_under_concurrent_create():
    profile = ProcessingProfile()
    created = False

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal created
        method = request.method
        path = request.url.path
        if method == "GET" and not created:
            return httpx2.Response(404, json={"status": {"error": "Not found"}})
        if method == "PUT" and not created:
            # Simulate concurrent worker winning creation with conflict
            created = True
            return httpx2.Response(409, json={"status": {"error": "Collection already exists"}})
        if method == "GET" and created:
            return httpx2.Response(
                200,
                json={
                    "status": "ok",
                    "result": {
                        "config": {"params": {"vectors": {"size": 1024, "distance": "Cosine"}}},
                        "payload_schema": {
                            "owner_id": {"data_type": "keyword"},
                            "paper_id": {"data_type": "keyword"},
                            "document_version_id": {"data_type": "keyword"},
                            "section_type": {"data_type": "keyword"},
                        },
                    },
                },
            )
        if method == "PUT" and "/index" in path:
            return httpx2.Response(200, json={"status": "ok", "result": {"status": "completed"}})
        return httpx2.Response(200, json={"status": "ok"})

    client = QdrantClient("http://qdrant:6333")
    async def mock_request(method, path, payload=None):
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as cl:
            return await client._request(cl, method, path, payload)
    client._async_request = mock_request

    ensure_collection(profile, client=client)


def test_ensure_collection_payload_index_requires_completed_status():
    profile = ProcessingProfile()

    def handler(request: httpx2.Request) -> httpx2.Response:
        method = request.method
        path = request.url.path
        if method == "GET":
            return httpx2.Response(404, json={"status": {"error": "Not found"}})
        if method == "PUT" and "/index" in path:
            # Return acknowledged instead of completed
            return httpx2.Response(200, json={"status": "ok", "result": {"status": "acknowledged"}})
        return httpx2.Response(200, json={"status": "ok", "result": {"status": "completed"}})

    client = QdrantClient("http://qdrant:6333")
    async def mock_request(method, path, payload=None):
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as cl:
            return await client._request(cl, method, path, payload)
    client._async_request = mock_request

    with pytest.raises(IntegrityFailure):
        ensure_collection(profile, client=client)


def test_verify_artifact_honors_deadline_parameter(tmp_path):
    ref = ArtifactRef("test-key", b"x" * 32, 100)
    dest = tmp_path / "dest.bin"
    with pytest.raises(StageFailure) as sf:
        verify_artifact(ref, dest, deadline=time.monotonic() - 1.0)
    assert sf.value.code == "DEPENDENCY_UNAVAILABLE"
    assert sf.value.retryable is True


def test_verify_artifact_aborts_slow_storage_stream_on_deadline(tmp_path):
    import hashlib
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    from dataclasses import replace
    from researcy.config import get_settings

    class SlowHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "1024")
            self.end_headers()
            self.wfile.write(b"a" * 100)
            self.wfile.flush()
            time.sleep(0.5)
            try:
                self.wfile.write(b"b" * 924)
                self.wfile.flush()
            except Exception:
                pass

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"127.0.0.1:{server.server_port}"

    try:
        settings = replace(
            get_settings(),
            storage_minio_endpoint=endpoint,
            storage_secure=False,
            storage_access_key="local-minio-key",
            storage_secret_key="local-minio-secret",
            storage_bucket="test-bucket",
            worker_io_deadline_seconds=30,
        )
        data = b"a" * 100 + b"b" * 924
        ref = ArtifactRef(
            key="processing/00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000002/0000000000000000000000000000000000000000000000000000000000000000/embedding/test",
            sha256=hashlib.sha256(data).digest(),
            byte_count=1024,
        )
        dest = tmp_path / "dest.bin"
        t0 = time.monotonic()
        deadline = t0 + 0.1
        with pytest.raises(StageFailure) as sf:
            verify_artifact(ref, dest, settings=settings, deadline=deadline)
        elapsed = time.monotonic() - t0
        assert sf.value.code == "DEPENDENCY_UNAVAILABLE"
        assert sf.value.retryable is True
        assert not dest.exists()
        assert elapsed < 0.9
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "corrupt_hit_maker",
    [
        lambda scope, iv, chunk, pid: [],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": True, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": "high", "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": float("nan"), "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": 1.5, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": 10**400, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"score": 0.9, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": "not-a-uuid", "score": 0.9, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": pid.hex, "score": 0.9, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": 0.9, "payload": {"chunk_id": "not-a-uuid", "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": 0.9, "payload": {"chunk_id": chunk.hex, "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": 0.9, "payload": {"chunk_id": str(uuid4()), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": 0.9, "payload": {"chunk_id": str(chunk), "owner_id": str(uuid4()), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": 0.9, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id)}}],
        lambda scope, iv, chunk, pid: [{"id": str(pid), "score": 0.9, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body", "extra": 1}}],
        lambda scope, iv, chunk, pid: [
            {"id": str(pid), "score": 0.9, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}},
            {"id": str(pid), "score": 0.8, "payload": {"chunk_id": str(chunk), "owner_id": str(scope.owner_id), "paper_id": str(scope.paper_id), "document_version_id": str(scope.document_version_id), "section_type": "body"}},
        ],
    ],
)
def test_validate_search_hits_malformed_rejection(corrupt_hit_maker):
    owner = uuid4()
    paper = uuid4()
    doc_v = uuid4()
    scope = DocumentScope(owner, paper, doc_v)
    profile = ProcessingProfile()
    chunk = uuid4()
    pid = point_id(profile.index_version, chunk)

    hits = corrupt_hit_maker(scope, profile.index_version, chunk, pid)
    with pytest.raises(IntegrityFailure):
        validate_search_hits(hits, scope, profile.index_version, {chunk}, 5)
