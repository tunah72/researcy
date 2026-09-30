from dataclasses import replace
import hashlib
import json
import re
from typing import Iterable, Iterator
from uuid import UUID

from researcy.ingestion.models import DocumentScope, ProcessingProfile, IntegrityFailure, StageFailure, deterministic_id
from .canonical import CanonicalRecord, CanonicalSpan, SourceMapping, SectionContent, ChunkRecord


_SENTENCE=re.compile(r'[^\n.!?]+[.!?](?:["\'\)\]]*)(?:\s+|$)')


def chunk_checksum(scope: DocumentScope, profile_hash: bytes, section_id: UUID, text: str,
    mappings: Iterable[SourceMapping]) -> bytes:
    payload={'scope':[str(scope.owner_id),str(scope.paper_id),str(scope.document_version_id)],
        'profile_hash':profile_hash.hex(),'section_id':str(section_id),'text':text,
        'mappings':[[mapping.start,mapping.end,str(mapping.span_id) if mapping.span_id else None,
            mapping.source_start,mapping.source_end,mapping.transformation,str(mapping.section_id)] for mapping in mappings]}
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()).digest()


def iter_sections(records: Iterable[CanonicalRecord]) -> Iterator[SectionContent]:
    """A section's spans must be consumed before requesting the next section."""
    source=iter(records);pending=None
    for record in source:
        if record.kind=='section':pending=record;break
    while pending is not None:
        section=pending;finished=False
        def spans():
            nonlocal pending,finished
            for record in source:
                if record.kind=='section':
                    pending=record;finished=True;return
                if record.kind=='span' and record.retrieval:
                    if record.section_id!=section.id or record.scope!=section.scope or record.profile_hash!=section.profile_hash:
                        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
                    yield record
            pending=None;finished=True
        stream=spans()
        yield SectionContent(section,stream)
        if not finished:
            if next(stream,None) is not None:
                raise ValueError('consume section spans before advancing sections')


def _pieces(spans: Iterable[CanonicalSpan], section):
    for span in spans:
        if not span.retrieval:continue
        if span.scope!=section.scope or span.section_id!=section.id or span.profile_hash!=section.profile_hash:
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
        if span.separator_before:
            yield span.separator_before,0,len(span.separator_before),SourceMapping(0,len(span.separator_before),None,None,None,'separator',section.id)
        cursor=0
        for mapping in span.mappings:
            if mapping.start!=cursor or mapping.end<mapping.start or mapping.end>len(span.normalized_text) or mapping.span_id!=span.id or mapping.section_id!=section.id:
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            if not 0<=mapping.source_start<mapping.source_end<=len(span.raw_text):
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            if mapping.start==mapping.end and mapping.transformation!='dehyphenation':
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            if mapping.transformation=='identity' and mapping.end-mapping.start!=mapping.source_end-mapping.source_start:
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            yield span.normalized_text,mapping.start,mapping.end,mapping
            cursor=mapping.end
        if cursor!=len(span.normalized_text):
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')


def _slice_mappings(mappings, left, right):
    result=[]
    for mapping in mappings:
        if mapping.start==mapping.end:
            if left<=mapping.start<=right:
                result.append(replace(mapping,start=mapping.start-left,end=mapping.end-left))
            continue
        start,end=max(left,mapping.start),min(right,mapping.end)
        if start>=end:continue
        if mapping.transformation in ('identity','separator'):
            source_start=mapping.source_start+start-mapping.start if mapping.span_id else None
            source_end=mapping.source_start+end-mapping.start if mapping.span_id else None
        else:
            if start!=mapping.start or end!=mapping.end:
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            source_start,source_end=mapping.source_start,mapping.source_end
        result.append(replace(mapping,start=start-left,end=end-left,source_start=source_start,source_end=source_end))
    return tuple(result)


def _mapped_cut(mappings,cut,maximum):
    for mapping in mappings:
        if mapping.start<cut<mapping.end and mapping.transformation not in ('identity','separator'):
            return mapping.start if mapping.start>0 else mapping.end if mapping.end<=maximum else 0
    return cut


