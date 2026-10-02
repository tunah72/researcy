from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from researcy.citations.models import ResolvedCitation, StoredCitation
from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.ingestion.models import DocumentScope
from researcy.retrieval.repository import ReadyDocument, load_ready_document
from .models import Conversation, Message, MessageSubmission, RunReservation, CompletedAnswer

RUN_SECONDS = 150
LEASE_GRACE_SECONDS = 15
SAFE_RUN_CODES = frozenset({
    'READER_INTERRUPTED', 'READER_FAILED', 'READER_DEADLINE_EXCEEDED',
    'READER_EVENT_TOO_LARGE', 'EVIDENCE_UNAVAILABLE', 'EVIDENCE_UNRESOLVED',
    'GENERATION_UNAVAILABLE', 'GENERATION_TIMEOUT', 'GENERATION_RATE_LIMITED',
    'GENERATION_INVALID_OUTPUT', 'GENERATION_INVALID_ACTION',
})

_CONVERSATION_SELECT = '''SELECT c.id,c.paper_id,c.document_version,c.created_at,c.updated_at,
    CASE WHEN m.id IS NULL THEN NULL ELSE jsonb_build_object(
      'id',m.id,'role',m.role,'text',left(m.text,240),'state',m.state) END last_message
    FROM conversations c LEFT JOIN LATERAL (
      SELECT id,role,text,state FROM messages WHERE owner_id=c.owner_id AND conversation_id=c.id
      ORDER BY sequence DESC LIMIT 1) m ON true '''
_RUN_SELECT = '''SELECT r.*,u.text question FROM reader_runs r JOIN messages u
    ON u.id=r.user_message_id AND u.owner_id=r.owner_id AND u.conversation_id=r.conversation_id '''
_MESSAGE_COLUMNS = 'id,sequence,role,text,state,error_code,request_id,created_at,updated_at'


def _missing() -> APIError:
    return APIError(404, 'RESOURCE_NOT_FOUND', 'The requested resource was not found.')


def _require_conversation(conn: psycopg.Connection, owner_id: UUID, conversation_id: UUID) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(_CONVERSATION_SELECT+'WHERE c.owner_id=%s AND c.id=%s',
            (owner_id, conversation_id)).fetchone()
    if row is None:
        raise _missing()
    return row


def _lock_owner(conn: psycopg.Connection, owner_id: UUID) -> None:
    # One lock order for reserve/reload/finish/fail; no network inside this transaction.
    if conn.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (owner_id,)).fetchone() is None:
        raise _missing()


def _reap_expired(conn: psycopg.Connection, owner_id: UUID) -> None:
    rows = conn.execute('''UPDATE reader_runs SET state='interrupted',finished_at=clock_timestamp(),
        validation_outcome='interrupted' WHERE owner_id=%s AND state='running'
        AND lease_expires_at<=clock_timestamp() RETURNING assistant_message_id,conversation_id''',
        (owner_id,)).fetchall()
    for message_id, conversation_id in rows:
        conn.execute('''UPDATE messages SET state='interrupted',error_code='READER_INTERRUPTED',
            updated_at=clock_timestamp() WHERE owner_id=%s AND id=%s AND state='running' ''',
            (owner_id, message_id))
        conn.execute('UPDATE conversations SET updated_at=clock_timestamp() WHERE owner_id=%s AND id=%s',
            (owner_id, conversation_id))


def create_owned_conversation(conn: psycopg.Connection, owner_id: UUID, document: ReadyDocument) -> Conversation:
    scope = document.scope
    if scope.owner_id != owner_id:
        raise _missing()
    with short_transaction(conn):
        conversation_id = conn.execute('''INSERT INTO conversations(owner_id,paper_id,document_version)
            VALUES(%s,%s,%s) RETURNING id''',
            (owner_id, scope.paper_id, scope.document_version_id)).fetchone()[0]
        return Conversation(**_require_conversation(conn, owner_id, conversation_id))


def get_owned_conversation(conn: psycopg.Connection, owner_id: UUID, conversation_id: UUID) -> Conversation:
    with short_transaction(conn):
        _require_conversation(conn, owner_id, conversation_id)
        _lock_owner(conn, owner_id)
        _reap_expired(conn, owner_id)
        return Conversation(**_require_conversation(conn, owner_id, conversation_id))


