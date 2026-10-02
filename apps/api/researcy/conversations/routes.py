import json
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from researcy.auth.sessions import get_current_user, require_csrf
from researcy.db import get_conn
from researcy.errors import APIError
from researcy.retrieval.repository import load_ready_document
from .models import (
    ConversationRequest,
    ConversationResponse,
    ConversationListResponse,
    MessageListResponse,
    MessageSubmission,
    MessageStreamReplayResponse,
)
from .repository import (
    create_owned_conversation,
    list_owned_conversations,
    list_owned_messages,
    get_owned_conversation,
    reserve_run,
)
from .stream import ReaderStreamResponse

router = APIRouter()
MAX_MESSAGE_BODY_BYTES = 16 * 1024


async def read_json_body(request: Request) -> dict:
    """Bound bytes after the caller's authentication/source check, including chunked bodies."""
    body = bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>MAX_MESSAGE_BODY_BYTES:
            raise APIError(413,'REQUEST_TOO_LARGE','The request exceeds the size limit.')
        body.extend(chunk)
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise APIError(422,'INVALID_REQUEST','A valid JSON request is required.') from exc
    if not isinstance(value, dict):
        raise APIError(422,'INVALID_REQUEST','A JSON object is required.')
    return value


@router.post('/api/papers/{paper_id}/conversations', response_model=ConversationResponse, status_code=201,
    openapi_extra={'requestBody':{'required':True,'content':{'application/json':{'schema':ConversationRequest.model_json_schema()}}}})
async def create_conversation(request: Request, paper_id: UUID):
    def authorize():
        with get_conn() as conn:
            owner = get_current_user(request, conn)
            require_csrf(request, conn, owner)
            conn.commit()
            return owner, load_ready_document(conn, owner, paper_id, None)
    owner, document = await run_in_threadpool(authorize)
    body = await read_json_body(request)
    try:
        ConversationRequest.model_validate(body)
    except ValidationError as exc:
        raise APIError(422,'INVALID_REQUEST','Conversation creation requires an empty JSON object.') from exc

    def persist():
        with get_conn() as conn:
            return create_owned_conversation(conn, owner, document)
    conversation = await run_in_threadpool(persist)
    return {'conversation':conversation,'request_id':request.state.request_id}


@router.get('/api/papers/{paper_id}/conversations', response_model=ConversationListResponse)
def conversations(request: Request, paper_id: UUID, before: UUID | None = None):
    with get_conn() as conn:
        owner = get_current_user(request, conn)
        conn.commit()
        records, cursor = list_owned_conversations(conn, owner, paper_id, before)
    return {'conversations':records,'next_before':cursor,'request_id':request.state.request_id}


@router.get('/api/conversations/{conversation_id}/messages', response_model=MessageListResponse)
def messages(request: Request, conversation_id: UUID, after: UUID | None = None):
    with get_conn() as conn:
        owner = get_current_user(request, conn)
        conn.commit()
        records, cursor = list_owned_messages(conn, owner, conversation_id, after)
    return {'messages':records,'next_after':cursor,'request_id':request.state.request_id}


@router.post(
    '/api/conversations/{conversation_id}/messages:stream',
    response_model=MessageStreamReplayResponse,
    openapi_extra={
        'requestBody': {
            'required': True,
            'content': {'application/json': {'schema': MessageSubmission.model_json_schema()}},
        },
        'responses': {
            '200': {
                'description': 'Real-time SSE event stream for new submissions, or JSON response for duplicate submission replays.',
                'content': {
                    'text/event-stream': {
                        'schema': {'type': 'string'},
                    },
                    'application/json': {
                        'schema': MessageStreamReplayResponse.model_json_schema(),
                    },
                },
            },
        },
    },
)
async def stream_messages(request: Request, conversation_id: UUID) -> Response:
    def authorize():
        with get_conn() as conn:
            owner = get_current_user(request, conn)
            require_csrf(request, conn, owner)
            conn.commit()
            conversation = get_owned_conversation(conn, owner, conversation_id)
            document = load_ready_document(conn, owner, conversation.paper_id, conversation.document_version)
            return owner, conversation, document

    owner, conversation, document = await run_in_threadpool(authorize)
    body = await read_json_body(request)
    try:
        submission = MessageSubmission.model_validate(body)
    except ValidationError as exc:
        raise APIError(422, 'INVALID_REQUEST', 'A valid message submission is required.') from exc

    def reserve():
        with get_conn() as conn:
            return reserve_run(
                conn,
                owner,
                conversation_id,
                submission.client_message_id,
                submission.question,
                request.state.request_id,
            )

    reservation = await run_in_threadpool(reserve)

    if reservation.is_replay:
        replay = MessageStreamReplayResponse(
            run_id=reservation.run_id,
            message_id=reservation.assistant_message_id,
            state=reservation.state,
            request_id=UUID(str(request.state.request_id)),
        )
        return JSONResponse(
            status_code=200,
            content=replay.model_dump(mode='json'),
        )

    return ReaderStreamResponse(
        reservation=reservation,
        document=document,
        settings=request.app.state.settings,
        request_id=request.state.request_id,
    )
