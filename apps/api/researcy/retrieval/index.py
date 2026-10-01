from array import array
import asyncio
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Sequence
from threading import Event
import sys
import tempfile
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid5

import httpx2
import psycopg
from psycopg.rows import dict_row

from researcy.config import get_settings
from researcy.db import get_conn
from researcy.documents.artifacts import verify_artifact
from researcy.documents.provenance import resolve_range
from researcy.ingestion.io import cancellable
from researcy.ingestion.jobs import (
    fenced_transaction,
    record_transition,
    require_owned,
    short_transaction,
)
from researcy.ingestion.models import (
    ArtifactRef,
    DocumentScope,
    ID_NAMESPACE,
    IntegrityFailure,
    Lease,
    LostLease,
    ProcessingProfile,
    StageFailure,
)
from researcy.retrieval.embedding import validate_vectors

PRIOR_STAGES: tuple[str, ...] = ("validating", "parsing", "normalizing", "chunking", "embedding")
_MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024  # 10 MiB stream cap


def point_id(index_version: bytes, chunk_id: UUID | str) -> UUID:
    if isinstance(chunk_id, str):
        chunk_uuid = UUID(chunk_id)
    else:
        chunk_uuid = chunk_id
    return uuid5(ID_NAMESPACE, f"point/{index_version.hex()}/{chunk_uuid}")


def collection_name(profile: ProcessingProfile) -> str:
    return f"researcy_m2_{profile.index_version.hex()}"


def chunk_set_hash(chunk_ids: Sequence[UUID]) -> bytes:
    return hashlib.sha256(b"".join(cid.bytes for cid in chunk_ids)).digest()


def point_set_hash(point_ids: Sequence[UUID]) -> bytes:
    return hashlib.sha256(b"".join(pid.bytes for pid in point_ids)).digest()


def validate_point_set(expected: list[dict], observed: list[dict]) -> None:
    if type(expected) is not list or type(observed) is not list:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    if len(expected) != len(observed):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    expected_by_id: dict[str, dict] = {}
    for pt in expected:
        if type(pt) is not dict or "id" not in pt or "payload" not in pt or "vector" not in pt:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        raw_id = pt["id"]
        if type(raw_id) is bool or not isinstance(raw_id, (str, UUID)):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        try:
            pid = str(UUID(str(raw_id)))
        except (ValueError, TypeError):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE") from None
        if pid in expected_by_id:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        expected_by_id[pid] = pt

    observed_by_id: dict[str, dict] = {}
    for pt in observed:
        if type(pt) is not dict or "id" not in pt or "payload" not in pt or "vector" not in pt:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        raw_id = pt["id"]
        if type(raw_id) is bool or not isinstance(raw_id, (str, UUID)):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        try:
            pid = str(UUID(str(raw_id)))
        except (ValueError, TypeError):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE") from None
        if pid in observed_by_id:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        observed_by_id[pid] = pt

    if set(expected_by_id.keys()) != set(observed_by_id.keys()):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    for pid, exp in expected_by_id.items():
        obs = observed_by_id[pid]

        exp_pl = exp.get("payload")
        obs_pl = obs.get("payload")
        if type(exp_pl) is not dict or type(obs_pl) is not dict:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        exp_payload = {k: str(v) if isinstance(v, UUID) else v for k, v in exp_pl.items()}
        obs_payload = {k: str(v) if isinstance(v, UUID) else v for k, v in obs_pl.items()}
        if exp_payload != obs_payload:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        exp_vec = exp.get("vector")
        obs_vec = obs.get("vector")
        if not isinstance(exp_vec, (list, tuple)) or not isinstance(obs_vec, (list, tuple)):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if len(exp_vec) != len(obs_vec) or len(exp_vec) != 1024:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        norm_sq = 0.0
        for ev, ov in zip(exp_vec, obs_vec):
            if type(ev) is bool or type(ov) is bool:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if not isinstance(ev, (int, float)) or not isinstance(ov, (int, float)):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if not math.isfinite(ev) or not math.isfinite(ov):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if abs(ev - ov) > 1e-5:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            norm_sq += float(ov) * float(ov)

        if abs(norm_sq - 1.0) > 1e-5:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")


