from array import array
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from uuid import UUID, uuid4
import psycopg
import pytest

from test_schema import insert_user, insert_paper
from test_document_provenance import source_lines

from conftest import _database_url
from researcy.documents.chunking import chunk_section, iter_sections
from researcy.documents.normalize import normalize_records
from researcy.documents.repository import (
    seal_embedding_manifest,
    select_embedding_batch,
    write_canonical_batch,
    write_chunk_batch,
)
from researcy.documents.artifacts import put_artifact
from researcy.errors import APIError
from researcy.ingestion.jobs import claim_due, commit_stage, seal_profile, short_transaction
from researcy.ingestion.models import DocumentScope, IntegrityFailure, ProcessingProfile, StageFailure
from researcy.retrieval import index
from researcy.retrieval import repository
from researcy.retrieval.repository import EvidenceHit, ReadyDocument, load_ready_document, search_dense


def _forbidden(*args, **kwargs):
    pytest.fail("external dependency must not be called when authorization or readiness fails")


class DeterministicEmbeddingClient:
    def __init__(self, profile, **kwargs):
        self.profile = profile

    def preflight(self):
        return {
            "runtime": "ollama",
            "version": "0.18.2",
            "model_tag": self.profile.model_tag,
            "model_digest": self.profile.model_digest,
            "dimension": 1024,
            "quantization": "F16",
        }

    def embed(self, texts):
        return array("f", [1.0] + [0.0] * 1023).tobytes()


@pytest.fixture(autouse=True)
def bind_repository_db(request, monkeypatch):
    """Bind canonical hydration to the disposable database."""
    if "selected_index" in request.fixturenames:
        fixture = request.getfixturevalue("selected_index")
        monkeypatch.setattr(repository, "get_conn", fixture["get_conn"])
    elif "queued_job" in request.fixturenames:
        conn = request.getfixturevalue("pg_conn")

        @contextmanager
        def scoped_connection():
            with psycopg.connect(_database_url(conn.info.dbname)) as connection:
                yield connection

        monkeypatch.setattr(repository, "get_conn", scoped_connection)


def test_parameter_validation_denies_invalid_inputs():
    document = ReadyDocument(DocumentScope(uuid4(),uuid4(),uuid4()),ProcessingProfile(),'test',bytes(32),frozenset())
    for query in ('','a'*2401):
        with pytest.raises(ValueError):
            search_dense(document,query)
    for limit in (True,0,6,'3',2.5):
        with pytest.raises(ValueError):
            search_dense(document,'valid query',limit)
    with pytest.raises(ValueError):
        search_dense(None,'valid query')


def test_foreign_and_nonexistent_paper_share_identical_404_before_dependencies(
    queued_job, monkeypatch
):
    scope, _ = queued_job
    foreign_owner = uuid4()
    nonexistent_paper = uuid4()

    monkeypatch.setattr(repository, "EmbeddingClient", _forbidden)
    monkeypatch.setattr(index, "QdrantClient", _forbidden)

    with pytest.raises(APIError) as nonexistent_err:
        with repository.get_conn() as conn:
            load_ready_document(conn,scope.owner_id,nonexistent_paper,None)

    with pytest.raises(APIError) as foreign_err:
        with repository.get_conn() as conn:
            load_ready_document(conn,foreign_owner,scope.paper_id,None)

    assert nonexistent_err.value.status_code == 404
    assert foreign_err.value.status_code == 404
    assert nonexistent_err.value.code == "RESOURCE_NOT_FOUND"
    assert foreign_err.value.code == "RESOURCE_NOT_FOUND"
    assert nonexistent_err.value.message == foreign_err.value.message


def test_unready_paper_returns_safe_unavailable_before_dependencies(
    queued_job, job_connections, monkeypatch
):
    scope, job = queued_job
    conn, _ = job_connections

    monkeypatch.setattr(repository, "EmbeddingClient", _forbidden)
    monkeypatch.setattr(index, "QdrantClient", _forbidden)

    # 1. Job is queued (pending stage, not ready)
    with pytest.raises(APIError) as unavailable:
        load_ready_document(conn,scope.owner_id,scope.paper_id,None)
    assert unavailable.value.code=='PAPER_NOT_READY'

    # 2. Job in validating/parsing/embedding/indexing stage
    for stage in ("validating", "parsing", "normalizing", "chunking", "embedding", "indexing"):
        with short_transaction(conn):
            conn.execute(
                "UPDATE ingestion_jobs SET stage = %s WHERE id = %s AND owner_id = %s",
                (stage, job, scope.owner_id),
            )
        with pytest.raises(APIError) as unavailable:
            load_ready_document(conn,scope.owner_id,scope.paper_id,None)
        assert unavailable.value.code=='PAPER_NOT_READY'

    # 3. Job in failed status
    with short_transaction(conn):
        conn.execute(
            """UPDATE ingestion_jobs
               SET status = 'failed', stage = 'failed', completed_at = clock_timestamp(),
                   failed_stage = 'embedding', error_code = 'DEPENDENCY_UNAVAILABLE',
                   failure_kind = 'temporary', retryable = true
               WHERE id = %s AND owner_id = %s""",
            (job, scope.owner_id),
        )
    with pytest.raises(APIError) as unavailable:
        load_ready_document(conn,scope.owner_id,scope.paper_id,None)
    assert unavailable.value.code=='PAPER_NOT_READY'


