import asyncio
from dataclasses import replace
import json
import time
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from conftest import _database_url
from test_conversations import reader_source
from test_generation import local_fault_server
from test_library import BASE_URL, SESSION_LOOKUP_KEY, _authenticate
from test_schema import insert_user, insert_paper, insert_job
from researcy.auth.sessions import _csrf_verifier
from researcy.config import Settings
from researcy.conversations.models import MessageStreamReplayResponse
from researcy.conversations.repository import create_owned_conversation, reserve_run, list_owned_messages
from researcy.conversations.stream import ReaderStreamResponse, EVENT_MAX_BYTES, TRANSPORT_CHUNK_SIZE
from researcy.main import app
from researcy.retrieval import hybrid
from researcy.retrieval.repository import hydrate_hits


def _setup_csrf(conn, client, owner_id):
    csrf = 'test-stream-csrf-token'
    conn.execute(
        'UPDATE sessions SET csrf_verifier=%s WHERE owner_id=%s',
        (_csrf_verifier(csrf, SESSION_LOOKUP_KEY.encode()), owner_id),
    )
    conn.commit()
    client.cookies.set('researcy_csrf', csrf)
    return csrf


def _parse_sse(text: str) -> list[dict]:
    events = []
    current_event = None
    current_data = []
    for line in text.splitlines():
        if line.startswith('event:'):
            current_event = line[len('event:'):].strip()
        elif line.startswith('data:'):
            current_data.append(line[len('data:'):].strip())
        elif line == '':
            if current_event is not None and current_data:
                events.append({
                    'event': current_event,
                    'data': json.loads('\n'.join(current_data)),
                })
            current_event = None
            current_data = []
    if current_event is not None and current_data:
        events.append({
            'event': current_event,
            'data': json.loads('\n'.join(current_data)),
        })
    return events


def test_stream_auth_csrf_origin_ownership_unready_before_malformed_body(reader_source, monkeypatch):
    conn = reader_source['conn']
    scope = reader_source['scope']
    document = reader_source['document']
    conversation = create_owned_conversation(conn, scope.owner_id, document)

    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('APP_ORIGINS', BASE_URL)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setenv('SESSION_LOOKUP_KEY', SESSION_LOOKUP_KEY)
    monkeypatch.setenv('DATABASE_URL', _database_url(conn.info.dbname))

    stream_path = f'/api/conversations/{conversation.id}/messages:stream'

    # 1. Unauthenticated client (no cookie) with malformed body
    with TestClient(app, base_url=BASE_URL) as anon_client:
        r = anon_client.post(stream_path, content=b'{')
        assert r.status_code == 401
        assert r.json()['code'] == 'UNAUTHENTICATED'

    with TestClient(app, base_url=BASE_URL) as client:
        _authenticate(client, conn, scope.owner_id)
        csrf = _setup_csrf(conn, client, scope.owner_id)

        # 2. Authenticated, but hostile Origin with malformed body
        r = client.post(
            stream_path,
            content=b'{',
            headers={'Origin': 'https://hostile.example', 'X-CSRF-Token': csrf},
        )
        assert r.status_code == 403
        assert r.json()['code'] == 'CSRF_REJECTED'

        # 3. Authenticated, trusted Origin, but missing CSRF token with malformed body
        r = client.post(
            stream_path,
            content=b'{',
            headers={'Origin': BASE_URL},
        )
        assert r.status_code == 403
        assert r.json()['code'] == 'CSRF_REJECTED'

        # 4. Authenticated, valid CSRF/Origin, but foreign/unknown conversation ID with malformed body
        r = client.post(
            f'/api/conversations/{uuid4()}/messages:stream',
            content=b'{',
            headers={'Origin': BASE_URL, 'X-CSRF-Token': csrf},
        )
        assert r.status_code == 404
        assert r.json()['code'] == 'RESOURCE_NOT_FOUND'

        # 5. Unready paper conversation with malformed body
        unready_paper, unready_ver = insert_paper(conn, scope.owner_id, None)
        insert_job(conn, scope.owner_id, unready_ver)
        conn.commit()
        unready_conv_id = conn.execute(
            'INSERT INTO conversations(owner_id, paper_id, document_version) VALUES(%s,%s,%s) RETURNING id',
            (scope.owner_id, unready_paper, unready_ver),
        ).fetchone()[0]
        conn.commit()
        r = client.post(
            f'/api/conversations/{unready_conv_id}/messages:stream',
            content=b'{',
            headers={'Origin': BASE_URL, 'X-CSRF-Token': csrf},
        )
        assert r.status_code == 409
        assert r.json()['code'] == 'PAPER_NOT_READY'

        # 6. Valid auth/Origin/CSRF/ready conversation, but malformed JSON
        r = client.post(
            stream_path,
            content=b'{',
            headers={'Origin': BASE_URL, 'X-CSRF-Token': csrf},
        )
        assert r.status_code == 422
        assert r.json()['code'] == 'INVALID_REQUEST'

        # 7. Valid JSON but missing required fields
        r = client.post(
            stream_path,
            json={'question': 'Where is the client_message_id?'},
            headers={'Origin': BASE_URL, 'X-CSRF-Token': csrf},
        )
        assert r.status_code == 422
        assert r.json()['code'] == 'INVALID_REQUEST'

        # 8. Blank question rejected
        r = client.post(
            stream_path,
            json={'client_message_id': str(uuid4()), 'question': '   '},
            headers={'Origin': BASE_URL, 'X-CSRF-Token': csrf},
        )
        assert r.status_code == 422
        assert r.json()['code'] == 'INVALID_REQUEST'


