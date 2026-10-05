from typing import Literal
from uuid import UUID,uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from researcy.citations.models import ResolvedCitation,StoredCitation
from researcy.citations.persistence import validate_stored_citation
from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.retrieval.repository import load_ready_document
from .models import (AcceptedIdea,ResearchDraft,ResearchReservation,ResearchSafeError,ResearchSnapshot,
    ResearchSource,ResearchSourceIdentity)

RUN_SECONDS=150
LEASE_GRACE_SECONDS=15
SAFE_RUN_CODES=frozenset(('RESEARCH_INTERRUPTED','RESEARCH_FAILED','RESEARCH_DEADLINE_EXCEEDED',
    'RESEARCH_EVENT_TOO_LARGE','RESEARCH_INSUFFICIENT_EVIDENCE','EVIDENCE_UNAVAILABLE','EVIDENCE_UNRESOLVED',
    'GENERATION_UNAVAILABLE','GENERATION_TIMEOUT','GENERATION_RATE_LIMITED','GENERATION_INVALID_OUTPUT',
    'GENERATION_INVALID_ACTION','DEPENDENCY_UNAVAILABLE','RESEARCH_SOURCE_CHANGED','RESEARCH_RUN_NOT_ACTIVE'))


def safe_message(code: str) -> str:
    if code=='RESEARCH_INSUFFICIENT_EVIDENCE':
        return 'The selected evidence does not support research directions. Try a different selection.'
    if code=='RESEARCH_INTERRUPTED':
        return 'The research directions were interrupted. Reload to see their saved state.'
    return 'The research directions could not be completed. Submit a new request to retry.'


def _missing() -> APIError:
    return APIError(404,'RESOURCE_NOT_FOUND','The requested resource was not found.')


def _changed() -> APIError:
    return APIError(409,'RESEARCH_SOURCE_CHANGED','The selected sources changed. Select the papers again.')


def _inactive() -> APIError:
    return APIError(409,'RESEARCH_RUN_NOT_ACTIVE','These research directions are no longer running.')


def _unresolved() -> APIError:
    return APIError(422,'EVIDENCE_UNRESOLVED','The research evidence cannot be resolved exactly.')


def _lock_owner(conn: psycopg.Connection,owner: UUID) -> None:
    if conn.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(owner,)).fetchone() is None:
        raise _missing()


def _reap(conn: psycopg.Connection,owner: UUID) -> None:
    conn.execute('''UPDATE research_runs SET state='interrupted',finished_at=clock_timestamp(),
        error_code='RESEARCH_INTERRUPTED',metrics=metrics||%s WHERE owner_id=%s AND state='running'
        AND lease_expires_at<=clock_timestamp()''',
        (Jsonb({'validation_outcome':'interrupted','unobserved_usage':'unknown'}),owner))


def load_selection(conn: psycopg.Connection,owner_id: UUID,active_id: UUID,
    selected: tuple[UUID,...]) -> tuple[ResearchSource,...]:
    if not 1<=len(selected)<=3 or len(set(selected))!=len(selected) or active_id in selected:
        raise APIError(422,'INVALID_REQUEST','Select one to three distinct related papers.')
    ordered=(active_id,*sorted(selected,key=lambda value:value.int))
    with short_transaction(conn):
        rows=conn.execute('''SELECT p.id,p.active_version_id,p.title,j.stage,j.status FROM papers p
            LEFT JOIN ingestion_jobs j ON j.owner_id=p.owner_id AND j.document_version_id=p.active_version_id
            WHERE p.owner_id=%s AND p.id=ANY(%s)''',(owner_id,list(ordered))).fetchall()
        by_id={row[0]:row for row in rows}
        # Establish ownership of the whole selection before disclosing any readiness.
        if set(by_id)!=set(ordered):raise _missing()
        for ordinal,paper in enumerate(ordered):
            row=by_id[paper]
            if row[3:5]!=('ready','succeeded'):
                raise APIError(409,'PAPER_NOT_READY' if ordinal==0 else 'RESEARCH_SELECTION_NOT_READY',
                    'This paper is not ready for reading.' if ordinal==0 else 'A selected paper is not ready for research.')
        headings={paper:tuple(row[0] for row in conn.execute('''SELECT title FROM document_sections
            WHERE owner_id=%s AND paper_id=%s AND document_version_id=%s AND title IS NOT NULL
            ORDER BY ordinal LIMIT 32''',(owner_id,paper,by_id[paper][1])).fetchall()) for paper in ordered}
    sources=[]
    for ordinal,paper in enumerate(ordered):
        try:document=load_ready_document(conn,owner_id,paper,by_id[paper][1])
        except APIError as error:
            if error.code=='PAPER_NOT_READY' and ordinal:
                raise APIError(409,'RESEARCH_SELECTION_NOT_READY','A selected paper is not ready for research.') from None
            raise
        sources.append(ResearchSource(ordinal,document,by_id[paper][2],headings[paper]))
    return tuple(sources)


