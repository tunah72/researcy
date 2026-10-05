import asyncio
from contextlib import contextmanager
from dataclasses import replace
import json
import threading
import time

import pytest

from test_generation import gateway_settings,local_fault_server
from test_research_repository import reserve
from test_research_output import idea


def supported(f):
    entry=idea()
    entry['premise_citations']=[{'source_ref':f'P{index}:S1','evidence_quote':
        ''.join(location.quote for location in f['hits'][f['paper_ids'][index]][0].locations)} for index in (0,1)]
    return entry


@contextmanager
def research_provider(f,case='valid'):
    requests=[]
    def respond(handler,body):
        requests.append(json.loads(body))
        if case=='429':handler.send_response(429);handler.end_headers();return
        handler.send_response(200);handler.send_header('Content-Type','text/event-stream');handler.end_headers()
        entry=supported(f)
        if case in ('repair','repair_widen','twice_bad') and len(requests)==1:
            entry['premise_citations'][0]['evidence_quote']='Invented quote.'
        if case=='twice_bad':entry['premise_citations'][0]['evidence_quote']='Still invented.'
        if case=='repair_widen' and len(requests)==2:entry['premise_citations'][0]['source_ref']='P9:S1'
        output={'next_action':'directions','refusal':None,'ideas':[entry]}
        if case=='early_schema_scope' and len(requests)==1:
            output['ideas']=[{'observed_gap':0,'page':1}]
        if case=='unsupported':output={'next_action':'search_arxiv_metadata','ideas':[],'refusal':None}
        if case=='scope':output['owner_id']='forged'
        if case=='refusal':output={'next_action':'directions','ideas':[],'refusal':'Untrusted provider explanation'}
        if case=='late_bad':
            bad=supported(f);bad['premise_citations'][0]['evidence_quote']='Invented second quote.'
            fragments=['{"next_action":"directions","refusal":null,"ideas":['+json.dumps(entry)+',',json.dumps(bad)+']}']
        elif case=='late_envelope':
            fragments=['{"next_action":"directions","refusal":null,"ideas":['+json.dumps(entry)+']',',"refusal":"Contradiction"}']
        elif case=='early_citation_scope' and len(requests)==1:
            entry['premise_citations'][0]['evidence_quote']='Invented quote.'
            fragments=['{"next_action":"directions","refusal":null,"ideas":['+json.dumps(entry)+']',
                ',"owner_id":"forged"}']
        elif case=='eof':fragments=['{"next_action":"directions","refusal":null,"ideas":[']
        else:fragments=[json.dumps(output)]
        for text in fragments:
            handler.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':text}}]})+'\n\n').encode())
            handler.wfile.flush()
        if case=='eof':return
        frame={'choices':[{'delta':{},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}
        handler.wfile.write(('data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n').encode());handler.wfile.flush()
    with local_fault_server(respond) as endpoint:
        yield gateway_settings(generation_endpoint=endpoint,generation_api_key='controlled-test-key'),requests


@pytest.mark.parametrize('case,state,calls,deltas,code',[
    ('valid','completed',1,1,None),('repair','completed',2,1,None),
    ('late_bad','failed',1,1,'EVIDENCE_UNRESOLVED'),('late_envelope','failed',1,1,'GENERATION_INVALID_OUTPUT'),
    ('twice_bad','failed',2,0,'EVIDENCE_UNRESOLVED'),('repair_widen','failed',2,0,'EVIDENCE_UNRESOLVED'),
    ('unsupported','failed',1,0,'GENERATION_INVALID_ACTION'),('scope','failed',1,0,'GENERATION_INVALID_ACTION'),
    ('early_schema_scope','failed',1,0,'GENERATION_INVALID_ACTION'),
    ('early_citation_scope','failed',1,0,'GENERATION_INVALID_ACTION'),
    ('refusal','failed',1,0,'RESEARCH_INSUFFICIENT_EVIDENCE'),('429','failed',1,0,'GENERATION_RATE_LIMITED'),
    ('eof','failed',1,0,'GENERATION_UNAVAILABLE'),
])
def test_graph_http_dispatch_repair_and_atomic_acceptance_are_bounded(research_sources,case,state,calls,deltas,code):
    from researcy.agents.research import run_research
    from researcy.research.repository import get_owned_research
    f=research_sources;run=reserve(f)
    before=f['conn'].execute('SELECT (SELECT count(*) FROM papers),(SELECT count(*) FROM ingestion_jobs)').fetchone();f['conn'].commit()
    with research_provider(f,case) as (settings,requests):
        async def execute():return [event async for event in run_research(run,settings,deadline=time.monotonic()+30)]
        events=asyncio.run(execute())
    assert len(requests)==calls
    assert sum(e.event=='direction.delta' for e in events)==deltas
    assert events[-1].event==('direction.completed' if state=='completed' else 'direction.failed')
    if code:assert events[-1].data['code']==code
    snapshot=get_owned_research(f['conn'],f['owner_id'],run.active_paper_id,run.run_id)
    assert snapshot.state==state and bool(snapshot.ideas)==(state=='completed')
    assert all('premise_citations' not in e.data['idea'] for e in events if e.event=='direction.delta')
    assert all(e.data['run_id']==str(run.run_id) and e.data['request_id']==str(run.request_id) for e in events)
    row=f['conn'].execute('SELECT generation_calls,repairs,metrics FROM research_runs WHERE id=%s',(run.run_id,)).fetchone()
    assert row[:2]==(calls,calls-1)
    if case not in ('429','eof'):assert row[2]['totals']=={'prompt_tokens':10*calls,'completion_tokens':20*calls,'total_tokens':30*calls}
    assert f['conn'].execute('SELECT (SELECT count(*) FROM papers),(SELECT count(*) FROM ingestion_jobs)').fetchone()==before
    assert f['conn'].execute('SELECT count(*) FROM research_citations WHERE run_id=%s',(run.run_id,)).fetchone()[0]==(2 if state=='completed' else 0)
    if state=='completed':
        assert [e.event for e in events]==['direction.delta','citation.resolved','citation.resolved','direction.completed']
        assert {c.paper_id for c in snapshot.ideas[0].premise_citations}==set(f['paper_ids'][:2])
        assert all(c.boxes for c in snapshot.ideas[0].premise_citations)
    if calls==2:
        initial=json.loads(requests[0]['messages'][-1]['content'])['sources']
        repaired=json.loads(requests[1]['messages'][-1]['content'])['sources']
        assert repaired==initial


def test_disconnect_after_delta_closes_provider_and_keeps_text_only_draft(research_sources):
    from researcy.agents.research import run_research
    from researcy.research.repository import get_owned_research
    f=research_sources;run=reserve(f);released=threading.Event();request_seen=threading.Event()
    def respond(handler,body):
        request_seen.set();handler.send_response(200);handler.send_header('Content-Type','text/event-stream');handler.end_headers()
        prefix='{"next_action":"directions","refusal":null,"ideas":['+json.dumps(supported(f))
        handler.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':prefix}}]})+'\n\n').encode());handler.wfile.flush()
        released.wait(timeout=5)
    with local_fault_server(respond) as endpoint:
        settings=gateway_settings(generation_endpoint=endpoint,generation_api_key='controlled-test-key')
        async def execute():
            stream=run_research(run,settings,deadline=time.monotonic()+10)
            try:
                first=await asyncio.wait_for(anext(stream),timeout=3)
                assert first.event=='direction.delta'
            finally:await stream.aclose();released.set()
        asyncio.run(execute())
    snapshot=get_owned_research(f['conn'],f['owner_id'],run.active_paper_id,run.run_id)
    assert request_seen.is_set() and snapshot.state=='interrupted' and snapshot.ideas==()
    assert len(snapshot.draft_ideas)==1
    assert 'premise_citations' not in snapshot.draft_ideas[0].model_dump()
    assert f['conn'].execute('SELECT count(*) FROM research_citations').fetchone()==(0,)


@pytest.mark.parametrize('publication_wins',[False,True])
def test_disconnect_publication_cas_has_one_durable_winner(research_sources,monkeypatch,publication_wins):
    from researcy.agents.research import run_research
    from researcy.research import repository
    f=research_sources;run=reserve(f);publishing=threading.Event();release=threading.Event()
    real_finish=repository.finish_research;real_fail=repository.fail_research
    def finish(conn,*args):
        if publication_wins:
            result=real_finish(conn,*args);publishing.set();release.wait(timeout=5);return result
        publishing.set();release.wait(timeout=5);return real_finish(conn,*args)
    def fail(conn,*args):
        try:return real_fail(conn,*args)
        finally:release.set()
    monkeypatch.setattr(repository,'finish_research',finish)
    monkeypatch.setattr(repository,'fail_research',fail)
    with research_provider(f) as (settings,requests):
        async def execute():
            stream=run_research(run,settings,deadline=time.monotonic()+10)
            first=await anext(stream)
            assert first.event=='direction.delta'
            assert await asyncio.to_thread(publishing.wait,3)
            await asyncio.wait_for(stream.aclose(),timeout=3)
        try:asyncio.run(execute())
        finally:release.set()
    snapshot=repository.get_owned_research(f['conn'],f['owner_id'],run.active_paper_id,run.run_id)
    assert snapshot.state==('completed' if publication_wins else 'interrupted')
    assert bool(snapshot.ideas)==publication_wins
    assert f['conn'].execute('SELECT count(*) FROM research_citations').fetchone()==(2 if publication_wins else 0,)


def test_cancel_during_retrieval_joins_thread_before_releasing_run(research_sources,monkeypatch):
    from researcy.agents import research
    from researcy.research.repository import get_owned_research
    f=research_sources;run=reserve(f);started=threading.Event();joined=threading.Event()
    def retrieve(*args,deadline,cancel):
        started.set()
        try:
            if not cancel.wait(timeout=3):raise AssertionError('Retrieval cancellation was not signalled.')
            from researcy.ingestion.models import LostLease
            raise LostLease()
        finally:joined.set()
    monkeypatch.setattr(research,'retrieve_research_evidence',retrieve)
    async def execute():
        stream=research.run_research(run,gateway_settings(generation_endpoint='http://127.0.0.1:1/v1',generation_api_key='test'),
            deadline=time.monotonic()+10)
        pending=asyncio.create_task(anext(stream))
        assert await asyncio.to_thread(started.wait,2)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):await pending
        await stream.aclose()
        assert joined.is_set()
    asyncio.run(execute())
    assert get_owned_research(f['conn'],f['owner_id'],run.active_paper_id,run.run_id).state=='interrupted'
    assert f['conn'].execute('SELECT generation_calls FROM research_runs WHERE id=%s',(run.run_id,)).fetchone()==(0,)
