from contextlib import contextmanager
from dataclasses import asdict
from typing import Iterator

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from researcy.config import get_settings
from .models import DocumentScope, Lease, ProcessingProfile, StageManifest, StageFailure, IntegrityFailure, LostLease, STAGES


MAX_SAFE_INTEGER = (1 << 53) - 1
BACKOFF = (5, 15, 45, 120)
_SAFE_FAILURES = {
    "DEPENDENCY_UNAVAILABLE": ("temporary",True),
    "DEPENDENCY_RATE_LIMITED": ("temporary",True),
    "PDF_SANDBOX_UNAVAILABLE": ("temporary",True),
    "PDF_TOO_LARGE": ("resource_limit",False),
    "PDF_TOO_MANY_PAGES": ("resource_limit",False),
    "PDF_PARSE_RESOURCE_LIMIT": ("resource_limit",False),
    "PROCESSING_RESOURCE_LIMIT": ("resource_limit",False),
    "EMBEDDING_CONTEXT_LIMIT": ("resource_limit",False),
    "EMBEDDING_MODEL_MISMATCH": ("integrity",False),
    "EMBEDDING_OUTPUT_INVALID": ("integrity",False),
    "PDF_PARSE_TIMEOUT": ("resource_limit",False),
    "PDF_ENCRYPTED": ("unsupported",False),
    "PDF_INVALID": ("unsupported",False),
    "PDF_NO_TEXT": ("unsupported",False),
    "PDF_PARSE_GEOMETRY_INVALID": ("unsupported",False),
    "PARSER_OUTPUT_INVALID": ("integrity",False),
    "PARSER_OUTPUT_CONFLICT": ("integrity",False),
    "PROCESSING_CONFIGURATION_INVALID": ("integrity",False),
    "PROCESSING_INTEGRITY_FAILURE": ("integrity",False),
}


@contextmanager
def short_transaction(conn: psycopg.Connection) -> Iterator[None]:
    """Require an idle connection: nesting would retain locks during external work."""
    if conn.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("job operations require an idle connection")
    settings = get_settings()
    with conn.transaction():
        conn.execute("SELECT set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
            (f"{settings.job_statement_timeout_ms}ms", f"{settings.job_lock_timeout_ms}ms"))
        yield


def require_owned(conn: psycopg.Connection, lease: Lease) -> dict:
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute("""SELECT j.*,v.paper_id FROM ingestion_jobs j JOIN document_versions v
            ON v.id=j.document_version_id AND v.owner_id=j.owner_id
            WHERE j.id=%s AND j.owner_id=%s AND j.document_version_id=%s AND v.paper_id=%s
              AND j.locked_by=%s AND j.lease_generation=%s AND j.status='running'
              AND j.lease_expires_at>clock_timestamp() FOR UPDATE OF j""",
            (lease.job_id,lease.scope.owner_id,lease.scope.document_version_id,lease.scope.paper_id,lease.locked_by,lease.generation))
        row = cursor.fetchone()
    if row is None:
        raise LostLease()
    return row


@contextmanager
def fenced_transaction(conn: psycopg.Connection, lease: Lease, *, ends_lease: bool = False) -> Iterator[dict]:
    """Lock before writes; recheck DB time before committing the complete batch."""
    with short_transaction(conn):
        row = require_owned(conn, lease)
        yield row
        if ends_lease:
            # The row lock prevents replacement; preserve the pre-release deadline.
            final = conn.execute("""SELECT 1 FROM ingestion_jobs WHERE id=%s AND owner_id=%s
                AND document_version_id=%s AND lease_generation=%s AND locked_by IS NULL
                AND status IN ('pending','failed','succeeded') AND clock_timestamp()<%s""",
                (lease.job_id,lease.scope.owner_id,lease.scope.document_version_id,lease.generation,row['lease_expires_at'])).fetchone()
            if final is None:
                raise LostLease()
        else:
            require_owned(conn, lease)


def record_transition(conn: psycopg.Connection, job_id, owner_id) -> None:
    conn.execute("""INSERT INTO ingestion_transitions(owner_id,document_version_id,job_id,stage,status,lease_generation,attempt,error_code)
        SELECT owner_id,document_version_id,id,stage,status,lease_generation,attempts,error_code
        FROM ingestion_jobs WHERE id=%s AND owner_id=%s""", (job_id,owner_id))