def _check_sources(conn: psycopg.Connection,owner: UUID,sources: tuple[ResearchSource,...],*,pointers: bool) -> None:
    if (not 2<=len(sources)<=4 or tuple(s.ordinal for s in sources)!=tuple(range(len(sources)))
        or len({s.document.scope.paper_id for s in sources})!=len(sources)
        or any(s.document.scope.owner_id!=owner for s in sources)):
        raise _changed()
    for source in sources:
        document=source.document;scope=document.scope
        row=conn.execute('''SELECT p.active_version_id,j.stage,j.status,j.profile_hash,pub.collection
            FROM papers p JOIN document_versions v ON v.owner_id=p.owner_id AND v.paper_id=p.id AND v.id=%s
            JOIN ingestion_jobs j ON j.owner_id=v.owner_id AND j.document_version_id=v.id
            JOIN index_publications pub ON pub.owner_id=v.owner_id AND pub.paper_id=v.paper_id
              AND pub.document_version_id=v.id AND pub.profile_hash=%s
            WHERE p.owner_id=%s AND p.id=%s FOR SHARE OF p''',
            (scope.document_version_id,document.profile_hash,owner,scope.paper_id)).fetchone()
        if (row is None or row[1:3]!=('ready','succeeded') or bytes(row[3])!=document.profile_hash
            or row[4]!=document.collection or (pointers and row[0]!=scope.document_version_id)):
            raise _changed()


def reserve_research(conn: psycopg.Connection,owner_id: UUID,sources: tuple[ResearchSource,...],
    request_id: UUID) -> ResearchReservation:
    failure=None;reservation=None
    with short_transaction(conn):
        _lock_owner(conn,owner_id);_reap(conn,owner_id)
        _check_sources(conn,owner_id,sources,pointers=True)
        if conn.execute("SELECT id FROM research_runs WHERE owner_id=%s AND state='running'",(owner_id,)).fetchone():
            failure=APIError(409,'RESEARCH_RUN_ACTIVE','Research directions are already running. Wait for them to finish.')
        else:
            quota=conn.execute('''SELECT count(*),greatest(1,ceil(extract(epoch FROM
                min(started_at)+INTERVAL '1 hour'-clock_timestamp())))::integer FROM research_runs
                WHERE owner_id=%s AND started_at>clock_timestamp()-INTERVAL '1 hour' ''',(owner_id,)).fetchone()
            if quota[0]>=20:
                failure=APIError(429,'RESEARCH_RATE_LIMITED','Please wait before requesting more research directions.')
                failure.retry_after=quota[1]
            else:
                run_id=uuid4();active=sources[0].document.scope
                lease=conn.execute('''INSERT INTO research_runs(id,owner_id,active_paper_id,document_version,
                    request_id,source_count,state,started_at,lease_expires_at)
                    SELECT %s,%s,%s,%s,%s,%s,'running',now,now+INTERVAL '165 seconds'
                    FROM (SELECT clock_timestamp() now) clock RETURNING lease_expires_at''',
                    (run_id,owner_id,active.paper_id,active.document_version_id,request_id,len(sources))).fetchone()[0]
                for source in sources:
                    scope=source.document.scope
                    conn.execute('''INSERT INTO research_run_sources(owner_id,run_id,paper_id,document_version,
                        profile_hash,ordinal,is_active) VALUES(%s,%s,%s,%s,%s,%s,%s)''',
                        (owner_id,run_id,scope.paper_id,scope.document_version_id,source.document.profile_hash,
                         source.ordinal,source.ordinal==0))
                reservation=ResearchReservation(run_id,owner_id,active.paper_id,request_id,sources,lease)
    if failure is not None:raise failure
    assert reservation is not None
    return reservation