def test_stream_real_sse_events_and_terminal_order(reader_source, monkeypatch):
    conn = reader_source['conn']
    scope = reader_source['scope']
    document = reader_source['document']
    conversation = create_owned_conversation(conn, scope.owner_id, document)

    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('APP_ORIGINS', BASE_URL)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setenv('SESSION_LOOKUP_KEY', SESSION_LOOKUP_KEY)
    monkeypatch.setenv('DATABASE_URL', _database_url(conn.info.dbname))

    hits = tuple(hydrate_hits(document, [(chunk_id, 1.0) for chunk_id in sorted(document.chunk_ids)]))
    monkeypatch.setattr(hybrid, 'retrieve_same_paper', lambda pinned, query, **kwargs: hits)
    quote = ''.join(fragment.quote for fragment in hits[0].locations)
    action = {
        'next_action': 'answer',
        'claims': [
            {
                'text': 'This paper contains exact indexed evidence.',
                'citations': [{'source_ref': 'S1', 'evidence_quote': quote}],
            }
        ],
        'refusal': None,
    }

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        raw = json.dumps(action)
        frame = {
            'choices': [{'delta': {'content': raw}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30},
        }
        handler.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode())
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        monkeypatch.setenv('GENERATION_PROVIDER', '9router')
        monkeypatch.setenv('GENERATION_MODEL', 'ag/gemini-3.8-flash-low')
        monkeypatch.setenv('GENERATION_ENDPOINT', endpoint)
        monkeypatch.setenv('GENERATION_API_KEY', 'test-key')

        with TestClient(app, base_url=BASE_URL) as client:
            _authenticate(client, conn, scope.owner_id)
            csrf = _setup_csrf(conn, client, scope.owner_id)

            client_msg_id = str(uuid4())
            stream_path = f'/api/conversations/{conversation.id}/messages:stream'
            response = client.post(
                stream_path,
                json={'client_message_id': client_msg_id, 'question': 'What evidence is indexed?'},
                headers={'Origin': BASE_URL, 'X-CSRF-Token': csrf},
            )

            assert response.status_code == 200
            assert response.headers['content-type'] == 'text/event-stream; charset=utf-8'
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['x-accel-buffering'] == 'no'

            events = _parse_sse(response.text)
            event_names = [e['event'] for e in events]
            assert event_names == ['answer.delta', 'citation.resolved', 'answer.completed']
            assert events[0]['data']['text'] == action['claims'][0]['text']
            assert events[-1]['data']['state'] == 'completed'
            assert len(events[-1]['data']['citations']) == 1

            # Verify DB persistence
            run_row = conn.execute(
                'SELECT state, generation_calls FROM reader_runs WHERE client_message_id=%s',
                (client_msg_id,),
            ).fetchone()
            assert run_row == ('completed', 1)

            # Messages endpoint lists completed message
            list_resp = client.get(f'/api/conversations/{conversation.id}/messages')
            assert list_resp.status_code == 200
            msgs = list_resp.json()['messages']
            assert len(msgs) == 2
            assert msgs[0]['role'] == 'user'
            assert msgs[1]['role'] == 'assistant'
            assert msgs[1]['state'] == 'completed'
            assert msgs[1]['text'] == action['claims'][0]['text']
            assert len(msgs[1]['citations']) == 1


