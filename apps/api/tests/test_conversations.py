from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import time

import psycopg
import pytest
from fastapi.testclient import TestClient

from conftest import _database_url
from test_library import BASE_URL, SESSION_LOOKUP_KEY, _authenticate
from researcy.errors import APIError


@pytest.fixture
def reader_source(selected_index):
    from researcy.retrieval import index
    from researcy.retrieval.repository import load_ready_document
    fixture = selected_index
    deadline = time.monotonic()+60
    index.index_selected(fixture['lease'],deadline)
    receipt = index.verify_index(fixture['lease'],deadline)
    index.publish_ready(fixture['conn'],fixture['lease'],receipt)
    fixture['document'] = load_ready_document(fixture['conn'],fixture['scope'].owner_id,
        fixture['scope'].paper_id,fixture['scope'].document_version_id)
    return fixture


@pytest.fixture
def reader_client(reader_source, monkeypatch):
    from researcy.main import app
    monkeypatch.setenv('APP_ENV','test')
    monkeypatch.setenv('APP_ORIGINS',BASE_URL)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setenv('SESSION_LOOKUP_KEY',SESSION_LOOKUP_KEY)
    monkeypatch.setenv('DATABASE_URL',_database_url(reader_source['conn'].info.dbname))
    with TestClient(app,base_url=BASE_URL) as client:
        _authenticate(client,reader_source['conn'],reader_source['scope'].owner_id)
        yield client


def test_ready_conversation_and_foreign_reads_use_private_boundaries(reader_source,reader_client):
    from researcy.auth.sessions import _csrf_verifier
    conn = reader_source['conn']
    csrf = 'reader-conversation-csrf'
    conn.execute('UPDATE sessions SET csrf_verifier=%s WHERE owner_id=%s',
        (_csrf_verifier(csrf,SESSION_LOOKUP_KEY.encode()),reader_source['scope'].owner_id))
    conn.commit()
    reader_client.cookies.set('researcy_csrf',csrf)
    path = f"/api/papers/{reader_source['scope'].paper_id}/conversations"
    response = reader_client.post(path,json={},headers={'Origin':BASE_URL,'X-CSRF-Token':csrf})
    assert response.status_code==201
    conversation = response.json()['conversation']
    assert conversation['document_version']==str(reader_source['scope'].document_version_id)
    assert reader_client.get(f"/api/conversations/{conversation['id']}/messages").json()['messages']==[]
    owner_b = conn.execute('INSERT INTO users(issuer,sub) VALUES(%s,%s) RETURNING id',
        ('https://accounts.google.com',str(uuid4()))).fetchone()[0]
    conn.commit()
    _authenticate(reader_client,conn,owner_b)
    foreign = reader_client.get(f"/api/conversations/{conversation['id']}/messages")
    missing = reader_client.get(f'/api/conversations/{uuid4()}/messages')
    assert foreign.status_code==missing.status_code==404
    assert foreign.json()['code']==missing.json()['code']=='RESOURCE_NOT_FOUND'
    assert foreign.json()['message']==missing.json()['message']
    assert reader_client.post(path,content=b'{',headers={'Origin':'https://hostile.example'}).status_code==403


def test_duplicate_uuid_does_not_charge_and_changed_question_conflicts(reader_source):
    from researcy.conversations.repository import create_owned_conversation,reserve_run
    conn, scope = reader_source['conn'],reader_source['scope']
    conversation = create_owned_conversation(conn,scope.owner_id,reader_source['document'])
    client_id = uuid4()
    first = reserve_run(conn,scope.owner_id,conversation.id,client_id,'Why parallelize?',uuid4())
    replay = reserve_run(conn,scope.owner_id,conversation.id,client_id,'Why parallelize?',uuid4())
    assert replay.run_id==first.run_id and replay.is_replay
    with pytest.raises(APIError) as caught:
        reserve_run(conn,scope.owner_id,conversation.id,client_id,'Changed question',uuid4())
    assert caught.value.code=='MESSAGE_CONFLICT'
    assert conn.execute('SELECT count(*) FROM reader_request_quota WHERE owner_id=%s',(scope.owner_id,)).fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM messages WHERE owner_id=%s',(scope.owner_id,)).fetchone()[0]==2
    conn.commit()


