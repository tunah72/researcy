from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_question_rejects_nul_before_postgres_persistence():
    from researcy.conversations.models import MessageSubmission

    with pytest.raises(ValidationError):
        MessageSubmission(client_message_id=uuid4(), question='Which evidence?\x00')


@pytest.mark.parametrize('corruption', ['missing_span', 'quote', 'boxes'])
def test_publication_rejects_citations_not_bound_to_canonical_fragments(selected_index, job_connections, corruption):
    from researcy.citations.models import ResolvedCitation, StoredCitation
    from researcy.conversations.repository import create_owned_conversation, reserve_run, finish_run
    from researcy.documents.canonical import EvidenceLocation
    from researcy.errors import APIError
    from researcy.retrieval.repository import load_ready_document

    scope = selected_index['scope']
    conn, _ = job_connections
    import time
    from researcy.retrieval import index

    deadline = time.monotonic()+60
    index.index_selected(selected_index['lease'], deadline)
    receipt = index.verify_index(selected_index['lease'], deadline)
    index.publish_ready(conn, selected_index['lease'], receipt)
    document = load_ready_document(conn, scope.owner_id, scope.paper_id, scope.document_version_id)
    conversation = create_owned_conversation(conn, scope.owner_id, document)
    reservation = reserve_run(conn, scope.owner_id, conversation.id, uuid4(), 'Which source supports this claim?', uuid4())
    span_id, raw, source_boxes, page_index = conn.execute('''SELECT s.id,s.raw_text,s.boxes,p.page_index
        FROM document_spans s JOIN document_pages p ON p.id=s.page_id AND p.owner_id=s.owner_id
        AND p.document_version_id=s.document_version_id
        WHERE s.owner_id=%s AND s.document_version_id=%s ORDER BY s.ordinal LIMIT 1''',
        (scope.owner_id, scope.document_version_id)).fetchone()
    conn.commit()
    quote = raw[:5]
    boxes = tuple(tuple(box) for box in source_boxes[:5])
    fragment = EvidenceLocation(span_id, page_index, 0, 5, quote, boxes)
    public_quote, public_boxes = quote, boxes
    if corruption == 'missing_span':
        fragment = replace(fragment, span_id=uuid4())
    elif corruption == 'quote':
        public_quote = 'unrelated quote'
    else:
        public_boxes = tuple((x0+1,y0,x1+1,y1) for x0,y0,x1,y1 in boxes)
    citation = ResolvedCitation(citation_id=uuid4(), paper_id=scope.paper_id,
        document_version=scope.document_version_id, source_ref='S1', evidence_quote=public_quote,
        page=page_index+1, boxes=public_boxes)
    stored = StoredCitation(citation, 0, (fragment,))
    with pytest.raises(APIError) as caught:
        finish_run(conn, reservation, ['A controlled claim.'], (stored,), {})
    assert caught.value.code == 'EVIDENCE_UNRESOLVED'
    assert conn.execute('SELECT state FROM messages WHERE owner_id=%s AND id=%s',
        (scope.owner_id, reservation.assistant_message_id)).fetchone()[0] == 'running'
    assert conn.execute('SELECT count(*) FROM citations WHERE owner_id=%s AND assistant_message_id=%s',
        (scope.owner_id, reservation.assistant_message_id)).fetchone()[0] == 0