def validate_search_hits(
    hits: list[dict],
    scope: DocumentScope,
    index_version: bytes,
    expected_chunk_ids: set[UUID],
    max_count: int,
) -> list[UUID]:
    if type(hits) is not list or not (1 <= len(hits) <= max_count):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    seen_points: set[str] = set()
    hit_cids: list[UUID] = []
    for h in hits:
        if type(h) is not dict:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        score = h.get("score")
        if score is None or type(score) is bool or not isinstance(score, (int, float)):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        try:
            score_val = float(score)
        except (OverflowError, ValueError, TypeError):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE") from None
        if not math.isfinite(score_val) or not (-1.0 - 1e-5 <= score_val <= 1.0 + 1e-5):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        pid_raw = h.get("id")
        if type(pid_raw) is not str:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        try:
            pid = UUID(pid_raw)
        except (ValueError, TypeError):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE") from None
        if str(pid) != pid_raw:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        if pid_raw in seen_points:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        seen_points.add(pid_raw)

        pl = h.get("payload")
        if type(pl) is not dict:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        expected_keys = {"chunk_id", "owner_id", "paper_id", "document_version_id", "section_type"}
        if set(pl.keys()) != expected_keys:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        if (
            pl.get("owner_id") != str(scope.owner_id)
            or pl.get("paper_id") != str(scope.paper_id)
            or pl.get("document_version_id") != str(scope.document_version_id)
            or pl.get("section_type") != "body"
        ):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        cid_raw = pl.get("chunk_id")
        if type(cid_raw) is not str:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        try:
            cid = UUID(cid_raw)
        except (ValueError, TypeError):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE") from None
        if str(cid) != cid_raw:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        if cid not in expected_chunk_ids:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        expected_pid = str(point_id(index_version, cid))
        if pid_raw != expected_pid:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        hit_cids.append(cid)

    return hit_cids



@dataclass(frozen=True, slots=True)
class IndexReceipt:
    profile: ProcessingProfile
    scope: DocumentScope
    source_sha256: bytes
    prior_stage_hashes: tuple[tuple[str, bytes], ...]
    chunk_set_hash: bytes
    embedding_manifest_hash: bytes
    point_set_hash: bytes
    collection: str
    point_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.profile, ProcessingProfile):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if not isinstance(self.scope, DocumentScope):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if type(self.source_sha256) is not bytes or len(self.source_sha256) != 32:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if type(self.prior_stage_hashes) is not tuple or len(self.prior_stage_hashes) != len(PRIOR_STAGES):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        for idx, st in enumerate(PRIOR_STAGES):
            pair = self.prior_stage_hashes[idx]
            if type(pair) is not tuple or len(pair) != 2 or pair[0] != st or type(pair[1]) is not bytes or len(pair[1]) != 32:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if type(self.chunk_set_hash) is not bytes or len(self.chunk_set_hash) != 32:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if type(self.embedding_manifest_hash) is not bytes or len(self.embedding_manifest_hash) != 32:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if self.embedding_manifest_hash != self.prior_stage_hashes[4][1]:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if type(self.point_set_hash) is not bytes or len(self.point_set_hash) != 32:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if type(self.collection) is not str or not self.collection:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if type(self.point_count) is not int or type(self.point_count) is bool or self.point_count <= 0:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    @property
    def profile_hash(self) -> bytes:
        return self.profile.profile_hash

    @property
    def index_version(self) -> bytes:
        return self.profile.index_version


class QdrantClient:
    def __init__(self, endpoint: str | None = None, deadline: float | None = None, *, cancel: Event | None=None):
        if endpoint is None:
            endpoint = get_settings().qdrant_endpoint
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("qdrant endpoint must be a plain HTTP origin")
        self.endpoint = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        self.deadline = deadline
        self.cancel=cancel

    async def _request(
        self, client: httpx2.AsyncClient, method: str, path: str, payload: dict | None = None
    ) -> dict:
        url = f"{self.endpoint}/{path.lstrip('/')}"
        async with client.stream(
            method, url, json=payload if payload is not None else None
        ) as response:
            if response.status_code == 429:
                raise StageFailure(
                    "DEPENDENCY_RATE_LIMITED", "temporary", True, retry_after_seconds=5
                )
            if response.status_code >= 500:
                raise StageFailure(
                    "DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5
                )

            data = bytearray()
            async for part in response.aiter_bytes(chunk_size=65536):
                if len(data) + len(part) > _MAX_RESPONSE_BYTES:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                data.extend(part)

            try:
                value = json.loads(data)
            except (ValueError, UnicodeError, RecursionError):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE") from None

            if type(value) is not dict:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            if response.status_code == 404:
                return value
            if 200 <= response.status_code < 300:
                return value
            clean_path = "/" + path.lstrip("/").split("?")[0].rstrip("/")
            if (
                method == "PUT"
                and clean_path.startswith("/collections/")
                and clean_path.count("/") == 2
                and response.status_code in (400, 409)
            ):
                return value

            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    def _run(self, operation):
        try:
            return asyncio.run(cancellable(operation,self.cancel))
        except (httpx2.TimeoutException, TimeoutError):
            raise StageFailure(
                "DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5
            ) from None
        except (httpx2.RequestError, OSError):
            raise StageFailure(
                "DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5
            ) from None

    async def _async_request(
        self, method: str, path: str, payload: dict | None = None
    ) -> dict:
        remaining = 10.0
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise StageFailure(
                    "DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5
                )
        timeout = max(0.001, min(remaining, 10.0))
        async with (
            asyncio.timeout(timeout),
            httpx2.AsyncClient(timeout=timeout, trust_env=False) as client,
        ):
            return await self._request(client, method, path, payload)

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        return self._run(self._async_request(method, path, payload))

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _validate_collection_schema(res: dict, profile: ProcessingProfile) -> dict:
    if type(res) is not dict or res.get("status") != "ok":
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    result = res.get("result")
    if type(result) is not dict:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    config = result.get("config")
    if type(config) is not dict:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    params = config.get("params")
    if type(params) is not dict:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    vectors = params.get("vectors")
    if type(vectors) is not dict:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    size = vectors.get("size")
    dist = vectors.get("distance")
    if type(size) is not int or type(size) is bool or size != profile.dimension:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    if type(dist) is not str or dist.lower() != profile.distance.lower():
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    payload_schema = result.get("payload_schema")
    if type(payload_schema) is not dict:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    for field, field_info in payload_schema.items():
        if type(field_info) is not dict:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    return result