def test_stream_duplicate_uuid_replay_and_running_replay(reader_source, monkeypatch):
    conn = reader_source['conn']
    scope = reader_source['scope']
    document = reader_source['document']
    conversation = create_owned_conversation(conn, scope.owner_id, document)

    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('APP_ORIGINS', BASE_URL)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setenv('SESSION_LOOKUP_KEY', SESSION_LOOKUP_KEY)
    monkeypatch.setenv('DATABASE_URL', _database_url(conn.info.dbname))

    hits = tuple(hydrate_hits(document, [(chunk_id, 1.0) for chunk_id in sorted(document.chunk_ids)]))
    monkeypatch.setattr(hybrid, 'retrieve_same_paper', lambda pinned, query, **kwargs: hits)
    quote = ''.join(fragment.quote for fragment in hits[0].locations)
    action = {
        'next_action': 'answer',
        'claims': [
            {
                'text': 'Replay test claim.',
                'citations': [{'source_ref': 'S1', 'evidence_quote': quote}],
            }
        ],
        'refusal': None,
    }

    def response_fn(handler, body):
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        raw = json.dumps(action)
        frame = {
            'choices': [{'delta': {'content': raw}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15},
        }
        handler.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode())
        handler.wfile.flush()

    with local_fault_server(response_fn) as endpoint:
        monkeypatch.setenv('GENERATION_PROVIDER', '9router')
        monkeypatch.setenv('GENERATION_MODEL', 'ag/gemini-3.8-flash-low')
        monkeypatch.setenv('GENERATION_ENDPOINT', endpoint)
        monkeypatch.setenv('GENERATION_API_KEY', 'test-key')

        with TestClient(app, base_url=BASE_URL) as client:
            _authenticate(client, conn, scope.owner_id)
            csrf = _setup_csrf(conn, client, scope.owner_id)

            client_msg_id = str(uuid4())
            stream_path = f'/api/conversations/{conversation.id}/messages:stream'
            headers = {'Origin': BASE_URL, 'X-CSRF-Token': csrf}

            # 1. First submission streams and completes
            r1 = client.post(
                stream_path,
                json={'client_message_id': client_msg_id, 'question': 'Question A?'},
                headers=headers,
            )
            assert r1.status_code == 200
            assert 'text/event-stream' in r1.headers['content-type']

            # 2. Duplicate submission with exact same client_message_id and question:
            # Must return persisted state JSON, no SSE, no re-generation
            r2 = client.post(
                stream_path,
                json={'client_message_id': client_msg_id, 'question': 'Question A?'},
                headers=headers,
            )
            assert r2.status_code == 200
            assert 'application/json' in r2.headers['content-type']
            replay_data = r2.json()
            assert replay_data['state'] == 'completed'
            assert 'run_id' in replay_data
            assert 'message_id' in replay_data
            assert 'request_id' in replay_data
            # Model validates cleanly against MessageStreamReplayResponse
            MessageStreamReplayResponse.model_validate(replay_data)

            # Quota charged only once
            quota_count = conn.execute(
                'SELECT count(*) FROM reader_request_quota WHERE owner_id=%s',
                (scope.owner_id,),
            ).fetchone()[0]
            assert quota_count == 1

            # 3. Duplicate client_message_id with DIFFERENT question conflicts
            r3 = client.post(
                stream_path,
                json={'client_message_id': client_msg_id, 'question': 'Changed question B?'},
                headers=headers,
            )
            assert r3.status_code == 409
            assert r3.json()['code'] == 'MESSAGE_CONFLICT'

            # 4. Running replay returns explicit state='running'
            running_client_id = uuid4()
            conn.commit()
            running_res = reserve_run(conn, scope.owner_id, conversation.id, running_client_id, 'Running Q?', uuid4())
            assert running_res.state == 'running'

            r4 = client.post(
                stream_path,
                json={'client_message_id': str(running_client_id), 'question': 'Running Q?'},
                headers=headers,
            )
            assert r4.status_code == 200
            assert 'application/json' in r4.headers['content-type']
            running_replay = r4.json()
            assert running_replay['state'] == 'running'
            assert running_replay['run_id'] == str(running_res.run_id)
            assert running_replay['message_id'] == str(running_res.assistant_message_id)