def test_dependency_failure_becomes_safe_unavailable_error(selected_index, monkeypatch):
    fixture = selected_index
    scope = fixture["scope"]
    lease = fixture["lease"]
    conn = fixture["conn"]

    deadline = time.monotonic() + 60
    index.index_selected(lease, deadline)
    receipt = index.verify_index(lease, deadline)
    index.publish_ready(conn, lease, receipt)

    # 1. EmbeddingClient preflight failure
    class FailingEmbeddingClient:
        def __init__(self, profile, **kwargs):
            self.profile = profile

        def preflight(self):
            raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True)

        def embed(self, texts):
            raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True)

    monkeypatch.setattr(repository, "EmbeddingClient", FailingEmbeddingClient)
    with pytest.raises(APIError) as embed_err:
        search_dense(load_ready_document(conn,scope.owner_id,scope.paper_id,None),"query text")
    assert embed_err.value.status_code == 503
    assert embed_err.value.code == "DEPENDENCY_UNAVAILABLE"
    assert "http" not in embed_err.value.message.lower()

    # 2. Qdrant failure via real HTTP timeout
    monkeypatch.setattr(repository, "EmbeddingClient", DeterministicEmbeddingClient)

    class HangingHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            time.sleep(2.0)

    server = ThreadingHTTPServer(("127.0.0.1", 0), HangingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        class FastTimeoutQdrantClient(index.QdrantClient):
            def __init__(self, **kwargs):
                super().__init__(
                    endpoint=f"http://127.0.0.1:{server.server_port}",
                    deadline=time.monotonic() + 0.1,
                )

        monkeypatch.setattr(index, "QdrantClient", FastTimeoutQdrantClient)

        with pytest.raises(APIError) as qdrant_err:
            search_dense(load_ready_document(conn,scope.owner_id,scope.paper_id,None),"query text")
        assert qdrant_err.value.status_code == 503
        assert qdrant_err.value.code == "DEPENDENCY_UNAVAILABLE"
        assert "127.0.0.1" not in qdrant_err.value.message
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    "corruption",
    [
        "foreign-chunk-id",
        "wrong-point-id",
        "foreign-owner",
        "wrong-section-type",
        "extra-payload-key",
        "duplicate-point",
        "noncanonical-chunk-id",
    ],
)
def test_poisoned_foreign_chunk_payload_returns_safe_unavailable(
    selected_index, corruption, monkeypatch
):
    fixture = selected_index
    scope = fixture["scope"]
    lease = fixture["lease"]
    conn = fixture["conn"]
    profile = fixture["profile"]
    client = fixture["client"]
    collection = fixture["collection"]

    deadline = time.monotonic() + 60
    index.index_selected(lease, deadline)
    receipt = index.verify_index(lease, deadline)
    index.publish_ready(conn, lease, receipt)

    monkeypatch.setattr(repository, "EmbeddingClient", DeterministicEmbeddingClient)

    valid_chunk_id = fixture["chunks"][0].id
    valid_point_id = index.point_id(profile.index_version, valid_chunk_id)

    # Read back the actual indexed point from Qdrant
    pts_res = client.request(
        "POST",
        f"/collections/{collection}/points/scroll",
        {"limit": 10, "with_payload": True, "with_vector": True},
    )
    original_point = pts_res["result"]["points"][0]

    if corruption == "foreign-chunk-id":
        foreign_chunk_id = uuid4()
        corrupt_pt = {
            "id": str(index.point_id(profile.index_version, foreign_chunk_id)),
            "payload": {
                "chunk_id": str(foreign_chunk_id),
                "owner_id": str(scope.owner_id),
                "paper_id": str(scope.paper_id),
                "document_version_id": str(scope.document_version_id),
                "section_type": "body",
            },
            "vector": original_point["vector"],
        }
        client.request("POST", f"/collections/{collection}/points/delete?wait=true", {"points": [original_point["id"]]})
        client.request("PUT", f"/collections/{collection}/points?wait=true", {"points": [corrupt_pt]})

    elif corruption == "wrong-point-id":
        wrong_pt_id = uuid4()
        corrupt_pt = {
            "id": str(wrong_pt_id),
            "payload": dict(original_point["payload"]),
            "vector": original_point["vector"],
        }
        client.request("POST", f"/collections/{collection}/points/delete?wait=true", {"points": [original_point["id"]]})
        client.request("PUT", f"/collections/{collection}/points?wait=true", {"points": [corrupt_pt]})

    elif corruption == "foreign-owner":
        corrupt_payload = dict(original_point["payload"])
        corrupt_payload["owner_id"] = str(uuid4())
        corrupt_pt = {
            "id": original_point["id"],
            "payload": corrupt_payload,
            "vector": original_point["vector"],
        }
        client.request("PUT", f"/collections/{collection}/points?wait=true", {"points": [corrupt_pt]})

    elif corruption == "wrong-section-type":
        corrupt_payload = dict(original_point["payload"])
        corrupt_payload["section_type"] = "header"
        corrupt_pt = {
            "id": original_point["id"],
            "payload": corrupt_payload,
            "vector": original_point["vector"],
        }
        client.request("PUT", f"/collections/{collection}/points?wait=true", {"points": [corrupt_pt]})

    elif corruption == "extra-payload-key":
        corrupt_payload = dict(original_point["payload"])
        corrupt_payload["malicious_extra"] = "payload_injection"
        corrupt_pt = {
            "id": original_point["id"],
            "payload": corrupt_payload,
            "vector": original_point["vector"],
        }
        client.request("PUT", f"/collections/{collection}/points?wait=true", {"points": [corrupt_pt]})

    elif corruption == "duplicate-point":
        # Add a duplicate point with same chunk_id under a different point_id in Qdrant
        extra_pid = uuid4()
        corrupt_pt = {
            "id": str(extra_pid),
            "payload": dict(original_point["payload"]),
            "vector": original_point["vector"],
        }
        client.request("PUT", f"/collections/{collection}/points?wait=true", {"points": [corrupt_pt]})

    elif corruption == "noncanonical-chunk-id":
        corrupt_payload = dict(original_point["payload"])
        corrupt_payload["chunk_id"] = valid_chunk_id.hex
        corrupt_pt = {
            "id": original_point["id"],
            "payload": corrupt_payload,
            "vector": original_point["vector"],
        }
        client.request("PUT", f"/collections/{collection}/points?wait=true", {"points": [corrupt_pt]})

    document = load_ready_document(conn,scope.owner_id,scope.paper_id,None)
    # A verified nonempty publication cannot legitimately return no dense points.
    with pytest.raises(APIError) as unavailable:
        search_dense(document,"Owned exact source")
    assert unavailable.value.code=='EVIDENCE_UNAVAILABLE'


