from uuid import uuid4

import pytest

from test_intake import client,_auth_headers
from test_jobs import snapshot
from researcy.ingestion.jobs import short_transaction


def terminal_retryable(conn,job):
    with short_transaction(conn):
        conn.execute("UPDATE ingestion_jobs SET stage='failed',status='failed',failed_stage='validating',error_code='DEPENDENCY_UNAVAILABLE',failure_kind='temporary',retryable=true,completed_at=clock_timestamp(),run_after=clock_timestamp()-interval '1 second' WHERE id=%s",(job,))


def test_job_is_owned_and_safe(client,queued_job,pg_conn):
    scope,job=queued_job;_auth_headers(client,pg_conn,scope.owner_id)
    result=client.get(f'/api/jobs/{job}')
    assert result.status_code==200
    body=result.json()
    assert body['job_id']==str(job) and body['paper_id']==str(scope.paper_id)
    assert body['preparation']=={'state':'waiting','reason':None,'retryable':False,'retry_after_seconds':0}
    assert set(body)=={'job_id','paper_id','document_version','stage','status','failed_stage','error_code','retry_revision','preparation','request_id'}


@pytest.mark.parametrize('mutation',[False,True])
def test_foreign_and_missing_job_are_indistinguishable_before_body_parsing(client,queued_job,pg_conn,mutation):
    scope,job=queued_job
    owner=pg_conn.execute("INSERT INTO users(issuer,sub) VALUES('https://accounts.google.com',%s) RETURNING id",('foreign-'+uuid4().hex,)).fetchone()[0];pg_conn.commit()
    headers=_auth_headers(client,pg_conn,owner)
    def request(identity):
        if mutation:return client.post(f'/api/jobs/{identity}/retry',headers=headers,content=b'not-json')
        return client.get(f'/api/jobs/{identity}')
    foreign=request(job);missing=request(uuid4())
    assert foreign.status_code==missing.status_code==404
    assert foreign.json()['code']==missing.json()['code']=='JOB_NOT_FOUND'
    assert foreign.json()['message']==missing.json()['message']


@pytest.mark.parametrize('failure',['unauthenticated','csrf','origin'])
def test_mutation_authorizes_before_malformed_body_and_quota(client,queued_job,pg_conn,failure):
    scope,job=queued_job;headers={}
    if failure!='unauthenticated':headers=_auth_headers(client,pg_conn,scope.owner_id)
    if failure=='csrf':headers.pop('x-csrf-token')
    if failure=='origin':headers['Origin']='https://untrusted.invalid'
    response=client.post(f'/api/jobs/{job}/retry',headers=headers,content=b'not-json')
    assert response.status_code==(401 if failure=='unauthenticated' else 403)
    assert snapshot(pg_conn,job)==('queued','pending',None,0,0,0)
    assert pg_conn.execute('SELECT count(*) FROM processing_retry_rate_limits').fetchone()[0]==0;pg_conn.commit()


def test_accepted_revision_replay_after_later_failure_never_requeues(client,queued_job,pg_conn):
    scope,job=queued_job;headers=_auth_headers(client,pg_conn,scope.owner_id);terminal_retryable(pg_conn,job)
    first=client.post(f'/api/jobs/{job}/retry',headers=headers,json={'retry_revision':0})
    assert first.status_code==202
    assert first.json()['retry_revision']==1
    assert first.json()['preparation']['state']=='delayed'
    terminal_retryable(pg_conn,job)
    replay=client.post(f'/api/jobs/{job}/retry',headers=headers,json={'retry_revision':0})
    assert replay.status_code==200 and replay.json()['status']=='failed' and replay.json()['retry_revision']==1
    assert pg_conn.execute('SELECT sum(request_count) FROM processing_retry_rate_limits WHERE owner_id=%s',(scope.owner_id,)).fetchone()[0]==1;pg_conn.commit()


@pytest.mark.parametrize('body',[{'retry_revision':True},{'retry_revision':-1},{'retry_revision':'0'},{'retry_revision':0,'owner_id':'foreign'},{'retry_revision':2**53},{}])
def test_retry_body_cannot_supply_coerced_or_extra_authority(client,queued_job,pg_conn,body):
    scope,job=queued_job;headers=_auth_headers(client,pg_conn,scope.owner_id);terminal_retryable(pg_conn,job)
    result=client.post(f'/api/jobs/{job}/retry',headers=headers,json=body)
    assert result.status_code==422
    assert snapshot(pg_conn,job)[:2]==('failed','failed')


@pytest.mark.parametrize('stage,status,attempts,reason,expected',[
    ('queued','pending',0,None,'waiting'),('parsing','running',1,None,'preparing'),
    ('embedding','pending',2,'temporary','delayed'),('failed','failed',1,'unsupported','failed')])
