from dataclasses import replace
from threading import Event
import time

import pytest

from researcy.errors import APIError


def selection(f,all_sources=False):
    from researcy.research.repository import load_selection
    return load_selection(f['conn'],f['owner_id'],f['paper_ids'][0],
        f['paper_ids'][1:4] if all_sources else (f['paper_ids'][1],))


def test_ref_catalog_binds_each_source_to_its_immutable_scope(research_sources):
    from researcy.research.evidence import retrieve_research_evidence
    f=research_sources;sources=selection(f,True)
    evidence=retrieve_research_evidence(sources,deadline=time.monotonic()+30,cancel=Event())
    assert list(evidence.catalog)==['P0:S1','P1:S1','P2:S1','P3:S1']
    expected_quotes={paper:f'Source {index} evaluates exact experimental evidence and limitations.'
        for index,paper in enumerate(f['paper_ids'][:4])}
    assert tuple(source.document.scope.paper_id for source in sources)==(
        f['paper_ids'][0],*sorted(f['paper_ids'][1:4],key=lambda paper:paper.int))
    for position,(ref,entry) in enumerate(evidence.catalog.items()):
        assert entry.hit.scope==sources[position].document.scope==evidence.documents_by_ref[ref].scope
        assert entry.raw_excerpt==expected_quotes[entry.hit.scope.paper_id]
        assert entry.hit.locations[0].page_index==0
        assert len(entry.hit.locations[0].boxes)==len(entry.raw_excerpt)


@pytest.mark.parametrize('field',['owner_id','paper_id','document_version_id'])
def test_outside_exact_tuple_hit_fails_closed(research_sources,monkeypatch,field):
    from uuid import uuid4
    from researcy.research.evidence import retrieve_research_evidence
    from researcy.retrieval import hybrid
    f=research_sources;sources=selection(f);hit=f['hits'][f['paper_ids'][0]][0]
    forged=replace(hit,scope=replace(hit.scope,**{field:uuid4()}))
    monkeypatch.setattr(hybrid,'retrieve_same_paper',lambda *args,**kwargs:(forged,))
    with pytest.raises(APIError):retrieve_research_evidence(sources,deadline=time.monotonic()+30,cancel=Event())


def test_missing_first_source_is_not_silently_filtered(research_sources,monkeypatch):
    from researcy.research.evidence import retrieve_research_evidence
    from researcy.retrieval import hybrid
    f=research_sources;sources=selection(f)
    monkeypatch.setattr(hybrid,'retrieve_same_paper',lambda document,*args,**kwargs:
        () if document.scope.paper_id==f['paper_ids'][1] else f['hits'][document.scope.paper_id])
    with pytest.raises(APIError) as error:retrieve_research_evidence(sources,deadline=time.monotonic()+30,cancel=Event())
    assert error.value.code=='RESEARCH_INSUFFICIENT_EVIDENCE'


def test_round_packing_skips_second_but_never_backfills_third(research_sources,monkeypatch):
    from researcy.research.evidence import retrieve_research_evidence
    from researcy.retrieval import hybrid
    from uuid import uuid4
    f=research_sources;sources=selection(f,True)
    candidates={}
    for source in sources:
        hit=f['hits'][source.document.scope.paper_id][0]
        candidates[source.document.scope.paper_id]=tuple(replace(hit,chunk_id=uuid4(),text=text)
            for text in ('x'*6000,'y'*6000,'z'))
    sources=tuple(replace(source,document=replace(source.document,
        chunk_ids=frozenset(hit.chunk_id for hit in candidates[source.document.scope.paper_id]))) for source in sources)
    def hits(document,*args,**kwargs):
        return candidates[document.scope.paper_id]
    monkeypatch.setattr(hybrid,'retrieve_same_paper',hits)
    evidence=retrieve_research_evidence(sources,deadline=time.monotonic()+30,cancel=Event())
    assert len(evidence.catalog)==4 and sum(len(entry.hit.text) for entry in evidence.catalog.values())==24000
    assert all(entry.hit.text=='x'*6000 for entry in evidence.catalog.values())


