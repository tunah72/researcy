"""Owner-scoped internal vector retrieval and canonical provenance rehydration."""

from array import array
from dataclasses import dataclass
import math
import sys
import time
from uuid import UUID

import httpx2
import psycopg
from psycopg.rows import dict_row

from researcy.config import get_settings
from researcy.db import get_conn
from researcy.documents.canonical import EvidenceLocation
from researcy.documents.provenance import resolve_range
from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.ingestion.models import (
    DocumentScope,
    IntegrityFailure,
    ProcessingProfile,
    StageFailure,
)
from researcy.retrieval.embedding import EmbeddingClient, validate_vectors
from researcy.retrieval import index


@dataclass(frozen=True, slots=True)
class EvidenceHit:
    scope: DocumentScope
    chunk_id: UUID
    section_id: UUID
    text: str
    score: float
    locations: tuple[EvidenceLocation, ...]




def search_owned(
    owner_id: UUID,
    paper_id: UUID,
    query: str,
    limit: int = 5,
) -> list[EvidenceHit]:
    """Execute an owner-scoped dense query against ready published evidence.

    Authorization and readiness must validate in PostgreSQL before any model or
    Qdrant call. Foreign/nonexistent papers return 404. Unready papers or poisoned
    payloads return safe unavailable evidence ([]). Expensive work runs outside
    database transactions.
    """
    if not isinstance(owner_id, UUID) or not isinstance(paper_id, UUID):
        raise ValueError("owner_id and paper_id must be UUID instances")
    if type(query) is not str or not (1 <= len(query) <= 2400):
        raise ValueError("query must be a string between 1 and 2400 code points")
    if type(limit) is not int or isinstance(limit, bool) or not (1 <= limit <= 5):
        raise ValueError("limit must be an integer between 1 and 5")

    # 1. Authoritative ownership, readiness, publication, and manifest check in PostgreSQL
    with get_conn() as conn:
        with short_transaction(conn):
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, active_version_id FROM papers WHERE id = %s AND owner_id = %s",
                    (paper_id, owner_id),
                )
                paper_row = cur.fetchone()
                if paper_row is None:
                    raise APIError(404, "RESOURCE_NOT_FOUND", "The requested resource was not found.")

                active_version_id = paper_row["active_version_id"]
                if active_version_id is None:
                    return []

                cur.execute(
                    """SELECT stage, status, profile_hash
                       FROM ingestion_jobs
                       WHERE owner_id = %s AND document_version_id = %s""",
                    (owner_id, active_version_id),
                )
                job_row = cur.fetchone()
                if (
                    job_row is None
                    or job_row["stage"] != "ready"
                    or job_row["status"] != "succeeded"
                    or job_row["profile_hash"] is None
                ):
                    return []
                job_profile_hash = bytes(job_row["profile_hash"])

                cur.execute(
                    """SELECT profile, index_version
                       FROM document_processing
                       WHERE owner_id = %s AND paper_id = %s AND document_version_id = %s AND profile_hash = %s""",
                    (owner_id, paper_id, active_version_id, job_profile_hash),
                )
                proc_row = cur.fetchone()
                if proc_row is None:
                    return []

                try:
                    profile = ProcessingProfile(**proc_row["profile"])
                except (TypeError, ValueError):
                    return []

                if (
                    profile.profile_hash != job_profile_hash
                    or profile.index_version != bytes(proc_row["index_version"])
                ):
                    return []

                cur.execute(
                    """SELECT collection, point_count, point_set_hash, chunk_set_hash, embedding_manifest_hash
                       FROM index_publications
                       WHERE owner_id = %s AND paper_id = %s AND document_version_id = %s AND profile_hash = %s""",
                    (owner_id, paper_id, active_version_id, job_profile_hash),
                )
                pub_row = cur.fetchone()
                if pub_row is None or pub_row["point_count"] <= 0:
                    return []

                pub_collection = pub_row["collection"]
                expected_collection = index.collection_name(profile)
                if pub_collection != expected_collection:
                    return []

                pub_embedding_manifest_hash = bytes(pub_row["embedding_manifest_hash"])

                cur.execute(
                    """SELECT content_hash, record_count
                       FROM stage_manifests
                       WHERE owner_id = %s AND paper_id = %s AND document_version_id = %s AND profile_hash = %s
                         AND stage = 'embedding' AND content_hash = %s""",
                    (owner_id, paper_id, active_version_id, job_profile_hash, pub_embedding_manifest_hash),
                )
                manifest_row = cur.fetchone()
                if manifest_row is None or manifest_row["record_count"] <= 0:
                    return []

                cur.execute(
                    """SELECT id, ordinal
                       FROM document_chunks
                       WHERE owner_id = %s AND paper_id = %s AND document_version_id = %s AND profile_hash = %s
                       ORDER BY ordinal""",
                    (owner_id, paper_id, active_version_id, job_profile_hash),
                )
                chunk_rows = cur.fetchall()
                ordered_chunk_ids = [UUID(str(r["id"])) for r in chunk_rows]

                if not (len(ordered_chunk_ids) == manifest_row["record_count"] == pub_row["point_count"]):
                    return []

                expected_chunk_set_hash = index.chunk_set_hash(ordered_chunk_ids)
                if bytes(pub_row["chunk_set_hash"]) != expected_chunk_set_hash:
                    return []

                ordered_point_ids = [index.point_id(profile.index_version, cid) for cid in ordered_chunk_ids]
                expected_point_set_hash = index.point_set_hash(ordered_point_ids)
                if bytes(pub_row["point_set_hash"]) != expected_point_set_hash:
                    return []

                cur.execute(
                    """SELECT chunk_ids FROM embedding_batches
                       WHERE owner_id = %s AND paper_id = %s AND document_version_id = %s AND profile_hash = %s""",
                    (owner_id, paper_id, active_version_id, job_profile_hash),
                )
                batch_rows = cur.fetchall()
                selected_chunk_ids: set[UUID] = set()
                for row in batch_rows:
                    selected_chunk_ids.update(UUID(str(c)) for c in row["chunk_ids"])

                if len(selected_chunk_ids) != len(ordered_chunk_ids) or set(ordered_chunk_ids) != selected_chunk_ids:
                    return []

    scope = DocumentScope(owner_id=owner_id, paper_id=paper_id, document_version_id=active_version_id)

    # 2. Expensive embedding work outside database transaction
    try:
        embedding_client = EmbeddingClient(profile)
        embedding_client.preflight()
        vector_bytes = embedding_client.embed([query])
        validate_vectors(vector_bytes, 1, profile.dimension)
    except (StageFailure, ValueError, httpx2.RequestError, httpx2.TimeoutException, OSError):
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "The embedding service is temporarily unavailable.") from None

    values = array("f")
    values.frombytes(vector_bytes)
    if sys.byteorder != "little":
        values.byteswap()
    query_vector = [float(v) for v in values]

    # 3. Expensive Qdrant search outside database transaction
    collection = expected_collection
    settings = get_settings()
    deadline = time.monotonic() + settings.worker_io_deadline_seconds

    try:
        qdrant = index.QdrantClient(endpoint=settings.qdrant_endpoint, deadline=deadline)
        search_payload = {
            "vector": query_vector,
            "filter": {
                "must": [
                    {"key": "owner_id", "match": {"value": str(owner_id)}},
                    {"key": "paper_id", "match": {"value": str(paper_id)}},
                    {"key": "document_version_id", "match": {"value": str(active_version_id)}},
                ]
            },
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        response = qdrant.request("POST", f"/collections/{collection}/points/search", search_payload)
    except (StageFailure, httpx2.RequestError, httpx2.TimeoutException, OSError):
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "The search service is temporarily unavailable.") from None

    if not isinstance(response, dict) or response.get("status") != "ok":
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "The search service is temporarily unavailable.")
    result_points = response.get("result")
    if not isinstance(result_points, list) or len(result_points) > limit:
        return []

    # 4. Strict result point and payload validation
    candidate_hits: list[tuple[UUID, float]] = []
    seen_chunk_ids: set[UUID] = set()

    for point in result_points:
        if not isinstance(point, dict):
            return []

        point_id_val = point.get("id")
        score = point.get("score")
        payload = point.get("payload")

        if point_id_val is None or score is None or not isinstance(payload, dict):
            return []

        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return []
        try:
            score_val = float(score)
        except (ValueError, TypeError, OverflowError):
            return []
        if not math.isfinite(score_val) or not (-1.0 - 1e-5 <= score_val <= 1.0 + 1e-5):
            return []

        if set(payload.keys()) != {"chunk_id", "owner_id", "paper_id", "document_version_id", "section_type"}:
            return []

        chunk_id_str = payload.get("chunk_id")
        owner_id_str = payload.get("owner_id")
        paper_id_str = payload.get("paper_id")
        version_id_str = payload.get("document_version_id")
        section_type = payload.get("section_type")

        if (
            not isinstance(chunk_id_str, str)
            or not isinstance(owner_id_str, str)
            or not isinstance(paper_id_str, str)
            or not isinstance(version_id_str, str)
            or not isinstance(section_type, str)
        ):
            return []

        if (
            owner_id_str != str(owner_id)
            or paper_id_str != str(paper_id)
            or version_id_str != str(active_version_id)
            or section_type != "body"
        ):
            return []

        try:
            chunk_uuid = UUID(chunk_id_str)
            point_uuid = UUID(str(point_id_val))
        except (ValueError, TypeError):
            return []
        if chunk_id_str != str(chunk_uuid):
            return []

        expected_point = index.point_id(profile.index_version, chunk_uuid)
        if point_uuid != expected_point:
            return []

        if chunk_uuid not in selected_chunk_ids or chunk_uuid in seen_chunk_ids:
            return []
        seen_chunk_ids.add(chunk_uuid)

        candidate_hits.append((chunk_uuid, score_val))

    # 5. Canonical rehydration and provenance verification
    evidence_hits: list[EvidenceHit] = []
    with get_conn() as conn:
        for chunk_uuid, score_val in candidate_hits:
            # Read chunk metadata in a short transaction that completes and leaves conn IDLE
            with short_transaction(conn):
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """SELECT c.section_id, c.text, c.checksum
                           FROM document_chunks c
                           JOIN document_sections s
                             ON s.id = c.section_id
                            AND s.owner_id = c.owner_id
                            AND s.paper_id = c.paper_id
                            AND s.document_version_id = c.document_version_id
                           WHERE c.id = %s
                             AND c.owner_id = %s
                             AND c.paper_id = %s
                             AND c.document_version_id = %s
                             AND c.profile_hash = %s""",
                        (chunk_uuid, owner_id, paper_id, active_version_id, job_profile_hash),
                    )
                    chunk_data = cur.fetchone()

            if chunk_data is None:
                return []

            section_id = chunk_data["section_id"]
            chunk_text = chunk_data["text"]

            # resolve_range internally uses short_transaction(conn) which requires an IDLE connection
            try:
                locations = resolve_range(conn, scope, chunk_uuid, 0, len(chunk_text))
            except (IntegrityFailure, StageFailure, APIError):
                return []

            if not locations:
                return []

            evidence_hits.append(
                EvidenceHit(
                    scope=scope,
                    chunk_id=chunk_uuid,
                    section_id=section_id,
                    text=chunk_text,
                    score=score_val,
                    locations=locations,
                )
            )

    return evidence_hits