def test_concurrent_conversations_reserve_one_running_owner(reader_source):
    from researcy.conversations.repository import create_owned_conversation,reserve_run
    conn, scope = reader_source['conn'],reader_source['scope']
    conversations = [create_owned_conversation(conn,scope.owner_id,reader_source['document']) for _ in range(2)]
    database = _database_url(conn.info.dbname)
    barrier = Barrier(2)
    def attempt(conversation):
        with psycopg.connect(database) as separate:
            barrier.wait(timeout=5)
            try:
                return reserve_run(separate,scope.owner_id,conversation.id,uuid4(),'Which evidence?',uuid4()).state
            except APIError as error:
                return error.code
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(attempt,conversations))
    assert sorted(outcomes)==['READER_RUN_ACTIVE','running']
    assert conn.execute("SELECT count(*) FROM reader_runs WHERE owner_id=%s AND state='running'",(scope.owner_id,)).fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM reader_request_quota WHERE owner_id=%s',(scope.owner_id,)).fetchone()[0]==1
    conn.commit()


def test_reload_expiry_cannot_be_overwritten_by_late_completion(reader_source):
    from researcy.conversations.repository import create_owned_conversation,reserve_run,list_owned_messages,finish_run
    conn, scope = reader_source['conn'],reader_source['scope']
    conversation = create_owned_conversation(conn,scope.owner_id,reader_source['document'])
    run = reserve_run(conn,scope.owner_id,conversation.id,uuid4(),'Why parallelize?',uuid4())
    conn.execute('UPDATE reader_runs SET lease_expires_at=started_at WHERE owner_id=%s AND id=%s',(scope.owner_id,run.run_id))
    conn.commit()
    messages,_ = list_owned_messages(conn,scope.owner_id,conversation.id)
    assert [(message.role,message.state) for message in messages]==[('user','completed'),('assistant','interrupted')]
    with pytest.raises(APIError) as caught:
        finish_run(conn,run,[],(),{},refusal='No supported evidence.')
    assert caught.value.code=='READER_RUN_NOT_ACTIVE'
    assert conn.execute('SELECT state FROM reader_runs WHERE owner_id=%s AND id=%s',(scope.owner_id,run.run_id)).fetchone()[0]=='interrupted'
    conn.commit()


def test_history_excludes_failed_draft_and_retains_successful_whole_turns(reader_source):
    from researcy.conversations.repository import create_owned_conversation,reserve_run,finish_run,fail_run,load_history,list_owned_messages
    conn, scope = reader_source['conn'],reader_source['scope']
    conversation = create_owned_conversation(conn,scope.owner_id,reader_source['document'])
    for index in range(7):
        run = reserve_run(conn,scope.owner_id,conversation.id,uuid4(),f'Question {index}',uuid4())
        finish_run(conn,run,[],(),{},refusal=f'No supporting evidence {index}.')
    failed = reserve_run(conn,scope.owner_id,conversation.id,uuid4(),'Failed question',uuid4())
    fail_run(conn,failed,'READER_FAILED',False,'Provisional unsupported draft')
    history = load_history(conn,scope.owner_id,conversation.id)
    assert [message.text for message in history if message.role=='user']==[f'Question {index}' for index in range(1,7)]
    assert all(message.state in ('completed','refused') for message in history)
    persisted,_ = list_owned_messages(conn,scope.owner_id,conversation.id)
    assert persisted[-1].state=='failed' and persisted[-1].text=='Provisional unsupported draft'


