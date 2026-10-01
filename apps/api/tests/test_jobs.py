from concurrent.futures import ThreadPoolExecutor
import hashlib
import time

import pytest
from psycopg.pq import TransactionStatus

from researcy.ingestion.jobs import claim_due, heartbeat, seal_profile, commit_stage, record_failure, release_owned, fenced_transaction
from researcy.ingestion.models import ProcessingProfile, StageManifest, StageFailure, LostLease


def expire(conn, job):
    conn.execute("""UPDATE ingestion_jobs SET heartbeat_at=clock_timestamp()-interval '100 seconds',
        lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s""", (job,))
    conn.commit()


def snapshot(conn, job):
    row = conn.execute("SELECT stage,status,locked_by,lease_generation,attempts,cycle_attempts FROM ingestion_jobs WHERE id=%s", (job,)).fetchone()
    conn.commit()
    return row


def test_two_claimers_cannot_own_one_job(queued_job, job_connections):
    scope, job = queued_job
    a, b = job_connections
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim_due, a, 'worker-a'), pool.submit(claim_due, b, 'worker-b')]
        leases = [future.result() for future in futures]
    won = next(lease for lease in leases if lease is not None)
    assert leases.count(None) == 1
    assert won.scope == scope and won.job_id == job
    assert snapshot(a, job) == ('validating', 'running', won.locked_by, 1, 1, 1)
    assert a.info.transaction_status == b.info.transaction_status == TransactionStatus.IDLE


def test_reclaimed_lease_rejects_all_stale_writers(queued_job, job_connections):
    _, job = queued_job
    a, b = job_connections
    old = claim_due(a, 'old-worker')
    profile = seal_profile(a, old, ProcessingProfile())
    expire(b, job)
    new = claim_due(b, 'new-worker')
    assert new.generation == old.generation + 1
    before = snapshot(b, job)
    assert heartbeat(a, old) is False
    manifest = StageManifest('validating', profile.profile_hash, hashlib.sha256(b'validated').digest(), 1, ())
    for operation in (lambda: commit_stage(a, old, manifest, 'parsing'),
                      lambda: record_failure(a, old, StageFailure('DEPENDENCY_UNAVAILABLE', 'temporary', True)),
                      lambda: release_owned(a, old)):
        with pytest.raises(LostLease):
            operation()
    assert snapshot(b, job) == before
    assert heartbeat(b, new) is True
    assert a.execute('SELECT stage FROM stage_manifests WHERE document_version_id=%s', (new.scope.document_version_id,)).fetchall() == []
    a.commit()


def test_expired_lease_is_not_revived_without_a_replacement(queued_job, job_connections):
    _, job = queued_job
    a, b = job_connections
    lease = claim_due(a, 'worker')
    expire(b, job)
    assert heartbeat(a, lease) is False
    with pytest.raises(LostLease):
        release_owned(a, lease)
    assert snapshot(b, job)[1:4] == ('running', 'worker', 1)


def test_final_fence_rolls_back_selected_manifest(queued_job, job_connections):
    scope, job = queued_job
    a, _ = job_connections
    lease = claim_due(a, 'worker')
    profile = seal_profile(a, lease, ProcessingProfile())
    with pytest.raises(LostLease):
        with fenced_transaction(a, lease):
            a.execute("UPDATE ingestion_jobs SET lease_expires_at=clock_timestamp()+interval '10 milliseconds' WHERE id=%s", (job,))
            a.execute("""INSERT INTO stage_manifests(owner_id,paper_id,document_version_id,profile_hash,stage,schema_version,content_hash,record_count,artifacts)
                VALUES(%s,%s,%s,%s,'validating',1,%s,1,'[]')""", (scope.owner_id,scope.paper_id,scope.document_version_id,profile.profile_hash,b'm'*32))
            time.sleep(.03)
    assert a.info.transaction_status == TransactionStatus.IDLE
    assert a.execute('SELECT stage FROM stage_manifests WHERE document_version_id=%s', (scope.document_version_id,)).fetchall() == []
    a.commit()
    assert snapshot(a, job)[:2] == ('validating', 'running')


def test_fifth_crashed_claim_terminalizes_instead_of_sticking(queued_job, job_connections):
    _, job = queued_job
    a, b = job_connections
    for attempt in range(1, 6):
        lease = claim_due(a, 'worker')
        assert lease.generation == attempt
        expire(b, job)
    assert claim_due(a, 'replacement') is None
    assert snapshot(a, job)[:2] == ('failed', 'failed')
    row = a.execute('SELECT attempts,cycle_attempts,error_code,retryable FROM ingestion_jobs WHERE id=%s', (job,)).fetchone()
    assert row == (5,5,'PROCESSING_INTERRUPTED',True)
    a.commit()


