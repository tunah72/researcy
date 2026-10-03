import asyncio
from threading import Event
import json

import httpx2
import pytest

from test_discovery_api import related_source,reader_source,reader_client,_path
from test_discovery_output import _wire
from test_generation import local_fault_server


_FEED='''<feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/1706.03762v7</id><title>Active attention source</title></entry>
<entry><id>http://arxiv.org/abs/2005.11401v1</id><title>Retrieval augmented generation</title><author><name>First author</name></author><summary>Sequence modeling using retrieved context.</summary></entry>
<entry><id>http://arxiv.org/abs/1810.04805v1</id><title>Bidirectional language representations</title><summary>Attention for language representations.</summary></entry>
<entry><id>http://arxiv.org/abs/2203.02155v1</id><title>Training language models</title><summary>Related language modeling.</summary></entry>
<entry><id>http://arxiv.org/abs/2301.00001v1</id><title>Fourth candidate not selected</title></entry>
</feed>'''
_REASONS={'papers':[
    {'arxiv_id':'2203.02155','reason':'Language-modeling topic in supplied metadata.'},
    {'arxiv_id':'2005.11401','reason':'Sequence-modeling topic in supplied abstract.'},
    {'arxiv_id':'1810.04805','reason':'Attention topic in supplied abstract.'},
]}


def _identities(source):
    conn,scope=source['conn'],source['scope']
    values={table:conn.execute(f'SELECT * FROM {table} WHERE owner_id=%s ORDER BY 1',(scope.owner_id,)).fetchall()
        for table in ('papers','document_versions','ingestion_jobs','import_idempotency')}
    conn.commit()
    return values


def _setup(related_source,monkeypatch,feed=_FEED):
    from researcy.agents import discovery
    from researcy.papers import arxiv
    source,client,headers=related_source
    conn,scope=source['conn'],source['scope']
    conn.execute("UPDATE papers SET source='arxiv',canonical_arxiv_id='1706.03762' WHERE owner_id=%s AND id=%s",(scope.owner_id,scope.paper_id));conn.commit()
    requests=[]
    real_search=arxiv.search_official_arxiv_metadata
    def metadata(request):
        requests.append(str(request.url))
        assert request.url.host=='export.arxiv.org' and request.url.path=='/api/query'
        return httpx2.Response(200,text=feed)
    async def search(query,**kwargs):
        return await real_search(query,transport=httpx2.MockTransport(metadata),**kwargs)
    monkeypatch.setattr(discovery,'search_official_arxiv_metadata',search)
    monkeypatch.setattr(arxiv,'_GLOBAL_LIMITER',arxiv.ArxivLimiter())
    monkeypatch.setenv('GENERATION_PROVIDER','9router')
    monkeypatch.setenv('GENERATION_MODEL','ag/gemini-3.8-flash-low')
    monkeypatch.setenv('GENERATION_API_KEY','controlled-loopback-only')
    return source,client,headers,requests


def _provider(contents,requests):
    def respond(handler,body):
        requests.append(json.loads(body))
        assert len(requests)<=len(contents),'Unexpected generation repair/retry'
        content=contents[len(requests)-1]
        handler.send_response(200);handler.send_header('Content-Type','text/event-stream');handler.end_headers()
        handler.wfile.write(_wire(content));handler.wfile.flush()
    return respond


def test_search_selects_authoritative_first_three_excluding_active_and_never_imports(related_source,monkeypatch):
    source,client,headers,metadata=_setup(related_source,monkeypatch)
    before=_identities(source)
    generation=[]
    with local_fault_server(_provider(['{"next_action":"search_arxiv_metadata"}',json.dumps(_REASONS)],generation)) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        response=client.post(_path(source),headers=headers)
    assert response.status_code==200
    papers=response.json()['papers']
    assert [paper['arxiv_id'] for paper in papers]==['2005.11401','1810.04805','2203.02155']
    assert papers[0]['title']=='Retrieval augmented generation'
    assert papers[0]['authors']==['First author']
    assert papers[1]['authors']==[]
    assert [paper['arxiv_url'] for paper in papers]==['https://arxiv.org/abs/2005.11401','https://arxiv.org/abs/1810.04805','https://arxiv.org/abs/2203.02155']
    assert response.headers['cache-control']=='no-store'
    assert len(generation)==2 and len(metadata)==1
    assert _identities(source)==before
    row=source['conn'].execute('SELECT state,generation_calls,metadata_searches,eligible,returned,usage FROM discovery_runs WHERE owner_id=%s',(source['scope'].owner_id,)).fetchone()
    assert row[:5]==('completed',2,1,4,3)
    assert row[5]['totals']['total_tokens']==60