def ensure_collection(profile: ProcessingProfile, *, client: QdrantClient | None = None) -> None:
    owned_client = False
    if client is None:
        client = QdrantClient()
        owned_client = True
    try:
        name = collection_name(profile)
        res = client.request("GET", f"/collections/{name}")
        collection_exists = False
        if type(res) is dict and res.get("status") == "ok" and res.get("result") is not None:
            _validate_collection_schema(res, profile)
            collection_exists = True
        elif type(res) is dict and res.get("status") != "ok":
            pass
        else:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        if not collection_exists:
            create_res = client.request(
                "PUT",
                f"/collections/{name}",
                {
                    "vectors": {
                        "size": profile.dimension,
                        "distance": "Cosine",
                    }
                },
            )
            if create_res.get("status") != "ok":
                # Re-read to handle concurrent creation / replay race
                fresh_res = client.request("GET", f"/collections/{name}")
                _validate_collection_schema(fresh_res, profile)
            else:
                fresh_res = client.request("GET", f"/collections/{name}")
                _validate_collection_schema(fresh_res, profile)

        # Ensure all 4 keyword payload indexes with wait=true and completed check
        schema_res = client.request("GET", f"/collections/{name}")
        result = _validate_collection_schema(schema_res, profile)
        payload_schema = result.get("payload_schema", {})
        for field in ("owner_id", "paper_id", "document_version_id", "section_type"):
            if field in payload_schema:
                field_info = payload_schema[field]
                if field_info.get("data_type") != "keyword":
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            else:
                idx_res = client.request(
                    "PUT",
                    f"/collections/{name}/index?wait=true",
                    {"field_name": field, "field_schema": "keyword"},
                )
                if idx_res.get("status") != "ok":
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                idx_result = idx_res.get("result")
                if not isinstance(idx_result, dict) or idx_result.get("status") != "completed":
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        # Fresh schema re-read: verify all 4 keyword indexes are confirmed present
        final_res = client.request("GET", f"/collections/{name}")
        final_result = _validate_collection_schema(final_res, profile)
        final_schema = final_result.get("payload_schema", {})
        for field in ("owner_id", "paper_id", "document_version_id", "section_type"):
            if (
                field not in final_schema
                or not isinstance(final_schema[field], dict)
                or final_schema[field].get("data_type") != "keyword"
            ):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    finally:
        if owned_client:
            client.close()


def _unpack_vectors(data: bytes, count: int, dimension: int = 1024) -> list[list[float]]:
    validate_vectors(data, count, dimension)
    values = array("f")
    values.frombytes(data)
    if sys.byteorder != "little":
        values.byteswap()
    result = []
    for idx in range(count):
        vec = values[idx * dimension : (idx + 1) * dimension].tolist()
        result.append(vec)
    return result


