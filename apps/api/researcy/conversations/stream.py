import asyncio
from collections.abc import AsyncIterator,Callable
import json
import logging
import time
from typing import TYPE_CHECKING
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from starlette.responses import Response
from starlette.types import Receive,Scope,Send

from researcy.config import Settings
from researcy.conversations.models import RunReservation
from researcy.conversations.repository import LEASE_GRACE_SECONDS, RUN_SECONDS, fail_run
from researcy.db import get_conn
from researcy.retrieval.repository import ReadyDocument

if TYPE_CHECKING:
    from researcy.agents.reader import ReaderEvent

EVENT_MAX_BYTES = 262144
TRANSPORT_CHUNK_SIZE = 16384


class ReaderStreamResponse(Response):
    """Direct awaited sends apply backpressure without a second transport queue."""

    def __init__(self,reservation: RunReservation,document: ReadyDocument,settings: Settings,
        request_id: UUID | str,runner: Callable[[RunReservation,ReadyDocument,Settings],AsyncIterator['ReaderEvent']] | None=None) -> None:
        super().__init__(status_code=200,media_type='text/event-stream; charset=utf-8',
            headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
        del self.headers['content-length']
        self.reservation = reservation
        self.document = document
        self.settings = settings
        self.request_id = str(request_id)
        self.runner = runner

    async def __call__(self,scope: Scope,receive: Receive,send: Send) -> None:
        partial: list[str] = []
        terminal = False
        transport_failed = False
        generator = None

        async def persist(code: str,interrupted: bool):
            def save():
                with get_conn() as conn:
                    fail_run(conn,self.reservation,code,interrupted,''.join(partial))
            try:
                await run_in_threadpool(save)
            except Exception:
                # Failed cleanup remains bounded by the persisted lease; no private diagnostics.
                logging.getLogger('researcy').error('reader_stream_cleanup_failed run_id=%s',self.reservation.run_id)

        async def write(payload: bytes,*,final: bool=False,terminal: bool=False):
            nonlocal transport_failed
            if transport_failed:
                return
            target_deadline = grace_deadline if (final or terminal) else deadline
            try:
                async with asyncio.timeout_at(target_deadline):
                    if not payload:
                        await send({'type':'http.response.body','body':b'','more_body':not final})
                    for offset in range(0,len(payload),TRANSPORT_CHUNK_SIZE):
                        last = offset+TRANSPORT_CHUNK_SIZE>=len(payload)
                        await send({'type':'http.response.body','body':payload[offset:offset+TRANSPORT_CHUNK_SIZE],
                            'more_body':not (final and last)})
            except (Exception, asyncio.CancelledError):
                transport_failed = True
                raise
        async def failure(code: str,message: str):
            nonlocal terminal
            data = {'run_id':str(self.reservation.run_id),'message_id':str(self.reservation.assistant_message_id),
                'code':code,'message':message,'request_id':self.request_id}
            await write(('event: answer.failed\ndata: '+json.dumps(data,separators=(',',':'))+'\n\n').encode(),terminal=True)
            terminal = True

        async def produce():
            nonlocal terminal
            try:
                # A genuine comment flushes the authorized stream before retrieval/model latency.
                await write(b': reader connected\n\n')
                async for event in generator:
                    wire = ('event: '+event.event+'\ndata: '+json.dumps(event.data,ensure_ascii=False,
                        separators=(',',':'),allow_nan=False)+'\n\n').encode('utf-8')
                    if len(wire)>EVENT_MAX_BYTES:
                        await persist('READER_EVENT_TOO_LARGE',False)
                        await failure('READER_EVENT_TOO_LARGE','The answer evidence exceeds the stream limit.')
                        break
                    if event.event=='answer.delta':
                        partial.append(event.data['text'])
                    is_term = event.event in ('answer.completed','answer.failed')
                    # Citation events are emitted only after the same atomic terminal commit.
                    await write(wire,terminal=is_term or event.event=='citation.resolved')
                    if is_term:
                        terminal = True
                        break
                if not terminal and not transport_failed:
                    await persist('READER_INTERRUPTED',True)
                    await failure('READER_INTERRUPTED','The answer was interrupted. Reload to see its saved state.')
                if not transport_failed:
                    await write(b'',final=True)
            except (TimeoutError, asyncio.CancelledError):
                raise
            except Exception:
                if not terminal and not transport_failed:
                    await persist('READER_FAILED',False)
                    try:
                        await failure('READER_FAILED','The answer could not be completed. Please submit a new question to retry.')
                        await write(b'',final=True)
                    except Exception:
                        pass

        async def disconnect():
            while True:
                if (await receive())['type']=='http.disconnect':
                    return

        producer = listener = None
        deadline = time.monotonic() + RUN_SECONDS
        grace_deadline = deadline + LEASE_GRACE_SECONDS
        try:
            async with asyncio.timeout_at(deadline):
                await send({'type':'http.response.start','status':self.status_code,'headers':self.raw_headers})
            runner = self.runner
            if runner is None:
                from researcy.agents.reader import run_reader
                generator = run_reader(self.reservation,self.document,self.settings,deadline=deadline)
            else:
                generator = runner(self.reservation,self.document,self.settings)
            producer = asyncio.create_task(produce())
            listener = asyncio.create_task(disconnect())
            async with asyncio.timeout_at(grace_deadline):
                done,_ = await asyncio.wait((producer,listener),return_when=asyncio.FIRST_COMPLETED)
                if listener in done and not terminal:
                    transport_failed = True
                if producer in done:
                    await producer
        except TimeoutError:
            transport_failed = True
        except asyncio.CancelledError:
            transport_failed = True
            raise
        finally:
            tasks = [task for task in (producer,listener) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if generator is not None:
                await generator.aclose()
            if not terminal or transport_failed:
                await persist('READER_INTERRUPTED',True)
