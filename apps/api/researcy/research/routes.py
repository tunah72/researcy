import asyncio
import time
from uuid import UUID

from fastapi import APIRouter,Request
from pydantic import TypeAdapter
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from researcy.auth.sessions import get_current_user,require_csrf
from researcy.db import get_conn
from researcy.errors import APIError
from researcy.generation.models import decode_output,InvalidModelOutput
from researcy.ingestion.jobs import short_transaction
from .models import ResearchRequest,ResearchReservation,ResearchSnapshot
from . import repository
from .stream import ResearchStreamResponse

router=APIRouter()
_REQUEST=TypeAdapter(ResearchRequest)
MAX_BODY_BYTES=2048


def _invalid() -> APIError:
    return APIError(422,'INVALID_REQUEST','Select one to three distinct ready related papers.')


def _uuid(value: str) -> UUID:
    try:return UUID(value)
    except ValueError:raise _invalid() from None


def _authorize(request: Request,paper_id: str) -> tuple[UUID,UUID]:
    with get_conn() as conn:
        with short_transaction(conn):
            owner=get_current_user(request,conn)
            require_csrf(request,conn,owner)
            active=_uuid(paper_id)
            if conn.execute('SELECT id FROM papers WHERE owner_id=%s AND id=%s',(owner,active)).fetchone() is None:
                raise APIError(404,'RESOURCE_NOT_FOUND','The requested resource was not found.')
    return owner,active


def _database(operation,*args):
    with get_conn() as conn:return operation(conn,*args)


async def _interrupt(reservation: ResearchReservation) -> None:
    task=asyncio.create_task(run_in_threadpool(_database,repository.fail_research,reservation,
        'RESEARCH_INTERRUPTED',True,(),{}))
    try:await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


async def _joined(operation,*args,listener: asyncio.Task | None=None):
    worker=asyncio.create_task(run_in_threadpool(operation,*args))
    try:
        if listener is not None:
            done,_=await asyncio.wait((worker,listener),return_when=asyncio.FIRST_COMPLETED)
            if listener in done:
                result=await asyncio.shield(worker)
                if isinstance(result,ResearchReservation):await _interrupt(result)
                raise ClientDisconnect()
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # Awaiting this write is essential: an abandoned worker could reserve after abort.
        try:
            result=await worker
            if isinstance(result,ResearchReservation):await _interrupt(result)
        except Exception:pass
        raise


async def _body(request: Request) -> ResearchRequest:
    body=bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>MAX_BODY_BYTES:raise _invalid()
        body.extend(chunk)
    content_type=request.headers.get('content-type','application/json').split(';',1)[0].strip().lower()
    if content_type!='application/json':raise _invalid()
    try:return decode_output(bytes(body),_REQUEST)
    except InvalidModelOutput:raise _invalid() from None


@router.post('/api/papers/{paper_id}/research-directions:stream',openapi_extra={
    'requestBody':{'required':True,'content':{'application/json':{'schema':ResearchRequest.model_json_schema()}}},
    'responses':{'200':{'description':'Bounded provisional ideas and committed exact citations.',
        'content':{'text/event-stream':{'schema':{'type':'string'}}}}}})
async def research_directions(request: Request,paper_id: str) -> ResearchStreamResponse:
    deadline=time.monotonic()+repository.RUN_SECONDS
    listener=None;transferred=False;reservation=None
    try:
        async with asyncio.timeout_at(deadline):
            owner,active=await _joined(_authorize,request,paper_id)
            if request.query_params:raise _invalid()
            submission=await _body(request)
            selected=tuple(UUID(value) for value in submission.related_paper_ids)
            if active in selected:raise _invalid()
            # Body reading ends before disconnect watching begins. This same task is
            # transferred to the response, so two consumers never race ASGI receive.
            async def disconnected():
                while True:
                    if (await request.receive())['type']=='http.disconnect':return
            listener=asyncio.create_task(disconnected())
            sources=await _joined(_database,repository.load_selection,owner,active,selected,listener=listener)
            settings=request.app.state.settings
            if not settings.generation_endpoint or not settings.generation_api_key:
                raise APIError(503,'GENERATION_UNCONFIGURED','Research directions are not configured.')
            reservation=await _joined(_database,repository.reserve_research,owner,sources,
                UUID(request.state.request_id),listener=listener)
            if listener.done():
                await _interrupt(reservation)
                raise ClientDisconnect()
            response=ResearchStreamResponse(reservation,settings,deadline=deadline,disconnect_task=listener)
            transferred=True
            return response
    except TimeoutError:
        if reservation is not None:await _interrupt(reservation)
        raise APIError(503,'RESEARCH_DEADLINE_EXCEEDED','The research request exceeded its time limit.') from None
    except asyncio.CancelledError:
        if reservation is not None:await _interrupt(reservation)
        raise
    finally:
        if listener is not None and not transferred:
            if not listener.done():listener.cancel()
            await asyncio.gather(listener,return_exceptions=True)


@router.get('/api/papers/{paper_id}/research-directions/{run_id}',response_model=ResearchSnapshot)
def research_snapshot(request: Request,paper_id: str,run_id: str) -> ResearchSnapshot:
    with get_conn() as conn:
        with short_transaction(conn):
            owner=get_current_user(request,conn)
        if request.query_params:raise _invalid()
        return repository.get_owned_research(conn,owner,_uuid(paper_id),_uuid(run_id))