def _load_indexing_metadata(lease: Lease):
    with get_conn() as conn:
        with short_transaction(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT j.*,v.paper_id FROM ingestion_jobs j JOIN document_versions v
                       ON v.id=j.document_version_id AND v.owner_id=j.owner_id
                       WHERE j.id=%s AND j.owner_id=%s AND j.document_version_id=%s AND v.paper_id=%s
                         AND j.locked_by=%s AND j.lease_generation=%s AND j.status='running'
                         AND j.lease_expires_at>clock_timestamp() FOR UPDATE OF j""",
                    (
                        lease.job_id,
                        lease.scope.owner_id,
                        lease.scope.document_version_id,
                        lease.scope.paper_id,
                        lease.locked_by,
                        lease.generation,
                    ),
                )
                job = cursor.fetchone()
            if job is None:
                raise LostLease()
            if job["stage"] not in ("embedding", "indexing"):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            paper_row = conn.execute(
                """SELECT active_version_id FROM papers WHERE id=%s AND owner_id=%s""",
                (lease.scope.paper_id, lease.scope.owner_id),
            ).fetchone()
            if paper_row is None or paper_row[0] != lease.scope.document_version_id:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            proc_row = conn.execute(
                """SELECT p.profile, p.profile_hash, p.original_sha256, v.sha256
                   FROM document_processing p
                   JOIN document_versions v ON v.id=p.document_version_id AND v.owner_id=p.owner_id
                   WHERE p.owner_id=%s AND p.paper_id=%s AND p.document_version_id=%s AND p.profile_hash=%s""",
                (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, job["profile_hash"]),
            ).fetchone()
            if proc_row is None:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            profile = ProcessingProfile(**proc_row[0])
            if profile.profile_hash != bytes(proc_row[1]) or profile.profile_hash != bytes(job["profile_hash"]):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            source_sha256 = bytes(proc_row[2])
            if source_sha256 != bytes(proc_row[3]):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            counts_row = conn.execute(
                """SELECT
                    (SELECT count(*) FROM document_pages WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s) AS page_count,
                    (SELECT count(*) FROM document_sections WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s) AS section_count,
                    (SELECT count(*) FROM document_blocks WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s) AS block_count,
                    (SELECT count(*) FROM document_spans WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s) AS span_count""",
                (
                    lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id,
                    lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id,
                    lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id,
                    lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id,
                ),
            ).fetchone()
            if counts_row is None:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            page_count, section_count, block_count, span_count = counts_row
            if page_count <= 0 or section_count <= 0 or block_count <= 0 or span_count <= 0:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            manifest_rows = conn.execute(
                """SELECT stage, content_hash, record_count, artifacts
                   FROM stage_manifests
                   WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s
                   ORDER BY CASE stage
                       WHEN 'validating' THEN 1
                       WHEN 'parsing' THEN 2
                       WHEN 'normalizing' THEN 3
                       WHEN 'chunking' THEN 4
                       WHEN 'embedding' THEN 5
                       ELSE 6 END
                   LIMIT 6""",
                (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, job["profile_hash"]),
            ).fetchall()
            if len(manifest_rows) != len(PRIOR_STAGES):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            prior_stage_tuples = tuple((row[0], bytes(row[1])) for row in manifest_rows)
            prior_stage_hashes = dict(prior_stage_tuples)
            prior_record_counts = {row[0]: row[2] for row in manifest_rows}
            prior_artifacts = {row[0]: row[3] for row in manifest_rows}

            for st in PRIOR_STAGES:
                if st not in prior_stage_hashes:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            if prior_record_counts.get("validating") != 1 or prior_stage_hashes.get("validating") != source_sha256:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            expected_parsing_count = page_count + block_count + span_count
            if prior_record_counts.get("parsing") != expected_parsing_count:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            parsing_arts = prior_artifacts.get("parsing")
            if not isinstance(parsing_arts, list) or len(parsing_arts) != 1:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            parser_art = parsing_arts[0]
            if not isinstance(parser_art, dict):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            parser_sha = parser_art.get("sha256")
            parser_key = parser_art.get("key")
            parser_bytes = parser_art.get("byte_count")
            if (
                not isinstance(parser_sha, str)
                or not isinstance(parser_key, str)
                or not isinstance(parser_bytes, int)
                or type(parser_bytes) is bool
                or parser_bytes <= 0
                or len(parser_sha) != 64
            ):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if bytes.fromhex(parser_sha) != prior_stage_hashes["parsing"]:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            expected_key_prefix = f"processing/{lease.scope.owner_id}/{lease.scope.document_version_id}/{profile.profile_hash.hex()}/parsing/"
            if not parser_key.startswith(expected_key_prefix) or parser_key != expected_key_prefix + parser_sha:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            expected_normalizing_count = page_count + section_count + block_count + span_count
            if prior_record_counts.get("normalizing") != expected_normalizing_count:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            chunks = conn.execute(
                """SELECT c.id, c.section_id, c.ordinal, c.text, c.checksum
                   FROM document_chunks c
                   JOIN document_sections s ON s.id=c.section_id AND s.owner_id=c.owner_id AND s.document_version_id=c.document_version_id
                   WHERE c.owner_id=%s AND c.paper_id=%s AND c.document_version_id=%s AND c.profile_hash=%s
                   ORDER BY c.ordinal LIMIT %s""",
                (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, job["profile_hash"], profile.max_chunks + 1),
            ).fetchall()
            if not (1 <= len(chunks) <= profile.max_chunks):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if any(c[2] != idx for idx, c in enumerate(chunks)):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            if (
                prior_record_counts["chunking"] != len(chunks)
                or prior_record_counts["embedding"] != len(chunks)
            ):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            expected_chunking_hash = hashlib.sha256(b"".join(bytes(c[4]) for c in chunks)).digest()
            if expected_chunking_hash != prior_stage_hashes.get("chunking"):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            max_batches = (profile.max_chunks + 3) // 4 + 1
            batch_rows = conn.execute(
                """SELECT batch_ordinal, chunk_ids, content_hash, artifact
                   FROM embedding_batches
                   WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s
                   ORDER BY batch_ordinal LIMIT %s""",
                (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, job["profile_hash"], max_batches),
            ).fetchall()
            if not batch_rows or len(batch_rows) > (profile.max_chunks + 3) // 4:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            batch_cids = [cid for b in batch_rows for cid in b[1]]
            chunk_cids = [c[0] for c in chunks]
            if batch_cids != chunk_cids:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            digest = hashlib.sha256()
            recomputed_artifacts = []
            for ordinal, batch in enumerate(batch_rows):
                b_ord, b_cids, b_hash, b_art = batch
                if b_ord != ordinal or not isinstance(b_art, dict):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                b_sha = b_art.get("sha256")
                b_key = b_art.get("key")
                b_bytes = b_art.get("byte_count")
                if (
                    not isinstance(b_sha, str)
                    or not isinstance(b_key, str)
                    or not isinstance(b_bytes, int)
                    or type(b_bytes) is bool
                    or b_bytes <= 0
                    or len(b_sha) != 64
                    or bytes.fromhex(b_sha) != bytes(b_hash)
                ):
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                expected_batch_key = f"processing/{lease.scope.owner_id}/{lease.scope.document_version_id}/{profile.profile_hash.hex()}/embedding/{b_sha}"
                if b_key != expected_batch_key:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

                digest.update(
                    json.dumps(
                        {
                            "ordinal": ordinal,
                            "chunk_ids": [str(cid) for cid in b_cids],
                            "sha256": bytes(b_hash).hex(),
                            "artifact": b_art,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                )
                recomputed_artifacts.append(
                    {"key": b_key, "sha256": b_sha, "byte_count": b_bytes}
                )

            expected_embedding_manifest_hash = digest.digest()
            if expected_embedding_manifest_hash != prior_stage_hashes["embedding"]:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            embedding_artifacts = prior_artifacts.get("embedding")
            if not isinstance(embedding_artifacts, list) or len(embedding_artifacts) != len(recomputed_artifacts):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if embedding_artifacts != recomputed_artifacts:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            return job, profile, source_sha256, prior_stage_tuples, chunks, batch_rows


def index_selected(lease: Lease, deadline: float, *, cancel: Event | None=None) -> IndexReceipt:
    if time.monotonic() >= deadline:
        raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

    job, profile, source_sha256, prior_stage_tuples, chunks, batch_rows = _load_indexing_metadata(lease)

    target_collection = collection_name(profile)
    with QdrantClient(deadline=deadline,cancel=cancel) as client:
        ensure_collection(profile, client=client)

        for batch_row in batch_rows:
            batch_ordinal, b_chunk_ids, content_hash, artifact_dict = batch_row
            content_hash = bytes(content_hash)

            if time.monotonic() >= deadline:
                raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

            with get_conn() as conn:
                with short_transaction(conn):
                    vec_row = conn.execute(
                        """SELECT selected_bytes FROM embedding_batches
                           WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s AND batch_ordinal=%s""",
                        (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, job["profile_hash"], batch_ordinal),
                    ).fetchone()
            if vec_row is None:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            selected_bytes = bytes(vec_row[0])

            if hashlib.sha256(selected_bytes).digest() != content_hash:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if artifact_dict.get("sha256") != content_hash.hex() or artifact_dict.get("byte_count") != len(selected_bytes):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            ref = ArtifactRef(
                key=artifact_dict["key"],
                sha256=content_hash,
                byte_count=len(selected_bytes),
            )
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir) / "selected.bin"
                verify_artifact(ref, tmp_path, deadline=deadline,cancel=cancel)
                downloaded = tmp_path.read_bytes()
                if downloaded != selected_bytes:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

            validate_vectors(selected_bytes, len(b_chunk_ids), profile.dimension)
            vectors = _unpack_vectors(selected_bytes, len(b_chunk_ids), profile.dimension)

            batch_points = []
            for chunk_id, vec in zip(b_chunk_ids, vectors):
                pid = str(point_id(profile.index_version, chunk_id))
                payload = {
                    "chunk_id": str(chunk_id),
                    "owner_id": str(lease.scope.owner_id),
                    "paper_id": str(lease.scope.paper_id),
                    "document_version_id": str(lease.scope.document_version_id),
                    "section_type": "body",
                }
                batch_points.append({"id": pid, "payload": payload, "vector": vec})

            upsert_res = client.request(
                "PUT",
                f"/collections/{target_collection}/points?wait=true",
                {"points": batch_points},
            )
            if upsert_res.get("status") != "ok":
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            res_data = upsert_res.get("result", {})
            if not isinstance(res_data, dict) or res_data.get("status") != "completed":
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    return verify_index(lease, deadline,cancel=cancel)


def verify_index(lease: Lease, deadline: float, *, cancel: Event | None=None) -> IndexReceipt:
    if time.monotonic() >= deadline:
        raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

    job, profile, source_sha256, prior_stage_tuples, chunks, batch_rows = _load_indexing_metadata(lease)
    prior_stage_hashes = dict(prior_stage_tuples)

    chunk_ids = [c[0] for c in chunks]
    c_set_hash = chunk_set_hash(chunk_ids)
    point_ids = [point_id(profile.index_version, cid) for cid in chunk_ids]
    p_set_hash = point_set_hash(point_ids)

    expected_point_ids = {str(pid) for pid in point_ids}
    point_id_to_chunk = {str(pid): cid for pid, cid in zip(point_ids, chunk_ids)}
    chunk_id_to_ordinal = {cid: idx for idx, cid in enumerate(chunk_ids)}

    target_collection = collection_name(profile)
    filter_payload = {
        "must": [
            {"key": "owner_id", "match": {"value": str(lease.scope.owner_id)}},
            {"key": "paper_id", "match": {"value": str(lease.scope.paper_id)}},
            {"key": "document_version_id", "match": {"value": str(lease.scope.document_version_id)}},
        ]
    }

    with QdrantClient(deadline=deadline,cancel=cancel) as client, get_conn() as provenance_conn:
        cnt_res = client.request(
            "POST",
            f"/collections/{target_collection}/points/count",
            {
                "filter": {"must": [{"key": "document_version_id", "match": {"value": str(lease.scope.document_version_id)}}]},
                "exact": True,
            },
        )
        if type(cnt_res) is not dict or cnt_res.get("status") != "ok":
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        cnt_result = cnt_res.get("result")
        if type(cnt_result) is not dict or "count" not in cnt_result:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        cnt_val = cnt_result.get("count")
        if type(cnt_val) is not int or type(cnt_val) is bool or cnt_val != len(chunk_ids):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        observed_ids: set[str] = set()
        offset = None
        cached_batch_ordinal = -1
        cached_vectors: list[list[float]] = []

        while True:
            if time.monotonic() >= deadline:
                raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

            scroll_payload: dict = {
                "filter": filter_payload,
                "limit": 4,
                "with_payload": True,
                "with_vector": True,
            }
            if offset is not None:
                scroll_payload["offset"] = offset
            s_res = client.request(
                "POST",
                f"/collections/{target_collection}/points/scroll",
                scroll_payload,
            )
            if type(s_res) is not dict or s_res.get("status") != "ok":
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            res_dict = s_res.get("result")
            if type(res_dict) is not dict or "points" not in res_dict:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            pts = res_dict.get("points")
            if type(pts) is not list:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            if not pts:
                break
            if len(pts) > 4:
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
            for pt in pts:
                if type(pt) is not dict:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                pid = str(pt.get("id", ""))
                if pid in observed_ids or pid not in expected_point_ids:
                    raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                observed_ids.add(pid)

                cid = point_id_to_chunk[pid]
                cord = chunk_id_to_ordinal[cid]
                batch_ord = cord // 4
                idx_in_batch = cord % 4

                if batch_ord != cached_batch_ordinal:
                    if time.monotonic() >= deadline:
                        raise StageFailure("DEPENDENCY_UNAVAILABLE", "temporary", True, retry_after_seconds=5)

                    with get_conn() as conn:
                        with short_transaction(conn):
                            row = conn.execute(
                                """SELECT chunk_ids, selected_bytes, content_hash, artifact
                                   FROM embedding_batches
                                   WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s AND batch_ordinal=%s""",
                                (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, job["profile_hash"], batch_ord),
                            ).fetchone()
                    if row is None:
                        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
                    b_chunk_ids, b_bytes, b_hash, b_artifact = row
                    b_bytes = bytes(b_bytes)
                    b_hash = bytes(b_hash)
                    if hashlib.sha256(b_bytes).digest() != b_hash:
                        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

                    ref = ArtifactRef(
                        key=b_artifact["key"],
                        sha256=b_hash,
                        byte_count=len(b_bytes),
                    )
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_path = Path(tmp_dir) / "selected.bin"
                        verify_artifact(ref, tmp_path, deadline=deadline,cancel=cancel)
                        downloaded = tmp_path.read_bytes()
                        if downloaded != b_bytes:
                            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

                    validate_vectors(b_bytes, len(b_chunk_ids), profile.dimension)
                    cached_vectors = _unpack_vectors(b_bytes, len(b_chunk_ids), profile.dimension)
                    cached_batch_ordinal = batch_ord

                expected_vector = cached_vectors[idx_in_batch]
                expected_pt = {
                    "id": pid,
                    "payload": {
                        "chunk_id": str(cid),
                        "owner_id": str(lease.scope.owner_id),
                        "paper_id": str(lease.scope.paper_id),
                        "document_version_id": str(lease.scope.document_version_id),
                        "section_type": "body",
                    },
                    "vector": expected_vector,
                }
                validate_point_set([expected_pt], [pt])
                # A search probe cannot establish provenance for the entire publication.
                resolve_range(provenance_conn, lease.scope, cid, 0, len(chunks[cord][3]))

            offset = res_dict.get("next_page_offset")
            if offset is None:
                break

        if observed_ids != expected_point_ids:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        with get_conn() as conn:
            with short_transaction(conn):
                first_batch_row = conn.execute(
                    """SELECT selected_bytes FROM embedding_batches
                       WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s AND batch_ordinal=0""",
                    (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, job["profile_hash"]),
                ).fetchone()
        if first_batch_row is None:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        first_vec_bytes = bytes(first_batch_row[0])[: profile.dimension * 4]
        first_vector = _unpack_vectors(first_vec_bytes, 1, profile.dimension)[0]

        search_res = client.request(
            "POST",
            f"/collections/{target_collection}/points/search",
            {
                "vector": first_vector,
                "filter": filter_payload,
                "limit": min(5, len(chunk_ids)),
                "with_payload": True,
                "with_vector": False,
            },
        )
        if type(search_res) is not dict or search_res.get("status") != "ok":
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        validate_search_hits(
            search_res.get("result"),
            lease.scope,
            profile.index_version,
            set(chunk_ids),
            min(5, len(chunk_ids)),
        )
        schema_res = client.request("GET", f"/collections/{target_collection}")
        schema_result = _validate_collection_schema(schema_res, profile)
        payload_schema = schema_result.get("payload_schema", {})
        for field in ("owner_id", "paper_id", "document_version_id", "section_type"):
            if (
                field not in payload_schema
                or not isinstance(payload_schema[field], dict)
                or payload_schema[field].get("data_type") != "keyword"
            ):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    return IndexReceipt(
        profile=profile,
        scope=lease.scope,
        source_sha256=source_sha256,
        prior_stage_hashes=prior_stage_tuples,
        chunk_set_hash=c_set_hash,
        embedding_manifest_hash=prior_stage_hashes["embedding"],
        point_set_hash=p_set_hash,
        collection=target_collection,
        point_count=len(chunk_ids),
    )


def publish_ready(conn: psycopg.Connection, lease: Lease, receipt: IndexReceipt) -> None:
    if not isinstance(receipt, IndexReceipt):
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
    if receipt.scope != lease.scope:
        raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

    with fenced_transaction(conn, lease, ends_lease=True) as job:
        if job["stage"] != "indexing" or bytes(job["profile_hash"]) != receipt.profile_hash:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        paper_row = conn.execute(
            """SELECT active_version_id FROM papers WHERE id=%s AND owner_id=%s""",
            (lease.scope.paper_id, lease.scope.owner_id),
        ).fetchone()
        if paper_row is None or paper_row[0] != lease.scope.document_version_id:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        proc_row = conn.execute(
            """SELECT p.original_sha256, p.profile_hash, v.sha256
               FROM document_processing p
               JOIN document_versions v ON v.id=p.document_version_id AND v.owner_id=p.owner_id
               WHERE p.owner_id=%s AND p.paper_id=%s AND p.document_version_id=%s AND p.profile_hash=%s""",
            (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, receipt.profile_hash),
        ).fetchone()
        if proc_row is None:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if (
            bytes(proc_row[0]) != receipt.source_sha256
            or bytes(proc_row[1]) != receipt.profile_hash
            or bytes(proc_row[2]) != receipt.source_sha256
        ):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        counts_row = conn.execute(
            """SELECT
                (SELECT count(*) FROM document_pages WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s) AS page_count,
                (SELECT count(*) FROM document_sections WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s) AS section_count,
                (SELECT count(*) FROM document_blocks WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s) AS block_count,
                (SELECT count(*) FROM document_spans WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s) AS span_count""",
            (
                lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id,
                lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id,
                lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id,
                lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id,
            ),
        ).fetchone()
        if counts_row is None:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        page_count, section_count, block_count, span_count = counts_row
        if page_count <= 0 or section_count <= 0 or block_count <= 0 or span_count <= 0:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        manifest_rows = conn.execute(
            """SELECT stage, content_hash, record_count
               FROM stage_manifests
               WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s
               ORDER BY CASE stage
                   WHEN 'validating' THEN 1
                   WHEN 'parsing' THEN 2
                   WHEN 'normalizing' THEN 3
                   WHEN 'chunking' THEN 4
                   WHEN 'embedding' THEN 5
                   ELSE 6 END
               LIMIT 6""",
            (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, receipt.profile_hash),
        ).fetchall()
        if len(manifest_rows) != len(PRIOR_STAGES):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        db_prior_tuples = tuple((row[0], bytes(row[1])) for row in manifest_rows)
        if db_prior_tuples != receipt.prior_stage_hashes:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        prior_counts = {row[0]: row[2] for row in manifest_rows}
        if prior_counts.get("validating") != 1:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if prior_counts.get("parsing") != page_count + block_count + span_count:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if prior_counts.get("normalizing") != page_count + section_count + block_count + span_count:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        if (
            prior_counts.get("embedding") != receipt.point_count
            or prior_counts.get("chunking") != receipt.point_count
        ):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        if receipt.collection != collection_name(receipt.profile):
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        chunk_rows = conn.execute(
            """SELECT id, ordinal FROM document_chunks
               WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s
               ORDER BY ordinal LIMIT %s""",
            (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id, receipt.profile_hash, receipt.profile.max_chunks + 1),
        ).fetchall()
        if len(chunk_rows) != receipt.point_count:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        c_ids = [c[0] for c in chunk_rows]
        if chunk_set_hash(c_ids) != receipt.chunk_set_hash:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")
        p_ids = [point_id(receipt.index_version, cid) for cid in c_ids]
        if point_set_hash(p_ids) != receipt.point_set_hash:
            raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        res = conn.execute(
            """INSERT INTO index_publications (
                   owner_id, paper_id, document_version_id, profile_hash, index_version,
                   chunk_set_hash, embedding_manifest_hash, embedding_stage,
                   collection, point_count, point_set_hash
               ) VALUES (
                   %s, %s, %s, %s, %s,
                   %s, %s, 'embedding',
                   %s, %s, %s
               ) ON CONFLICT (document_version_id) DO NOTHING
               RETURNING document_version_id""",
            (
                lease.scope.owner_id,
                lease.scope.paper_id,
                lease.scope.document_version_id,
                receipt.profile_hash,
                receipt.index_version,
                receipt.chunk_set_hash,
                receipt.embedding_manifest_hash,
                receipt.collection,
                receipt.point_count,
                receipt.point_set_hash,
            ),
        ).fetchone()

        if res is None:
            existing = conn.execute(
                """SELECT owner_id, paper_id, document_version_id, profile_hash, index_version,
                          chunk_set_hash, embedding_manifest_hash, collection, point_count, point_set_hash
                   FROM index_publications
                   WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s""",
                (lease.scope.owner_id, lease.scope.paper_id, lease.scope.document_version_id),
            ).fetchone()
            if existing is None or (
                existing[0] != lease.scope.owner_id
                or existing[1] != lease.scope.paper_id
                or bytes(existing[3]) != receipt.profile_hash
                or bytes(existing[4]) != receipt.index_version
                or bytes(existing[5]) != receipt.chunk_set_hash
                or bytes(existing[6]) != receipt.embedding_manifest_hash
                or existing[7] != receipt.collection
                or existing[8] != receipt.point_count
                or bytes(existing[9]) != receipt.point_set_hash
            ):
                raise IntegrityFailure("PROCESSING_INTEGRITY_FAILURE")

        conn.execute(
            """UPDATE ingestion_jobs SET
                   stage='ready',
                   status='succeeded',
                   completed_at=clock_timestamp(),
                   updated_at=clock_timestamp(),
                   locked_by=NULL,
                   lease_expires_at=NULL,
                   heartbeat_at=NULL,
                   error_code=NULL,
                   failed_stage=NULL,
                   failure_kind=NULL,
                   retryable=false
               WHERE id=%s AND owner_id=%s AND locked_by=%s AND lease_generation=%s""",
            (lease.job_id, lease.scope.owner_id, lease.locked_by, lease.generation),
        )

        record_transition(conn, lease.job_id, lease.scope.owner_id)
