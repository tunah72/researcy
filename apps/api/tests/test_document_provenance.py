from uuid import uuid4

import pytest

from researcy.documents.models import PageRecord, BlockRecord, SpanRecord
from researcy.documents.normalize import normalize_records
from researcy.documents.provenance import resolve_range
from researcy.ingestion.models import DocumentScope, ProcessingProfile


def source_lines(pages):
    ordinal=0
    for index,lines in enumerate(pages):
        yield PageRecord(index,(0,0,600,800),(0,0,600,800),0,600,800,(1,0,0,-1,0,800))
        for text,y,group,role in lines:
            boxes=tuple((40+position*5,y,45+position*5,y+10) for position in range(len(text)))
            yield BlockRecord(index,ordinal,(40,y,40+len(text)*5,y+10),role,12,role=='heading',group)
            yield SpanRecord(index,ordinal,ordinal,text,boxes)
            ordinal+=1


def canonical(pages,scope=None):
    scope=scope or DocumentScope(uuid4(),uuid4(),uuid4())
    return list(normalize_records(source_lines(pages),ProcessingProfile(),scope=scope))


def test_normalization_preserves_unicode_source_and_explicit_deletion():
    records=canonical([[('An  efﬁcient hy-',650,0,'text'),('phenated\tresult 😀.',630,0,'text')]])
    spans=[record for record in records if record.kind=='span']
    assert [span.raw_text for span in spans]==['An  efﬁcient hy-','phenated\tresult 😀.']
    assert ''.join(span.separator_before+span.normalized_text for span in spans)=='An efficient hyphenated result 😀.'
    first=spans[0]
    ligature=next(mapping for mapping in first.mappings if mapping.transformation=='ligature')
    assert first.raw_text[ligature.source_start:ligature.source_end]=='ﬁ'
    assert first.normalized_text[ligature.start:ligature.end]=='fi'
    deletion=next(mapping for mapping in first.mappings if mapping.transformation=='dehyphenation')
    assert deletion.start==deletion.end and first.raw_text[deletion.source_start:deletion.source_end]=='-'
    assert len(spans[1].character_boxes)==len(spans[1].raw_text)


def test_margin_repetition_keeps_source_and_never_removes_body_repetition():
    pages=[[('Journal 2026',770,0,'text'),('Body repeats',600,1,'text'),(str(index+1),20,2,'text')] for index in range(5)]
    records=canonical(pages)
    blocks=[record for record in records if record.kind=='block']
    spans={record.block_id:record for record in records if record.kind=='span'}
    removed=[spans[block.id].raw_text for block in blocks if block.excluded]
    retained=[spans[block.id].raw_text for block in blocks if not block.excluded]
    assert removed==[value for index in range(5) for value in ('Journal 2026',str(index+1))]
    assert retained==['Body repeats']*5
    assert len(spans)==15


def test_two_page_margin_coincidence_is_not_removed():
    records=canonical([[('Title',770,0,'text')],[('Title',770,0,'text')]])
    assert [record.excluded for record in records if record.kind=='block']==[False,False]


def test_sections_and_ids_are_scoped_deterministic_and_do_not_fabricate_titles():
    pages=[[('Unknown preface',650,0,'text'),('1 Methods',600,1,'heading'),('Measured body',580,2,'text')]]
    scope=DocumentScope(uuid4(),uuid4(),uuid4())
    first=canonical(pages,scope);replay=canonical(pages,scope)
    assert first==replay
    sections=[record for record in first if record.kind=='section']
    assert [section.title for section in sections]==[None,'1 Methods']
    foreign=canonical(pages,DocumentScope(uuid4(),scope.paper_id,scope.document_version_id))
    assert {record.id for record in first}.isdisjoint(record.id for record in foreign)


def test_dehyphenation_does_not_join_distinct_paragraphs():
    records=canonical([[('Preserved-',650,0,'text'),('another paragraph',620,1,'text')]])
    spans=[record for record in records if record.kind=='span']
    assert spans[0].normalized_text=='Preserved-'
    assert spans[1].separator_before=='\n\n'
    assert not any(mapping.transformation=='dehyphenation' for span in spans for mapping in span.mappings)


@pytest.mark.parametrize("page_count,excluded",[(5,True),(6,False)])
def test_margin_repetition_requires_the_document_fraction(page_count,excluded):
    pages=[[(('Repeated' if index<3 else 'Unique '+str(index)),770,0,'text'),
        ('Body',600,1,'text')] for index in range(page_count)]
    records=canonical(pages)
    blocks=[record for record in records if record.kind=='block']
    spans={record.block_id:record for record in records if record.kind=='span'}
    assert [block.excluded for block in blocks if spans[block.id].raw_text=='Repeated']==[excluded]*3



@pytest.fixture
def mapped_document(queued_job,job_connections):
    from researcy.documents.chunking import chunk_section,iter_sections
    from researcy.documents.repository import write_canonical_batch,write_chunk_batch
    from researcy.ingestion.jobs import claim_due,seal_profile

    scope,_=queued_job;conn,_=job_connections;lease=claim_due(conn,'provenance-test')
    profile=seal_profile(conn,lease,ProcessingProfile())
    records=list(normalize_records(source_lines([[('An  efﬁcient hy-',650,0,'text'),
        ('phenated result 😀.',630,0,'text')]]),profile,scope=scope))
    write_canonical_batch(conn,lease,records)
    chunks=[chunk for section in iter_sections(records) for chunk in chunk_section(section,profile)]
    write_chunk_batch(conn,lease,chunks)
    return conn,scope,chunks[0],records


