from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
import psycopg

from conftest import _database_url

from test_conversations import reader_source


def test_abstract_column_preserves_unknown_metadata(pg_conn):
    from test_schema import insert_user, insert_paper
    owner = insert_user(pg_conn, str(uuid4()), None)
    paper, version = insert_paper(pg_conn, owner, None)
    assert pg_conn.execute('SELECT abstract FROM papers WHERE owner_id=%s AND id=%s', (owner,paper)).fetchone()==(None,)


@pytest.mark.parametrize('title',[None,' ','Untitled Document','the and','\x00unsafe'])
def test_missing_title_stops_before_ready_and_reservation(pg_conn,title):
    from researcy.discovery.repository import load_active_metadata
    from researcy.errors import APIError
    from test_schema import insert_user, insert_paper
    owner = insert_user(pg_conn,str(uuid4()),None)
    paper, version = insert_paper(pg_conn,owner,None)
    # PostgreSQL forbids NUL; the shared title validator covers that input directly.
    if title is not None and '\x00' in title:
        from researcy.papers.arxiv import related_title_terms
        with pytest.raises(APIError) as caught:
            related_title_terms(title)
    else:
        pg_conn.execute('UPDATE papers SET title=%s WHERE owner_id=%s AND id=%s',(title,owner,paper))
        pg_conn.commit()
        with pytest.raises(APIError) as caught:
            load_active_metadata(pg_conn,owner,paper)
    assert caught.value.code=='DISCOVERY_METADATA_MISSING'
    assert pg_conn.execute('SELECT count(*) FROM discovery_runs WHERE owner_id=%s',(owner,)).fetchone()==(0,)


def test_owner_scope_is_indistinguishable(pg_conn):
    from researcy.discovery.repository import load_active_metadata
    from researcy.errors import APIError
    from test_schema import insert_user, insert_paper
    owner = insert_user(pg_conn,str(uuid4()),None)
    stranger = insert_user(pg_conn,str(uuid4()),None)
    paper, version = insert_paper(pg_conn,owner,None)
    pg_conn.commit()
    errors=[]
    for identifier in (paper,uuid4()):
        with pytest.raises(APIError) as caught:
            load_active_metadata(pg_conn,stranger,identifier)
        errors.append((caught.value.status_code,caught.value.code,caught.value.message))
    assert errors[0]==errors[1]
    assert errors[0][0]==404


def test_attempt_caps_and_interruption_cannot_be_overwritten(reader_source):
    from researcy.discovery.repository import load_active_metadata,reserve_discovery,record_discovery_attempt,finish_discovery
    from researcy.errors import APIError
    conn,scope=reader_source['conn'],reader_source['scope']
    conn.execute('UPDATE papers SET title=%s,abstract=%s WHERE owner_id=%s AND id=%s',('Attention mechanisms','Sequence modeling.',scope.owner_id,scope.paper_id))
    conn.commit()
    source=load_active_metadata(conn,scope.owner_id,scope.paper_id)
    assert source.abstract=='Sequence modeling.'
    run=reserve_discovery(conn,source,str(uuid4()))
    record_discovery_attempt(conn,run,'initial')
    record_discovery_attempt(conn,run,'follow_up')
    with pytest.raises(APIError):
        record_discovery_attempt(conn,run,'follow_up')
    assert finish_discovery(conn,run,state='interrupted',metrics={'passes':[]})
    assert not finish_discovery(conn,run,state='completed',metrics={})
    assert conn.execute('SELECT state,generation_calls FROM discovery_runs WHERE owner_id=%s AND id=%s',(scope.owner_id,run.run_id)).fetchone()==('interrupted',2)


def test_active_slot_expiry_and_rolling_quota(reader_source):
    from researcy.discovery.repository import load_active_metadata,reserve_discovery,finish_discovery
    from researcy.errors import APIError
    conn,scope=reader_source['conn'],reader_source['scope']
    conn.execute('UPDATE papers SET title=%s WHERE owner_id=%s AND id=%s',('Attention mechanisms',scope.owner_id,scope.paper_id))
    conn.commit()
    source=load_active_metadata(conn,scope.owner_id,scope.paper_id)
    first=reserve_discovery(conn,source,str(uuid4()))
    with pytest.raises(APIError) as caught:
        reserve_discovery(conn,source,str(uuid4()))
    assert caught.value.code=='DISCOVERY_RUN_ACTIVE'
    conn.execute("UPDATE discovery_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE owner_id=%s AND id=%s",(scope.owner_id,first.run_id))
    conn.commit()
    second=reserve_discovery(conn,source,str(uuid4()))
    assert conn.execute('SELECT state FROM discovery_runs WHERE owner_id=%s AND id=%s',(scope.owner_id,first.run_id)).fetchone()==('interrupted',)
    conn.commit()
    finish_discovery(conn,second,state='completed',metrics={})
    for _ in range(18):
        run=reserve_discovery(conn,source,str(uuid4()))
        finish_discovery(conn,run,state='failed',metrics={})
    with pytest.raises(APIError) as caught:
        reserve_discovery(conn,source,str(uuid4()))
    assert caught.value.status_code==429
    assert caught.value.retry_after>0


def test_concurrent_requests_reserve_one_owner_slot(reader_source):
    from researcy.discovery.repository import load_active_metadata,reserve_discovery
    from researcy.errors import APIError
    conn,scope=reader_source['conn'],reader_source['scope']
    conn.execute('UPDATE papers SET title=%s WHERE owner_id=%s AND id=%s',('Attention mechanisms',scope.owner_id,scope.paper_id))
    conn.commit()
    source=load_active_metadata(conn,scope.owner_id,scope.paper_id)
    barrier=Barrier(2)
    database=_database_url(conn.info.dbname)
    def attempt(_):
        with psycopg.connect(database) as separate:
            barrier.wait(timeout=5)
            try:
                reserve_discovery(separate,source,str(uuid4()))
                return 'reserved'
            except APIError as error:
                return error.code
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes=list(workers.map(attempt,range(2)))
    assert sorted(outcomes)==['DISCOVERY_RUN_ACTIVE','reserved']
    assert conn.execute("SELECT count(*) FROM discovery_runs WHERE owner_id=%s AND state='running'",(scope.owner_id,)).fetchone()==(1,)