@pytest.mark.parametrize('initial,feed,searches',[('{"next_action":"stop"}',_FEED,0),('{"next_action":"search_arxiv_metadata"}','<feed xmlns="http://www.w3.org/2005/Atom"/>',1)])
def test_stop_or_empty_metadata_has_no_follow_up(related_source,monkeypatch,initial,feed,searches):
    source,client,headers,metadata=_setup(related_source,monkeypatch,feed)
    generation=[]
    with local_fault_server(_provider([initial],generation)) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        response=client.post(_path(source),headers=headers)
    assert response.status_code==200 and response.json()['papers']==[]
    assert len(generation)==1 and len(metadata)==searches
    assert source['conn'].execute('SELECT state,generation_calls,metadata_searches FROM discovery_runs WHERE owner_id=%s',(source['scope'].owner_id,)).fetchone()==('completed',1,searches)


@pytest.mark.parametrize('initial',['{"next_action":"import_paper"}','{"next_action":"search_arxiv_metadata","url":"https://hostile.example"}','{"next_action":"search_arxiv_metadata","owner_id":"forged"}','{"next_action":"search_arxiv_metadata","query":"all:everything"}','{"next_action":"stop"} trailing'])
def test_invalid_initial_cannot_dispatch_metadata_or_import_and_next_explicit_run_recovers(related_source,monkeypatch,initial):
    source,client,headers,metadata=_setup(related_source,monkeypatch)
    before=_identities(source)
    generation=[]
    with local_fault_server(_provider([initial,'{"next_action":"stop"}'],generation)) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        rejected=client.post(_path(source),headers=headers)
        recovered=client.post(_path(source),headers=headers)
    assert rejected.status_code==502 and rejected.json()['code']=='GENERATION_INVALID_ACTION'
    assert recovered.status_code==200 and recovered.json()['papers']==[]
    assert len(generation)==2 and metadata==[]
    assert _identities(source)==before
    assert source['conn'].execute('SELECT state FROM discovery_runs WHERE owner_id=%s ORDER BY started_at',(source['scope'].owner_id,)).fetchall()==[('failed',),('completed',)]


@pytest.mark.parametrize('papers',[
    [{'arxiv_id':'9999.99999','reason':'Invented identity.'}],
    [{'arxiv_id':'2005.11401v1','reason':'Versioned identity forbidden.'}],
    [{'arxiv_id':'2005.11401','reason':'Missing two selected IDs.'}],
    [{'arxiv_id':'2005.11401','reason':'Duplicate.'},{'arxiv_id':'2005.11401','reason':'Duplicate.'},{'arxiv_id':'1810.04805','reason':'Other.'}],
])
def test_final_identity_mismatch_rejects_every_result_without_repair(related_source,monkeypatch,papers):
    source,client,headers,metadata=_setup(related_source,monkeypatch)
    generation=[]
    with local_fault_server(_provider(['{"next_action":"search_arxiv_metadata"}',json.dumps({'papers':papers})],generation)) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        response=client.post(_path(source),headers=headers)
    assert response.status_code==502 and response.json()['code']=='GENERATION_INVALID_OUTPUT'
    assert 'papers' not in response.json()
    assert len(generation)==2 and len(metadata)==1
    row=source['conn'].execute('SELECT state,generation_calls,returned,usage FROM discovery_runs WHERE owner_id=%s',(source['scope'].owner_id,)).fetchone()
    assert row[:3]==('failed',2,0)
    assert row[3]['totals']['total_tokens']==60