def list_owned_conversations(conn: psycopg.Connection, owner_id: UUID, paper_id: UUID,
    before: UUID | None = None) -> tuple[list[Conversation], UUID | None]:
    with short_transaction(conn):
        if conn.execute('SELECT id FROM papers WHERE owner_id=%s AND id=%s', (owner_id, paper_id)).fetchone() is None:
            raise _missing()
        _lock_owner(conn, owner_id)
        _reap_expired(conn, owner_id)
        where = 'WHERE c.owner_id=%s AND c.paper_id=%s'
        params = [owner_id, paper_id]
        if before is not None:
            cursor = conn.execute('''SELECT created_at,id FROM conversations
                WHERE owner_id=%s AND paper_id=%s AND id=%s''', (owner_id, paper_id, before)).fetchone()
            if cursor is None:
                raise _missing()
            where += ' AND (c.created_at,c.id)<(%s,%s)'
            params.extend(cursor)
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(_CONVERSATION_SELECT+where+' ORDER BY c.created_at DESC,c.id DESC LIMIT 21', params).fetchall()
        return [Conversation(**row) for row in rows[:20]], rows[19]['id'] if len(rows)>20 else None


def _messages(conn: psycopg.Connection, owner_id: UUID, rows: list[dict]) -> list[Message]:
    if not rows:
        return []
    by_message: dict[UUID, list[ResolvedCitation]] = {}
    with conn.cursor(row_factory=dict_row) as cur:
        citations = cur.execute('''SELECT c.assistant_message_id,c.id citation_id,c.paper_id,c.document_version,
            c.source_ref,c.evidence_quote,c.page,c.boxes,c.section FROM citations c JOIN messages m
              ON m.id=c.assistant_message_id AND m.owner_id=c.owner_id AND m.conversation_id=c.conversation_id
            WHERE c.owner_id=%s AND c.assistant_message_id=ANY(%s) AND c.state='accepted' AND m.state='completed'
            ORDER BY c.ordinal''', (owner_id, [row['id'] for row in rows])).fetchall()
    for citation in citations:
        message_id = citation.pop('assistant_message_id')
        by_message.setdefault(message_id, []).append(ResolvedCitation(**citation))
    return [Message(**row, citations=tuple(by_message.get(row['id'], ()))) for row in rows]


def list_owned_messages(conn: psycopg.Connection, owner_id: UUID, conversation_id: UUID,
    after: UUID | None = None) -> tuple[list[Message], UUID | None]:
    with short_transaction(conn):
        _require_conversation(conn, owner_id, conversation_id)
        _lock_owner(conn, owner_id)
        _reap_expired(conn, owner_id)
        sequence = 0
        if after is not None:
            cursor = conn.execute('''SELECT sequence FROM messages
                WHERE owner_id=%s AND conversation_id=%s AND id=%s''', (owner_id, conversation_id, after)).fetchone()
            if cursor is None:
                raise _missing()
            sequence = cursor[0]
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(f'''SELECT {_MESSAGE_COLUMNS} FROM messages
                WHERE owner_id=%s AND conversation_id=%s AND sequence>%s ORDER BY sequence LIMIT 51''',
                (owner_id, conversation_id, sequence)).fetchall()
        return _messages(conn, owner_id, rows[:50]), rows[49]['id'] if len(rows)>50 else None


def _reservation(row: dict, replay: bool) -> RunReservation:
    return RunReservation(row['id'], DocumentScope(row['owner_id'],row['paper_id'],row['document_version']),
        row['conversation_id'],row['user_message_id'],row['assistant_message_id'],row['question'],
        row['request_id'],row['lease_expires_at'],row['state'],replay)


