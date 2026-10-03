import asyncio
from dataclasses import replace
import json
import threading
from uuid import uuid4

import pytest

from test_conversations import reader_source
from test_generation import local_fault_server


def test_complete_claim_waits_for_validated_action_discriminator():
    from researcy.agents.reader_parser import ClaimParser
    parser = ClaimParser()
    assert parser.feed(b'{"claims":[{"text":"Supported claim.","citations":[{"source_ref":"S1","evidence_quote":"Exact source."}]}],')==()
    claims = parser.feed(b'"next_action":"answer","refusal":null}')
    assert [claim.text for claim in claims]==['Supported claim.']
    parser.finish()


def test_real_graph_publishes_only_exact_cited_claim_after_incremental_delta(reader_source,monkeypatch):
    from conftest import _database_url
    from researcy.config import Settings
    from researcy.agents.reader import run_reader
    from researcy.conversations.repository import create_owned_conversation,reserve_run
    from researcy.retrieval import hybrid
    from researcy.retrieval.repository import hydrate_hits
    fixture = reader_source
    conn,document = fixture['conn'],fixture['document']
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    # The retrieval publication is real; native embedding is not this controlled
    # transport test's boundary. Canonical hydration and citation resolution stay real.
    hits = tuple(hydrate_hits(document,[(chunk_id,1.) for chunk_id in sorted(document.chunk_ids)]))
    monkeypatch.setattr(hybrid,'retrieve_same_paper',lambda pinned,query,**kwargs:hits)
    quote = ''.join(fragment.quote for fragment in hits[0].locations)
    action = {'next_action':'answer','claims':[{'text':'This paper contains exact indexed evidence.',
        'citations':[{'source_ref':'S1','evidence_quote':quote}]}],'refusal':None}
    calls = []
    def response_fn(handler,body):
        calls.append(json.loads(body))
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        raw = json.dumps(action)
        frame = {'choices':[{'delta':{'content':raw},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}
        handler.wfile.write(('data: '+json.dumps(frame)+'\n\n').encode())
        handler.wfile.flush()
    conversation = create_owned_conversation(conn,document.scope.owner_id,document)
    reservation = reserve_run(conn,document.scope.owner_id,conversation.id,uuid4(),'What evidence is indexed?',uuid4())
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            return [event async for event in run_reader(reservation,document,settings)]
        events = asyncio.run(run())
    assert [event.event for event in events]==['answer.delta','citation.resolved','answer.completed']
    assert events[0].data['text']==action['claims'][0]['text']
    assert events[-1].data['state']=='completed'
    assert len(calls)==1
    state = conn.execute('SELECT state,generation_calls,usage FROM reader_runs WHERE id=%s',(reservation.run_id,)).fetchone()
    assert state[0:2]==('completed',1)
    assert state[2]['passes'][0]['usage']=={'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}
    assert conn.execute('SELECT evidence_quote,state FROM citations WHERE assistant_message_id=%s',
        (reservation.assistant_message_id,)).fetchall()==[(quote,'accepted')]


@pytest.mark.parametrize('case,expected_state,expected_calls,expected_searches,has_delta',[
    ('search_answer','completed',2,1,True),
    ('repair_answer','completed',2,0,True),
    ('search_bad_quote','failed',2,1,False),
    ('follow_up_search','failed',2,1,False),
    ('unsupported','failed',1,0,False),
    ('forged_scope','failed',1,0,False),
    ('late_bad_quote','failed',1,0,True),
    ('contradictory_final','failed',1,0,True),
    ('refusal','refused',1,0,True),
    ('partial_usage','completed',1,0,True),
    ('rate_limited','failed',1,0,False),
    ('provider_failure','failed',1,0,False),
    ('partial_eof','failed',1,0,False),
    ('truncated_answer_repair','completed',2,0,True),
    ('truncated_answer_exhausted','failed',2,0,False),
    ('truncated_after_delta','failed',1,0,True),
])
def test_real_graph_branches_and_failure_publication_are_bounded(reader_source,monkeypatch,
    case,expected_state,expected_calls,expected_searches,has_delta):
    from conftest import _database_url
    from researcy.config import Settings
    from researcy.agents.reader import run_reader
    from researcy.conversations.repository import create_owned_conversation,reserve_run,load_history
    from researcy.retrieval import hybrid
    from researcy.retrieval.repository import hydrate_hits
    conn,document = reader_source['conn'],reader_source['document']
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    hits = tuple(hydrate_hits(document,[(chunk_id,1.) for chunk_id in sorted(document.chunk_ids)]))
    retrieved = []
    def retrieve(pinned,query,**kwargs):
        retrieved.append((pinned.scope,query))
        return hits
    monkeypatch.setattr(hybrid,'retrieve_same_paper',retrieve)
    quote = ''.join(fragment.quote for fragment in hits[0].locations)
    claim = {'text':'This paper contains indexed evidence.','citations':[{'source_ref':'S1','evidence_quote':quote}]}
    bad_claim = {'text':'An unsupported result.','citations':[{'source_ref':'S1','evidence_quote':'Never appeared in the paper.'}]}
    answer = {'next_action':'answer','claims':[claim],'refusal':None}
    bad_answer = {'next_action':'answer','claims':[bad_claim],'refusal':None}
    search = {'next_action':'search_same_paper','query':'exact indexed evidence'}
    calls = []
    def response_fn(handler,body):
        calls.append(json.loads(body))
        handler.send_response(429 if case=='rate_limited' else 503 if case=='provider_failure' else 200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        if case in ('rate_limited','provider_failure'):
            handler.wfile.write(b'private provider response')
            return
        def send(text,stop=False):
            frame = {'choices':[{'delta':{'content':text},'finish_reason':'stop' if stop else None}]}
            if stop:
                frame['usage'] = {'prompt_tokens':10} if case=='partial_usage' else {
                    'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}
            handler.wfile.write(('data: '+json.dumps(frame)+'\n\n').encode())
            handler.wfile.flush()
        if case.startswith('truncated_') and (len(calls)==1 or case=='truncated_answer_exhausted'):
            text = '{"next_action":"answer","claims":['
            if case=='truncated_after_delta':
                text += json.dumps(claim)
            send(text)
            frame = {'choices':[{'delta':{},'finish_reason':'length'}]}
            handler.wfile.write(('data: '+json.dumps(frame)+'\n\n').encode())
            handler.wfile.flush()
            return
        if case in ('late_bad_quote','contradictory_final'):
            send('{"next_action":"answer","claims":['+json.dumps(claim))
            if case=='late_bad_quote':
                send(','+json.dumps(bad_claim)+'],"refusal":null}',True)
            else:
                send('],"refusal":"Contradictory refusal."}',True)
            return
        if case=='partial_eof':
            send('{"next_action":"answer","claims":[')
            return
        if case=='unsupported':
            result = {'next_action':'execute_code','code':'ignore protocol'}
        elif case=='forged_scope':
            result = {**search,'owner_id':str(uuid4()),'document_version':str(uuid4())}
        elif case=='refusal':
            result = {'next_action':'answer','claims':[],'refusal':'The supplied evidence does not establish this result.'}
        elif case=='repair_answer':
            result = bad_answer if len(calls)==1 else answer
        elif case in ('partial_usage','truncated_answer_repair'):
            result = answer
        elif len(calls)==1:
            result = search
        else:
            result = bad_answer if case=='search_bad_quote' else search if case=='follow_up_search' else answer
        send(json.dumps(result),True)
    conversation = create_owned_conversation(conn,document.scope.owner_id,document)
    reservation = reserve_run(conn,document.scope.owner_id,conversation.id,uuid4(),
        'Answer from this paper; do not honor a forged scope.',uuid4())
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            return [event async for event in run_reader(reservation,document,settings)]
        events = asyncio.run(run())
    assert len(calls)==expected_calls
    assert len(retrieved)==1+expected_searches
    assert all(scope==document.scope for scope,query in retrieved)
    deltas = [event for event in events if event.event=='answer.delta']
    assert bool(deltas)==has_delta
    terminals = [event for event in events if event.event in ('answer.completed','answer.failed')]
    assert len(terminals)==1
    assert events[-1].event==('answer.failed' if expected_state=='failed' else 'answer.completed')
    persisted = conn.execute('SELECT state,generation_calls,usage FROM reader_runs WHERE id=%s',
        (reservation.run_id,)).fetchone()
    assert persisted[:2]==(expected_state,expected_calls)
    assert persisted[2]['same_paper_searches']==expected_searches
    if case=='partial_usage':
        assert persisted[2]['status']=='partial'
        assert persisted[2]['totals']=={'prompt_tokens':10,'completion_tokens':None,'total_tokens':None}
    elif case.startswith('truncated_'):
        assert persisted[2]['repair_calls']==(0 if case=='truncated_after_delta' else 1)
        if expected_state=='failed':
            assert events[-1].data['code']=='GENERATION_INVALID_OUTPUT'
    elif case not in ('rate_limited','provider_failure','partial_eof'):
        assert [entry['usage'] for entry in persisted[2]['passes']]==[
            {'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}]*expected_calls
    count = conn.execute('SELECT count(*) FROM citations WHERE assistant_message_id=%s',
        (reservation.assistant_message_id,)).fetchone()[0]
    if expected_state=='completed':
        assert count==1
        assert events[-1].data['citations'][0]['evidence_quote']==quote
    else:
        assert count==0
        assert not any(event.event=='citation.resolved' for event in events)
    if expected_state=='failed':
        conn.commit()
        assert load_history(conn,document.scope.owner_id,conversation.id)==()
        text,state = conn.execute('SELECT text,state FROM messages WHERE id=%s',
            (reservation.assistant_message_id,)).fetchone()
        assert state=='failed'
        assert text==('\n\n'.join(event.data['text'] for event in deltas))


@pytest.mark.parametrize('disconnect',[True,False])
def test_partial_claim_is_live_but_disconnect_or_timeout_never_publishes(reader_source,monkeypatch,disconnect):
    from conftest import _database_url
    from researcy.config import Settings
    from researcy.agents.reader import run_reader
    from researcy.conversations.repository import create_owned_conversation,reserve_run,load_history
    from researcy.retrieval import hybrid
    from researcy.retrieval.repository import hydrate_hits
    conn,document = reader_source['conn'],reader_source['document']
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    hits = tuple(hydrate_hits(document,[(chunk_id,1.) for chunk_id in sorted(document.chunk_ids)]))
    monkeypatch.setattr(hybrid,'retrieve_same_paper',lambda pinned,query,**kwargs:hits)
    quote = ''.join(fragment.quote for fragment in hits[0].locations)
    claim = {'text':'A provisional indexed fact.','citations':[{'source_ref':'S1','evidence_quote':quote}]}
    closed = threading.Event()
    received = []
    def response_fn(handler,body):
        received.append(json.loads(body))
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        frame = {'choices':[{'delta':{'content':'{"next_action":"answer","claims":['+json.dumps(claim)},
            'finish_reason':None}]}
        handler.wfile.write(('data: '+json.dumps(frame)+'\n\n').encode())
        handler.wfile.flush()
        handler.connection.settimeout(4)
        if handler.connection.recv(1)==b'':
            closed.set()
    conversation = create_owned_conversation(conn,document.scope.owner_id,document)
    reservation = reserve_run(conn,document.scope.owner_id,conversation.id,uuid4(),'What is indexed?',uuid4())
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key',
            generation_pass_seconds=1 if not disconnect else 60)
        async def run():
            stream = run_reader(reservation,document,settings)
            first = await asyncio.wait_for(anext(stream),timeout=3)
            assert first.event=='answer.delta' and first.data['text']==claim['text']
            assert conn.execute('SELECT state FROM reader_runs WHERE id=%s',(reservation.run_id,)).fetchone()[0]=='running'
            assert conn.execute('SELECT count(*) FROM citations WHERE assistant_message_id=%s',
                (reservation.assistant_message_id,)).fetchone()[0]==0
            if disconnect:
                await stream.aclose()
            else:
                rest = [event async for event in stream]
                assert [event.event for event in rest]==['answer.failed']
                assert rest[0].data['code']=='GENERATION_TIMEOUT'
        asyncio.run(run())
        assert closed.wait(timeout=2)
    expected = 'interrupted' if disconnect else 'failed'
    assert received[0]['model']=='ag/gemini-3.8-flash-low' and len(received)==1
    assert conn.execute('SELECT state,generation_calls FROM reader_runs WHERE id=%s',
        (reservation.run_id,)).fetchone()==(expected,1)
    assert conn.execute('SELECT text,state FROM messages WHERE id=%s',
        (reservation.assistant_message_id,)).fetchone()==(claim['text'],expected)
    assert conn.execute('SELECT count(*) FROM citations WHERE assistant_message_id=%s',
        (reservation.assistant_message_id,)).fetchone()[0]==0
    conn.commit()
    assert load_history(conn,document.scope.owner_id,conversation.id)==()


@pytest.mark.parametrize('publication_wins',[False,True])
def test_disconnect_and_publication_obey_the_database_cas_winner(reader_source,monkeypatch,publication_wins):
    from conftest import _database_url
    from researcy.config import Settings
    from researcy.agents.reader import run_reader
    from researcy.conversations import repository
    from researcy.retrieval import hybrid
    from researcy.retrieval.repository import hydrate_hits
    conn,document = reader_source['conn'],reader_source['document']
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    hits = tuple(hydrate_hits(document,[(chunk_id,1.) for chunk_id in sorted(document.chunk_ids)]))
    monkeypatch.setattr(hybrid,'retrieve_same_paper',lambda pinned,query,**kwargs:hits)
    quote = ''.join(fragment.quote for fragment in hits[0].locations)
    action = {'next_action':'answer','claims':[{'text':'A supported fact.','citations':[
        {'source_ref':'S1','evidence_quote':quote}]}],'refusal':None}
    entered,release,interruption_saved = threading.Event(),threading.Event(),threading.Event()
    finish,fail = repository.finish_run,repository.fail_run
    def publication(*args,**kwargs):
        result = finish(*args,**kwargs) if publication_wins else None
        entered.set()
        assert release.wait(timeout=5)
        return result if publication_wins else finish(*args,**kwargs)
    def interruption(*args,**kwargs):
        result = fail(*args,**kwargs)
        interruption_saved.set()
        return result
    monkeypatch.setattr(repository,'finish_run',publication)
    monkeypatch.setattr(repository,'fail_run',interruption)
    def response_fn(handler,body):
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream')
        handler.end_headers()
        frame = {'choices':[{'delta':{'content':json.dumps(action)},'finish_reason':'stop'}]}
        handler.wfile.write(('data: '+json.dumps(frame)+'\n\n').encode())
        handler.wfile.flush()
    conversation = repository.create_owned_conversation(conn,document.scope.owner_id,document)
    reservation = repository.reserve_run(conn,document.scope.owner_id,conversation.id,uuid4(),'A supported fact?',uuid4())
    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(),generation_endpoint=endpoint,generation_api_key='test-key')
        async def run():
            stream = run_reader(reservation,document,settings)
            closer = None
            try:
                assert (await anext(stream)).event=='answer.delta'
                assert await asyncio.to_thread(entered.wait,2)
                closer = asyncio.create_task(stream.aclose())
                if not publication_wins:
                    assert await asyncio.to_thread(interruption_saved.wait,2)
                    assert conn.execute('SELECT state FROM reader_runs WHERE owner_id=%s AND id=%s',
                        (document.scope.owner_id,reservation.run_id)).fetchone()==('interrupted',)
                    conn.commit()
            finally:
                release.set()
                if closer is not None:
                    await closer
                else:
                    await stream.aclose()
        asyncio.run(run())
    expected = 'completed' if publication_wins else 'interrupted'
    assert conn.execute('SELECT state FROM reader_runs WHERE owner_id=%s AND id=%s',
        (document.scope.owner_id,reservation.run_id)).fetchone()==(expected,)
    assert conn.execute('SELECT count(*) FROM citations WHERE owner_id=%s AND assistant_message_id=%s',
        (document.scope.owner_id,reservation.assistant_message_id)).fetchone()[0]==(1 if publication_wins else 0)


def test_retrieval_failure_before_generation_preserves_unknown_usage(reader_source,monkeypatch):
    from conftest import _database_url
    from researcy.config import Settings
    from researcy.agents.reader import run_reader
    from researcy.conversations.repository import create_owned_conversation,reserve_run
    from researcy.errors import APIError
    from researcy.retrieval import hybrid
    conn,document = reader_source['conn'],reader_source['document']
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    def unavailable(pinned,query,**kwargs):
        raise APIError(503,'DEPENDENCY_UNAVAILABLE','The dependency is unavailable.')
    monkeypatch.setattr(hybrid,'retrieve_same_paper',unavailable)
    conversation = create_owned_conversation(conn,document.scope.owner_id,document)
    reservation = reserve_run(conn,document.scope.owner_id,conversation.id,uuid4(),
        'Answer from indexed evidence.',uuid4())
    async def run():
        return [event async for event in run_reader(reservation,document,Settings.from_env())]
    events = asyncio.run(run())
    assert [event.event for event in events]==['answer.failed']
    assert events[0].data['code']=='DEPENDENCY_UNAVAILABLE'
    state,calls,usage = conn.execute('SELECT state,generation_calls,usage FROM reader_runs WHERE id=%s AND owner_id=%s',
        (reservation.run_id,document.scope.owner_id)).fetchone()
    assert (state,calls)==('failed',0)
    assert usage['status']=='unknown'
    assert usage['totals']=={'prompt_tokens':None,'completion_tokens':None,'total_tokens':None}
    assert usage['estimated_cost'] is None
    assert conn.execute('SELECT error_code FROM messages WHERE id=%s',
        (reservation.assistant_message_id,)).fetchone()[0]=='DEPENDENCY_UNAVAILABLE'


def test_reader_disconnect_closes_real_embedding_preflight_before_timeout(reader_source,monkeypatch):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from conftest import _database_url
    from researcy.config import Settings
    from researcy.agents.reader import run_reader
    from researcy.conversations.repository import create_owned_conversation,reserve_run
    conn,document = reader_source['conn'],reader_source['document']
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    connected,closed = threading.Event(),threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length','1000')
            self.end_headers()
            self.wfile.write(b'{')
            self.wfile.flush()
            connected.set()
            self.connection.settimeout(3)
            try:
                if self.rfile.read(1)==b'':
                    closed.set()
            except OSError:
                pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    monkeypatch.setenv('OLLAMA_BASE_URL',f'http://127.0.0.1:{server.server_port}')
    conversation = create_owned_conversation(conn,document.scope.owner_id,document)
    reservation = reserve_run(conn,document.scope.owner_id,conversation.id,uuid4(),'Read indexed evidence.',uuid4())
    async def run():
        stream = run_reader(reservation,document,Settings.from_env())
        first = asyncio.create_task(anext(stream))
        try:
            assert await asyncio.to_thread(connected.wait,2)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(first,2)
            assert await asyncio.to_thread(closed.wait,2)
        finally:
            if not first.done():
                first.cancel()
            await asyncio.gather(first,return_exceptions=True)
            await stream.aclose()
    try:
        asyncio.run(run())
        assert conn.execute('SELECT state FROM reader_runs WHERE id=%s',(reservation.run_id,)).fetchone()[0]=='interrupted'
        conn.commit()
        next_run = reserve_run(conn,document.scope.owner_id,conversation.id,uuid4(),'New explicit submission.',uuid4())
        assert not next_run.is_replay
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_disconnect_preserves_received_terminal_usage_without_publication(reader_source, monkeypatch):
    from conftest import _database_url
    from researcy.config import Settings
    from researcy.agents.reader import run_reader
    from researcy.generation.client import GenerationClient
    from researcy.conversations.repository import create_owned_conversation, reserve_run
    from researcy.retrieval import hybrid
    from researcy.retrieval.repository import hydrate_hits

    conn, document = reader_source['conn'], reader_source['document']
    monkeypatch.setenv('DATABASE_URL', _database_url(conn.info.dbname))
    hits = tuple(hydrate_hits(document, [(chunk_id, 1.) for chunk_id in sorted(document.chunk_ids)]))
    monkeypatch.setattr(hybrid, 'retrieve_same_paper', lambda pinned, query, **kwargs: hits)
    quote = ''.join(fragment.quote for fragment in hits[0].locations)
    action = {'next_action': 'answer', 'claims': [{'text': 'Provisional supported claim.',
        'citations': [{'source_ref': 'S1', 'evidence_quote': quote}]}], 'refusal': None}
    usage = {'prompt_tokens': 40, 'completion_tokens': 20, 'total_tokens': 60}
    closed = threading.Event()

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        frame = {'choices': [{'delta': {'content': json.dumps(action)}, 'finish_reason': 'stop'}],
            'usage': usage}
        handler.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode())
        handler.wfile.flush()
        handler.connection.settimeout(4)
        if handler.connection.recv(1) == b'':
            closed.set()

    conversation = create_owned_conversation(conn, document.scope.owner_id, document)
    reservation = reserve_run(conn, document.scope.owner_id, conversation.id, uuid4(), 'Received accounting?', uuid4())
    original_source = GenerationClient._stream_events

    async def exercise(settings):
        received = asyncio.Event()

        async def record_source(self, *args, **kwargs):
            checkpoint = kwargs['checkpoint_terminal']

            def record(event):
                checkpoint(event)
                received.set()

            kwargs['checkpoint_terminal'] = record
            async for event in original_source(self, *args, **kwargs):
                yield event

        monkeypatch.setattr(GenerationClient, '_stream_events', record_source)
        stream = run_reader(reservation, document, settings)
        assert (await asyncio.wait_for(anext(stream), 3)).event == 'answer.delta'
        await asyncio.wait_for(received.wait(), 1)
        await stream.aclose()

    with local_fault_server(response_fn) as endpoint:
        settings = replace(Settings.from_env(), generation_endpoint=endpoint, generation_api_key='test-key')
        asyncio.run(exercise(settings))
        assert closed.wait(2)
    state, calls, recorded = conn.execute('SELECT state,generation_calls,usage FROM reader_runs WHERE id=%s',
        (reservation.run_id,)).fetchone()
    assert (state, calls) == ('interrupted', 1)
    assert recorded['status'] == 'known'
    assert recorded['totals'] == usage
    assert recorded['passes'][0]['finish_reason'] == 'stop'
    assert conn.execute('SELECT count(*) FROM citations WHERE assistant_message_id=%s',
        (reservation.assistant_message_id,)).fetchone()[0] == 0
