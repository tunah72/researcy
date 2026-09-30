from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from researcy.errors import APIError
from .jobs import short_transaction, record_transition, MAX_SAFE_INTEGER
from .models import DocumentScope, JobSnapshot, RetryResult, STAGES


class RetryWait(APIError):
    def __init__(self, seconds: int, *, quota: bool = False):
        super().__init__(429, 'PROCESSING_RETRY_RATE_LIMITED' if quota else 'PROCESSING_RETRY_COOLDOWN',
            'Preparation cannot be retried yet.')
        self.retry_after = max(1,seconds)


def _read_owned(conn: psycopg.Connection, owner_id: UUID, job_id: UUID, *, lock: bool = False) -> dict:
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute("""SELECT j.*,v.paper_id,
            GREATEST(0,ceil(extract(epoch FROM j.run_after-clock_timestamp())))::bigint AS retry_after_seconds
            FROM ingestion_jobs j JOIN document_versions v ON v.id=j.document_version_id AND v.owner_id=j.owner_id
            WHERE j.owner_id=%s AND j.id=%s""" + (' FOR UPDATE OF j' if lock else ''), (owner_id,job_id))
        row = cursor.fetchone()
    if row is None:
        raise APIError(404,'JOB_NOT_FOUND','The job was not found.')
    return row


def _snapshot(row: dict) -> JobSnapshot:
    return JobSnapshot(DocumentScope(row['owner_id'],row['paper_id'],row['document_version_id']),row['id'],
        row['stage'],row['status'],row['failed_stage'],row['error_code'],row['failure_kind'],row['retryable'],
        row['retry_revision'],row['attempts'],row['cycle_attempts'],row['retry_after_seconds'])


def get_owned_job(conn: psycopg.Connection, owner_id: UUID, job_id: UUID) -> JobSnapshot:
    with short_transaction(conn):
        return _snapshot(_read_owned(conn,owner_id,job_id))


def retry_owned(conn: psycopg.Connection, owner_id: UUID, job_id: UUID, revision: int) -> RetryResult:
    """Replay first; only a new accepted transition consumes persistent owner quota."""
    with short_transaction(conn):
        row = _read_owned(conn,owner_id,job_id,lock=True)
        if type(revision) is not int or not 0 <= revision <= MAX_SAFE_INTEGER or revision > row['retry_revision']:
            raise APIError(409,'PROCESSING_RETRY_CONFLICT','Preparation could not be retried.')
        if revision < row['retry_revision']:
            return RetryResult(_snapshot(row),False)
        if (row['status'] != 'failed' or not row['retryable']
            or max(row['attempts'],row['lease_generation'],row['retry_revision']) >= MAX_SAFE_INTEGER):
            raise APIError(409,'PROCESSING_RETRY_CONFLICT','Preparation could not be retried.')
        if row['retry_after_seconds'] > 0:
            raise RetryWait(row['retry_after_seconds'])
        # All accepted retries for one owner serialize after the owned job lock.
        conn.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (owner_id,))
        quota = conn.execute("""SELECT coalesce(sum(request_count),0),
            GREATEST(1,ceil(extract(epoch FROM min(window_start)+interval '1 hour'-clock_timestamp())))::bigint
            FROM processing_retry_rate_limits WHERE owner_id=%s AND window_start>clock_timestamp()-interval '1 hour'""",
            (owner_id,)).fetchone()
        if quota[0] >= 5:
            raise RetryWait(quota[1],quota=True)
        completed = {entry[0] for entry in conn.execute("""SELECT stage FROM stage_manifests
            WHERE owner_id=%s AND document_version_id=%s AND profile_hash=%s""",
            (owner_id,row['document_version_id'],row['profile_hash'])).fetchall()}
        stage = next((stage for stage in STAGES if stage not in completed),'indexing')
        result = conn.execute("""UPDATE ingestion_jobs SET stage=%s,status='pending',cycle_attempts=0,
            retry_revision=retry_revision+1,run_after=clock_timestamp(),updated_at=clock_timestamp(),completed_at=NULL,
            failed_stage=NULL,error_code=NULL,failure_kind=NULL,retryable=false
            WHERE owner_id=%s AND id=%s AND retry_revision=%s AND status='failed' AND retryable
              AND run_after<=clock_timestamp()""", (stage,owner_id,job_id,revision))
        if result.rowcount != 1:
            raise APIError(409,'PROCESSING_RETRY_CONFLICT','Preparation could not be retried.')
        conn.execute("DELETE FROM processing_retry_rate_limits WHERE owner_id=%s AND window_start<=clock_timestamp()-interval '1 hour'", (owner_id,))
        conn.execute("""INSERT INTO processing_retry_rate_limits(owner_id,window_start,request_count)
            VALUES(%s,clock_timestamp(),1) ON CONFLICT(owner_id,window_start)
            DO UPDATE SET request_count=processing_retry_rate_limits.request_count+1""", (owner_id,))
        record_transition(conn,job_id,owner_id)
        return RetryResult(_snapshot(_read_owned(conn,owner_id,job_id)),True)
