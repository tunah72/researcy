import math
from uuid import UUID
import psycopg

from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.ingestion.models import DocumentScope, IntegrityFailure
from .canonical import EvidenceLocation, SourceMapping
from .normalize import LIGATURES


def _unresolved():
    return APIError(422,'EVIDENCE_UNRESOLVED','The requested source range cannot be resolved exactly.')


def _valid_boxes(boxes,raw,block,media):
    if not isinstance(boxes,list) or len(boxes)!=len(raw):
        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
    for box in boxes:
        if (not isinstance(box,list) or len(box)!=4 or any(type(value) not in (int,float) or not math.isfinite(value) for value in box)
            or box[0]>box[2] or box[1]>box[3] or box[0]<block[0] or box[1]<block[1] or box[2]>block[2] or box[3]>block[3]
            or box[0]<media[0] or box[1]<media[1] or box[2]>media[2] or box[3]>media[3]):
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
    union=(min(box[0] for box in boxes),min(box[1] for box in boxes),max(box[2] for box in boxes),max(box[3] for box in boxes))
    if any(not math.isclose(actual,expected,rel_tol=0,abs_tol=1e-4) for actual,expected in zip(union,block)):
        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')


def validate_source_mapping(mapping: SourceMapping, text: str, raw: str | None) -> None:
    if (type(mapping.start) is not int or type(mapping.end) is not int or
        not 0<=mapping.start<=mapping.end<=len(text)):
        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
    normalized=text[mapping.start:mapping.end]
    if mapping.transformation=='separator':
        if (mapping.span_id is not None or mapping.source_start is not None or mapping.source_end is not None or
            mapping.start==mapping.end or not normalized.isspace()):
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
        return
    if (raw is None or mapping.span_id is None or type(mapping.source_start) is not int or
        type(mapping.source_end) is not int or not 0<=mapping.source_start<mapping.source_end<=len(raw)):
        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
    original=raw[mapping.source_start:mapping.source_end]
    valid=(mapping.transformation=='identity' and original==normalized or
        mapping.transformation=='whitespace' and original.isspace() and normalized==' ' or
        mapping.transformation=='ligature' and len(original)==1 and LIGATURES.get(original)==normalized or
        mapping.transformation=='dehyphenation' and original=='-' and mapping.start==mapping.end)
    if not valid:
        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')


def resolve_range(conn: psycopg.Connection, scope: DocumentScope, chunk_id: UUID, start: int, end: int) -> tuple[EvidenceLocation, ...]:
    """Resolve explicit code-point offsets; never fuzzy-search or trust index payloads."""
    from .chunking import chunk_checksum

    with short_transaction(conn):
        chunk=conn.execute('''SELECT profile_hash,section_id,text,checksum FROM document_chunks
            WHERE id=%s AND owner_id=%s AND paper_id=%s AND document_version_id=%s''',
            (chunk_id,scope.owner_id,scope.paper_id,scope.document_version_id)).fetchone()
        if chunk is None:
            raise APIError(404,'RESOURCE_NOT_FOUND','The requested resource was not found.')
        profile_hash,section_id,text,checksum=chunk
        if type(start) is not int or type(end) is not int or not 0<=start<end<=len(text):
            raise _unresolved()
        rows=conn.execute('''SELECT ordinal,chunk_start,chunk_end,span_id,source_start,source_end,transformation,metadata
            FROM chunk_span_mappings WHERE chunk_id=%s AND owner_id=%s AND paper_id=%s AND document_version_id=%s
            ORDER BY ordinal LIMIT %s''',(chunk_id,scope.owner_id,scope.paper_id,scope.document_version_id,2*len(text)+2)).fetchall()
        ids=list({row[3] for row in rows if row[3] is not None})
        sources=conn.execute('''SELECT s.id,s.raw_text,s.boxes,p.page_index,b.box,p.media_box,b.section_id,b.excluded
            FROM document_spans s JOIN document_blocks b ON b.id=s.block_id AND b.owner_id=s.owner_id
              AND b.document_version_id=s.document_version_id AND b.page_id=s.page_id
            JOIN document_pages p ON p.id=s.page_id AND p.owner_id=s.owner_id AND p.document_version_id=s.document_version_id
            WHERE s.owner_id=%s AND s.paper_id=%s AND s.document_version_id=%s AND s.id=ANY(%s)''',
            (scope.owner_id,scope.paper_id,scope.document_version_id,ids)).fetchall()
    source_by_id={row[0]:row[1:] for row in sources}
    mappings=[];cursor=0
    for ordinal,row in enumerate(rows):
        stored_ordinal,left,right,span_id,source_start,source_end,transformation,metadata=row
        if stored_ordinal!=ordinal or metadata!={} or left<0 or right<left or right>len(text):
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
        mapping=SourceMapping(left,right,span_id,source_start,source_end,transformation,section_id)
        mappings.append(mapping)
        if right>left:
            if left!=cursor: raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            cursor=right
        elif left!=cursor or transformation!='dehyphenation':
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
        if transformation=='separator':
            validate_source_mapping(mapping,text,None)
            continue
        if span_id not in source_by_id:
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
        raw,boxes,page_index,block,media,source_section,excluded=source_by_id[span_id]
        if source_section!=section_id or excluded:
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
        validate_source_mapping(mapping,text,raw)
    if cursor!=len(text) or chunk_checksum(scope,bytes(profile_hash),section_id,text,tuple(mappings))!=bytes(checksum):
        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
    for raw,boxes,page_index,block,media,source_section,excluded in source_by_id.values():
        _valid_boxes(boxes,raw,block,media)
    locations=[]
    for mapping in mappings:
        if mapping.transformation=='separator': continue
        left=max(start,mapping.start);right=min(end,mapping.end)
        deletion=mapping.start==mapping.end and start<mapping.start<end
        if left>=right and not deletion: continue
        raw,boxes,page_index,*_=source_by_id[mapping.span_id]
        source_start,source_end=mapping.source_start,mapping.source_end
        if mapping.transformation=='identity':
            source_start+=left-mapping.start;source_end=mapping.source_start+right-mapping.start
        elif not deletion and (left!=mapping.start or right!=mapping.end):
            raise _unresolved()
        location=EvidenceLocation(mapping.span_id,page_index,source_start,source_end,raw[source_start:source_end],tuple(tuple(box) for box in boxes[source_start:source_end]))
        if locations and locations[-1].span_id==location.span_id and locations[-1].source_end==source_start:
            old=locations[-1]
            locations[-1]=EvidenceLocation(old.span_id,old.page_index,old.source_start,source_end,old.quote+location.quote,old.boxes+location.boxes)
        else:
            locations.append(location)
    if not locations: raise _unresolved()
    return tuple(locations)
