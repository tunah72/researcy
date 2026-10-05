from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from conftest import _database_url
from researcy.errors import APIError


def reserve(fixture):
    from researcy.research.repository import load_selection,reserve_research
    return reserve_research(fixture['conn'],fixture['owner_id'],load_selection(fixture['conn'],
        fixture['owner_id'],fixture['paper_ids'][0],(fixture['paper_ids'][1],)),uuid4())


def test_mixed_foreign_unready_selection_hides_owned_readiness(research_sources):
    from researcy.research.repository import load_selection
    f=research_sources
    for missing in (f['foreign_id'],uuid4()):
        with pytest.raises(APIError) as error:
            load_selection(f['conn'],f['owner_id'],f['paper_ids'][0],(missing,f['queued_id']))
        assert (error.value.status_code,error.value.code)==(404,'RESOURCE_NOT_FOUND')
    with pytest.raises(APIError) as error:
        load_selection(f['conn'],f['owner_id'],f['paper_ids'][0],(f['queued_id'],))
    assert error.value.code=='RESEARCH_SELECTION_NOT_READY'


def test_concurrent_reservations_leave_exactly_one_owner_run(research_sources):
    from researcy.research.repository import load_selection,reserve_research
    f=research_sources
    sources=load_selection(f['conn'],f['owner_id'],f['paper_ids'][0],(f['paper_ids'][1],))
    barrier=Barrier(2)
    def attempt(_):
        with psycopg.connect(_database_url(f['conn'].info.dbname)) as conn:
            barrier.wait(timeout=10)
            try:
                reserve_research(conn,f['owner_id'],sources,uuid4());return 'reserved'
            except APIError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as workers:outcomes=list(workers.map(attempt,range(2)))
    assert sorted(outcomes)==['RESEARCH_RUN_ACTIVE','reserved']
    assert f['conn'].execute("SELECT count(*) FROM research_runs WHERE state='running'").fetchone()==(1,)


def test_every_reserved_outcome_counts_toward_twentieth_hour_limit(research_sources):
    from researcy.research.repository import fail_research
    f=research_sources
    for _ in range(20):fail_research(f['conn'],reserve(f),'RESEARCH_INTERRUPTED',True,(),{})
    with pytest.raises(APIError) as error:reserve(f)
    assert (error.value.status_code,error.value.code)==(429,'RESEARCH_RATE_LIMITED')
    assert error.value.retry_after>0


def test_expired_owned_get_interrupts_and_late_finish_cannot_publish(research_sources):
    from researcy.research.repository import get_owned_research,finish_research
    f=research_sources;run=reserve(f);conn=f['conn']
    conn.execute('UPDATE research_runs SET lease_expires_at=started_at WHERE id=%s',(run.run_id,));conn.commit()
    snapshot=get_owned_research(conn,f['owner_id'],run.active_paper_id,run.run_id)
    assert snapshot.state=='interrupted' and snapshot.ideas==()
    assert snapshot.error.code=='RESEARCH_INTERRUPTED'
    ideas,citations=f['resolved_idea_for'](f['paper_ids'][0])
    with pytest.raises(APIError):finish_research(conn,run,ideas,citations,{})
    assert conn.execute('SELECT count(*) FROM research_citations').fetchone()==(0,)


def test_unselected_canonical_source_cannot_be_published(research_sources):
    from researcy.research.repository import finish_research
    f=research_sources;run=reserve(f);conn=f['conn']
    ideas,citations=f['resolved_idea_for'](f['paper_ids'][2])
    with pytest.raises(APIError) as error:finish_research(conn,run,ideas,citations,{})
    assert error.value.code=='EVIDENCE_UNRESOLVED'
    assert conn.execute('SELECT state FROM research_runs WHERE id=%s',(run.run_id,)).fetchone()==('running',)
    assert conn.execute('SELECT count(*) FROM research_ideas').fetchone()==(0,)
    assert conn.execute('SELECT count(*) FROM research_citations').fetchone()==(0,)