def test_stream_rejects_oversize_event_without_publication(reader_source, monkeypatch):
    from researcy.agents.reader import ReaderEvent
    conn = reader_source['conn']
    scope = reader_source['scope']
    document = reader_source['document']
    conversation = create_owned_conversation(conn, scope.owner_id, document)

    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    async def idle_receive():
        await asyncio.Event().wait()
    # 2. Oversize event (> 262,144 bytes) cap defense
    oversize_text = 'X' * (EVENT_MAX_BYTES + 1000)
    async def oversize_runner(reservation, doc, settings):
        yield ReaderEvent('answer.delta', {
            'run_id': str(reservation.run_id),
            'message_id': str(reservation.assistant_message_id),
            'sequence': 1,
            'text': oversize_text,
            'request_id': str(reservation.request_id),
        })

    res2 = reserve_run(conn, scope.owner_id, conversation.id, uuid4(), 'Oversize?', uuid4())
    stream_resp2 = ReaderStreamResponse(
        reservation=res2,
        document=document,
        settings=Settings.from_env(),
        request_id=str(res2.request_id),
        runner=oversize_runner,
    )

    oversize_chunks = []
    async def collect_send2(msg):
        if msg['type'] == 'http.response.body':
            oversize_chunks.append(msg['body'])

    asyncio.run(stream_resp2({'type': 'http'}, idle_receive, collect_send2))

    oversize_payload = b''.join(oversize_chunks).decode('utf-8')
    events2 = _parse_sse(oversize_payload)
    assert len(events2) == 1
    assert events2[0]['event'] == 'answer.failed'
    assert events2[0]['data']['code'] == 'READER_EVENT_TOO_LARGE'

    # Check DB state
    failed_state = conn.execute(
        'SELECT state, validation_outcome FROM reader_runs WHERE id=%s',
        (res2.run_id,),
    ).fetchone()
    assert failed_state == ('failed', 'READER_EVENT_TOO_LARGE')


def test_stream_unstarted_route_abort_persists_interrupted(reader_source,monkeypatch):
    conn = reader_source['conn']
    scope = reader_source['scope']
    document = reader_source['document']
    conversation = create_owned_conversation(conn, scope.owner_id, document)

    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    res = reserve_run(conn, scope.owner_id, conversation.id, uuid4(), 'Aborted?', uuid4())
    assert res.state == 'running'

    response = ReaderStreamResponse(
        reservation=res,
        document=document,
        settings=Settings.from_env(),
        request_id=str(res.request_id),
    )

    async def fail_receive():
        return {'type': 'http.disconnect'}

    async def fail_send(msg):
        raise ConnectionResetError('Transport closed before response headers.')

    with pytest.raises(ConnectionResetError):
        asyncio.run(response({'type': 'http'}, fail_receive, fail_send))

    # Verify adapter fail_run covers unstarted
    aborted_state = conn.execute(
        'SELECT state FROM reader_runs WHERE id=%s',
        (res.run_id,),
    ).fetchone()[0]
    assert aborted_state == 'interrupted'


def test_stream_disconnect_interrupts_a_backpressured_send(reader_source,monkeypatch):
    from types import SimpleNamespace
    conn,document = reader_source['conn'],reader_source['document']
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    conversation = create_owned_conversation(conn,document.scope.owner_id,document)
    reservation = reserve_run(conn,document.scope.owner_id,conversation.id,uuid4(),'Disconnect while writing?',uuid4())
    async def runner(run,doc,settings):
        yield SimpleNamespace(event='answer.delta',data={'run_id':str(run.run_id),
            'message_id':str(run.assistant_message_id),'sequence':1,'text':'x'*240000,'request_id':str(run.request_id)})
    response = ReaderStreamResponse(reservation,document,Settings.from_env(),reservation.request_id,runner=runner)
    async def run():
        writing = asyncio.Event()
        never = asyncio.Event()
        async def send(message):
            if message['type']=='http.response.body':
                writing.set()
                await never.wait()
        async def receive():
            await writing.wait()
            return {'type':'http.disconnect'}
        task = asyncio.create_task(response({'type':'http'},receive,send))
        try:
            await asyncio.wait_for(asyncio.shield(task),timeout=2)
        finally:
            pending = [item for item in asyncio.all_tasks() if item is not asyncio.current_task() and not item.done()]
            for item in pending:
                item.cancel()
            await asyncio.sleep(0)
            for item in pending:
                if not item.done():
                    item.cancel()
            await asyncio.gather(*pending,return_exceptions=True)
    asyncio.run(run())
    assert conn.execute('SELECT state FROM reader_runs WHERE owner_id=%s AND id=%s',
        (document.scope.owner_id,reservation.run_id)).fetchone()==('interrupted',)


