from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID
import psycopg

from researcy.db import get_conn
from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from .repository import ReadyDocument, EvidenceHit, hydrate_hits, search_dense


def _rank_scores(dense_ids: Sequence[UUID], lexical_ids: Sequence[UUID]) -> dict[UUID, float]:
    scores: dict[UUID, float] = {}
    for branch in (dense_ids, lexical_ids):
        seen = set()
        for rank, chunk_id in enumerate(branch, 1):
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            scores[chunk_id] = scores.get(chunk_id,0.)+1/(60+rank)
    return scores


def fuse_ranks(dense_ids: Sequence[UUID], lexical_ids: Sequence[UUID]) -> tuple[UUID, ...]:
    scores = _rank_scores(dense_ids,lexical_ids)
    return tuple(sorted(scores,key=lambda chunk_id:(-scores[chunk_id],chunk_id.int)))


def search_lexical(document: ReadyDocument, query: str) -> list[EvidenceHit]:
    if type(query) is not str or not 1<=len(query)<=2400:
        raise ValueError('query must be a string between 1 and 2400 code points')
    scope = document.scope
    try:
        with get_conn() as conn:
            with short_transaction(conn):
                rows = conn.execute('''SELECT id,ts_rank_cd(search_vector,q.query) score
                    FROM document_chunks CROSS JOIN (SELECT websearch_to_tsquery('simple',%s) query) q
                    WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND profile_hash=%s
                      AND search_vector@@q.query ORDER BY score DESC,id LIMIT 5''',
                    (query,scope.owner_id,scope.paper_id,scope.document_version_id,document.profile_hash)).fetchall()
        return hydrate_hits(document, rows)
    except psycopg.Error:
        raise APIError(503,'DEPENDENCY_UNAVAILABLE','The evidence database is temporarily unavailable.') from None


def pack_evidence(hits: Sequence[EvidenceHit]) -> tuple[EvidenceHit, ...]:
    packed, normalized_size, raw_size = [], 0, 0
    for hit in hits[:5]:
        source_size = sum(len(location.quote) for location in hit.locations)
        if not hit.text or not hit.locations:
            raise APIError(503,'EVIDENCE_UNAVAILABLE','The paper evidence is unavailable.')
        if normalized_size+len(hit.text)>12000 or raw_size+source_size>12000:
            continue
        packed.append(hit)
        normalized_size += len(hit.text)
        raw_size += source_size
        if len(packed)==5:
            break
    return tuple(packed)


def retrieve_same_paper(document: ReadyDocument, query: str) -> tuple[EvidenceHit, ...]:
    dense = search_dense(document,query)
    lexical = search_lexical(document,query)
    by_id = {hit.chunk_id:hit for hit in (*dense,*lexical)}
    scores = _rank_scores([hit.chunk_id for hit in dense],[hit.chunk_id for hit in lexical])
    ranked = sorted(scores,key=lambda chunk_id:(-scores[chunk_id],chunk_id.int))[:5]
    return pack_evidence(tuple(replace(by_id[chunk_id],score=scores[chunk_id]) for chunk_id in ranked))