def test_rolling_hour_quota_rejects_twenty_first_new_run(reader_source):
    from researcy.conversations.repository import create_owned_conversation,reserve_run,fail_run
    conn, scope = reader_source['conn'],reader_source['scope']
    conversation = create_owned_conversation(conn,scope.owner_id,reader_source['document'])
    for index in range(20):
        run = reserve_run(conn,scope.owner_id,conversation.id,uuid4(),f'Question {index}',uuid4())
        fail_run(conn,run,'READER_FAILED',False,'')
    with pytest.raises(APIError) as caught:
        reserve_run(conn,scope.owner_id,conversation.id,uuid4(),'Over quota',uuid4())
    assert caught.value.code=='READER_RATE_LIMITED'
    conn.execute("UPDATE reader_request_quota SET accepted_at=clock_timestamp()-INTERVAL '61 minutes' WHERE owner_id=%s",(scope.owner_id,))
    conn.commit()
    assert reserve_run(conn,scope.owner_id,conversation.id,uuid4(),'After window expires',uuid4()).state=='running'


def test_history_budget_keeps_newest_whole_turns(reader_source):
    from researcy.conversations.repository import create_owned_conversation,reserve_run,finish_run,load_history
    conn, scope = reader_source['conn'],reader_source['scope']
    conversation = create_owned_conversation(conn,scope.owner_id,reader_source['document'])
    for index in range(3):
        run = reserve_run(conn,scope.owner_id,conversation.id,uuid4(),str(index)+'q'*1999,uuid4())
        finish_run(conn,run,[],(),{},refusal=str(index)+'r'*1999)
    history = load_history(conn,scope.owner_id,conversation.id)
    assert [(message.role,message.text[0]) for message in history]==[
        ('user','1'),('assistant','1'),('user','2'),('assistant','2')]
    assert sum(len(message.text) for message in history)==8000


def test_conversation_cursor_returns_complete_ordered_pages_and_is_scoped(reader_source):
    from researcy.conversations.repository import create_owned_conversation,list_owned_conversations,list_owned_messages
    conn, scope = reader_source['conn'],reader_source['scope']
    created = [create_owned_conversation(conn,scope.owner_id,reader_source['document']) for _ in range(21)]
    first,cursor = list_owned_conversations(conn,scope.owner_id,scope.paper_id)
    second,last = list_owned_conversations(conn,scope.owner_id,scope.paper_id,cursor)
    assert [item.id for item in first+second]==[item.id for item in reversed(created)]
    assert last is None
    with pytest.raises(APIError) as caught:
        list_owned_conversations(conn,scope.owner_id,scope.paper_id,uuid4())
    assert caught.value.code=='RESOURCE_NOT_FOUND'
    with pytest.raises(APIError) as caught:
        list_owned_messages(conn,scope.owner_id,created[0].id,uuid4())
    assert caught.value.code=='RESOURCE_NOT_FOUND'


def test_unready_conversation_rejected_before_malformed_body(selected_index,monkeypatch):
    from researcy.auth.sessions import _csrf_verifier
    from researcy.main import app
    conn,scope = selected_index['conn'],selected_index['scope']
    monkeypatch.setenv('APP_ENV','test')
    monkeypatch.setenv('APP_ORIGINS',BASE_URL)
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setenv('SESSION_LOOKUP_KEY',SESSION_LOOKUP_KEY)
    monkeypatch.setenv('DATABASE_URL',_database_url(conn.info.dbname))
    with TestClient(app,base_url=BASE_URL) as client:
        _authenticate(client,conn,scope.owner_id)
        csrf = 'reader-unready-csrf'
        conn.execute('UPDATE sessions SET csrf_verifier=%s WHERE owner_id=%s',
            (_csrf_verifier(csrf,SESSION_LOOKUP_KEY.encode()),scope.owner_id))
        conn.commit()
        client.cookies.set('researcy_csrf',csrf)
        response = client.post(f'/api/papers/{scope.paper_id}/conversations',content=b'{',
            headers={'Origin':BASE_URL,'X-CSRF-Token':csrf,'Content-Type':'application/json'})
    assert response.status_code==409 and response.json()['code']=='PAPER_NOT_READY'
    assert conn.execute('SELECT count(*) FROM conversations WHERE owner_id=%s',(scope.owner_id,)).fetchone()[0]==0
    conn.commit()