def claim_due(conn: psycopg.Connection, worker_id: str) -> Lease | None:
    """Claim one row and close its transaction before any expensive work."""
    if type(worker_id) is not str or not worker_id or len(worker_id) > 128:
        raise ValueError("invalid worker identity")
    with short_transaction(conn):
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""SELECT j.*,v.paper_id FROM ingestion_jobs j JOIN document_versions v
                ON v.owner_id=j.owner_id AND v.id=j.document_version_id
                WHERE (j.status='pending' AND j.run_after<=clock_timestamp())
                   OR (j.status='running' AND j.lease_expires_at<=clock_timestamp())
                ORDER BY CASE WHEN j.status='running' THEN j.lease_expires_at ELSE j.run_after END,j.created_at,j.id
                FOR UPDATE OF j SKIP LOCKED LIMIT 1""")
            row = cursor.fetchone()
        if row is None:
            return None
        stage = 'validating' if row['stage'] == 'queued' else row['stage']
        exhausted = row['cycle_attempts'] >= 5
        overflow = max(row['attempts'],row['lease_generation']) >= MAX_SAFE_INTEGER
        if exhausted or overflow:
            conn.execute("""UPDATE ingestion_jobs SET status='failed',stage='failed',failed_stage=%s,
                error_code=%s,failure_kind=%s,retryable=%s,completed_at=clock_timestamp(),
                updated_at=clock_timestamp(),run_after=clock_timestamp()+%s*interval '1 second',
                locked_by=NULL,lease_expires_at=NULL,heartbeat_at=NULL WHERE id=%s AND owner_id=%s""",
                (stage,'PROCESSING_ATTEMPT_LIMIT' if overflow else 'PROCESSING_INTERRUPTED',
                 'integrity' if overflow else 'temporary',not overflow,0 if overflow else 120,row['id'],row['owner_id']))
            record_transition(conn,row['id'],row['owner_id'])
            return None
        generation = row['lease_generation'] + 1
        conn.execute("""UPDATE ingestion_jobs SET status='running',stage=%s,locked_by=%s,lease_generation=%s,
            lease_expires_at=clock_timestamp()+%s*interval '1 second',heartbeat_at=clock_timestamp(),
            attempts=attempts+1,cycle_attempts=cycle_attempts+1,updated_at=clock_timestamp(),
            completed_at=NULL,failed_stage=NULL,error_code=NULL,failure_kind=NULL,retryable=false
            WHERE id=%s AND owner_id=%s""",
            (stage,worker_id,generation,get_settings().job_lease_seconds,row['id'],row['owner_id']))
        record_transition(conn,row['id'],row['owner_id'])
        return Lease(DocumentScope(row['owner_id'],row['paper_id'],row['document_version_id']),row['id'],worker_id,generation,stage)


def heartbeat(conn: psycopg.Connection, lease: Lease) -> bool:
    with short_transaction(conn):
        result = conn.execute("""UPDATE ingestion_jobs j SET heartbeat_at=clock_timestamp(),
            lease_expires_at=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp()
            FROM document_versions v WHERE j.id=%s AND j.owner_id=%s AND j.document_version_id=%s
            AND v.id=j.document_version_id AND v.owner_id=j.owner_id AND v.paper_id=%s
            AND j.locked_by=%s AND j.lease_generation=%s AND j.status='running'
            AND j.lease_expires_at>clock_timestamp()""",
            (get_settings().job_lease_seconds,lease.job_id,lease.scope.owner_id,lease.scope.document_version_id,
             lease.scope.paper_id,lease.locked_by,lease.generation))
        return result.rowcount == 1


def seal_profile(conn: psycopg.Connection, lease: Lease, profile: ProcessingProfile) -> ProcessingProfile:
    with fenced_transaction(conn,lease) as row:
        source = conn.execute("""SELECT sha256,pending_config FROM document_versions
            WHERE id=%s AND owner_id=%s AND paper_id=%s FOR UPDATE""",
            (lease.scope.document_version_id,lease.scope.owner_id,lease.scope.paper_id)).fetchone()
        existing = conn.execute("""SELECT profile,profile_hash FROM document_processing
            WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s""",
            (lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id)).fetchone()
        if existing:
            try:
                selected = ProcessingProfile(**existing[0])
            except (ValueError,TypeError):
                raise IntegrityFailure('PROCESSING_CONFIGURATION_INVALID') from None
            if selected.profile_hash != existing[1] or selected.profile_hash != profile.profile_hash:
                raise IntegrityFailure('PROCESSING_CONFIGURATION_INVALID')
            return selected
        # M1 has no nonempty supported configuration schema; do not ignore legacy input.
        if source[1] not in (None, {}):
            raise IntegrityFailure('PROCESSING_CONFIGURATION_INVALID')
        conn.execute("""INSERT INTO document_processing
            (owner_id,paper_id,document_version_id,original_sha256,profile_hash,profile,index_version)
            VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id,source[0],
             profile.profile_hash,Jsonb(asdict(profile)),profile.index_version))
        conn.execute("UPDATE ingestion_jobs SET profile_hash=%s,updated_at=clock_timestamp() WHERE id=%s AND owner_id=%s",
            (profile.profile_hash,lease.job_id,lease.scope.owner_id))
        return profile


