import asyncio
from collections.abc import AsyncIterator,Callable
import json
import logging
import time

from starlette.concurrency import run_in_threadpool
from starlette.responses import Response
from starlette.types import Receive,Scope,Send

from researcy.config import Settings
from researcy.db import get_conn
from researcy.errors import APIError
from .models import ResearchDraft,ResearchEvent,ResearchReservation
from . import repository

EVENT_MAX_BYTES=262144
TRANSPORT_CHUNK_SIZE=16384
_EVENT_NAMES=frozenset(('direction.delta','citation.resolved','direction.completed','direction.failed'))


def encode_event(event: ResearchEvent) -> bytes:
    if event.event not in _EVENT_NAMES:raise ValueError('Unsupported Research event.')
    wire=('event: '+event.event+'\ndata: '+json.dumps(event.data,ensure_ascii=False,
        separators=(',',':'),allow_nan=False)+'\n\n').encode('utf-8')
    if len(wire)>EVENT_MAX_BYTES:
        raise APIError(503,'RESEARCH_EVENT_TOO_LARGE','The research evidence exceeds the stream limit.')
    return wire


class ResearchStreamResponse(Response):
    """One receive owner and direct awaited bounded sends; no transport queue or replay."""
    def __init__(self,reservation: ResearchReservation,settings: Settings,*,deadline: float,
        runner: Callable[...,AsyncIterator[ResearchEvent]] | None=None,
        disconnect_task: asyncio.Task | None=None) -> None:
        super().__init__(status_code=200,media_type='text/event-stream; charset=utf-8',headers={
            'Cache-Control':'no-store','X-Accel-Buffering':'no','X-Research-Run-ID':str(reservation.run_id),
            'X-Request-ID':str(reservation.request_id)})
        del self.headers['content-length']
        self.reservation=reservation;self.settings=settings;self.deadline=deadline
        self.runner=runner;self.disconnect_task=disconnect_task

    async def __call__(self,scope: Scope,receive: Receive,send: Send) -> None:
        drafts=[];terminal=False;transport_failed=False;generator=None
        producer=None;listener=self.disconnect_task

        async def persist():
            def save():
                with get_conn() as conn:
                    repository.fail_research(conn,self.reservation,'RESEARCH_INTERRUPTED',True,tuple(drafts),{})
            task=asyncio.create_task(run_in_threadpool(save))
            try:await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
            except Exception:
                logging.getLogger('researcy').error('research_stream_cleanup_failed run_id=%s',self.reservation.run_id)

        async def write(payload: bytes,*,final: bool=False):
            nonlocal transport_failed
            if transport_failed:return
            try:
                async with asyncio.timeout_at(self.deadline):
                    if not payload:await send({'type':'http.response.body','body':b'','more_body':not final})
                    for offset in range(0,len(payload),TRANSPORT_CHUNK_SIZE):
                        last=offset+TRANSPORT_CHUNK_SIZE>=len(payload)
                        await send({'type':'http.response.body','body':payload[offset:offset+TRANSPORT_CHUNK_SIZE],
                            'more_body':not (final and last)})
            except BaseException:
                transport_failed=True
                raise

        async def produce():
            nonlocal terminal
            await write(b': research connected\n\n')
            async for event in generator:
                wire=encode_event(event)
                if event.event=='direction.delta':drafts.append(ResearchDraft(**event.data['idea']))
                await write(wire)
                if event.event in ('direction.completed','direction.failed'):
                    terminal=True
                    break
            if not terminal:
                await persist()
                await write(encode_event(ResearchEvent('direction.failed',{
                    'run_id':str(self.reservation.run_id),'request_id':str(self.reservation.request_id),
                    'code':'RESEARCH_INTERRUPTED','message':repository.safe_message('RESEARCH_INTERRUPTED')})))
                terminal=True
            await write(b'',final=True)

        async def disconnect():
            while True:
                if (await receive())['type']=='http.disconnect':return
        try:
            if listener is None:listener=asyncio.create_task(disconnect())
            if listener.done():return
            async with asyncio.timeout_at(self.deadline):
                await send({'type':'http.response.start','status':self.status_code,'headers':self.raw_headers})
            runner=self.runner
            if runner is None:
                from researcy.agents.research import run_research
                runner=run_research
            generator=runner(self.reservation,self.settings,deadline=self.deadline)
            producer=asyncio.create_task(produce())
            async with asyncio.timeout_at(self.deadline):
                done,_=await asyncio.wait((producer,listener),return_when=asyncio.FIRST_COMPLETED)
                if listener in done and not terminal:transport_failed=True
                if producer in done:await producer
        except asyncio.CancelledError:
            transport_failed=True
            raise
        except Exception:
            transport_failed=True
        finally:
            tasks=[t for t in (producer,listener) if t is not None]
            for task in tasks:
                if not task.done():task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if generator is not None:await generator.aclose()
            if not terminal or transport_failed:await persist()
