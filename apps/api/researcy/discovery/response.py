import asyncio
import json
import logging
from threading import Event
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.types import Receive,Scope,Send

from researcy.agents.discovery import run_discovery
from researcy.config import Settings
from researcy.errors import APIError
from .models import ActiveMetadata,DiscoveryReservation
from .repository import reserve_discovery,finish_discovery,abandon_unpublished_discovery
from .runtime import database


class DiscoveryJSONResponse(Response):
    def __init__(self,request: Request,source: ActiveMetadata,settings: Settings,*,started: float,deadline: float) -> None:
        super().__init__(media_type='application/json',headers={'Cache-Control':'no-store'})
        self.request=request
        self.source=source
        self.settings=settings
        self.started=started
        self.deadline=deadline
        self.cancel=Event()
        self.reservation: DiscoveryReservation | None=None
        self.graph_started=False

    async def __call__(self,scope: Scope,receive: Receive,send: Send) -> None:
        def reserve(conn):
            self.reservation=reserve_discovery(conn,self.source,str(self.request.state.request_id))
            return self.reservation
        async def produce():
            reservation=await database(reserve,deadline=self.deadline,cancel=self.cancel)
            if self.cancel.is_set():
                raise asyncio.CancelledError()
            if time.monotonic()>=self.deadline:
                raise APIError(504,'DISCOVERY_TIMEOUT','The related-paper search exceeded its time limit.')
            self.graph_started=True
            return await run_discovery(reservation,self.settings,started=self.started,deadline=self.deadline,cancel=self.cancel)
        async def disconnect():
            while True:
                if (await receive())['type']=='http.disconnect':
                    self.cancel.set()
                    return
        listener=asyncio.create_task(disconnect())
        producer=asyncio.create_task(produce())
        sender=None
        interrupted=False
        timed_out=False
        published=False
        response_started=False
        async def publish(response,deadline):
            nonlocal sender,interrupted,published,response_started
            async def guarded_send(message):
                nonlocal published,response_started
                if self.cancel.is_set():
                    raise asyncio.CancelledError()
                if response.status_code==200 and time.monotonic()>=deadline:
                    raise TimeoutError()
                if message['type']=='http.response.start':
                    response_started=True
                await send(message)
                if message['type']=='http.response.body' and not message.get('more_body',False):
                    published=True
            response.headers['Cache-Control']='no-store'
            sender=asyncio.create_task(response(scope,receive,guarded_send))
            done,_=await asyncio.wait({listener,sender},timeout=max(0,deadline-time.monotonic()),return_when=asyncio.FIRST_COMPLETED)
            # A completed final-body send wins over the ensuing normal disconnect/EOF.
            if published or sender in done and not sender.cancelled():
                await sender
            elif self.cancel.is_set() or listener in done:
                interrupted=True
                sender.cancel()
            else:
                sender.cancel()
                await asyncio.gather(sender,return_exceptions=True)
                raise TimeoutError()
        async def timeout_response():
            error=APIError(504,'DISCOVERY_TIMEOUT','The related-paper search exceeded its time limit.')
            return await self.request.app.exception_handlers[APIError](self.request,error)
        try:
            done,_=await asyncio.wait({listener,producer},timeout=max(0,self.deadline-time.monotonic()),return_when=asyncio.FIRST_COMPLETED)
            if self.cancel.is_set() or listener in done:
                interrupted=True
                producer.cancel()
            elif producer in done:
                try:
                    value=await producer
                    response=JSONResponse(value.model_dump(mode='json'))
                except APIError as error:
                    response=await self.request.app.exception_handlers[APIError](self.request,error)
                await publish(response,self.deadline if response.status_code==200 else self.deadline+15)
            else:
                raise TimeoutError()
        except TimeoutError:
            timed_out=True
            producer.cancel()
            await asyncio.gather(producer,return_exceptions=True)
            if self.reservation is not None:
                await database(abandon_unpublished_discovery,self.reservation,state='failed',
                    error_code='DISCOVERY_TIMEOUT',deadline=self.deadline+15)
            if not self.cancel.is_set() and not response_started:
                await publish(await timeout_response(),self.deadline+15)
        except (asyncio.CancelledError,OSError):
            interrupted=True
            self.cancel.set()
            producer.cancel()
        finally:
            listener.cancel()
            if not producer.done(): producer.cancel()
            if sender is not None and not sender.done(): sender.cancel()
            await asyncio.gather(listener,producer,*([sender] if sender is not None else []),return_exceptions=True)
            if self.reservation is not None:
                state='interrupted' if interrupted else 'failed'
                code='DISCOVERY_INTERRUPTED' if interrupted else 'DISCOVERY_TIMEOUT' if timed_out else 'INTERNAL_ERROR'
                if not self.graph_started:
                    await database(finish_discovery,self.reservation,state=state,
                        metrics={'latency_ms':round((time.monotonic()-self.started)*1000),'generation_attempts':0,
                            'physical_generation_requests':0,'metadata_searches':0,'returned':0,'status':'unknown'},
                        error_code=code,deadline=self.deadline+15)
                elif not published:
                    await database(abandon_unpublished_discovery,self.reservation,state=state,error_code=code,deadline=self.deadline+15)
                def log_terminal(conn):
                    row=conn.execute('SELECT state,usage FROM discovery_runs WHERE owner_id=%s AND id=%s',
                        (self.source.owner_id,self.reservation.run_id)).fetchone()
                    if row is not None:
                        logging.getLogger('researcy').info(json.dumps({'role':'discovery',
                            'run_id':str(self.reservation.run_id),'request_id':self.reservation.request_id,
                            'paper_id':str(self.source.paper_id),'document_version':str(self.source.document_version),
                            'configured_provider':self.settings.generation_provider,'configured_model':self.settings.generation_model,
                            'repair_calls':0,**row[1],'terminal_state':row[0],'response_published':published}))
                try:
                    await database(log_terminal,deadline=self.deadline+15)
                except Exception:
                    logging.getLogger('researcy').warning(json.dumps({'role':'discovery',
                        'run_id':str(self.reservation.run_id),'request_id':self.reservation.request_id,
                        'terminal_observation':'unavailable','response_published':published}))
