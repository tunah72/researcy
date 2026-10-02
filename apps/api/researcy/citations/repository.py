from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.retrieval.repository import load_ready_document
from .models import ResolvedCitation


def get_owned_citation(conn: psycopg.Connection,owner_id: UUID,citation_id: UUID) -> ResolvedCitation:
    missing = APIError(404,'RESOURCE_NOT_FOUND','The requested resource was not found.')
    with short_transaction(conn):
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute('''SELECT c.id citation_id,c.paper_id,c.document_version,c.source_ref,
                c.evidence_quote,c.page,c.boxes,c.section FROM citations c JOIN messages m
                  ON m.id=c.assistant_message_id AND m.owner_id=c.owner_id AND m.conversation_id=c.conversation_id
                  AND m.paper_id=c.paper_id AND m.document_version=c.document_version
                JOIN conversations v ON v.id=c.conversation_id AND v.owner_id=c.owner_id
                  AND v.paper_id=c.paper_id AND v.document_version=c.document_version
                WHERE c.owner_id=%s AND c.id=%s AND c.state='accepted' AND m.role='assistant' AND m.state='completed' ''',
                (owner_id,citation_id)).fetchone()
    if row is None:
        raise missing
    # Publication/canonical source authority remains the same as Reader and retrieval.
    load_ready_document(conn,owner_id,row['paper_id'],row['document_version'])
    return ResolvedCitation(**row)