def test_library_and_detail_project_persisted_preparation(client,queued_job,pg_conn,stage,status,attempts,reason,expected):
    scope,job=queued_job;_auth_headers(client,pg_conn,scope.owner_id)
    with short_transaction(pg_conn):
        if status=='running':
            pg_conn.execute("UPDATE ingestion_jobs SET stage=%s,status=%s,attempts=%s,cycle_attempts=%s,locked_by='test-worker',lease_generation=1,heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+interval '90 seconds' WHERE id=%s",(stage,status,attempts,attempts,job))
        elif status=='failed':
            pg_conn.execute("UPDATE ingestion_jobs SET stage='failed',status='failed',attempts=%s,cycle_attempts=%s,failed_stage='validating',error_code='PDF_INVALID',failure_kind=%s,completed_at=clock_timestamp() WHERE id=%s",(attempts,attempts,reason,job))
        else:
            pg_conn.execute('UPDATE ingestion_jobs SET stage=%s,status=%s,attempts=%s,cycle_attempts=%s,failure_kind=%s WHERE id=%s',(stage,status,attempts,attempts,reason,job))
    detail=client.get(f'/api/papers/{scope.paper_id}');listing=client.get('/api/papers')
    assert detail.status_code==listing.status_code==200
    for paper in (detail.json(),listing.json()['papers'][0]):
        assert paper['stage']==stage and paper['preparation']['state']==expected and paper['job_id']==str(job)


@pytest.mark.parametrize('counter',['attempts','lease_generation','retry_revision'])
def test_exhausted_lifetime_counter_disallows_retry_in_every_owned_projection(client,queued_job,pg_conn,counter):
    from psycopg import sql
    scope,job=queued_job;headers=_auth_headers(client,pg_conn,scope.owner_id)
    terminal_retryable(pg_conn,job)
    with short_transaction(pg_conn):
        pg_conn.execute(sql.SQL('UPDATE ingestion_jobs SET {}=%s WHERE id=%s').format(sql.Identifier(counter)),((1<<53)-1,job))
    projected=client.get(f'/api/jobs/{job}')
    detail=client.get(f'/api/papers/{scope.paper_id}')
    listing=client.get('/api/papers')
    for response in (projected,detail,listing):
        assert response.status_code==200
    for item in (projected.json(),detail.json(),listing.json()['papers'][0]):
        assert item['preparation']['state']=='failed' and item['preparation']['retryable'] is False
    denied=client.post(f'/api/jobs/{job}/retry',headers=headers,json={'retry_revision':projected.json()['retry_revision']})
    assert denied.status_code==409 and denied.json()['code']=='JOB_NOT_RETRYABLE'


def test_persisted_retry_revision_cannot_exceed_browser_exact_integer_boundary(pg_conn,queued_job):
    import psycopg
    _,job=queued_job
    with pytest.raises(psycopg.errors.CheckViolation):
        with short_transaction(pg_conn):
            pg_conn.execute('UPDATE ingestion_jobs SET retry_revision=%s WHERE id=%s',(1<<53,job))


def test_stale_retry_waiting_for_publication_returns_current_complete_snapshot(client,selected_index,pg_conn,monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from researcy.retrieval import index

    scope=selected_index['scope'];lease=selected_index['lease']
    headers=_auth_headers(client,pg_conn,scope.owner_id)
    with short_transaction(pg_conn):
        pg_conn.execute('UPDATE ingestion_jobs SET retry_revision=1 WHERE id=%s',(lease.job_id,))
    receipt=index.index_selected(lease,time.monotonic()+60)
    publication_written=Event();release_commit=Event()
    record=index.record_transition
    def hold_publication(conn,job_id,owner_id):
        record(conn,job_id,owner_id)
        publication_written.set()
        assert release_commit.wait(5)
    monkeypatch.setattr(index,'record_transition',hold_publication)
    with ThreadPoolExecutor(max_workers=2) as executor:
        publish=executor.submit(index.publish_ready,selected_index['conn'],lease,receipt)
        assert publication_written.wait(5)
        replay=executor.submit(client.post,f'/api/jobs/{lease.job_id}/retry',headers=headers,json={'retry_revision':0})
        try:
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                waiting=pg_conn.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%FOR UPDATE OF j%')").fetchone()[0]
                pg_conn.commit()
                if waiting:break
                time.sleep(.01)
            assert waiting
        finally:
            release_commit.set()
        publish.result(timeout=5)
        result=replay.result(timeout=5)
    assert result.status_code==200
    assert result.json()['stage']=='ready' and result.json()['status']=='succeeded'
    assert result.json()['retry_revision']==1 and result.json()['preparation']['state']=='complete'