def test_aggregate_deadline_returns_failure_and_retains_received_usage(related_source,monkeypatch):
    from researcy.discovery import routes
    source,client,headers,metadata=_setup(related_source,monkeypatch)
    monkeypatch.setattr(routes,'RUN_SECONDS',0.4)
    release=Event()
    generation=[]
    def respond(handler,body):
        generation.append(json.loads(body))
        handler.send_response(200);handler.send_header('Content-Type','text/event-stream');handler.end_headers()
        handler.wfile.write(_wire('{"next_action":"stop"}',done=False));handler.wfile.flush()
        release.wait(2)
    with local_fault_server(respond) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        try:
            response=client.post(_path(source),headers=headers)
        finally:
            release.set()
    assert response.status_code==504
    assert response.json()['code']=='DISCOVERY_TIMEOUT'
    assert len(generation)==1 and metadata==[]
    row=source['conn'].execute('SELECT state,error_code,generation_calls,usage FROM discovery_runs WHERE owner_id=%s',(source['scope'].owner_id,)).fetchone()
    assert row[:3]==('failed','DISCOVERY_TIMEOUT',1)
    assert row[3]['totals']['total_tokens']==30


@pytest.mark.parametrize('phase',['initial','follow_up'])
def test_disconnect_closes_provider_and_releases_owner_slot_without_late_tools(related_source,monkeypatch,phase):
    source,client,headers,metadata=_setup(related_source,monkeypatch)
    entered,closed=Event(),Event()
    generation=[]
    def respond(handler,body):
        generation.append(json.loads(body))
        handler.send_response(200);handler.send_header('Content-Type','text/event-stream');handler.end_headers()
        if phase=='follow_up' and len(generation)==1:
            handler.wfile.write(_wire('{"next_action":"search_arxiv_metadata"}'));handler.wfile.flush()
            return
        content='{"next_action":"stop"}' if phase=='initial' else json.dumps(_REASONS)
        handler.wfile.write(_wire(content,done=False));handler.wfile.flush()
        entered.set()
        handler.rfile.read(1)
        closed.set()
    with local_fault_server(respond) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        cookie='; '.join(f'{name}={value}' for name,value in client.cookies.items())
        path=_path(source)
        async def disconnect_request():
            incoming=asyncio.Queue()
            await incoming.put({'type':'http.request','body':b'','more_body':False})
            sent=[]
            scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST','scheme':'http',
                'path':path,'raw_path':path.encode(),'query_string':b'','root_path':'',
                'headers':[(b'host',b'localhost:3000'),(b'cookie',cookie.encode()),
                    (b'origin',headers['Origin'].encode()),(b'x-csrf-token',headers['X-CSRF-Token'].encode())],
                'client':('127.0.0.1',4321),'server':('localhost',3000)}
            async def send(message):
                sent.append(message['type'])
            task=asyncio.create_task(client.app(scope,incoming.get,send))
            try:
                assert await asyncio.to_thread(entered.wait,3)
                await incoming.put({'type':'http.disconnect'})
                await asyncio.wait_for(task,3)
                assert await asyncio.to_thread(closed.wait,1)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task,return_exceptions=True)
        asyncio.run(disconnect_request())
    attempts=1 if phase=='initial' else 2
    assert len(generation)==attempts and len(metadata)==attempts-1
    row=source['conn'].execute('SELECT state,error_code,generation_calls,usage FROM discovery_runs WHERE owner_id=%s',(source['scope'].owner_id,)).fetchone()
    assert row[:3]==('interrupted','DISCOVERY_INTERRUPTED',attempts)
    assert row[3]['totals']['total_tokens']==30*attempts
    source['conn'].commit()
    recovered=[]
    with local_fault_server(_provider(['{"next_action":"stop"}'],recovered)) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        response=client.post(_path(source),headers=headers)
    assert response.status_code==200 and response.json()['papers']==[]
    assert len(recovered)==1


