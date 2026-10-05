from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from test_conversations import reader_source,reader_client


def test_quote_proposals_cannot_supply_page_scope_or_geometry():
    from researcy.citations.models import ProposedCitation
    with pytest.raises(ValidationError):
        ProposedCitation(source_ref='S1',evidence_quote='source',page=1,boxes=[[0,0,1,1]])


def test_exact_raw_quote_resolves_original_page_and_character_boxes(reader_source,monkeypatch):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import make_evidence_catalog,resolve_proposal
    from researcy.retrieval.repository import hydrate_hits
    source = reader_source
    from researcy.retrieval import repository
    # This test uses actual temporary PostgreSQL, not index-supplied text.
    monkeypatch.setattr(repository,'get_conn',source['get_conn'])
    hits = hydrate_hits(source['document'],[(source['chunks'][0].id,1.)])
    catalog = make_evidence_catalog(tuple(hits))
    quote = 'exact source'
    resolved = resolve_proposal(source['conn'],source['document'],catalog,ProposedCitation(source_ref='S1',evidence_quote=quote))
    span_id,raw,boxes = source['conn'].execute('''SELECT id,raw_text,boxes FROM document_spans
        WHERE owner_id=%s AND document_version_id=%s ORDER BY ordinal LIMIT 1''',
        (source['scope'].owner_id,source['scope'].document_version_id)).fetchone()
    source['conn'].commit()
    start = raw.index(quote)
    assert len(resolved)==1
    assert resolved[0].evidence_quote==quote
    assert resolved[0].document_version==source['scope'].document_version_id and resolved[0].page==1
    assert resolved[0].boxes==tuple(tuple(box) for box in boxes[start:start+len(quote)])
    assert resolved[0].raw_fragments[0].span_id==span_id


@pytest.mark.parametrize('quote',['fabricated text','Exact source','exact sourcE'])
def test_nonverbatim_quote_is_unresolved(reader_source,monkeypatch,quote):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import make_evidence_catalog,resolve_proposal
    from researcy.retrieval import repository
    from researcy.errors import APIError
    monkeypatch.setattr(repository,'get_conn',reader_source['get_conn'])
    hits = repository.hydrate_hits(reader_source['document'],[(reader_source['chunks'][0].id,1.)])
    with pytest.raises(APIError) as caught:
        resolve_proposal(reader_source['conn'],reader_source['document'],make_evidence_catalog(tuple(hits)),
            ProposedCitation(source_ref='S1',evidence_quote=quote))
    assert caught.value.code=='EVIDENCE_UNRESOLVED'


def test_catalog_cannot_grant_foreign_pinned_version(reader_source,monkeypatch):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import make_evidence_catalog,resolve_proposal
    from researcy.retrieval import repository
    from researcy.errors import APIError
    monkeypatch.setattr(repository,'get_conn',reader_source['get_conn'])
    hits = repository.hydrate_hits(reader_source['document'],[(reader_source['chunks'][0].id,1.)])
    document = replace(reader_source['document'],scope=replace(reader_source['scope'],document_version_id=uuid4()))
    with pytest.raises(APIError) as caught:
        resolve_proposal(reader_source['conn'],document,make_evidence_catalog(tuple(hits)),
            ProposedCitation(source_ref='S1',evidence_quote='exact source'))
    assert caught.value.code=='EVIDENCE_UNRESOLVED'