@pytest.mark.parametrize("mismatch", ["collection", "chunk_set_hash", "point_set_hash"])
def test_publication_mismatch_returns_safe_unavailable_before_dependencies(
    selected_index, mismatch, monkeypatch
):
    fixture = selected_index
    scope = fixture["scope"]
    lease = fixture["lease"]
    conn = fixture["conn"]

    deadline = time.monotonic() + 60
    index.index_selected(lease, deadline)
    receipt = index.verify_index(lease, deadline)
    index.publish_ready(conn, lease, receipt)

    monkeypatch.setattr(repository, "EmbeddingClient", _forbidden)
    monkeypatch.setattr(index, "QdrantClient", _forbidden)

    if mismatch == "collection":
        monkeypatch.setattr(index, "collection_name", lambda profile: "foreign_collection_name")
    elif mismatch == "chunk_set_hash":
        monkeypatch.setattr(index, "chunk_set_hash", lambda chunk_ids: b"\x00" * 32)
    elif mismatch == "point_set_hash":
        monkeypatch.setattr(index, "point_set_hash", lambda point_ids: b"\x00" * 32)

    with pytest.raises(APIError) as unavailable:
        load_ready_document(conn,scope.owner_id,scope.paper_id,None)
    assert unavailable.value.code=='EVIDENCE_UNAVAILABLE'