def commit_stage(conn: psycopg.Connection, lease: Lease, manifest: StageManifest, next_stage: str) -> None:
    position = STAGES.index(manifest.stage)
    expected = STAGES[position+1] if position+1 < len(STAGES) else 'indexing'
    if next_stage != expected:
        raise IntegrityFailure()
    artifacts = [dict(key=ref.key,sha256=ref.sha256.hex(),byte_count=ref.byte_count) for ref in manifest.artifacts]
    with fenced_transaction(conn,lease) as row:
        if row['stage'] != manifest.stage or row['profile_hash'] != manifest.profile_hash:
            raise IntegrityFailure()
        result = conn.execute("""INSERT INTO stage_manifests
            (owner_id,paper_id,document_version_id,profile_hash,stage,schema_version,content_hash,record_count,artifacts)
            VALUES(%s,%s,%s,%s,%s,1,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING content_hash""",
            (lease.scope.owner_id,lease.scope.paper_id,lease.scope.document_version_id,manifest.profile_hash,
             manifest.stage,manifest.content_hash,manifest.record_count,Jsonb(artifacts))).fetchone()
        if result is None:
            existing = conn.execute("""SELECT content_hash,record_count,artifacts FROM stage_manifests
                WHERE owner_id=%s AND document_version_id=%s AND profile_hash=%s AND stage=%s""",
                (lease.scope.owner_id,lease.scope.document_version_id,manifest.profile_hash,manifest.stage)).fetchone()
            if existing != (manifest.content_hash,manifest.record_count,artifacts):
                raise IntegrityFailure()
        conn.execute("UPDATE ingestion_jobs SET stage=%s,updated_at=clock_timestamp() WHERE id=%s AND owner_id=%s", (next_stage,lease.job_id,lease.scope.owner_id))
        record_transition(conn,lease.job_id,lease.scope.owner_id)


def record_failure(conn: psycopg.Connection, lease: Lease, failure: StageFailure) -> None:
    kind,retryable = _SAFE_FAILURES.get(failure.code,("integrity",False))
    code = failure.code if failure.code in _SAFE_FAILURES else "PROCESSING_INTEGRITY_FAILURE"
    with fenced_transaction(conn,lease,ends_lease=True) as row:
        temporary = kind == 'temporary' and retryable
        automatic = temporary and row['cycle_attempts'] < 5 and failure.retry_after_seconds <= 300
        delay = max(BACKOFF[min(row['cycle_attempts']-1,3)],failure.retry_after_seconds) if temporary else 0
        conn.execute("""UPDATE ingestion_jobs SET stage=%s,status=%s,failed_stage=%s,error_code=%s,
            failure_kind=%s,retryable=%s,completed_at=CASE WHEN %s THEN NULL ELSE clock_timestamp() END,
            run_after=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp(),
            locked_by=NULL,lease_expires_at=NULL,heartbeat_at=NULL WHERE id=%s AND owner_id=%s
            AND locked_by=%s AND lease_generation=%s AND status='running' AND lease_expires_at>clock_timestamp()""",
            (row['stage'] if automatic else 'failed','pending' if automatic else 'failed',row['stage'],code,
             kind,temporary and not automatic,automatic,delay,
             lease.job_id,lease.scope.owner_id,lease.locked_by,lease.generation))
        record_transition(conn,lease.job_id,lease.scope.owner_id)


def release_owned(conn: psycopg.Connection, lease: Lease) -> None:
    with fenced_transaction(conn,lease,ends_lease=True):
        conn.execute("""UPDATE ingestion_jobs SET status='pending',run_after=clock_timestamp(),updated_at=clock_timestamp(),
            locked_by=NULL,lease_expires_at=NULL,heartbeat_at=NULL WHERE id=%s AND owner_id=%s
            AND locked_by=%s AND lease_generation=%s AND status='running' AND lease_expires_at>clock_timestamp()""",
            (lease.job_id,lease.scope.owner_id,lease.locked_by,lease.generation))
        record_transition(conn,lease.job_id,lease.scope.owner_id)