def test_stream_stalled_initial_headers_bounded_interruption_without_second_write(reader_source, monkeypatch):
    from types import SimpleNamespace
    conn, document = reader_source['conn'], reader_source['document']
    monkeypatch.setenv('DATABASE_URL', _database_url(conn.info.dbname))
    monkeypatch.setattr('researcy.conversations.stream.RUN_SECONDS', 0.05, raising=False)
    conversation = create_owned_conversation(conn, document.scope.owner_id, document)
    reservation = reserve_run(conn, document.scope.owner_id, conversation.id, uuid4(), 'Stalled headers?', uuid4())
    async def runner(run, doc, settings):
        yield SimpleNamespace(event='answer.delta', data={'run_id': str(run.run_id),
            'message_id': str(run.assistant_message_id), 'sequence': 1, 'text': 'hello', 'request_id': str(run.request_id)})
    response = ReaderStreamResponse(reservation, document, Settings.from_env(), reservation.request_id, runner=runner)
    sent_messages = []
    async def run():
        never = asyncio.Event()
        async def send(message):
            sent_messages.append(message)
            if message['type'] == 'http.response.start':
                await never.wait()
        async def receive():
            await never.wait()
        task = asyncio.create_task(response({'type': 'http'}, receive, send))
        try:
            await asyncio.wait_for(task, timeout=0.5)
        finally:
            pending = [item for item in asyncio.all_tasks() if item is not asyncio.current_task() and not item.done()]
            for item in pending:
                item.cancel()
            await asyncio.sleep(0)
            for item in pending:
                if not item.done():
                    item.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    asyncio.run(run())
    assert len(sent_messages) == 1
    assert sent_messages[0]['type'] == 'http.response.start'
    state_row = conn.execute('SELECT state, validation_outcome FROM reader_runs WHERE owner_id=%s AND id=%s',
        (document.scope.owner_id, reservation.run_id)).fetchone()
    assert state_row == ('interrupted', 'READER_INTERRUPTED')


def test_stream_stalled_body_send_deadline_interrupts_and_acloses_generator_without_second_write(reader_source, monkeypatch):
    from types import SimpleNamespace
    conn, document = reader_source['conn'], reader_source['document']
    monkeypatch.setenv('DATABASE_URL', _database_url(conn.info.dbname))
    monkeypatch.setattr('researcy.conversations.stream.RUN_SECONDS', 0.05, raising=False)
    conversation = create_owned_conversation(conn, document.scope.owner_id, document)
    reservation = reserve_run(conn, document.scope.owner_id, conversation.id, uuid4(), 'Stalled body?', uuid4())
    generator_closed = False
    async def runner(run, doc, settings):
        nonlocal generator_closed
        try:
            yield SimpleNamespace(event='answer.delta', data={'run_id': str(run.run_id),
                'message_id': str(run.assistant_message_id), 'sequence': 1, 'text': 'streaming claim text', 'request_id': str(run.request_id)})
            while True:
                await asyncio.sleep(1)
        finally:
            generator_closed = True
    response = ReaderStreamResponse(reservation, document, Settings.from_env(), reservation.request_id, runner=runner)
    sent_messages = []
    async def run():
        never = asyncio.Event()
        async def send(message):
            sent_messages.append(message)
            if message['type'] == 'http.response.body' and b'event: answer.delta' in message.get('body', b''):
                await never.wait()
        async def receive():
            await never.wait()
        task = asyncio.create_task(response({'type': 'http'}, receive, send))
        try:
            await asyncio.wait_for(task, timeout=0.5)
        finally:
            pending = [item for item in asyncio.all_tasks() if item is not asyncio.current_task() and not item.done()]
            for item in pending:
                item.cancel()
            await asyncio.sleep(0)
            for item in pending:
                if not item.done():
                    item.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    asyncio.run(run())
    assert generator_closed is True
    delta_bodies = [m for m in sent_messages if m['type'] == 'http.response.body' and b'event: answer.delta' in m.get('body', b'')]
    assert len(delta_bodies) == 1
    error_bodies = [m for m in sent_messages if m['type'] == 'http.response.body' and b'event: answer.failed' in m.get('body', b'')]
    assert len(error_bodies) == 0
    # Total body messages: exactly the initial comment + the single stalled answer.delta attempt
    body_messages = [m for m in sent_messages if m['type'] == 'http.response.body']
    assert len(body_messages) == 2
    state_row = conn.execute('SELECT state, validation_outcome FROM reader_runs WHERE owner_id=%s AND id=%s',
        (document.scope.owner_id, reservation.run_id)).fetchone()
    assert state_row == ('interrupted', 'READER_INTERRUPTED')


