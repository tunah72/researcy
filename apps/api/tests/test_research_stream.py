import asyncio
from contextlib import contextmanager
import json
import socket
import threading
import time
from uuid import UUID

import httpx2
import pytest
import uvicorn

from researcy.config import Settings
from test_research_repository import reserve
from test_research_agent import research_provider
from test_research_api import research_client,headers,path


@pytest.mark.parametrize('stalled',['headers','body'])
def test_stalled_send_obeys_absolute_deadline_and_releases_owner_run(research_sources,stalled):
    from researcy.research.stream import ResearchStreamResponse
    from researcy.research.repository import get_owned_research
    f=research_sources;run=reserve(f);writes=[];closed=[]
    async def runner(*args,**kwargs):
        try:
            await asyncio.sleep(10)
            yield None
        finally:closed.append(True)
    async def execute():
        never=asyncio.Event()
        async def receive():await never.wait()
        async def send(message):
            writes.append(message)
            if (stalled=='headers' and message['type']=='http.response.start') or message['type']=='http.response.body':
                await never.wait()
        response=ResearchStreamResponse(run,Settings.from_env(),deadline=time.monotonic()+0.05,runner=runner)
        await asyncio.wait_for(response({'type':'http'},receive,send),timeout=2)
    asyncio.run(execute())
    snapshot=get_owned_research(f['conn'],f['owner_id'],run.active_paper_id,run.run_id)
    assert snapshot.state=='interrupted' and snapshot.ideas==()
    assert len(writes)==(1 if stalled=='headers' else 2)


def test_header_precedes_first_delta_and_disconnect_cancels_backpressure(research_sources):
    from researcy.research.stream import ResearchStreamResponse
    from researcy.research.models import ResearchEvent
    from researcy.research.repository import get_owned_research
    f=research_sources;run=reserve(f);messages=[]
    async def runner(*args,**kwargs):
        yield ResearchEvent('direction.delta',{'run_id':str(run.run_id),'request_id':str(run.request_id),
            'sequence':1,'idea_index':0,'idea':{'observed_gap':'Evidence','proposed_direction':'Hypothesis','possible_method':'Method'}})
    async def execute():
        writing=asyncio.Event();never=asyncio.Event()
        async def receive():await writing.wait();return {'type':'http.disconnect'}
        async def send(message):
            messages.append(message)
            if message['type']=='http.response.body':writing.set();await never.wait()
        response=ResearchStreamResponse(run,Settings.from_env(),deadline=time.monotonic()+3,runner=runner)
        await asyncio.wait_for(response({'type':'http'},receive,send),timeout=2)
    asyncio.run(execute())
    assert dict(messages[0]['headers'])[b'x-research-run-id']==str(run.run_id).encode()
    assert all(len(m.get('body',b''))<=16384 for m in messages)
    assert get_owned_research(f['conn'],f['owner_id'],run.active_paper_id,run.run_id).state=='interrupted'


def test_oversized_terminal_event_is_rejected_before_any_publication(research_sources,monkeypatch):
    from researcy.agents.research import run_research
    from researcy.research import stream
    from researcy.research.repository import get_owned_research
    f=research_sources;run=reserve(f);real_encode=stream.encode_event
    def enforce_smaller_terminal(event):
        # Controlled wire-size boundary; canonical resolution remains real.
        if event.event=='direction.completed':
            from researcy.errors import APIError
            raise APIError(503,'RESEARCH_EVENT_TOO_LARGE','The evidence exceeds the stream limit.')
        return real_encode(event)
    monkeypatch.setattr(stream,'encode_event',enforce_smaller_terminal)
    with research_provider(f) as (settings,requests):
        async def execute():return [e async for e in run_research(run,settings,deadline=time.monotonic()+30)]
        events=asyncio.run(execute())
    assert events[-1].event=='direction.failed' and events[-1].data['code']=='RESEARCH_EVENT_TOO_LARGE'
    assert get_owned_research(f['conn'],f['owner_id'],run.active_paper_id,run.run_id).state=='failed'
    assert f['conn'].execute('SELECT count(*) FROM research_citations').fetchone()==(0,)