def test_resolved_normalization_returns_verbatim_source_characters_and_boxes(mapped_document):

    conn,scope,chunk,records=mapped_document
    start=chunk.text.index('efficient');end=chunk.text.index(' result')
    locations=resolve_range(conn,scope,chunk.id,start,end)
    assert [location.quote for location in locations]==['efﬁcient hy-','phenated']
    spans={record.id:record for record in records if record.kind=='span'}
    for location in locations:
        span=spans[location.span_id]
        assert location.quote==span.raw_text[location.source_start:location.source_end]
        assert location.boxes==span.character_boxes[location.source_start:location.source_end]
        assert location.page_index==0


def test_partial_ligature_and_foreign_version_cannot_resolve(mapped_document):
    from researcy.errors import APIError

    conn,scope,chunk,_=mapped_document;start=chunk.text.index('fi')
    with pytest.raises(APIError) as exc:
        resolve_range(conn,scope,chunk.id,start,start+1)
    assert exc.value.code=='EVIDENCE_UNRESOLVED'
    foreign=DocumentScope(scope.owner_id,scope.paper_id,uuid4())
    with pytest.raises(APIError) as foreign_error:
        resolve_range(conn,foreign,chunk.id,0,1)
    with pytest.raises(APIError) as missing_error:
        resolve_range(conn,scope,uuid4(),0,1)
    assert (foreign_error.value.status_code,foreign_error.value.code,foreign_error.value.message)==(
        missing_error.value.status_code,missing_error.value.code,missing_error.value.message)


@pytest.mark.parametrize("corruption",["missing-mapping","wrong-source-box"])
def test_inconsistent_mapping_or_source_geometry_fails_closed(mapped_document,corruption):
    from psycopg.types.json import Jsonb
    from researcy.ingestion.models import StageFailure

    conn,scope,chunk,records=mapped_document
    # Deliberately bypass immutability only inside this disposable test database.
    if corruption=='missing-mapping':
        conn.execute('ALTER TABLE chunk_span_mappings DISABLE TRIGGER trg_chunk_span_mappings_immutable')
        conn.execute('DELETE FROM chunk_span_mappings WHERE chunk_id=%s AND ordinal=0',(chunk.id,))
    else:
        span=next(record for record in records if record.kind=='span')
        boxes=[list(box) for box in span.character_boxes];boxes[0]=[0,0,1,1]
        conn.execute('ALTER TABLE document_spans DISABLE TRIGGER trg_document_spans_immutable')
        conn.execute('UPDATE document_spans SET boxes=%s WHERE id=%s',(Jsonb(boxes),span.id))
    conn.commit()
    with pytest.raises(StageFailure) as exc:
        resolve_range(conn,scope,chunk.id,0,len(chunk.text))
    assert exc.value.retryable is False


def test_heading_cues_do_not_discard_original_mapped_source_text():
    records=canonical([[('Bold label and substantive body.',650,0,'heading')]])
    span=next(record for record in records if record.kind=='span')
    assert span.retrieval and span.normalized_text==span.raw_text
    assert span.mappings[0].span_id==span.id


def test_separate_number_and_typographic_title_share_one_source_section():
    page=PageRecord(0,(0,0,600,800),(0,0,600,800),0,600,800,(1,0,0,-1,0,800))
    number_boxes=tuple((40+i*5,650,45+i*5,660) for i in range(5))
    title_boxes=tuple((80+i*5,650,85+i*5,660) for i in range(7))
    records=[page,BlockRecord(0,0,(40,650,65,660),'text',12,True,0),
        SpanRecord(0,0,0,'3.2.1',number_boxes),
        BlockRecord(0,1,(80,650,115,660),'heading',12,True,0),
        SpanRecord(0,1,1,'Methods',title_boxes)]
    scope=DocumentScope(uuid4(),uuid4(),uuid4())
    canonical_records=list(normalize_records(iter(records),ProcessingProfile(),scope=scope))
    sections=[record for record in canonical_records if record.kind=='section']
    spans=[record for record in canonical_records if record.kind=='span']
    assert [section.title for section in sections]==[None,'3.2.1 Methods']
    assert {span.section_id for span in spans}=={sections[-1].id}
    assert ''.join(span.raw_text for span in spans)=='3.2.1Methods'


def test_normalization_bound_rejects_the_document_before_emitting_partial_source():
    from dataclasses import replace
    from researcy.ingestion.models import StageFailure

    profile=replace(ProcessingProfile(),max_characters=5)
    scope=DocumentScope(uuid4(),uuid4(),uuid4())
    records=normalize_records(source_lines([[('Too long',650,0,'text')]]),profile,scope=scope)
    with pytest.raises(StageFailure) as exc:
        next(records)
    assert exc.value.code=='PDF_PARSE_RESOURCE_LIMIT' and exc.value.retryable is False
