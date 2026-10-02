from dataclasses import dataclass
from uuid import uuid4

import psycopg

from researcy.documents.canonical import EvidenceLocation
from researcy.documents.provenance import resolve_range
from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.ingestion.models import IntegrityFailure
from researcy.retrieval.repository import ReadyDocument,EvidenceHit
from .models import ProposedCitation,ResolvedCitation


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    hit: EvidenceHit
    raw_excerpt: str


EvidenceCatalog = dict[str,CatalogEntry]


def _unresolved() -> APIError:
    return APIError(422,'EVIDENCE_UNRESOLVED','The answer evidence cannot be resolved exactly.')


def make_evidence_catalog(hits: tuple[EvidenceHit,...]) -> EvidenceCatalog:
    if len(hits)>5 or sum(len(hit.text) for hit in hits)>12000:
        raise _unresolved()
    catalog = {}
    raw_size = 0
    scope = hits[0].scope if hits else None
    for ordinal,hit in enumerate(hits,1):
        if hit.scope!=scope or not hit.locations:
            raise _unresolved()
        raw = ''.join(location.quote for location in hit.locations)
        raw_size += len(raw)
        if not raw or raw_size>12000:
            raise _unresolved()
        catalog[f'S{ordinal}'] = CatalogEntry(hit,raw)
    return catalog


def _collapse_whitespace(text: str) -> tuple[str,list[tuple[int,int]]]:
    parts,intervals = [],[]
    cursor = 0
    while cursor<len(text):
        end = cursor+1
        if text[cursor].isspace():
            while end<len(text) and text[end].isspace():
                end += 1
            parts.append(' ')
        else:
            parts.append(text[cursor])
        intervals.append((cursor,end))
        cursor = end
    return ''.join(parts),intervals


def _unique_match(raw: str,quote: str) -> tuple[int,int]:
    # Only existing whitespace runs are equivalent; never insert source separators.
    collapsed,intervals = _collapse_whitespace(raw)
    requested,_ = _collapse_whitespace(quote)
    first = collapsed.find(requested)
    if first<0 or collapsed.find(requested,first+1)>=0:
        raise _unresolved()
    return intervals[first][0],intervals[first+len(requested)-1][1]


def _selected_fragments(locations: tuple[EvidenceLocation,...],start: int,end: int) -> tuple[EvidenceLocation,...]:
    selected,cursor = [],0
    for fragment in locations:
        left,right = max(start,cursor),min(end,cursor+len(fragment.quote))
        if left<right:
            offset = left-cursor
            selected.append(EvidenceLocation(fragment.span_id,fragment.page_index,fragment.source_start+offset,
                fragment.source_start+right-cursor,fragment.quote[offset:right-cursor],fragment.boxes[offset:right-cursor]))
        cursor += len(fragment.quote)
    if not selected:
        raise _unresolved()
    return tuple(selected)


def _validate_selection(conn: psycopg.Connection,entry: CatalogEntry,fragments: tuple[EvidenceLocation,...]) -> None:
    scope = entry.hit.scope
    with short_transaction(conn):
        mappings = conn.execute('''SELECT chunk_start,chunk_end,span_id,source_start,source_end,transformation
            FROM chunk_span_mappings WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND chunk_id=%s
            ORDER BY ordinal LIMIT %s''',
            (scope.owner_id,scope.paper_id,scope.document_version_id,entry.hit.chunk_id,2*len(entry.hit.text)+2)).fetchall()
    for fragment in fragments:
        covered = fragment.source_start
        for left,right,span_id,source_start,source_end,transformation in mappings:
            if span_id!=fragment.span_id or source_start is None:
                continue
            overlap_start,overlap_end = max(fragment.source_start,source_start),min(fragment.source_end,source_end)
            if overlap_start>=overlap_end:
                continue
            if overlap_start!=covered:
                raise _unresolved()
            covered = overlap_end
            if transformation=='identity':
                continue
            elif transformation in ('whitespace','ligature','dehyphenation'):
                if overlap_start!=source_start or overlap_end!=source_end:
                    raise _unresolved()
            else:
                raise _unresolved()
        if covered!=fragment.source_end:
            raise _unresolved()


def resolve_proposal(conn: psycopg.Connection,document: ReadyDocument,catalog: EvidenceCatalog,
    proposal: ProposedCitation) -> tuple[ResolvedCitation,...]:
    entry = catalog.get(proposal.source_ref)
    if entry is None or entry.hit.scope!=document.scope or entry.hit.chunk_id not in document.chunk_ids:
        raise _unresolved()
    start,end = _unique_match(entry.raw_excerpt,proposal.evidence_quote)
    selected = _selected_fragments(entry.hit.locations,start,end)
    _validate_selection(conn,entry,selected)
    try:
        # Validate the whole immutable mapping, then select raw offsets. A normalized
        # interval cannot represent a deleted hyphen selected at a quote boundary.
        locations = resolve_range(conn,document.scope,entry.hit.chunk_id,0,len(entry.hit.text))
        authoritative = _selected_fragments(locations,start,end)
    except (IntegrityFailure,APIError):
        raise _unresolved() from None
    if authoritative!=selected:
        raise _unresolved()
    with short_transaction(conn):
        section = conn.execute('''SELECT title FROM document_sections
            WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND id=%s''',
            (document.scope.owner_id,document.scope.paper_id,document.scope.document_version_id,entry.hit.section_id)).fetchone()
    if section is None:
        raise _unresolved()
    groups: list[list[EvidenceLocation]] = []
    for fragment in authoritative:
        if not groups or groups[-1][0].page_index!=fragment.page_index:
            groups.append([])
        groups[-1].append(fragment)
    citations = []
    for fragments in groups:
        quote = ''.join(fragment.quote for fragment in fragments)
        if len(quote)>2000:
            raise _unresolved()
        citation = ResolvedCitation(citation_id=uuid4(),paper_id=document.scope.paper_id,
            document_version=document.scope.document_version_id,source_ref=proposal.source_ref,evidence_quote=quote,
            page=fragments[0].page_index+1,boxes=tuple(box for fragment in fragments for box in fragment.boxes),section=section[0])
        citation._raw_fragments = tuple(fragments)
        citations.append(citation)
    return tuple(citations)