def test_citation_get_exposes_only_owned_completed_accepted_evidence(reader_source,reader_client,monkeypatch):
    from researcy.citations.models import ProposedCitation,StoredCitation
    from researcy.citations.resolver import make_evidence_catalog,resolve_proposal
    from researcy.conversations.repository import create_owned_conversation,reserve_run,finish_run
    from researcy.retrieval import repository
    from test_library import _authenticate
    source,conn = reader_source,reader_source['conn']
    scope = source['scope']
    monkeypatch.setattr(repository,'get_conn',source['get_conn'])
    hit = repository.hydrate_hits(source['document'],[(source['chunks'][0].id,1.)])[0]
    citation = resolve_proposal(conn,source['document'],make_evidence_catalog((hit,)),
        ProposedCitation(source_ref='S1',evidence_quote='exact source'))[0]
    conversation = create_owned_conversation(conn,scope.owner_id,source['document'])
    run = reserve_run(conn,scope.owner_id,conversation.id,uuid4(),'Which exact source?',uuid4())
    finish_run(conn,run,['A controlled source statement.'],(StoredCitation(citation,0,citation.raw_fragments),),{})
    path = f'/api/citations/{citation.citation_id}'
    response = reader_client.get(path)
    assert response.status_code==200
    assert response.json()['citation']==citation.model_dump(mode='json')
    assert 'raw_fragments' not in response.json()['citation']
    conn.execute("UPDATE citations SET state='provisional' WHERE owner_id=%s AND id=%s",(scope.owner_id,citation.citation_id))
    conn.commit()
    assert reader_client.get(path).status_code==404
    owner_b = conn.execute('INSERT INTO users(issuer,sub) VALUES(%s,%s) RETURNING id',
        ('https://accounts.google.com',str(uuid4()))).fetchone()[0]
    conn.commit()
    _authenticate(reader_client,conn,owner_b)
    assert reader_client.get(path).status_code==reader_client.get(f'/api/citations/{uuid4()}').status_code==404


def test_research_reader_uuid_collision_fails_closed(research_sources):
    from test_research_repository import reserve
    from researcy.research.repository import finish_research
    from researcy.conversations.repository import create_owned_conversation,reserve_run,finish_run
    from researcy.citations.repository import get_owned_citation
    from researcy.errors import APIError
    f=research_sources;conn=f['conn'];run=reserve(f)
    ideas,citations=f['resolved_idea_for'](f['paper_ids'][0])
    finish_research(conn,run,ideas,citations,{})
    conversation=create_owned_conversation(conn,f['owner_id'],f['publications'][0]['document'])
    reader=reserve_run(conn,f['owner_id'],conversation.id,uuid4(),'What is the exact evidence?',uuid4())
    finish_run(conn,reader,['The source reports experimental limitations.'],citations,{})
    with pytest.raises(APIError) as error:
        get_owned_citation(conn,f['owner_id'],citations[0].citation.citation_id)
    assert error.value.status_code==404



@pytest.fixture
def mapped_quote_source(queued_job,job_connections,request):
    from test_document_provenance import source_lines
    from dataclasses import replace
    from researcy.documents.normalize import normalize_records
    from researcy.documents.chunking import iter_sections,chunk_section
    from researcy.documents.repository import write_canonical_batch,write_chunk_batch
    from researcy.documents.provenance import resolve_range
    from researcy.ingestion.models import ProcessingProfile
    from researcy.ingestion.jobs import claim_due,seal_profile
    from researcy.retrieval.repository import ReadyDocument,EvidenceHit
    from researcy.citations.resolver import make_evidence_catalog
    scope,_ = queued_job
    conn,_ = job_connections
    profile = ProcessingProfile()
    lease = claim_due(conn,'citation-mapping-test')
    seal_profile(conn,lease,profile)
    source_records = list(source_lines(request.param))
    width = max(600,max(len(text)*5+40 for page in request.param for text,_,_,_ in page))
    source_records = [replace(record,media_box=(0,0,width,800),crop_box=(0,0,width,800),width=width)
        if record.kind=='page' else record for record in source_records]
    records = list(normalize_records(source_records,profile,scope=scope))
    write_canonical_batch(conn,lease,records)
    chunks = [chunk for section in iter_sections(records) for chunk in chunk_section(section,profile)]
    write_chunk_batch(conn,lease,chunks)
    document = ReadyDocument(scope,profile,'not-a-runtime-publication',profile.profile_hash,frozenset(chunk.id for chunk in chunks))
    hits = tuple(EvidenceHit(scope,chunk.id,chunk.section_id,chunk.text,1.,
        resolve_range(conn,scope,chunk.id,0,len(chunk.text))) for chunk in chunks)
    return conn,document,make_evidence_catalog(hits),records


