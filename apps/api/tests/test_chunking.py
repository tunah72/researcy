from dataclasses import replace
from uuid import uuid4

import pytest

from researcy.documents.chunking import chunk_section, iter_sections
from researcy.documents.normalize import normalize_records
from researcy.ingestion.models import DocumentScope, ProcessingProfile
from test_document_provenance import source_lines


def chunks_for(pages,profile):
    scope=DocumentScope(uuid4(),uuid4(),uuid4())
    records=normalize_records(source_lines(pages),profile,scope=scope)
    return [chunk for section in iter_sections(records) for chunk in chunk_section(section,profile)]


def test_oversized_paragraphs_advance_without_losing_unicode_text():
    profile=ProcessingProfile(chunk_target=100,chunk_maximum=160,chunk_overlap=25)
    text=''.join(f'Observation {index} 😀. ' for index in range(120))
    chunks=chunks_for([[(text,600,0,'text')]],profile)
    assert all(len(chunk.text)<=160 for chunk in chunks)
    assert ''.join(chunk.text[chunk.overlap_characters:] for chunk in chunks)==text
    assert all(chunk.overlap_characters<len(chunk.text) for chunk in chunks)
    assert all(chunk.overlap_characters<=25 for chunk in chunks)
    for chunk in chunks:
        intervals=[(mapping.start,mapping.end) for mapping in chunk.source_mappings if mapping.end>mapping.start]
        assert intervals[0][0]==0 and intervals[-1][1]==len(chunk.text)
        assert all(left[1]==right[0] for left,right in zip(intervals,intervals[1:]))


def test_chunking_never_crosses_sections_or_duplicates_canonical_source():
    profile=ProcessingProfile(chunk_target=80,chunk_maximum=120,chunk_overlap=20)
    pages=[[('1 Methods',700,0,'heading'),('Measured observations. '*20,670,1,'text'),
        ('2 Results',500,2,'heading'),('Observed outcomes. '*20,470,3,'text')]]
    chunks=chunks_for(pages,profile)
    assert len({chunk.section_id for chunk in chunks})==2
    by_section={}
    for chunk in chunks:
        assert {mapping.section_id for mapping in chunk.source_mappings}=={chunk.section_id}
        by_section.setdefault(chunk.section_id,[]).append(chunk.text[chunk.overlap_characters:])
    assert {''.join(values) for values in by_section.values()}=={'1 Methods\n\n'+'Measured observations. '*20,'2 Results\n\n'+'Observed outcomes. '*20}
    assert len({mapping.span_id for chunk in chunks for mapping in chunk.source_mappings if mapping.span_id})==4


def test_mapping_and_checksum_change_with_source_identity():
    profile=ProcessingProfile();scope=DocumentScope(uuid4(),uuid4(),uuid4())
    pages=[[('Identical source text.',600,0,'text')]]
    def extract(selected):
        records=normalize_records(source_lines(pages),profile,scope=selected)
        return [chunk for section in iter_sections(records) for chunk in chunk_section(section,profile)]
    first=extract(scope);replay=extract(scope)
    assert first==replay
    foreign=extract(replace(scope,document_version_id=uuid4()))
    assert first[0].id!=foreign[0].id and first[0].checksum!=foreign[0].checksum


def test_chunk_limit_persists_an_honest_terminal_resource_failure(queued_job,job_connections):
    from researcy.ingestion.jobs import claim_due,seal_profile,record_failure
    from researcy.ingestion.models import StageFailure

    scope,job=queued_job;conn,_=job_connections
    lease=claim_due(conn,'chunk-limit-test')
    profile=seal_profile(conn,lease,ProcessingProfile(chunk_target=20,chunk_maximum=30,chunk_overlap=0,max_chunks=1))
    records=normalize_records(source_lines([[('A'*80,600,0,'text')]]),profile,scope=scope)
    with pytest.raises(StageFailure) as exc:
        for section in iter_sections(records):
            list(chunk_section(section,profile))
    record_failure(conn,lease,exc.value)
    observed=conn.execute('SELECT status,error_code,failure_kind,retryable FROM ingestion_jobs WHERE id=%s AND owner_id=%s',(job,scope.owner_id)).fetchone()
    assert observed==('failed','PROCESSING_RESOURCE_LIMIT','resource_limit',False)