@pytest.mark.parametrize('ordinals',[(0,),(1,),(0,1)])
def test_active_selected_and_split_source_premises_all_resolve(research_sources,ordinals):
    from researcy.research.repository import reserve_research
    from researcy.research.models import ProposedIdea
    from researcy.research.evidence import retrieve_research_evidence,resolve_idea
    from uuid import uuid4
    f=research_sources;sources=selection(f)
    reservation=reserve_research(f['conn'],f['owner_id'],sources,uuid4())
    evidence=retrieve_research_evidence(sources,deadline=time.monotonic()+30,cancel=Event())
    idea=ProposedIdea(observed_gap='The sources report experimental limitations.',proposed_direction='Hypothesis: compare baselines.',
        possible_method='Hypothesis: run a controlled measurement.',premise_citations=[
            {'source_ref':f'P{n}:S1','evidence_quote':evidence.catalog[f'P{n}:S1'].raw_excerpt} for n in ordinals])
    citations=resolve_idea(f['conn'],reservation,evidence,idea,0)
    assert [c.citation.paper_id for c in citations]==[sources[n].document.scope.paper_id for n in ordinals]
    assert all(c.citation.boxes==tuple(box for fragment in c.raw_fragments for box in fragment.boxes) for c in citations)
    forged=idea.model_copy(update={'premise_citations':[idea.premise_citations[0].model_copy(update={'source_ref':'P9:S1'})]})
    with pytest.raises(APIError):resolve_idea(f['conn'],reservation,evidence,forged,0)
    invented=idea.model_copy(update={'premise_citations':[idea.premise_citations[0].model_copy(update={'evidence_quote':'invented quote'})]})
    with pytest.raises(APIError):resolve_idea(f['conn'],reservation,evidence,invented,0)


def test_navigation_query_uses_title_then_headings_with_bounded_context(research_sources):
    from researcy.research.evidence import build_research_query
    source=selection(research_sources)[0]
    query=build_research_query(replace(source,title='t'*2000,headings=('not used',)))
    assert query=='t'*1000+' limitations future work evaluation methods experiments'
    assert build_research_query(replace(source,title=None,headings=('Methods','Limitations')))=='Methods Limitations limitations future work evaluation methods experiments'


def test_real_multpage_quote_splits_exact_page_local_sources_without_normalized_fallback(selected_index_factory,monkeypatch):
    from uuid import uuid4
    from researcy.retrieval import index,repository as retrieval_repository,hybrid
    from researcy.research import repository
    from researcy.research.models import ProposedIdea
    from researcy.research.evidence import retrieve_research_evidence,resolve_idea
    publications=[]
    for pages in (('First evidence on page one.','Second evidence on page two.'),('Related evidence is exact.',)):
        source=selected_index_factory(owner_id=publications[0]['scope'].owner_id if publications else None,source_texts=pages)
        deadline=time.monotonic()+60
        index.index_selected(source['lease'],deadline)
        index.publish_ready(source['conn'],source['lease'],index.verify_index(source['lease'],deadline))
        publications.append(source)
    conn=publications[0]['conn'];owner=publications[0]['scope'].owner_id
    monkeypatch.setattr(retrieval_repository,'get_conn',publications[0]['get_conn'])
    sources=repository.load_selection(conn,owner,publications[0]['scope'].paper_id,(publications[1]['scope'].paper_id,))
    by_scope={s.document.scope:tuple(retrieval_repository.hydrate_hits(s.document,[(c,1.) for c in sorted(s.document.chunk_ids)])) for s in sources}
    monkeypatch.setattr(hybrid,'retrieve_same_paper',lambda document,*args,**kwargs:by_scope[document.scope])
    evidence=retrieve_research_evidence(sources,deadline=time.monotonic()+30,cancel=Event())
    assert evidence.catalog['P0:S1'].raw_excerpt=='First evidence on page one.Second evidence on page two.'
    run=repository.reserve_research(conn,owner,sources,uuid4())
    idea=ProposedIdea(observed_gap='The source reports evidence on two pages.',proposed_direction='Hypothesis: compare outcomes.',
        possible_method='Hypothesis: measure a matched baseline.',premise_citations=[
            {'source_ref':'P0:S1','evidence_quote':'First evidence on page one.Second evidence on page two.'}])
    citations=resolve_idea(conn,run,evidence,idea,0)
    assert [(c.citation.page,c.citation.evidence_quote) for c in citations]==[
        (1,'First evidence on page one.'),(2,'Second evidence on page two.')]
    for citation in citations:
        raw,boxes=conn.execute('''SELECT raw_text,boxes FROM document_spans WHERE owner_id=%s
            AND document_version_id=%s AND id=%s''',(owner,sources[0].document.scope.document_version_id,
                citation.raw_fragments[0].span_id)).fetchone()
        assert citation.citation.evidence_quote==raw
        assert citation.citation.boxes==tuple(tuple(box) for box in boxes)
    conn.commit()
    normalized=idea.model_copy(update={'premise_citations':[idea.premise_citations[0].model_copy(
        update={'evidence_quote':'First evidence on page one. Second evidence on page two.'})]})
    with pytest.raises(APIError):resolve_idea(conn,run,evidence,normalized,0)