@pytest.mark.parametrize('mapped_quote_source',[
    [[('An  efﬁcient hy-',650,0,'text'),('phenated result 😀.',630,0,'text')]]
],indirect=True)
def test_raw_ligature_dehyphenation_and_whitespace_preserve_original_characters(mapped_quote_source):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import resolve_proposal
    from researcy.errors import APIError
    conn,document,catalog,records = mapped_quote_source
    resolved = resolve_proposal(conn,document,catalog,ProposedCitation(source_ref='S1',evidence_quote='efﬁcient hy-phenated'))
    assert resolved[0].evidence_quote=='efﬁcient hy-phenated'
    spans = [record for record in records if record.kind=='span']
    expected = spans[0].character_boxes[4:]+spans[1].character_boxes[:8]
    assert resolved[0].boxes==expected
    whitespace = resolve_proposal(conn,document,catalog,ProposedCitation(source_ref='S1',evidence_quote='An efﬁcient'))
    assert whitespace[0].evidence_quote=='An  efﬁcient'
    with pytest.raises(APIError):
        resolve_proposal(conn,document,catalog,ProposedCitation(source_ref='S1',evidence_quote='efficient'))


@pytest.mark.parametrize('mapped_quote_source',[
    [[('An \ufffd efﬁcient cafe\u0301 result 😀.',650,0,'text')]]
],indirect=True)
@pytest.mark.parametrize('escaped',[False,True])
def test_decoded_and_streamed_unicode_quotes_preserve_every_raw_character(mapped_quote_source,escaped):
    import json
    from researcy.agents.reader_parser import ClaimParser
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import resolve_proposal
    from researcy.errors import APIError
    from researcy.generation.models import decode_output,READER_INITIAL_OUTPUT
    conn,document,catalog,records = mapped_quote_source
    quote = 'An \ufffd efﬁcient cafe\u0301 result 😀.'
    raw = json.dumps({'next_action':'answer','claims':[{'text':'The recorded result is shown.',
        'citations':[{'source_ref':'S1','evidence_quote':quote}]}],'refusal':None},ensure_ascii=escaped).encode()
    action = decode_output(raw,READER_INITIAL_OUTPUT)
    parser = ClaimParser()
    claims = []
    for byte in raw:
        claims.extend(parser.feed(bytes((byte,))))
    parser.finish()
    assert action.claims[0].citations[0].evidence_quote=='An \ufffd efﬁcient cafe\u0301 result 😀.'
    assert claims[0].citations[0].evidence_quote=='An \ufffd efﬁcient cafe\u0301 result 😀.'
    resolved = resolve_proposal(conn,document,catalog,action.claims[0].citations[0])
    span = next(record for record in records if record.kind=='span')
    assert [(citation.page,citation.evidence_quote,citation.boxes) for citation in resolved]==[
        (1,'An \ufffd efﬁcient cafe\u0301 result 😀.',span.character_boxes)]
    with pytest.raises(APIError) as error:
        resolve_proposal(conn,document,catalog,
            ProposedCitation(source_ref='S1',evidence_quote='An  efﬁcient cafe\u0301 result 😀.'))
    assert error.value.code=='EVIDENCE_UNRESOLVED'


@pytest.mark.parametrize('mapped_quote_source',[
    [[('Same phrase and same phrase.',650,0,'text')]]
],indirect=True)
def test_repeated_raw_quote_is_ambiguous_not_first_match(mapped_quote_source):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import resolve_proposal
    from researcy.errors import APIError
    conn,document,catalog,_ = mapped_quote_source
    with pytest.raises(APIError) as caught:
        resolve_proposal(conn,document,catalog,ProposedCitation(source_ref='S1',evidence_quote='phrase'))
    assert caught.value.code=='EVIDENCE_UNRESOLVED'


@pytest.mark.parametrize('mapped_quote_source',[
    [[('cross ',650,0,'text')],[('page',650,0,'text')]]
],indirect=True)
def test_cross_page_quote_has_separate_exact_page_local_citations(mapped_quote_source):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import resolve_proposal
    conn,document,catalog,records = mapped_quote_source
    resolved = resolve_proposal(conn,document,catalog,ProposedCitation(source_ref='S1',evidence_quote='cross page'))
    assert [(citation.page,citation.evidence_quote) for citation in resolved]==[(1,'cross '),(2,'page')]
    spans = [record for record in records if record.kind=='span']
    assert [citation.boxes for citation in resolved]==[span.character_boxes for span in spans]
    assert resolved[0].citation_id!=resolved[1].citation_id


@pytest.mark.parametrize('mapped_quote_source',[
    [[('begin'+' '*2100+'end',650,0,'text')]]
],indirect=True)
def test_whitespace_equivalence_cannot_exceed_page_local_quote_limit(mapped_quote_source):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import resolve_proposal
    from researcy.errors import APIError
    conn,document,catalog,_ = mapped_quote_source
    with pytest.raises(APIError) as caught:
        resolve_proposal(conn,document,catalog,ProposedCitation(source_ref='S1',evidence_quote='begin end'))
    assert (caught.value.status_code,caught.value.code)==(422,'EVIDENCE_UNRESOLVED')


