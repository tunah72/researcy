from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.papers.arxiv import related_title_terms
from researcy.retrieval.repository import load_ready_document
from .models import ActiveMetadata, DiscoveryReservation


RUN_SECONDS = 150


def _missing() -> APIError:
    return APIError(404,'RESOURCE_NOT_FOUND','The requested resource was not found.')


def load_active_metadata(conn: psycopg.Connection,owner_id: UUID,paper_id: UUID) -> ActiveMetadata:
    with short_transaction(conn):
        row = conn.execute('SELECT active_version_id,canonical_arxiv_id,title,abstract FROM papers WHERE owner_id=%s AND id=%s',(owner_id,paper_id)).fetchone()
    if row is None:
        raise _missing()
    version,canonical,title,abstract = row
    related_title_terms(title)
    load_ready_document(conn,owner_id,paper_id,version)
    return ActiveMetadata(owner_id,paper_id,version,canonical,' '.join(title.split()),abstract)


def reserve_discovery(conn: psycopg.Connection,source: ActiveMetadata,request_id: str) -> DiscoveryReservation:
    failure = None
    run_id = uuid4()
    with short_transaction(conn):
        if conn.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(source.owner_id,)).fetchone() is None:
            raise _missing()
        row=conn.execute('SELECT active_version_id,title,abstract,canonical_arxiv_id FROM papers WHERE owner_id=%s AND id=%s FOR UPDATE',(source.owner_id,source.paper_id)).fetchone()
        if row is None:
            raise _missing()
        if row[0]!=source.document_version or ' '.join((row[1] or '').split())!=source.title or row[2:]!=(source.abstract,source.canonical_arxiv_id):
            raise APIError(409,'DISCOVERY_SOURCE_CHANGED','This paper changed. Reload before searching.')
        conn.execute("UPDATE discovery_runs SET state='interrupted',finished_at=clock_timestamp(),error_code='DISCOVERY_INTERRUPTED' WHERE owner_id=%s AND state='running' AND lease_expires_at<=clock_timestamp()",(source.owner_id,))
        if conn.execute("SELECT id FROM discovery_runs WHERE owner_id=%s AND state='running'",(source.owner_id,)).fetchone():
            failure=APIError(409,'DISCOVERY_RUN_ACTIVE','A related-paper search is already running.')
        else:
            count,retry=conn.execute("SELECT count(*),GREATEST(1,ceil(extract(epoch FROM min(started_at)+interval '1 hour'-clock_timestamp()))) FROM discovery_runs WHERE owner_id=%s AND started_at>clock_timestamp()-interval '1 hour'",(source.owner_id,)).fetchone()
            if count>=20:
                failure=DiscoveryQuotaExceeded(int(retry))
            else:
                conn.execute("INSERT INTO discovery_runs(id,owner_id,paper_id,document_version,request_id,state,lease_expires_at) VALUES(%s,%s,%s,%s,%s,'running',clock_timestamp()+interval '165 seconds')",(run_id,source.owner_id,source.paper_id,source.document_version,request_id))
    if failure:
        raise failure
    return DiscoveryReservation(run_id,source,request_id)


class DiscoveryQuotaExceeded(APIError):
    __slots__=('retry_after',)

    def __init__(self,retry_after: int):
        super().__init__(429,'DISCOVERY_RATE_LIMITED','Please wait before searching again.')
        self.retry_after=retry_after


def record_discovery_attempt(conn: psycopg.Connection,reservation: DiscoveryReservation,kind: str) -> None:
    expected=0 if kind=='initial' else 1 if kind=='follow_up' else -1
    with short_transaction(conn):
        changed=conn.execute("UPDATE discovery_runs SET generation_calls=generation_calls+1 WHERE owner_id=%s AND id=%s AND state='running' AND generation_calls=%s AND lease_expires_at>clock_timestamp() RETURNING id",(reservation.source.owner_id,reservation.run_id,expected)).fetchone()
        if changed is None:
            raise APIError(409,'DISCOVERY_RUN_NOT_ACTIVE','This search is no longer running.')


def record_discovery_search(conn: psycopg.Connection,reservation: DiscoveryReservation) -> None:
    with short_transaction(conn):
        changed=conn.execute("UPDATE discovery_runs SET action='search_arxiv_metadata',metadata_searches=1 WHERE owner_id=%s AND id=%s AND state='running' AND generation_calls=1 AND metadata_searches=0 AND lease_expires_at>clock_timestamp() RETURNING id",(reservation.source.owner_id,reservation.run_id)).fetchone()
        if changed is None:
            raise APIError(409,'DISCOVERY_RUN_NOT_ACTIVE','This search is no longer running.')


def finish_discovery(conn: psycopg.Connection,reservation: DiscoveryReservation,*,state: str,metrics: dict,error_code: str | None=None) -> bool:
    if state not in {'completed','failed','interrupted'}:
        raise ValueError('Invalid terminal state.')
    with short_transaction(conn):
        changed=conn.execute('''UPDATE discovery_runs SET state=%s,finished_at=clock_timestamp(),usage=%s,
          error_code=%s,action=%s,inspected_unique=%s,eligible=%s,returned=%s,latency_ms=%s
          WHERE owner_id=%s AND id=%s AND state='running'
          AND (%s<>'completed' OR lease_expires_at>clock_timestamp()) RETURNING id''',
          (state,Jsonb(metrics),error_code,metrics.get('action'),metrics.get('inspected_unique',0),
           metrics.get('eligible',0),metrics.get('returned',0),metrics.get('latency_ms'),
           reservation.source.owner_id,reservation.run_id,state)).fetchone()
    return changed is not None