def test_discovery_quota_is_independent_and_reader_history_never_widens_metadata_context(related_source,monkeypatch):
    from uuid import uuid4
    from researcy.conversations.repository import create_owned_conversation,reserve_run
    source,client,headers,metadata=_setup(related_source,monkeypatch)
    conn,scope=source['conn'],source['scope']
    conversation=create_owned_conversation(conn,scope.owner_id,source['document'])
    question='Private Reader turn must not enter metadata discovery.'
    reader=reserve_run(conn,scope.owner_id,conversation.id,uuid4(),question,uuid4())
    generation=[]
    with local_fault_server(_provider(['{"next_action":"stop"}'],generation)) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        response=client.post(_path(source),headers=headers)
    assert response.status_code==200 and response.json()['papers']==[]
    assert len(generation)==1 and metadata==[]
    assert question not in json.dumps(generation)
    assert conn.execute('SELECT state FROM reader_runs WHERE owner_id=%s AND id=%s',(scope.owner_id,reader.run_id)).fetchone()==('running',)
    assert conn.execute('SELECT count(*) FROM reader_request_quota WHERE owner_id=%s',(scope.owner_id,)).fetchone()==(1,)
    assert conn.execute('SELECT count(*) FROM discovery_runs WHERE owner_id=%s',(scope.owner_id,)).fetchone()==(1,)

@pytest.mark.parametrize('phase',['attempt','search','completion','publication','completion_deadline','publication_deadline'])
def test_disconnect_at_committed_boundary_never_leaves_success_or_loses_attempts(related_source,monkeypatch,phase):
    from researcy.discovery import repository,routes
    source,client,headers,metadata=_setup(related_source,monkeypatch)
    if phase in {'completion_deadline','publication_deadline'}:
        monkeypatch.setattr(routes,'RUN_SECONDS',3)
    entered,release=Event(),Event()
    operation={'attempt':'record_discovery_attempt','search':'record_discovery_search',
        'completion':'finish_discovery','completion_deadline':'finish_discovery'}.get(phase)
    if operation:
        original=getattr(repository,operation)
        def paused(conn,*args,**kwargs):
            result=original(conn,*args,**kwargs)
            if phase not in {'completion','completion_deadline'} or kwargs.get('state')=='completed':
                entered.set()
                assert release.wait(5)
            return result
        monkeypatch.setattr(repository,operation,paused)
    initial='{"next_action":"search_arxiv_metadata"}' if phase=='search' else '{"next_action":"stop"}'
    generation=[]
    with local_fault_server(_provider([initial],generation)) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        cookie='; '.join(f'{name}={value}' for name,value in client.cookies.items())
        path=_path(source)
        async def disconnect_request():
            incoming=asyncio.Queue()
            await incoming.put({'type':'http.request','body':b'','more_body':False})
            bodies=[]
            starts=[]
            scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST','scheme':'http',
                'path':path,'raw_path':path.encode(),'query_string':b'','root_path':'',
                'headers':[(b'host',b'localhost:3000'),(b'cookie',cookie.encode()),
                    (b'origin',headers['Origin'].encode()),(b'x-csrf-token',headers['X-CSRF-Token'].encode())],
                'client':('127.0.0.1',4321),'server':('localhost',3000)}
            async def send(message):
                if message['type']=='http.response.start':
                    starts.append(message['status'])
                if phase=='publication' and message['type']=='http.response.start' or phase=='publication_deadline' and message['type']=='http.response.body':
                    entered.set()
                    await asyncio.to_thread(release.wait,5)
                if message['type']=='http.response.body':
                    bodies.append(message.get('body',b''))
            task=asyncio.create_task(client.app(scope,incoming.get,send))
            try:
                assert await asyncio.to_thread(entered.wait,5)
                if phase in {'completion_deadline','publication_deadline'}:
                    await asyncio.sleep(3.1)
                else:
                    await incoming.put({'type':'http.disconnect'})
                    # Let the receive owner observe disconnect while the boundary is paused.
                    await asyncio.sleep(0.05)
                release.set()
                await asyncio.wait_for(task,5)
                if phase=='completion_deadline':
                    assert json.loads(b''.join(bodies))['code']=='DISCOVERY_TIMEOUT'
                else:
                    assert not bodies
                if phase=='publication_deadline':
                    assert starts==[200]
            finally:
                release.set()
                if not task.done(): task.cancel()
                await asyncio.gather(task,return_exceptions=True)
        asyncio.run(disconnect_request())
    row=source['conn'].execute('SELECT state,error_code,generation_calls,metadata_searches,usage FROM discovery_runs WHERE owner_id=%s',(source['scope'].owner_id,)).fetchone()
    expected=('failed','DISCOVERY_TIMEOUT') if phase in {'completion_deadline','publication_deadline'} else ('interrupted','DISCOVERY_INTERRUPTED')
    assert row[:4]==(*expected,1,int(phase=='search'))
    assert row[4]['generation_attempts']==1
    assert row[4]['metadata_searches']==int(phase=='search')
    assert row[4]['returned']==0
    assert len(generation)==int(phase!='attempt') and metadata==[]