def test_qdrant_non_ok_status_raises_dependency_unavailable(selected_index, monkeypatch):
    fixture = selected_index
    scope = fixture["scope"]
    lease = fixture["lease"]
    conn = fixture["conn"]

    deadline = time.monotonic() + 60
    index.index_selected(lease, deadline)
    receipt = index.verify_index(lease, deadline)
    index.publish_ready(conn, lease, receipt)

    monkeypatch.setattr(repository, "EmbeddingClient", DeterministicEmbeddingClient)

    class NotOkStatusQdrantClient:
        def __init__(self, **kwargs):
            pass

        def request(self, method, path, payload=None):
            return {"status": "not_found", "result": []}

    monkeypatch.setattr(index, "QdrantClient", NotOkStatusQdrantClient)

    with pytest.raises(APIError) as err:
        search_dense(load_ready_document(conn,scope.owner_id,scope.paper_id,None),"test query")
    assert err.value.status_code == 503
    assert err.value.code == "DEPENDENCY_UNAVAILABLE"


@pytest.mark.parametrize("bad_score", [2.0, -10.0, 10**400])
def test_qdrant_out_of_range_score_returns_safe_unavailable(selected_index, bad_score, monkeypatch):
    fixture = selected_index
    scope = fixture["scope"]
    lease = fixture["lease"]
    conn = fixture["conn"]

    deadline = time.monotonic() + 60
    index.index_selected(lease, deadline)
    receipt = index.verify_index(lease, deadline)
    index.publish_ready(conn, lease, receipt)

    monkeypatch.setattr(repository, "EmbeddingClient", DeterministicEmbeddingClient)

    valid_chunk_id = fixture["chunks"][0].id
    profile = fixture["profile"]
    valid_point_id = index.point_id(profile.index_version, valid_chunk_id)

    class BadScoreQdrantClient:
        def __init__(self, **kwargs):
            pass

        def request(self, method, path, payload=None):
            return {
                "status": "ok",
                "result": [
                    {
                        "id": str(valid_point_id),
                        "score": bad_score,
                        "payload": {
                            "chunk_id": str(valid_chunk_id),
                            "owner_id": str(scope.owner_id),
                            "paper_id": str(scope.paper_id),
                            "document_version_id": str(scope.document_version_id),
                            "section_type": "body",
                        },
                    }
                ],
            }

    monkeypatch.setattr(index, "QdrantClient", BadScoreQdrantClient)

    with pytest.raises(APIError) as unavailable:
        search_dense(load_ready_document(conn,scope.owner_id,scope.paper_id,None),"test query")
    assert unavailable.value.code=='EVIDENCE_UNAVAILABLE'


def test_tampered_canonical_provenance_returns_safe_unavailable(selected_index, monkeypatch):
    fixture = selected_index
    scope = fixture["scope"]
    lease = fixture["lease"]
    conn = fixture["conn"]

    deadline = time.monotonic() + 60
    index.index_selected(lease, deadline)
    receipt = index.verify_index(lease, deadline)
    index.publish_ready(conn, lease, receipt)

    monkeypatch.setattr(repository, "EmbeddingClient", DeterministicEmbeddingClient)

    def failing_resolve_range(*args, **kwargs):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    monkeypatch.setattr(repository, "resolve_range", failing_resolve_range)
    with pytest.raises(APIError) as unavailable:
        search_dense(load_ready_document(conn,scope.owner_id,scope.paper_id,None),"probe query")
    assert unavailable.value.code=='EVIDENCE_UNAVAILABLE'


def test_ready_owned_lookup_rehydrates_canonical_provenance(selected_index, monkeypatch):
    fixture = selected_index
    scope = fixture["scope"]
    lease = fixture["lease"]
    conn = fixture["conn"]
    profile = fixture["profile"]
    chunk = fixture["chunks"][0]

    deadline = time.monotonic() + 60
    index.index_selected(lease, deadline)
    receipt = index.verify_index(lease, deadline)
    index.publish_ready(conn, lease, receipt)

    monkeypatch.setattr(repository, "EmbeddingClient", DeterministicEmbeddingClient)

    hits = search_dense(load_ready_document(conn,scope.owner_id,scope.paper_id,None),"Owned exact source",limit=5)
    assert len(hits) == 1

    hit = hits[0]
    assert isinstance(hit, EvidenceHit)
    assert hit.scope == scope
    assert hit.chunk_id == chunk.id
    assert hit.section_id == chunk.section_id
    assert hit.text == chunk.text
    assert hit.score > 0.0

    # Provenance locations verified: page, quote, boxes
    assert len(hit.locations) >= 1
    loc = hit.locations[0]
    assert loc.page_index == 0
    assert loc.quote == chunk.text
    assert len(loc.boxes) == len(chunk.text)
    for box in loc.boxes:
        assert isinstance(box, tuple) and len(box) == 4
        assert box[0] <= box[2] and box[1] <= box[3]