def _cut(text,mappings,profile):
    target=min(profile.chunk_target,len(text));minimum=max(1,target//2)
    for candidates in ([match.end() for match in re.finditer(r'\n\n',text)],
        [match.end() for match in _SENTENCE.finditer(text)],
        [match.end() for match in re.finditer(r'\s+',text)]):
        before=[position for position in candidates if minimum<=position<=target]
        after=[position for position in candidates if target<position<=len(text)]
        candidate=max(before) if before else min(after) if after else None
        if candidate is not None:
            cut=_mapped_cut(mappings,candidate,len(text))
            if cut>0:return cut
    return _mapped_cut(mappings,target,len(text))


def _overlap_start(text,mappings,maximum):
    if maximum==0:return len(text)
    sentences=list(_SENTENCE.finditer(text))
    if not sentences or sentences[-1].end()!=len(text):return len(text)
    start=len(text)
    for sentence in reversed(sentences):
        candidate=sentence.start()
        if candidate<=0 or len(text)-candidate>maximum:break
        if start!=len(text) and sentence.end()!=start:break
        if _mapped_cut(mappings,candidate,len(text))!=candidate:break
        start=candidate
    return start


def chunk_section(section: SectionContent, profile: ProcessingProfile, *, start_ordinal: int=0) -> Iterator[ChunkRecord]:
    if type(start_ordinal) is not int or not 0<=start_ordinal<=profile.max_chunks or section.section.profile_hash!=profile.profile_hash:
        raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
    metadata=section.section;buffer='';mappings=[];ordinal=start_ordinal;overlap=0;new_characters=0
    def emit(cut):
        nonlocal buffer,mappings,ordinal,overlap,new_characters
        if cut<=overlap or cut>len(buffer):
            raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
        if ordinal>=profile.max_chunks:
            raise StageFailure('PROCESSING_RESOURCE_LIMIT','resource_limit',False)
        text=buffer[:cut];selected=_slice_mappings(mappings,0,cut)
        cursor=0
        for mapping in selected:
            if mapping.start!=cursor or mapping.end<mapping.start:
                raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
            cursor=mapping.end
        if cursor!=len(text):raise IntegrityFailure('PROCESSING_INTEGRITY_FAILURE')
        checksum=chunk_checksum(metadata.scope,profile.profile_hash,metadata.id,text,selected)
        chunk=ChunkRecord(deterministic_id(metadata.scope,profile.profile_hash,'chunk',f'{metadata.id}/{ordinal}/{checksum.hex()}'),
            metadata.scope,profile.profile_hash,metadata.id,ordinal,text,checksum,selected,overlap)
        ordinal+=1
        keep=_overlap_start(text,selected,profile.chunk_overlap)
        mappings=list(_slice_mappings(mappings,keep,len(buffer)))
        buffer=buffer[keep:];overlap=cut-keep;new_characters=len(buffer)-overlap
        return chunk
    for text,left,right,mapping in _pieces(section.spans,metadata):
        if left==right:
            mappings.append(replace(mapping,start=len(buffer),end=len(buffer)))
            continue
        consumed=0
        while left+consumed<right:
            capacity=profile.chunk_maximum-len(buffer)
            remaining=right-left-consumed
            if capacity==0 or (mapping.transformation not in ('identity','separator') and remaining>capacity):
                cut=_cut(buffer,mappings,profile)
                # Never emit only the preceding chunk's overlap.
                if cut<=overlap:cut=_mapped_cut(mappings,len(buffer),len(buffer))
                yield emit(cut);continue
            take=min(capacity,remaining)
            start=len(buffer);source_start=mapping.source_start;source_end=mapping.source_end
            if mapping.transformation=='identity':
                source_start+=consumed;source_end=source_start+take
            buffer+=text[left+consumed:left+consumed+take]
            mappings.append(replace(mapping,start=start,end=start+take,source_start=source_start,source_end=source_end))
            consumed+=take;new_characters+=take
    if new_characters:
        yield emit(len(buffer))