@pytest.mark.parametrize('failure',['provider_503','metadata_after_redirect','metadata_connect','metadata_duplicate'])
def test_failed_run_retains_observed_headers_and_partial_physical_search_counts(related_source,monkeypatch,failure):
    from researcy.agents import discovery
    from researcy.papers import arxiv
    source,client,headers,_=_setup(related_source,monkeypatch)
    before=_identities(source)
    metadata=[]
    if failure.startswith('metadata_'):
        from test_arxiv_search import _entry,_feed
        real_search=arxiv.search_official_arxiv_metadata
        def upstream(request):
            metadata.append(str(request.url))
            if failure=='metadata_connect':
                raise httpx2.ConnectError('private transport detail',request=request)
            if failure=='metadata_duplicate':
                return httpx2.Response(200,text=_feed([_entry('2301.00001',title='First title'),_entry('2301.00001',title='Conflicting title')]))
            return httpx2.Response(307,headers={'Location':str(request.url.copy_with(host='arxiv.org'))}) if len(metadata)==1 else httpx2.Response(500)
        async def search(query,**kwargs):
            return await real_search(query,transport=httpx2.MockTransport(upstream),**kwargs)
        monkeypatch.setattr(discovery,'search_official_arxiv_metadata',search)
    generation=[]
    good=_provider(['{"next_action":"search_arxiv_metadata"}'],generation)
    def provider(handler,body):
        if failure!='provider_503':
            good(handler,body)
            return
        generation.append(json.loads(body))
        handler.send_response(503);handler.end_headers()
    with local_fault_server(provider) as endpoint:
        monkeypatch.setenv('GENERATION_ENDPOINT',endpoint)
        response=client.post(_path(source),headers=headers)
    assert response.status_code in {502,503} and 'papers' not in response.json()
    assert len(generation)==1
    assert _identities(source)==before
    row=source['conn'].execute('SELECT state,generation_calls,metadata_searches,usage FROM discovery_runs WHERE owner_id=%s',(source['scope'].owner_id,)).fetchone()
    assert row[:3]==('failed',1,int(failure!='provider_503'))
    assert row[3]['physical_generation_requests']==1
    assert row[3]['returned']==0
    if failure=='metadata_after_redirect':
        assert len(metadata)==2
        assert row[3]['arxiv_http_requests']==2 and row[3]['arxiv_redirects']==1
        assert row[3]['totals']['total_tokens']==30
    elif failure=='provider_503':
        assert row[3]['totals']['total_tokens'] is None
    if failure=='metadata_connect':
        assert row[3]['arxiv_http_requests'] is None
        assert row[3]['arxiv_http_requests_observed']==0 and row[3]['arxiv_http_request_attempts']==1
    if failure=='metadata_duplicate':
        assert row[3]['inspected_entries']==2 and row[3]['inspected_unique']==1 and row[3]['duplicates']==1