def _locked(conn: psycopg.Connection,reservation: ResearchReservation) -> dict:
    _lock_owner(conn,reservation.owner_id);_reap(conn,reservation.owner_id)
    with conn.cursor(row_factory=dict_row) as cur:
        row=cur.execute('''SELECT * FROM research_runs WHERE owner_id=%s AND active_paper_id=%s AND id=%s
            FOR UPDATE''',(reservation.owner_id,reservation.active_paper_id,reservation.run_id)).fetchone()
    if row is None:raise _missing()
    pins=conn.execute('''SELECT paper_id,document_version,profile_hash,ordinal FROM research_run_sources
        WHERE owner_id=%s AND run_id=%s ORDER BY ordinal''',(reservation.owner_id,reservation.run_id)).fetchall()
    expected=[(s.document.scope.paper_id,s.document.scope.document_version_id,s.document.profile_hash,s.ordinal)
        for s in reservation.sources]
    if row['request_id']!=reservation.request_id or pins!=expected:raise _changed()
    return row


def record_research_attempt(conn: psycopg.Connection,reservation: ResearchReservation,
    kind: Literal['initial','repair']) -> None:
    if kind not in ('initial','repair'):raise ValueError('Unknown Research pass.')
    changed=None
    with short_transaction(conn):
        row=_locked(conn,reservation)
        changed=conn.execute('''UPDATE research_runs SET generation_calls=generation_calls+1,repairs=repairs+%s
            WHERE owner_id=%s AND id=%s AND state='running' AND generation_calls=%s AND repairs=0
            AND lease_expires_at>clock_timestamp() RETURNING id''',
            (int(kind=='repair'),row['owner_id'],row['id'],int(kind=='repair'))).fetchone()
    if changed is None:raise _inactive()


def _snapshot(conn: psycopg.Connection,row: dict) -> ResearchSnapshot:
    with conn.cursor(row_factory=dict_row) as cur:
        sources=cur.execute('''SELECT paper_id,document_version FROM research_run_sources
            WHERE owner_id=%s AND run_id=%s ORDER BY ordinal''',(row['owner_id'],row['id'])).fetchall()
        ideas=cur.execute('''SELECT idea_index,observed_gap,proposed_direction,possible_method FROM research_ideas
            WHERE owner_id=%s AND run_id=%s ORDER BY idea_index''',(row['owner_id'],row['id'])).fetchall()
        citations=cur.execute('''SELECT idea_index,id citation_id,paper_id,document_version,source_ref,
            evidence_quote,page,boxes,section FROM research_citations WHERE owner_id=%s AND run_id=%s
            ORDER BY ordinal''',(row['owner_id'],row['id'])).fetchall()
    by_idea={}
    for citation in citations:
        index=citation.pop('idea_index');by_idea.setdefault(index,[]).append(ResolvedCitation(**citation))
    accepted=[]
    for idea in ideas:
        index=idea.pop('idea_index');accepted.append(AcceptedIdea(**idea,premise_citations=tuple(by_idea.get(index,()))))
    return ResearchSnapshot(run_id=row['id'],active_paper_id=row['active_paper_id'],document_version=row['document_version'],
        sources=tuple(ResearchSourceIdentity(**s) for s in sources),state=row['state'],ideas=tuple(accepted),
        draft_ideas=tuple(ResearchDraft(**draft) for draft in row['draft_ideas']),
        error=ResearchSafeError(code=row['error_code'],message=safe_message(row['error_code'])) if row['error_code'] else None,
        request_id=row['request_id'])