def reserve_run(conn: psycopg.Connection, owner_id: UUID, conversation_id: UUID,
    client_message_id: UUID, question: str, request_id: UUID | str) -> RunReservation:
    submission = MessageSubmission(client_message_id=client_message_id, question=question)
    conversation = get_owned_conversation(conn, owner_id, conversation_id)
    # The shared loader owns its short transaction; never nest it under owner locks.
    load_ready_document(conn, owner_id, conversation.paper_id, conversation.document_version)
    failure = None
    reservation = None
    with short_transaction(conn):
        _lock_owner(conn, owner_id)
        _require_conversation(conn, owner_id, conversation_id)
        _reap_expired(conn, owner_id)
        with conn.cursor(row_factory=dict_row) as cur:
            existing = cur.execute(_RUN_SELECT+'''WHERE r.owner_id=%s AND r.conversation_id=%s
                AND r.client_message_id=%s''', (owner_id,conversation_id,submission.client_message_id)).fetchone()
        if existing is not None:
            if existing['question'] != question:
                failure = APIError(409, 'MESSAGE_CONFLICT', 'This submission identifier belongs to a different question.')
            else:
                reservation = _reservation(existing, True)
        elif conn.execute("SELECT id FROM reader_runs WHERE owner_id=%s AND state='running'", (owner_id,)).fetchone():
            failure = APIError(409, 'READER_RUN_ACTIVE', 'A question is already running. Wait for it to finish.')
        elif conn.execute('''SELECT count(*) FROM reader_request_quota
            WHERE owner_id=%s AND accepted_at>clock_timestamp()-INTERVAL '1 hour' ''', (owner_id,)).fetchone()[0]>=20:
            failure = APIError(429, 'READER_RATE_LIMITED', 'Please wait before sending another question.')
        else:
            run_id, user_id, assistant_id = uuid4(), uuid4(), uuid4()
            sequence = conn.execute('''SELECT coalesce(max(sequence),0)+1 FROM messages
                WHERE owner_id=%s AND conversation_id=%s''', (owner_id,conversation_id)).fetchone()[0]
            source = (owner_id,conversation_id,conversation.paper_id,conversation.document_version)
            for message_id, seq, role, text, state in (
                (user_id,sequence,'user',question,'completed'), (assistant_id,sequence+1,'assistant','','running')):
                conn.execute('''INSERT INTO messages(id,owner_id,conversation_id,paper_id,document_version,
                    sequence,role,text,state,request_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (message_id,*source,seq,role,text,state,request_id))
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute('''INSERT INTO reader_runs(id,owner_id,conversation_id,paper_id,document_version,
                    client_message_id,user_message_id,assistant_message_id,state,request_id,started_at,lease_expires_at)
                    SELECT %s,%s,%s,%s,%s,%s,%s,%s,'running',%s,now,now+%s*INTERVAL '1 second'
                    FROM (SELECT clock_timestamp() now) clock RETURNING *''',
                    (run_id,*source,client_message_id,user_id,assistant_id,request_id,RUN_SECONDS+LEASE_GRACE_SECONDS)).fetchone()
            row['question'] = question
            conn.execute('INSERT INTO reader_request_quota(owner_id,run_id) VALUES(%s,%s)', (owner_id,run_id))
            conn.execute('UPDATE conversations SET updated_at=clock_timestamp() WHERE owner_id=%s AND id=%s',
                (owner_id,conversation_id))
            reservation = _reservation(row, False)
    # Reconciliation commits even when the new request is rejected.
    if failure is not None:
        raise failure
    assert reservation is not None
    return reservation


def _locked_run(conn: psycopg.Connection, reservation: RunReservation) -> dict:
    _lock_owner(conn, reservation.scope.owner_id)
    _reap_expired(conn, reservation.scope.owner_id)
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute('''SELECT * FROM reader_runs WHERE owner_id=%s AND conversation_id=%s
            AND id=%s FOR UPDATE''', (reservation.scope.owner_id,reservation.conversation_id,reservation.run_id)).fetchone()
    if row is None:
        raise _missing()
    return row


def fail_run(conn: psycopg.Connection, reservation: RunReservation, safe_code: str,
    interrupted: bool, partial_text: str) -> None:
    if safe_code not in SAFE_RUN_CODES:
        raise ValueError('Unknown safe Reader failure code.')
    with short_transaction(conn):
        row = _locked_run(conn, reservation)
        if row['state'] != 'running':
            return
        state = 'interrupted' if interrupted else 'failed'
        conn.execute('''UPDATE messages SET state=%s,error_code=%s,text=%s,updated_at=clock_timestamp()
            WHERE id=%s AND owner_id=%s AND state='running' ''',
            (state,safe_code,partial_text,row['assistant_message_id'],row['owner_id']))
        conn.execute('''UPDATE reader_runs SET state=%s,finished_at=clock_timestamp(),validation_outcome=%s
            WHERE id=%s AND owner_id=%s AND state='running' ''', (state,safe_code,row['id'],row['owner_id']))
        conn.execute('UPDATE conversations SET updated_at=clock_timestamp() WHERE owner_id=%s AND id=%s',
            (row['owner_id'],row['conversation_id']))


def _persist_citations(conn: psycopg.Connection, row: dict, citations: tuple[StoredCitation, ...]) -> None:
    for ordinal, stored in enumerate(citations):
        citation = stored.citation
        if (citation.paper_id!=row['paper_id'] or citation.document_version!=row['document_version']
            or not stored.raw_fragments or any(fragment.page_index+1!=citation.page for fragment in stored.raw_fragments)):
            raise APIError(422,'EVIDENCE_UNRESOLVED','The answer evidence cannot be resolved exactly.')
        page = conn.execute('''SELECT id FROM document_pages WHERE owner_id=%s AND paper_id=%s
            AND document_version_id=%s AND page_index=%s''',
            (row['owner_id'],row['paper_id'],row['document_version'],citation.page-1)).fetchone()
        if page is None:
            raise APIError(422,'EVIDENCE_UNRESOLVED','The answer evidence cannot be resolved exactly.')
        fragments, quote_parts, exact_boxes = [], [], []
        source_ids = [fragment.span_id for fragment in stored.raw_fragments]
        sources = conn.execute('''SELECT s.id,s.raw_text,s.boxes FROM document_spans s
            JOIN document_blocks b ON b.id=s.block_id AND b.owner_id=s.owner_id
              AND b.document_version_id=s.document_version_id AND b.page_id=s.page_id
            WHERE s.owner_id=%s AND s.paper_id=%s AND s.document_version_id=%s
              AND s.page_id=%s AND s.id=ANY(%s) AND NOT b.excluded''',
            (row['owner_id'],row['paper_id'],row['document_version'],page[0],source_ids)).fetchall()
        by_id = {span_id:(raw,boxes) for span_id,raw,boxes in sources}
        for fragment in stored.raw_fragments:
            source = by_id.get(fragment.span_id)
            if (source is None or type(fragment.source_start) is not int or type(fragment.source_end) is not int
                or not 0<=fragment.source_start<fragment.source_end<=len(source[0])):
                raise APIError(422,'EVIDENCE_UNRESOLVED','The answer evidence cannot be resolved exactly.')
            raw, source_boxes = source
            quote = raw[fragment.source_start:fragment.source_end]
            boxes = tuple(tuple(box) for box in source_boxes[fragment.source_start:fragment.source_end])
            if fragment.quote!=quote or fragment.boxes!=boxes:
                raise APIError(422,'EVIDENCE_UNRESOLVED','The answer evidence cannot be resolved exactly.')
            quote_parts.append(quote)
            exact_boxes.extend(boxes)
            fragments.append({'span_id':str(fragment.span_id),'source_start':fragment.source_start,
                'source_end':fragment.source_end,'quote':quote})
        exact_quote = ''.join(quote_parts)
        if citation.evidence_quote!=exact_quote or citation.boxes!=tuple(exact_boxes):
            raise APIError(422,'EVIDENCE_UNRESOLVED','The answer evidence cannot be resolved exactly.')
        conn.execute('''INSERT INTO citations(id,owner_id,conversation_id,assistant_message_id,paper_id,document_version,
            claim_index,source_ref,evidence_quote,page_id,page,boxes,raw_fragments,ordinal,section,state)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'accepted')''',
            (citation.citation_id,row['owner_id'],row['conversation_id'],row['assistant_message_id'],row['paper_id'],
             row['document_version'],stored.claim_index,citation.source_ref,exact_quote,page[0],citation.page,
             Jsonb(exact_boxes),Jsonb(fragments),ordinal,citation.section))


def finish_run(conn: psycopg.Connection, reservation: RunReservation, accepted_claims: list[str],
    citations: tuple[StoredCitation, ...], usage: dict, *, refusal: str | None = None) -> CompletedAnswer:
    if refusal is not None:
        if accepted_claims or citations or not refusal.strip():
            raise ValueError('A refusal cannot contain claims or citations.')
        state, text = 'refused', refusal
    else:
        if (not 1<=len(accepted_claims)<=12 or len(citations)>24
            or any(not claim.strip() or len(claim)>2000 for claim in accepted_claims)
            or any(not 0<=citation.claim_index<len(accepted_claims) for citation in citations)
            or any(not 1<=sum(citation.claim_index==index for citation in citations)<=4 for index in range(len(accepted_claims)))):
            raise ValueError('Every accepted claim requires bounded resolved citations.')
        state, text = 'completed', '\n\n'.join(accepted_claims)
    result = None
    with short_transaction(conn):
        row = _locked_run(conn, reservation)
        if row['state'] == 'running':
            # Lease CAS is evaluated at publication, not just at lock acquisition.
            changed = conn.execute('''UPDATE reader_runs SET state=%s,finished_at=clock_timestamp(),validated_action=%s,
                usage=%s,validation_outcome=%s WHERE owner_id=%s AND id=%s AND state='running'
                AND lease_expires_at>clock_timestamp() RETURNING id''',
                (state,Jsonb({'next_action':'answer','claims':[{'text':claim,'citations':[
                    {'source_ref':c.citation.source_ref,'evidence_quote':c.citation.evidence_quote}
                    for c in citations if c.claim_index==index]} for index,claim in enumerate(accepted_claims)],'refusal':refusal}),
                 Jsonb(usage),state,row['owner_id'],row['id'])).fetchone()
            if changed is None:
                _reap_expired(conn, row['owner_id'])
            else:
                conn.execute('''UPDATE messages SET text=%s,state=%s,error_code=NULL,updated_at=clock_timestamp()
                    WHERE owner_id=%s AND id=%s AND state='running' ''', (text,state,row['owner_id'],row['assistant_message_id']))
                _persist_citations(conn, row, citations)
                conn.execute('UPDATE conversations SET updated_at=clock_timestamp() WHERE owner_id=%s AND id=%s',
                    (row['owner_id'],row['conversation_id']))
                with conn.cursor(row_factory=dict_row) as cur:
                    message = cur.execute(f'SELECT {_MESSAGE_COLUMNS} FROM messages WHERE owner_id=%s AND id=%s',
                        (row['owner_id'],row['assistant_message_id'])).fetchone()
                accepted = tuple(citation.citation for citation in citations)
                result = CompletedAnswer(row['id'],Message(**message,citations=accepted),accepted)
    if result is None:
        raise APIError(409,'READER_RUN_NOT_ACTIVE','This answer is no longer running.')
    return result


def load_history(conn: psycopg.Connection, owner_id: UUID, conversation_id: UUID) -> tuple[Message, ...]:
    with short_transaction(conn):
        _require_conversation(conn, owner_id, conversation_id)
        _lock_owner(conn, owner_id)
        _reap_expired(conn, owner_id)
        pairs = conn.execute('''SELECT u.id,a.id,length(u.text)+length(a.text) FROM reader_runs r
            JOIN messages u ON u.id=r.user_message_id AND u.owner_id=r.owner_id
            JOIN messages a ON a.id=r.assistant_message_id AND a.owner_id=r.owner_id
            WHERE r.owner_id=%s AND r.conversation_id=%s AND r.state IN ('completed','refused')
              AND u.state='completed' AND a.state IN ('completed','refused')
            ORDER BY u.sequence DESC LIMIT 6''', (owner_id,conversation_id)).fetchall()
        ids, size = [], 0
        for user_id, assistant_id, length in pairs:
            if size+length>8000:
                break
            ids.extend((user_id,assistant_id))
            size += length
        if not ids:
            return ()
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(f'''SELECT {_MESSAGE_COLUMNS} FROM messages WHERE owner_id=%s
                AND conversation_id=%s AND id=ANY(%s) ORDER BY sequence''', (owner_id,conversation_id,ids)).fetchall()
        return tuple(_messages(conn, owner_id, rows))


def record_generation_attempt(conn: psycopg.Connection,reservation: RunReservation) -> None:
    with short_transaction(conn):
        row = _locked_run(conn,reservation)
        changed = conn.execute('''UPDATE reader_runs SET generation_calls=generation_calls+1
            WHERE owner_id=%s AND id=%s AND state='running' AND generation_calls<2
              AND lease_expires_at>clock_timestamp() RETURNING id''',
            (row['owner_id'],row['id'])).fetchone()
        if changed is None:
            raise APIError(409,'READER_RUN_NOT_ACTIVE','This answer is no longer running.')


def record_run_metrics(conn: psycopg.Connection,reservation: RunReservation,usage: dict,
    latency_ms: int,first_delta_ms: int | None) -> None:
    with short_transaction(conn):
        conn.execute('''UPDATE reader_runs SET usage=%s,latency_ms=%s,first_delta_ms=%s
            WHERE owner_id=%s AND conversation_id=%s AND id=%s''',
            (Jsonb(usage),latency_ms,first_delta_ms,reservation.scope.owner_id,
             reservation.conversation_id,reservation.run_id))
