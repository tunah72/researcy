from dataclasses import dataclass
from uuid import UUID

import psycopg

from researcy.documents.models import Box
from researcy.errors import APIError
from researcy.ingestion.models import DocumentScope
from .models import StoredCitation


@dataclass(frozen=True,slots=True)
class CanonicalCitation:
    page_id: UUID
    evidence_quote: str
    boxes: tuple[Box,...]
    raw_fragments: tuple[dict,...]


def validate_stored_citation(conn: psycopg.Connection,scope: DocumentScope,stored: StoredCitation) -> CanonicalCitation:
    """Verify raw offsets/quote/boxes only; the caller owns membership, INSERT and transaction."""
    unresolved=APIError(422,'EVIDENCE_UNRESOLVED','The answer evidence cannot be resolved exactly.')
    citation=stored.citation
    if (citation.paper_id!=scope.paper_id or citation.document_version!=scope.document_version_id
        or not stored.raw_fragments or any(fragment.page_index+1!=citation.page for fragment in stored.raw_fragments)):
        raise unresolved
    page=conn.execute('''SELECT id FROM document_pages WHERE owner_id=%s AND paper_id=%s
        AND document_version_id=%s AND page_index=%s''',
        (scope.owner_id,scope.paper_id,scope.document_version_id,citation.page-1)).fetchone()
    if page is None:
        raise unresolved
    fragments,quote_parts,exact_boxes=[],[],[]
    sources=conn.execute('''SELECT s.id,s.raw_text,s.boxes FROM document_spans s
        JOIN document_blocks b ON b.id=s.block_id AND b.owner_id=s.owner_id
          AND b.document_version_id=s.document_version_id AND b.page_id=s.page_id
        WHERE s.owner_id=%s AND s.paper_id=%s AND s.document_version_id=%s
          AND s.page_id=%s AND s.id=ANY(%s) AND NOT b.excluded''',
        (scope.owner_id,scope.paper_id,scope.document_version_id,page[0],[f.span_id for f in stored.raw_fragments])).fetchall()
    by_id={span_id:(raw,boxes) for span_id,raw,boxes in sources}
    for fragment in stored.raw_fragments:
        source=by_id.get(fragment.span_id)
        if (source is None or type(fragment.source_start) is not int or type(fragment.source_end) is not int
            or not 0<=fragment.source_start<fragment.source_end<=len(source[0])):
            raise unresolved
        raw,source_boxes=source
        quote=raw[fragment.source_start:fragment.source_end]
        boxes=tuple(tuple(box) for box in source_boxes[fragment.source_start:fragment.source_end])
        if fragment.quote!=quote or fragment.boxes!=boxes:
            raise unresolved
        quote_parts.append(quote);exact_boxes.extend(boxes)
        fragments.append({'span_id':str(fragment.span_id),'source_start':fragment.source_start,
            'source_end':fragment.source_end,'quote':quote})
    exact_quote=''.join(quote_parts)
    if citation.evidence_quote!=exact_quote or citation.boxes!=tuple(exact_boxes):
        raise unresolved
    return CanonicalCitation(page[0],exact_quote,tuple(exact_boxes),tuple(fragments))