@contextmanager
def real_api_socket(app):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
    thread=threading.Thread(target=lambda:asyncio.run(server.serve(sockets=[listener])),daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit=True;thread.join(timeout=5);listener.close()


def test_actual_tcp_post_commit_reload_and_cross_source_citation(research_sources,research_client,monkeypatch):
    from researcy.main import app
    from dataclasses import replace
    f=research_sources
    with research_provider(f) as (settings,requests):
        monkeypatch.setattr(app.state,'settings',replace(settings,trusted_origins=(headers(research_client)['Origin'],)))
        with real_api_socket(app) as endpoint:
            with httpx2.Client(base_url=endpoint,cookies=dict(research_client.cookies)) as client:
                response=client.post(path(f),json={'related_paper_ids':[str(f['paper_ids'][1])]},headers=headers(research_client),timeout=30)
                assert response.status_code==200 and response.headers['cache-control']=='no-store'
                run_id=UUID(response.headers['x-research-run-id'])
                events=[json.loads(frame.split('data: ',1)[1]) for frame in response.text.split('\n\n') if frame.startswith('event:')]
                assert events[-1]['run_id']==str(run_id) and len(events[-1]['ideas'])==1
                snapshot=client.get(f"/api/papers/{f['paper_ids'][0]}/research-directions/{run_id}").json()
                assert snapshot['state']=='completed'
                for citation in snapshot['ideas'][0]['premise_citations']:
                    resolved=client.get('/api/citations/'+citation['citation_id'])
                    assert resolved.status_code==200 and resolved.json()['citation']==citation
    assert len(requests)==1


def test_real_socket_disconnect_during_reservation_joins_then_interrupts(research_sources,research_client,monkeypatch):
    from urllib.parse import urlsplit
    from researcy.main import app
    from researcy.research import repository
    from dataclasses import replace
    f=research_sources;created=threading.Event();release=threading.Event();interrupted=threading.Event();reserved=[]
    real_reserve=repository.reserve_research;real_fail=repository.fail_research
    def reserve_blocked(conn,*args):
        result=real_reserve(conn,*args);reserved.append(result);created.set();release.wait(timeout=5);return result
    def observe_fail(conn,*args):
        result=real_fail(conn,*args);interrupted.set();return result
    monkeypatch.setattr(repository,'reserve_research',reserve_blocked)
    monkeypatch.setattr(repository,'fail_research',observe_fail)
    with research_provider(f) as (settings,requests):
        monkeypatch.setattr(app.state,'settings',replace(settings,trusted_origins=(headers(research_client)['Origin'],)))
        with real_api_socket(app) as endpoint:
            target=urlsplit(endpoint)
            body=json.dumps({'related_paper_ids':[str(f['paper_ids'][1])]}).encode()
            h=headers(research_client)
            cookie='; '.join(f'{key}={value}' for key,value in research_client.cookies.items())
            wire=(f'POST {path(f)} HTTP/1.1\r\nHost: {target.netloc}\r\nContent-Type: application/json\r\n'
                f"Origin: {h['Origin']}\r\nX-CSRF-Token: {h['X-CSRF-Token']}\r\nCookie: {cookie}\r\n"
                f'Content-Length: {len(body)}\r\n\r\n').encode()+body
            connection=socket.create_connection((target.hostname,target.port),timeout=3)
            try:
                connection.sendall(wire)
                assert created.wait(timeout=3)
                connection.shutdown(socket.SHUT_RDWR);connection.close()
            finally:release.set()
            assert interrupted.wait(timeout=3)
            snapshot=repository.get_owned_research(f['conn'],f['owner_id'],reserved[0].active_paper_id,reserved[0].run_id)
            assert snapshot.state=='interrupted' and snapshot.ideas==()
    assert requests==[]


def test_real_socket_run_header_allows_abort_before_first_delta_and_owned_reload(research_sources,research_client,monkeypatch):
    from researcy.main import app
    from researcy.retrieval import hybrid
    from researcy.research import repository
    from dataclasses import replace
    f=research_sources;retrieving=threading.Event();stopped=threading.Event();real_fail=repository.fail_research
    def retrieve(document,query,*,deadline,cancel):
        retrieving.set()
        if not cancel.wait(timeout=3):raise AssertionError('Disconnect did not cancel retrieval.')
        from researcy.ingestion.models import LostLease
        raise LostLease()
    def fail(conn,*args):
        result=real_fail(conn,*args);stopped.set();return result
    monkeypatch.setattr(hybrid,'retrieve_same_paper',retrieve)
    monkeypatch.setattr(repository,'fail_research',fail)
    with research_provider(f) as (settings,requests):
        monkeypatch.setattr(app.state,'settings',replace(settings,trusted_origins=(headers(research_client)['Origin'],)))
        with real_api_socket(app) as endpoint:
            with httpx2.Client(base_url=endpoint,cookies=dict(research_client.cookies)) as client:
                with client.stream('POST',path(f),json={'related_paper_ids':[str(f['paper_ids'][1])]},headers=headers(research_client),timeout=5) as response:
                    assert response.status_code==200
                    run_id=UUID(response.headers['x-research-run-id'])
                    assert retrieving.wait(timeout=2)
                assert stopped.wait(timeout=3)
                snapshot=client.get(f"/api/papers/{f['paper_ids'][0]}/research-directions/{run_id}").json()
                assert snapshot['state']=='interrupted' and snapshot['ideas']==[]
    assert requests==[]