def test_failure_backoff_preserves_checkpoint_and_counters(queued_job, job_connections):
    scope, job = queued_job
    a, b = job_connections
    lease = claim_due(a, 'worker')
    profile = seal_profile(a, lease, ProcessingProfile())
    manifest = StageManifest('validating', profile.profile_hash, hashlib.sha256(b'validated').digest(), 1, ())
    commit_stage(a, lease, manifest, 'parsing')
    # A fresh lease snapshot is required after stage advance.
    lease = type(lease)(lease.scope,lease.job_id,lease.locked_by,lease.generation,'parsing')
    record_failure(a, lease, StageFailure('DEPENDENCY_UNAVAILABLE','temporary',True))
    assert snapshot(b, job) == ('parsing','pending',None,1,1,1)
    delay = b.execute('SELECT extract(epoch FROM run_after-clock_timestamp()) FROM ingestion_jobs WHERE id=%s', (job,)).fetchone()[0]
    assert 3 < delay <= 5
    assert b.execute('SELECT stage FROM stage_manifests WHERE document_version_id=%s', (scope.document_version_id,)).fetchall() == [('validating',)]
    b.commit()
    assert claim_due(a, 'early') is None


def test_upstream_cooldown_above_automatic_cap_ends_cycle(queued_job, job_connections):
    _, job = queued_job
    a, _ = job_connections
    lease = claim_due(a, 'worker')
    record_failure(a, lease, StageFailure('DEPENDENCY_RATE_LIMITED','temporary',True,301))
    row = a.execute('SELECT stage,status,retryable,extract(epoch FROM run_after-clock_timestamp()) FROM ingestion_jobs WHERE id=%s', (job,)).fetchone()
    assert row[:3] == ('failed','failed',True)
    assert 299 < row[3] <= 301
    a.commit()


def test_locked_oldest_job_does_not_block_another_due_job(pg_conn, queued_job, job_connections):
    from test_schema import insert_paper, insert_job

    scope, first = queued_job
    _, version = insert_paper(pg_conn, scope.owner_id, None)
    second = insert_job(pg_conn, scope.owner_id, version)
    pg_conn.commit()
    a, b = job_connections
    with a.transaction():
        a.execute('SELECT id FROM ingestion_jobs WHERE id=%s FOR UPDATE', (first,))
        lease = claim_due(b, 'worker')
        assert lease.job_id == second
    assert snapshot(a, first)[:2] == ('queued','pending')


def test_lifetime_counter_exhaustion_does_not_wrap_or_offer_retry(queued_job, job_connections):
    from researcy.ingestion.jobs import MAX_SAFE_INTEGER

    _, job = queued_job
    a, _ = job_connections
    a.execute('UPDATE ingestion_jobs SET attempts=%s WHERE id=%s', (MAX_SAFE_INTEGER,job))
    a.commit()
    assert claim_due(a, 'worker') is None
    row = a.execute('SELECT status,attempts,error_code,retryable FROM ingestion_jobs WHERE id=%s', (job,)).fetchone()
    assert row == ('failed',MAX_SAFE_INTEGER,'PROCESSING_ATTEMPT_LIMIT',False)
    a.commit()


def test_unknown_legacy_configuration_is_not_ignored(queued_job, job_connections):
    from psycopg.types.json import Jsonb
    from researcy.ingestion.models import IntegrityFailure

    scope, job = queued_job
    a, _ = job_connections
    a.execute('UPDATE document_versions SET pending_config=%s WHERE id=%s', (Jsonb({'legacy_parser':'unqualified'}),scope.document_version_id))
    a.commit()
    lease = claim_due(a, 'worker')
    with pytest.raises(IntegrityFailure) as exc:
        seal_profile(a, lease, ProcessingProfile())
    record_failure(a, lease, exc.value)
    assert snapshot(a, job)[:2] == ('failed','failed')
    assert a.execute('SELECT profile_hash FROM document_processing WHERE document_version_id=%s', (scope.document_version_id,)).fetchone() is None
    a.commit()


def test_claim_does_not_increment_or_reject_the_last_safe_retry_revision(queued_job, job_connections):
    from researcy.ingestion.jobs import MAX_SAFE_INTEGER
    from researcy.ingestion.retry import retry_owned
    from test_processing_retry import terminal

    scope, job=queued_job
    a,_=job_connections
    terminal(a,job)
    a.execute('UPDATE ingestion_jobs SET retry_revision=%s WHERE id=%s', (MAX_SAFE_INTEGER-1,job));a.commit()
    assert retry_owned(a,scope.owner_id,job,MAX_SAFE_INTEGER-1).accepted is True
    lease=claim_due(a,'last-revision-worker')
    assert lease is not None
    assert snapshot(a,job)[1]=='running'
    assert a.execute('SELECT retry_revision FROM ingestion_jobs WHERE id=%s', (job,)).fetchone()[0]==MAX_SAFE_INTEGER
    a.commit()


@pytest.mark.parametrize("kind", ["temporary","unknown-provider-kind"])
def test_failure_metadata_never_persists_provider_text(queued_job, job_connections, kind):
    _,job=queued_job
    a,_=job_connections
    lease=claim_due(a,'worker')
    record_failure(a,lease,StageFailure('provider response containing private document text',kind,True))
    row=a.execute('SELECT status,error_code,failure_kind,retryable FROM ingestion_jobs WHERE id=%s', (job,)).fetchone()
    assert row==('failed','PROCESSING_INTEGRITY_FAILURE','integrity',False)
    assert a.execute('SELECT error_code FROM ingestion_transitions WHERE job_id=%s ORDER BY id DESC LIMIT 1', (job,)).fetchone()[0]=='PROCESSING_INTEGRITY_FAILURE'
    a.commit()