@pytest.mark.parametrize('mapped_quote_source',[
    [[('An efﬁcient hy-',650,0,'text'),('phenated result.',630,0,'text')]]
],indirect=True)
@pytest.mark.parametrize('quote',['hy-','-phenated','-','phenated'])
def test_exact_quote_can_select_or_exclude_boundary_dehyphenation(mapped_quote_source,quote):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import resolve_proposal
    conn,document,catalog,records = mapped_quote_source
    resolved = resolve_proposal(conn,document,catalog,ProposedCitation(source_ref='S1',evidence_quote=quote))
    spans = [record for record in records if record.kind=='span']
    expected = {
        'hy-':spans[0].character_boxes[-3:],
        '-phenated':spans[0].character_boxes[-1:]+spans[1].character_boxes[:8],
        '-':spans[0].character_boxes[-1:],
        'phenated':spans[1].character_boxes[:8],
    }
    assert [(citation.page,citation.evidence_quote,citation.boxes) for citation in resolved]==[(1,quote,expected[quote])]


@pytest.mark.parametrize('mapped_quote_source',[
    [[('The method supports',650,0,'text'),('parallel measured evaluation.',630,0,'text')]]
],indirect=True)
def test_normalized_span_separator_is_not_raw_evidence(mapped_quote_source):
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import resolve_proposal
    from researcy.errors import APIError
    conn,document,catalog,records = mapped_quote_source
    assert catalog['S1'].hit.text=='The method supports parallel measured evaluation.'
    assert catalog['S1'].raw_excerpt=='The method supportsparallel measured evaluation.'
    resolved = resolve_proposal(conn,document,catalog,
        ProposedCitation(source_ref='S1',evidence_quote='supportsparallel'))
    spans = [record for record in records if record.kind=='span']
    assert [(citation.page,citation.evidence_quote,citation.boxes) for citation in resolved]==[
        (1,'supportsparallel',spans[0].character_boxes[-8:]+spans[1].character_boxes[:8])]
    with pytest.raises(APIError) as error:
        resolve_proposal(conn,document,catalog,
            ProposedCitation(source_ref='S1',evidence_quote='supports parallel'))
    assert error.value.code=='EVIDENCE_UNRESOLVED'


@pytest.mark.parametrize('mapped_quote_source',[
    [[('Exact source.',650,0,'text')]]
],indirect=True)
@pytest.mark.parametrize('corruption',['missing-mapping','nonfinite-box','out-of-page-box'])
def test_corrupted_canonical_quote_source_never_returns_a_citation(mapped_quote_source,corruption):
    from psycopg.types.json import Jsonb
    from researcy.citations.models import ProposedCitation
    from researcy.citations.resolver import resolve_proposal
    from researcy.errors import APIError
    conn,document,catalog,records = mapped_quote_source
    if corruption=='missing-mapping':
        conn.execute('ALTER TABLE chunk_span_mappings DISABLE TRIGGER trg_chunk_span_mappings_immutable')
        conn.execute('DELETE FROM chunk_span_mappings WHERE chunk_id=%s AND ordinal=0',(catalog['S1'].hit.chunk_id,))
    else:
        span = next(record for record in records if record.kind=='span')
        boxes = [list(box) for box in span.character_boxes]
        boxes[0][0] = 'NaN' if corruption=='nonfinite-box' else -1
        conn.execute('ALTER TABLE document_spans DISABLE TRIGGER trg_document_spans_immutable')
        if corruption=='nonfinite-box':
            # Corruption only: production PostgreSQL already rejects this value.
            conn.execute('ALTER TABLE document_spans DROP CONSTRAINT document_spans_check')
        conn.execute('UPDATE document_spans SET boxes=%s WHERE id=%s',(Jsonb(boxes),span.id))
    conn.commit()
    with pytest.raises(APIError) as caught:
        resolve_proposal(conn,document,catalog,ProposedCitation(source_ref='S1',evidence_quote='Exact source.'))
    assert (caught.value.status_code,caught.value.code)==(422,'EVIDENCE_UNRESOLVED')