def test_invalid_raw_fragment_rolls_back_entire_terminal_publication(research_sources):
    from researcy.research.repository import finish_research
    f=research_sources;run=reserve(f);conn=f['conn']
    ideas,citations=f['resolved_idea_for'](f['paper_ids'][0])
    bad=replace(citations[0],raw_fragments=(replace(citations[0].raw_fragments[0],quote='invented raw quote'),))
    with pytest.raises(APIError):finish_research(conn,run,ideas,(bad,),{})
    assert conn.execute('SELECT state FROM research_runs WHERE id=%s',(run.run_id,)).fetchone()==('running',)
    assert conn.execute('SELECT count(*) FROM research_ideas').fetchone()==(0,)
    assert conn.execute('SELECT count(*) FROM research_citations').fetchone()==(0,)


def test_atomic_completion_reload_and_failure_callback_preserve_winner(research_sources):
    from researcy.research.repository import finish_research,fail_research,get_owned_research,record_research_attempt
    from researcy.citations.repository import get_owned_citation
    f=research_sources;run=reserve(f);conn=f['conn']
    record_research_attempt(conn,run,'initial')
    ideas,citations=f['resolved_idea_for'](f['paper_ids'][1])
    completed=finish_research(conn,run,ideas,citations,{'status':'known'})
    fail_research(conn,run,'RESEARCH_INTERRUPTED',True,(),{})
    snapshot=get_owned_research(conn,f['owner_id'],run.active_paper_id,run.run_id)
    assert snapshot==completed and snapshot.state=='completed' and snapshot.draft_ideas==()
    with pytest.raises(APIError) as error:get_owned_research(conn,uuid4(),run.active_paper_id,run.run_id)
    assert error.value.status_code==404


def test_attempt_ledger_forbids_repair_first_or_third_dispatch(research_sources):
    from researcy.research.repository import record_research_attempt
    f=research_sources;run=reserve(f)
    with pytest.raises(APIError):record_research_attempt(f['conn'],run,'repair')
    record_research_attempt(f['conn'],run,'initial');record_research_attempt(f['conn'],run,'repair')
    with pytest.raises(APIError):record_research_attempt(f['conn'],run,'repair')
    assert f['conn'].execute('SELECT generation_calls,repairs FROM research_runs WHERE id=%s',(run.run_id,)).fetchone()==(2,1)


def test_frozen_scientific_upload_binding_uses_verified_bytes_without_fabricated_arxiv_metadata(selected_index, monkeypatch):
    import hashlib
    import time
    from researcy import db
    from researcy.evaluation import m5
    from researcy.retrieval import index
    f=selected_index;scope=f['scope']
    deadline=time.monotonic()+60
    index.index_selected(f['lease'],deadline)
    index.publish_ready(f['conn'],f['lease'],index.verify_index(f['lease'],deadline))
    monkeypatch.setattr(db,'get_conn',f['get_conn'])
    pin={'paper_id':str(scope.paper_id),'document_version':str(scope.document_version_id),
        'profile_hash':f['profile'].profile_hash.hex()}
    manifest={'sources':[{'id':'1706.03762','edition':'arxiv:1706.03762v7',
        'sha256':hashlib.sha256(f['source_bytes']).hexdigest()}]}
    document={'compose_project':'researcy-m5-acceptance','database_name':f['conn'].info.dbname,
        'owner_id':str(scope.owner_id),'sources':{'1706.03762':pin}}
    assert m5._check_application_bindings(manifest,document,'researcy-m5-acceptance')==document['sources']
    row=f['conn'].execute('''SELECT p.source,p.canonical_arxiv_id,v.source_version FROM papers p
        JOIN document_versions v ON v.owner_id=p.owner_id AND v.paper_id=p.id
        WHERE p.owner_id=%s AND p.id=%s AND v.id=%s''',
        (scope.owner_id,scope.paper_id,scope.document_version_id)).fetchone()
    assert row==('upload',None,None)
    manifest['sources'][0]['sha256']='f'*64
    with pytest.raises(m5.EvaluationError,match='SOURCE_IDENTITY_MISMATCH'):
        m5._check_application_bindings(manifest,document,'researcy-m5-acceptance')