def test_stream_writable_graph_deadline_preserves_terminal_failure(reader_source, monkeypatch):
    from researcy.generation.client import GenerationClient
    from researcy.ingestion.models import LostLease

    conn, document = reader_source['conn'], reader_source['document']
    monkeypatch.setenv('DATABASE_URL', _database_url(conn.info.dbname))
    monkeypatch.setattr('researcy.conversations.stream.RUN_SECONDS', 0.05, raising=False)
    conversation = create_owned_conversation(conn, document.scope.owner_id, document)
    reservation = reserve_run(conn, document.scope.owner_id, conversation.id, uuid4(), 'Graph deadline?', uuid4())

    def delayed_retrieve(pinned, query, *, deadline=None, cancel=None, **kwargs):
        if cancel is not None:
            cancel.wait(timeout=2.0)
        raise LostLease()

    monkeypatch.setattr(hybrid, 'retrieve_same_paper', delayed_retrieve)

    generation_called = False
    def fake_stream(*args, **kwargs):
        nonlocal generation_called
        generation_called = True
        raise AssertionError('Generation should not be called')

    monkeypatch.setattr(GenerationClient, 'stream', fake_stream)

    response = ReaderStreamResponse(
        reservation=reservation,
        document=document,
        settings=Settings.from_env(),
        request_id=str(reservation.request_id),
    )

    sent_messages = []
    async def run():
        async def send(message):
            sent_messages.append(message)
        async def receive():
            await asyncio.Event().wait()
        task = asyncio.create_task(response({'type': 'http'}, receive, send))
        try:
            await asyncio.wait_for(task, timeout=1.0)
        finally:
            pending = [item for item in asyncio.all_tasks() if item is not asyncio.current_task() and not item.done()]
            for item in pending:
                item.cancel()
            await asyncio.sleep(0)
            for item in pending:
                if not item.done():
                    item.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    asyncio.run(run())

    assert not generation_called
    body_chunks = [m['body'] for m in sent_messages if m['type'] == 'http.response.body']
    payload = b''.join(body_chunks).decode('utf-8')
    events = _parse_sse(payload)
    failed_events = [e for e in events if e.get('event') == 'answer.failed']
    assert len(failed_events) == 1
    assert failed_events[0]['data']['code'] == 'READER_DEADLINE_EXCEEDED'

    state_row = conn.execute('SELECT state, validation_outcome FROM reader_runs WHERE owner_id=%s AND id=%s',
        (document.scope.owner_id, reservation.run_id)).fetchone()
    assert state_row == ('failed', 'READER_DEADLINE_EXCEEDED')


def test_committed_citation_sequence_uses_terminal_delivery_grace(reader_source, monkeypatch):
    from types import SimpleNamespace

    conn, document = reader_source['conn'], reader_source['document']
    monkeypatch.setenv('DATABASE_URL', _database_url(conn.info.dbname))
    clock = {'now': 1000.0}
    monkeypatch.setattr(time, 'monotonic', lambda: clock['now'])
    conversation = create_owned_conversation(conn, document.scope.owner_id, document)
    reservation = reserve_run(conn, document.scope.owner_id, conversation.id, uuid4(), 'Committed boundary?', uuid4())
    bodies = []

    async def runner(run, doc, settings):
        clock['now'] = 1150.0
        yield SimpleNamespace(event='citation.resolved', data={'citation_id': str(uuid4())})
        yield SimpleNamespace(event='answer.completed', data={'message_id': str(run.assistant_message_id)})

    async def exercise():
        async def send(message):
            await asyncio.sleep(0)
            if message['type'] == 'http.response.body':
                bodies.append(message['body'])

        async def receive():
            await asyncio.Event().wait()

        response = ReaderStreamResponse(reservation, document, Settings.from_env(),
            reservation.request_id, runner=runner)
        await response({'type': 'http'}, receive, send)

    asyncio.run(exercise())
    events = _parse_sse(b''.join(bodies).decode())
    assert [event['event'] for event in events] == ['citation.resolved', 'answer.completed']