def get_owned_research(conn: psycopg.Connection,owner_id: UUID,active_id: UUID,run_id: UUID) -> ResearchSnapshot:
    with short_transaction(conn):
        if conn.execute('SELECT id FROM papers WHERE owner_id=%s AND id=%s',(owner_id,active_id)).fetchone() is None:
            raise _missing()
        _lock_owner(conn,owner_id);_reap(conn,owner_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row=cur.execute('SELECT * FROM research_runs WHERE owner_id=%s AND active_paper_id=%s AND id=%s',
                (owner_id,active_id,run_id)).fetchone()
        if row is None:raise _missing()
        return _snapshot(conn,row)


def finish_research(conn: psycopg.Connection,reservation: ResearchReservation,ideas: tuple[AcceptedIdea,...],
    citations: tuple[StoredCitation,...],metrics: dict) -> ResearchSnapshot:
    if not 1<=len(ideas)<=3 or not 1<=len(citations)<=24:raise _unresolved()
    expected=[c for idea in ideas for c in idea.premise_citations]
    if (expected!=[c.citation for c in citations] or len({c.citation_id for c in expected})!=len(expected)
        or any(tuple(c.citation for c in citations if c.claim_index==index)!=idea.premise_citations
            for index,idea in enumerate(ideas))):
        raise _unresolved()
    accepted=None
    with short_transaction(conn):
        row=_locked(conn,reservation)
        if row['state']=='running':
            _check_sources(conn,reservation.owner_id,reservation.sources,pointers=False)
            membership={(s.document.scope.paper_id,s.document.scope.document_version_id):s.document.scope for s in reservation.sources}
            canonical=[]
            for stored in citations:
                scope=membership.get((stored.citation.paper_id,stored.citation.document_version))
                if scope is None or not 0<=stored.claim_index<len(ideas):raise _unresolved()
                canonical.append(validate_stored_citation(conn,scope,stored))
            changed=conn.execute('''UPDATE research_runs SET state='completed',finished_at=clock_timestamp(),
                publication_xid=pg_current_xact_id(),metrics=%s
                WHERE owner_id=%s AND id=%s AND state='running' AND lease_expires_at>clock_timestamp() RETURNING id''',
                (Jsonb(metrics),row['owner_id'],row['id'])).fetchone()
            if changed is None:_reap(conn,row['owner_id'])
            else:
                for index,idea in enumerate(ideas):
                    conn.execute('''INSERT INTO research_ideas(owner_id,run_id,idea_index,observed_gap,proposed_direction,possible_method)
                        VALUES(%s,%s,%s,%s,%s,%s)''',(row['owner_id'],row['id'],index,idea.observed_gap,idea.proposed_direction,idea.possible_method))
                for ordinal,(stored,provenance) in enumerate(zip(citations,canonical)):
                    c=stored.citation
                    conn.execute('''INSERT INTO research_citations(id,owner_id,run_id,idea_index,paper_id,document_version,
                        source_ref,evidence_quote,page_id,page,boxes,raw_fragments,ordinal,section)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (c.citation_id,row['owner_id'],row['id'],stored.claim_index,c.paper_id,c.document_version,c.source_ref,
                         provenance.evidence_quote,provenance.page_id,c.page,Jsonb(provenance.boxes),Jsonb(provenance.raw_fragments),ordinal,c.section))
                row.update(state='completed',finished_at=True,metrics=metrics)
                accepted=_snapshot(conn,row)
    if accepted is None:raise _inactive()
    return accepted


def fail_research(conn: psycopg.Connection,reservation: ResearchReservation,code: str,interrupted: bool,
    drafts: tuple[ResearchDraft,...],metrics: dict) -> None:
    if code not in SAFE_RUN_CODES or len(drafts)>3:raise ValueError('Invalid safe Research failure.')
    # Revalidation prevents quotes/citations or unchecked model text entering draft storage.
    drafts=tuple(ResearchDraft.model_validate(d.model_dump()) for d in drafts)
    with short_transaction(conn):
        row=_locked(conn,reservation)
        if row['state']!='running':return
        conn.execute('''UPDATE research_runs SET state=%s,finished_at=clock_timestamp(),error_code=%s,draft_ideas=%s,metrics=%s
            WHERE owner_id=%s AND id=%s AND state='running' ''',
            ('interrupted' if interrupted else 'failed',code,Jsonb([d.model_dump() for d in drafts]),Jsonb(metrics),row['owner_id'],row['id']))


def record_research_metrics(conn: psycopg.Connection,reservation: ResearchReservation,metrics: dict) -> None:
    """Late terminal accounting may enrich metadata, never alter the durable winner."""
    with short_transaction(conn):
        _lock_owner(conn,reservation.owner_id)
        conn.execute('''UPDATE research_runs SET metrics=metrics||%s WHERE owner_id=%s AND id=%s
            AND coalesce(jsonb_array_length(metrics->'passes'),0)<=%s''',
            (Jsonb(metrics),reservation.owner_id,reservation.run_id,len(metrics.get('passes',[]))))
