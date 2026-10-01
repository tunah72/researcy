from dataclasses import replace
from threading import Event

import pytest

from researcy.ingestion import worker
from researcy.ingestion.models import LostLease
from test_jobs import expire,snapshot

@pytest.fixture(autouse=True)
def worker_database(pg_conn,monkeypatch):
    from conftest import _database_url
    monkeypatch.setenv('DATABASE_URL',_database_url(pg_conn.info.dbname))


def test_stage_deadline_stops_heartbeat_and_terminalizes_owned_work(queued_job,job_connections,monkeypatch):
    _,job=queued_job;conn,_=job_connections
    settings=replace(worker.get_settings(),worker_stage_deadlines=(("validating",.15),),job_heartbeat_seconds=.05)
    monkeypatch.setattr(worker,'get_settings',lambda:settings)
    def blocked_stage(lease,deadline,cancel):
        assert cancel.wait(2), 'A stuck stage must be cancelled by its deadline'
        raise LostLease()
    monkeypatch.setattr(worker,'execute_stage',blocked_stage)
    assert worker.run_once('deadline-worker') is True
    assert snapshot(conn,job)[:3]==('failed','failed',None)
    row=conn.execute('SELECT error_code,retryable FROM ingestion_jobs WHERE id=%s',(job,)).fetchone();conn.commit()
    assert row==('PROCESSING_RESOURCE_LIMIT',False)


def test_lost_heartbeat_does_not_overwrite_replacement_progress(queued_job,job_connections,monkeypatch):
    from researcy.ingestion.jobs import claim_due
    _,job=queued_job;conn,other=job_connections
    settings=replace(worker.get_settings(),job_heartbeat_seconds=.05)
    monkeypatch.setattr(worker,'get_settings',lambda:settings)
    replacement=[]
    def interrupted_stage(lease,deadline,cancel):
        expire(other,job);replacement.append(claim_due(other,'replacement-worker'))
        assert cancel.wait(2), 'Lost lease must cancel expensive work'
        raise LostLease()
    monkeypatch.setattr(worker,'execute_stage',interrupted_stage)
    assert worker.run_once('stale-worker') is True
    assert snapshot(conn,job)[:4]==('validating','running','replacement-worker',replacement[0].generation)


def test_shutdown_releases_current_lease_without_erasing_checkpoint(queued_job,job_connections,monkeypatch):
    _,job=queued_job;conn,_=job_connections;stop=Event()
    def shutdown_stage(lease,deadline,cancel):
        stop.set()
        assert cancel.wait(2), 'Shutdown must cancel current stage'
        raise LostLease()
    monkeypatch.setattr(worker,'execute_stage',shutdown_stage)
    assert worker.run_once('shutdown-worker',stop=stop) is True
    assert snapshot(conn,job)[:4]==('validating','pending',None,1)
    before=snapshot(conn,job)
    assert worker.run_once('shutdown-worker',stop=stop) is False
    assert snapshot(conn,job)==before

def test_shutdown_delivered_during_connect_does_not_consume_claim(queued_job,job_connections,monkeypatch):
    from contextlib import contextmanager

    _,job=queued_job;conn,_=job_connections;stop=Event();original=worker.get_conn
    @contextmanager
    def shutdown_connect():
        with original() as connected:
            stop.set()
            yield connected
    monkeypatch.setattr(worker,'get_conn',shutdown_connect)
    assert worker.run_once('not-started-worker',stop=stop) is False
    assert snapshot(conn,job)==('queued','pending',None,0,0,0)


@pytest.mark.parametrize('stage',['embedding','indexing'])
def test_dependency_stage_watchdog_timeout_keeps_automatic_retry(queued_job,job_connections,monkeypatch,stage):
    from researcy.ingestion.jobs import short_transaction

    _,job=queued_job;conn,_=job_connections
    with short_transaction(conn):
        conn.execute('UPDATE ingestion_jobs SET stage=%s WHERE id=%s',(stage,job))
    settings=replace(worker.get_settings(),worker_stage_deadlines=((stage,.1),),job_heartbeat_seconds=.05)
    monkeypatch.setattr(worker,'get_settings',lambda:settings)
    def blocked_dependency(lease,deadline,cancel):
        assert cancel.wait(2)
        raise LostLease()
    monkeypatch.setattr(worker,'execute_stage',blocked_dependency)
    assert worker.run_once('dependency-deadline') is True
    assert snapshot(conn,job)[:3]==(stage,'pending',None)
    row=conn.execute('SELECT error_code,failure_kind,failed_stage FROM ingestion_jobs WHERE id=%s',(job,)).fetchone();conn.commit()
    assert row==('DEPENDENCY_UNAVAILABLE','temporary',stage)


def test_expired_previous_stage_budget_does_not_fail_unstarted_checkpoint(queued_job,job_connections,monkeypatch):
    from researcy.ingestion.jobs import commit_stage,seal_profile,short_transaction
    from researcy.ingestion.models import ProcessingProfile,StageManifest

    _,job=queued_job;conn,_=job_connections
    settings=replace(worker.get_settings(),worker_stage_deadlines=(('validating',.1),('parsing',60)),job_heartbeat_seconds=.05)
    monkeypatch.setattr(worker,'get_settings',lambda:settings)
    def checkpoint_then_delayed_return(lease,deadline,cancel):
        with worker.get_conn() as stage_conn:
            profile=seal_profile(stage_conn,lease,ProcessingProfile())
            with short_transaction(stage_conn):
                source=stage_conn.execute('SELECT sha256 FROM document_versions WHERE id=%s',(lease.scope.document_version_id,)).fetchone()[0]
            commit_stage(stage_conn,lease,StageManifest('validating',profile.profile_hash,bytes(source),1,()),'parsing')
        assert cancel.wait(2)
    monkeypatch.setattr(worker,'execute_stage',checkpoint_then_delayed_return)
    assert worker.run_once('transition-deadline') is True
    assert snapshot(conn,job)[:3]==('parsing','pending',None)
    row=conn.execute('SELECT error_code,failed_stage FROM ingestion_jobs WHERE id=%s',(job,)).fetchone();conn.commit()
    assert row==(None,None)

def test_worker_entry_refuses_api_role_before_consuming_jobs(queued_job,job_connections,monkeypatch):
    _,job=queued_job;conn,_=job_connections
    monkeypatch.setenv('APP_ROLE','api')
    def forbidden_claim(*args,**kwargs):
        raise AssertionError('An API-role process must refuse startup before claiming')
    monkeypatch.setattr(worker,'run_once',forbidden_claim)
    with pytest.raises(ValueError,match='worker role'):
        worker.main()
    assert snapshot(conn,job)==('queued','pending',None,0,0,0)
