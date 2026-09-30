from uuid import uuid4

import pytest

from researcy.errors import APIError
from researcy.ingestion.jobs import claim_due, record_failure
from researcy.ingestion.models import StageFailure
from researcy.ingestion.retry import retry_owned
from test_schema import insert_paper, insert_job
from test_jobs import snapshot


def terminal(conn, job, retryable=True):
    conn.execute("""UPDATE ingestion_jobs SET stage='failed',status='failed',failed_stage='validating',
        completed_at=clock_timestamp(),error_code='DEPENDENCY_UNAVAILABLE',failure_kind='temporary',
        retryable=%s,attempts=5,cycle_attempts=5,lease_generation=5,
        locked_by=NULL,heartbeat_at=NULL,lease_expires_at=NULL,run_after=clock_timestamp()-interval '1 second'
        WHERE id=%s""", (retryable,job))
    conn.commit()


def test_delayed_duplicate_retry_cannot_start_a_second_cycle(queued_job, job_connections):
    scope, job = queued_job
    a, b = job_connections
    terminal(a, job)
    accepted = retry_owned(a, scope.owner_id, job, 0)
    assert accepted.accepted is True
    assert accepted.job.retry_revision == 1
    lease = claim_due(b, 'new-cycle')
    # End the new cycle after one attempt with a long dependency cooldown.
    record_failure(b, lease, StageFailure('DEPENDENCY_RATE_LIMITED','temporary',True,301))
    before = snapshot(b, job)
    replay = retry_owned(a, scope.owner_id, job, 0)
    assert replay.accepted is False and replay.job.status == 'failed'
    assert replay.job.retry_revision == 1
    assert snapshot(b, job) == before
    assert replay.job.attempts == 6 and replay.job.cycle_attempts == 1


def test_future_retry_revision_and_unsupported_input_do_not_reset_job(queued_job, job_connections):
    scope, job = queued_job
    a, _ = job_connections
    terminal(a, job, retryable=False)
    before = snapshot(a, job)
    for revision in (0, 1):
        with pytest.raises(APIError) as exc:
            retry_owned(a, scope.owner_id, job, revision)
        assert exc.value.status_code == 409
        assert snapshot(a, job) == before


def test_retry_foreign_and_nonexistent_are_indistinguishable(queued_job, job_connections):
    scope, job = queued_job
    a, _ = job_connections
    terminal(a, job)
    errors = []
    for owner, target in ((uuid4(),job), (scope.owner_id,uuid4())):
        with pytest.raises(APIError) as exc:
            retry_owned(a, owner, target, 0)
        errors.append((exc.value.status_code,exc.value.code,exc.value.message))
    assert errors[0] == errors[1] and errors[0][0] == 404
    assert snapshot(a, job)[:2] == ('failed','failed')


def test_manual_retry_cooldown_is_enforced_before_new_transition(queued_job, job_connections):
    scope, job = queued_job
    a, _ = job_connections
    terminal(a, job)
    a.execute("UPDATE ingestion_jobs SET run_after=clock_timestamp()+interval '30 seconds' WHERE id=%s", (job,));a.commit()
    with pytest.raises(APIError) as exc:
        retry_owned(a, scope.owner_id, job, 0)
    assert exc.value.status_code == 429
    assert 28 <= exc.value.retry_after <= 30
    assert snapshot(a, job)[:2] == ('failed','failed')


def test_owner_quota_counts_only_newly_accepted_retries(queued_job, job_connections):
    scope, first = queued_job
    a, _ = job_connections
    jobs = [first]
    for _ in range(5):
        _, version = insert_paper(a, scope.owner_id, None)
        jobs.append(insert_job(a, scope.owner_id, version))
    a.commit()
    for job in jobs:
        terminal(a, job)
    for job in jobs[:5]:
        assert retry_owned(a, scope.owner_id, job, 0).accepted is True
    assert retry_owned(a, scope.owner_id, first, 0).accepted is False
    with pytest.raises(APIError) as exc:
        retry_owned(a, scope.owner_id, jobs[5], 0)
    assert exc.value.status_code == 429
    assert snapshot(a, jobs[5])[:2] == ('failed','failed')
    total = a.execute('SELECT sum(request_count) FROM processing_retry_rate_limits WHERE owner_id=%s', (scope.owner_id,)).fetchone()[0]
    assert total == 5
    a.commit()


def test_concurrent_duplicate_retry_has_one_transition_and_one_quota_charge(queued_job, job_connections):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    scope, job = queued_job
    a, b = job_connections
    terminal(a, job)
    start = Barrier(2)
    def submit(conn):
        start.wait()
        return retry_owned(conn,scope.owner_id,job,0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit,a),pool.submit(submit,b)]
        results = [future.result() for future in futures]
    assert sorted(result.accepted for result in results) == [False,True]
    assert {result.job.retry_revision for result in results} == {1}
    assert snapshot(a,job) == ('validating','pending',None,5,5,0)
    assert a.execute('SELECT sum(request_count) FROM processing_retry_rate_limits WHERE owner_id=%s', (scope.owner_id,)).fetchone()[0] == 1
    assert a.execute('SELECT stage,status FROM ingestion_transitions WHERE job_id=%s', (job,)).fetchall() == [('validating','pending')]
    a.commit()
