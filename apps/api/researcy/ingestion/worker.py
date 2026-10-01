import os
import signal
import time
from dataclasses import replace
from threading import Event,Lock,Thread
from uuid import uuid4

import psycopg

from researcy.config import get_settings
from researcy.db import get_conn
from .jobs import claim_due,heartbeat,record_failure,release_owned,require_owned,short_transaction
from .models import LostLease,StageFailure
from .stages import execute_stage


def run_once(worker_id: str,*,stop: Event | None=None) -> bool:
    stop=stop if stop is not None else Event()
    if stop.is_set():
        return False
    settings=get_settings()
    with get_conn() as conn:
        if stop.is_set():
            return False
        lease=claim_due(conn,worker_id)
    if lease is None:
        return False
    cancel=Event();finished=Event();lock=Lock()
    claim_deadline=time.monotonic()+settings.worker_claim_deadline_seconds
    stage_deadlines=dict(settings.worker_stage_deadlines)
    budget=[min(claim_deadline,time.monotonic()+stage_deadlines[lease.stage]),lease.stage]
    reason=[None]
    expired_stage=[None]

    def watch() -> None:
        next_heartbeat=time.monotonic()+settings.job_heartbeat_seconds
        while not finished.wait(.05):
            with lock:
                expired=time.monotonic()>=budget[0]
                deadline_stage=budget[1]
            if stop.is_set() or expired:
                reason[0]='shutdown' if stop.is_set() else 'deadline'
                expired_stage[0]=deadline_stage
                cancel.set();return
            if time.monotonic()>=next_heartbeat:
                try:
                    with get_conn() as conn:
                        owned=heartbeat(conn,lease)
                except psycopg.Error:
                    owned=False
                if not owned:
                    reason[0]='lost';cancel.set();return
                next_heartbeat=time.monotonic()+settings.job_heartbeat_seconds

    watcher=Thread(target=watch,name='ingestion-heartbeat')
    watcher.start()
    failure=None
    try:
        while not cancel.is_set():
            if stop.is_set() or time.monotonic()>=budget[0]:
                reason[0]='shutdown' if stop.is_set() else 'deadline'
                expired_stage[0]=budget[1]
                cancel.set();break
            execute_stage(lease,budget[0],cancel)
            if cancel.is_set():
                break
            with get_conn() as conn:
                with short_transaction(conn):
                    row=conn.execute('SELECT stage,status FROM ingestion_jobs WHERE id=%s AND owner_id=%s',
                        (lease.job_id,lease.scope.owner_id)).fetchone()
                    if row==('ready','succeeded'):
                        return True
                    owned=require_owned(conn,lease)
            if owned['stage']==lease.stage or owned['stage'] not in stage_deadlines:
                raise StageFailure('PROCESSING_INTEGRITY_FAILURE','integrity',False)
            lease=replace(lease,stage=owned['stage'])
            with lock:
                budget[0]=min(claim_deadline,time.monotonic()+stage_deadlines[lease.stage])
                budget[1]=lease.stage
    except LostLease:
        pass
    except StageFailure as error:
        failure=error
    except psycopg.Error:
        failure=StageFailure('DEPENDENCY_UNAVAILABLE','temporary',True)
    finally:
        finished.set();watcher.join()
    try:
        with get_conn() as conn:
            if reason[0]=='lost':
                return True
            if stop.is_set() or reason[0]=='shutdown':
                release_owned(conn,lease)
            elif reason[0]=='deadline':
                with short_transaction(conn):
                    current=require_owned(conn,lease)
                if current['stage']!=expired_stage[0]:
                    # A completed checkpoint outlived its old budget; do not fail
                    # the unstarted next stage. Release it for a fresh claim.
                    release_owned(conn,lease)
                elif expired_stage[0] in ('embedding','indexing'):
                    record_failure(conn,lease,StageFailure('DEPENDENCY_UNAVAILABLE','temporary',True,retry_after_seconds=5))
                else:
                    code='PDF_PARSE_TIMEOUT' if expired_stage[0]=='parsing' else 'PROCESSING_RESOURCE_LIMIT'
                    record_failure(conn,lease,StageFailure(code,'resource_limit',False))
            elif failure is not None:
                record_failure(conn,lease,failure)
    except (LostLease,psycopg.Error):
        # No stale error/release writes; an unavailable ledger recovers by expiry.
        pass
    return True


def main() -> None:
    settings=get_settings()
    if settings.app_role!='worker':
        raise ValueError('worker entry requires worker role')
    stop=Event()
    for signum in (signal.SIGTERM,signal.SIGINT):
        signal.signal(signum,lambda *_:stop.set())
    worker_id=f'worker-{os.getpid()}-{uuid4().hex}'
    idle=settings.worker_idle_min_seconds
    while not stop.is_set():
        try:
            claimed=run_once(worker_id,stop=stop)
        except psycopg.Error:
            claimed=False
        if claimed:
            idle=settings.worker_idle_min_seconds
        else:
            stop.wait(idle)
            idle=min(settings.worker_idle_max_seconds,idle+settings.worker_idle_min_seconds)


if __name__=='__main__':
    main()
