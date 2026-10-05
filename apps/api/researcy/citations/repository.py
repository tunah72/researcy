from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from researcy.documents.canonical import EvidenceLocation
from researcy.errors import APIError
from researcy.ingestion.jobs import short_transaction
from researcy.retrieval.repository import load_ready_document
from .models import ResolvedCitation,StoredCitation
from .persistence import validate_stored_citation


def get_owned_citation(conn: psycopg.Connection,owner_id: UUID,citation_id: UUID) -> ResolvedCitation:
    missing = APIError(404,'RESOURCE_NOT_FOUND','The requested resource was not found.')
    with short_transaction(conn):
        # Even an unaccepted same-owner collision cannot pick an arbitrary store.
        identities=conn.execute('''SELECT id FROM citations WHERE owner_id=%s AND id=%s UNION ALL
            SELECT id FROM research_citations WHERE owner_id=%s AND id=%s''',
            (owner_id,citation_id,owner_id,citation_id)).fetchall()
        if len(identities)!=1:
            raise missing
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute('''SELECT c.id citation_id,c.paper_id,c.document_version,c.source_ref,
                c.evidence_quote,c.page,c.boxes,c.section FROM citations c JOIN messages m
                  ON m.id=c.assistant_message_id AND m.owner_id=c.owner_id AND m.conversation_id=c.conversation_id
                  AND m.paper_id=c.paper_id AND m.document_version=c.document_version
                JOIN conversations v ON v.id=c.conversation_id AND v.owner_id=c.owner_id
                  AND v.paper_id=c.paper_id AND v.document_version=c.document_version
                WHERE c.owner_id=%s AND c.id=%s AND c.state='accepted' AND m.role='assistant' AND m.state='completed' ''',
                (owner_id,citation_id)).fetchone()
            research = cur.execute('''SELECT c.id citation_id,c.paper_id,c.document_version,c.source_ref,
                c.evidence_quote,c.page,c.boxes,c.section,c.raw_fragments,s.profile_hash FROM research_citations c
                JOIN research_runs r ON r.owner_id=c.owner_id AND r.id=c.run_id AND r.state='completed'
                JOIN research_ideas i ON i.owner_id=c.owner_id AND i.run_id=c.run_id AND i.idea_index=c.idea_index
                JOIN research_run_sources s ON s.owner_id=c.owner_id AND s.run_id=c.run_id
                  AND s.paper_id=c.paper_id AND s.document_version=c.document_version
                JOIN document_pages p ON p.owner_id=c.owner_id AND p.paper_id=c.paper_id
                  AND p.document_version_id=c.document_version AND p.id=c.page_id AND p.page_index+1=c.page
                JOIN index_publications pub ON pub.owner_id=s.owner_id AND pub.paper_id=s.paper_id
                  AND pub.document_version_id=s.document_version AND pub.profile_hash=s.profile_hash
                WHERE c.owner_id=%s AND c.id=%s''',(owner_id,citation_id)).fetchone()
    if research is not None:
        try:
            raw=research.pop('raw_fragments')
            profile_hash=bytes(research.pop('profile_hash'))
            document=load_ready_document(conn,owner_id,research['paper_id'],research['document_version'])
            if document.profile_hash!=profile_hash:
                raise missing
            citation=ResolvedCitation(**research)
            fragments=[];offset=0
            for fragment in raw:
                end=offset+len(fragment['quote'])
                fragments.append(EvidenceLocation(UUID(fragment['span_id']),citation.page-1,fragment['source_start'],
                    fragment['source_end'],fragment['quote'],citation.boxes[offset:end]))
                offset=end
            if offset!=len(citation.boxes):
                raise missing
            with short_transaction(conn):
                validate_stored_citation(conn,document.scope,StoredCitation(citation,0,tuple(fragments)))
            return citation
        except (APIError,ValueError,KeyError,TypeError):
            raise missing from None
    if row is None:
        raise missing
    # Publication/canonical source authority remains the same as Reader and retrieval.
    load_ready_document(conn,owner_id,row['paper_id'],row['document_version'])
    return ResolvedCitation(**row)
